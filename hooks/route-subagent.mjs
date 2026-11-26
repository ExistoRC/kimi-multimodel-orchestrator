import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OVERRIDE_FILENAME = 'multimodel-orchestrator.routing.json';
const MODE_TIERS = {
  single: ['L1'],
  'two-tier': ['L1', 'L2'],
  modality: ['any'],
  auto: ['L1', 'L2'],
};
const MODALITIES = new Set(['text', 'image', 'video']);
const PERMISSIONS = new Set(['read', 'write', 'verify']);
const TASK_ID = /^[A-Za-z0-9._-]{1,128}$/;
const METADATA = /<!--\s*KIMI_MULTIMODEL_TASK\s*([\s\S]*?)-->/g;

function block(message) {
  console.error(`[kimi-multimodel-orchestrator] ${message}`);
  process.exitCode = 2;
}

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readJson(filename) {
  const text = await readFile(filename, 'utf8');
  return JSON.parse(text);
}

function migrateLegacyRouting(config) {
  const migrated = structuredClone(config);
  const aliases = { 'worker-l3': 'worker-l2', 'worker-vision-deep': 'worker-vision' };
  if (isRecord(migrated.models)) {
    for (const [legacy, replacement] of Object.entries(aliases)) {
      if (!Object.hasOwn(migrated.models, legacy)) continue;
      if (!Object.hasOwn(migrated.models, replacement)) migrated.models[replacement] = migrated.models[legacy];
      delete migrated.models[legacy];
    }
  }
  for (const tableName of ['routes', 'autoRoutes']) {
    const table = migrated[tableName];
    if (!isRecord(table)) continue;
    if (table.L3 && !table.L2) table.L2 = table.L3;
    delete table.L3;
    for (const routes of Object.values(table)) {
      if (!isRecord(routes)) continue;
      for (const [modality, alias] of Object.entries(routes)) {
        if (alias in aliases) routes[modality] = aliases[alias];
      }
    }
  }
  return migrated;
}

async function loadRouting() {
  const home = process.env.KIMI_CODE_HOME;
  if (home) {
    const override = path.join(home, OVERRIDE_FILENAME);
    try {
      return migrateLegacyRouting(await readJson(override));
    } catch (error) {
      if (error?.code !== 'ENOENT') {
        throw new Error(`无法读取用户路由配置 ${override}：${error.message}`);
      }
    }
  }
  return migrateLegacyRouting(await readJson(path.join(PLUGIN_ROOT, 'routing.json')));
}

function tiersFor(config) {
  if (!isRecord(config)) {
    throw new Error('路由配置必须是对象');
  }
  if (config.version === 1) return ['L1', 'L2'];
  if (config.version !== 2) throw new Error('路由配置的 version 必须为 1 或 2');
  const tiers = MODE_TIERS[config.mode];
  if (!tiers) throw new Error('version 2 路由的 mode 必须为 single、two-tier、modality 或 auto');
  return tiers;
}

function validateRouting(config) {
  const tiers = tiersFor(config);
  if (!isRecord(config.managedAgents) || Object.keys(config.managedAgents).length === 0) {
    throw new Error('路由配置必须包含非空 managedAgents 对象');
  }
  for (const [profile, permission] of Object.entries(config.managedAgents)) {
    if (!profile || !PERMISSIONS.has(permission)) {
      throw new Error(`Agent ${profile} 的权限档无效：${permission}`);
    }
  }
  if (!isRecord(config.models) || Object.keys(config.models).length === 0) {
    throw new Error('路由配置必须包含非空 models 对象');
  }
  for (const [alias, definition] of Object.entries(config.models)) {
    if (!alias || !isRecord(definition) || !Array.isArray(definition.modalities)) {
      throw new Error(`模型 ${alias} 必须声明 modalities 数组`);
    }
    const modalities = new Set(definition.modalities);
    if (modalities.size !== definition.modalities.length || modalities.size === 0) {
      throw new Error(`模型 ${alias} 的 modalities 不能为空或包含重复项`);
    }
    for (const modality of modalities) {
      if (!MODALITIES.has(modality)) {
        throw new Error(`模型 ${alias} 包含未知模态：${modality}`);
      }
    }
  }
  if (!isRecord(config.routes)) {
    throw new Error('路由配置必须包含 routes 对象');
  }
  for (const tier of tiers) {
    if (!isRecord(config.routes[tier])) {
      throw new Error(`缺少 ${tier} 路由`);
    }
    for (const modality of MODALITIES) {
      const alias = config.routes[tier][modality];
      if (typeof alias !== 'string' || !Object.hasOwn(config.models, alias)) {
        throw new Error(`${tier}/${modality} 指向了未声明的模型：${alias}`);
      }
      if (!config.models[alias].modalities.includes(modality)) {
        throw new Error(`${tier}/${modality} 的模型 ${alias} 未声明支持该模态`);
      }
    }
  }
  return config;
}

function metadataFrom(prompt) {
  if (typeof prompt !== 'string') {
    throw new Error('受管分派缺少 prompt/prompt_template 文本');
  }
  const matches = [...prompt.matchAll(METADATA)];
  if (matches.length !== 1) {
    throw new Error('受管分派必须且只能包含一个 KIMI_MULTIMODEL_TASK 元数据块');
  }
  let metadata;
  try {
    metadata = JSON.parse(matches[0][1].trim());
  } catch (error) {
    throw new Error(`任务元数据不是合法 JSON：${error.message}`);
  }
  if (!isRecord(metadata)) {
    throw new Error('任务元数据必须是 JSON 对象');
  }
  return metadata;
}

function validateDispatch(input, config) {
  const profile = input.subagent_type;
  const permission = config.managedAgents[profile];
  const prompt = input.prompt ?? input.prompt_template;
  const metadata = metadataFrom(prompt);
  const required = ['task_id', 'tier', 'modality', 'profile', 'permission', 'selection', 'model'];
  for (const field of required) {
    if (typeof metadata[field] !== 'string' || metadata[field].length === 0) {
      throw new Error(`任务元数据缺少字符串字段 ${field}`);
    }
  }
  if (!TASK_ID.test(metadata.task_id)) {
    throw new Error('task_id 只能包含字母、数字、点、下划线和连字符，且最长 128 字符');
  }
  const tiers = tiersFor(config);
  if (!tiers.includes(metadata.tier)) {
    throw new Error(`当前模式不接受任务等级 ${metadata.tier}；可选 ${tiers.join('、')}`);
  }
  if (!MODALITIES.has(metadata.modality)) {
    throw new Error(`未知模态 ${metadata.modality}；可选 text、image、video`);
  }
  if (metadata.profile !== profile) {
    throw new Error(`元数据 profile=${metadata.profile} 与 subagent_type=${profile} 不一致`);
  }
  if (metadata.permission !== permission) {
    throw new Error(`${profile} 的权限档必须为 ${permission}，不能写为 ${metadata.permission}`);
  }
  if (metadata.selection !== 'auto' && metadata.selection !== 'manual') {
    throw new Error('selection 必须为 auto 或 manual');
  }
  if (metadata.model !== input.model) {
    throw new Error(`元数据 model=${metadata.model} 与工具参数 model=${input.model} 不一致`);
  }
  const definition = config.models[metadata.model];
  if (definition === undefined) {
    throw new Error(`模型 ${metadata.model} 不在路由配置中`);
  }
  if (!definition.modalities.includes(metadata.modality)) {
    throw new Error(`模型 ${metadata.model} 未声明支持 ${metadata.modality}`);
  }
  if (metadata.selection === 'auto' && config.mode !== 'auto') {
    const expected = config.routes[metadata.tier][metadata.modality];
    if (metadata.model !== expected) {
      throw new Error(`${metadata.tier}/${metadata.modality} 自动路由应使用 ${expected}，而不是 ${metadata.model}`);
    }
  }
}

async function main() {
  let raw = '';
  for await (const chunk of process.stdin) {
    raw += chunk;
  }
  const payload = JSON.parse(raw);
  const input = payload.tool_input;
  if (!isRecord(input)) {
    throw new Error('Hook 负载缺少 tool_input 对象');
  }
  if (input.resume || (payload.tool_name === 'AgentSwarm' && !Array.isArray(input.items))) {
    return;
  }
  const profile = input.subagent_type ?? 'coder';
  let config;
  try {
    config = validateRouting(await loadRouting());
  } catch (error) {
    if (typeof profile === 'string' && profile.startsWith('mm-')) {
      throw error;
    }
    return;
  }
  if (typeof profile !== 'string' || !Object.hasOwn(config.managedAgents, profile)) {
    return;
  }
  validateDispatch(input, config);
}

main().catch((error) => {
  block(error instanceof Error ? error.message : String(error));
});

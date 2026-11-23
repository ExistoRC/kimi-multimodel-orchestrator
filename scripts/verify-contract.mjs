import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const errors = [];

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function fail(message) {
  errors.push(message);
}

function parseArguments(argv) {
  const options = { root: process.cwd(), contract: 'orchestration.contract.json' };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help' || argument === '-h') return { help: true };
    if (argument !== '--root' && argument !== '--contract') throw new Error(`未知参数：${argument}`);
    const value = argv[index + 1];
    if (!value) throw new Error(`${argument} 缺少路径`);
    options[argument.slice(2)] = value;
    index += 1;
  }
  return options;
}

function projectFile(root, value, label) {
  if (!nonEmptyString(value)) {
    fail(`${label} 必须是非空相对路径`);
    return undefined;
  }
  if (path.isAbsolute(value) || path.win32.isAbsolute(value) || value.includes('\0')) {
    fail(`${label} 不能是绝对路径或包含空字符：${value}`);
    return undefined;
  }
  const resolved = path.resolve(root, value);
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    fail(`${label} 越过项目根目录：${value}`);
    return undefined;
  }
  if (!existsSync(resolved) || !statSync(resolved).isFile()) {
    fail(`${label} 不存在或不是文件：${value}`);
    return undefined;
  }
  return resolved;
}

function sourceAt(root, value, label) {
  const filename = projectFile(root, value, label);
  return filename === undefined ? undefined : readFileSync(filename, 'utf8');
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function declaresExport(source, name) {
  const escaped = escapeRegExp(name);
  const declaration = new RegExp(`\\bexport\\s+(?:declare\\s+)?(?:default\\s+)?(?:async\\s+)?(?:function|class|const|let|var|type|interface|enum)\\s+${escaped}\\b`);
  const named = new RegExp(`\\bexport\\s*\\{[^}]*\\b${escaped}\\b[^}]*\\}`);
  return declaration.test(source) || named.test(source);
}

function checkExportName(name, label) {
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) fail(`${label} 不是受支持的导出名：${name}`);
}

function checkSecurity(security) {
  if (security === undefined) return;
  if (!isRecord(security)) {
    fail('security 必须是对象');
    return;
  }
  const expected = ['authenticate', 'authorize_scope', 'optimistic_lock', 'state_transition'];
  if (!Array.isArray(security.order) || security.order.length !== expected.length || security.order.some((step, index) => step !== expected[index])) {
    fail(`security.order 必须依次为 ${expected.join(' -> ')}`);
  }
  if (!Array.isArray(security.forbiddenErrorFields) || security.forbiddenErrorFields.some((field) => !nonEmptyString(field))) {
    fail('security.forbiddenErrorFields 必须是字符串数组');
  }
  if (!isRecord(security.reportScope) || Object.values(security.reportScope).some((scope) => !nonEmptyString(scope))) {
    fail('security.reportScope 必须是角色到数据域说明的非空字符串映射');
  }
}

function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    console.log('用法：node scripts/verify-contract.mjs [--root <项目目录>] [--contract <契约相对路径>]');
    return;
  }
  const root = path.resolve(options.root);
  const contractFile = projectFile(root, options.contract, '契约文件');
  if (!contractFile) return finish();
  let contract;
  try {
    contract = JSON.parse(readFileSync(contractFile, 'utf8'));
  } catch (error) {
    fail(`契约 JSON 无法解析：${error.message}`);
    return finish();
  }
  if (!isRecord(contract)) {
    fail('契约根节点必须是对象');
    return finish();
  }
  if (contract.contractVersion !== 1) fail('contractVersion 必须为 1');
  if (!isRecord(contract.canonical)) {
    fail('canonical 必须是对象');
    return finish();
  }
  const typesSource = sourceAt(root, contract.canonical.types, 'canonical.types');
  if (contract.canonical.schema !== undefined) sourceAt(root, contract.canonical.schema, 'canonical.schema');
  const exports = new Set();
  let exportCount = 0;
  if (!Array.isArray(contract.modules) || contract.modules.length === 0) {
    fail('modules 必须是非空数组');
  } else {
    for (const [moduleIndex, module] of contract.modules.entries()) {
      const label = `modules[${moduleIndex}]`;
      if (!isRecord(module)) {
        fail(`${label} 必须是对象`);
        continue;
      }
      const moduleSource = sourceAt(root, module.path, `${label}.path`);
      if (!nonEmptyString(module.owner)) fail(`${label}.owner 必须是非空字符串`);
      if (!isRecord(module.exports) || Object.keys(module.exports).length === 0) {
        fail(`${label}.exports 必须是非空的导出符号到契约类型映射`);
      } else {
        for (const [name, typeReference] of Object.entries(module.exports)) {
          exportCount += 1;
          checkExportName(name, `${label}.exports.${name}`);
          if (!nonEmptyString(typeReference)) {
            fail(`${label}.exports.${name} 的契约类型引用必须是非空字符串`);
            continue;
          }
          exports.add(name);
          if (moduleSource !== undefined && !declaresExport(moduleSource, name)) {
            fail(`${label}.path 未找到导出 ${name}`);
          }
          if (typesSource === undefined) {
            fail(`${label}.exports.${name} 需要 canonical.types 中的 ${typeReference}`);
          } else if (!declaresExport(typesSource, typeReference)) {
            fail(`canonical.types 未找到 ${typeReference}（${label}.exports.${name}）`);
          }
        }
      }
      if (!Array.isArray(module.tests) || module.tests.length === 0) {
        fail(`${label}.tests 必须至少包含一个指定单测文件`);
      } else {
        for (const [testIndex, testFile] of module.tests.entries()) {
          projectFile(root, testFile, `${label}.tests[${testIndex}]`);
        }
      }
    }
  }
  if (contract.routes !== undefined) {
    if (!Array.isArray(contract.routes)) {
      fail('routes 必须是数组');
    } else {
      for (const [routeIndex, route] of contract.routes.entries()) {
        const label = `routes[${routeIndex}]`;
        if (!isRecord(route)) {
          fail(`${label} 必须是对象`);
          continue;
        }
        if (!/^[A-Z]+$/.test(route.method || '')) fail(`${label}.method 必须是 HTTP 方法大写字符串`);
        if (!nonEmptyString(route.path) || !route.path.startsWith('/')) fail(`${label}.path 必须以 / 开头`);
        if (!exports.has(route.export)) fail(`${label}.export 未在 modules.exports 中声明：${route.export}`);
        if (route.httpTest !== 'required') fail(`${label}.httpTest 必须为 required，禁止绕过真实 HTTP 验收`);
        const httpSource = sourceAt(root, route.httpFile, `${label}.httpFile`);
        if (httpSource !== undefined) {
          if (!httpSource.includes(route.path)) fail(`${label}.httpFile 未找到路由路径 ${route.path}`);
          if (!httpSource.includes(route.export)) fail(`${label}.httpFile 未找到导出绑定 ${route.export}`);
        }
      }
    }
  }
  checkSecurity(contract.security);
  return finish(exportCount);
}

function finish(exportCount = 0) {
  if (errors.length) {
    for (const error of errors) console.error(`[contract] ${error}`);
    process.exitCode = 2;
    return;
  }
  console.log(JSON.stringify({ ok: true, exportCount, note: '结构与存在性检查通过；类型、HTTP 与业务探针仍需由主代理执行' }));
}

try {
  main();
} catch (error) {
  console.error(`[contract] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 2;
}

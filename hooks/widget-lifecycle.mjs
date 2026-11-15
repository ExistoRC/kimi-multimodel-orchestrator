import { spawn, spawnSync } from 'node:child_process';
import { access, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const HOME = process.env.KIMI_CODE_HOME || path.join(os.homedir(), '.kimi-code');
const DATA_DIR = path.join(HOME, 'multimodel-orchestrator');
const RUNTIME_FILE = path.join(DATA_DIR, 'runtime.json');
const SETTINGS_FILE = path.join(DATA_DIR, 'settings.json');
const action = process.argv[2]?.replace(/^--/, '') || 'show';
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function runtime() {
  try {
    return JSON.parse(await readFile(RUNTIME_FILE, 'utf8'));
  } catch {
    return undefined;
  }
}

async function request(action) {
  const current = await runtime();
  if (!current) return false;
  try {
    const endpoint = action ? '/command' : '/health';
    const response = await fetch(`http://${current.host}:${current.port}${endpoint}`, {
      method: action ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${current.token}`,
        'Content-Type': 'application/json',
      },
      body: action ? JSON.stringify({ action }) : undefined,
      signal: AbortSignal.timeout(1500),
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function exists(filename) {
  try {
    await access(filename);
    return true;
  } catch {
    return false;
  }
}

function supportsPySide6(executable) {
  const result = spawnSync(executable, ['-c', 'import PySide6'], { stdio: 'ignore', windowsHide: true });
  return result.status === 0;
}

async function runtimeStatus() {
  const running = await request();
  const venv = path.join(DATA_DIR, 'widget-venv', process.platform === 'win32' ? 'Scripts/pythonw.exe' : 'bin/python');
  const base = { running, platform: process.platform, platformVerified: process.platform === 'win32' };
  if (await exists(venv)) {
    const ready = supportsPySide6(venv);
    return { ...base, ready: running || ready, installRequired: !running && !ready, source: ready ? 'venv' : 'none', reason: ready ? null : 'pyside6_missing', executable: ready ? venv : undefined };
  }
  const candidates = process.platform === 'win32' ? ['pythonw', 'python', 'py'] : ['python3', 'python'];
  for (const candidate of candidates) {
    if (supportsPySide6(candidate)) {
      return { ...base, ready: true, installRequired: false, source: 'global', reason: null, executable: candidate };
    }
  }
  return { ...base, ready: running, installRequired: !running, source: 'none', reason: 'venv_missing', executable: undefined };
}

async function pythonExecutable() {
  const status = await runtimeStatus();
  if (status.executable) return status.executable;
  throw new Error('悬浮窗运行环境未安装。请先运行插件 scripts/install-widget.mjs 安装 PySide6。');
}

async function start() {
  const python = await pythonExecutable();
  const child = spawn(python, ['-m', 'widget.main'], {
    cwd: HOME,
    env: {
      ...process.env,
      KIMI_CODE_HOME: HOME,
      PYTHONPATH: [PLUGIN_ROOT, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    },
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  child.unref();
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await delay(250);
    if (await request()) return true;
  }
  throw new Error('悬浮窗启动超时；请检查桌面会话和 PySide6 运行环境。');
}

async function main() {
  if (!['ensure', 'show', 'hide', 'settings', 'quit', 'status'].includes(action)) {
    throw new Error(`未知悬浮窗操作：${action}`);
  }
  if (action === 'status') {
    const { executable: _, ...status } = await runtimeStatus();
    console.log(JSON.stringify(status));
    return;
  }
  if (action === 'ensure') {
    try {
      const settings = JSON.parse(await readFile(SETTINGS_FILE, 'utf8'));
      if (settings.auto_start === false) return;
    } catch {}
  }
  if (await request()) {
    if (action !== 'ensure') await request(action);
    return;
  }
  if (action === 'hide' || action === 'quit') return;
  await start();
  if (action !== 'ensure') await request(action);
}

main().then(
  () => undefined,
  (error) => {
    console.error(`[kimi-multimodel-orchestrator] ${error.message}`);
    process.exitCode = action === 'ensure' ? 0 : 1;
  },
);

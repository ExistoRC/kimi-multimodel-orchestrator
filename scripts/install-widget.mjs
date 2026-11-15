import { spawn } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const HOME = process.env.KIMI_CODE_HOME || path.join(os.homedir(), '.kimi-code');
const DATA_DIR = path.join(HOME, 'multimodel-orchestrator');
const VENV = path.join(DATA_DIR, 'widget-venv');
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: PLUGIN_ROOT,
      stdio: 'inherit',
      windowsHide: false,
      env: { ...process.env, PIP_CACHE_DIR: process.env.PIP_CACHE_DIR || path.join(DATA_DIR, 'pip-cache') },
    });
    child.once('error', reject);
    child.once('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with code ${code}`));
    });
  });
}

try {
  await run(PYTHON, ['-m', 'venv', VENV]);
  const python = path.join(VENV, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  await run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', path.join(PLUGIN_ROOT, 'requirements-widget.txt')]);
  await run(python, ['-c', 'from PySide6.QtWidgets import QApplication; print("PySide6 widget runtime: OK")']);
  console.log(`\n悬浮窗运行环境已安装到：${VENV}`);
  console.log('使用 /kimi-multimodel-orchestrator:widget 唤醒，或在新会话自动启动。');
} catch (error) {
  console.error(`悬浮窗运行环境安装失败：${error.message}`);
  process.exitCode = 1;
}

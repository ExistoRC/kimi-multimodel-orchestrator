import { readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

async function main() {
  let raw = '';
  for await (const chunk of process.stdin) {
    raw += chunk;
  }
  if (!raw) return;
  JSON.parse(raw);
  const home = process.env.KIMI_CODE_HOME || path.join(os.homedir(), '.kimi-code');
  const runtimeFile = path.join(home, 'multimodel-orchestrator', 'runtime.json');
  let runtime;
  try {
    runtime = JSON.parse(await readFile(runtimeFile, 'utf8'));
  } catch {
    return;
  }
  const base = `http://${runtime.host}:${runtime.port}`;
  try {
    await fetch(`${base}/event`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${runtime.token}`,
        'Content-Type': 'application/json',
      },
      body: raw,
      signal: AbortSignal.timeout(1500),
    });
  } catch {}
}

main().catch(() => undefined);

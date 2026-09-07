import { spawnSync } from 'node:child_process';

export function python(args) {
  const candidates = process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
  for (const command of candidates) {
    const probe = spawnSync(command, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'], { windowsHide: true });
    if (probe.status !== 0) continue;
    const result = spawnSync(command, args, { stdio: 'inherit', windowsHide: true });
    process.exit(result.status ?? 1);
  }
  console.error('Python 3.10+ is required. Install it and retry.');
  process.exit(1);
}

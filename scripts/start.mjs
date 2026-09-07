import { python } from './python.mjs';
python(['run.py', ...process.argv.slice(2)]);

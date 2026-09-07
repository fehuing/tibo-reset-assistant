import { python } from './python.mjs';
process.env.PYTHONPATH = 'ops';
python(['-m', 'unittest', 'discover', '-s', 'tests', '-v']);

"""Portable AI settings. Authentication stays in the CLI user's own home."""
import os
from pathlib import Path
import re

MODEL = os.getenv('CODEX_MODEL', 'gpt-6-astra').strip()
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', MODEL):
    raise ValueError('Invalid CODEX_MODEL')


def input_dir(state):
    return Path(state) / 'ai-input'


def analysis_dir(state):
    return Path(state) / 'ai-analysis'


def bounded_int(name, default, minimum, maximum):
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value

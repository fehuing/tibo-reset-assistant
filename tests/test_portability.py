import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collector import collect
from server import initialize

ROOT = Path(__file__).resolve().parents[1]


class PortableDefaultsTests(unittest.TestCase):
    def test_offline_collection_never_contacts_reference_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            initialize(ROOT, state)
            before = (state / 'data.json').read_bytes()
            with patch('collector.fetch_x_profile', side_effect=OSError('offline')), patch('collector.collect_fallback') as fallback:
                with self.assertRaises(RuntimeError):
                    collect(state / 'data.json', state / 'cache.json')
                fallback.assert_not_called()
            self.assertEqual((state / 'data.json').read_bytes(), before)

    def test_initialization_never_overwrites_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / 'data.json').write_text('{"my":"data"}')
            initialize(ROOT, state)
            self.assertEqual(json.loads((state / 'data.json').read_text()), {'my': 'data'})
            self.assertFalse((state / 'reactions.sqlite3').exists())

    def test_bundled_watch_never_contains_production_counts(self):
        data = json.loads((ROOT / 'sample-data/watch.json').read_text(encoding='utf-8'))
        self.assertEqual(set(data), {'schema_version', 'checked_at', 'watch'})

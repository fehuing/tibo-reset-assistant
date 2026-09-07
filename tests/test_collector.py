"""Regression checks for misleading or partially downloaded public data."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collector import attach_post_content, classify_reset, collect, merge_x_posts, parse_x_profile, transform

def row(ident="100", when="2026-09-01T00:00:00Z"):
    return {"id": ident, "reset_type": "regular", "announced_at": when, "text": "The limits have been reset.", "source": {"url": "https://x.com/thsottiaux/status/" + ident}}

class FeedSafetyTests(unittest.TestCase):
    def test_full_post_content_preserves_paragraphs_and_classification(self):
        baseline = transform({'data': {'stats': {'total': 1}}}, [row()], True)
        text = 'We reset Codex usage.\n\n' + 'Long announcement content. ' * 30 + 'The final sentence.'
        manifest = {'posts': {'100': {'status': 'ready', 'full_text': text, 'text_captured_at': '2026-09-05T00:00:00Z',
            'full_text_sha256': 'a' * 64, 'screenshot': {'file': '100-aaaaaaaaaaaaaaaa.jpg', 'source_url': row()['source']['url']}}}}
        result = attach_post_content(baseline, {}, manifest)['records'][0]
        self.assertEqual(result['full_text'], text)
        self.assertTrue(result['text_complete'])
        self.assertEqual(result['reset_type'], 'regular')
        self.assertEqual(result['announced_at'], row()['announced_at'])
        self.assertTrue(result['excerpt'].endswith('…'))
        self.assertEqual(result['screenshot']['file'], '100-aaaaaaaaaaaaaaaa.jpg')

    def test_unverified_source_body_is_not_marked_complete(self):
        baseline = transform({'data': {'stats': {'total': 1}}}, [row()], True)
        result = attach_post_content(baseline, {}, {})['records'][0]
        self.assertEqual(result['source_text'], row()['text'])
        self.assertFalse(result['text_complete'])
        self.assertNotIn('full_text', result)

    def test_full_text_is_published_while_screenshot_is_pending(self):
        baseline = transform({'data': {'stats': {'total': 1}}}, [row()], True)
        content = {'status':'text_ready','full_text':'Complete captured text','text_captured_at':'2026-09-01T00:00:00Z','full_text_sha256':'a'*64}
        result = attach_post_content(baseline, {}, {'posts':{'100':content}})['records'][0]
        self.assertTrue(result['text_complete'])
        self.assertEqual(result['full_text'],content['full_text'])
        self.assertNotIn('screenshot',result)

    def test_fallback_is_published_when_x_is_unavailable(self):
        status = {
            "data": {"stats": {"total": 1}, "latest_reset": {"id": "100"}},
            "meta": {"generated_at": "2026-09-01T00:01:00Z"},
        }
        page = {"data": [row()], "pagination": {"has_more": False}}
        with tempfile.TemporaryDirectory() as directory, patch(
            "collector.fetch_x_profile", side_effect=RuntimeError("X unavailable")
        ), patch("collector.fetch", side_effect=[status, page]):
            output = Path(directory) / "data.json"
            result = collect(output, Path(directory) / "cache.json", allow_fallback=True)
            published = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["source"]["active"], "codex_resets_fallback")
        self.assertTrue(result["source"]["fallback_used"])
        self.assertEqual(published["records"][0]["id"], "100")

    def test_failed_history_never_replaces_known_good_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data.json"
            output.write_text('{"known":"good"}')
            with patch("collector.fetch_x_profile", side_effect=RuntimeError("X unavailable")), patch(
                "collector.fetch", side_effect=[{"data": {"stats": {"total": 1}}}, RuntimeError("fallback unavailable")]
            ):
                with self.assertRaises(RuntimeError):
                    collect(output, Path(directory) / "cache.json", allow_fallback=True)
            self.assertEqual(output.read_text(), '{"known":"good"}')

    def test_parses_public_x_relay_payload(self):
        html = (
            'screen_name:"thsottiaux" '
            '__typename:"Tweet",rest_id:"123" '
            '__typename:"TBirdData",full_text:"We reset Codex usage.\\nEnjoy!",created_at_ms:1788477129000}'
        )
        posts = parse_x_profile(html)
        self.assertEqual(posts[0]["id"], "123")
        self.assertEqual(posts[0]["text"], "We reset Codex usage.\nEnjoy!")
        self.assertEqual(posts[0]["announced_at"], "2026-09-03T23:12:09Z")

    def test_classifier_requires_reset_and_usage_context(self):
        self.assertEqual(classify_reset("We reset usage for all paid Codex users"), "regular")
        self.assertEqual(classify_reset("You get one banked reset for your paid ChatGPT plan"), "banked")
        self.assertIsNone(classify_reset("I feel reset after sleeping"))
        self.assertIsNone(classify_reset("Codex usage is looking better"))

    def test_direct_x_merge_preserves_history_and_adds_only_reset_posts(self):
        baseline = transform({"data": {"stats": {"total": 1}}}, [row()], True)
        posts = [
            {"id": "101", "text": "We reset Codex usage for paid users", "announced_at": "2026-09-02T00:00:00Z", "source_url": "https://x.com/thsottiaux/status/101"},
            {"id": "102", "text": "A different AGI benchmark", "announced_at": "2026-09-03T00:00:00Z", "source_url": "https://x.com/thsottiaux/status/102"},
        ]
        result = merge_x_posts(baseline, posts, dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc))
        self.assertEqual([record["id"] for record in result["records"]], ["101", "100"])
        self.assertEqual(result["source"]["active"], "x_direct")
        self.assertEqual(result["source"]["recent_posts_seen"], 2)

    def test_rejects_untrusted_source_and_mismatched_snapshots(self):
        status = {"data": {"stats": {"total": 1}}}
        bad = row()
        bad["source"]["url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            transform(status, [bad], True)
        with self.assertRaises(ValueError):
            transform({"data": {"stats": {"total": 2}}}, [row()], True)

    def test_timezone_aware_intervals_and_id_deduplication(self):
        newest = row("102", "2026-09-02T08:00:00+08:00")
        previous = row("101", "2026-09-01T00:00:00Z")
        result = transform({"data": {"stats": {"total": 2}}}, [previous, newest, newest], True)
        self.assertEqual([r["id"] for r in result["records"]], ["102", "101"])
        self.assertEqual(result["stats"]["longest_interval_days"], 1.0)
        self.assertEqual(result["stats"]["avg_interval_days"], 1.0)

    def test_observed_record_is_not_misrepresented_as_a_post(self):
        observed = row()
        observed["id"] = "observed-20260825T143200Z"
        observed["source"]["type"] = "observed"
        result = transform({"data": {"stats": {"total": 1}}}, [observed], True)
        self.assertEqual(result["records"][0]["source_type"], "observed")

if __name__ == "__main__":
    unittest.main()

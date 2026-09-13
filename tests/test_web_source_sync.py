"""Behavior checks for the portable web projections (requires npm ci)."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for the web projection checks')
class WebSourceSyncTests(unittest.TestCase):
    def test_calendar_time_and_portable_archive_contract(self):
        script = r"""
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const cache = new Map();
function load(file) {
  file = path.resolve(file);
  if (cache.has(file)) return cache.get(file).exports;
  if (file.endsWith('.json')) return JSON.parse(fs.readFileSync(file, 'utf8'));
  const mod = { exports: {} }; cache.set(file, mod);
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true, jsx: ts.JsxEmit.ReactJSX }
  }).outputText;
  const localRequire = id => {
    if (!id.startsWith('.') && !id.startsWith('@/')) return require(id);
    let target = id.startsWith('@/') ? path.resolve(id.slice(2)) : path.resolve(path.dirname(file), id);
    if (!path.extname(target)) target += '.ts';
    return load(target);
  };
  new Function('require', 'module', 'exports', output)(localRequire, mod, mod.exports);
  return mod.exports;
}
const { calendarDateKey, calendarWindow, projectCalendar } = load('lib/calendar-history.ts');
const { latestReset, confirmedResetAt } = load('lib/latest-reset.ts');
const { postScreenshot, postText } = load('lib/post-content.ts');
const { translationMessage } = load('lib/translation.ts');
const { statusView } = load('lib/announcements.ts');
const { collectionIssue, validCollectionStatus } = load('lib/collection-status.ts');
const { CollectionNotice } = load('components/collection-notice.tsx');
const seed = load('lib/calendar-history.json');
assert.equal(calendarDateKey(Date.parse('2026-09-13T16:00:00Z')), '2026-09-14');
assert.equal(calendarDateKey(Date.parse('2026-09-13T15:59:59Z')), '2026-09-13');
const calendarFrame = calendarWindow(Date.parse('2026-09-14T12:00:00+08:00'));
assert.ok(calendarFrame.columns >= 26 && calendarFrame.columns <= 27);
assert.equal(new Date(calendarFrame.first + 8 * 3600000).getUTCDay(), 0);
assert.equal(calendarDateKey(calendarFrame.end), '2026-09-14');
assert.equal(projectCalendar([], []).length, seed.records.length);
const id = '2099999999999999999', hash = 'a'.repeat(64);
const base = { id, reset_type: 'regular', announced_at: '2026-09-14T10:00:00Z', excerpt: 'A future reset', source_type: 'x_post', source_url: `https://x.com/thsottiaux/status/${id}` };
const planned = { ...base, status: 'planned' };
const delivered = { ...base, status: 'announced', reset_confirmation: { method: 'private_reset_report', kind: 'official', reset_at: '2026-09-14T16:01:00Z' } };
const event = { record_id: id, announced_at: base.announced_at, status: 'announced' };
assert.equal(projectCalendar([planned], [{...event, status: 'planned'}]).length, seed.records.length);
const projected = projectCalendar([delivered], [event]);
assert.equal(projected.length, seed.records.length + 1);
assert.equal(projected[0].announced_at, delivered.reset_confirmation.reset_at);
assert.equal(delivered.announced_at, base.announced_at, 'Projection must preserve the source timestamp');
assert.equal(latestReset([planned], Date.parse('2026-09-15T00:00:00Z')), null);
assert.equal(latestReset([delivered], Date.parse('2026-09-15T00:00:00Z')).at, delivered.reset_confirmation.reset_at);
assert.equal(latestReset([{...delivered, reset_confirmation: {...delivered.reset_confirmation, kind: 'manual'}}], Date.parse('2026-09-15T00:00:00Z')).at, null);
const snapshot = { ...delivered, announced_at: '2026-09-12T03:20:00Z',
  historical_verification: {method: 'site_owner_verified_history', initialized_at: '2026-09-13T00:00:00Z', baseline_sha256: hash, status: 'announced'},
  reset_confirmation: {method: 'historical_public_snapshot', kind: 'official', reset_at: '2026-09-12T08:31:00Z', verified_at: '2026-09-13T00:00:00Z'}
};
assert.equal(latestReset([snapshot], Date.parse('2026-09-13T00:00:00Z')).at, '2026-09-12T08:31:00Z', 'The public snapshot must show 16:31 Beijing reset time, not the 11:20 announcement');
assert.match(statusView(snapshot, 'zh').note, /16:31/);
assert.equal(confirmedResetAt({...snapshot, historical_verification: undefined}), null);
assert.equal(confirmedResetAt({...snapshot, reset_confirmation: {...snapshot.reset_confirmation, kind: 'manual'}}), null);
assert.equal(confirmedResetAt({...snapshot, reset_confirmation: {...snapshot.reset_confirmation, verified_at: 'invalid'}}), null);
assert.equal(confirmedResetAt({...snapshot, reset_confirmation: {...snapshot.reset_confirmation, reset_at: 'invalid'}}), null);
const futureSnapshot = {...snapshot, announced_at: base.announced_at, reset_confirmation: {...snapshot.reset_confirmation, reset_at: delivered.reset_confirmation.reset_at}};
assert.equal(projectCalendar([futureSnapshot], [event])[0].announced_at, delivered.reset_confirmation.reset_at);
const stage = {state: 'ok', code: 'ok', checked_at: '2026-09-14T00:00:00Z', last_success_at: '2026-09-14T00:00:00Z'};
const diagnostics = {schema_version: 1, enabled: true, state: 'degraded', source_url: 'https://x.com/thsottiaux', interval_seconds: 120, next_check_at: null, stale: false, stages: {feed: stage, watch: stage}};
const { renderToStaticMarkup } = require('react-dom/server');
const { createElement } = require('react');
for (const code of ['model_auth_required', 'model_rate_limited', 'model_timeout', 'model_unavailable', 'invalid_result_schema']) {
  const status = {...diagnostics, stages: {...diagnostics.stages, analysis: {...stage, state: 'error', code}}};
  assert.equal(validCollectionStatus(status), true);
  assert.equal(collectionIssue(status).key, 'analysis');
  for (const locale of ['zh', 'en']) {
    const html = renderToStaticMarkup(createElement(CollectionNotice, {status, locale, snapshot: false}));
    assert.match(html, /Codex/);
    assert.ok(!html.includes('暂时无法从 Tibo 的 X 页面获取最新公告'));
    assert.ok(!html.includes('Latest announcements could not be collected'));
  }
}
assert.equal(validCollectionStatus({...diagnostics, stages: {...diagnostics.stages, analysis: {...stage, checked_at: 'invalid'}}}), false);
const record = { ...delivered, text_complete: true, full_text: 'Complete source', full_text_sha256: hash,
  translation_zh: { source_sha256: hash, text: '完整正文' },
  screenshot: { file: `${id}-${hash.slice(0, 16)}.jpg`, sha256: hash, source_url: base.source_url, captured_at: '2026-09-14T11:00:00Z', width: 600, height: 800 }
};
global.window = { location: { pathname: '/' } };
assert.equal(postScreenshot(record).url, `/post-images/${record.screenshot.file}`);
global.window.location.pathname = '/radar/';
assert.equal(postScreenshot(record).url, `/radar/post-images/${record.screenshot.file}`);
assert.equal(postScreenshot({...record, screenshot: {...record.screenshot, file: '../../secret.jpg'}}), null);
assert.equal(postText(record).translation, '完整正文');
assert.equal(postText({...record, full_text_sha256: 'b'.repeat(64)}).translation, '');
assert.equal(translationMessage(record, 'zh'), '');
assert.match(translationMessage({...record, translation_zh: undefined, translation_status: {state: 'retrying', source_sha256: hash}}, 'zh'), /自动重试/);
console.log(JSON.stringify({calendarSeedCount: seed.records.length, result: 'passed'}));
"""
        result = subprocess.run(['node', '-e', script], cwd=ROOT, text=True,
                                encoding='utf-8', capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['result'], 'passed')


if __name__ == '__main__':
    unittest.main()

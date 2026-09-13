"""Publish Reset Radar data from Tibo's public X timeline, with API fallback.

The primary source is the server-rendered public profile at x.com/thsottiaux.
It exposes recent original posts without account credentials.  Existing verified
history is retained and new reset announcements are merged atomically.  The
Codex Resets read-only API is queried only when the X page cannot be read or
parsed, or when a fresh installation needs its historical baseline.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from announcement_semantics import annotate_records, build_events
from post_briefs import attach_briefs
from collection_status import XCollectionError, diagnose

FALLBACK_ORIGIN = "https://codex-resets.com"
X_PROFILE_URL = "https://x.com/thsottiaux"
MAX_BYTES = 2 * 1024 * 1024
SOURCE_PATTERN = re.compile(r"https://x\.com/thsottiaux/status/[0-9]+")
TWEET_START = re.compile(r'__typename:"Tweet",rest_id:"([0-9]+)"')
TWEET_DETAILS = re.compile(
    r'__typename:"TBirdData".*?full_text:"((?:\\.|[^"\\])*)".*?created_at_ms:([0-9]+)',
    re.DOTALL,
)
RESET_TERM = re.compile(r"\breset[a-z]*\b", re.IGNORECASE)
RESET_CONTEXT = re.compile(
    r"\b(codex|chatgpt|usage|limit|limits|paid|subscription|subscriptions|"
    r"account|accounts|user|users|banked|credit|credits|allowance|allowances)\b",
    re.IGNORECASE,
)
BANKED_TERM = re.compile(r"\b(banked reset|reset card|saved reset|banked credit)\b", re.IGNORECASE)


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("Refusing an unexpectedly large feed")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def fetch(path, cache):
    """Fetch one fallback API object, preserving its ETag response cache."""
    cached = cache.get(path, {})
    headers = {"User-Agent": "ResetRadar/2.0 (fallback announcement reader)", "Accept": "application/json"}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    request = urllib.request.Request(FALLBACK_ORIGIN + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Fallback response exceeds size limit")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Fallback source did not return a JSON object")
            cache[path] = {"etag": response.headers.get("ETag"), "body": data}
            return data
    except urllib.error.HTTPError as error:
        if error.code == 304 and isinstance(cached.get("body"), dict):
            return cached["body"]
        if error.code == 429:
            raise RuntimeError("Fallback source rate limited the request") from error
        raise


def fetch_x_profile():
    request = urllib.request.Request(
        X_PROFILE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if urllib.parse.urlparse(response.geturl()).hostname not in ("x.com", "www.x.com"):
            raise ValueError("Unexpected X redirect")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("X profile response exceeds size limit")
        return raw.decode("utf-8", errors="replace")


def _decode_flight_string(value):
    try:
        decoded = json.loads('"' + value + '"')
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid encoded post text") from error
    if not isinstance(decoded, str) or not decoded.strip():
        raise ValueError("Missing post text")
    return decoded


def parse_x_profile(html):
    """Extract recent original posts from X's server-rendered Relay payload."""
    if not isinstance(html, str) or 'screen_name:"thsottiaux"' not in html:
        raise ValueError("X profile identity was not present")
    starts = list(TWEET_START.finditer(html))
    posts = []
    seen = set()
    for index, start in enumerate(starts):
        ident = start.group(1)
        if ident in seen:
            continue
        seen.add(ident)
        end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        details = TWEET_DETAILS.search(html, start.end(), end)
        if not details:
            continue
        timestamp = dt.datetime.fromtimestamp(int(details.group(2)) / 1000, tz=dt.timezone.utc)
        posts.append({
            "id": ident,
            "text": _decode_flight_string(details.group(1)),
            "announced_at": timestamp.isoformat().replace("+00:00", "Z"),
            "source_url": "https://x.com/thsottiaux/status/" + ident,
        })
    if not posts:
        raise ValueError("No recent X posts could be parsed")
    return posts


def classify_reset(text):
    """Return the reset category for explicit usage-reset announcements."""
    if not isinstance(text, str) or not RESET_TERM.search(text) or not RESET_CONTEXT.search(text):
        return None
    return "banked" if BANKED_TERM.search(text) else "regular"


def parse_date(value):
    timestamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Announcement time must include a timezone")
    return timestamp


def _excerpt(text):
    words = text.split()
    return " ".join(words[:20]) + ("…" if len(words) > 20 else "")


def _feed(records, now, source, source_generated_at=None):
    unique = {record["id"]: record for record in records}
    ordered = sorted(unique.values(), key=lambda row: parse_date(row["announced_at"]), reverse=True)
    intervals = [
        (parse_date(ordered[i]["announced_at"]) - parse_date(ordered[i + 1]["announced_at"])).total_seconds() / 86400
        for i in range(len(ordered) - 1)
    ]
    mean = sum(intervals) / len(intervals) if intervals else None
    maximum = max(intervals) if intervals else None
    if mean is not None and (not math.isfinite(mean) or mean < 0):
        raise ValueError("Invalid calculated interval")
    return {
        "schema_version": 1,
        "checked_at": now.isoformat(),
        "source_generated_at": source_generated_at,
        "history_complete": True,
        "source": source,
        "records": ordered,
        "stats": {
            "total": len(ordered),
            "avg_interval_days": round(mean, 1) if mean is not None else None,
            "longest_interval_days": round(maximum, 1) if maximum is not None else None,
        },
    }


def transform(status, rows, complete, now=None):
    """Validate and transform the fallback API history."""
    status_data = status.get("data")
    if not isinstance(status_data, dict) or not isinstance(status_data.get("stats"), dict):
        raise ValueError("Invalid fallback status response")
    records = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid fallback record")
        ident = row.get("id")
        source = row.get("source", {}).get("url", "")
        kind = row.get("reset_type")
        source_type = row.get("source", {}).get("type", "x_post")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident) or not SOURCE_PATTERN.fullmatch(source):
            raise ValueError("Invalid fallback identity or source link")
        if source_type not in ("x_post", "observed") or (source_type == "x_post" and not source.endswith("/" + ident)):
            raise ValueError("Fallback source type and identity disagree")
        if kind not in ("regular", "banked"):
            raise ValueError("Unknown reset category")
        announced = row.get("announced_at")
        parse_date(announced)
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Missing announcement text")
        records.append({"id": ident, "reset_type": kind, "announced_at": announced, "excerpt": _excerpt(text), "source_text": text,
                        "source_url": source, "source_type": source_type})
    total = status_data["stats"].get("total")
    if not isinstance(total, int) or total < 0 or (complete and total != len({row["id"] for row in records})):
        raise ValueError("Fallback total and history disagree")
    latest = status_data.get("latest_reset")
    ordered = sorted(records, key=lambda row: parse_date(row["announced_at"]), reverse=True)
    if latest and ordered and latest.get("id") != ordered[0]["id"]:
        raise ValueError("Fallback source changed during collection")
    return _feed(
        ordered,
        now or dt.datetime.now(dt.timezone.utc),
        {"active": "codex_resets_fallback", "primary": X_PROFILE_URL, "fallback": FALLBACK_ORIGIN, "fallback_used": True},
        status.get("meta", {}).get("generated_at"),
    )


def collect_fallback(cache):
    status = fetch("/api/v1/status", cache)
    rows = []
    path = "/api/v1/resets?limit=100&order=desc"
    visited = set()
    for _ in range(10):
        if path in visited:
            raise ValueError("Repeated fallback history cursor")
        visited.add(path)
        page = fetch(path, cache)
        if not isinstance(page.get("data"), list) or not isinstance(page.get("pagination"), dict):
            raise ValueError("Invalid fallback history response")
        rows.extend(page["data"])
        if not page["pagination"].get("has_more"):
            return transform(status, rows, True), visited
        cursor = page["pagination"].get("next_cursor")
        if not isinstance(cursor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", cursor):
            raise ValueError("Invalid fallback history cursor")
        path = "/api/v1/resets?limit=100&order=desc&cursor=" + urllib.parse.quote(cursor, safe="")
    raise ValueError("Fallback history exceeded the 1000-record safety limit")


def merge_x_posts(existing, posts, now=None):
    records = existing.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("A verified historical baseline is required")
    merged = []
    for record in records:
        if not isinstance(record, dict) or not SOURCE_PATTERN.fullmatch(str(record.get("source_url", ""))):
            raise ValueError("Existing feed contains an invalid record")
        merged.append(record)
    matched = 0
    for post in posts:
        kind = classify_reset(post["text"])
        if not kind:
            continue
        matched += 1
        merged.append({
            "id": post["id"],
            "reset_type": kind,
            "announced_at": post["announced_at"],
            "excerpt": _excerpt(post["text"]),
            "source_text": post["text"],
            "source_url": post["source_url"],
            "source_type": "x_post",
            **({'in_reply_to_status_id': post['in_reply_to_status_id']} if post.get('in_reply_to_status_id') else {}),
        })
    return _feed(
        merged,
        now or dt.datetime.now(dt.timezone.utc),
        {
            "active": "x_direct",
            "primary": X_PROFILE_URL,
            "fallback": FALLBACK_ORIGIN,
            "fallback_used": False,
            "recent_posts_seen": len(posts),
            "reset_posts_matched": matched,
        },
        max(post["announced_at"] for post in posts),
    )


def attach_post_content(feed, cache, manifest, translations=None):
    """Enrich display content only; never change the announcement classification."""
    archived = {}
    for key, value in cache.items():
        if key.startswith('/api/v1/resets') and isinstance(value, dict):
            for record in value.get('body', {}).get('data', []):
                if isinstance(record, dict) and isinstance(record.get('text'), str):
                    archived[record.get('id')] = record['text']
    posts = manifest.get('posts', {})
    for record in feed['records']:
        # Recover previous unabridged source responses for historical records.
        if not record.get('source_text') and record['id'] in archived:
            record['source_text'] = archived[record['id']]
        post_id = record['source_url'].rsplit('/', 1)[-1]
        content = posts.get(post_id, {})
        body = content.get('full_text')
        if content.get('status') in ('ready', 'text_ready') and isinstance(body, str) and 0 < len(body) <= 60000:
            record['full_text'] = body
            record['text_complete'] = True
            record['text_source'] = 'x_post_page'
            record['text_captured_at'] = content['text_captured_at']
            record['full_text_sha256'] = content['full_text_sha256']
            translation = (translations or {}).get(post_id, content.get('translation_zh', {}))
            if translation.get('source_sha256') == content['full_text_sha256'] and isinstance(translation.get('text'), str):
                record['translation_zh'] = translation
            else:
                record.pop('translation_zh', None)
            record['excerpt'] = _excerpt(body)
            shot = content.get('screenshot', {})
            if re.fullmatch(r'[0-9]+-[a-f0-9]{16}\.jpg', str(shot.get('file', ''))) and shot.get('source_url') == record['source_url']:
                record['screenshot'] = shot
            else:
                record.pop('screenshot', None)
        else:
            record['text_complete'] = False
    return feed


def collect(output, cache_path, allow_fallback=False):
    from historical_baseline import load_baseline, retain_history, apply_baseline
    from publication_state import publication_lock
    baseline = load_baseline(output.parent / 'historical-baseline.json')
    cache = read_json(cache_path)
    existing = read_json(output)
    try:
        document = fetch_x_profile()
        posts = parse_x_profile(document)
        from x_public import public_posts
        verified = {p['id']: p for p in public_posts(document) if p['author'] == 'thsottiaux'}
        for post in posts:
            if post['id'] in verified:
                original = verified[post['id']]
                post['text'] = original['text']
                if original.get('reply_to_id'):
                    post['in_reply_to_status_id'] = original['reply_to_id']
        if not existing.get("records") and allow_fallback:
            existing, visited = collect_fallback(cache)
            atomic_json(cache_path, {key: value for key, value in cache.items() if key in visited or key == "/api/v1/status"})
        result = merge_x_posts(existing, posts)
    except Exception as x_error:
        if not allow_fallback:
            raise XCollectionError(x_error) from x_error
        try:
            result, visited = collect_fallback(cache)
            result["source"]["primary_error"] = diagnose(x_error)
            atomic_json(cache_path, {key: value for key, value in cache.items() if key in visited or key == "/api/v1/status"})
        except Exception as fallback_error:
            raise XCollectionError(x_error, fallback_error) from x_error
    result = retain_history(result, existing, baseline)
    result = attach_post_content(result, cache, read_json(output.parent / 'post-content.json'), read_json(output.parent / 'post-translations.zh.json'))
    result = annotate_records(result)
    result = apply_baseline(result, baseline)
    result = build_events(result)
    result = attach_briefs(result)
    result["mode"] = "live"
    with publication_lock(output.parent):
        atomic_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".data/data.json"))
    parser.add_argument("--cache", type=Path, default=Path(".data/source-cache.json"))
    parser.add_argument("--allow-fallback", action="store_true")
    args = parser.parse_args()
    try:
        feed = collect(args.output, args.cache, args.allow_fallback)
        print(json.dumps({"ok": True, "records": len(feed["records"]), "checked_at": feed["checked_at"], "source": feed["source"]["active"]}))
    except Exception as error:
        print(json.dumps({"ok": False, "diagnostic": diagnose(error), "previous_feed_retained": args.output.exists()}), file=sys.stderr)
        sys.exit(1)

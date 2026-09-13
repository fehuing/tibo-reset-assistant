"""Copy only public X source material into the Codex worker's input spool.

Only whitelisted public material enters this spool. Account membership and
authentication permissions are never changed by the broker.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

from ai_analysis import AnalysisError, POST_ID, atomic_json, make_input, read_json, safe_error

from ai_config import input_dir
from file_lock import file_lock
DEFAULT_DEST = None
POST_FIELDS = ('id', 'author', 'text', 'announced_at', 'source_url', 'reply_to_id', 'reply_context',
               'quoted_id', 'quoted_context', 'first_seen_at', 'last_seen_at', 'source_text_sha256',
               'media_only', 'has_media')
CONTENT_FIELDS = ('full_text', 'full_text_sha256', 'status', 'source_url', 'text_source',
                  'text_captured_at', 'text_complete', 'author_verified', 'media_only',
                  'discovery_text_sha256', 'reply_to_id', 'reply_context', 'quoted_id', 'quoted_context')
SHOT_FIELDS = ('file', 'sha256', 'width', 'height', 'captured_at', 'source_url', 'method',
               'capture_version', 'document_sha256')


def _context(value):
    if not isinstance(value, dict):
        return None
    return {key: value[key] for key in ('text', 'author', 'source_url') if key in value}


def _whitelist(value, fields):
    output = {key: value[key] for key in fields if key in value}
    for key in ('reply_context', 'quoted_context'):
        if key in output:
            output[key] = _context(output[key])
    return output


@contextlib.contextmanager
def _broker_lock(destination):
    with file_lock(Path(destination) / 'broker.lock'):
        yield


def _copy_image(source, destination, expected_hash):
    # make_input has already checked source path, size and digest. Read/check
    # again so a replacement during copying cannot enter the trusted spool.
    raw = source.read_bytes()
    if len(raw) > 4 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise AnalysisError('screenshot_changed_during_copy')
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_hash:
        return False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.image-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o640)
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return True


def prepare_inputs(state, dest=DEFAULT_DEST):
    state = Path(state)
    dest = Path(dest) if dest is not None else input_dir(state)
    # Parent/group permissions are provisioned by the deployer. Existing files,
    # users, groups and authentication paths are never chmod/chown targets here.
    dest.mkdir(parents=True, exist_ok=True, mode=0o750)
    with _broker_lock(dest):
        # Fresh reads after locking prevent a slower concurrent broker from
        # replacing a newer snapshot with an earlier in-memory snapshot.
        archive = read_json(state / 'activity-archive.json')
        manifest = read_json(state / 'post-content.json')
        posts, contents = {}, {}
        copied, pending = 0, 0
        for ident, post in archive.get('posts', {}).items():
            if not POST_ID.fullmatch(str(ident)) or not isinstance(post, dict):
                continue
            if str(post.get('id')) != ident or post.get('author', '').lower() != 'thsottiaux' or post.get('source_url') != 'https://x.com/thsottiaux/status/' + ident:
                continue
            public_post = _whitelist(post, POST_FIELDS)
            posts[ident] = public_post
            original = manifest.get('posts', {}).get(ident, {})
            if not isinstance(original, dict):
                original = {}
            content = _whitelist(original, CONTENT_FIELDS)
            if isinstance(original.get('screenshot'), dict):
                content['screenshot'] = _whitelist(original['screenshot'], SHOT_FIELDS)
            try:
                source = make_input(ident, public_post, content, state)
                if source.get('image_path'):
                    image_dir = dest / 'post-images'
                    image_dir.mkdir(exist_ok=True, mode=0o750)
                    shot = content['screenshot']
                    copied += int(_copy_image(Path(source['image_path']), image_dir / shot['file'], shot['sha256']))
                contents[ident] = content
            except (AnalysisError, OSError) as error:
                # No partial captured text or raw errors are sent to the model.
                contents[ident] = {'status': 'pending', 'error_code': safe_error(error)}
                pending += 1
        checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
        generation = hashlib.sha256(json.dumps({'posts': posts, 'contents': contents}, ensure_ascii=False,
                                               sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        old = read_json(dest / 'activity-archive.json')
        changed = old.get('input_generation') != generation
        atomic_json(dest / 'post-content.json', {'schema_version': 1, 'input_generation': generation,
                                                 'checked_at': checked_at, 'posts': contents})
        atomic_json(dest / 'activity-archive.json', {'schema_version': 1, 'input_generation': generation,
                                                    'checked_at': checked_at, 'posts': posts})
        if changed:
            atomic_json(dest / 'ready.signal', {'input_generation': generation, 'updated_at': checked_at})
        return {'posts': len(posts), 'ready': len(posts) - pending, 'pending': pending,
                'media_images_copied': copied, 'changed': changed, 'input_generation': generation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('.data'))
    parser.add_argument('--dest', type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    os.umask(0o027)
    print(json.dumps(prepare_inputs(args.state, args.dest), ensure_ascii=False))


if __name__ == '__main__':
    main()

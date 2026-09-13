"""Create complete small list images; original X captures remain immutable."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
from activity_ingest import atomic_json, read_json


def create_thumbnail(raw, width=440):
    from PIL import Image
    with Image.open(BytesIO(raw)) as original:
        if original.width > 24000 or original.height > 24000:
            raise ValueError('Image dimensions exceed limit')
        original.load()
        preview = original.convert('RGB')
        preview.thumbnail((width, 24000), Image.Resampling.LANCZOS)
        output = BytesIO()
        preview.save(output, format='JPEG', quality=68, optimize=True)
        return output.getvalue(), preview.width, preview.height


def build_thumbnails(state=Path('.data')):
    manifest_path = state / 'post-content.json'
    manifest = read_json(manifest_path)
    count, original_bytes, preview_bytes = 0, 0, 0
    for post_id, content in manifest.get('posts', {}).items():
        shot = content.get('screenshot', {})
        if not re.fullmatch(r'\d+', post_id) or not re.fullmatch(r'\d+-[a-f0-9]{16}\.jpg', shot.get('file', '')):
            continue
        original = state / 'post-images' / shot['file']
        if not original.is_file():
            continue
        raw = original.read_bytes()
        if hashlib.sha256(raw).hexdigest() != shot.get('sha256'):
            continue
        old = shot.get('thumbnail', {})
        if old.get('source_sha256') == shot['sha256'] and re.fullmatch(r'\d+-[a-f0-9]{16}\.jpg', old.get('file', '')):
            previous = state / 'post-images' / old['file']
            if previous.is_file() and hashlib.sha256(previous.read_bytes()).hexdigest() == old.get('sha256'):
                continue
        preview, width, height = create_thumbnail(raw)
        digest = hashlib.sha256(preview).hexdigest()
        name = post_id + '-' + digest[:16] + '.jpg'
        target = state / 'post-images' / name
        target.write_bytes(preview)
        target.chmod(0o644)
        shot['thumbnail'] = {'file': name, 'sha256': digest, 'width': width, 'height': height,
                             'source_sha256': shot['sha256'], 'source_url': shot['source_url'], 'captured_at': shot['captured_at']}
        original_bytes += len(raw)
        preview_bytes += len(preview)
        count += 1
    if count:
        atomic_json(manifest_path, manifest, mode=0o644)
    return {'created': count, 'original_bytes': original_bytes, 'thumbnail_bytes': preview_bytes}


if __name__ == '__main__':
    import json
    print(json.dumps(build_thumbnails()), flush=True)

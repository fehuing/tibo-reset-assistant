"""Process and thread locks for private publication and model queues."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading

_guard = threading.Lock()
_locks = {}


@contextmanager
def file_lock(path, blocking=True):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _guard:
        local = _locks.setdefault(str(path), threading.Lock())
    if not local.acquire(blocking=blocking):
        raise BlockingIOError('Worker already running')
    try:
        with path.open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                if stream.tell() == 0:
                    stream.write(b'0'); stream.flush()
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise BlockingIOError('Worker already running') from error
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
    finally:
        local.release()

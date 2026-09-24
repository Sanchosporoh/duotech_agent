"""Operating-system lock shared by all dashboard sessions in one project."""
from contextlib import contextmanager
import os


def _is_empty(path):
    return path.stat().st_size==0


@contextmanager
def acquire(root, name='cycle.lock'):
    if name not in ('cycle.lock','petex.lock','lifecycle.lock'):
        raise ValueError('Unknown project lock')
    path=root/'data/live'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    # Unbuffered: a failed first write must not stay in a buffer and fail again on close.
    stream=path.open('a+b',buffering=0)
    locked=False
    try:
        if _is_empty(path):
            try:
                stream.write(b'0')
            except OSError:
                pass  # another process created the file and locked its byte at this very moment
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError:
            pass
        yield locked
    finally:
        if locked:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()

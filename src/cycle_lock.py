"""Operating-system lock shared by all dashboard sessions in one project."""
from contextlib import contextmanager
import os


@contextmanager
def acquire(root, name='cycle.lock'):
    if name not in ('cycle.lock','petex.lock','lifecycle.lock'):
        raise ValueError('Unknown project lock')
    path=root/'data/live'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.open('a+b')
    locked=False
    try:
        if path.stat().st_size==0:
            stream.write(b'0');stream.flush()
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

import os
import pathlib
import traceback

LOG = pathlib.Path('tradingview/_os_close.txt')
_orig_close = os.close


def _close(fd, *args, **kwargs):
    try:
        if fd > 2:
            with LOG.open('a', encoding='utf-8') as handle:
                handle.write('--- os.close(%d)\n' % fd)
                handle.write(''.join(traceback.format_stack(limit=6)))
    except Exception:
        pass
    return _orig_close(fd, *args, **kwargs)


os.close = _close


def test_hook():
    assert os.close is _close

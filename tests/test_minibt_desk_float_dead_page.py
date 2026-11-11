"""独立浮窗关掉后不该再往「死页面」发脚本（v1.3.7-49）。

用户 2026-11-08 实测：浮窗浮到主窗口外后**关闭时**（尤其大模型连不上、
每秒都有 `pi_event` 补丁时）stderr 循环刷

```
runJavaScript: disabled in Discarded state
```

根因：`desk.sender` 的广播还握着**已经关闭 / 被 Qt discard** 的面板，
于是每一条补丁都往死页面塞一次 `runJavaScript` ✗。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _source() -> str:
    return (ROOT / 'minibt' / 'desk' / 'float_window.py').read_text(
        encoding='utf-8')


class _FakeWin:
    def __init__(self, fail=False):
        self.fail = fail
        self.scripts = []

    def run_script(self, script):
        if self.fail:
            raise RuntimeError('page deleted')
        self.scripts.append(script)


class _FakePage:
    def __init__(self):
        self.destroyed = _Signal()
        self.lifecycleChanged = _Signal()


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def disconnect(self):
        self.slots = []

    def emit(self, *args):
        for fn in list(self.slots):
            fn(*args)


class _FakeView:
    def __init__(self, visible=True):
        self.visible = visible
        self.destroyed = _Signal()
        self._page = _FakePage()

    def page(self):
        return self._page

    def isVisible(self):
        return self.visible


class _FakePanel:
    def __init__(self, visible=True, fail=False):
        self.webview = _FakeView(visible)
        self.win = _FakeWin(fail)


def test_liveness_helpers_reject_dead_pages(monkeypatch):
    from minibt.desk import float_window as fw

    assert fw._alive(None) is False
    assert fw._page_usable(None) is False
    # 页面对象不存在 → 不能发
    assert fw._page_usable(object()) is False
    # 控件不存活（shiboken6 说无效）→ 不能发
    import shiboken6

    class _Dead:
        def page(self):
            raise RuntimeError('C++ object deleted')

    monkeypatch.setattr(shiboken6, 'isValid', lambda obj: False)
    assert fw._alive(_Dead()) is False
    assert fw._page_usable(_FakePanel()) is False


def test_send_swallows_runtime_error():
    from minibt.desk import float_window as fw

    panel = _FakePanel(fail=True)
    assert fw._send_to(panel, 'x') is False     # 页面已销毁 → False，不抛
    ok = _FakePanel()
    assert fw._send_to(ok, 'x') is True
    assert ok.win.scripts == ['x']


def test_broadcast_prunes_dead_sender_and_restores_sender():
    """一个浮窗发不出去 → 立刻注销；全部没了 → `desk.sender` 还原 ✓"""
    from minibt.desk import float_window as fw

    class _Desk:
        def __init__(self):
            self.received = []
            self.sender = self.received.append

    desk = _Desk()
    original = desk.sender
    fw._STATE.update({'panel': None, 'senders': [], 'wrapped': False,
                      'desk': None, 'previous': None})
    fw._attach_sender(desk)
    assert fw._STATE['wrapped'] is True
    alive = _FakePanel()
    dead = _FakePanel(fail=True)
    fw._STATE['senders'].append(lambda script: fw._send_to(alive, script))
    fw._STATE['senders'].append(lambda script: fw._send_to(dead, script))
    desk.sender('a')                       # 广播一次：主窗口 + 2 个浮窗
    assert alive.win.scripts == ['a']
    # 死掉的那个被摘掉（不会再每拍重试 ✓）
    assert len(fw._STATE['senders']) == 1
    desk.sender('b')
    assert alive.win.scripts == ['a', 'b']
    fw._detach_all()
    assert desk.sender is original
    assert fw._STATE['senders'] == []


def test_close_float_resets_state():
    from minibt.desk import float_window as fw

    class _View:
        def __init__(self):
            self.closed = False
            self.destroyed = _Signal()

        def page(self):
            return _FakePage()

        def close(self):
            self.closed = True

    class _Panel:
        def __init__(self):
            self.webview = _View()

    panel = _Panel()
    fw._STATE.update({'panel': panel, 'senders': [lambda s: True],
                      'wrapped': True, 'desk': None, 'previous': None})
    fw.close_float(None)
    assert panel.webview.closed is True
    assert fw.float_state()['open'] is False
    assert fw.float_state()['senders'] == 0


def test_hidden_float_is_not_scripted():
    """关着的浮窗不发脚本（Qt 随时可能 discard → 一跑就刷警告 ✗）"""
    code = _source()
    assert 'if view is not None and not view.isVisible():' in code
    assert 'return True                  # 只是关着' in code


def test_source_guards_and_resync():
    code = _source()
    for token in ('def _page_usable(panel) -> bool:',
                  'def _send_to(panel, script: str) -> bool:',
                  'def _drop_sender(',
                  'def _detach_all() -> None:',
                  'def float_state() -> Dict[str, Any]:',
                  'QWebEnginePage.LifecycleState.Discarded',
                  "changed = getattr(page, 'lifecycleChanged', None)",
                  'def _on_float_gone(desk, panel, reason: str) -> None:',
                  '浮窗页面已丢弃（Discarded）',
                  'renderProcessTerminated.connect(',
                  'desk.sender = previous',
                  '_push_config(panel, desk)\n            return \'\''):
        assert token in code, token
    # `_push_config` 不能再绕过验活直接 run_script ✗
    block = code.split('def _push_config(', 1)[1].split('def _raise(', 1)[0]
    assert 'panel.run_script' not in block
    assert '_send_to(panel,' in block


def test_float_refresh_pulls_history():
    """重开浮窗时补拉当前会话（关着期间不发脚本，界面别停旧内容 ✓）"""
    code = (ROOT / 'jslib' / 'src' / 'desk' / 'pi-float.ts').read_text(
        encoding='utf-8')
    block = code.split('refresh(): void {', 1)[1].split('setTheme(', 1)[0]
    assert "onCommand('pi_history', { id: this.sessionId })" in block


def test_app_close_path_resets_float():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'float_window.close_float(self)' in app

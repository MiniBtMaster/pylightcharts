"""周期切换 / 二级报价面板 / 截图回执（用户 2026-11-08 实测三连）。

背景（模型原话）：「请将白银切换为 5 分钟周期，并打开二级报价页面」→
**没能切换和打开**；同时 `desk_screenshot` 连续两次失败（超时 / 前端报错）。

三个根因：

1. **周期单位歧义**：「5 分钟」被模型写成 `cycle: 5` → 当成 **5 秒** →
   天勤不支持 → 空 K 线 → 推 `reset` 补丁把图**清空** ✗（用户看到"没切换"）；
2. **二级报价只订阅了数据、没人去点按钮**：`desk_book{action:"watch"}`
   只调 `_on_book_watch`（后端订阅），右侧面板一直隐藏 ✗；
3. **截图没回执**：前端 `screenshot()` 是"下载 PNG"，QtWebEngine 里
   `<a download>` 本来就不工作 → 后端工具永远等不到 `screenshot` 命令 → 超时 ✗。
"""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
from minibt.desk import tools  # noqa: E402
from minibt.desk.app import Desk  # noqa: E402


def _read(*parts) -> str:
    return (REPO.joinpath(*parts)).read_text(encoding='utf-8')


# ------------------------------------------------------------------ 周期
def test_normalize_cycle_units():
    for raw, expect in ((300, 300), ('300', 300), ('300s', 300), ('5m', 300),
                        ('5分', 300), ('5分钟', 300), ('1h', 3600),
                        ('1d', 86400), ('1w', 604800), (5, 5), ('5秒', 5),
                        (7, 0), ('abc', 0), (None, 0), ('', 0)):
        assert Desk.normalize_cycle(raw) == expect, raw
    # 标签（给模型核对）
    assert Desk.cycle_label(300) == '5分'
    assert Desk.cycle_label(60) == '1分'
    assert Desk.cycle_label(90) == '90秒'


def test_set_cycle_refuses_and_keeps_state(tmp_path):
    """周期不支持 / 取不到数据 → **不改状态**（以前会把图清空 ✗）"""
    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.tabs = {'SHFE.ag2612': {'cycle': 60}}
    desk.last_symbol = 'SHFE.ag2612'
    bad = desk.set_cycle('SHFE.ag2612', 7)
    assert bad['ok'] is False and '不支持的周期' in bad['error']
    assert 'supported' in bad and 300 in bad['supported']
    assert desk.tabs['SHFE.ag2612']['cycle'] == 60      # 没被改 ✓
    # ★ 有行情源、但该周期取不到 K 线 → 拒绝，且**不改状态 / 不清图**
    class _DeadFeed:
        kind = 'futures'

        def available(self):
            return True

        def klines(self, symbol, cycle, length=500):
            return None            # 天勤不支持 / 未登录时就是这个效果

    desk.feeds = [_DeadFeed()]
    missing = desk.set_cycle('SHFE.ag2612', '5m')
    assert missing['ok'] is False
    assert '暂时切不过去' in missing['error']
    assert desk.tabs['SHFE.ag2612']['cycle'] == 60
    # 没有任何 `reset=True` 的空 K 线补丁被推出去 ✓
    klines = [p for p in desk.sent if isinstance(p, dict)
              and p.get('type') == 'kline']
    assert klines == []


def test_tool_set_cycle_reports_label_and_rejects_bad():
    class _Desk:
        CYCLES_SUPPORTED = Desk.CYCLES_SUPPORTED
        normalize_cycle = staticmethod(Desk.normalize_cycle)
        cycle_label = staticmethod(Desk.cycle_label)

        def __init__(self):
            self.calls = []

        def set_cycle(self, symbol, cycle, cell):
            self.calls.append((symbol, cycle, cell))
            return {'ok': True, 'symbol': symbol, 'cycle': cycle,
                    'label': Desk.cycle_label(cycle)}

        def _on_set_cycle(self, payload):
            self.calls.append(payload)

    desk = _Desk()
    data = json.loads(tools.call('desk_set_cycle', {'cycle': '5m'}, desk))
    assert data['ok'] is True and data['cycle'] == 300
    assert data['label'] == '5分'
    assert desk.calls == [('SHFE.ag2612', 300, 0)] or desk.calls[0][1] == 300
    bad = json.loads(tools.call('desk_set_cycle', {'cycle': 7}, desk))
    assert bad['ok'] is False and '不支持' in bad['error']
    assert '5 分钟 = 300' in bad['hint']


# ------------------------------------------------------------------ 二级报价
class _BookDesk:
    tabs = {'SHFE.ag2612': {}}
    last_symbol = 'SHFE.ag2612'
    _active_local_page = ''

    def __init__(self):
        self.pushed = []
        self.watched = []

    def push(self, patch):
        self.pushed.append(patch)

    def _on_book_watch(self, payload):
        self.watched.append(payload)

    def book_payload(self, symbol, feed=None):
        return {'bids': [[12656, 5]], 'asks': [[12657, 5]], 'last': 12656}

    def current_feed(self):
        return None


def test_book_open_pushes_ui_action():
    desk = _BookDesk()
    data = json.loads(tools.call('desk_book', {'action': 'open'}, desk))
    assert data['ok'] is True and data['shown'] is True
    assert desk.pushed[-1] == {'type': 'ui_action', 'action': 'book',
                               'page': 'chart:SHFE.ag2612',
                               'symbol': 'SHFE.ag2612', 'on': True}
    # close / toggle
    tools.call('desk_book', {'action': 'close'}, desk)
    assert desk.pushed[-1]['on'] is False
    tools.call('desk_book', {'action': 'toggle'}, desk)
    assert 'on' not in desk.pushed[-1]


def test_book_watch_also_shows_panel():
    """`watch` = 订阅 + 默认把面板显示出来（用户说的"打开二级报价"✓）"""
    desk = _BookDesk()
    data = json.loads(tools.call('desk_book', {'action': 'watch'}, desk))
    assert data['panel_shown'] is True
    assert desk.watched[-1]['on'] is True
    assert any(p.get('action') == 'book' and p.get('on') is True
               for p in desk.pushed)
    # 显式 `open:false` → 只订阅，不动面板 ✓
    desk2 = _BookDesk()
    data = json.loads(tools.call('desk_book', {'action': 'watch',
                                              'open': False}, desk2))
    assert data['panel_shown'] is None
    assert not [p for p in desk2.pushed if p.get('action') == 'book']


def test_open_ui_book_target():
    desk = _BookDesk()
    data = json.loads(tools.call('desk_open_ui', {'target': 'book'}, desk))
    assert data['ok'] is True and data['shown'] is True
    assert desk.pushed[-1]['action'] == 'book'


def test_book_shown_handler_and_frontend_routing():
    app = _read('minibt', 'desk', 'app.py')
    assert "'book_shown': self._on_book_shown" in app
    assert 'def _on_book_shown(' in app
    ts = _read('jslib', 'src', 'desk', 'app.ts')
    assert "action === 'book'" in ts
    assert 'toggleBook?.(' in ts or 'toggleBook' in ts
    assert "this.send('book_shown'" in ts
    page = _read('jslib', 'src', 'desk', 'chart-page.ts')
    assert 'toggleBook(visible?: boolean): boolean {' in page


# ------------------------------------------------------------------ 截图
class _ShotDesk:
    tabs = {'SHFE.ag2612': {}}
    last_symbol = 'SHFE.ag2612'

    def __init__(self, path='', error=''):
        self._shot_pending = None
        self.pushed = []
        self.path = path
        self.error = error

    def push(self, patch):
        self.pushed.append(patch)
        if self.error:
            self._shot_pending['error'] = self.error
        self._shot_done(self.path)

    def _shot_done(self, path):
        pending = self._shot_pending
        if not pending:
            return
        pending['path'] = str(path or '')
        pending['event'].set()


def test_screenshot_tool_returns_path():
    desk = _ShotDesk(path='C:/tmp/a.png')
    data = json.loads(tools.call('desk_screenshot', {}, desk))
    assert data['ok'] is True and data['path'] == 'C:/tmp/a.png'
    assert desk.pushed[-1]['action'] == 'screenshot'


def test_screenshot_tool_reports_frontend_error():
    """前端报错要**原样带回来**（以前只会说"截图失败（前端报错）" ✗）"""
    desk = _ShotDesk(error='takeScreenshot 不可用')
    data = json.loads(tools.call('desk_screenshot', {}, desk))
    assert data['ok'] is False
    assert 'takeScreenshot 不可用' in data['error']
    assert 'hint' in data


def test_frontend_capture_screenshot_exists():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read('jslib', 'src', 'desk', name)
        assert 'captureScreenshot(name?: string): void {' in page, name
        assert "onCommand?.('screenshot', {" in page, name
        assert 'dataUrl: canvas.toDataURL' in page, name
        assert '前端截图出错' in page, name
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert 'captureScreenshot?: (name?: string) => void;' in app
    assert 'capture.call(target, name || undefined);' in app
    # 没有图表页时立刻回空（别让工具等到超时 ✓）
    assert "error: '当前页没有图表（先切到实时 / 本地图表）'" in app


def test_backend_screenshot_always_replies():
    """`_on_screenshot` 每条失败路径都要 `_shot_done('')`（否则工具超时 ✗）"""
    app = _read('minibt', 'desk', 'app.py')
    block = app.split('def _on_screenshot(', 1)[1].split(
        'def _on_open_export', 1)[0]
    # 三条失败分支：没有 dataURL / base64 坏 / 落盘失败
    assert block.count("_shot_done('')") >= 3
    assert "pending['error'] = " in block

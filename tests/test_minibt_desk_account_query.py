"""MCP 账户查询 / 下单诚实回执 + PI 悬浮球可拖动 + 悬浮窗 ↑↓ 历史。

用户 2026-11-08 实测（三个反馈）：

1. 悬浮球只能停在默认位置 → 希望**能沿边界移动**；
2. 悬浮窗输入框 ↑/↓ 不能翻历史输入（对话页可以）；
3. 模型连下 5 单，审计全是 `PENDING` + `account: ""`，柜台里一笔都没有 ——
   `desk_order` 恒回「已提交」，账户查询接口（`desk_account`）实际读的是
   `Trading.positions/orders`（**不存在**）→ 恒空 ✗。
"""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
from minibt.desk import tools  # noqa: E402
from minibt.desk import user_prefs  # noqa: E402


# --------------------------------------------------------------- 悬浮球 / 历史
def _float() -> str:
    return (REPO / 'jslib' / 'src' / 'desk' / 'pi-float.ts').read_text(
        encoding='utf-8')


def test_float_icon_can_move_anywhere():
    """PI 小球：按下拖动 → 跟着鼠标 → **停在任意位置**（不再吸附边界 ✓）"""
    code = _float()
    for token in ("const ICON_KEY = 'desk.pi.float.icon';",
                  'private _startIconDrag(event: MouseEvent): void {',
                  'private _onIconDrag(event: MouseEvent): void {',
                  'private _endIconDrag(event: MouseEvent): void {',
                  'private _placeIcon(): void {',
                  'private iconPos: { left: number; top: number } | null'
                  ' = null;',
                  'this.iconPos = {'):
        assert token in code, token
    # 不再"找最近的边"
    assert "['left', centerX]" not in code
    assert "'left', centerX" not in code
    # 拖动后不能顺带打开窗口（双击才开 ✓）
    assert "this.icon.addEventListener('dblclick'" in code
    assert 'this.iconMoved = true;' in code
    # 刷新 / 重启后按记住的位置还原
    assert 'this.iconPos = { left: data.left, top: data.top };' in code
    assert 'window.localStorage.setItem(' in code


def test_float_input_history_arrows():
    """悬浮窗输入框：↑ 上一条 / ↓ 下一条（到底清空，和对话页一致 ✓）"""
    code = _float()
    assert 'private readonly history: string[] = [];' in code
    assert 'private historyAt = -1;' in code
    assert "if (event.key === 'ArrowUp') {" in code
    assert "if (event.key === 'ArrowDown') {" in code
    assert 'this._remember(text);' in code
    assert 'private _applyHistory(text: string): void {' in code
    assert 'if (this.history.length > 100) this.history.shift();' in code
    # 输入历史要能触发 @文件 联想（不然翻出来就没联想）
    assert 'private onInputChanged(): void {' in code


# --------------------------------------------------------------- 账户查询
class _FakeStore:
    def __init__(self):
        self.rows = [{'ts': '2026-11-08 22:00:00', 'kind': 'order',
                      'text': '快期模拟 SHFE.ag2612 卖开 2 手 @ 12666',
                      'status': 'PENDING', 'account': '快期模拟'}]

    def orders(self, limit=30):
        return self.rows[:limit]


class _FakeBench:
    def __init__(self):
        self.store = _FakeStore()


class _FakeView:
    """`Desk.account_view()` 的最小替身（真实现见 minibt/desk/accounts.py）"""

    def labels(self, symbol=''):
        return ['快期模拟', '中信/88888']

    @staticmethod
    def identity_of(item):
        return item

    def instance_for(self, key='', symbol=''):
        return '中信/88888' if key == 'real' else '快期模拟'

    def summary(self, symbol='', key=''):
        return {'type': 'account', 'label': '中信/88888',
                'labels': ['快期模拟', '中信/88888'],
                'values': {'balance': 100000.0, 'available': 88000.0,
                           'margin': 12000.0, 'risk_ratio': 0.12}}

    def tables(self, limit=100, symbol='', key=''):
        return {
            'positions': {'columns': ['合约', '方向', '手数'],
                          'rows': [['SHFE.ag2612', '空', 5]]},
            'orders': {'columns': ['委托号', '状态'],
                       'rows': [['#1', '已撤']]},
            'unfilled': {'columns': ['委托号', '状态'],
                         'rows': [['#5', '挂单中']]},
            'trades': {'columns': ['成交号'], 'rows': [['T1']]},
        }


class _FakeDesk:
    tabs = {'SHFE.ag2612': {}}
    last_symbol = 'SHFE.ag2612'
    _workbench = _FakeBench()

    def __init__(self, ready=True, text='快期模拟 SHFE.ag2612 买平 5 手 @ 12650'):
        self.ready = ready
        self.text = text
        self.placed = []
        self.cancelled = []
        self.pending = []

    def trading_snapshot(self, symbol=''):
        return {'ready': self.ready, 'account': '中信/88888', 'key': 'real',
                'identity': 'real:中信:88888', 'labels': ['快期模拟'],
                'hint': '先 desk_login_futures 登录天勤'}

    def account_view(self):
        return _FakeView()

    def _on_place_order(self, payload):
        self.placed.append(payload)
        return self.text

    def pending_orders(self, symbol=''):
        return list(self.pending)

    def _on_order_action(self, payload):
        self.cancelled.append(payload)


def _allow_order():
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    user_prefs.set_setting(tools.SETTING_ALLOW, True)


def test_account_summary_reads_account_view():
    """`desk_account{summary}` 要真读到资金 / 持仓数 / 登录状态 ✓"""
    _allow_order()
    desk = _FakeDesk()
    data = json.loads(tools.call('desk_account', {'action': 'summary'}, desk))
    assert data['ok'] is True
    assert data['balance']['balance'] == 100000.0
    assert data['counts']['positions'] == 1
    assert data['counts']['unfilled'] == 1
    assert data['login']['ready'] is True
    assert desk.placed == []


def test_account_positions_unfilled_trades_audit():
    _allow_order()
    desk = _FakeDesk()
    positions = json.loads(tools.call('desk_account',
                                      {'action': 'positions'}, desk))
    assert positions['positions']['rows'] == [['SHFE.ag2612', '空', 5]]
    unfilled = json.loads(tools.call('desk_account',
                                     {'action': 'unfilled'}, desk))
    assert unfilled['count'] == 1
    pending = json.loads(tools.call('desk_account', {'action': 'pending'}, desk))
    assert pending['count'] == 1 and pending['message'] == '未成交 1 笔'
    audit = json.loads(tools.call('desk_account', {'action': 'audit'}, desk))
    assert audit['count'] == 1
    assert '已提交给柜台' in audit['note']


def test_account_unknown_action_is_clear():
    data = json.loads(tools.call('desk_account', {'action': 'nope'},
                                 _FakeDesk()))
    assert data['ok'] is False and 'action 只能是' in data['error']


def test_order_refuses_when_not_logged_in():
    """没登录交易 → `need_login`，**一单都不提交** ✓"""
    _allow_order()
    desk = _FakeDesk(ready=False)
    data = json.loads(tools.call('desk_order', {
        'symbol': 'SHFE.ag2612', 'side': 'buy', 'volume': 5, 'price': 12650,
        'offset': 'close', 'confirm': True}, desk))
    assert data['ok'] is False and data['need_login'] is True
    assert data['submitted'] is False
    assert desk.placed == []


def test_order_reports_real_failure_text():
    _allow_order()
    desk = _FakeDesk(text='下单未启用（需要先连接行情/交易接口）')
    data = json.loads(tools.call('desk_order', {
        'symbol': 'SHFE.ag2612', 'side': 'buy', 'volume': 5, 'price': 12650,
        'confirm': True}, desk))
    assert data['ok'] is False and data['submitted'] is False
    assert '未启用' in data['error']


def test_order_success_carries_account_and_next_hint():
    _allow_order()
    desk = _FakeDesk()
    data = json.loads(tools.call('desk_order', {
        'symbol': 'SHFE.ag2612', 'side': 'buy', 'volume': 5, 'price': 12650,
        'confirm': True}, desk))
    assert data['ok'] is True and data['submitted'] is True
    assert data['account'] == '中信/88888'
    assert 'desk_account' in data['next_hint']
    assert len(desk.placed) == 1


def test_cancel_all_is_honest_when_no_pending():
    _allow_order()
    desk = _FakeDesk()
    data = json.loads(tools.call('desk_order_action', {
        'action': 'cancel_all', 'symbol': 'SHFE.ag2612',
        'confirm': True}, desk))
    assert data['ok'] is True and data['cancelled'] == 0
    assert '没有挂单' in data['message']
    assert desk.cancelled == []            # 没挂单就不去点"撤全部" ✓
    desk.pending = [{'order_id': '#1'}, {'order_id': '#2'}]
    data = json.loads(tools.call('desk_order_action', {
        'action': 'cancel_all', 'symbol': 'SHFE.ag2612',
        'confirm': True}, desk))
    assert data['cancelled'] == 2
    assert desk.cancelled == [{'action': 'cancel_all',
                               'symbol': 'SHFE.ag2612'}]


def test_audit_records_account_and_order_returns_text():
    """审计要写明账户（以前恒空串 → 用户以为"没绑账户" ✗）"""
    app = (REPO / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _after_order(', 1)[1].split('def _on_focus_chart',
                                                       1)[0]
    assert 'price=price, account=label,' in block
    assert "trader.account_label(symbol)" in block
    # 下单处理器要把回执文本返回给工具（以前恒 None → 工具只能盲报成功 ✗）
    inner = app.split('def _place_order_inner(', 1)[1].split(
        'def _reset_trade_caches', 1)[0]
    assert 'return str(text or \'\')' in inner


def test_trading_snapshot_and_status_block():
    app = (REPO / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'def trading_snapshot(self, symbol: str = \'\')' in app
    assert "'type': 'trading_snapshot'," in app
    assert '还没连上交易：先 desk_login_futures' in app
    status = (REPO / 'minibt' / 'desk' / 'tools.py').read_text(
        encoding='utf-8')
    assert "'trading': {key: trading.get(key) for key in" in status

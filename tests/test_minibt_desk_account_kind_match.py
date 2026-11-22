"""账户类型必须**真匹配**：不能拿「另一个账户」的数据冒充（v1.3.9-30）。

用户实测 2026-11-18：切换到实盘后，交易页 / 首页的数据还是快期模拟的，只有
按钮文字变成「TqAccount」。

根因：desk 只用一个 `TqApi(target)` 连接（target 要么 TqKq 要么 TqAccount），
`_account_list` 里只有那一个账户；而：
* `instance_for('real')` 找不到实盘时**回落到 `items[0]`** → 返回模拟账户，
  标签写「TqAccount」、数字是模拟 ✗
* `account_catalog()` 三个 key 全标「可用」→ 用户能点到不存在的账户 ✗

现在：类型对不上 → `instance_for()` 返回 None、`summary()` 返回空（显示 --），
目录里那种账户直接置灰，并给一句明确提示。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCOUNTS = (ROOT / 'minibt' / 'desk' / 'accounts.py').read_text(encoding='utf-8')
APP = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')


def test_instance_for_never_returns_wrong_kind():
    body = ACCOUNTS.split('def instance_for(', 1)[1]
    body = body.split('def index_for_key(', 1)[0]
    assert "if key in ('kq', 'sim'):" in body
    assert 'return None' in body
    # `kq` / `real` 分支里不能再有「找不到就 items[0]」的兜底
    assert body.count('return None') >= 2
    kq = body.split("if key in ('kq', 'sim'):", 1)[1].split('if key ==', 1)[0]
    real = body.split("if key == 'real':", 1)[1].split('if key ==', 1)[0]
    assert 'return items[0]' not in kq
    assert 'return items[0]' not in real


def test_summary_empty_when_kind_missing():
    body = ACCOUNTS.split('def summary(', 1)[1]
    body = body.split('def ', 1)[0]
    assert "if requested in ('kq', 'sim', 'real') and account is None:" in body
    assert 'return {}' in body


def test_catalog_marks_kind_by_real_accounts():
    body = APP.split('def account_catalog(', 1)[1]
    body = body.split('def _feed_online(', 1)[0]
    assert 'has_sim' in body and 'has_real' in body
    assert 'sim_available' in body
    assert "available = futures_on and sim_available" in body
    assert "available = futures_on and real_available" in body


def test_switch_to_missing_kind_gives_clear_hint():
    body = APP.split('def set_account_kind(', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    assert '看盘账号里没有实盘 TqAccount' in body
    assert "patch_toast(" in body


def test_ctp_pending_login_counts_as_real():
    """CTP 登录中（`broker_id` 还没回填）也要认成实盘 ✓

    用户实测 2026-11-18：登录的明明是实盘，却提示
    「天勤里没有实盘账户（TqAccount），无法切到实盘」→ 因为判身份只看
    `broker_id` / `account_id`（CTP 登录要好几秒才回填）✗
    """
    import sys
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))
    from minibt.desk import accounts

    class TqAccount:
        broker_id = ''
        account_id = ''

    class TqKq:
        broker_id = ''
        account_id = ''

    assert accounts._looks_real(TqAccount()) is True
    assert accounts._looks_real(TqKq()) is False
    assert accounts.AccountView.identity_of(TqAccount()) == 'real:'
    assert accounts.AccountView.identity_of(TqKq()) == 'sim'


def test_home_switch_checks_identity_before_writing_key():
    """首页切实盘：先核对身份**再**写 key（否则先改后拒 → 下一秒被打回 ✗）"""
    body = APP.split('def set_account_kind(', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    # 只看真正的赋值语句（注释里也提到这串，别被误导 ✅）
    assign = body.rindex('self._home_key = key')
    assert body.index('identity = next(') < assign
    assert '天勤里没有实盘账户（TqAccount），无法切到实盘' in body
    # 「已回到快期模拟」只在**确实没有实盘**时才写（`_verified_account_key`）
    assert "self._account_kind = 'kq'" in APP


def test_manual_choice_is_not_overridden_on_symbol_switch():
    """手动切过的页 / 格 → 换标的时**不再自动覆盖** ✓

    用户实测 2026-11-18：刚在交易账户页切到 TqAccount，切个合约又被
    `_auto_account_for_symbol()` 顶回「快期模拟」✗
    """
    body = APP.split('def _auto_account_for_symbol(', 1)[1]
    body = body.split('def _push_cell_account(', 1)[0]
    assert '_account_user' in body
    assert 'return current or wanted' in body
    # `set_account_kind()` 里要记下"用户手动切过"
    switch = APP.split('def set_account_kind(', 1)[1]
    switch = switch.split('def _focus_symbols', 1)[0]
    assert 'marks.add(store)' in switch
    assert 'marks.add(page)' in switch


def test_account_patch_logs_key_changes():
    """`_account_patch()` 在 key **变化**时记一行（诊断被顶回旧账户 ✓）"""
    body = APP.split('def _account_patch(', 1)[1]
    body = body.split('#: 单图换标的时自动切账户', 1)[0]
    assert '_account_key_seen' in body
    assert "f'账户补丁：{marker} → {key}'" in body
    # 诊断日志必须在账户补丁**之后**（第一包仍要是 `account` ✓）
    assert body.index('payload = self.account_payload(') < body.index(
        "'账户补丁：")


def test_no_auto_account_switch_at_all():
    """账户**只能**通过切换按钮改（用户 2026-11-18 明确要求 ✓）"""
    assert 'AUTO_ACCOUNT_ON_SWITCH = False' in APP
    body = APP.split('def _auto_account_for_symbol(', 1)[1]
    body = body.split('def _push_cell_account(', 1)[0]
    assert 'if not self.AUTO_ACCOUNT_ON_SWITCH:' in body
    assert "return self.account_key_for(f'{page}#0')" in body


def test_positions_and_orders_follow_page_account():
    """持仓线 / 挂单线要按**这一页 / 这一格**的账户取（否则切了实盘仍读模拟 ✓）"""
    pos = APP.split('def position_payload(', 1)[1]
    pos = pos.split('def ', 1)[0]
    assert "kwargs = view.account_kwargs(" in pos
    assert "self.account_key_for(f'{page}#{cell}')" in pos
    orders = APP.split('def pending_orders(', 1)[1]
    orders = orders.split('def orders_payload(', 1)[0]
    assert 'view.pending_orders(symbol, key)' in orders
    # AccountView 里也要真按 key 取
    accounts = (ROOT / 'minibt' / 'desk' / 'accounts.py').read_text(
        encoding='utf-8')
    view = accounts.split('def pending_orders(', 1)[1]
    view = view.split('def ', 1)[0]
    assert 'api = self.api(symbol, key)' in view
    assert 'kwargs = self.account_kwargs(symbol, key)' in view


def test_switch_pushes_position_orders_and_state():
    """切完账户要立刻重推持仓线 / 挂单线 / 交易状态（不用等下一拍 ✓）"""
    body = APP.split('def set_account_kind(', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    assert 'self._push_orders(cell_symbol,' in body
    assert 'payload_pos = self.position_payload(cell_symbol)' in body
    assert 'self.push(self.trading_state(symbol))' in body


def test_single_writer_logs_every_change():
    """所有账户 key 写入都走 `_set_account_key()`（谁改的一目了然 ✓）

    用户实测 2026-11-18：切到实盘后"很快就跳回快期模拟"，但不知道是谁改的 →
    统一入口在**变更**时记一行 `账户切换：chart:X#0 → kq（原因）`。
    """
    assert 'def _set_account_key(self, store: str, key: str,' in APP
    body = APP.split('def _set_account_key(', 1)[1].split('    def ', 1)[0]
    assert "f'账户切换：{store} → {key}（{reason or \"未标明\"}）'" in body
    # 各写入点都带原因
    assert "self._set_account_key(store, key, '用户切换')" in APP
    assert "'镜像同页'" in APP
    assert "'换标的自动'" in APP
    assert "'换合约搬 key'" in APP
    assert "'开图默认'" in APP


def test_active_key_never_silently_flips_to_sim():
    """`active_account_key()` 不许偷偷把用户选的实盘改成模拟 ✓

    行情源短暂不可用（盘前 / 断线重连）时会走 fallback —— 以前顺手写
    `self._account_kind = fallback` → 用户选的实盘被改掉 ✗
    """
    body = APP.split('def active_account_key(', 1)[1]
    body = body.split('    def ', 1)[0]
    assert 'self._account_kind = fallback' not in body
    assert 'return fallback' in body


def test_switch_writes_focus_cell_too():
    """切换账户要同时写「焦点格」——读写口径必须一致 ✓

    用户实测 2026-11-18：挂单后（焦点格变了）再切账户没反应、按钮又弹回去 ——
    下拉框给的 `cell` 和每秒补丁读的 `cell`（焦点格）不是同一格 ✗
    """
    body = APP.split('def set_account_kind(', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    assert "self._set_account_key(target_store, key, '同页焦点格')" in body


def test_switch_verifies_target_account_exists():
    """目标账户在行情账号里不存在 → 明确拒绝 + 恢复下拉框（不留半截状态 ✓）"""
    body = APP.split('def set_account_kind(', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    assert 'view_check.instance_for(key, symbol)' in body
    assert 'self._restore_account_kind(page)' in body
    assert '没有「' in body


def test_account_kwargs_never_passes_none():
    """`account_kwargs()` 绝不能返回 `{'account': None}` ✓

    tqsdk 多账户模式下 `account=None` 会抛
    「多账户模式下，需要指定账户实例」（用户截图 2026-11-18 ✗）：
    切到快期模拟后平仓 → 报错、平不掉。
    """
    accounts = (ROOT / 'minibt' / 'desk' / 'accounts.py').read_text(
        encoding='utf-8')
    body = accounts.split('def account_kwargs(', 1)[1].split('    def ', 1)[0]
    assert 'if account is None:' in body
    assert 'account = items[0]' in body
    assert "return {'account': account}" in body


def test_trading_falls_back_to_real_instance():
    """下单 / 撤单 / 查单也保证带真实账户实例（逐级兜底 ✓）"""
    trading = (ROOT / 'minibt' / 'desk' / 'trading.py').read_text(
        encoding='utf-8')
    assert 'def _order_account_kwargs(' in trading
    assert "return {'account': items[0]} if items else {}" in trading
    # 下单（`insert`，`place` 只是它的包装）走兜底
    assert 'kwargs = self._order_account_kwargs(symbol)' in trading


def test_order_logs_actual_account_instance():
    """下单要记「实际用的账户实例」（排查"显示模拟、下到实盘" ✓）"""
    trading = (ROOT / 'minibt' / 'desk' / 'trading.py').read_text(
        encoding='utf-8')
    assert '[委托账户]' in trading
    assert "name = type(used).__name__ if used is not None else '默认'" in trading
    # 登录成功后打印账户列表（多账户注册了哪几个实例 ✓）
    assert '账户列表：' in APP
    assert "getattr(inner, '_account_list', None)" in APP


def test_ticket_actions_use_current_account():
    """交易页所有按钮 / 右键菜单都要落到**当前账户** ✓

    下单 / 撤单 / 平仓 / 反手 / 全平 都只走 `Trading.insert()/cancel()/action()`，
    而它们统一从 `_order_account_kwargs()` 取账户 → 跟着页面 key 走 ✓
    """
    trading = (ROOT / 'minibt' / 'desk' / 'trading.py').read_text(
        encoding='utf-8')
    for name in ('def insert(', 'def cancel_order(', 'def action(',
                 'def _position('):
        assert name in trading, name
    # 下单 / 撤单 / 查单都用兜底 kwargs（不再出现"不带 account"的调用）
    assert trading.count('_order_account_kwargs(symbol)') >= 3

"""本地图表回放：退出/关闭时按当前收盘价平仓 + 指标回放可下单 ✓

用户需求（2026-11-21）：

1. 退出回放时如果有持仓 → 以**当前收盘价**在本地模拟账户平仓；
2. 关闭 desk 时若还在回放 → 同样处理；
3. 回放**跑完**不平仓（保持持仓），只有"退出 / 关闭"才平；
4. **策略回放**不可手动下单；**指标回放 / 纯 K 线回放**可以正常下单
   （以前报「下单参数不合法」—— 价格框留空时后端把 0 当非法参数 ✗）
"""
from __future__ import annotations

import pytest

from minibt.desk.local_data import LocalSim


@pytest.fixture()
def sim(tmp_path):
    store = LocalSim(initial_cash=100000.0,
                     db_path=str(tmp_path / 'acct.db'))
    store.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                       margin_rate=0.1)
    store.set_price('rb2601_60', 3500.0, 0)
    return store


def test_blank_price_uses_current_price(sim):
    """价格留空（对手价）→ 用**现价**成交，不再报"参数不合法" ✓"""
    result = sim.order('rb2601_60', 'buy', 2, 0)
    assert result.get('ok'), result
    assert result['order']['price'] == pytest.approx(3500.0)
    assert sim.book('rb2601_60')['long'] == pytest.approx(2.0)


def test_close_positions_at_replay_price(sim):
    """退出回放：按**当前收盘价**平仓（不是成本价 / 不是挂单 ✓）"""
    sim.order('rb2601_60', 'buy', 3, 3500.0, force=True)
    sim.set_price('rb2601_60', 3550.0, 0)
    closed = sim.close_positions(['rb2601_60'], {'rb2601_60': 3580.0})
    assert closed == ['rb2601_60']
    book = sim.book('rb2601_60')
    assert float(book.get('long') or 0) == 0.0
    # 成交记录里最后一笔平仓价 = 回放收盘价 ✓
    trades = [item for item in sim.trades
              if str(item.get('symbol')) == 'rb2601_60']
    assert trades, sim.trades
    assert float(trades[-1].get('price') or 0) == pytest.approx(3580.0)
    # 已实现盈亏 = (3580-3500)*3手*10乘数 = 2400 ✓
    assert sim.realized == pytest.approx(2400.0)


def test_close_positions_skips_flat_and_unknown(sim):
    """没持仓的合约不动；没有价格也不乱成交 ✓"""
    assert sim.close_positions(['rb2601_60']) == []


def test_replay_exit_closes_and_keeps_finish_positions():
    """`_on_replay_exit` 平仓；回放**跑完**（不退出）不平仓 ✓"""
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('rb2601_60', 3500.0, 0)
    sim.order('rb2601_60', 'buy', 1, 3500.0, force=True)

    # 回放开始 / 推进：记下"动过的合约"
    desk._on_replay_price({'symbol': 'rb2601_60', 'price': 3600.0,
                           'cells': [{'symbol': 'rb2601_60',
                                      'price': 3600.0}]})
    assert 'rb2601_60' in desk._replay_open_symbols

    # 回放跑完 → 只暂停，不平仓 ✓
    assert float(sim.book('rb2601_60').get('long') or 0) == 1.0

    # 退出回放 → 按最后那根收盘价平掉 ✓
    desk._on_replay_exit({'local': True, 'symbol': 'rb2601_60',
                          'cells': [{'symbol': 'rb2601_60',
                                     'price': 3605.0}]})
    assert float(sim.book('rb2601_60').get('long') or 0) == 0.0


def test_desk_close_flattens_replay_positions():
    """关闭 desk 时还在回放 → 也要平仓 ✓"""
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('rb2601_60', 3500.0, 0)
    sim.order('rb2601_60', 'buy', 2, 3500.0, force=True)
    desk._replay_open_symbols.add('rb2601_60')
    desk.close()
    assert float(sim.book('rb2601_60').get('long') or 0) == 0.0


def test_strategy_replay_blocks_manual_order():
    """策略回放中手动下单被拦；指标 / K 线回放 → 正常下单 ✓"""
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('rb2601_60', 3500.0, 0)
    desk.sent.clear()

    def long_qty() -> float:
        return float(sim.book('rb2601_60').get('long') or 0)

    # 指标 / K 线回放（没有策略 runner）：允许下单，价格留空 = 对手价 ✓
    desk._local_replay_active = True
    desk._on_local_order({'symbol': 'rb2601_60', 'side': 'buy',
                          'volume': 1, 'price': 0})
    assert long_qty() == 1.0

    # 策略回放：有 runner + 正在回放 → **手动**下单被拦掉 ✓
    desk._local_runners = {'demo': {'runner': object()}}
    desk._on_local_order({'symbol': 'rb2601_60', 'side': 'buy',
                          'volume': 1, 'price': 0})
    assert long_qty() == 1.0

    # 策略自己的成交（`auto=True`）不能被拦 ✓
    desk._on_local_order({'symbol': 'rb2601_60', 'side': 'buy',
                          'volume': 1, 'price': 0, 'auto': True})
    assert long_qty() == 2.0

    # 退出回放后（`_local_replay_active=False`）→ 手动下单又恢复 ✓
    desk._local_replay_active = False
    desk._on_local_order({'symbol': 'rb2601_60', 'side': 'buy',
                          'volume': 1, 'price': 0})
    assert long_qty() == 3.0


def test_local_position_rows_expose_raw_fields(sim):
    """持仓表必须带 `raw`（右键菜单要 symbol / side / volume ✓）

    以前只给 `rows`（预格式化字符串）→ 前端拿到空合约 / 0 手 →
    右键"平"发到真实交易通道 → 提示「交易未启用」✗
    """
    sim.order('rb2601_60', 'buy', 2, 3500.0, force=True)
    payload = sim.payload('rb2601_60')
    raw = payload['tables']['positions']['raw']
    assert raw and raw[0]['symbol'] == 'rb2601_60'
    assert raw[0]['side'] == '多'
    assert raw[0]['volume'] == pytest.approx(2.0)
    orders_raw = payload['tables']['orders']['raw']
    assert orders_raw and 'order_id' in orders_raw[0]


def test_local_close_side_by_volume_and_side(sim):
    """锁仓：右键"平多"只平多、按手数；价格 = 市价 ✓"""
    sim.order('rb2601_60', 'buy', 3, 3500.0, force=True)
    sim.order('rb2601_60', 'sell', 1, 3500.0, force=True)
    sim.set_price('rb2601_60', 3520.0, 0)

    done = sim.close_side('rb2601_60', '多', 2)
    assert done == [('多', 2.0, 3520.0)]
    book = sim.book('rb2601_60')
    assert book['long'] == pytest.approx(1.0)
    assert book['short'] == pytest.approx(1.0)     # 空单不动 ✓

    # 全平（多空一起）→ 都按市价成交 ✓
    done = sim.close_side('rb2601_60')
    assert {side for side, _q, _p in done} == {'多', '空'}
    assert all(price == pytest.approx(3520.0) for _s, _q, price in done)
    book = sim.book('rb2601_60')
    assert book['long'] == 0 and book['short'] == 0


def test_local_account_action_close_reverse_all_use_market():
    """右键 平 / 反手 / 全平 → 本地模拟账户**市价**成交（不再"交易未启用"）✓"""
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('rb2601_60', 3500.0, 0)
    sim.order('rb2601_60', 'buy', 2, 3500.0, force=True)
    sim.set_price('rb2601_60', 3510.0, 0)

    # 平（多，1 手）→ 按市价 3510 成交 ✓
    desk._on_local_account_action({'action': 'close',
                                   'symbol': 'rb2601_60',
                                   'side': '多', 'volume': 1})
    assert sim.book('rb2601_60')['long'] == pytest.approx(1.0)
    assert sim.trades[-1]['price'] == pytest.approx(3510.0)

    # 反手 → 平掉剩余 1 手多 + 开 1 手空，都按市价 ✓
    desk._on_local_account_action({'action': 'reverse',
                                   'symbol': 'rb2601_60'})
    book = sim.book('rb2601_60')
    assert book['long'] == 0
    assert book['short'] == pytest.approx(1.0)
    assert sim.trades[-1]['price'] == pytest.approx(3510.0)

    # 全平 → 空单也按市价平掉 ✓
    desk._on_local_account_action({'action': 'all',
                                   'symbol': 'rb2601_60'})
    book = sim.book('rb2601_60')
    assert book['long'] == 0 and book['short'] == 0
    assert sim.trades[-1]['price'] == pytest.approx(3510.0)


def test_frontend_local_maps_position_action():
    """本地图表必须把 `position_action` / `order_action` 转本地账户命令 ✓"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    at = source.index("cmd === 'account_action'")
    body = source[at:at + 400]
    assert "cmd === 'position_action'" in body
    assert "cmd === 'order_action'" in body
    assert "'local_account_action'" in body


def test_realtime_replay_paths_untouched():
    """⚠ 实时图表的下单 / 账户**不受**本地回放改动影响 ✓（用户 2026-11-21）

    * `replay_price`（实时图表：单个 symbol、没有 `cells`）→ 不登记"本地回放"
      → 不拦手动下单、不在关窗时误平；
    * `replay_exit`（实时图表：没有 `local`）→ 不平仓（保持原行为）；
    * `replay_order`（实时图表回放下单）→ 永远不拦。
    """
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('SHFE.ag2612', volume_multiple=15, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('SHFE.ag2612', 13900.0, 1)
    sim.order('SHFE.ag2612', 'buy', 1, 13900.0, force=True)

    # 实时图表回放推进（没有 cells）→ 不算"本地回放在跑"
    desk._local_runners = {'S': {'runner': object()}}
    desk._on_replay_price({'symbol': 'SHFE.ag2612', 'price': 13950.0})
    assert desk._local_replay_active is False
    assert 'SHFE.ag2612' not in desk._replay_open_symbols

    # 实时图表回放下单 → 不拦 ✓
    desk.sent.clear()
    desk._on_replay_order({'symbol': 'SHFE.ag2612', 'side': 'buy',
                           'qty': 1, 'price': 13950.0})
    assert float(sim.book('SHFE.ag2612').get('long') or 0) == 2.0

    # 实时图表退出回放（没有 local）→ 持仓**不变** ✓
    desk._on_replay_exit({'symbol': 'SHFE.ag2612', 'price': 13960.0})
    assert float(sim.book('SHFE.ag2612').get('long') or 0) == 2.0


def test_local_replay_price_marks_local_active():
    """本地图表回放（带 `cells`）才登记 → 才能拦手动下单 / 退出平仓 ✓"""
    from tests.test_minibt_desk_realtime_pages import _desk  # noqa: PLC0415

    desk = _desk()
    sim = desk.local_sim()
    sim.set_contract('rb2601_60', volume_multiple=10, price_tick=1.0,
                     margin_rate=0.1)
    sim.set_price('rb2601_60', 3500.0, 0)
    desk._on_replay_price({'symbol': 'rb2601_60', 'price': 3510.0,
                           'cells': [{'symbol': 'rb2601_60',
                                      'price': 3510.0, 'index': 3}]})
    assert desk._local_replay_active is True
    assert 'rb2601_60' in desk._replay_open_symbols

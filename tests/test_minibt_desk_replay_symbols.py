"""回放：策略下单的合约名 / 账户规格 / 现价必须**是同一个名字** ✓

用户 2026-11-2x 实测（`tutorials/basic/strategy_replay.py`）：

* 持仓盈亏恒为 0；
* 初始 10 万，可用资金变成 1,008,461（多出来一笔名义本金）；
* 账户权益只少了手续费（999,993）。

根因：
1. `StrategyRunner.source_of_kline()` 用 `_seed_order + _requests` 拼名字，
   但默认 seed KLine 不在 `_seed_order` 里 → 下标错位：
   seed 拿到了 `test`，真正的 `self.data` 找不到名字 → 回退成 DataFrame 的
   `DCE.l2609`；
2. `LocalSim` 登记的规格是 `l2609_60`，下单 / 成交却是 `DCE.l2609`
   → 查不到 `margin_rate` → 按「现货」记账（可用资金暴涨 / 保证金 0）；
3. 回放现价更新的是图表名 `l2609_60`，持仓却是 `DCE.l2609`
   → 现价永远停在开仓价 → 浮盈恒 0。
"""
from __future__ import annotations

import pandas as pd

from minibt import Strategy
from minibt.desk.local_data import LocalSim


def _chart_frame(symbol: str = 'DCE.l2609', closes=(8460, 8464, 8468, 8472)):
    return pd.DataFrame({
        'datetime': pd.Series(pd.date_range(
            '2026-05-06 09:00', periods=len(closes), freq='min')).astype('int64'),
        'open': [float(value) for value in closes],
        'high': [float(value) + 4 for value in closes],
        'low': [float(value) - 4 for value in closes],
        'close': [float(value) for value in closes],
        'volume': [10.0] * len(closes),
        'symbol': [symbol] * len(closes),
        'duration': [60] * len(closes),
        'price_tick': [1.0] * len(closes),
        'volume_multiple': [5.0] * len(closes),
    })


class _BuyOnce(Strategy):
    """策略里用一个**对不上图表 CSV 名**的数据名（`test`）→ 走兜底路径 ✓"""

    params = dict(symbol='test')

    def __init__(self):
        self.data = self.get_kline(self.params.symbol)

    def next(self):
        if not self.data.position:
            self.data.buy(size=1)


def test_account_spec_and_orders_share_the_chart_symbol():
    from minibt.desk.strategy_runner import StrategyRunner

    frame = _chart_frame()
    runner = StrategyRunner(_BuyOnce, symbol='l2609_60', cycle=60)
    runner.prepare([('l2609_60', frame)], seed_kline=True)
    assert runner.replay(frame, 4)
    # 下单 = 图表数据名（不是 `test`，也不是 DataFrame 里的 `DCE.l2609`）✓
    assert runner.orders, runner.error
    assert {str(item['symbol']) for item in runner.orders} == {'l2609_60'}
    spec = runner.account_spec()
    contracts = spec['contracts']
    # `test` 不该再混进合约表（那是 seed KLine 错位的产物 ✗）
    assert set(contracts) == {'l2609_60'}
    assert contracts['l2609_60']['minibt_symbol'] == 'DCE.l2609'
    assert contracts['l2609_60']['volume_multiple'] == 5.0


def test_real_contract_alias_shares_position_and_specs():
    """下单用 `DCE.l2609`、现价用 `l2609_60` → 同一份持仓 / 保证金 / 浮盈 ✓"""
    sim = LocalSim(100000.0, 'fixed', 0.0)
    sim.prepare_replay(1_000_000.0, {
        'l2609_60': {'price_tick': 1.0, 'volume_multiple': 5.0,
                     'margin_rate': 0.05, 'slip_point': 0.0,
                     'commission': {'fixed_commission': 1.0},
                     'minibt_symbol': 'DCE.l2609'},
    })
    sim.set_price('l2609_60', 8468.0, 0)
    opened = sim.order('DCE.l2609', 'sell', 1, 8468.0)
    assert opened['ok'] and opened['fee'] == 1.0
    values = sim.payload('l2609_60')['values']
    # 开仓不付名义本金；权益 = 初始 - 手续费；保证金 = 8468 × 5 × 5%
    assert values['balance'] == 999_999.0
    assert values['margin'] == 2_117.0
    assert values['available'] == 999_999.0 - 2_117.0
    assert values['float_profit'] == 0.0
    # 回放推进一根（现价 8400）→ 空单浮盈 = (8468-8400) × 5
    sim.clear_hold('l2609_60')
    sim.set_price('l2609_60', 8400.0, 0)
    values = sim.payload('l2609_60')['values']
    assert values['float_profit'] == 340.0
    assert values['balance'] == 1_000_339.0
    rows = sim.payload('l2609_60')['tables']['positions']['rows']
    assert rows[0][0] == 'l2609_60' and rows[0][4] == '8,400'
    # 两种写法都能读到同一份持仓 ✓
    assert sim.book('DCE.l2609')['short'] == 1.0


def _desk(tmp_path, monkeypatch):
    from minibt.desk import local_data, user_prefs as up

    monkeypatch.setattr(up, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    monkeypatch.setenv('MINIBT_DESK_SIM_DB', str(tmp_path / 'sim.sqlite3'))
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    return desk


def test_local_chart_only_uses_the_local_sim_account(tmp_path, monkeypatch):
    """本地图表只关联本地模拟账户（切实盘 / 快期模拟都不影响 ✓）"""
    desk = _desk(tmp_path, monkeypatch)
    desk._local_pages = {'local:1': {0: 'l2609_60'}}
    desk._local_cell_names = {0: 'l2609_60'}
    payload = desk.account_payload(symbol='l2609_60', key='real')
    assert payload['type'] == 'local_account'
    assert payload['kind'] == 'local'
    assert payload['labels'] == ['本地模拟（回放）']
    # 本地页的账户目录只有一个「本地模拟（回放）」→ 不能切实盘 ✓
    assert desk.set_account_kind('real', 'local:1') is False
    kinds = [item for item in desk.sent
             if isinstance(item, str) and '"account_kind"' in item]
    assert kinds, '应推送本地模拟账户目录'
    assert '本地模拟（回放）' in kinds[-1]
    assert 'TqAccount' not in kinds[-1]

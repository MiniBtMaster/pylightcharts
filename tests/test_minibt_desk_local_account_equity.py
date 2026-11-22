"""本地模拟账户的「账户权益」口径（`LocalSim.payload` / `_account_values`）。

两个回归点：

1. **死代码清理**：`payload()` 里曾有一行 `balance = self.cash + market_value`
   算了但**从没用过**（`values['balance']` 取的是 `account['equity']`）。
   留着容易让人误以为账户权益 = 现金 + 名义市值 —— 期货按保证金口径，
   正确公式是 `cash + 浮动盈亏`（`_account_values().equity`）✓
2. **分析页格式串 BUG**：`analysis()` 里曾写成 `f'...: , .2f'`（逗号/点号两边
   有空格）→ `ValueError: Invalid format specifier`，只要有一个**平过仓**的
   合约，「本地模拟账户 → 分析」页就直接报错 ✗
"""
from __future__ import annotations

import pytest

from minibt.desk.local_data import LocalSim


@pytest.fixture()
def sim(tmp_path):
    return LocalSim(initial_cash=1_000_000.0, db_path=str(tmp_path / 'a.db'))


def test_payload_balance_equals_equity_not_cash_plus_market_value(sim, monkeypatch):
    """期货持仓：`balance` 必须走保证金口径（= equity），而不是 `现金+市值` ✓"""
    monkeypatch.setattr(sim, 'save', lambda: None)
    # 期货规格：1 手 × 10 倍 × 保证金率 10%（`set_contract` 是真实入口 ✓）
    sim.set_contract('DCE.v2609', volume_multiple=10, price_tick=1,
                     margin_rate=0.1)
    sim.set_price('DCE.v2609', 5000.0)
    sim.order('DCE.v2609', 'buy', 2, 5000.0)      # 现价 5000 → 立即成交 ✓

    payload = sim.payload('DCE.v2609')
    values = payload['values']
    account = sim._account_values()

    assert values['balance'] == pytest.approx(account['equity'])
    # 「现金 + 名义市值」是另一种口径（以前那行死代码算的就是它）——
    # 期货下两者**不该相等**，否则说明数据没能区分口径
    naive = sim.cash + values['market_value']
    assert naive != pytest.approx(account['equity'])


def test_analysis_payload_ok_after_closing(sim, monkeypatch):
    """平过仓之后「分析」页也要能出数据（以前格式串直接抛 ValueError ✗）"""
    monkeypatch.setattr(sim, 'save', lambda: None)
    sim.set_contract('DCE.v2609', volume_multiple=10, price_tick=1,
                     margin_rate=0.1)
    sim.set_price('DCE.v2609', 5000.0)
    sim.order('DCE.v2609', 'buy', 1, 5000.0)
    sim.set_price('DCE.v2609', 5010.0)
    sim.order('DCE.v2609', 'sell', 1, 5010.0, close=True)

    payload = sim.analysis()
    table = payload.get('table') or {}
    assert table.get('columns'), payload      # 列头在（顺带验证格式串没炸）
    rows = table.get('rows') or []
    assert rows, payload
    # 每行 7 列，最后一列是「已实现 - 手续费」，必须是能看的数字串 ✓
    last = rows[0][-1]
    assert len(rows[0]) == 7
    assert last.replace(',', '').replace('-', '').replace('.', '').isdigit(), last

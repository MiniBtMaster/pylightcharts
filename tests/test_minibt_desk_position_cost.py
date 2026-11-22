"""持仓表 / 持仓线：成本价与盈亏要和**券商终端（快期）**对得上（2026-11-03）

用户先报「成本 11,780.33、现价 11,748，3 手空单却亏 24,195」→ 打开**快期**
一看：持仓表同样写着 **开仓均价 11,780.3、亏损 -30,495**（当时最新价 12,458：
`(11780.3 − 12458) × 15 × 3 ≈ −30,495`）—— 说明**券商的成本价就是 11,780.33，
盈亏一直是对的**，白银本身就有隔夜持仓（用户自己想起 ✓）。

所以真正要修的是这三处（都已修 ✓）：

1. `market_value_*` 在期货上是 `nan`，`float(nan)` 原样返回 → 表格印出 `nan` ✗
   → `_num()` 把 NaN / inf 当"没数据"（显示 `--`）；
2. 持仓市值没乘**合约乘数**（期货 = 手数 × 乘数 × 最新价，
   快期 560,610 = 3 × 15 × 12,458）→ 新增 `position_value()`；
3. 「开仓价」= `open_price_*`（今仓）、「持仓均价」= `position_price_*`
   （真实成本）—— 两列的字段顺序以前是反的 ✗。

⚠️ **不要**拿 `float_profit_*` 去"反推改写"成本价：试过反推会把 11,780.33
算成 11,210.33，反而和快期对不上 ✗（`test_no_profit_derived_cost` 守这条）。
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 快期（券商终端）那笔真实持仓：3 手空、乘数 15、最新价 12,458
AG_POSITION = {
    'instrument_id': 'ag2612',
    'exchange_id': 'SHFE',
    'volume_short': 3,
    'open_price_short': 11780.33,       # 今仓开仓均价（快期「开仓均价」同一列）
    'position_price_short': 11780.33,   # 真实持仓成本（快期也是这个值 ✓）
    'float_profit_short': -30495.0,     # 快期「浮动盈亏」
    'volume_multiple': 15,
    'last_price': 12458.0,
    'market_value_short': float('nan'),
}


def test_position_cost_matches_broker_terminal():
    """成本价 / 盈亏和**快期**逐项一致（不许自己"算"出另一套 ✗）"""
    from minibt.desk.accounts import position_cost

    avg, profit = position_cost(
        AG_POSITION, 3, ('position_price_short', 'open_price_short'),
        ('float_profit_short',), '空')
    assert round(avg, 2) == 11780.33          # 快期「开仓均价」11780.3 ✓
    assert profit == -30495.0                 # 快期「浮动盈亏」-30,495 ✓
    # (11780.33 − 12,458) × 15 × 3 ≈ −30,495 ✓ 本来就自洽，不用改成本价
    assert round((avg - 12458.0) * 15 * 3, 2) == pytest.approx(-30495.0,
                                                             abs=0.5)


def test_no_profit_derived_cost():
    """护栏：**不能**拿盈亏反推改写成本价 ✗（会和快期对不上）"""
    text = (ROOT / 'minibt' / 'desk' / 'accounts.py').read_text(encoding='utf-8')
    assert 'derived' not in text
    # 反过来：盈亏只会"缺了才补"，不会被用来覆盖成本价 ✓
    assert 'if profit is None and avg and unit and last:' in text


def test_position_cost_prefers_position_price_when_consistent():
    """两个字段本来就一致（比如同一价位持有）→ 不瞎改 ✓"""
    from minibt.desk.accounts import position_cost

    row = dict(AG_POSITION, position_price_short=11210.33,
               open_price_short=11780.33)
    avg, profit = position_cost(
        row, 3, ('position_price_short', 'open_price_short'),
        ('float_profit_short',), '空')
    # 有 `position_price_*` 就用它（真实成本），不用今开仓均价 ✓
    assert round(avg, 2) == pytest.approx(11210.33, abs=0.01)
    # 盈亏原样用券商的（不因为成本价"看着不对"去改它 ✓）
    assert profit == -30495.0


def test_position_cost_fills_profit_when_missing():
    from minibt.desk.accounts import position_cost

    row = dict(AG_POSITION)
    row.pop('float_profit_short')
    avg, profit = position_cost(
        row, 3, ('position_price_short',), ('float_profit_short',), '空')
    # 没有盈亏字段 → 用成本价 × 最新价自己算 ✓
    assert profit == pytest.approx((11780.33 - 12458.0) * 15 * 3, abs=0.01)


def test_position_value_uses_multiplier_and_never_nan():
    from minibt.desk.accounts import position_value

    # 市值 = 手数 × 乘数 × 最新价（期货不能只乘均价 ✗）
    assert position_value(AG_POSITION, 3, 11780.33) == pytest.approx(
        3 * 15 * 12458.0)      # 快期「持仓市值」560,610 ✓
    # 字段是 NaN → 不能原样输出 `nan` ✗
    from minibt.desk.accounts import _money, _num

    assert _num(float('nan')) is None
    assert _money(float('nan')) == '--'


def test_positions_table_uses_consistent_avg_and_value():
    """账户面板「持仓」表：均价与盈亏自洽、市值不再是 `nan` ✓"""
    from minibt.desk.accounts import AccountView

    class Api:
        def get_position_list(self):
            return [dict(AG_POSITION)]

    view = AccountView.__new__(AccountView)      # 只测纯数据转换
    view.decimals_of = lambda code: 2            # type: ignore[assignment]
    result = AccountView._positions(view, Api(), {}, 20)
    assert result['columns'][4:7] == ['开仓价', '持仓均价', '浮动盈亏']
    row = result['rows'][0]
    assert row[0] == 'SHFE.ag2612' and row[1] == '卖' and row[2] == '3'
    assert row[4] == '11,780.33'                 # 开仓价（今开仓均价）✓
    assert row[5] == '11,780.33'                 # 持仓均价（真实成本）✓
    assert row[6] == '-30,495.00'                # 快期同值 ✓
    assert row[7] == '560,610.00'                # 3 × 15 × 12,458 ✓
    assert 'nan' not in ' '.join(str(cell) for cell in row)
    raw = result['raw'][0]
    assert round(raw['avg'], 2) == 11780.33


def test_chart_position_side_matches_broker():
    """图上持仓线 / 标签用**券商同一个成本价**（11,780.33），不自己反推 ✓"""
    from minibt.desk.app import _position_side

    side = _position_side(
        AG_POSITION, 3, ('position_price_short', 'open_price_short'),
        ('float_profit_short', 'position_profit_short'), '空')
    assert side['side'] == '空'
    assert side['volume'] == 3.0
    assert round(side['avg'], 2) == 11780.33
    assert side['profit'] == -30495.0
    # 线画在 11,780.33、标签写"亏损 30495.00" → 快期一致 ✓
    assert round((side['avg'] - 12458.0) * 15 * 3, 2) == pytest.approx(
        side['profit'], abs=0.5)


def test_source_guards_for_field_priority():
    """源码护栏：开仓价 / 持仓均价 / 成本价键的优先级不能又反回去 ✗"""
    text = (ROOT / 'minibt' / 'desk' / 'accounts.py').read_text(encoding='utf-8')
    assert "LONG_AVG = ('position_price_long', 'open_price_long')" in text
    assert "SHORT_AVG = ('position_price_short', 'open_price_short')" in text
    assert "LONG_PRICE = ('open_price_long', 'position_price_long')" in text
    assert "SHORT_PRICE = ('open_price_short', 'position_price_short')" in text
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "('position_price_short', 'open_price_short')" in app
    assert "('open_price_short', 'position_price_short')" not in app

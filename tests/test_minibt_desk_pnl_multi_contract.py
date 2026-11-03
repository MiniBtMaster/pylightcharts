"""多合约回测的「盈亏」副图空白（2026-10-30 用户实测 ✓）

现象：
* `tutorials/strategies/kalman_filter.py`（**多合约对冲**：pp2609 + l2609）回测
  有交易、有权益曲线，但回测结果页的**盈亏副图**只有坐标轴，没有一根盈亏竖线；
* `cmo.py`（单合约）就正常 —— 差别只在「多合约」。

根因（已用 Qt WebEngine 真渲染 + 控制台抓错定位）：
* 多合约策略两个腿经常在**同一根 K 线**成交 → `strategy_backtest_dict()` 的
  `pnl` 里出现**重复时间戳**（同一 `time` 两行）；
* `BacktestPage` 的「0 基准线」挂在一条隐藏 Line 上，`series.set()` 时把原始
  （含重复时间）的 frame 直接给 lightweight-charts；
* LWC 在**渲染阶段**（不是 setData 当场）抛 `Uncaught Error: Value is null` →
  这个 pane 整块画不出来（自定义序列的竖线也一起没了）✗。

修法：`pages._collapse_time()` —— 同一 `time` 的盈亏按 K 线**求和**（该根 K 线的
净盈亏），权益 / 回撤取最后一个；`draw_trade_lines` 的连线 / 标记同样去重。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pylightcharts import Window
from pylightcharts.abstract import AbstractChart


def _chart():
    captured = []
    window = Window(script_func=captured.append)
    window.loaded = True
    chart = AbstractChart(window)
    chart.set(pd.DataFrame({
        'time': pd.date_range('2026-04-20', periods=12, freq='min'),
        'open': np.arange(12, dtype=float) + 100,
        'high': np.arange(12, dtype=float) + 101,
        'low': np.arange(12, dtype=float) + 99,
        'close': np.arange(12, dtype=float) + 100.5,
        'volume': np.arange(12, dtype=float),
    }))
    captured.clear()                  # 丢掉 `chart.set()` 那批脚本
    chart.scripts = captured          # 后续断言用（离屏，脚本只记录不执行）
    return chart


def _pair_pnl() -> pd.DataFrame:
    """两条腿在同一根 K 线各成交一次（时间戳重复 ✓ 复现原 bug）"""
    times = list(pd.date_range('2026-04-20', periods=6, freq='min'))
    rows = []
    for index, stamp in enumerate(times):
        rows.append({'time': stamp, 'value': -24.0, 'kind': 'open'})
        rows.append({'time': stamp, 'value': float(index), 'kind': 'close'})
    return pd.DataFrame(rows)


def _equity(n: int = 12) -> pd.DataFrame:
    return pd.DataFrame({
        'time': pd.date_range('2026-04-20', periods=n, freq='min'),
        'value': 1e6 * np.cumprod(1 + np.linspace(0.0, -0.002, n)),
    })


# ------------------------------------------------------------- 单元：合并
def test_collapse_time_sums_pnl_per_bar():
    from minibt.strategy.pages import _collapse_time

    frame = _pair_pnl()
    assert frame['time'].duplicated().any()
    out = _collapse_time(frame, 'value', 'sum')
    assert not out['time'].duplicated().any()
    assert len(out) == 6
    # 同一根 K 线：-24（开仓手续费）+ index（平仓）→ 求和
    assert out['value'].iloc[0] == -24.0
    assert out['value'].iloc[3] == -21.0


def test_collapse_time_keeps_last_for_curves():
    from minibt.strategy.pages import _collapse_time

    frame = pd.DataFrame({
        'time': list(pd.date_range('2026-01-01', periods=3, freq='min')) * 2,
        'value': [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
    })
    out = _collapse_time(frame, 'value', 'last')
    assert list(out['value']) == [10.0, 20.0, 30.0]


def test_collapse_time_is_a_noop_without_duplicates():
    from minibt.strategy.pages import _collapse_time

    frame = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=3),
                          'value': [1.0, 2.0, 3.0]})
    assert _collapse_time(frame, 'value') is frame
    # 边界数据不炸
    assert _collapse_time(None) is None
    assert len(_collapse_time(pd.DataFrame(columns=['time', 'value']))) == 0


# ------------------------------------------------- 盈亏副图：不再出现重复时间
def test_pnl_series_has_unique_times():
    from minibt.strategy.pages import BacktestPage

    chart = _chart()
    page = BacktestPage(chart, show_drawdown=False)
    page.update(_equity(), pnl=_pair_pnl())
    assert page.panes.get('pnl') is not None

    scripts = '\n'.join(chart.scripts)
    # 自定义序列（盈亏竖线）的数据里，每一个 time 只能出现一次
    import json
    import re
    payloads = []
    for match in re.finditer(r'\.series\.setData\((\[.*?\])\)', scripts, re.S):
        try:
            payloads.append(json.loads(match.group(1)))
        except Exception:                                        # noqa: BLE001
            continue
    assert payloads, scripts[:400]
    for rows in payloads:
        times = [row.get('time') for row in rows
                 if isinstance(row, dict) and 'time' in row]
        if not times:
            continue
        assert len(times) == len(set(times)), '出现重复时间戳 → LWC 会抛 Value is null'
    # 盈亏那一组必须是**合并后**的 6 根，且带 shapes（竖线）
    pnl_rows = []
    for rows in payloads:
        if rows and isinstance(rows[0], dict) and 'shapes' in rows[0]:
            pnl_rows = rows
            break
    assert len(pnl_rows) == 6, [len(rows) for rows in payloads]
    assert all(row.get('shapes') for row in pnl_rows)


def test_equity_band_pane_still_works_with_duplicates():
    """权益 / 回撤也走同一个去重（防御：万一上游给了重复时间）✓"""
    from minibt.strategy.pages import BacktestPage

    chart = _chart()
    equity = _equity()
    dup = pd.concat([equity, equity], ignore_index=True)
    page = BacktestPage(chart, show_drawdown=False)
    page.update(dup)
    assert 'equity' in page.panes
    assert 'drawdown' not in page.panes        # 默认不画回撤 ✓


# ------------------------------------------------- 交易连线 / 标记：也要去重
def test_trade_lines_dedupe_times():
    from minibt.strategy import realtime as rt

    captured = []

    class _Series:
        name = ''

        def set(self, frame, shapes=None):
            captured.append(list(frame['time']))

    class _Chart:
        def add_custom_series(self, **_kw):
            return _Series()

    def _trade(index):
        return {'entry_index': index, 'exit_index': index + 1,
                'entry_price': 100.0, 'exit_price': 101.0, 'side': 'long'}

    class _Style:
        show = True
        line_color = None
        line_width = 3
        line_dash = 'dashed'

        def __getattr__(self, _name):                        # noqa: D105
            raise AttributeError(_name)

    import pandas as pd
    frame = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=5,
                                                freq='min')})
    # 两笔都落在同一个入场下标（同一根 K 线）→ 时间重复
    trades = [_trade(1), _trade(1)]
    original_lines = rt.extract_trade_lines
    rt.extract_trade_lines = lambda *a, **k: trades
    rt.resolve_tradestyle = lambda *a, **k: _Style()
    try:
        rt.draw_trade_lines(_Chart(), None, 'X', frame, 0, theme_dark=True)
    finally:
        rt.extract_trade_lines = original_lines
    assert captured, '没有下发交易连线'
    for times in captured:
        assert len(times) == len(set(times)), times


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

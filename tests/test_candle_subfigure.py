"""pylightcharts 的**蜡烛副图**（``category='candles'``）。

历史 bug：``extract_minibt_indicators`` 里对 ``iscandles`` 直接 ``continue``
（"蜡烛图类指标先跳过"），于是 pylightcharts 下蜡烛副图**整条不画**（bokeh 正常）。
现在改为：前 4 条（open/high/low/close）出一条 ``Candlestick``，同一指标里其余
可画线（CDV 的 ``ctl`` / ``sma1`` / ``sma2`` / ``ema1`` / ``ema2``）按同一个
``overlap``/``source`` 追加 —— 副图蜡烛时它们靠 ``source`` 落到**同一个副图**。
"""
import numpy as np
import pytest


@pytest.fixture()
def headless(monkeypatch):
    """把 StrategyWindow 的 Chart 换成 HeadlessChart（不出窗口）。"""
    import minibt.strategy.strategy_window as sw
    from pylightcharts.headless import HeadlessChart
    monkeypatch.setattr(
        sw, 'Chart',
        lambda *a, **kw: HeadlessChart(
            **{k: v for k, v in kw.items() if k != 'title'}))
    return sw


def _make(strategy_cls, indicator):
    from minibt import LocalDatas
    from minibt.utils import Config
    import minibt.btplot as btp
    k = LocalDatas.test.kline
    strat = btp._make_step_strategy(k, [indicator], Config(theme='dark'),
                                    'CDV')
    strat._start_strategy_run()
    return strat


def test_cdv_subfigure_has_candlestick_and_ma_lines(headless):
    import minibt.strategy.realtime as rt
    from minibt import LocalDatas

    k = LocalDatas.test.kline
    ind = k.tradingview.CumulativeDeltaVolume(
        showma1=True, showma2=True, showema1=True, showema2=True)
    strat = _make(None, ind)

    specs = rt.extract_minibt_indicators(strat, 0)
    kinds = {s.name: (s.kind, s.overlap) for s in specs}
    assert kinds.get('CumulativeDeltaVolume') == ('Candlestick', False), kinds
    for name in ('ctl', 'sma1', 'sma2', 'ema1', 'ema2'):
        assert name in kinds, (name, list(kinds))
        assert kinds[name][0] == 'Line', kinds[name]
        assert kinds[name][1] is False, kinds[name]

    chart = rt.RealtimeChart([strat], browser=False, realtime=False,
                             bars='chart', theme='dark', info_pages=False)
    # 主图 + 蜡烛副图 = 2 个 pane
    assert chart.chart.pane_count() == 2, chart.chart.pane_count()
    names = [getattr(s, 'name', '?') for s in chart.chart.lines()]
    assert 'CumulativeDeltaVolume' in names, names
    for name in ('sma1', 'sma2', 'ema1', 'ema2'):
        assert name in names, names


def test_cdv_line_mode_has_ctl_line(headless):
    """``style='Line'``：``ctl`` 有线；蜡烛 OHLC 全 NaN（渲染不出蜡烛）。"""
    import minibt.strategy.realtime as rt
    from minibt import LocalDatas

    k = LocalDatas.test.kline
    ind = k.tradingview.CumulativeDeltaVolume(style='Line')
    strat = _make(None, ind)
    specs = rt.extract_minibt_indicators(strat, 0)
    by_name = {s.name: s for s in specs}
    assert 'ctl' in by_name and by_name['ctl'].kind == 'Line', list(by_name)
    cand = by_name.get('CumulativeDeltaVolume')
    if cand is not None:
        assert cand.kind == 'Candlestick'
        for key in ('open', 'high', 'low', 'close'):
            arr = np.asarray(cand.ohlc[key], dtype=float)
            assert not np.isfinite(arr).any(), (key, arr[:5])

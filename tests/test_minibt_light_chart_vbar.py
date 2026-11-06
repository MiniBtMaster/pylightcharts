"""原生 pylightcharts 窗口的柱状指标配色 / 基线（2026-11-02 用户实测）

现象：`tutorials/basic/live_chart.py`（`bt.run()` → 原生 pylightcharts 窗口）
里策略的 MACD 柱体**全是指标线色（橙）**，用户写的

    self.macd.linestyle = dict(macdh=LineStyle(
        line_dash=LineDash.vbar, vbar_base=0.,
        vbar_up_color=Colors.red, vbar_down_color=Colors.green))

完全没生效（`Colors.red` 这种 `rgba(..., 100)` 的 alpha 还会被引擎夹成实色）。

根因：`minibt/strategy/light_chart.py` 建柱体时**只给 `macdh` 写死红绿**，
且从不传 `vbar_base`（LWC 的 `base`）→ 用户设的上下行色 / 基线全被忽略 ✗。
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from minibt.strategy import light_chart as lc

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FakeSeries:
    def __init__(self):
        self.data = None
        self._vbar_style = None

    def set(self, frame):
        self.data = frame


class FakeChart:
    def __init__(self):
        self.calls = []

    def create_histogram(self, **kwargs):
        self.calls.append(kwargs)
        return FakeSeries()


# ------------------------------------------------------------------ 样式解析
def test_vbar_style_reads_colors_and_base():
    up, down, base = lc._vbar_style({
        'vbar_up_color': 'rgba(10, 20, 30, 100)',     # 自定义色，alpha 0~255
        'vbar_down_color': '#26a69a',
        'vbar_base': 50,
    })
    assert up == 'rgba(10, 20, 30, 0.392)'            # alpha 归一化到 0~1 ✓
    assert down == '#26a69a'
    assert base == 50.0


def test_vbar_style_drops_palette_defaults():
    """调色板**默认**涨跌色（`Colors.bull_color` / `bear_color`）＝没设置 ✓

    用户 2026-11-03：柱体又暗又偏，跟成交量一个色 ✗ —— 正是因为库里默认
    就拿这两个半透明色当柱体色。丢掉之后 `_hist_color_column()` 会回退到
    K 线涨跌色（`vbar_base` 以上上涨色、以下下跌色）✓。
    """
    up, down, base = lc._vbar_style({
        'vbar_up_color': 'rgba(39, 157, 130, 100)',   # Colors.bull_color
        'vbar_down_color': 'rgba(200, 97, 100, 100)',  # Colors.bear_color
        'vbar_base': 0,
    })
    assert up is None and down is None
    assert base == 0.0


def test_vbar_style_prefers_color_base_and_defaults_to_zero():
    assert lc._vbar_style({'vbar_base': 5, 'vbar_color_base': 50})[2] == 50.0
    assert lc._vbar_style({})[2] == 0.0
    assert lc._vbar_style({'vbar_base': 'x'})[2] == 0.0


def test_hist_color_column_uses_explicit_colors():
    colors = lc._hist_color_column(
        [3.0, -2.0, 0.5, -0.1],
        {'vbar_base': 0.0, 'vbar_up_color': 'red', 'vbar_down_color': 'green'},
        'macdh')
    assert colors.tolist() == ['red', 'green', 'red', 'green']


def test_hist_color_column_honours_vbar_base():
    colors = lc._hist_color_column(
        [40, 60], {'vbar_base': 50.0,
                   'vbar_up_color': 'red', 'vbar_down_color': 'green'},
        'rsi')
    assert colors.tolist() == ['green', 'red']        # 40 < 50 < 60 ✓


def test_hist_color_column_defaults_to_kline_colors():
    """没配颜色 → 任何柱体线都按 K 线涨跌色分色（不只 macdh ✓）

    用户 2026-11-03：所有默认柱体（`LineStyle(line_dash=LineDash.vbar)`）
    都要求 `vbar_base` 以上涨色、以下跌色，除非自己配了颜色。
    """
    colors = lc._hist_color_column([1.0, -1.0], {}, 'macdh',
                                   default_up='#f00', default_down='#0f0')
    assert colors.tolist() == ['#f00', '#0f0']
    # 非 macdh 的柱体同样分色 ✓（以前保持单色 = 指标线色 ✗）
    colors = lc._hist_color_column([1.0, -1.0], {}, 'rsi',
                                   default_up='#f00', default_down='#0f0')
    assert colors.tolist() == ['#f00', '#0f0']
    # 调色板默认色（半透明）也被当作"没设置"→ 还是 K 线色 ✓
    colors = lc._hist_color_column(
        [2.0, -2.0],
        {'vbar_up_color': 'rgba(39, 157, 130, 100)',
         'vbar_down_color': 'rgba(200, 97, 100, 100)'},
        'ao', default_up='#f00', default_down='#0f0')
    assert colors.tolist() == ['#f00', '#0f0']
    # 没有默认色可用 / 只有一边颜色 → 不做逐点配色（避免一半 null ✗）
    assert lc._hist_color_column([1.0, -1.0], {}, 'rsi') is None
    assert lc._hist_color_column([1.0], {'vbar_up_color': 'red'}, 'x') is None


# ---------------------------------------------------------- 建序列（真流程）
def test_create_histogram_passes_base_and_colors():
    df = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=3)})
    ind = pd.DataFrame({'macdh': [3.0, -2.0, 0.0]})
    chart = FakeChart()
    line = lc.create_histogram_with_style(
        chart, df, ind, 'macdh',
        {'vbar_base': 0.0, 'vbar_up_color': 'red', 'vbar_down_color': 'green'},
        color='#ff9800', legend=True)
    call = chart.calls[0]
    assert call['name'] == 'macdh'
    assert call['base'] == 0.0                        # vbar_base → LWC base ✓
    assert line.data['color'].tolist() == ['red', 'green', 'green']
    assert line._vbar_style == ('red', 'green', 0.0)  # 实时更新要用 ✓


def test_create_histogram_without_base_keeps_default():
    df = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=2)})
    ind = pd.DataFrame({'macdh': [1.0, -1.0]})
    chart = FakeChart()
    lc.create_histogram_with_style(chart, df, ind, 'macdh', {}, color='#123456')
    assert 'base' not in chart.calls[0]              # 没设就不传（= 0 ✓）


def test_hist_point_color_for_realtime_updates():
    line = FakeSeries()
    line._vbar_style = ('red', 'green', 50.0)
    assert lc._hist_point_color(line, 60) == 'red'
    assert lc._hist_point_color(line, 40) == 'green'
    assert lc._hist_point_color(FakeSeries(), 1) is None


# ------------------------------------------------- pylightcharts 的 Histogram
def test_pylightcharts_histogram_supports_base():
    from pylightcharts import Window
    from pylightcharts.abstract import AbstractChart

    captured = []
    window = Window(script_func=captured.append)
    window.loaded = True
    chart = AbstractChart(window)
    chart.set(pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=4),
        'open': 1.0, 'high': 2.0, 'low': 0.5, 'close': 1.5, 'volume': 3.0,
    }))
    captured.clear()
    hist = chart.create_histogram(name='rsi', color='#f00', base=50.0)
    assert hist.base == 50.0
    assert 'base: 50.0' in captured[0]
    plain = chart.create_histogram(name='macdh', color='#0f0')
    assert plain.base is None
    assert 'base:' not in captured[-1]


# -------------------------------------- desk 策略线（本地图表 / 实时图表）✓
def _macd_strategy():
    from minibt import (Colors, LineDash, LineStyle, LocalDatas, Strategy)

    class _S(Strategy):
        params = dict(symbol='test')

        def __init__(self):
            self.data = self.get_kline(LocalDatas.test)
            self.macd = self.data.close.macd()
            self.macd.linestyle = dict(macdh=LineStyle(
                line_dash=LineDash.vbar, vbar_base=0.,
                vbar_up_color=Colors.red, vbar_down_color=Colors.green))

    strategy = _S()
    strategy._start_strategy_run()
    return strategy


def test_strategy_overlay_item_carries_vbar_colors():
    """desk 里「策略的 macdh」也要带 upColor/downColor（不是指标线色 ✗）"""
    from minibt.desk import strategy_overlay as so
    from minibt.strategy.realtime import extract_minibt_indicators
    from minibt import LocalDatas

    strategy = _macd_strategy()
    frame = LocalDatas.test.kline.pandas_object
    specs = extract_minibt_indicators(strategy, 0)

    class Runner:
        def specs(self, plot_id=0):
            return specs

        def frame(self, plot_id=0):
            return frame

        def signals(self, plot_id=0):
            return []

    items = so._items_for_plot(Runner(), 0, frame, frame)
    hist = next(item for item in items if item['label'] == 'macdh')
    assert hist['kind'] == 'hist'
    assert hist['base'] == 0.0
    # ★ 以前这里只读 `spec.up_color`（只有实时图表才填）→ 全是指标线色 ✗
    assert hist['upColor'] and hist['upColor'] != hist['color']
    assert hist['downColor'] and hist['downColor'] != hist['color']
    assert hist['upColor'] != hist['downColor']


def test_strategy_overlay_reads_vbar_base():
    from minibt.desk import strategy_overlay as so
    from minibt.strategy.realtime import IndicatorSpec

    spec = IndicatorSpec(name='rsi', overlap=False,
                         values=pd.Series([40.0, 60.0]),
                         kind='Histogram', vbar_base=50.0,
                         vbar_up_color='red', vbar_down_color='green',
                         source='rsi')
    frame = pd.DataFrame({
        'datetime': [1_700_000_000, 1_700_000_060],
        'time': [1_700_000_000, 1_700_000_060],
        'open': 1.0, 'high': 2.0, 'low': 0.5, 'close': 1.5, 'volume': 1.0,
    })

    class Runner:
        def specs(self, plot_id=0):
            return [spec]

        def frame(self, plot_id=0):
            return frame

        def signals(self, plot_id=0):
            return []

    items = so._items_for_plot(Runner(), 0, frame, frame)
    assert items and items[0]['base'] == 50.0
    assert items[0]['upColor'] == 'red' and items[0]['downColor'] == 'green'


# --------------------------------------------------------------- 源码护栏
def test_light_chart_no_longer_hardcodes_macdh_only():
    source = (ROOT / 'minibt' / 'strategy' / 'light_chart.py').read_text(
        encoding='utf-8')
    assert 'def create_histogram_with_style(' in source
    assert 'def _vbar_style(' in source
    assert 'def _hist_color_column(' in source
    # 建柱体不再各自手写「只认 macdh」的块 ✓
    assert source.count('create_histogram_with_style(') >= 3   # 定义 + 两处调用
    assert 'hist_data[\'color\'] = btcolors.bear_color' not in source


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

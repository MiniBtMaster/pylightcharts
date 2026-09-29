"""minibt.strategy.realtime —— `PlotInfo` -> pylightcharts 映射层单测。

不跑完整回测：用假的策略/数据集对象喂 `extract_minibt_*`，用 `HeadlessChart`
捕获下发的脚本，断言映射结果。覆盖：

* 样式映射表（线型 / 标记形状 / 尺寸）；
* `extract_minibt_{spans,bands,candlestyle,signal_texts}`；
* `apply_{spans,bands,histogram_colors,color_rules,signals}`。
"""
import importlib.util
import pathlib
import sys
import threading
import time

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pylightcharts.headless import HeadlessChart          # noqa: E402

RT_PATH = ROOT / 'minibt' / 'strategy' / 'realtime.py'
if not RT_PATH.exists():
    # 从 sdist 运行、或只装了 pip 版 minibt 时没有这个文件，整份跳过
    pytest.skip('minibt/strategy/realtime.py 不存在（跳过映射层单测）',
                allow_module_level=True)


def _load_realtime():
    spec = importlib.util.spec_from_file_location('minibt_realtime', RT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules['minibt_realtime'] = module       # dataclass 需要注册模块
    spec.loader.exec_module(module)
    return module


rt = _load_realtime()


# ------------------------------------------------------------------ 测试替身

class FakeStyle:
    """`SignalStyle` / `SpanStyle` / `BandStyle` 的替身（属性访问）。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeDataset:
    """`_btindicatordataset` 的值：只要 `_get_plot_datas` 的 11/13/10 项。"""

    def __init__(self, spans=(), bands=(), texts=None, plot_id=0,
                 iscandles=False):
        self.plot_id = plot_id
        self.iscandles = iscandles
        self.pandas_object = None
        self._spans = list(spans)
        self._bands = list(bands)
        self._texts = dict(texts or {})

    def _get_plot_datas(self, key):                # noqa: ARG002
        data = [None] * 14
        data[10] = {'signal_texts': self._texts}
        data[11] = self._spans
        data[13] = self._bands
        return tuple(data)


class FakeKline:
    """`_btklinedataset` 的值：`extract_minibt_candlestyle` 读的那几个属性。"""

    def __init__(self, contract='DCE.pp2609_60', up=None, down=None):
        symbol, cycle = contract.rsplit('_', 1)   # 'DCE.pp2601' + '60'
        self.symbol = symbol
        self.cycle = cycle
        self._light_chart_candles_up_color = up is not None
        self._light_chart_candles_down_color = down is not None
        self.bull_color = up
        self.bear_color = down


class FakeStrategy:
    def __init__(self, datasets=None, klines=None):
        self._btindicatordataset = datasets or {}
        self._btklinedataset = klines or {}


class FakeManager:
    def __init__(self, series, specs):
        self.series = list(series)
        self.specs = list(specs)


# -------------------------------------------------------------------- 工具

def make_frame(rows=4):
    base = np.arange(rows, dtype=float)
    return pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=rows, freq='min'),
        'open': base, 'high': base + 1.0, 'low': base, 'close': base,
        'volume': base,
    })


def make_chart(frame=None):
    chart = HeadlessChart(width=800, height=600)
    chart.set(make_frame() if frame is None else frame)
    return chart


def scripts(chart):
    return '\n'.join(chart._scripts)


# ------------------------------------------------------------ 样式映射表

@pytest.mark.parametrize('name,expected', [
    ('solid', 0), ('dotted', 1), ('dashed', 2), ('large_dashed', 3),
    ('sparse_dotted', 4), ('dotdash', 2), ('dashdot', 3), ('SOLID', 0),
])
def test_line_style_value(name, expected):
    assert rt.line_style_value(name) == expected


def test_unknown_line_style_falls_back_to_solid(capsys):
    assert rt.line_style_value('nope') == 0
    assert '未知线型' in capsys.readouterr().out


@pytest.mark.parametrize('name,expected', [
    ('triangle', 'arrow_up'), ('inverted_triangle', 'arrow_down'),
    ('circle', 'circle'), ('circle_cross', 'circle'), ('square', 'square'),
    ('dot', 'circle'), ('nope', 'circle'),
])
def test_marker_shape_value(name, expected):
    assert rt.marker_shape_value(name) == expected


def test_marker_size_is_clamped():
    assert rt.marker_size_value(12) == pytest.approx(1.0)
    assert rt.marker_size_value(1) >= 0.5
    assert rt.marker_size_value(999) <= 2.0


@pytest.mark.parametrize('value,expected', [
    ('red', 'red'), (None, None), ('', None),
])
def test_as_color(value, expected):
    assert rt._as_color(value, 'fallback') == (
        expected if expected is not None else 'fallback')


def test_iter_style_accepts_list_dict_and_single():
    span = FakeStyle(location=0)
    assert list(rt._iter_style([span])) == [span]
    assert list(rt._iter_style({'a': span})) == [span]
    assert list(rt._iter_style(span)) == [span]
    assert rt._iter_style(None) == []


# --------------------------------------------------------- extract_* 提取

def test_extract_spans():
    dataset = FakeDataset(spans=[FakeStyle(location=0.0, line_color='red',
                                           line_dash='dotted', line_width=2),
                                 FakeStyle(location=np.nan)])
    spans = rt.extract_minibt_spans(FakeStrategy({'cci': dataset}), 0)
    assert spans == [{'source': 'cci', 'price': 0.0, 'color': 'red',
                      'style': 'dotted', 'width': 2}]


def test_extract_spans_skips_other_plot():
    dataset = FakeDataset(spans=[FakeStyle(location=1.0)], plot_id=7)
    assert rt.extract_minibt_spans(FakeStrategy({'x': dataset}), 0) == []


def test_extract_spans_uses_defaults():
    dataset = FakeDataset(spans=[FakeStyle(location=-100.0)])
    span = rt.extract_minibt_spans(FakeStrategy({'c': dataset}), 0)[0]
    assert span['color'] == '#666666'
    assert span['style'] == 'dashed' and span['width'] == 1


def test_extract_bands():
    dataset = FakeDataset(bands=[FakeStyle(lower='cci', upper='zero',
                                           fill_color='steelblue',
                                           fill_alpha=0.3)])
    bands = rt.extract_minibt_bands(FakeStrategy({'cci': dataset}), 0)
    assert bands == [{'source': 'cci', 'lower': 'cci', 'upper': 'zero',
                      'color': 'steelblue', 'alpha': 0.3,
                      'line_color': None}]


def test_extract_bands_skips_incomplete():
    dataset = FakeDataset(bands=[FakeStyle(lower='a'), FakeStyle(upper='b')])
    assert rt.extract_minibt_bands(FakeStrategy({'x': dataset}), 0) == []


def test_extract_candlestyle_only_explicit_colors():
    kline = FakeKline(up='lime', down='#ff5722')
    strategy = FakeStrategy(klines={'k': kline})
    assert rt.extract_minibt_candlestyle(
        strategy, 'DCE.pp2609_60') == {'up': 'lime', 'down': '#ff5722'}


def test_extract_candlestyle_empty_when_unset():
    strategy = FakeStrategy(klines={'k': FakeKline()})
    assert rt.extract_minibt_candlestyle(strategy, 'DCE.pp2609_60') == {}


def test_extract_candlestyle_other_contract():
    strategy = FakeStrategy(klines={'k': FakeKline(up='lime')})
    assert rt.extract_minibt_candlestyle(strategy, 'SHFE.ni2601_60') == {}


def test_extract_signal_texts():
    dataset = FakeDataset(texts={'long_signal': ['', 'R', '', 'B']})
    texts = rt.extract_minibt_signal_texts(FakeStrategy({'d': dataset}), 0)
    assert texts == {'long_signal': ['', 'R', '', 'B']}


# ------------------------------------------------------------- apply_* 落地

def test_apply_spans_emits_horizontal_span():
    chart = make_chart()
    made = rt.apply_spans(chart, [{'source': 'x', 'price': 50.0,
                                   'color': 'red', 'style': 'dotted',
                                   'width': 2}])
    assert len(made) == 1
    out = scripts(chart)
    assert 'HorizontalSpan' in out
    assert "lineColor: 'red'" in out and 'filled: false' in out


def test_apply_bands_uses_fill_between_with_alpha():
    chart = make_chart()
    upper = chart.add_series('Line', name='zero')
    lower = chart.add_series('Line', name='cci')
    times = list(make_frame()['time'])
    upper.set(pd.DataFrame({'time': times, 'zero': [0.0] * 4}))
    lower.set(pd.DataFrame({'time': times,
                            'cci': [1.0, -1.0, 2.0, -2.0]}))
    spec = rt.IndicatorSpec(name='zero', overlap=False)
    spec.source = 'cci'
    lower_spec = rt.IndicatorSpec(name='cci', overlap=False)
    lower_spec.source = 'cci'
    manager = rt.IndicatorManager(chart)      # 用真管理器：需要 series_named
    manager.series = [upper, lower]
    manager.specs = [spec, lower_spec]
    rt.apply_bands(manager, [{'source': 'cci', 'lower': 'cci',
                              'upper': 'zero', 'color': 'steelblue',
                              'alpha': 0.3, 'line_color': None}])
    out = scripts(chart)
    assert 'LineFill' in out and 'opacity: 0.3' in out


def test_apply_bands_skips_missing_line():
    chart = make_chart()
    manager = FakeManager([], [])
    rt.apply_bands(manager, [{'source': 'cci', 'lower': 'a', 'upper': 'b',
                              'color': 'x', 'alpha': 1.0,
                              'line_color': None}])
    assert 'LineFill' not in scripts(chart)


def test_apply_histogram_colors_splits_by_base():
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Histogram', name='macdh')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'macdh': [-1.0, 2.0, -3.0, 4.0]}))
    spec = rt.IndicatorSpec(name='macdh', overlap=False,
                            values=pd.Series([-1.0, 2.0, -3.0, 4.0]),
                            kind='Histogram')
    spec.source = 'macd'
    manager = FakeManager([series], [spec])
    rt.apply_histogram_colors(manager, FakeStrategy(), '', 4)
    out = scripts(chart)
    assert '"color":"#26a69a"' in out or "'#26a69a'" in out


def test_apply_color_rules_on_kline_and_indicator():
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Line', name='ma')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'ma': [1.0, -1.0, 1.0, -1.0]}))
    kline = FakeKline()
    kline.__dict__['_color_rules'] = [{
        'condition': np.array([True, False, True, False]), 'color': 'red',
        'else_color': None, 'options': {'wick_color': 'orange'}}]
    dataset = FakeDataset()
    dataset.__dict__['_color_rules'] = [{
        'condition': np.array([True, True, False, False]), 'color': 'green',
        'else_color': 'gray', 'options': {}}]
    strategy = FakeStrategy({'ma': dataset}, {'k': kline})
    spec = rt.IndicatorSpec(name='ma', overlap=True)
    spec.source = 'ma'
    rt.apply_color_rules(chart, FakeManager([series], [spec]), strategy,
                         'DCE.pp2609_60')
    out = scripts(chart)
    assert 'orange' in out            # K 线：逐根变色
    assert 'gray' in out              # 指标：else_color


def test_indicator_reslice_keeps_histogram_colors_on_update():
    """回放逐根推进（`reslice` 增量分支 / 整段 set）都要保持柱体配色。

    历史 bug：增量分支只发 `{time, value}`，新柱子掉回系列默认色 —— 回放时
    看着就是“macd / rsi 变回 line_color”。
    """
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Histogram', name='macdh')
    values = pd.Series([1.0, -1.0, 2.0, -2.0])
    series.set(pd.DataFrame({'time': list(frame['time']), 'macdh': values}))
    spec = rt.IndicatorSpec(name='macdh', overlap=False, kind='Histogram',
                            values=values, vbar_base=0.0,
                            vbar_up_color='red', vbar_down_color='green',
                            up_color='red', down_color='green')
    manager = rt.IndicatorManager(chart)
    manager.align = 'tail'
    manager.series, manager.specs = [series], [spec]

    # 增量：2 -> 4 根，只 update 后两根，但必须带颜色
    chart._scripts.clear()
    manager.reslice(frame, previous=2)
    joined = '\n'.join(chart._scripts)
    assert '"color":"red"' in joined and '"color":"green"' in joined, joined

    # 整段 set 也要把颜色刷回来
    chart._scripts.clear()
    manager.reslice(frame)
    joined = '\n'.join(chart._scripts)
    assert '"color":"red"' in joined and '"color":"green"' in joined, joined


def test_bokeh_pops_every_minibt_only_linestyle_key():
    """`LineStyle` 里 bokeh 不认识的字段，必须在传给 bokeh 前全部剔除。

    历史 bug：新增 `vbar_up_color` / `vbar_color_base` 时漏了剔除，bokeh 直接
    报 `AttributeError: unexpected attribute '...' to Line`。这个测试把"每个
    非 bokeh 字段都要有对应的 pop/del"钉住。
    """
    import dataclasses
    try:
        from minibt.utils import LineStyle
    except Exception:
        pytest.skip('minibt not importable')
    bokeh_line_keys = {'line_dash', 'line_width', 'line_color', 'name'}
    minibt_only = {f.name for f in dataclasses.fields(LineStyle)} - bokeh_line_keys
    for relative in ('minibt/strategy/bokeh_plot.py', 'minibt/btplot.py'):
        path = ROOT / relative
        if not path.exists():
            continue
        source = path.read_text(encoding='utf-8', errors='ignore')
        for key in sorted(minibt_only):
            popped = (f'_lineinfo.pop("{key}", None)' in source
                      or f'del _lineinfo["{key}"]' in source)
            assert popped, (relative, key)


def test_replay_build_indicators_applies_all_decorations(monkeypatch):
    """回放路径必须也应用「柱体配色 / 逐点配色 / 色带 / 水平线 / K 线涨跌色」。

    历史 bug：这些只在 `RealtimeChart._rebuild_indicators` 里调用了，回放
    （`ReplayWindow._build_indicators`）漏掉 —— 表现就是 replay 里 macd 柱子
    颜色不生效（只有 vbar 形状，没有上下行配色）。
    """
    try:
        import minibt.strategy.realtime as real
        import minibt.strategy.replay_window as rw
    except Exception:                    # 没有 minibt 包：跳过
        pytest.skip('minibt not importable')
    called = []
    names = ('apply_histogram_colors', 'apply_color_rules', 'apply_bands',
             'apply_spans', 'apply_candlestyle', 'apply_watermark',
             'palette_for', 'strategy_contracts', 'strategy_watermark',
             'extract_minibt_bands', 'extract_minibt_spans',
             'extract_minibt_candlestyle')
    for name in names:
        assert hasattr(real, name), name
        monkeypatch.setattr(real, name,
                            lambda *a, _n=name, **k: called.append(_n))
    # `strategy_contracts` 要返回列表（代码里会 .index(contract)）
    monkeypatch.setattr(real, 'strategy_contracts',
                        lambda *a, **k: (called.append('strategy_contracts'),
                                         ['X_60'])[1])

    frame = make_frame()
    chart = FakeStyle(candle_data=pd.DataFrame(
        {'time': list(frame['time']), 'open': 1.0, 'high': 2.0, 'low': 0.5,
         'close': 1.5, 'volume': 1.0}))
    holder = FakeStyle(
        chart=chart,
        indicators_of=lambda strategy, contract: [object()],
        window=FakeStyle(strategy='S', contract='X_60',
                         _apply_pane_stretch=lambda: called.append('stretch')),
        _strategy_by_name=lambda name: FakeStyle(),
        _refresh_signals=lambda frame=None: called.append('signals'),
        spans=[])
    holder._indicator_manager = FakeStyle(
        build=lambda *a, **k: called.append('manager.build'))

    rw.ReplayWindow._build_indicators(holder)

    for expected in ('manager.build', 'apply_histogram_colors',
                     'apply_color_rules', 'apply_bands', 'apply_spans',
                     'apply_candlestyle'):
        assert expected in called, (expected, called)


def test_vbar_line_style_colors_control_histogram():
    """`LineStyle(vbar_up_color/vbar_down_color, vbar_base)` 控制柱体上下行颜色。

    不设颜色时跟主图 K 线色一致（`strategy_candle_colors`）。
    """
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Histogram', name='macdh')

    class _Manager:                 # 无 view_values/spec_values：落回 spec.values
        def __init__(self, s, sp):
            self.series, self.specs = [s], [sp]

    values = pd.Series([1.0, -1.0, 2.0, -2.0])
    series.set(pd.DataFrame({'time': list(frame['time']), 'macdh': values}))
    spec = rt.IndicatorSpec(name='macdh', overlap=False, kind='Histogram',
                            values=values, vbar_base=0.0,
                            vbar_up_color='red', vbar_down_color='green')
    rt.apply_histogram_colors(_Manager(series, spec), FakeStrategy(),
                              'DCE.pp2609_60', len(values))
    assert series.data['color'].tolist() == ['red', 'green', 'red', 'green']
    assert (spec.up_color, spec.down_color) == ('red', 'green')

    # 不设颜色：跟 K 线色（这里没有 -> pylightcharts 默认涨/跌色）
    spec2 = rt.IndicatorSpec(name='macdh2', overlap=False, kind='Histogram',
                             values=values, vbar_base=0.0)
    series2 = chart.add_series('Histogram', name='macdh2')
    series2.set(pd.DataFrame({'time': list(frame['time']), 'macdh2': values}))
    rt.apply_histogram_colors(_Manager(series2, spec2), FakeStrategy(),
                              'DCE.pp2609_60', len(values))
    assert series2.data['color'].tolist() == ['#26a69a', '#ef5350',
                                              '#26a69a', '#ef5350']

    # `vbar_color_base`：柱子仍从 vbar_base(0) 画，但按 1.5 分色
    spec3 = rt.IndicatorSpec(name='macdh3', overlap=False, kind='Histogram',
                             values=values, vbar_base=0.0,
                             vbar_color_base=1.5, vbar_up_color='red',
                             vbar_down_color='green')
    series3 = chart.add_series('Histogram', name='macdh3')
    series3.set(pd.DataFrame({'time': list(frame['time']), 'macdh3': values}))
    rt.apply_histogram_colors(_Manager(series3, spec3), FakeStrategy(),
                              'DCE.pp2609_60', len(values))
    # values = [1, -1, 2, -2] vs 1.5 -> [F, F, T, F]
    assert series3.data['color'].tolist() == ['green', 'green', 'red', 'green']

    # 显式 line_color 且没给上下行色：整段单色（不逐点配色）
    spec4 = rt.IndicatorSpec(name='macdh4', overlap=False, kind='Histogram',
                             values=values, vbar_base=0.0, color='blue')
    series4 = chart.add_series('Histogram', name='macdh4')
    series4.set(pd.DataFrame({'time': list(frame['time']), 'macdh4': values}))
    rt.apply_histogram_colors(_Manager(series4, spec4), FakeStrategy(),
                              'DCE.pp2609_60', len(values))
    assert 'color' not in series4.data.columns
    assert (spec4.up_color, spec4.down_color) == ('blue', 'blue')


def test_apply_color_rules_ignores_missing_condition():
    chart = make_chart()
    kline = FakeKline()
    kline.__dict__['_color_rules'] = [{'condition': None, 'color': 'red'}]
    strategy = FakeStrategy(klines={'k': kline})
    rt.apply_color_rules(chart, FakeManager([], []), strategy,
                         'DCE.pp2609_60')
    assert 'red' not in scripts(chart)   # condition 为 None → 不下发


def test_color_rules_tail_align_when_chart_loaded_more_history():
    """实盘「无限历史」：图比条件长（401/601 vs 200）时按尾部对齐。

    老 K 线（条件未覆盖）必须**不套色**，而不是被 `else_color` 统一刷色
    （历史 bug：直接报 `condition has 200 rows but the frame has 601`）。
    """
    n = 601
    times = pd.date_range('2024-01-01', periods=n, freq='min')
    frame = pd.DataFrame({'time': times, 'open': 1.0, 'high': 2.0,
                          'low': 0.5, 'close': 1.5, 'volume': 1.0})
    chart = make_chart(frame)
    mask = np.zeros(200, dtype=bool)
    mask[-1] = True
    kline = FakeKline()
    kline.__dict__['_color_rules'] = [{
        'condition': mask, 'color': 'red', 'else_color': 'blue',
        'options': {}}]
    strategy = FakeStrategy(klines={'k': kline})
    manager = FakeManager([], [])
    manager.align = 'tail'
    rt._COLOR_BY_WARNED.clear()
    rt.apply_color_rules(chart, manager, strategy, 'DCE.pp2609_60')
    assert not rt._COLOR_BY_WARNED, rt._COLOR_BY_WARNED   # 不再报长度不匹配
    colors = list(chart.candle_data['color'])
    assert len(colors) == n
    assert set(colors[:n - 200]) == {None}     # 老 K 线：保持原色
    assert colors[-1] == 'red'                 # 最后 200 根：命中
    assert colors[-2] == 'blue'                # 最后 200 根：未命中


# ----------------------------------------------------------------- 信号

def test_apply_signals_forwards_marker_and_text():
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='circle_cross',
                      size=12, label=FakeStyle(text='B', size=9,
                                               color='blue'))
    rt.apply_signals(chart, frame,
                     [('long_signal', np.array([0.0, 1.0, 0.0, 1.0]), style)])
    out = scripts(chart)
    assert '"marker":"circle_cross"' in out      # 原样透传 minibt 名字
    assert '"type":"marker"' in out and '"type":"text"' in out
    assert '"text":"B"' in out


def test_apply_signals_per_point_texts_win():
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='triangle', size=12,
                      label=FakeStyle(text='B', size=9, color='blue'))
    rt.apply_signals(chart, frame,
                     [('long_signal', np.array([0.0, 1.0, 0.0, 0.0]), style)],
                     {'long_signal': ['', 'R', '', '']})
    out = scripts(chart)
    assert '"text":"R"' in out and '"text":"B"' not in out


def test_apply_signals_skips_when_no_signal():
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='triangle', size=12)
    rt.apply_signals(chart, frame,
                     [('long_signal', np.zeros(4), style)])
    assert '"type":"marker"' not in scripts(chart)


def test_apply_signals_short_uses_high_anchor():
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='high', color='green', marker='inverted_triangle',
                      size=12)
    rt.apply_signals(chart, frame,
                     [('short_signal', np.array([0.0, 0.0, 1.0, 0.0]), style)])
    out = scripts(chart)
    assert '"marker":"inverted_triangle"' in out
    assert '"offset":-2.0' in out                # 上方信号锚点为尖端


def test_apply_signals_returns_deletable_series():
    """信号是自定义序列，返回值必须能 delete（切策略/合约时清理用）。"""
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='triangle', size=12)
    made = rt.apply_signals(
        chart, frame,
        [('long_signal', np.array([0.0, 1.0, 0.0, 0.0]), style)])
    assert len(made) == 1
    made[0].delete()
    assert 'removeSeries' in scripts(chart)


# ------------------------------------------------- 实盘更新（重取 + 逐点配色）

class ValueDataset:
    """`_get_plot_datas` 第 8 项带数值的替身（模拟会被策略重建的指标对象）。"""

    def __init__(self, values, plot_id=0):
        self.plot_id = plot_id
        self.iscandles = False
        self.pandas_object = None
        self._values = np.asarray(values, dtype=float)

    def _get_plot_datas(self, key):            # noqa: ARG002
        data = [None] * 14
        data[8] = self._values.reshape(-1, 1) if self._values.ndim == 1 \
            else self._values
        return tuple(data)


def test_indicator_values_resolve_fresh_dataset():
    """实盘每次跑策略会重建指标对象，取值必须按 key 现取而不是闭包旧对象。"""
    strategy = FakeStrategy({'ma': ValueDataset([1.0, 2.0, 3.0])})
    get_values = rt._indicator_values(strategy, 'ma', 0, 0)
    assert list(get_values()) == [1.0, 2.0, 3.0]
    strategy._btindicatordataset['ma'] = ValueDataset([1.0, 2.0, 3.0, 9.9])
    assert list(get_values()) == [1.0, 2.0, 3.0, 9.9]


def test_update_last_sends_histogram_color():
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Histogram', name='macdh')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'macdh': [0.5, -1.0, 2.0, -3.0]}))
    spec = rt.IndicatorSpec(name='macdh', overlap=False, kind='Histogram',
                            up_color='lime', down_color='tomato',
                            get_values=lambda: np.array([0.5, -1.0, 2.0,
                                                         -3.0]))
    manager = rt.IndicatorManager(chart)
    manager.series, manager.specs = [series], [spec]
    manager.update_last(frame['time'].iloc[-1])
    out = scripts(chart)
    assert '"value":-3.0' in out and '"color":"tomato"' in out


def test_update_last_sends_color_rule():
    """均线等 color_by 线更新最后一点时要带颜色，否则会掉回基色。"""
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Line', name='ma')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'ma': [1.0, 2.0, 3.0, 4.0]}))
    spec = rt.IndicatorSpec(name='ma', overlap=True, color='yellow',
                            get_values=lambda: np.array([1.0, 2.0, 3.0,
                                                         4.0]),
                            color_conditions=[
                                (np.array([False, False, True, True]),
                                 'orange', None)])
    manager = rt.IndicatorManager(chart)
    manager.series, manager.specs = [series], [spec]
    manager.update_last(frame['time'].iloc[-1])
    assert '"color":"orange"' in scripts(chart)


def test_update_last_skips_nan_point():
    """全 NaN 的线（如未触发的止损线）不推更新，避免 value 被 pandas 转成 NaT。"""
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Line', name='stop')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'stop': [np.nan] * 4}))
    spec = rt.IndicatorSpec(name='stop', overlap=True,
                            get_values=lambda: np.array([np.nan] * 4))
    manager = rt.IndicatorManager(chart)
    manager.series, manager.specs = [series], [spec]
    before = len(chart._scripts)
    manager.update_last(frame['time'].iloc[-1])
    assert len(chart._scripts) == before          # 没有下发 update


def test_signal_manager_updates_add_remove_and_hold():
    """tick 中信号出现 / 保持 / 消失；换根时最后两根重新计算。"""
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='triangle', size=12,
                      label=FakeStyle(text='B', size=9, color='blue'))
    manager = rt.SignalManager(chart)

    def rows():
        series = manager.series.get('long_signal')
        return 0 if series is None else len(series.data)

    manager.update(frame, [('long_signal', np.array([0., 1., 0., 0.]), style)])
    assert rows() == 1                       # 第 2 根出现信号
    manager.update(frame, [('long_signal', np.array([0., 1., 1., 0.]), style)])
    assert rows() == 1                       # 条件保持 -> 仍然只有一个
    manager.update(frame, [('long_signal', np.array([0., 1., 0., 1.]), style)])
    assert rows() == 2                       # 末根新信号
    manager.update(frame, [('long_signal', np.array([0., 0., 0., 0.]), style)])
    assert rows() == 0                       # 信号消失 -> 点也删掉
    manager.update(frame, [('long_signal', np.array([0., 0., 0., 1.]), style)])
    assert rows() == 1
    manager.clear()
    assert manager.series == {}


class SignalDataset:
    """`_get_plot_datas` 第 4/8 项带列名和数值的信号数据集替身。"""

    def __init__(self, long_signal, short_signal=None, plot_id=0):
        n = len(long_signal)
        short = np.zeros(n) if short_signal is None else np.asarray(
            short_signal, dtype=float)
        self.plot_id = plot_id
        self._lines = ['cci', 'zero', 'long_signal', 'short_signal']
        self._values = np.column_stack([
            np.zeros(n), np.zeros(n),
            np.asarray(long_signal, dtype=float), short])
        self._plotinfo = FakeStyle(
            signallines=['long_signal', 'short_signal'],
            signalstyle={'long_signal': FakeStyle(show=True, key='low',
                                                  color='red'),
                         'short_signal': FakeStyle(show=True, key='high',
                                                   color='green')})

    def _get_plot_datas(self, key):            # noqa: ARG002
        data = [None] * 14
        data[4] = self._lines
        data[8] = self._values
        return tuple(data)


def test_extract_signals_reads_fresh_dataset():
    """实盘每次重算会换掉指标对象；信号要按 key 现取，不能停在旧值。"""
    strategy = FakeStrategy({'cci': SignalDataset([0., 0., 1., 0.])})
    before = rt.extract_minibt_signals(strategy, 0)
    assert float(np.asarray(before[0][1])[-1]) == 0.0
    # 模拟 tick：最后一根的信号出现（新对象，值和旧的不一样）
    strategy._btindicatordataset['cci'] = SignalDataset(
        [0., 0., 1., 1.])
    after = rt.extract_minibt_signals(strategy, 0)
    assert float(np.asarray(after[0][1])[-1]) == 1.0


def test_signal_manager_reuses_series():
    """更新不能每次重建序列（否则会闪烁 / 报 detach）。"""
    frame = make_frame()
    chart = make_chart(frame)
    style = FakeStyle(key='low', color='red', marker='triangle', size=12)
    manager = rt.SignalManager(chart)
    manager.update(frame, [('long_signal', np.array([0., 1., 0., 0.]), style)])
    series = manager.series['long_signal']
    manager.update(frame, [('long_signal', np.array([0., 1., 1., 0.]), style)])
    assert manager.series['long_signal'] is series


def test_strategy_preload_reads_kline_attribute():
    kline = FakeKline()
    kline._preload = 500
    strategy = FakeStrategy(klines={'k': kline})
    assert rt.strategy_preload(strategy, 'DCE.pp2609_60') == 500
    assert rt.strategy_preload(strategy, 'SHFE.ni2610_60') is None


def test_realtime_history_prepends_and_keeps_newest():
    """无限历史：向前补一批，最新一根不能丢（实时 update 走 chart.update）。"""
    index = pd.date_range('2024-01-01', periods=30, freq='min')
    full = pd.DataFrame({
        'time': index, 'open': np.arange(30.0), 'high': np.arange(30.0) + 1,
        'low': np.arange(30.0), 'close': np.arange(30.0) + 0.5,
        'volume': 1.0})
    chart = make_chart(full.tail(10).reset_index(drop=True))

    def loader(count, before=None):
        data = full
        if before is not None:
            data = data[data['time'] < pd.Timestamp(before)]
        return data.tail(int(count))

    added = []
    history = rt.RealtimeHistory(
        chart, loader, page=8, threshold=3,
        on_load=lambda h, n: added.append(n))
    history.stop()                       # 手动触发，避免 set() 引发的自动翻页
    assert history.load() == 8
    assert len(chart.candle_data) == 18
    assert pd.Timestamp(int(chart.candle_data['time'].max()), unit='s') == \
        full['time'].iloc[-1]
    # 实时又追加了一根新 K 线，再向前翻页不能把它丢掉
    new_bar = full.iloc[-1].copy()
    new_bar['time'] = full['time'].iloc[-1] + pd.Timedelta(minutes=1)
    chart.update(new_bar)
    assert history.load() == 8
    assert pd.Timestamp(int(chart.candle_data['time'].max()), unit='s') == \
        pd.Timestamp(new_bar['time'])
    assert added[:2] == [8, 8]


def test_refresh_market_updates_previous_and_all_new_bars(monkeypatch):
    """换根：上一根用最终值回填，之后每一根新 K 线都 K 线+指标一起补；
    即使一次 feed 跳了多根（指标算得慢）也不能漏根。"""
    index = pd.date_range('2024-01-01', periods=6, freq='min')
    frame_all = pd.DataFrame({
        'time': index, 'open': np.arange(6.0), 'high': np.arange(6.0) + 1,
        'low': np.arange(6.0), 'close': np.arange(6.0) + 0.5,
        'volume': 1.0})
    chart = make_chart(frame_all.iloc[:3].reset_index(drop=True))

    rc = object.__new__(rt.RealtimeChart)
    rc.chart = chart
    rc.indicators = rt.IndicatorManager(chart)
    rc.indicators.align = 'tail'
    rc.signal_manager = rt.SignalManager(chart)
    rc.spans = []
    rc._last_time = pd.Timestamp(frame_all['time'].iloc[2])
    rc.window = type('W', (), {'contract': 'X', 'strategy': 'S'})()
    rc._strategy_obj = lambda: type(
        'S', (), {'_btindicatordataset': {}, '_btklinedataset': {}})()

    values = np.arange(10.0, 16.0)          # 6 根：10..15
    spec = rt.IndicatorSpec(name='ma', overlap=True,
                            values=pd.Series(values[:3]),
                            get_values=lambda: values)
    series = chart.add_series('Line', name='ma')
    series.set(pd.DataFrame({'time': list(frame_all['time'].iloc[:3]),
                             'ma': values[:3]}))
    rc.indicators.series, rc.indicators.specs = [series], [spec]
    monkeypatch.setattr(rt, 'strategy_kline_frame',
                        lambda strategy, contract, tail=None: frame_all)
    chart._scripts.clear()
    rc._refresh_market()

    # K 线补齐到 6 根
    assert len(chart.candle_data) == 6
    # 上一根（index2，值 12）+ 3 根新根（13/14/15）都推送了
    updates = [s for s in chart._scripts if 'series.update' in s
               and '"value"' in s]
    pushed = [float(s.split('"value":')[1].split(',')[0].split('}')[0])
              for s in updates]
    assert pushed == [12.0, 13.0, 14.0, 15.0]


class _MarketApi:
    def __init__(self, changed):
        self.changed = changed
        self.calls = 0

    def is_changing(self, obj, key=None):
        self.calls += 1
        return self.changed


class _MarketStrategy:
    def __init__(self, api, klines):
        self._api = api
        self._btklinedataset = klines


def _market_kline(tq):
    return FakeStyle(_dataset=FakeStyle(tq_object=tq))


def test_market_changed_uses_tq_is_changing():
    frame = make_frame()
    strategy = _MarketStrategy(_MarketApi(True),
                               {'k': _market_kline(frame)})
    assert rt.RealtimeChart._market_changed(strategy) is True
    strategy2 = _MarketStrategy(_MarketApi(False),
                                {'k': _market_kline(frame)})
    assert rt.RealtimeChart._market_changed(strategy2) is False


class _FeedStrategy:
    """`feed()` 用的假策略：wait_update 恒返回 True，可调用（实盘入口）。"""

    _is_live_trading = True          # 走 item(step_only=not changed) 分支

    def __init__(self, api, klines):
        self._api = api
        self._btklinedataset = klines
        self.steps = []

    def wait_update(self, timeout=None):
        return True

    def __call__(self, step_only=False):
        self.steps.append(step_only)


def _feed_chart(api):
    strategy = _FeedStrategy(api, {'k': _market_kline(make_frame())})
    rc = object.__new__(rt.RealtimeChart)
    rc.strategies = [strategy]
    rc._disconnected = False
    rc._switching = False
    rc._lock = threading.RLock()
    rc._push_interval = 0.0                 # 默认：不限速
    rc._last_push = 0.0
    rc._last_time = None
    rc.window = FakeStyle(contract='X', strategy='S')
    rc._strategy_obj = lambda: strategy
    calls = []
    rc._refresh_market = lambda push_indicators=True: calls.append(
        ('kline', push_indicators))
    rc._sync_history_cache = lambda: calls.append(('cache', None))
    return rc, strategy, calls


def test_feed_pushes_kline_every_loop_even_if_market_unchanged():
    """行情没变：仍推 K 线（push_indicators=False），但不重算指标/信号。"""
    rc, strategy, calls = _feed_chart(_MarketApi(False))
    rc.feed(timeout=0)
    assert strategy.steps == [True], strategy.steps     # step_only=True
    assert calls == [('kline', False)], calls           # 只推 K 线


def test_feed_recomputes_indicators_when_market_changed():
    """行情变了：K 线 + 指标 + 信号一起推，并同步无限历史缓存。"""
    rc, strategy, calls = _feed_chart(_MarketApi(True))
    rc.feed(timeout=0)
    assert strategy.steps == [False], strategy.steps
    assert calls == [('kline', True), ('cache', None)], calls


def test_market_changed_falls_back_to_true():
    # 没有天勤 api / 没有 tq_object -> 保持旧行为（每次都算）
    frame = make_frame()
    assert rt.RealtimeChart._market_changed(
        _MarketStrategy(None, {'k': _market_kline(frame)})) is True
    assert rt.RealtimeChart._market_changed(
        _MarketStrategy(_MarketApi(False), {'k': _market_kline(None)})) is True


class _PushKline:
    symbol = 'X'
    cycle = 60

    def __init__(self, tq):
        self._dataset = FakeStyle(tq_object=tq)


class _CloseApi:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_realtime_disconnect_closes_api_and_is_idempotent():
    api = _CloseApi()
    rc = object.__new__(rt.RealtimeChart)
    rc.strategies = [FakeStyle(_api=api)]
    rc._disconnected = False
    rc._api_factory = None
    rc._period_ms = 100
    rc._loop_thread = None
    rc.chart = FakeStyle(is_alive=False)
    rc.window = FakeStyle(replace_setting=lambda *a, **k: None,
                          set_contract=lambda *a, **k: None)
    rc.disconnect()
    rc.disconnect()                       # 重复点击不应再次 close
    assert rc._disconnected is True and api.closed is True


def test_realtime_disconnect_reconnect_rebinds_api():
    class _Tq(_CloseApi):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def get_account(self):
            return ('acct', self.name)

        def get_kline_serial(self, symbol, cycle, length):
            return ('kline', self.name)

        def get_tick_serial(self, symbol):
            return ('tick', self.name)

    old, new = _Tq('old'), _Tq('new')
    dataset = FakeStyle(tq_object='old_kline', tq_tick='old_tick')
    kline = FakeStyle(symbol='X', cycle=60, _dataset=dataset, _preload=200)
    strategy = FakeStyle(_api=old, _btklinedataset={'k': kline})
    menu = []
    rc = object.__new__(rt.RealtimeChart)
    rc.strategies = [strategy]
    rc._disconnected = False
    rc._api_factory = lambda: new
    rc._period_ms = 100
    rc._loop_thread = None
    rc.chart = FakeStyle(is_alive=False)
    rc.window = FakeStyle(
        contract='X_60', strategy='S',
        replace_setting=lambda o, n, cb=None: menu.append((o, n)),
        set_contract=lambda *a, **k: None)
    rc.disconnect()
    assert old.closed is True and rc._disconnected is True
    assert menu[-1] == ('断开连接', '重新连接')
    rc.reconnect()
    assert strategy._api is new and rc._disconnected is False
    assert dataset.tq_object == ('kline', 'new')
    assert menu[-1] == ('重新连接', '断开连接')


def test_realtime_reset_returns_to_first_strategy_and_contract():
    class Window:
        strategies = ['A', 'B']
        strategy = 'B'
        contract = 'B_c2'

        def contracts_of(self, name):
            return {'A': ['A_c1'], 'B': ['B_c1']}[name]

        def set_strategy(self, name, contract=None):
            self.strategy, self.contract = name, contract

    rc = object.__new__(rt.RealtimeChart)
    rc.window = Window()
    rc.chart = FakeStyle()
    rc.reset()
    assert rc.window.strategy == 'A' and rc.window.contract == 'A_c1'


def test_push_throttle_and_new_bar_override():
    ns0 = 1704067200000000000
    ns1 = 1704067260000000000
    tq = pd.DataFrame({'datetime': [ns0, ns1]})
    strategy = FakeStyle(_btklinedataset={'k': _PushKline(tq)})
    chart = object.__new__(rt.RealtimeChart)
    chart.window = FakeStyle(contract='X_60')
    chart._strategy_obj = lambda: strategy
    chart._push_interval = 100.0
    chart._last_time = pd.Timestamp(ns1)          # 已是最新一根
    chart._last_push = time.monotonic()
    assert chart._should_push() is False          # 刚推过 -> 节流
    chart._last_time = pd.Timestamp(ns0)          # 落后一根
    chart._last_push = time.monotonic()
    assert chart._should_push() is True           # 有新根 -> 立即推
    chart._push_interval = 0.0
    assert chart._should_push() is True           # 关闭节流


def test_fast_time_to_datetime_matches_reference():
    pytest.importorskip('minibt')
    from minibt.indicators.core import _fast_time_to_datetime
    from minibt.utils import time_to_datetime
    values = pd.Series([1704067200000000000, 1704067260000000000],
                       dtype='int64')
    fast = list(_fast_time_to_datetime(values))
    slow = list(values.apply(time_to_datetime))
    assert fast == slow


def test_view_values_uses_time_indexed_cache():
    """实盘策略只算 preload 根时，历史部分从全量缓存按时间取。"""
    frame = make_frame(6)
    chart = make_chart(frame.iloc[:3])
    manager = rt.IndicatorManager(chart)
    manager.align = 'tail'
    times = rt.IndicatorManager._frame_seconds(frame)
    spec = rt.IndicatorSpec(name='ma', overlap=True,
                            values=pd.Series([10., 11, 12, 13, 14, 15]),
                            get_values=lambda: np.array([13., 14, 15]))
    spec.cached_series = pd.Series([10., 11, 12, 13, 14, 15], index=times)
    # 视图是最后 3 根 -> 缓存按时间取到 13/14/15
    view = frame.tail(3).reset_index(drop=True)
    assert list(manager.view_values(spec, view)) == [13.0, 14.0, 15.0]
    # 视图扩到 5 根 -> 取到 11..15（实时值只有最后 3 个，但缓存是全量）
    view5 = frame.tail(5).reset_index(drop=True)
    assert list(manager.view_values(spec, view5)) == [11.0, 12.0, 13.0,
                                                      14.0, 15.0]


def test_apply_histogram_colors_uses_candle_rule_colors():
    """K 线用 color_by 配色时，MACD 柱体也应跟着用同一组颜色（不再是默认红绿）。"""
    frame = make_frame()
    chart = make_chart(frame)
    series = chart.add_series('Histogram', name='macdh')
    series.set(pd.DataFrame({'time': list(frame['time']),
                             'macdh': [-1.0, 2.0, -3.0, 4.0]}))
    spec = rt.IndicatorSpec(name='macdh', overlap=False,
                            values=pd.Series([-1.0, 2.0, -3.0, 4.0]),
                            kind='Histogram')
    spec.source = 'macd'
    kline = FakeKline()
    kline.__dict__['_color_rules'] = [{
        'condition': np.array([True, False, True, False]),
        'color': 'lime', 'else_color': 'tomato', 'options': {}}]
    strategy = FakeStrategy({'macd': FakeDataset()}, {'k': kline})
    manager = FakeManager([series], [spec])
    rt.apply_histogram_colors(manager, strategy, 'DCE.pp2609_60', 4)
    out = scripts(chart)
    assert 'lime' in out and 'tomato' in out
    assert '#26a69a' not in out                   # 默认色不应再出现
    assert spec.up_color == 'lime' and spec.down_color == 'tomato'

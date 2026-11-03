"""柱状指标（`LineDash.vbar`）的涨跌色没生效 —— minibt 的调色板 alpha 是 0~255 ✓

用户 2026-10-31：给 `pandas_ta.macd` 加了

```python
@tobtind(lines=['macdx', 'macdh', 'macds'], lib='pta',
         linestyle=dict(macdh=LineStyle(line_dash=LineDash.vbar, vbar_base=0.,
                                        vbar_up_color=Colors.bull_color,
                                        vbar_down_color=Colors.bear_color)))
```

跑 `tutorials/basic/live_chart.py` 时 MACD 柱体**没有**按这两个颜色走。

根因：`Colors.bull_color = 'rgba(39, 157, 130, 100)'` —— alpha 是 **0~255**
（100 ≈ 0.39 半透明）；而 Lightweight Charts 的颜色解析把 `rgba()` 第 4 个参数
当 **0~1** 用（`parseFloat` 直接用，100 被 CSS 夹成 1）→ 半透明的涨跌色被夹成
**实色**，看起来和主题默认的 `#26a69a` / `#ef5350` 几乎一样 → “颜色没生效”✗。

修法：`pylightcharts.colors.normalize_color()` 把 `a > 1` 的 `rgba()` 按 0~255
换算成 0~1；`minibt/strategy/realtime.py::_as_color()`（柱体 / 蜡烛 / 指标线）
和 desk 的 `indicator_catalog` / `strategy_overlay` 都走它 ✓。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_normalize_color_converts_0_255_alpha():
    from pylightcharts.colors import normalize_color

    assert normalize_color('rgba(39, 157, 130, 100)') == \
        'rgba(39, 157, 130, 0.392)'
    assert normalize_color('rgba(200,97,100,100)') == \
        'rgba(200, 97, 100, 0.392)'
    # 已经是 0~1 / 十六进制 / rgb() / 其它写法 → 原样返回 ✓
    for value in ('rgba(0,0,0,0.5)', 'rgba(1, 2, 3, 1)', '#26a69a',
                  'rgb(1,2,3)', 'red', None):
        assert normalize_color(value) == value


def test_as_color_normalizes_minibt_palette():
    from minibt import Colors
    from minibt.strategy.realtime import _as_color

    assert _as_color(Colors.bull_color) == 'rgba(39, 157, 130, 0.392)'
    assert _as_color(Colors.bear_color) == 'rgba(200, 97, 100, 0.392)'
    assert _as_color('#26a69a') == '#26a69a'
    assert _as_color(None, 'x') == 'x'


def test_histogram_colors_use_normalized_palette():
    """`apply_histogram_colors` 下发的颜色必须是 0~1 alpha ✓"""
    pd = pytest.importorskip('pandas')
    import numpy as np
    from minibt import Colors
    from minibt.strategy import realtime as rt

    class _Series:
        def __init__(self):
            self.data = pd.DataFrame({'time': [1, 2, 3, 4],
                                      'value': [1.0, -1.0, 2.0, -2.0]})

        def color_by(self, condition, color, else_color=None, **kw):
            from pylightcharts.colors import color_by as _cb
            self.data = _cb(self.data, condition, color, else_color, **kw)

    class _Manager:
        def __init__(self, series, spec):
            self.series, self.specs = [series], [spec]

    class _Strategy:
        config = None
        _btklinedataset = {}

    series = _Series()
    spec = rt.IndicatorSpec(name='macdh', overlap=False, kind='Histogram',
                            values=series.data['value'], vbar_base=0.0,
                            vbar_up_color=Colors.bull_color,
                            vbar_down_color=Colors.bear_color)
    rt.apply_histogram_colors(_Manager(series, spec), _Strategy(), 'X',
                              len(series.data))
    colors = list(series.data['color'])
    assert colors == ['rgba(39, 157, 130, 0.392)',
                      'rgba(200, 97, 100, 0.392)',
                      'rgba(39, 157, 130, 0.392)',
                      'rgba(200, 97, 100, 0.392)']
    assert (spec.up_color, spec.down_color) == (
        'rgba(39, 157, 130, 0.392)', 'rgba(200, 97, 100, 0.392)')


def test_desk_payloads_normalize_colors():
    """desk 的柱体 / 蜡烛颜色同样规范化（浅色主题下才不会“没变化”）✓"""
    from minibt.desk import indicator_catalog as catalog

    assert catalog._norm_color('rgba(39, 157, 130, 100)') == \
        'rgba(39, 157, 130, 0.392)'
    assert catalog._norm_color(None) is None
    assert catalog._norm_color('#ef5350') == '#ef5350'
    source = (ROOT / 'minibt' / 'desk' / 'indicator_catalog.py').read_text(
        encoding='utf-8')
    assert "_norm_color(style.get('vbar_up_color'))" in source
    assert "'upColor': _norm_color(bull)" in source
    overlay = (ROOT / 'minibt' / 'desk' / 'strategy_overlay.py').read_text(
        encoding='utf-8')
    assert '_nc = lambda value: value' in overlay        # 兜底（旧 pylightcharts）


def test_realtime_wires_normalize_color():
    """源码护栏：`_as_color` / 蜡烛配色都走 normalize_color ✓"""
    source = (ROOT / 'minibt' / 'strategy' / 'realtime.py').read_text(
        encoding='utf-8')
    assert 'from pylightcharts.colors import normalize_color' in source
    assert 'return normalize_color(str(getattr(value' in source
    assert "up, down = _as_color(style.get('up')), _as_color(style.get('down'))" in source


def test_hist_colors_use_plotted_values_not_second_fetch():
    """上色用**图上已经 set 的那份值**，不再二次取（长度不符会静默失败）✓

    用户实测：策略自带的 MACD 柱体是橙色的（指标线色），工具栏加的同一个
    指标却正常 —— 因为 `apply_histogram_colors()` 二次 `view_values()` 在实盘 /
    多策略场景里拿到的是**另一份**（长度不同）→ `series.color_by()` 抛异常被
    吞 → 整根柱子保持序列色 ✗。
    """
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    from minibt.strategy import realtime as rt

    class _Series:
        def __init__(self):
            self.data = pd.DataFrame({'time': [1, 2, 3, 4],
                                      'value': [1.0, -1.0, 2.0, -2.0]})
            self.calls = []

        def color_by(self, condition, color, else_color=None, **kw):
            from pylightcharts.colors import color_by as _cb
            self.calls.append((len(condition), color, else_color))
            self.data = _cb(self.data, condition, color, else_color, **kw)

    class _Manager:
        """二次取值的接口故意返回**长度不对**的值（模拟实盘里的错位）✓"""

        def __init__(self, series, spec):
            self.series, self.specs = [series], [spec]

        def view_values(self, spec, frame):
            return np.array([1.0, -1.0])            # 长度 2 ≠ 4 ✗

        def spec_values(self, spec, n=None):
            return np.array([1.0, -1.0])

    class _Strategy:
        config = None
        _btklinedataset = {}

    series = _Series()
    spec = rt.IndicatorSpec(name='macdh', overlap=False, kind='Histogram',
                            values=series.data['value'], vbar_base=0.0,
                            vbar_up_color='#ef5350',
                            vbar_down_color='#26a69a')
    rt.apply_histogram_colors(_Manager(series, spec), _Strategy(), 'X',
                              len(series.data))
    assert series.calls and series.calls[0][0] == 4        # 用的是图上的 4 个点 ✓
    assert list(series.data['color']) == ['#ef5350', '#26a69a',
                                          '#ef5350', '#26a69a']


def test_hist_color_failure_warns_once(capsys):
    """真配不上颜色时打印一次提示（不再静默）✓"""
    pd = pytest.importorskip('pandas')
    from minibt.strategy import realtime as rt

    class _Series:
        data = pd.DataFrame({'time': [1, 2], 'value': [1.0, -1.0]})

        def color_by(self, *args, **kwargs):
            raise ValueError('length mismatch')

    class _Manager:
        def __init__(self, series, spec):
            self.series, self.specs = [series], [spec]

    class _Strategy:
        config = None
        _btklinedataset = {}

    rt._HIST_COLOR_WARNED.clear()
    spec = rt.IndicatorSpec(name='warned_macdh', overlap=False,
                            kind='Histogram', vbar_base=0.0,
                            vbar_up_color='#ef5350',
                            vbar_down_color='#26a69a')
    manager = _Manager(_Series(), spec)
    rt.apply_histogram_colors(manager, _Strategy(), 'X', 2)
    rt.apply_histogram_colors(manager, _Strategy(), 'X', 2)
    out = capsys.readouterr().out
    assert out.count('未配色') == 1
    assert 'warned_macdh' in out

"""desk 柱状指标的涨 / 跌色 + 画线导航条滚动条（2026-10-31 用户反馈）✓

1. 看盘窗口里 MACD 的 `macdh` 柱体是**指标线的颜色**（橙色），既不是
   `vbar_up_color/vbar_down_color`，也不是「跟 K 线涨跌色一致」；
   根因：两个图表页里**第一个** `IndicatorLayer`（格 1 用的）主题回调只给了
   `{background, text}`，没有 `up` / `down` → 颜色一路退到 `item.color` ✗。
2. 画线导航条（`.desk-draw-rail`）高度不够时出现滚动条，用户要求**隐藏**，
   但滚轮仍要能滚到所有工具 ✓。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_first_indicator_layer_gets_up_down():
    """两个页面里**每个** `IndicatorLayer` 都要带 `up` / `down` ✓"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(f'jslib/src/desk/{name}')
        # 两处构造（格 1 那个 + 每格的那个）都必须给 pal.up / pal.down
        assert page.count('up: pal.up, down: pal.down') >= 2, name
        # 之前那种「只有 background / text」的写法不能再出现 ✓
        assert "text: this.options.theme === 'light' ? '#1f2329' : '#d8d9db',"\
            not in page, name
        assert 'const pal = chartPalette(' in page, name


def test_hist_theme_colors_covered_by_vitest():
    """vitest 覆盖「无 up/down → 柱子变成指标线色」的回归 ✓"""
    test = _read('jslib/test/hist-indicator-colors.test.ts')
    assert 'uses the theme up/down colours when the item has none' in test
    assert "own upColor / downColor" in test
    assert 'keeps the transparent colour on gap points' in test


def test_draw_rail_hides_scrollbar_but_keeps_wheel():
    """滚动条隐藏（Chromium / Firefox），`overflow-y: auto` 保留滚轮 ✓"""
    css = _read('jslib/src/desk/desk.css')
    rail = css.split('.desk-draw-rail {', 1)[1].split('}', 1)[0]
    assert 'overflow-y: auto' in rail            # 还能滚 ✓
    assert 'scrollbar-width: none' in rail       # Firefox ✓
    assert '-ms-overflow-style: none' in rail    # 旧 Edge ✓
    assert '.desk-draw-rail::-webkit-scrollbar {' in css
    bar = css.split('.desk-draw-rail::-webkit-scrollbar {', 1)[1].split('}', 1)[0]
    assert 'display: none' in bar
    assert 'width: 0' in bar
    # 构建产物也要带上 ✓
    built = _read('pylightcharts/js/desk.css')
    assert '.desk-draw-rail::-webkit-scrollbar' in built


# ---------------------------------------------------------------- 默认柱体色
def _macd_frame(rows: int = 240):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 0.4, rows))
    return pd.DataFrame({
        'datetime': pd.date_range('2024-01-01', periods=rows, freq='min'),
        'open': close - rng.normal(0, 0.2, rows),
        'high': close + abs(rng.normal(0, 0.3, rows)),
        'low': close - abs(rng.normal(0, 0.3, rows)),
        'close': close,
        'volume': rng.integers(100, 900, rows).astype(float),
    })


def test_palette_default_colors_mean_unset():
    """`Colors.bull_color` / `bear_color`（调色板**半透明**默认值）＝"没设置" ✓

    用户 2026-11-03：desk 里 MACD 柱体又暗又偏，跟主图成交量一个颜色 ✗。
    根因：库里（`pandas_ta.py` / `tradingview.py`）默认就拿
    `Colors.bull_color='rgba(39,157,130,100)'`（alpha 100/255 ≈ 0.39）当柱体色，
    于是绕过了「没配 → 用主题 K 线涨跌色」的回退 ✗。
    """
    from minibt.desk.indicator_catalog import _vbar_color

    for palette in ('rgba(39, 157, 130, 100)', 'rgba(200, 97, 100, 100)',
                    '#279d82', '#c86164', 'rgba(39, 157, 130, 0.392)'):
        assert _vbar_color(palette) is None, palette
    # 用户自己设的颜色照旧生效 ✓
    assert _vbar_color('#ff0000') == '#ff0000'
    assert _vbar_color('red') == 'red'
    assert _vbar_color(None) is None


def test_default_vbar_follows_kline_up_down():
    """默认柱体：`vbar_base` 以上 → K 线上涨色、以下 → 下跌色 ✓

    后端不再下发 `upColor/downColor`（留空）→ 前端 `indicator.ts` 用
    `theme().up` / `theme().down`，也就是主图蜡烛的涨跌色；`base` 默认 0，
    用户设了 `vbar_base` 就按用户的值。
    """
    import minibt.desk.indicator_catalog as ic

    out = ic.compute(_macd_frame(), ['pta_macd'])
    items = out if isinstance(out, list) else (out.get('items') or [])
    hist = next(item for item in items if item['kind'] == 'hist')
    assert hist['base'] == 0.0                       # 默认分界 0 ✓
    assert not hist.get('upColor')                   # 留空 → 主题涨色 ✓
    assert not hist.get('downColor')                 # 留空 → 主题跌色 ✓
    # 图例小方块仍用指标线色（不跟着变 ✓）
    assert hist.get('color')


def test_strategy_vbar_defaults_follow_theme():
    """策略链路的柱体也一样：调色板默认色 → 留空（不退回指标线色 ✗）"""
    import pandas as pd

    from minibt.desk import strategy_overlay as so
    from minibt.strategy.realtime import IndicatorSpec

    frame = pd.DataFrame({
        'datetime': pd.date_range('2024-01-01', periods=3, freq='min'),
        'close': [1.0, 2.0, 3.0],
    })

    class Runner:
        def __init__(self, specs):
            self._specs = specs

        def specs(self, plot_id=0):
            return self._specs

        def frame(self, plot_id=0):
            return frame

        def signals(self, plot_id=0):
            return []

    spec = IndicatorSpec(name='macdh', overlap=False,
                         values=pd.Series([1.0, -1.0, 2.0]),
                         kind='Histogram', vbar_base=0.0,
                         vbar_up_color='rgba(39, 157, 130, 100)',
                         vbar_down_color='rgba(200, 97, 100, 100)',
                         source='macd')
    item = next(i for i in so._items_for_plot(Runner([spec]), 0, frame, frame)
                if i.get('kind') == 'hist')
    assert item['base'] == 0.0
    assert item['upColor'] is None and item['downColor'] is None

    # 用户自定义颜色 / 自定义 base → 原样下发 ✓
    spec.vbar_up_color, spec.vbar_down_color = '#ff0000', '#00ff00'
    spec.vbar_base = 50.0
    item = next(i for i in so._items_for_plot(Runner([spec]), 0, frame, frame)
                if i.get('kind') == 'hist')
    assert (item['upColor'], item['downColor']) == ('#ff0000', '#00ff00')
    assert item['base'] == 50.0

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

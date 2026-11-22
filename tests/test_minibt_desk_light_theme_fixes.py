"""浅色主题 + 回放视窗的三个修复（2026-10-30 用户实测）✓

1. 回测页（合约图表 / 回测结果）**主图与副图之间**的分隔线在浅色下太深；
2. 回测中 / 参数优化中，图表区默认黑底（浅色主题下也是黑的）；
3. 回测完成后在回测页回放：可视区 K 线数量越来越少、K 线一直往左挪。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


# ---------------------------------------------------------------- ① 分隔线
def test_pane_separator_lighter_in_light_theme():
    from minibt.desk import miniqt_backtest_chart as chart_mod
    light = chart_mod._inject_separator_css(
        '<html><head></head><body></body></html>', False)
    dark = chart_mod._inject_separator_css(
        '<html><head></head><body></body></html>', True)
    # 浅色：很淡的灰（以前 rgba(100,116,139,.32) 偏深 ✗）
    assert 'rgba(224, 227, 235, .95)' in light
    assert 'rgba(100, 116, 139, .32)' not in light
    assert 'height: 2px !important' in light
    assert 'rgba(148, 163, 184, .45)' in dark          # 深色保持原样 ✓
    # LWC 侧（pane_separator）与 CSS 侧颜色一致 ✓
    js = chart_mod.DESK_DRIVER_JS
    source = pathlib.Path(chart_mod.__file__).read_text(encoding='utf-8')
    assert "else 'rgba(224, 227, 235, .95)')" in source
    assert 'DESK_DRIVER_JS' in source or js


def test_pylightcharts_light_separator_is_pale():
    themes = _read('pylightcharts/themes.py')
    light = themes.split("LIGHT: Dict[str, str] = {", 1)[1].split('}', 1)[0]
    assert "'pane_separator': '#E0E3EB'" in light      # 原来 #B6C4D6 偏深 ✗
    # 只有注释里还能看到旧值，代码里必须已经换掉 ✓
    assert light.count('#B6C4D6') <= 1
    desk_theme = _read('jslib/src/desk/theme.ts')
    assert "'rgba(224,227,235,0.95)'" in desk_theme     # 看盘窗口 / 本地图表 ✓


# ------------------------------------------------------- ② 回测中的占位底色
def test_backtest_placeholder_follows_theme():
    """回测中 / 优化中还没图表 → iframe 占位页底色跟主题（不能写死黑 ✗）"""
    page = _read('jslib/src/desk/strategy-lab-page.ts')
    assert "const light = this.options.theme === 'light';" in page
    assert "background:${light ? '#ffffff' : '#111111'}" in page
    assert "color:${light ? '#5c6672' : '#9aa4b2'}" in page
    assert 'background:#111;color:#9aa4b2' not in page
    # 浏览器壳（/strategy_chart 出错 / 还没算完）同理 ✓
    web = _read('minibt/desk/web.py')
    assert 'light = str(theme or \'\').lower() == \'light\'' in web
    assert '#ffffff' in web and '#111111' in web


def test_backtest_iframe_background_follows_theme():
    """iframe 自身的 CSS 底色：以前写死 #000 → 还没装图表时浅色下一片黑 ✗"""
    css = _read('jslib/src/desk/desk.css')
    rules = [line for line in css.splitlines()
             if line.startswith('.desk-strategy-iframe')]
    assert rules, 'desk.css 里找不到 .desk-strategy-iframe'
    assert all('var(--desk-bg)' in line for line in rules), rules
    assert all('#000' not in line for line in rules), rules


def test_placeholder_is_set_before_chart_ready():
    """回测中 / 参数优化中：两个 iframe 一建出来就有主题色占位页 ✓"""
    page = _read('jslib/src/desk/strategy-lab-page.ts')
    # 构造函数里两个 iframe 都先喂占位页（否则只剩 CSS 黑底）
    assert 'this._setPlaceholder(this.chartFrame);' in page
    assert 'this._setPlaceholder(this.resultFrame);' in page
    assert 'private _placeholderHtml(): string {' in page
    # 还没 ready 的 _loadFrame 也要保持占位页（不能直接 return 留空 ✗）
    assert ('if (!this.initialReady) {\n'
            '            // 回测 / 优化还没算完 → 保持主题色占位页'
            in page.replace('\r\n', '\n'))
    # 切换主题后重刷占位页 ✓
    assert 'this._refreshPlaceholders();' in page


def test_headless_page_background_follows_theme():
    """pylightcharts 导出的 HTML：<body> 底色跟主题（浅色→#ffffff）✓"""
    import numpy as np
    import pandas as pd

    from pylightcharts.headless import HeadlessChart

    chart = HeadlessChart(width=480, height=320)
    chart.set(pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=5, freq='D'),
        'open': np.arange(5, dtype=float) + 100,
        'high': np.arange(5, dtype=float) + 101,
        'low': np.arange(5, dtype=float) + 99,
        'close': np.arange(5, dtype=float) + 100.5,
        'volume': np.arange(5, dtype=float),
    }))
    dark = chart.to_html()
    assert 'background: #000;' in dark          # 默认深色：保持原样 ✓
    chart.theme('light')
    light = chart.to_html()
    assert 'background: #ffffff;' in light      # 浅色：不能还是黑底 ✗


# ------------------------------------------------------------ ③ 回放视窗
def test_replay_keeps_width_and_right_gap():
    """回放新增 K 线：视窗宽度不变、最新 K 线到右边距离不变 ✓

    以前固定再平移 delta：LWC 自己已经跟着滚过一次 → 每拍多滚一根 →
    K 线越来越往左跑、可视根数越来越少（用户实测 ✗）
    """
    from minibt.desk import miniqt_backtest_chart as chart_mod
    js = chart_mod.DESK_DRIVER_JS
    assert 'function applyBars(h, count) {\n    var before = currentRange(h);' in js
    assert 'function shiftForBars(h, before, prevBars, nextBars)' in js
    assert 'var moved = before ? (after.from - before.from) : delta;' in js
    assert 'var remain = delta - moved;' in js
    # 只补差值，宽度按**setData 之前**的视窗算（可视根数不变 ✓）
    assert 'var width = anchor.to - anchor.from;' in js
    assert 'from: after.from + remain, to: after.from + remain + width' in js
    # 最新一根的逻辑下标含左侧空白 ✓
    assert 'var newest = state.padLen + prevBars - 1;' in js
    # 重复 replayStart（两个图表对齐）时不重新量宽度 → 不会越量越窄 ✓
    assert 'if (state.widthSet) return state.winWidth;' in js
    assert 'state.widthSet = true;' in js


def test_driver_helper_covers_auto_follow():
    """node 假 LWC 要覆盖「LWC 自己跟着滚」的情况 ✓"""
    helper = _read('tests/helpers/strategy_driver_test.js')
    assert 'options.follow' in helper
    assert "check('no double shift when LWC follows'" in helper
    assert "check('width constant when LWC follows'" in helper

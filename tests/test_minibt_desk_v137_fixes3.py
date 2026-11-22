"""用户 2026-11-08 四条反馈（v1.3.7-65）。

1. 图表右键 →「资讯 / 财务…」打开标的资讯页，**关掉后再打开打不开**；
2. 设置 → 资讯数据源里「想换源 / 加 Tushare（P1）」这句要删；
3. 设置 → 个性化 → PI 操控 desk：**悬浮球背景色**（自选 + 持久化 + 恢复默认），
   小球文字改「π」并放大；
4. **K 线事件圆点**看不到。
"""
from __future__ import annotations

import pathlib

from minibt.desk import user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


# ------------------------------------------------------------ ① 关掉再打开
def test_close_tab_clears_cached_pages():
    app = _read('app.ts')
    block = app[app.index('    closeTab(id: string): void {'):]
    block = block[:block.index('    /**')]
    # 关页时把缓存的页面引用清掉，否则再打开什么都不出现 ✗
    assert 'this.infoPage = null;' in block
    assert 'this.symbolInfoPage = null;' in block
    # 打开时再防御一次（引用还在但 pages 里没有了 ✓）
    open_block = app[app.index('openSymbolInfo(symbols: string[]'):]
    open_block = open_block[:open_block.index('    /**')]
    assert '!this.pages.has(SYMBOL_INFO_TAB_ID)' in open_block
    assert 'this.symbolInfoPage = null;' in open_block


# ------------------------------------------------------------ ② 去掉 Tushare 提示
def test_settings_note_has_no_tushare_hint():
    settings = _read('settings-page.ts')
    assert 'Tushare' not in settings
    assert '下一步开启（P1）' not in settings


# ------------------------------------------------------------ ③ 悬浮球颜色 / π
def test_float_ball_font_follows_theme_accent():
    """用户 2026-11-08：π 的字色跟主题色（不要自选底色时的深色覆盖）"""
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-pi-float-icon[data-custom="1"] { color:' not in css
    icon = css.split('.desk-pi-float-icon {', 1)[1].split('}', 1)[0]
    assert 'color: var(--desk-accent)' in icon


def test_all_events_switch_and_cleanup_button():
    prefs = (ROOT / 'minibt' / 'desk' / 'user_prefs.py').read_text(
        encoding='utf-8')
    assert "'chart_events_all'" in prefs
    settings = _read('settings-page.ts')
    assert 'chart_events_all' in settings
    assert "'清理重复会话'" in settings
    assert "'pi_cleanup'" in settings
    app = _read('app.ts')
    assert "case 'pi_cleanup'" in app


def test_float_ball_color_setting_and_pi_symbol():
    # 后端设置白名单
    assert 'pi_float_color' in user_prefs.SETTING_KEYS
    prefs = (ROOT / 'minibt' / 'desk' / 'user_prefs.py').read_text(
        encoding='utf-8')
    assert "'pi_float_color'" in prefs
    # 前端：设置项 + 颜色选择 + 恢复默认
    settings = _read('settings-page.ts')
    assert 'pi_float_color?: string;' in settings
    assert "picker.type = 'color'" in settings
    assert "onSetting('pi_float_color', picker.value)" in settings
    assert "onSetting('pi_float_color', '')" in settings       # 恢复默认 ✓
    # PiFloat：π 字 + setBallColor
    float_page = _read('pi-float.ts')
    assert "this.icon.textContent = 'π';" in float_page
    assert 'setBallColor(color: string): void {' in float_page
    assert "this.icon.dataset.custom = '1';" in float_page
    assert "delete this.icon.dataset.custom;" in float_page
    # 宿主：创建时带上设置里的颜色，改变时立刻生效，补丁回来也同步
    app = _read('app.ts')
    assert 'ballColor: String(this.settingsValues.pi_float_color || \'\'),' \
        in app
    assert "if (key === 'pi_float_color')" in app
    assert 'this.piFloat?.setBallColor(' in app
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    icon = css.split('.desk-pi-float-icon {', 1)[1].split('}', 1)[0]
    assert 'font-size: 22px' in icon            # π 要够大 ✓
    # 字色跟随主题色（不再为自选底色改深色 ✓）
    assert 'color: var(--desk-accent)' in icon


# ------------------------------------------------------------ ④ K 线事件圆点
def test_calendar_dots_are_top_dom_badges():
    """圆点：贴可视区顶部 + 无文字（tooltip）+ 只画标的专属事件 ✓"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(name)
        assert 'desk-cal-badge' in page, name
        # v1.3.7-68：旧 tooltip 已禁用（改用悬停卡片 ✓）
        assert "badge.removeAttribute('title')" in page, name
        assert 'private _bindCalPopover(' in page, name
        assert 'paneRect.top - hostRect.top + 4' in page, name
        assert 'subscribeVisibleLogicalRangeChange' in page, name
        # 本地图表单格时 `cellBars[0]` 可能是空数组 → 回退 `this.bars`
        assert 'this.calBadges' in page, name
    app = _read('app.ts')
    assert 'setSymbolEvents?.(' in app
    assert '_ensureCalendarForPage' in app

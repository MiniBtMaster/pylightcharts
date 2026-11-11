"""v1.3.7-99：技术分析悬浮标签固定在图表右上角 + 开关（ta_badge）。"""
from __future__ import annotations

import pathlib

import pytest

from minibt.desk import user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
CHART = (JSLIB / 'chart-page.ts').read_text(encoding='utf-8')
LOCAL = (JSLIB / 'local-chart-page.ts').read_text(encoding='utf-8')
SYMBOL = (JSLIB / 'symbol-info.ts').read_text(encoding='utf-8')
CSS = (JSLIB / 'desk.css').read_text(encoding='utf-8')


def test_badge_pinned_to_chart_corner():
    """标签挂在图表格子里、靠 CSS 的 right/top 固定（不再按最后一根 K 线）✓"""
    assert 'host.appendChild(badge)' in CHART
    assert 'this.cellElements[0] || this.element' in CHART
    css = CSS[CSS.index('.desk-ta-badge {'):CSS.index('.desk-ta-badge {') + 400]
    assert 'right: 12px' in css and 'top: 10px' in css
    # 旧实现（按 timeToCoordinate 贴最后一根 K 线 + top:28px）不能还在 ✓
    assert "badge.style.top = '28px'" not in CHART
    assert 'x - 60' not in CHART


def test_badge_respects_setting():
    assert '_taBadgeOff' in CHART
    assert "values.ta_badge === false" in CHART
    assert 'if (this._taBadgeOff()) return;' in CHART


def test_setting_whitelisted(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    values = user_prefs.set_setting('ta_badge', False)
    assert values.get('ta_badge') is False
    assert (user_prefs.settings() or {}).get('ta_badge') is False
    user_prefs.set_setting('ta_badge', True)
    assert (user_prefs.settings() or {}).get('ta_badge') is True


def test_symbol_dialog_has_badge_toggle():
    assert "dataset.taBadge = '1'" in SYMBOL
    assert '在图表右上角显示技术分析标签' in SYMBOL
    assert "key: 'ta_badge'" in SYMBOL
    assert "onCommand('set_setting'" in SYMBOL
    assert 'badgeRow' in SYMBOL


def test_local_chart_also_pins_badge():
    assert 'setTaSignal(' in LOCAL
    # 本地图表沿用同一套 CSS（right/top 固定）✓
    assert 'desk-ta-badge' in LOCAL


# ------------------------------------------------ v1.3.7-100（悬停卡片）
def test_badge_uses_card_not_native_title():
    for text in (CHART, LOCAL):
        assert 'removeAttribute(\'title\')' in text
        # TA 徽标不再设原生 title（挂单线等其它徽标不受影响 ✓）
        assert 'badge.title = rows' not in text
        assert '_bindTaPopover' in text
        assert 'desk-cal-pop desk-ta-pop' in text


def test_card_content_and_clamp():
    # 卡片头部：项数 / 多空中立 / 评分
    for text in (CHART, LOCAL):
        assert '技术分析 · ${rows.length} 项' in text
        assert '评分 ${score.toFixed(2)}' in text
        assert "pop-row'" in text and 'buy' in text and 'sell' in text
        # 右边界夹到**图表格子**里（右边有账户面板也不会遮）✓
        assert 'cellRect' in text
        assert 'maxLeft' in text


def test_ta_pop_style():
    css = CSS[CSS.index('.desk-ta-pop'):CSS.index('.desk-ta-pop') + 400]
    assert '.desk-ta-pop' in css
    assert 'color: #ef5350' in css          # 多 = 红
    assert 'color: #26a69a' in css          # 空 = 绿


def test_local_page_pinned_and_gated():
    """本地图表页也修好了（固定右上角 + 开关 + 卡片）✓"""
    assert 'this.cellElements[0] || this.element' in LOCAL
    assert '_taBadgeOff' in LOCAL
    assert "badge.style.top = '28px'" not in LOCAL

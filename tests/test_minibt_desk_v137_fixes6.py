"""v1.3.7-72：资讯右键菜单 / 双击 / 标的识别（找不到标的要提示）。

用户 2026-11-08：
* 点资讯只弹「已跳转」但图表没打开 —— 因为没带标的、且只对当前页 focusTime；
* 交互改成：左键不动作、右键菜单（打开原文 / 打开图表）、双击开原文；
* 找不到标的（综合 / 宏观资讯）要明确提示，不能静默。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


def test_news_menu_and_no_left_click():
    page = _read('info-page.ts')
    # 左键不动作（没有 click 里直接跳 / 开原文）
    block = page.split("node.addEventListener('dblclick'", 1)[1].split(
        '});', 2)[0]
    assert "onCommand('news_focus'" not in block
    # 右键菜单四项
    menu = page.split('private _showNewsMenu(', 1)[1].split(
        'private _symbolOf(', 1)[0]
    for label in ("'打开原文'", "'复制标题'", "'让 AI 分析这条'"):
        assert label in menu, label
    assert '打开图表' in menu
    # 找不到标的 → 明确提示
    assert '没法打开图表' in menu
    # 双击开原文
    assert "onCommand('open_url'" in page


def test_symbol_resolution_rules():
    page = _read('info-page.ts')
    block = page.split('private _symbolOf(', 1)[1].split(
        'private _relatedRows(', 1)[0]
    assert "const own = String((item as { symbol?: string }).symbol || '');"         in block
    assert 'text.includes(row.name)' in block        # 名称 → 代码 ✓
    assert '([A-Z]{2,6}' in page                     # 期货代码 ✓
    assert '6\d{5}|0\d{5}|3\d{5}' in page       # A 股代码 ✓


def test_news_focus_opens_page_then_jumps():
    app = _read('app.ts')
    block = app.split("cmd === 'news_focus'", 1)[1].split(
        "if (cmd === 'open_symbol_info')", 1)[0]
    assert 'if (!symbol)' in block
    assert '没有对应标的' in block
    assert 'this.openChart(symbol)' in block
    assert 'page.focusTime(seconds, label);' in block
    # 等 K 线到了再跳（最多 ~1.5 秒）
    assert 'jump(tries - 1)' in block


def test_news_panel_supports_context_menu():
    panel = (JSLIB / '..' / 'panels' / 'news.ts').read_text(encoding='utf-8')
    assert 'onItemContextMenu?: ' in panel
    assert 'onItemDoubleClick?: ' in panel
    assert "node.addEventListener('contextmenu'" in panel
    assert "node.addEventListener('dblclick'" in panel

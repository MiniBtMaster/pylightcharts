"""v1.3.7-103：PI 技能对话框 —— 搜索按钮不竖排 + 几个小体验修复。"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
SKILLS = (JSLIB / 'pi-skills.ts').read_text(encoding='utf-8')
CSS = (JSLIB / 'desk.css').read_text(encoding='utf-8')


def test_button_text_never_wraps():
    """搜索按钮文字要**从左到右**一行（以前被挤成「搜\n索」✗）"""
    block = CSS[CSS.index('.desk-pi-btn {'):CSS.index('.desk-pi-btn {') + 420]
    assert 'white-space: nowrap' in block
    assert 'flex: 0 0 auto' in block
    assert 'min-width: 56px' in block


def test_search_row_input_grows_button_keeps_width():
    assert '.desk-pi-search-row .desk-pi-input-small { flex: 1 1 auto;' in CSS
    assert '.desk-pi-search-row .desk-pi-btn { flex: 0 0 auto; }' in CSS


def test_chip_never_wraps():
    assert '.desk-pi-chip { white-space: nowrap; flex: 0 0 auto; }' in CSS


def test_empty_query_gives_feedback():
    """空关键词以前**什么都不发生**（像点坏了）→ 聚焦 + 提示 ✓"""
    assert '先输入关键词再搜索' in SKILLS
    assert 'this.searchBox.focus();' in SKILLS
    assert "onToast?.('info'" in SKILLS


def test_searching_state_and_timeout():
    assert 'this.searchButton = searchButton;' in SKILLS
    assert "this.searchButton.textContent = '搜索中…';" in SKILLS
    assert 'this.searchButton.disabled = true;' in SKILLS
    assert 'resetSearching' in SKILLS
    # 12 秒兜底（后端没回也不会永久变灰 ✓）
    assert 'this.resetSearching(), 12000' in SKILLS
    # 拿到结果就复原
    assert 'setSearch(patch: Record<string, unknown>): void {\n        this.resetSearching();' in SKILLS


def test_empty_installed_hint_is_actionable():
    assert '还没有安装技能' in SKILLS
    assert '未找到技能' not in SKILLS

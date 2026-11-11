"""v1.3.7-106：PI 对话右侧圆点导航 —— 只留自定义提示（原生 title 禁用）。"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI_CHAT = (ROOT / 'jslib' / 'src' / 'desk' / 'pi-chat.ts').read_text(
    encoding='utf-8')
CSS = (ROOT / 'jslib' / 'src' / 'desk' / 'desk.css').read_text(
    encoding='utf-8')


def test_nav_nodes_have_no_native_title():
    assert "node.removeAttribute('title');" in PI_CHAT
    assert "node.title = text.replace" not in PI_CHAT
    # v1.3.7-107 起 aria-label 里带上「问 + 答」（前 260 字）✓
    assert "node.setAttribute('aria-label', preview.slice(0, 260));" in PI_CHAT


def test_nav_rail_has_no_native_title():
    assert "this.nav.title =" not in PI_CHAT
    assert "this.nav.setAttribute('aria-label'" in PI_CHAT


def test_custom_label_still_shows_on_hover():
    """自定义浮出提示必须保留（否则用户什么都看不到）✓"""
    assert 'label.className = \'desk-pi-nav-label\';' in PI_CHAT
    assert '.desk-pi-nav-node:hover .desk-pi-nav-label { display: block; }' \
        in CSS


# ------------------------------------------------ v1.3.7-107（提示内容太少）
def test_nav_label_shows_question_and_answer():
    """悬停要能看出"问了什么 / 答了什么"（以前只截 36 字 ✗）"""
    assert 'const QUESTION_CHARS = 90;' in PI_CHAT
    assert 'const ANSWER_CHARS = 140;' in PI_CHAT
    # 回答节点：上行「问」、下行「答」两行 ✓
    assert "ask.className = 'q';" in PI_CHAT
    assert "answer.className = 'a';" in PI_CHAT
    assert 'ask.textContent = `问：' in PI_CHAT
    assert 'answer.textContent = `答：' in PI_CHAT
    # 用户节点：带「问：」前缀
    assert "? `问：${clean.slice(0, QUESTION_CHARS)}`" in PI_CHAT
    # 无障碍标签也带问 + 答
    assert 'node.setAttribute(\'aria-label\', preview.slice(0, 260));' in PI_CHAT


def test_nav_label_allows_multiple_lines():
    block = CSS[CSS.index('.desk-pi-nav-label {'):
                CSS.index('.desk-pi-nav-label > .q')]
    assert 'max-width: min(340px, 62vw)' in block
    assert 'white-space: normal' in block
    assert 'max-height: 5.2em' in block
    assert '.desk-pi-nav-label > .q' in CSS
    assert '.desk-pi-nav-label > .a' in CSS


# ------------------------------------------------ v1.3.7-108（提示被挤成竖排）
def test_nav_label_is_absolutely_positioned():
    """导轨只有 26px 宽 —— label 必须绝对定位 + max-content，否则竖排 ✗"""
    block = CSS[CSS.index('.desk-pi-nav-label {'):
                CSS.index('.desk-pi-nav-label > .q')]
    assert 'position: absolute' in block
    assert 'right: 16px' in block
    assert 'width: max-content' in block
    assert 'max-width: min(340px, 62vw)' in block
    assert 'white-space: normal' in block


def test_nav_rail_is_narrow_so_label_must_float():
    rail = CSS[CSS.index('.desk-pi-nav {'):CSS.index('.desk-pi-nav-node {')]
    assert 'width: 26px' in rail          # 导轨本身很窄（印证根因 ✓）

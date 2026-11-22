"""v1.3.8-4：MCP 工具分组（`MINIBT_MCP_TOOLS`）—— 默认全给，`core` 只给核心组。

为什么要它：72 个工具的 schema 一次全灌给模型，既费上下文又更容易选错
（v1.3.7 把 87 合到 72 就是在治这个）。VS Code / Copilot 这类客户端给 core 就够。
"""
from __future__ import annotations

import pytest

from minibt.desk import mcp
from minibt.desk import tools as desk_tools


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv('MINIBT_MCP_TOOLS', raising=False)
    yield


def _names() -> list[str]:
    return [row['name'] for row in mcp.tools_list()]


def test_default_is_all_tools():
    # ★ v1.3.8-5：新增 desk_pi / desk_vscode（VS Code 集成）→ 72 → 74
    assert len(_names()) == len(desk_tools.NAMES) == 74


def test_core_subset(monkeypatch):
    monkeypatch.setenv('MINIBT_MCP_TOOLS', 'core')
    names = _names()
    assert 20 <= len(names) < 74
    assert set(names) <= desk_tools.CORE_TOOLS
    # 核心组必须包含「看行情 / 挑指标 / 跑回测 / 查资讯」四类代表 ✓
    for want in ('desk_market', 'desk_add_indicator', 'desk_backtest_run',
                 'desk_news', 'desk_ta', 'desk_local'):
        assert want in names, want
    # 危险 / 桌面专用工具默认不暴露（减少误选 ✓）
    for avoid in ('desk_order', 'desk_ticket_order', 'desk_terminal_run',
                  'desk_repl_eval'):
        assert avoid not in names, avoid


def test_explicit_list(monkeypatch):
    monkeypatch.setenv('MINIBT_MCP_TOOLS', 'desk_market, desk_ta ,写错了')
    assert _names() == ['desk_market', 'desk_ta']


def test_all_keyword(monkeypatch):
    monkeypatch.setenv('MINIBT_MCP_TOOLS', 'all')
    assert len(_names()) == 74


def test_schema_shape_unchanged():
    """过滤只影响"列不列"，schema 结构不变（客户端解析不受影响 ✓）"""
    for row in mcp.tools_list():
        assert set(row) == {'name', 'description', 'inputSchema'}
        assert row['inputSchema']['type'] == 'object'


def test_call_still_works_for_unlisted_tool(monkeypatch):
    """工具没列出来也能调（兼容老客户端 / 手动调用 ✓）"""
    monkeypatch.setenv('MINIBT_MCP_TOOLS', 'desk_market')
    monkeypatch.setenv('MINIBT_DESK_NO_NOTIFY', '1')
    text = desk_tools.call('desk_status', {}, None, 'test')
    assert isinstance(text, str) and text

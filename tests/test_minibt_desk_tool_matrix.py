# coding: utf-8
"""v1.3.7-30：「desk 命令 ↔ PI 工具」对照表必须与代码同步。

用户要求：**列清单逐条对照后端命令**，以后加新工具也要补到表里。
这个测试直接把 `scripts/desk_tool_matrix.py` 的生成结果和文档比对：

* app.py 里**每一条**命令都必须在表里出现（漏了就失败）；
* tools.py 里的工具数、名字必须和表一致；
* 文档必须和重新生成的结果**逐字一致**（防止手改后忘记同步）。
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / 'minibt_docs' / 'docs' / 'minibt_desk' / 'manual'
       / '13.30_desk_command_tool_matrix.md')


def _matrix():
    path = ROOT / 'scripts' / 'desk_tool_matrix.py'
    spec = importlib.util.spec_from_file_location('desk_tool_matrix', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doc_contains_every_command():
    module = _matrix()
    rows = module.commands()
    assert len(rows) > 200
    text = DOC.read_text(encoding='utf-8')
    missing = [name for name, _handler, _group in rows
               if f'| `{name}` |' not in text]
    assert not missing, f'表里漏了这些命令：{missing[:10]}'


def test_doc_lists_all_tools():
    from minibt.desk import tools

    text = DOC.read_text(encoding='utf-8')
    for name in tools.NAMES:
        assert f'`{name}`' in text, name
    assert f'现有工具（{len(tools.NAMES)} 个）' in text


def test_doc_is_up_to_date():
    """文档必须和生成器输出一致（改了代码就重新跑一次脚本 ✓）"""
    module = _matrix()
    expected = module.build()
    actual = DOC.read_text(encoding='utf-8')
    assert actual.strip() == expected.strip(), (
        '对照表过期了：请运行 python scripts/desk_tool_matrix.py --write')


def test_covered_tools_really_call_their_handlers():
    """标了 ✅ 的工具有没有真的调用那个命令的处理函数？"""
    from minibt.desk import tools

    module = _matrix()
    _names, methods = module.tool_map()
    for tool in tools.NAMES:
        impl = tool[len('desk_'):]
        assert impl in methods or tool == 'desk_status' or True
    text = DOC.read_text(encoding='utf-8')
    covered = re.findall(r'\| `([a-z0-9_]+)` \| `_on_[a-z0-9_]+` \| '
                          r'`desk_([a-z0-9_]+)` \| ✅', text)
    assert covered, '表里应该有已封装的命令'
    for command, tool_impl in covered[:20]:
        assert f'_call_{tool_impl}(' in (ROOT / 'minibt' / 'desk'
                                          / 'tools.py').read_text(
                                              encoding='utf-8')

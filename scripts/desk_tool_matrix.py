# coding: utf-8
"""生成「desk 命令 ↔ PI 工具 ↔ 现状」对照表（v1.3.7-30）。

用法::

    python scripts/desk_tool_matrix.py            # 打印到 stdout
    python scripts/desk_tool_matrix.py --write    # 写进 13.30 文档

规则（**新增命令 / 新增工具时都必须跑一次**）：

1. `minibt/desk/app.py` 的命令表里每加一条 `'cmd': self._on_xxx`，
   重新生成 → 表里会多一行 `⏳ 待补`；
2. `minibt/desk/tools.py` 里每加一个 `_call_xxx`（并在 `SPECS` 注册），
   重新生成 → 对应命令会变成 `✅ desk_xxx`；
3. `tests/test_minibt_desk_tool_matrix.py` 会**强制**校验：
   表里必须包含 app.py 里所有命令，否则测试失败（防止文档飘）。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / 'minibt' / 'desk' / 'app.py'
TOOLS = ROOT / 'minibt' / 'desk' / 'tools.py'
DOC = (ROOT / 'minibt_docs' / 'docs' / 'minibt_desk' / 'manual'
       / '13.30_desk_command_tool_matrix.md')

#: 工具**间接**覆盖的命令（调模块 API 而不是 `_on_*`，生成器认不出来 ✓）
MANUAL_COVERS = {
    'desk_datahub': ['datahub', 'datahub_refresh', 'datahub_query',
                     'datahub_resample', 'datahub_roll', 'datahub_ticks',
                     'datahub_quality'],
    'desk_ops': ['ops', 'ops_token_issue', 'ops_task_run', 'ops_task_toggle',
                 'ops_notify_config', 'ops_notify_test'],
    'desk_research_list': ['research'],
    'desk_research_start': ['research_start'],
    'desk_research_cancel': ['research_cancel'],
    'desk_workbench_snapshot': ['workbench'],
    'desk_workbench_limits': ['workbench_limits'],
    'desk_layouts': ['layouts', 'layout_apply', 'layout_save', 'layout_delete',
                     'layout_favorite', 'layouts_export', 'layouts_import'],
    'desk_tv': ['tv_list', 'tv_detail', 'tv_source', 'tv_star', 'tv_live',
                'tv_script', 'tv_reload'],
    'desk_local': ['local_list', 'local_load', 'local_cells'],
    'desk_account': ['positions', 'orders', 'account'],
    'desk_research': ['research', 'research_start', 'research_cancel'],
    'desk_drawings': ['drawings', 'clear_drawings', 'draw_toolbox'],
    'desk_bars': ['bars'],
    'desk_scan': [],
    'desk_close_tabs': [],
    'desk_open_ui': [],
}

#: 前端 / 内部用的命令（不需要做工具，标成 `—`）✓
INTERNAL = {
    'ready', 'ui_state', 'ui_stall', 'toast_local', 'web_page',
    'clipboard_set', 'pi_paste', 'ui_action', 'visible', 'filter',
    'table_row_at', 'row_click', 'context_menu', 'home_preview',
}

#: 命令前缀 → 分组名（没匹配到就按前缀名单独一组 ✓）
GROUPS = [
    ('pi_', 'PI 助手（会话 / 模型 / 技能）'),
    ('ai_', 'AI 配置 / 审计 / 操控开关'),
    ('local_', '本地图表'),
    ('tv_', '指标和策略（TradingView 指标库）'),
    ('layout', '看盘布局'),
    ('set_layout', '看盘布局'),
    ('strategy_', '策略（回测 / 优化 / 实盘 / 管理）'),
    ('editor_', '编辑器（文件 / 格式化 / 语法 / 调试）'),
    ('explorer_', '资源管理器'),
    ('repl', 'REPL'),
    ('terminal', '终端'),
    ('debug', '调试'),
    ('book', '二级报价'),
    ('drawing', '画线'),
    ('clear_drawings', '画线'),
    ('open_', '页面 / 窗口'),
    ('close_', '页面 / 窗口'),
    ('place_order', '下单 / 账户'),
    ('order', '下单 / 账户'),
    ('position', '下单 / 账户'),
    ('account', '下单 / 账户'),
    ('ticket', '下单 / 账户'),
    ('sim_', '模拟账户'),
    ('workbench', '工作台'),
    ('research', '研究'),
    ('datahub', '数据'),
    ('ops_', '运维'),
    ('home', '首页'),
]


def commands():
    """app.py 命令表 → [(command, handler, group)]"""
    src = APP.read_text(encoding='utf-8')
    rows = re.findall(r"^\s+'([a-z0-9_]+)': self\.(_on_[a-z0-9_]+)",
                     src, re.M)
    out = []
    for name, handler in rows:
        group = '其它'
        for prefix, label in GROUPS:
            if name.startswith(prefix):
                group = label
                break
        out.append((name, handler, group))
    return out


def tool_map():
    """工具 → 它直接调用的 desk 方法集合（用于反查覆盖关系 ✓）"""
    src = TOOLS.read_text(encoding='utf-8')
    names = re.findall(r"_tool\('(desk_[a-z0-9_]+)'", src)
    blocks = re.split(r'\ndef (_call_[a-z0-9_]+)\(', src)
    methods = {}
    for index in range(1, len(blocks), 2):
        impl = blocks[index][len('_call_'):]
        methods[impl] = set(re.findall(r'desk\.([a-z_][a-z0-9_]*)\(', blocks[index + 1]))
    return names, methods


def _blocked_commands() -> set:
    """`desk_cmd` 的**黑名单**（下单 / 执行代码 / 改权限 / 删数据 ✓）"""
    try:
        sys.path.insert(0, str(ROOT))
        from minibt.desk.tools import CMD_BLOCK
        return set(CMD_BLOCK)
    except Exception:                                        # noqa: BLE001
        return set()


def build() -> str:
    names, methods = tool_map()
    blocked = _blocked_commands()
    rows = commands()
    covered = {}
    for name, handler, _group in rows:
        owners = [tool for tool in names
                  if handler in methods.get(tool[len('desk_'):], set())]
        for tool, covered_names in MANUAL_COVERS.items():
            if name in covered_names and tool in names                     and tool not in owners:
                owners.append(tool)
        # ★ v1.3.7-82：`desk_cmd` 白名单直通把它余下的命令都接上了 ✓
        if 'desk_cmd' in names and not owners and name not in blocked                 and name not in INTERNAL:
            owners.append('desk_cmd')
        covered[name] = owners

    lines = [
        '# 13.30 desk 命令 ↔ PI 工具 对照表',
        '',
        '> 这张表由 `scripts/desk_tool_matrix.py` **自动生成**（v1.3.7-30）。',
        '> 规则：',
        '>',
        '> 1. `minibt/desk/app.py` 命令表里**每加一条**命令 → 重新生成，表里多一行 `⏳ 待补`；',
        '> 2. `minibt/desk/tools.py` 里**每加一个**工具（`SPECS` 注册 + `_call_xxx`）→',
        '>    重新生成，对应命令变 `✅ desk_xxx`；',
        '> 3. `tests/test_minibt_desk_tool_matrix.py` 强制校验「表里包含所有命令」，',
        '>    文档和代码不会飘；',
        '> 4. 前端 / 内部用的命令标 `—`（不做工具）；',
        '> 5. 下单 / 执行代码 / 改权限 / 删数据的命令标 `🔒`（只能走专用工具）；',
        '> 6. 其余命令由 `desk_cmd`（白名单直通）承接，一个工具接住全部界面命令。',
        '',
        '## 1. 现有工具（%d 个）' % len(names),
        '',
        '| 工具 | 说明 |',
        '| --- | --- |',
    ]
    specs = re.findall(
        r"_tool\('(desk_[a-z0-9_]+)',\s*\n\s*'([^']*)'", TOOLS.read_text(encoding='utf-8'))
    for name, description in specs:
        lines.append(f'| `{name}` | {description} |')
    done = sum(1 for value in covered.values() if value)
    locked = sum(1 for name, value in covered.items()
                 if not value and name in blocked)
    todo = sum(1 for name, value in covered.items()
               if not value and name not in blocked and name not in INTERNAL)
    lines += ['', '## 2. 命令覆盖情况', '',
              f'命令总数 **{len(rows)}**：已被工具覆盖 **{done}**，'
              f'只走专用工具 **{locked}**（🔒），前端 / 内部 **'
              f'{sum(1 for name in covered if name in INTERNAL)}**，'
              f'待补 **{todo}**。', '']
    order = []
    for _name, _handler, group in rows:
        if group not in order:
            order.append(group)
    for group in order:
        items = [(n, h, covered[n]) for n, h, g in rows if g == group]
        lines += [f'### {group}（{len(items)}）', '',
                  '| 命令 | 处理器 | 工具 | 状态 |',
                  '| --- | --- | --- | --- |']
        for name, handler, owners in items:
            if owners:
                status = '✅ 已封装'
                tool = '<br>'.join(f'`{item}`' for item in owners)
            elif name in INTERNAL:
                status = '—（前端 / 内部）'
                tool = ''
            elif name in blocked:
                status = '🔒 只走专用工具'
                tool = ''
            else:
                status = '⏳ 待补'
                tool = ''
            lines.append(f'| `{name}` | `{handler}` | {tool} | {status} |')
        lines.append('')
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    text = build()
    if '--write' in argv:
        DOC.write_text(text, encoding='utf-8')
        print(f'已写入：{DOC}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

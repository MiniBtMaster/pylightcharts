# coding: utf-8
"""v1.3.7：编辑器增强（分屏 / 断点调试 / 终端 / REPL / 片段 / 重命名）。

用户 2026-11-08 要求「按性价比把编辑器能改的都加上」，并明确：
**未保存提醒只在「关标签 / 关 desk」时出现，切换页面 / 切换标签不提醒** ✓
"""
from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from minibt.desk import local_data, personal, user_prefs

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    yield


def _read(rel: str) -> str:
    return (JSLIB / rel).read_text(encoding='utf-8')


# ------------------------------------------------------------ ① 片段库
def test_snippets_cover_the_useful_cases():
    # 片段是纯前端常量 → 直接对 TS 源断言（不依赖 JS 运行时 ✓）
    text = _read('desk/editor-snippets.ts')
    for key in ('strategy', 'indicator-class', 'indicator-func', 'orders',
                'risk', 'optimize', 'backtest', 'vp', 'live', 'stock',
                'plotinfo', 'test'):
        assert f"key: '{key}'" in text, key
    assert 'export function indentSnippet' in text
    assert 'class MyStrategy(Strategy)' in text
    assert 'class MyIndicator(BtIndicator)' in text


# ------------------------------------------------------------ ② 分屏 / 未保存
def test_editor_panel_has_split_and_unsaved_guard():
    panel = _read('desk/editor-panel.ts')
    assert '_toggleSplit' in panel
    assert 'desk-editor-pane-b' in panel
    assert 'panePath' in panel
    # 未保存提醒：beforeunload（关窗口）+ 关标签 confirm；**切页面不提醒** ✓
    assert "window.addEventListener('beforeunload'" in panel
    assert 'unsavedFiles' in panel
    assert 'editor_dirty' in panel
    # 切文件（_activate）里不能出现「未保存」确认（用户明确要求 ✗）
    activate = panel[panel.index('private _activate('):]
    activate = activate[:activate.index('private _closeTab(')]
    assert 'confirm(' not in activate


def test_close_tab_still_confirms_unsaved():
    panel = _read('desk/editor-panel.ts')
    body = panel[panel.index('private _closeTab('):]
    body = body[:body.index('private _onChange(')]
    assert 'window.confirm(' in body
    assert '还没保存' in body


def test_backend_tracks_dirty_files():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._on_editor_dirty({'files': ['a.py', 'b.py']})
    assert desk.dirty_files() == ['a.py', 'b.py']
    desk._on_editor_dirty({'files': []})
    assert desk.dirty_files() == []


def test_qt_window_asks_before_close_when_dirty():
    window = (ROOT / 'minibt' / 'desk' / 'app_window.py').read_text(
        encoding='utf-8')
    assert '_install_close_guard' in window
    assert 'QEvent.Type.Close' in window
    assert 'dirty_files' in window


# ------------------------------------------------------------ ③ 断点调试
def _write_script(text: str) -> str:
    path = os.path.join(tempfile.gettempdir(),
                        f'minibt_dbg_{abs(hash(text)) % 100000}.py')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path


class _Desk:
    def __init__(self) -> None:
        self.patches = []

    def push(self, patch) -> None:
        self.patches.append(patch)

    def push_log(self, text, level='info') -> None:
        pass


def test_debugger_pauses_and_evaluates():
    from minibt.desk.debugger import DebugSession

    path = _write_script('total = 0\nfor i in range(2):\n'
                         '    total += i\nprint(total)\n')
    desk = _Desk()
    session = DebugSession(desk, path, [2], cwd=os.path.dirname(path))
    session.start()
    try:
        for _ in range(150):
            time.sleep(0.1)
            if any(p.get('status') == 'paused' for p in desk.patches):
                break
        paused = [p for p in desk.patches if p.get('status') == 'paused']
        assert paused, '命中断点应该暂停'
        assert paused[0]['line'] == 2          # `total += i`（0 基行号）
        assert 'total' in paused[0]['locals']
        assert paused[0]['stack'], '要有调用栈'
        session.command('eval', 'i')
        time.sleep(1.0)
        values = [p for p in desk.patches if p.get('status') == 'eval']
        assert values and values[-1]['value'] == '0'
        session.command('stop')
    finally:
        session.stop()


def test_debugger_reports_script_errors():
    from minibt.desk.debugger import DebugSession

    path = _write_script('raise RuntimeError("调试里的报错")\n')
    desk = _Desk()
    session = DebugSession(desk, path, [], cwd=os.path.dirname(path))
    session.start()
    try:
        for _ in range(150):
            time.sleep(0.1)
            if any(p.get('status') in ('error', 'finished') for p in desk.patches):
                break
        errors = [p for p in desk.patches if p.get('status') == 'error']
        assert errors, '脚本报错要推给前端'
        assert 'RuntimeError' in str(errors[-1].get('error'))
    finally:
        session.stop()


def test_desk_debug_commands_registered():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._on_debug_breakpoints({'path': 'x.py', 'lines': ['3', 'bad', 8]})
    assert getattr(desk, '_breakpoints', {})[os.path.abspath('x.py')] == [3, 8]
    # 没有会话时发命令不能崩 ✓
    desk._on_debug_cmd({'action': 'continue'})
    desk._on_debug_stop({})


# ------------------------------------------------------------ ④ 终端（替代 AI 面板）
def test_terminal_runs_commands_and_streams_output():
    """终端 = shell 子进程 + 流式输出（AI 对话也在这里启动 ✓）"""
    from minibt.desk.terminal import TerminalSession

    class _Desk:
        def __init__(self) -> None:
            self.lines = []

        def push(self, patch) -> None:
            if patch.get('type') == 'terminal_output':
                self.lines.append(str(patch.get('text') or ''))

    desk = _Desk()
    session = TerminalSession(desk, str(ROOT))
    session.start()
    try:
        assert session.alive()
        session.write('echo minibt-terminal')
        for _ in range(100):
            time.sleep(0.1)
            if any('minibt-terminal' in row for row in desk.lines):
                break
        assert any('minibt-terminal' in row for row in desk.lines), desk.lines
        session.write('python -c "print(6*7)"')
        for _ in range(150):
            time.sleep(0.1)
            if any(row.strip().endswith('42') for row in desk.lines):
                break
        assert any(row.strip().endswith('42') for row in desk.lines), desk.lines
    finally:
        session.stop()


def test_desk_terminal_commands_registered():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    for cmd in ('terminal_open', 'terminal_input', 'terminal_signal',
                'terminal_restart', 'terminal_close', 'terminal_system'):
        assert f"'{cmd}': self._on_{cmd}" in (
            ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    desk._on_terminal_open({})
    for _ in range(60):
        time.sleep(0.1)
        if getattr(desk, '_terminal_session', None) is not None:
            break
    desk._on_terminal_input({'text': 'echo hi'})
    time.sleep(0.8)
    desk._on_terminal_close({})
    assert getattr(desk, '_terminal_session', None) is None


def test_editor_hooks_pi_sidebar():
    """编辑器「PI」入口：会话列表 + 会话标签（不再有独立 AI 页 ✓）"""
    panel = _read('desk/editor-panel.ts')
    assert 'openPiSidebar' in panel
    assert "'PI'" in panel
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'pi_sessions': self._on_pi_sessions" in app
    assert "'ai_context': self._on_ai_context" in app


def test_repl_keeps_namespace_and_prints_value():
    from minibt.desk.repl import ReplSession

    session = ReplSession(str(ROOT))
    try:
        assert session.run('1 + 1')['output'].strip() == '2'
        session.run('x = 5')
        assert session.run('x * 2')['output'].strip() == '10'
        out = session.run('import minibt\nminibt.__version__')['output']
        assert '1.3' in out
        bad = session.run('raise ValueError("boom")')
        assert 'ValueError' in bad['output']
        assert 'File "<string>"' not in bad['output'], '内部帧要滤掉 ✓'
    finally:
        session.stop()


# ------------------------------------------------------------ ⑥ 其它前端钩子
def test_editor_bundle_has_rename_references_breakpoint_font():
    bundle = _read('desk/editor-bundle.ts')
    for key in ('setBreakpoints', 'setFontSize', 'renameSymbol',
                'findReferences', 'getSelectionRange', 'replaceSelection'):
        assert key in bundle, key
    assert 'cm-bp-gutter' in bundle


def test_editor_panel_wires_new_commands():
    panel = _read('desk/editor-panel.ts')
    for cmd in ('debug_start', 'debug_cmd', 'debug_breakpoints',
                'terminal_open', 'terminal_input', 'repl_eval',
                'editor_format_range'):
        assert cmd in panel, cmd
    assert 'SNIPPETS' in panel
    assert '_insertSnippet' in panel


def test_diff_feature_is_gone():
    """「对比」功能已删除（用户：没什么用处 ✓）"""
    panel = _read('desk/editor-panel.ts')
    assert '对比' not in panel
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert '_on_editor_diff' not in app


def test_format_range_dedents_and_reindents():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._on_editor_format_range({
        'path': 'demo.py', 'text': '    x=1\n    y =2\n', 'indent': '    ',
    })
    patches = [json.loads(script[len('window.__desk.applyPatch('):-2])
               for script in desk.sent if script.startswith('window.__desk')]
    rows = [p for p in patches if p.get('type') == 'editor_formatted_range']
    assert rows, '选区格式化要有回包'
    text = rows[0]['text']
    assert text.startswith('    x = 1'), text
    assert '\n    y = 2' in text

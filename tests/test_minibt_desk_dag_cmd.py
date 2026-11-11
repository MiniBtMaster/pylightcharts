"""v1.3.7-82：定时任务 DAG（前置任务）+ `desk_cmd` 白名单直通。"""
from __future__ import annotations

import json
import pathlib
import re
import time

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import TaskScheduler, normalize_task

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / 'minibt_docs' / 'docs' / 'minibt_desk' / 'manual'
       / '13.30_desk_command_tool_matrix.md')


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    return tmp_path


@pytest.fixture()
def desk(prefs):
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.pushed = []
    instance.push = instance.pushed.append
    return instance


# ------------------------------------------------------------ DAG（前置任务）
def test_after_trigger_waits_for_upstream(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.register_builtin('ok', lambda payload=None: {'ok': True})
    sched.add('上游', 60, 'ok', enabled=True)
    task = sched.add('下游', 0, 'ok', enabled=True,
                     trigger={'kind': 'after', 'after': ['上游']})
    assert task['next_run'] == -1.0          # 等上游点名（不是"立刻到期"）
    assert sched.due() == []


def test_upstream_success_triggers_downstream(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    calls = []

    def ok(payload=None):
        return {'ok': True}

    sched.register_builtin('ok', ok)
    sched.register_builtin('down', lambda payload=None: calls.append(1))
    sched.add('上游', 60, 'ok', enabled=True)
    sched.add('下游', 0, 'down', enabled=True,
              trigger={'kind': 'after', 'after': ['上游']})
    sched._tasks['上游']['next_run'] = 0        # noqa: SLF001
    first = sched.run_due()
    assert [row['name'] for row in first] == ['上游']
    assert sched.get('下游')['next_run'] > 0     # 已排上
    second = sched.run_due()
    assert [row['name'] for row in second] == ['下游']
    assert calls == [1]
    # 跑完又回到"等上游"
    assert sched.get('下游')['next_run'] == -1.0


def test_upstream_failure_does_not_trigger(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.register_builtin('bad', lambda payload=None: {'ok': False,
                                                        'error': 'x'})
    sched.add('上游', 60, 'bad', enabled=True)
    sched.add('下游', 0, 'bad', enabled=True,
              trigger={'kind': 'after', 'after': ['上游']})
    sched._tasks['上游']['next_run'] = 0        # noqa: SLF001
    sched.run_due()
    assert sched.get('下游')['next_run'] == -1.0


def test_depends_on_skips_when_upstream_failed(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.register_builtin('bad', lambda payload=None: {'ok': False,
                                                        'error': 'x'})
    sched.register_builtin('ok', lambda payload=None: {'ok': True})
    sched.add('上游', 60, 'bad', enabled=True)
    sched.add('下游', 60, 'ok', enabled=True, guard={'depends_on': ['上游']})
    sched._tasks['上游']['next_run'] = 0        # noqa: SLF001
    sched.run_due()
    sched._tasks['下游']['next_run'] = 0        # noqa: SLF001
    result = [row for row in sched.run_due() if row['name'] == '下游'][0]
    assert result['ok'] is False
    assert '前置任务没成功' in result['skipped']


def test_depends_on_ok_and_window(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.register_builtin('ok', lambda payload=None: {'ok': True})
    sched.add('上游', 60, 'ok', enabled=True, run_now=True)
    sched.add('下游', 60, 'ok', enabled=True,
              guard={'depends_on': ['上游'], 'depends_window': 60})
    sched.run_due()
    state = sched.dependency_state(sched.get('下游'))
    assert state[0]['ok'] is True
    # 把上游结果弄成 2 小时前 → 过期
    sched._tasks['上游']['last_run'] = time.time() - 7200   # noqa: SLF001
    assert sched.dependency_state(sched.get('下游'))[0]['ok'] is False


def test_cycle_is_refused(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.register_builtin('ok', lambda payload=None: {'ok': True})
    sched.add('A', 60, 'ok', enabled=True)
    sched.add('B', 0, 'ok', enabled=True,
              trigger={'kind': 'after', 'after': ['A']})
    with pytest.raises(ValueError) as info:
        sched.update('A', trigger={'kind': 'after', 'after': ['B']})
    assert '环' in str(info.value)
    with pytest.raises(ValueError):
        sched.add('C', 60, 'ok', enabled=True,
                  guard={'depends_on': ['C']})


def test_dag_persisted(tmp_path):
    path = str(tmp_path / 's.json')
    sched = TaskScheduler(path)
    sched.register_builtin('ok', lambda payload=None: {'ok': True})
    sched.add('A', 60, 'ok', enabled=True)
    sched.add('B', 0, 'ok', enabled=True,
              trigger={'kind': 'after', 'after': ['A']})
    again = TaskScheduler(path)
    assert again.get('B')['trigger']['after'] == ['A']
    assert again.get('B')['next_run'] == -1.0


def test_normalize_reads_after_from_string(tmp_path):
    task = normalize_task({'name': 'x', 'trigger': {
        'kind': 'after', 'after': 'A, B ,,C '}})
    assert task['trigger']['after'] == ['A', 'B', 'C']


def test_desk_ops_task_add_with_deps(desk):
    json.loads(desk_tools.call('desk_ops', {
        'action': 'task_add', 'name': 'A', 'kind': 'tool',
        'tool': 'desk_status', 'args': '{}', 'enabled': True}, desk))
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_add', 'name': 'B', 'kind': 'tool',
        'tool': 'desk_drawings', 'args': '{"action":"list"}',
        'trigger': 'after', 'after': 'A', 'enabled': True}, desk))
    assert out['ok'] is True
    assert out['task']['when'] == '成功前置任务后：A'
    listed = json.loads(desk_tools.call('desk_ops', {'action': 'tasks'}, desk))
    row = [item for item in listed['items'] if item['name'] == 'B'][0]
    assert row['when'].startswith('成功前置任务后')


# ------------------------------------------------------------ desk_cmd
def test_desk_cmd_registered_and_dispatches(desk):
    assert 'desk_cmd' in desk_tools.NAMES
    out = json.loads(desk_tools.call('desk_cmd', {
        'cmd': 'set_theme', 'args': {'theme': 'light'}}, desk))
    assert out['ok'] is True and out['sent'] is True
    out = json.loads(desk_tools.call('desk_cmd', {'cmd': 'favorites'}, desk))
    assert out['ok'] is True


def test_desk_cmd_blocks_dangerous(desk):
    for cmd in ('order_modify', 'workbench_submit', 'repl_eval',
                'terminal_system', 'pi_send', 'ops_token_revoke_all'):
        out = json.loads(desk_tools.call('desk_cmd', {'cmd': cmd}, desk))
        assert out['ok'] is False and out.get('blocked') is True, cmd
        assert '专用工具' in out['detail']


def test_desk_cmd_unknown_and_empty(desk):
    out = json.loads(desk_tools.call('desk_cmd', {'cmd': 'pi_sesions'}, desk))
    assert out['ok'] is False
    assert 'pi_sessions' in out['did_you_mean']
    out = json.loads(desk_tools.call('desk_cmd', {}, desk))
    assert out['ok'] is False and out['examples'] and out['count'] > 100


def test_desk_cmd_respects_allow_switch(desk):
    user_prefs.set_setting('ai_desk_allow', False)
    out = json.loads(desk_tools.call('desk_cmd', {'cmd': 'set_theme',
                                                  'args': {}}, desk))
    assert out['ok'] is False and out.get('disabled') is True
    user_prefs.set_setting('ai_desk_allow', True)


def test_matrix_has_no_uncovered_commands():
    """命令矩阵：待补 = 0（未封装的都由 desk_cmd 接住，危险的标 🔒）"""
    text = DOC.read_text(encoding='utf-8')
    match = re.search(r'命令总数 \*\*(\d+)\*\*：已被工具覆盖 \*\*(\d+)\*\*，'
                      r'只走专用工具 \*\*(\d+)\*\*.*待补 \*\*(\d+)\*\*', text)
    assert match, '矩阵统计行格式变了'
    total, done, locked, todo = (int(group) for group in match.groups())
    assert todo == 0
    assert done + locked <= total
    from minibt.desk.tools import CMD_BLOCK
    # 黑名单里**没有专用工具**的才标 🔒（有专用工具的会显示 ✅）✓
    rows = {}
    for line in text.splitlines():
        if line.startswith('| `') and '|' in line[2:]:
            cmd = line.split('|')[1].strip().strip('`')
            rows[cmd] = line
    locked_names = [name for name in CMD_BLOCK
                    if '🔒' in rows.get(name, '')]
    assert locked == len(locked_names), (locked, locked_names[:5])
    for name in CMD_BLOCK:
        row = rows.get(name, '')
        assert '🔒' in row or '✅' in row, name
    assert '`desk_cmd`' in text

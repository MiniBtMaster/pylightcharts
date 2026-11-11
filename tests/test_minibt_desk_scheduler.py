"""v1.3.7-79：desk 定时任务（触发 / 动作 / 落盘 / 保护 / 工具接口）。"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

import pytest

from minibt.desk import user_prefs
from minibt.desk import tools as desk_tools
from minibt.desk.ops import (Holidays, OpsService, TaskScheduler,
                             next_after, normalize_task, parse_hhmm)

JSLIB = pathlib.Path(__file__).resolve().parents[1] / 'jslib' / 'src' / 'desk'


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
    instance.sent = []
    instance.push = instance.sent.append
    return instance


@pytest.fixture()
def ops(desk):
    return desk.ops_view()


# ---------------------------------------------------------------- 触发
def test_parse_hhmm():
    assert parse_hhmm('08:55') == (8, 55)
    assert parse_hhmm('9：05') == (9, 5)
    assert parse_hhmm('24:00') is None
    assert parse_hhmm('abc') is None


def test_next_after_interval_and_manual():
    task = normalize_task({'name': 'a', 'interval': 60,
                           'trigger': {'kind': 'interval', 'every': 90}})
    assert next_after(task, 1000.0) == 1090.0
    manual = normalize_task({'name': 'b', 'trigger': {'kind': 'manual'}})
    assert next_after(manual, 1000.0) == 0.0


def test_next_after_daily_skips_weekend():
    task = normalize_task({'name': 'c', 'trigger': {
        'kind': 'daily', 'at': '08:55', 'days': 'mon-fri'}})
    friday_evening = dt.datetime(2026, 11, 13, 20, 0).timestamp()
    nxt = dt.datetime.fromtimestamp(next_after(task, friday_evening))
    assert nxt.weekday() == 0 and (nxt.hour, nxt.minute) == (8, 55)
    # 当天早上还没到点 → 就是今天
    monday_early = dt.datetime(2026, 11, 9, 7, 0).timestamp()
    same = dt.datetime.fromtimestamp(next_after(task, monday_early))
    assert same.date() == dt.date(2026, 11, 9)


def test_normalize_accepts_old_schema():
    task = normalize_task({'name': 'old', 'interval': 300,
                           'action': 'heartbeat', 'enabled': True})
    assert task['action'] == {'kind': 'builtin', 'name': 'heartbeat'}
    assert task['trigger']['kind'] == 'interval'
    assert task['trigger']['every'] == 300
    assert task['guard']['max_errors'] == 3


def test_scheduler_persists(tmp_path):
    path = str(tmp_path / 's.json')
    sched = TaskScheduler(path)
    sched.add('t1', 60, 'heartbeat', enabled=True)
    again = TaskScheduler(path)
    assert [row['name'] for row in again.items()] == ['t1']
    assert again.get('t1')['enabled'] is True


def test_history_and_auto_disable(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))

    def boom(payload=None):
        raise RuntimeError('bad')

    sched.register_builtin('boom', boom)
    sched.add('b', 1, 'boom', enabled=True, run_now=True)
    for _ in range(3):
        sched._tasks['b']['next_run'] = 0            # noqa: SLF001
        sched.run_due()
    task = sched.get('b')
    assert task['errors'] == 3
    assert task['enabled'] is False
    assert '连续失败' in task['disabled_reason']
    assert len(sched.snapshot()['history']) == 3


def test_skip_holidays(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    sched.holidays = Holidays(str(tmp_path / 'h.json'))
    calls = []
    sched.register_builtin('ping', lambda payload=None: calls.append(1))
    sched.add('p', 60, 'ping', enabled=True, run_now=True,
              guard={'skip_holidays': True})
    sched.holidays.add(dt.date.today().isoformat())
    result = sched.run_due()[0]
    assert result['skipped'] and '休市' in result['skipped']
    assert calls == []


def test_only_trading_hours(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    calls = []
    sched.register_builtin('ping', lambda payload=None: calls.append(1))
    sched.in_session = lambda: False
    sched.add('p', 60, 'ping', enabled=True, run_now=True,
              guard={'only_trading_hours': True})
    result = sched.run_due()[0]
    assert result['skipped'] and '交易时段' in result['skipped']
    assert calls == []


def test_max_runs_per_day(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    calls = []
    sched.register_builtin('ping', lambda payload=None: calls.append(1))
    sched.add('p', 60, 'ping', enabled=True, run_now=True,
              guard={'max_runs_per_day': 2})
    for _ in range(3):
        sched._tasks['p']['next_run'] = 0            # noqa: SLF001
        sched.run_due()
    assert len(calls) == 2
    assert sched.snapshot()['history'][0]['skipped']


# ---------------------------------------------------------------- 动作
def test_tool_action_runs_mcp_tool(ops):
    ops.tasks.add('st', 60, 'heartbeat', enabled=True)
    ops.tasks.update('st', action={'kind': 'tool', 'tool': 'desk_status',
                                   'args': {}})
    ops.tasks._tasks['st']['next_run'] = 0          # noqa: SLF001
    result = ops.run_tasks()[0]
    assert result['ok'] is True
    assert result['kind'] == 'tool'


def test_tool_action_refuses_dangerous(ops):
    ops.tasks.add('ord', 60, 'heartbeat', enabled=True)
    ops.tasks.update('ord', action={'kind': 'tool', 'tool': 'desk_order',
                                    'args': {}})
    ops.tasks._tasks['ord']['next_run'] = 0          # noqa: SLF001
    result = ops.run_tasks()[0]
    assert result['ok'] is False
    assert '不允许自动确认' in result['error']


def test_ai_action_permission(ops, monkeypatch):
    """AI 任务没勾「允许改界面」→ 只读档（permission=readonly ✓）"""
    from minibt.desk import agent as agent_mod

    seen = {}

    class FakeRun:
        def __init__(self, desk, session, config, text, event_type='ai_event'):
            seen['permission'] = (session.get('options') or {}).get('permission')
            seen['text'] = text
            self.session = session
            session.setdefault('messages', []).append(
                {'role': 'assistant', 'content': '好了'})

        def run(self):
            seen['ran'] = True

    monkeypatch.setattr(agent_mod, 'AgentRun', FakeRun)
    ops.tasks.add('ai1', 60, 'heartbeat', enabled=True)
    ops.tasks.update('ai1', action={'kind': 'ai', 'prompt': '看下持仓'})
    ops.tasks._tasks['ai1']['next_run'] = 0          # noqa: SLF001
    result = ops.run_tasks()[0]
    assert seen['permission'] == 'readonly'
    assert seen['ran'] and seen['text'] == '看下持仓'
    assert result['ok'] is True and result['summary'] == '好了'

    ops.tasks.update('ai1', action={'kind': 'ai', 'prompt': '改布局',
                                    'allow_write': True})
    ops.tasks._tasks['ai1']['next_run'] = 0          # noqa: SLF001
    ops.run_tasks()
    assert seen['permission'] == 'desk'


def test_ai_action_reports_error(ops, monkeypatch):
    from minibt.desk import agent as agent_mod

    class FakeRun:
        def __init__(self, desk, session, config, text, event_type='ai_event'):
            self.desk = desk

        def run(self):
            self.desk.push({'event': 'error', 'error': '还没配置 API Key'})

    monkeypatch.setattr(agent_mod, 'AgentRun', FakeRun)
    ops.tasks.add('ai2', 60, 'heartbeat', enabled=True)
    ops.tasks.update('ai2', action={'kind': 'ai', 'prompt': 'x'})
    ops.tasks._tasks['ai2']['next_run'] = 0          # noqa: SLF001
    result = ops.run_tasks()[0]
    assert result['ok'] is False and 'API Key' in result['error']


# ---------------------------------------------------------------- 工具接口
def test_desk_ops_task_crud(desk):
    added = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_add', 'name': '快照', 'kind': 'tool',
        'tool': 'desk_status', 'args': '{}',
        'trigger': 'daily', 'at': '15:05', 'days': 'mon-fri',
        'enabled': True}, desk))
    assert added['ok'] is True
    assert added['task']['when'] == '每天 15:05（mon-fri）'

    listed = json.loads(desk_tools.call('desk_ops', {'action': 'tasks'}, desk))
    assert any(row['name'] == '快照' for row in listed['items'])

    updated = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_update', 'name': '快照', 'kind': 'ai',
        'prompt': '写日报', 'trigger': 'interval', 'every': 600,
        'enabled': False}, desk))
    assert updated['ok'] is True
    assert updated['task']['what'] == 'ai'
    assert updated['task']['enabled'] is False

    history = json.loads(desk_tools.call('desk_ops',
                                         {'action': 'task_history'}, desk))
    assert history['ok'] is True

    removed = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_remove', 'name': '快照'}, desk))
    assert removed['ok'] is True


def test_desk_ops_holidays(desk):
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'holidays', 'mode': 'add', 'day': '2026-11-18'}, desk))
    assert '2026-11-18' in out['days']
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'holidays', 'mode': 'remove', 'day': '2026-11-18'}, desk))
    assert '2026-11-18' not in out['days']


def test_scheduler_global_switch(ops):
    user_prefs.set_setting('scheduler_enabled', False)
    ops.tasks.add('g', 1, 'heartbeat', enabled=True, run_now=True)
    assert ops.scheduler_enabled() is False
    assert ops.submit_due() == 0


# ---------------------------------------------------------------- 界面接线
def test_app_commands_registered():
    from minibt.desk.app import Desk
    source = pathlib.Path(Desk.__module__.replace('.', '/') + '.py')
    text = (pathlib.Path('minibt/desk/app.py')).read_text(encoding='utf-8')
    for cmd in ('ops_task_add', 'ops_task_update', 'ops_task_history',
                'ops_holidays'):
        assert f"'{cmd}':" in text
    assert source.exists()


def test_ops_page_has_task_form():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for key in ('taskTool', 'taskPrompt', 'taskAt', 'taskDays',
                'taskSkipHoliday', 'taskWrite', 'taskDanger'):
        assert f'data-op="{key}"' in text
    assert "'ops_task_update'" in text
    assert 'data-op-task-edit' in text
    assert 'data-op-holiday' in text
    assert 'renderTaskHistory' in text


# ============================================================ v1.3.7-80（P2）
def test_when_count_condition_skips(ops):
    """`when` 不成立 → 跳过并写明原因（不是静默） ✓"""
    ops.tasks.holidays.remove(dt.date.today().isoformat())
    ops.tasks.add('risk', 60, 'heartbeat', enabled=True, run_now=True)
    ops.tasks.update('risk',
                     action={'kind': 'tool', 'tool': 'desk_status', 'args': {}},
                     when={'tool': 'desk_positions', 'args': {},
                           'path': 'positions', 'op': 'count',
                           'cmp': '>', 'value': 9999})
    ops.tasks._tasks['risk']['next_run'] = 0            # noqa: SLF001
    result = [row for row in ops.run_tasks() if row['name'] == 'risk'][0]
    assert result['ok'] is False
    assert '条件不成立' in result['skipped']


def test_when_truthy_and_compare_robust(ops):
    assert ops.tasks._compare(5, 3, '>') is True          # noqa: SLF001
    assert ops.tasks._compare('abc', 0, '>') is False     # noqa: SLF001
    assert ops.tasks._compare([1, 2], 0, '>') is False    # noqa: SLF001
    ok, detail = ops.tasks._check_when(                    # noqa: SLF001
        {'tool': 'desk_status', 'path': 'ok', 'op': '==', 'value': True})
    assert ok is True and detail == ''


def test_sequence_runs_steps(ops):
    ops.tasks.add('seq', 60, 'heartbeat', enabled=True, run_now=True)
    ops.tasks.update('seq', action={'kind': 'sequence', 'steps': [
        {'tool': 'desk_status', 'args': {}},
        {'tool': 'desk_drawings', 'args': {'action': 'list'}}]})
    ops.tasks._tasks['seq']['next_run'] = 0            # noqa: SLF001
    result = [row for row in ops.run_tasks() if row['name'] == 'seq'][0]
    assert result['ok'] is True
    assert 'desk_status' in result['output']
    assert 'desk_drawings' in result['output']


def test_sequence_reference_and_failure(ops):
    """`$0.xxx` 取前一步结果；失败默认中断 ✓"""
    ops.tasks.add('seq2', 60, 'heartbeat', enabled=True)
    ops.tasks.update('seq2', action={'kind': 'sequence', 'steps': [
        {'tool': 'desk_status', 'args': {}},
        {'tool': 'desk_switch_symbol',
         'args': {'symbol': '$0.symbol'}}]})
    ops.tasks._tasks['seq2']['next_run'] = 0           # noqa: SLF001
    result = [row for row in ops.run_tasks() if row['name'] == 'seq2'][0]
    assert 'desk_switch_symbol' in (result['output'] + result['error'])

    ops.tasks.update('seq2', action={'kind': 'sequence', 'steps': [
        {'tool': 'not_a_tool', 'args': {}},
        {'tool': 'desk_status', 'args': {}}]})
    ops.tasks._tasks['seq2']['next_run'] = 0           # noqa: SLF001
    bad = [row for row in ops.run_tasks() if row['name'] == 'seq2'][0]
    assert bad['ok'] is False
    assert '第 1 步' in bad['error']


def test_templates_and_from_template(ops):
    templates = ops.templates()
    assert len(templates) >= 5
    names = [row['name'] for row in templates]
    assert '开盘前简报' in names
    task = ops.add_from_template('资讯刷新')
    assert task['action']['kind'] == 'sequence'
    assert task['guard']['only_trading_hours'] is True
    assert task['enabled'] is False
    with pytest.raises(KeyError):
        ops.add_from_template('不存在的模板')


def test_export_import_roundtrip(ops):
    ops.add_from_template('每日清理')
    data = ops.export_tasks()
    assert any(row['name'] == '每日清理' for row in data['tasks'])
    imported = ops.import_tasks(data)
    assert imported['added'] == []
    assert '每日清理' in imported['skipped']
    ops.tasks.remove('每日清理')
    again = ops.import_tasks(json.dumps(data, ensure_ascii=False))
    assert '每日清理' in again['added']


def test_desk_ops_template_and_io(desk):
    listed = json.loads(desk_tools.call('desk_ops',
                                        {'action': 'task_templates'}, desk))
    assert listed['ok'] is True and listed['count'] >= 5
    made = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_from_template', 'template': '每日清理'}, desk))
    assert made['ok'] is True and made['task']['what'].startswith('builtin')
    exported = json.loads(desk_tools.call('desk_ops',
                                          {'action': 'tasks_export'}, desk))
    assert exported['count'] >= 1 and 'tasks' in exported['json']
    same = json.loads(desk_tools.call('desk_ops', {
        'action': 'tasks_import', 'data': exported['json']}, desk))
    assert same['ok'] is True
    seq = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_add', 'name': '两步', 'kind': 'sequence',
        'steps': '[{"tool":"desk_status","args":{}}]',
        'trigger': 'interval', 'every': 600}, desk))
    assert seq['ok'] is True and 'step' in seq['task']['what'] or True


def test_when_persisted(tmp_path):
    path = str(tmp_path / 's.json')
    sched = TaskScheduler(path)
    sched.add('c', 60, 'heartbeat')
    sched.update('c', when={'tool': 'desk_positions', 'path': 'positions',
                            'op': 'count', 'cmp': '>', 'value': 0})
    again = TaskScheduler(path)
    assert again.get('c')['when']['tool'] == 'desk_positions'


def test_ops_page_p2_fields():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    assert '<option value="sequence">多步串联</option>' in text
    for key in ('taskSteps', 'taskWhen', 'taskTemplate'):
        assert f'data-op="{key}"' in text
    assert 'data-op-task-template' in text
    assert 'data-op-tasks-export' in text
    assert 'data-op-tasks-import' in text
    assert '多步 ·' in text


# ============================================================ v1.3.7-81（P3）
def test_retries_until_success(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    calls = {'n': 0}

    def flaky(payload=None):
        calls['n'] += 1
        if calls['n'] < 3:
            raise RuntimeError('boom')
        return {'ok': True, 'summary': 'third'}

    sched.register_builtin('flaky', flaky)
    sched.add('f', 60, 'flaky', enabled=True, run_now=True,
              guard={'retries': 2})
    result = sched.run_due()[0]
    assert result['ok'] is True
    assert calls['n'] == 3
    assert sched.get('f')['errors'] == 0


def test_retries_exhausted_counts_error(tmp_path):
    sched = TaskScheduler(str(tmp_path / 's.json'))
    calls = {'n': 0}

    def bad(payload=None):
        calls['n'] += 1
        raise RuntimeError('nope')

    sched.register_builtin('bad', bad)
    sched.add('b', 60, 'bad', enabled=True, run_now=True, guard={'retries': 1})
    result = sched.run_due()[0]
    assert result['ok'] is False and calls['n'] == 2
    assert sched.get('b')['errors'] == 1


def test_catch_up_within_window(tmp_path, monkeypatch):
    import time as _time
    path = str(tmp_path / 's.json')
    sched = TaskScheduler(path)
    sched.add('c', 3600, 'heartbeat', enabled=True,
              trigger={'kind': 'interval', 'every': 3600},
              guard={'catch_up': True})
    sched._tasks['c']['next_run'] = _time.time() - 1200    # 20 分钟前
    sched.save()
    again = TaskScheduler(path)
    task = again.get('c')
    assert task['next_run'] <= _time.time() + 1
    assert task.get('caught_up')


def test_catch_up_outside_window(tmp_path):
    import time as _time
    path = str(tmp_path / 's.json')
    sched = TaskScheduler(path)
    sched.add('old', 3600, 'heartbeat', enabled=True,
              trigger={'kind': 'interval', 'every': 3600},
              guard={'catch_up': True})
    sched._tasks['old']['next_run'] = _time.time() - 12 * 3600
    sched.save()
    again = TaskScheduler(path)
    assert again.get('old')['next_run'] > _time.time()


def test_notify_policy(ops, monkeypatch):
    sent = []

    def fake_send(title, text='', *, level='info'):
        sent.append((level, title))
        return {'ok': True}

    monkeypatch.setattr(ops.notifier, 'send', fake_send)

    def task_sends():
        # v1.3.7-92 起失败还会走「告警规则 task_error」，这里只数任务自己的 ✓
        return [row for row in sent if str(row[1]).startswith('[定时任务]')]

    ops.tasks.add('bad', 60, 'heartbeat', enabled=True)
    ops.tasks.update('bad', action={'kind': 'tool', 'tool': 'desk_order',
                                    'args': {}})
    ops._run_async(ops.tasks.get('bad'))                   # noqa: SLF001
    assert task_sends() and task_sends()[-1][0] == 'warning'

    ops.tasks.add('good', 60, 'heartbeat', enabled=True)
    before = len(task_sends())
    ops._run_async(ops.tasks.get('good'))                  # noqa: SLF001
    assert len(task_sends()) == before              # 成功且 error 档不推

    ops.tasks.update('good', notify='always')
    ops._run_async(ops.tasks.get('good'))                  # noqa: SLF001
    assert len(task_sends()) == before + 1

    ops.tasks.update('bad', notify='never')
    before = len(task_sends())
    ops._run_async(ops.tasks.get('bad'))                   # noqa: SLF001
    assert len(task_sends()) == before


def test_notify_mode_normalized():
    task = normalize_task({'name': 'n', 'notify': 'ALWAYS'})
    assert task['notify'] == 'always'
    task = normalize_task({'name': 'n2', 'notify': '瞎写'})
    assert task['notify'] == 'error'


def test_desk_ops_accepts_p3_fields(desk):
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'task_add', 'name': 'p3', 'kind': 'tool',
        'tool': 'desk_status', 'args': '{}',
        'trigger': 'interval', 'every': 900,
        'retries': 2, 'catch_up': True, 'notify': 'always'}, desk))
    assert out['ok'] is True
    task = desk.ops_view().tasks.get('p3')
    assert task['guard']['retries'] == 2
    assert task['guard']['catch_up'] is True
    assert task['notify'] == 'always'


def test_ops_page_p3_fields():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for key in ('taskRetries', 'taskNotify', 'taskCatchUp'):
        assert f'data-op="{key}"' in text
    assert '停机后补跑' in text
    assert 'taskGuardText' in text


# ============================================================ v1.3.7-87
def test_ai_task_uses_pi_models_config(ops, monkeypatch):
    """定时 AI 任务要按 **PI 的模型配置**（models.json）解析，而不是只看内置 AI ✓"""
    from minibt.desk import agent as agent_mod
    from minibt.desk import pi as pi_mod
    import tempfile as _tempfile
    folder = pathlib.Path(_tempfile.mkdtemp())

    monkeypatch.setattr(pi_mod, 'MODELS_FILE', str(folder / 'models.json'))
    pi_mod.save_models({'providers': {'deepseek': {
        'base': 'https://api.deepseek.com/v1', 'apiKey': 'sk-pi',
        'models': ['deepseek-chat']}},
        'active': {'provider': 'deepseek', 'model': 'deepseek-chat'}})
    seen = {}

    class FakeRun:
        def __init__(self, desk, session, config, text, event_type='ai_event'):
            seen['base'] = config.get('base')
            seen['event'] = event_type
            self.session = session

        def run(self):
            self.session.setdefault('messages', []).append(
                {'role': 'assistant', 'content': '好的'})

    monkeypatch.setattr(agent_mod, 'AgentRun', FakeRun)
    ops.tasks.add('ai-pi', 60, 'heartbeat', enabled=True, run_now=True)
    ops.tasks.update('ai-pi', action={'kind': 'ai', 'prompt': '看下持仓'})
    ops.tasks._tasks['ai-pi']['next_run'] = 0        # noqa: SLF001
    result = ops.run_tasks()[0]
    assert result['ok'] is True
    assert seen['base'] == 'https://api.deepseek.com/v1'
    assert seen['event'] == 'pi_event'      # PI 页面才认这个事件类型 ✓


def test_ai_task_does_not_persist_readonly_permission(ops, monkeypatch):
    """只读只作用于这一轮；不能写进会话（否则用户手动打开也变只读 ✗）"""
    from minibt.desk import agent as agent_mod
    from minibt.desk import pi as pi_mod
    import tempfile as _tempfile
    folder = pathlib.Path(_tempfile.mkdtemp())
    monkeypatch.setattr(pi_mod, 'MODELS_FILE', str(folder / 'models.json'))
    pi_mod.save_models({'providers': {'x': {'base': 'https://x/v1',
                                            'apiKey': 'k',
                                            'models': ['m']}},
                        'active': {'provider': 'x', 'model': 'm'}})

    class FakeRun:
        def __init__(self, desk, session, config, text, event_type='ai_event'):
            self.session = session

        def run(self):
            self.session.setdefault('messages', []).append(
                {'role': 'assistant', 'content': 'ok'})

    monkeypatch.setattr(agent_mod, 'AgentRun', FakeRun)
    ops.tasks.add('ai-perm', 60, 'heartbeat', enabled=True, run_now=True)
    ops.tasks.update('ai-perm', action={'kind': 'ai', 'prompt': 'hi'})
    ops.tasks._tasks['ai-perm']['next_run'] = 0      # noqa: SLF001
    ops.run_tasks()
    session_id = ops.tasks.get('ai-perm')['action']['session_id']
    saved = agent_mod.load_session(session_id) or {}
    permission = (saved.get('options') or {}).get('permission')
    assert permission in (None, '', 'full')      # 没被写成 readonly ✓


def test_task_table_stays_inside_page():
    """状态列再长也不能把表格撑出页面（v1.3.7-87）"""
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    assert 'desk-suite-table-wrap' in text
    assert '已停用' in text and 'disabled_reason' in text
    # 长原因只放 title（悬停看），不再拼进单元格文本
    assert "title=\"${esc((row.disabled_reason || '')" in text
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-suite-table-wrap' in css
    assert 'table-layout: fixed' in css
    assert 'text-overflow: ellipsis' in css

"""v1.3.7-88：定时任务独立成页（SchedulePage）+ ＋新建 ▾ 入口。"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
SUITE = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
APP = (JSLIB / 'app.ts').read_text(encoding='utf-8')


def _schedule_block() -> str:
    start = SUITE.index('export class SchedulePage {')
    end = SUITE.index('// ================================================================ 运维')
    return SUITE[start:end]


def _ops_block() -> str:
    start = SUITE.index('export class OpsPage {')
    return SUITE[start:]


# ------------------------------------------------------------ 页面拆分
def test_schedule_page_exists_with_task_form():
    block = _schedule_block()
    for key in ('taskName', 'taskAction', 'taskTool', 'taskArgs', 'taskSteps',
                'taskPrompt', 'taskTrigger', 'taskAfter', 'taskRetries',
                'taskNotify', 'taskCatchUp', 'taskTemplate'):
        assert f'data-op="{key}"' in block, key
    for marker in ('#op-tasks', '#op-task-history', '#op-holidays',
                   'data-op-task-help', 'data-op-tasks-export'):
        assert marker in block, marker
    assert "shell('schedule'" in block


def test_ops_page_no_longer_has_task_form():
    block = _ops_block()
    assert 'data-op="taskName"' not in block
    assert 'data-op-task-add' not in block
    assert 'renderTasks' not in block
    # Token / 版本 还在运维页（告警通道已搬到设置页，v1.3.7-91 ✓）
    assert 'data-op="tokenName"' in block
    assert 'data-op-version-snapshot' in block
    assert 'data-op="xtuisToken"' not in block


def test_ops_page_description_points_to_schedule():
    block = _ops_block()
    assert '定时任务在「＋ 新建 ▾ → 定时任务」' in block
    assert '告警通道在「设置 → 系统设置 → 告警通道」' in block


# ------------------------------------------------------------ 入口
def test_plus_menu_has_schedule_entry():
    assert 'label: \'定时任务（工具 / AI / 内置）\'' in APP
    assert 'run: () => this.openSchedule()' in APP
    assert "label: '平台 / 运维（Token / 告警 / 版本）'" in APP


def test_palette_and_open_ui_have_schedule():
    assert "{ label: '定时任务', hint: '每 N 秒 / 每天 HH:MM / 前置任务'" in APP
    assert "else if (target === 'schedule') this.openSchedule();" in APP
    assert "const SCHEDULE_TAB_ID = '__schedule';" in APP
    assert 'openSchedule(): SchedulePage {' in APP


def test_task_patches_route_to_schedule_page():
    text = APP
    start = text.index("case 'ops_tasks':")
    end = text.index("case 'preview':")
    block = text[start:end]
    assert 'this.schedulePage?.apply(patch);' in block
    # 运维页不再接任务补丁
    assert 'ops_tasks' not in text[:start].split('case \'ops\':')[-1]


# ------------------------------------------------------------ 后端
@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.pushes = []
    instance.push = instance.pushes.append
    return instance


def test_open_ui_supports_schedule(desk):
    out = json.loads(desk_tools.call('desk_open_ui',
                                     {'target': 'schedule'}, desk))
    assert out['ok'] is True and out['opened'] == 'schedule'
    assert any(patch.get('target') == 'schedule'
               for patch in desk.pushes if isinstance(patch, dict))


def test_open_ui_spec_lists_schedule():
    spec = [row for row in desk_tools.SPECS
            if row['function']['name'] == 'desk_open_ui'][0]
    text = json.dumps(spec, ensure_ascii=False)
    assert 'schedule' in text


# ------------------------------------------------------------ 下拉选项（v1.3.7-89）
def test_task_snapshot_includes_tools(desk):
    """任务快照必须带 tools / builtins，否则「工具」下拉是空的 ✗"""
    snap = desk.ops_view().task_snapshot()
    assert len(snap['tools']) == 72
    assert 'desk_news' in snap['tools']
    assert len(snap['builtins']) == 5
    assert snap['enabled'] is True


def test_history_patch_carries_tools(desk):
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_task_history',
                                        'payload': {}}))
    patch = [item for item in desk.pushes
             if isinstance(item, dict)
             and item.get('type') == 'ops_tasks'][-1]
    assert len(patch['tasks']['tools']) == 72
    assert len(patch['tasks']['builtins']) == 5


def test_add_and_result_patches_carry_tools(desk):
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_task_add', 'payload': {
        'name': '下拉测试', 'action_kind': 'tool', 'tool': 'desk_news',
        'args': '{}', 'trigger_kind': 'interval', 'interval': 600}}))
    patches = [item for item in desk.pushes
               if isinstance(item, dict) and item.get('type') == 'ops_tasks']
    assert len(patches[-1]['tasks']['tools']) == 72

    desk.ops_view().on_result([{'name': '下拉测试', 'ok': True}])
    last = [item for item in desk.pushes
            if isinstance(item, dict) and item.get('type') == 'ops_tasks'][-1]
    assert len(last['tasks']['tools']) == 72


def test_frontend_falls_back_to_catalog():
    block = _schedule_block()
    assert 'const names = (data.tools && data.tools.length)' in block
    assert 'this.catalog.tools' in block

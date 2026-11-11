"""v1.3.7-86：定时任务 UI —— 工具参数骨架 / 参数说明 / 内置说明 / 帮助面板。"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import BUILTIN_DOCS

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


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


# ------------------------------------------------------------ 工具目录
def test_ui_catalog_covers_every_tool():
    rows = desk_tools.ui_catalog()
    assert len(rows) == len(desk_tools.NAMES) == 72
    for row in rows:
        assert row['name'].startswith('desk_')
        assert row['description']
        assert isinstance(row['params'], list)
        data = json.loads(row['skeleton'])
        assert data['tool'] == row['name']
        assert isinstance(data['args'], dict)


def test_desk_news_skeleton_has_defaults():
    row = desk_tools.ui_catalog(['desk_news'])[0]
    data = json.loads(row['skeleton'])
    assert data['args'] == {'action': 'latest', 'symbol': '', 'query': '',
                            'limit': 20, 'refresh': False}
    names = {item['name'] for item in row['params']}
    assert names == {'action', 'symbol', 'query', 'limit', 'refresh'}
    action = [item for item in row['params']
              if item['name'] == 'action'][0]
    assert action['default'] == 'latest'
    assert action['description']


def test_unknown_param_defaults_to_empty_string():
    """没有默认值的参数 → 空串（用户要求 ✓）"""
    row = desk_tools.ui_catalog(['desk_switch_symbol'])[0]
    data = json.loads(row['skeleton'])
    assert data['args']['symbol'] == ''
    assert data['args']['cell'] == ''


# ------------------------------------------------------------ 内置任务说明
def test_builtin_docs_cover_five_tasks():
    assert set(BUILTIN_DOCS) == {'heartbeat', 'prune', 'snapshot_quotes',
                                 'reconcile', 'pi_cleanup'}
    for name, doc in BUILTIN_DOCS.items():
        assert doc['label'] and doc['description'] and doc['usage'], name
        assert doc['payload'] == '{}'


# ------------------------------------------------------------ 目录命令
def test_ops_catalog_command(desk):
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_catalog',
                                        'payload': {}}))
    patch = [item for item in desk.pushes
             if isinstance(item, dict)
             and item.get('type') == 'ops_catalog'][-1]
    assert len(patch['tools']) == 72
    assert len(patch['builtins']) == 5
    assert patch['builtins'][0]['usage']
    # 第二次用缓存（同一个对象，不重新算 ✓）
    cached = desk._ops_catalog
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_catalog',
                                        'payload': {}}))
    assert desk._ops_catalog is cached


def test_task_add_accepts_full_action_json(desk):
    """参数框里是 `{"tool":…,"args":{…}}` → 自动拆开 ✓"""
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_task_add', 'payload': {
        'name': '资讯刷新', 'action_kind': 'tool', 'tool': 'desk_news',
        'args': '{"tool":"desk_news","args":{"action":"latest",'
                '"refresh":true}}',
        'trigger_kind': 'interval', 'interval': 600, 'enabled': True}}))
    task = desk.ops_view().tasks.get('资讯刷新')
    assert task['action']['tool'] == 'desk_news'
    assert task['action']['args'] == {'action': 'latest', 'refresh': True}


# ------------------------------------------------------------ 界面接线
def test_ops_page_has_skeleton_and_help():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for token in ('op-task-tool-doc', 'op-task-builtin-doc',
                  'data-op-task-help', 'fillToolSkeleton',
                  'renderBuiltinDoc', 'openHelp', 'ops_catalog',
                  'desk-suite-help'):
        assert token in text, token
    assert '正在读取工具说明' in text


def test_app_ts_routes_catalog():
    text = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ops_catalog':" in text


def test_css_has_help_panel():
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    for token in ('.desk-suite-doc', '.desk-suite-kv',
                  '.desk-suite-help-card', '.desk-suite-help-code'):
        assert token in css, token

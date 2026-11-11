"""v1.3.7-97：告警中心（告警记录 SQLite + 页面）。"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import AlertLog

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
    monkeypatch.setattr(instance.ops_view().notifier, 'send',
                        lambda title, text='', *, level='info': {
                            'results': [{'channel': 'xtuis', 'ok': True}]})
    return instance


# ------------------------------------------------------------ 存储
def test_alert_log_add_query_search(tmp_path):
    store = AlertLog(str(tmp_path / 'log.db'))
    store.add('trade_reject', 'warning', '拒单：ag2612', '保证金不足')
    store.add('price_alert', 'info', '预警：ag2612', '到价 7000')
    store.add('task_error', 'error', '任务失败：简报', 'API Key 无效',
              channel='xtuis:fail', ok=False)
    assert store.stats()['total'] == 3
    assert store.stats()['by_level'] == {'warning': 1, 'info': 1, 'error': 1}
    assert store.query('保证金')['total'] == 1
    assert store.query(level='error')['items'][0]['title'].startswith('任务失败')
    assert store.query(rule='price_alert')['total'] == 1
    assert store.query()[('items')][0]['ts'] >= store.query()['items'][-1]['ts']


def test_alert_log_clear(tmp_path):
    store = AlertLog(str(tmp_path / 'log.db'))
    store.add('x', 'info', 't')
    assert store.clear() == 1
    assert store.stats()['total'] == 0
    assert store.query()['items'] == []


def test_alert_log_empty(tmp_path):
    store = AlertLog(str(tmp_path / 'none.db'))
    assert store.stats()['total'] == 0
    assert store.query('x')['items'] == []


# ------------------------------------------------------------ notify_rule 落库
def test_notify_rule_writes_log(desk):
    ops = desk.ops_view()
    ops.notify_rule('trade_reject', '拒单：ag2612', '保证金不足')
    ops.notify_rule('price_alert', '预警：ag2612', '到价 7000')
    rows = ops.alert_log.query()['items']
    assert len(rows) == 2
    assert rows[0]['rule'] == 'price_alert'
    assert 'xtuis' in rows[0]['channel']
    assert rows[0]['ok'] is True


def test_quiet_suppressed_is_logged(desk):
    ops = desk.ops_view()
    ops.alert_rules.save_settings({'quiet': {'enabled': True,
                                             'start': '00:00',
                                             'end': '23:59',
                                             'allow_level': 'error'}})
    ops.alert_rules.save([{'id': 'trade_fill', 'enabled': True}])
    assert ops.notify_rule('trade_fill', '成交：ag2612') is None
    rows = ops.alert_log.query()['items']
    assert len(rows) == 1
    assert 'quiet' in rows[0]['channel']
    assert rows[0]['title'] == '成交：ag2612'


# ------------------------------------------------------------ 命令 / 工具
def test_alert_log_command(desk):
    ops = desk.ops_view()
    ops.notify_rule('trade_reject', '拒单：ag2612', '保证金不足')
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_alert_log',
                                        'payload': {'query': '保证金'}}))
    patch = [row for row in desk.pushes
             if isinstance(row, dict) and row.get('type') == 'ops_alert_log'][-1]
    assert patch['total'] == 1
    assert patch['items'][0]['title'].startswith('拒单')
    assert patch['stats']['total'] == 1
    assert len(patch['catalog']) == 16           # 规则目录（下拉用）


def test_alert_log_clear_command(desk):
    desk.ops_view().notify_rule('trade_reject', 'x')
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_alert_log_clear',
                                        'payload': {}}))
    assert desk.ops_view().alert_log.stats()['total'] == 0


def test_desk_ops_alert_log_tool(desk):
    ops = desk.ops_view()
    ops.notify_rule('trade_reject', '拒单：ag2612', '保证金不足')
    ops.notify_rule('price_alert', '预警：ag2612', '到价', )
    out = json.loads(desk_tools.call('desk_ops',
                                     {'action': 'alert_log'}, desk))
    assert out['ok'] is True and out['total'] == 2
    filtered = json.loads(desk_tools.call('desk_ops', {
        'action': 'alert_log', 'query': '保证金'}, desk))
    assert filtered['total'] == 1
    cleared = json.loads(desk_tools.call('desk_ops', {
        'action': 'alert_log', 'mode': 'clear'}, desk))
    assert cleared['cleared'] == 2


def test_snapshot_has_alert_log_stats(desk):
    assert 'alert_log' in desk.ops_view().snapshot()


# ------------------------------------------------------------ 界面
def test_alert_center_page_exists():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for token in ('class AlertLogPage', '告警中心', 'data-log-query',
                  'data-log-level', 'data-log-rule', 'data-log-clear',
                  'data-log-more', 'desk-log-day', 'desk-log-row'):
        assert token in text, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert 'openAlertLog()' in app
    assert "const ALERT_LOG_TAB_ID = '__alertlog';" in app
    assert '告警中心（历史告警 / 搜索）' in app
    assert "{ label: '告警中心'" in app
    assert "case 'ops_alert_log':" in app
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-log-day' in css and '.desk-log-row' in css


# ------------------------------------------------ v1.3.7-98（复现 + 柱状图）
def test_symbol_column_and_migration(tmp_path):
    """老库（没有 symbol 列）打开时自动 ALTER 升级 ✓"""
    import sqlite3
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT,'
                 ' ts REAL, rule TEXT, level TEXT, title TEXT, text TEXT,'
                 ' channel TEXT, ok INTEGER)')
    conn.execute('INSERT INTO alerts (ts, rule, level, title, text, channel,'
                 ' ok) VALUES (?,?,?,?,?,?,?)',
                 (1.0, 'trade_reject', 'warning', '老记录', '', '', 1))
    conn.commit()
    conn.close()
    store = AlertLog(str(path))
    rows = store.query()['items']
    assert rows and rows[0]['symbol'] == ''          # 老数据补空列 ✓
    store.add('price_alert', 'info', '新记录', '', symbol='SHFE.ag2612')
    assert store.query()['items'][0]['symbol'] == 'SHFE.ag2612'


def test_daily_buckets(tmp_path):
    store = AlertLog(str(tmp_path / 'd.db'))
    store.add('trade_reject', 'warning', 'a', symbol='X')
    store.add('price_alert', 'info', 'b')
    store.add('task_error', 'error', 'c')
    buckets = store.daily(7)
    assert len(buckets) == 7
    today = buckets[-1]
    assert today['total'] == 3
    assert (today['error'], today['warning'], today['info']) == (1, 1, 1)
    assert buckets[0]['total'] == 0


def test_notify_rule_records_symbol(desk):
    ops = desk.ops_view()
    ops.notify_rule('trade_reject', '拒单：ag2612', '保证金不足',
                    symbol='SHFE.ag2612')
    ops.notify_rule('price_alert', '预警：a2701', '到价', symbol='DCE.a2701')
    rows = ops.alert_log.query()['items']
    assert {row['symbol'] for row in rows} == {'SHFE.ag2612', 'DCE.a2701'}


def test_alert_log_command_has_daily(desk):
    desk.ops_view().notify_rule('trade_reject', '拒单', 'x',
                               symbol='SHFE.ag2612')
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_alert_log',
                                        'payload': {}}))
    patch = [row for row in desk.pushes
             if isinstance(row, dict) and row.get('type') == 'ops_alert_log'][-1]
    assert len(patch['daily']) == 14
    assert patch['items'][0]['symbol'] == 'SHFE.ag2612'


def test_alert_log_tool_has_symbol_and_daily(desk):
    desk.ops_view().notify_rule('trade_reject', '拒单', 'x',
                               symbol='SHFE.ag2612')
    out = json.loads(desk_tools.call('desk_ops', {'action': 'alert_log'},
                                     desk))
    assert out['items'][0]['symbol'] == 'SHFE.ag2612'
    assert len(out['daily']) == 14


def test_alert_center_has_replay_and_chart():
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for token in ('data-log-open', 'data-log-row-symbol', 'desk-log-bars',
                  'renderDaily', 'onOpen'):
        assert token in text, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert 'onOpen: (symbol) => {' in app
    assert 'this.openChart(symbol);' in app
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-log-bars' in css and '.desk-log-bar .seg.error' in css

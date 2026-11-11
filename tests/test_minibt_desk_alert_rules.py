"""v1.3.7-92：告警规则（交易回执 / 预警 / 行情停更 / 任务失败）。"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import ALERT_CATALOG, AlertRules

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


@pytest.fixture()
def sent(desk, monkeypatch):
    rows = []

    def fake_send(title, text='', *, level='info'):
        rows.append({'title': title, 'text': text, 'level': level})
        return {'at': 0, 'title': title, 'results': [{'channel': 'xtuis',
                                                      'ok': True}]}

    monkeypatch.setattr(desk.ops_view().notifier, 'send', fake_send)
    return rows


# ------------------------------------------------------------ 规则存储
def test_catalog_defaults():
    ids = [row['id'] for row in ALERT_CATALOG]
    assert ids == ['trade_reject', 'trade_fill', 'price_alert',
                   'data_stale', 'task_error', 'position_risk',
                   'order_stale', 'login_lost', 'strategy_live',
                   'strategy_error', 'strategy_drawdown', 'backtest_done',
                   'optimize_done', 'news_macro', 'news_keyword',
                   'system_error']
    on = {row['id']: row['enabled'] for row in ALERT_CATALOG}
    assert on['trade_reject'] is True and on['data_stale'] is True
    assert on['trade_fill'] is False          # 成交默认不推（长线会嫌吵）
    assert on['system_error'] is False


def test_rules_persist_and_reset(tmp_path):
    path = str(tmp_path / 'alerts.json')
    store = AlertRules(path)
    store.save([{'id': 'trade_fill', 'enabled': True, 'level': 'warning',
                 'min_interval': 60}])
    again = AlertRules(path)
    row = again.get('trade_fill')
    assert row['enabled'] is True and row['level'] == 'warning'
    assert row['min_interval'] == 60
    again.reset()
    assert AlertRules(path).get('trade_fill')['enabled'] is False


def test_rules_ignore_unknown_fields(tmp_path):
    store = AlertRules(str(tmp_path / 'a.json'))
    store.save([{'id': 'nope', 'enabled': True},
                {'id': 'trade_fill', 'level': '瞎写'}])
    assert store.get('nope') is None
    assert store.get('trade_fill')['level'] == 'info'      # 非法等级不改


# ------------------------------------------------------------ notify_rule
def test_notify_rule_respects_enabled(desk, sent):
    ops = desk.ops_view()
    assert ops.notify_rule('trade_reject', '拒单', '保证金不足') is not None
    assert sent[-1]['level'] == 'warning'
    ops.alert_rules.save([{'id': 'trade_fill', 'enabled': True}])
    ops.notify_rule('trade_fill', '成交')
    assert sent[-1]['title'] == '成交'
    ops.alert_rules.save([{'id': 'trade_fill', 'enabled': False}])
    before = len(sent)
    assert ops.notify_rule('trade_fill', '成交') is None
    assert len(sent) == before


def test_notify_rule_dedupes(desk, sent):
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'data_stale', 'min_interval': 600}])
    assert ops.notify_rule('data_stale', '停更 A', key='X') is not None
    assert ops.notify_rule('data_stale', '停更 A', key='X') is None
    assert ops.notify_rule('data_stale', '停更 B', key='Y') is not None


def test_notify_rule_unknown(desk, sent):
    assert desk.ops_view().notify_rule('nope', 'x') is None


# ------------------------------------------------------------ 钩子
def test_trade_hook_reject_and_fill(desk, sent):
    desk._on_trade_alert('reject', {'symbol': 'SHFE.ag2612',
                                    'message': '保证金不足', 'side': 'buy',
                                    'volume': 1})
    assert '拒单' in sent[-1]['title'] and '保证金不足' in sent[-1]['text']
    before = len(sent)
    desk._on_trade_alert('fill', {'symbol': 'SHFE.ag2612'})
    assert len(sent) == before                 # 成交默认关 ✓
    desk.ops_view().alert_rules.save([{'id': 'trade_fill', 'enabled': True}])
    desk._on_trade_alert('fill', {'symbol': 'SHFE.ag2612', 'side': 'sell',
                                  'volume': 2, 'price': 7000})
    assert '成交' in sent[-1]['title']


def test_task_failure_rule_fires(desk, sent):
    ops = desk.ops_view()
    ops.tasks.add('会失败的任务', 60, 'heartbeat', enabled=True)
    ops.tasks.update('会失败的任务',
                     action={'kind': 'tool', 'tool': 'desk_order', 'args': {}})
    ops._run_async(ops.tasks.get('会失败的任务'))       # noqa: SLF001
    titles = [row['title'] for row in sent]
    assert any('定时任务失败' in title for title in titles)


def test_hooks_present_in_source():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert app.count('notify_rule(') >= 3
    assert "'price_alert'" in app and "'data_stale'" in app
    assert '_on_trade_alert' in app and "'trade_reject'" in app
    ops_src = (ROOT / 'minibt' / 'desk' / 'ops.py').read_text(encoding='utf-8')
    assert "'task_error'" in ops_src
    trading = (ROOT / 'minibt' / 'desk' / 'trading.py').read_text(
        encoding='utf-8')
    assert 'set_alert_hook' in trading
    assert "_alert('reject'" in trading and "_alert('fill'" in trading


# ------------------------------------------------------------ 工具 / 界面
def test_desk_ops_alert_rules_tool(desk):
    out = json.loads(desk_tools.call('desk_ops',
                                     {'action': 'alert_rules'}, desk))
    assert out['ok'] is True and out['count'] == 16
    saved = json.loads(desk_tools.call('desk_ops', {
        'action': 'alert_rules', 'mode': 'save',
        'rules': '[{"id":"system_error","enabled":true}]'}, desk))
    assert [row for row in saved['rules']
            if row['id'] == 'system_error'][0]['enabled'] is True
    reset = json.loads(desk_tools.call('desk_ops', {
        'action': 'alert_rules', 'mode': 'reset'}, desk))
    assert [row for row in reset['rules']
            if row['id'] == 'system_error'][0]['enabled'] is False


def test_settings_page_has_rules_table():
    text = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    assert '_renderAlertRules' in text and 'this._renderAlertRules();' in text
    assert 'ops_alert_rules' in text
    assert '告警规则（哪些事要推手机）' in text
    assert '保存规则' in text and '恢复默认' in text
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ops_alert_rules':" in app


# ------------------------------------------------ v1.3.7-93（持仓 / 挂单 / 掉线）
def test_thresholds_default():
    rows = {row['id']: row for row in ALERT_CATALOG}
    assert rows['position_risk']['threshold'] == 5.0
    assert rows['position_risk']['threshold_unit'] == '%'
    assert rows['order_stale']['threshold'] == 10
    assert rows['order_stale']['threshold_unit'] == '分钟'


def test_threshold_persisted(tmp_path):
    path = str(tmp_path / 'a.json')
    store = AlertRules(path)
    store.save([{'id': 'position_risk', 'threshold': 8.5, 'enabled': True}])
    again = AlertRules(path)
    assert again.get('position_risk')['threshold'] == 8.5


def test_position_risk_hook(desk, sent):
    class FakeView:
        def tables(self, **kwargs):
            return {'positions': {'raw': [
                {'symbol': 'SHFE.ag2612', 'side': '多', 'volume': 3,
                 'avg': 12000.0, 'profit': -60000.0, 'value': 100000.0},
                {'symbol': 'DCE.a2701', 'side': '多', 'volume': 1,
                 'avg': 4000.0, 'profit': -10.0, 'value': 40000.0}]}}

    desk.account_view = lambda: FakeView()
    desk.tabs = {'SHFE.ag2612': {'symbol': 'SHFE.ag2612'}}
    desk._risk_at = 0
    desk._check_position_risk()
    assert sent and '持仓风险' in sent[-1]['title']
    assert 'SHFE.ag2612' in sent[-1]['title']
    # 第二条只有 -0.025% → 不该推 ✓
    assert all('DCE.a2701' not in row['title'] for row in sent)


def test_login_lost_hook(desk, sent):
    class FakeTrader:
        stale_seconds = 0.0

        def __init__(self):
            self.ok = True

        def ready(self, symbol=''):
            return self.ok

        def set_alert_hook(self, hook):
            pass

        def poll_orders(self):
            pass

    trader = FakeTrader()
    desk.trading = True
    desk.trading_view = lambda: trader
    desk._conn_at = 0
    desk._conn_state = True
    desk._check_login_state()                  # 正常 → 不推
    before = len(sent)
    trader.ok = False
    desk._conn_at = 0
    desk._check_login_state()
    assert len(sent) == before + 1
    assert '掉线' in sent[-1]['title']


def test_order_stale_alert(desk, sent):
    desk.ops_view().alert_rules.save([{'id': 'order_stale', 'enabled': True,
                                       'threshold': 10}])
    desk._on_trade_alert('stale', {'symbol': 'SHFE.ag2612', 'minutes': 12.5,
                                   'side': 'buy', 'volume': 1,
                                   'price': 7000, 'order_id': 'o1'})
    assert '挂单超时' in sent[-1]['title']
    assert '12.5' in sent[-1]['text']


def test_stale_threshold_injected_into_trading(desk):
    class FakeTrader:
        stale_seconds = 0.0

        def set_alert_hook(self, hook):
            pass

        def poll_orders(self):
            pass

    trader = FakeTrader()
    desk.trading = True
    desk.trading_view = lambda: trader
    desk.ops_view().alert_rules.save([{'id': 'order_stale', 'enabled': True,
                                       'threshold': 10}])
    desk._poll_order_receipts()
    assert trader.stale_seconds == 600.0
    # 关掉 → 注入 0（不提醒）✓
    desk.ops_view().alert_rules.save([{'id': 'order_stale',
                                       'enabled': False}])
    desk._poll_order_receipts()
    assert trader.stale_seconds == 0.0


# ------------------------------------------------ v1.3.7-94（策略 / 资讯 / 静默）
def test_new_rule_defaults():
    rows = {row['id']: row for row in ALERT_CATALOG}
    assert rows['strategy_live']['enabled'] is True
    assert rows['strategy_error']['enabled'] is True
    assert rows['strategy_drawdown']['enabled'] is False        # 默认关 ✓
    assert rows['strategy_drawdown']['threshold'] == 10.0
    assert rows['news_macro']['enabled'] is False               # 默认关 ✓
    assert rows['news_macro']['threshold'] == 15
    assert rows['news_keyword']['enabled'] is False


def test_quiet_and_digest_default_off(tmp_path):
    store = AlertRules(str(tmp_path / 'a.json'))
    settings = store.settings()
    assert settings['quiet']['enabled'] is False
    assert settings['digest']['enabled'] is False
    assert settings['quiet']['start'] == '23:00'


def test_quiet_settings_persist(tmp_path):
    path = str(tmp_path / 'a.json')
    store = AlertRules(path)
    store.save_settings({'quiet': {'enabled': True, 'start': '22:30',
                                   'end': '07:30', 'allow_level': 'warning'},
                         'digest': {'enabled': True, 'at': '15:30'}})
    again = AlertRules(path).settings()
    assert again['quiet']['start'] == '22:30'
    assert again['quiet']['allow_level'] == 'warning'
    assert again['digest']['at'] == '15:30'


def test_quiet_window_cross_midnight():
    from minibt.desk.ops import OpsService
    import time as _time
    stamp = _time.mktime(_time.strptime('2026-11-12 02:00',
                                        '%Y-%m-%d %H:%M'))
    assert OpsService._in_quiet({'start': '23:00', 'end': '08:00'},
                                stamp) is True
    noon = _time.mktime(_time.strptime('2026-11-12 12:00',
                                       '%Y-%m-%d %H:%M'))
    assert OpsService._in_quiet({'start': '23:00', 'end': '08:00'},
                                noon) is False
    day = _time.mktime(_time.strptime('2026-11-12 13:00',
                                      '%Y-%m-%d %H:%M'))
    assert OpsService._in_quiet({'start': '12:00', 'end': '14:00'},
                                day) is True


def test_quiet_suppresses_low_level(desk, sent):
    ops = desk.ops_view()
    ops.alert_rules.save_settings({'quiet': {'enabled': True,
                                             'start': '00:00',
                                             'end': '23:59',
                                             'allow_level': 'error'}})
    assert ops.notify_rule('strategy_live', '策略启动') is None    # 被压
    assert ops.notify_rule('task_error', '任务失败', level='error')
    stats = ops._digest_stats
    assert stats['strategy_live']['quiet'] == 1
    assert stats['task_error']['hit'] == 1


def test_digest_sends_once(desk, sent):
    ops = desk.ops_view()
    ops.alert_rules.save_settings({'quiet': {'enabled': False},
                                   'digest': {'enabled': True, 'at': '00:00'}})
    ops.notify_rule('trade_reject', '拒单')
    record = ops.maybe_digest()
    assert record is not None
    assert '每日告警汇总' in sent[-1]['title']
    assert '拒单' in sent[-1]['text']
    assert ops.maybe_digest() is None           # 一天一次 ✓


def test_digest_off_by_default(desk, sent):
    ops = desk.ops_view()
    ops.notify_rule('trade_reject', '拒单')
    assert ops.maybe_digest() is None
    assert not any('每日告警汇总' in row['title'] for row in sent)


def test_strategy_hooks(desk, sent):
    class FakeLive:
        file = 'C:/x/my_strategy.py'

        def status(self):
            return {'name': 'my_strategy', 'running': True, 'error': ''}

    desk._notify_strategy('start', FakeLive(),
                          {'name': 'my_strategy', 'running': True,
                           'account': '快期模拟', 'account_real': False})
    assert '策略启动' in sent[-1]['title']
    desk._notify_strategy('stop', FakeLive(), {'name': 'my_strategy'})
    assert '策略停止' in sent[-1]['title']
    desk._notify_strategy('start', FakeLive(),
                          {'name': 'bad', 'running': False,
                           'error': '账号未登录'})
    assert '启动失败' in sent[-1]['title']
    assert '账号未登录' in sent[-1]['text']


def test_strategy_error_poll_dedupes(desk, sent):
    desk.strategy_live_items = lambda: [
        {'name': 'my', 'file': 'f.py', 'running': False, 'error': 'boom'}]
    desk._strat_at = 0
    desk._strat_seen = {}
    desk._check_strategy_errors()
    assert '策略异常' in sent[-1]['title']
    before = len(sent)
    desk._strat_at = 0
    desk._check_strategy_errors()
    assert len(sent) == before                 # 同一个错误不重复推 ✓


def test_ops_alert_rules_settings_tool(desk):
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'alert_rules', 'mode': 'settings',
        'quiet': '{"enabled": true, "start": "21:00", "end": "06:00"}',
        'digest': '{"enabled": true, "at": "15:00"}'}, desk))
    assert out['ok'] is True
    assert out['settings']['quiet']['start'] == '21:00'
    assert out['settings']['digest']['at'] == '15:00'


def test_ui_hides_four_extension_entries():
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    start = app.index('export class DeskApp')
    assert '四个扩展入口暂时关闭' in app
    assert '四个扩展页暂时不进命令面板' in app
    # 定时任务入口保留 ✓
    assert "label: '定时任务（工具 / AI / 内置）'" in app
    assert "{ label: '定时任务', hint: '每 N 秒 / 每天 HH:MM / 前置任务'" in app


def test_tool_doc_is_vertical_layout():
    suite = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    assert 'desk-suite-doc-head' in suite
    assert 'desk-suite-doc-line' in suite
    assert 'desk-suite-help-name' in suite
    assert 'desk-suite-help-desc' in suite
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-suite-form .desk-suite-doc' in css
    assert 'grid-column: 1 / -1' in css


# ------------------------------------------------ v1.3.7-96（回测 / 优化完成 + 分组）
def test_backtest_rules_default_off():
    rows = {row['id']: row for row in ALERT_CATALOG}
    assert rows['backtest_done']['enabled'] is False
    assert rows['optimize_done']['enabled'] is False
    assert rows['backtest_done']['source'] == '策略'


def test_notify_lab_done_backtest(desk, sent):
    class FakeLab:
        mode = 'backtest'
        status = 'ready'
        file = 'C:/x/my_strategy.py'
        optimization_rows = []
        strategies = [{'metrics': {'total_return': 0.32,
                                   'sharpe_ratio': 1.4}}]

    desk.notify_lab_done(FakeLab())         # 默认关 → 不推 ✓
    assert not [row for row in sent if '回测完成' in row['title']]
    desk.ops_view().alert_rules.save([{'id': 'backtest_done',
                                       'enabled': True}])
    desk.notify_lab_done(FakeLab())
    assert '回测完成' in sent[-1]['title']
    assert 'my_strategy.py' in sent[-1]['title']
    assert 'total_return=0.32' in sent[-1]['text']


def test_notify_lab_done_optimize(desk, sent):
    class FakeLab:
        mode = 'optimize'
        status = 'ready'
        file = 'C:/x/opt.py'
        optimization_rows = [{'params': {'fast': 5}}, {'params': {'fast': 9}}]
        strategies = [{'metrics': {}}]

    desk.ops_view().alert_rules.save([{'id': 'optimize_done',
                                       'enabled': True}])
    desk.notify_lab_done(FakeLab())
    assert '参数优化完成' in sent[-1]['title']
    assert '共 2 组' in sent[-1]['text']


def test_notify_lab_done_error(desk, sent):
    class FakeLab:
        mode = 'backtest'
        status = 'error'
        file = 'C:/x/bad.py'
        error = '数据缺失'

    desk.notify_lab_done(FakeLab())         # system_error 默认关
    assert not [row for row in sent if '回测失败' in row['title']]
    desk.ops_view().alert_rules.save([{'id': 'system_error',
                                       'enabled': True}])
    desk.notify_lab_done(FakeLab())
    assert '回测失败' in sent[-1]['title']
    assert '数据缺失' in sent[-1]['text']


def test_lab_hook_wired_in_strategy_lab():
    src = (ROOT / 'minibt' / 'desk' / 'strategy_lab.py').read_text(
        encoding='utf-8')
    assert '_notify_done' in src
    assert src.count('self._notify_done()') >= 3
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'def notify_lab_done' in app


def test_settings_rules_grouped_by_source():
    text = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    assert '按来源分组' in text
    assert 'const order: string[] = [];' in text
    assert '`${group}（${items.length}）`' in text

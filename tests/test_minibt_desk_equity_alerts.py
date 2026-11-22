"""v1.3.7-95：账户净值曲线（equity.db）+ 资讯关键词自定义。"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import AlertRules, EquityStore

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
        return {'at': 0, 'title': title, 'results': []}

    monkeypatch.setattr(desk.ops_view().notifier, 'send', fake_send)
    return rows


def _feed(store, key, values):
    store.SAMPLE_GAP = 0
    for value in values:
        store._last.clear()                       # noqa: SLF001
        store.add(key, value, value)


# ------------------------------------------------------------ 净值存储
def test_equity_store_series_and_stats(tmp_path):
    store = EquityStore(str(tmp_path / 'equity.db'))
    _feed(store, 'acc', (100000, 104000, 98000, 102000))
    rows = store.series('acc', days=30)
    assert [row['equity'] for row in rows] == [100000, 104000, 98000, 102000]
    stats = store.stats('acc', days=30)
    assert stats['points'] == 4
    assert stats['peak'] == 104000
    assert stats['current'] == 102000
    assert stats['drawdown'] == pytest.approx(1.92, abs=0.02)
    assert stats['max_drawdown'] == pytest.approx(5.77, abs=0.02)
    assert len(stats['points_list']) == 4


def test_equity_store_empty(tmp_path):
    stats = EquityStore(str(tmp_path / 'e.db')).stats('nobody')
    assert stats['points'] == 0 and stats['peak'] == 0.0
    assert stats['points_list'] == []


def test_equity_sample_gap(tmp_path):
    store = EquityStore(str(tmp_path / 'e.db'))
    assert store.add('a', 100.0) is True
    assert store.add('a', 101.0) is False         # 55 秒内不再记 ✓
    assert store.stats('a')['points'] == 1


# ------------------------------------------------------------ 采样 / 回撤告警
def test_sample_equity_from_account(desk):
    class FakeView:
        def summary(self, symbol=''):
            return {'account': '快期模拟',
                    'values': {'balance': 100000.0, 'float_profit': 500.0}}

    desk.account_view = lambda: FakeView()
    desk.tabs = {'SHFE.ag2612': {}}
    desk._eq_at = 0
    desk._sample_equity()
    ops = desk.ops_view()
    assert ops.equity_keys == ['快期模拟']
    assert ops.equity.stats('快期模拟')['points'] == 1


def test_drawdown_alert_uses_series(desk, sent):
    ops = desk.ops_view()
    _feed(ops.equity, '快期模拟', (110000, 88000))
    ops.equity_keys = ['快期模拟']
    ops.alert_rules.save([{'id': 'strategy_drawdown', 'enabled': True,
                           'threshold': 10}])
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert '回撤' in sent[-1]['title']
    assert '20.0%' in sent[-1]['text']


def test_drawdown_below_threshold_silent(desk, sent):
    ops = desk.ops_view()
    _feed(ops.equity, '快期模拟', (100000, 99000))
    ops.equity_keys = ['快期模拟']
    ops.alert_rules.save([{'id': 'strategy_drawdown', 'enabled': True,
                           'threshold': 10}])
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert not any('回撤' in row['title'] for row in sent)


# ------------------------------------------------------------ 关键词
def test_keywords_default_empty(tmp_path):
    assert AlertRules(str(tmp_path / 'a.json')).settings()['keywords'] == []


def test_keywords_saved_and_cleaned(tmp_path):
    path = str(tmp_path / 'a.json')
    store = AlertRules(path)
    store.save_settings({'keywords': '降息，抛储, 降息 , 碳酸锂'})
    words = AlertRules(path).settings()['keywords']
    assert words == ['降息', '抛储', '碳酸锂']       # 去重 + 中文逗号 ✓
    store.save_settings({'keywords': ['x']})        # 太短的不收
    assert AlertRules(path).settings()['keywords'] == []


def test_keyword_alert_matches_news(desk, sent, monkeypatch):
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'news_keyword', 'enabled': True}])
    ops.alert_rules.save_settings({'keywords': ['降息']})
    from minibt.desk import info as info_mod
    rows = [{'id': 'n1', 'title': '央行宣布降息 25 个基点', 'source': '财新',
             'published': '10:00'},
            {'id': 'n2', 'title': '无关新闻'}]
    monkeypatch.setattr(info_mod, 'news', lambda *a, **k: {'items': rows})
    # v1.3.7-102：首扫只做基线（旧新闻不推）→ 先跑一次把 n1/n2 记进 seen ✓
    desk._news_at = 0
    desk._watch_alerts()
    rows.append({'id': 'n3', 'title': '刚刚：央行再次降息', 'source': '财新',
                 'published': '10:30'})
    desk._news_at = 0
    desk._watch_alerts()
    assert any('关键词「降息」' in row['title'] for row in sent)
    before = len(sent)
    desk._news_at = 0
    desk._watch_alerts()                          # 同一条不重复推 ✓
    assert len(sent) == before


def test_keyword_rate_limited(desk, sent, monkeypatch):
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'news_keyword', 'enabled': True}])
    ops.alert_rules.save_settings({'keywords': ['降息']})
    rows: list = []
    from minibt.desk import info as info_mod
    monkeypatch.setattr(info_mod, 'news', lambda *a, **k: {'items': rows})
    desk._news_at = 0
    desk._watch_alerts()                           # 首个空扫描 = 基线 ✓
    rows.extend({'id': f'n{i}', 'title': f'降息消息 {i}'} for i in range(6))
    desk._news_at = 0
    desk._watch_alerts()
    hits = [row for row in sent if '关键词「降息」' in row['title']]
    assert len(hits) == 3                          # 10 分钟内最多 3 条 ✓


# ------------------------------------------------------------ 命令 / 界面
def test_ops_equity_command(desk):
    ops = desk.ops_view()
    _feed(ops.equity, '快期模拟', (100000, 108000))
    ops.equity_keys = ['快期模拟']
    desk.handle('desk_~_' + json.dumps({'cmd': 'ops_equity',
                                        'payload': {}}))
    patch = [item for item in desk.pushes
             if isinstance(item, dict)
             and item.get('type') == 'ops_equity'][-1]
    assert patch['key'] == '快期模拟'
    assert patch['stats']['points'] == 2


def test_snapshot_has_equity_and_settings(desk):
    snap = desk.ops_view().snapshot()
    assert 'equity' in snap and 'alert_settings' in snap
    assert 'keywords' in snap['alert_settings']


def test_settings_page_has_curve_and_keywords():
    text = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    for token in ('_renderEquityCurve', 'desk-settings-equity', 'setEquity',
                  'ops_equity', '资讯关键词', '保存关键词'):
        assert token in text, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ops_equity':" in app
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-settings-equity' in css


def test_desk_ops_equity_tool(desk):
    ops = desk.ops_view()
    _feed(ops.equity, 'acc', (100000, 104000, 98000))
    ops.equity_keys = ['acc']
    out = json.loads(desk_tools.call('desk_ops', {'action': 'equity'}, desk))
    assert out['ok'] is True
    assert out['key'] == 'acc'
    assert out['stats']['peak'] == 104000.0
    assert out['stats']['drawdown'] == pytest.approx(5.77, abs=0.02)
    assert len(out['points']) == 3

"""v1.3.7-102：告警只认「本次运行里即时发生」的事件（不啃历史数据）。"""
from __future__ import annotations

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.push = lambda patch: None
    return instance


@pytest.fixture()
def sent(desk, monkeypatch):
    rows = []

    def fake_send(title, text='', *, level='info'):
        rows.append({'title': title, 'text': text, 'level': level})
        return {'results': [{'channel': 'xtuis', 'ok': True}]}

    monkeypatch.setattr(desk.ops_view().notifier, 'send', fake_send)
    return rows


# ------------------------------------------------------------ 资讯关键词
def test_keyword_first_scan_is_baseline(desk, sent, monkeypatch):
    """缓存里的旧新闻只在首扫时入基线，**不推**；之后新出现的才推 ✓"""
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'news_keyword', 'enabled': True}])
    ops.alert_rules.save_settings({'keywords': ['降息']})
    from minibt.desk import info as info_mod
    rows = [{'id': 'old1', 'title': '旧闻：降息预期'}]
    monkeypatch.setattr(info_mod, 'news', lambda *a, **k: {'items': rows})
    desk._news_at = 0
    desk._watch_alerts()
    assert sent == []                      # 历史新闻不推 ✓
    rows.append({'id': 'new1', 'title': '刚刚：央行降息 25bp'})
    desk._news_at = 0
    desk._watch_alerts()
    assert any('关键词「降息」' in row['title'] for row in sent)


def test_symbol_news_first_scan_is_baseline(desk, sent, monkeypatch):
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'news_keyword', 'enabled': True}])
    desk._watch_symbols = lambda: ['SSE.600519']
    rows = [{'id': 'old1', 'title': '茅台旧闻', 'symbol': 'SSE.600519'}]
    from minibt.desk import info as info_mod
    monkeypatch.setattr(info_mod, 'news', lambda *a, **k: {'items': rows})
    desk._news_at = 0
    desk._watch_alerts()
    assert sent == []
    rows.append({'id': 'new1', 'title': '茅台公告', 'symbol': 'SSE.600519'})
    desk._news_at = 0
    desk._watch_alerts()
    assert any('茅台公告' in row['title'] for row in sent)


def test_macro_stale_cache_not_pushed(desk, sent, monkeypatch):
    """财经日历缓存过期 → 不当即时事件 ✓"""
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'news_macro', 'enabled': True,
                           'threshold': 60}])
    import time as _time
    today = _time.strftime('%Y-%m-%d')
    soon = _time.strftime('%H:%M', _time.localtime(_time.time() + 600))
    items = [{'id': 'e1', 'day': today, 'time': soon, 'region': '美国',
              'event': '初请失业金', 'importance': 2}]
    from minibt.desk import info as info_mod
    for stale in (True, False):
        monkeypatch.setattr(info_mod, 'calendar',
                            lambda **k: {'items': items, 'stale': stale})
        desk._news_at = 0
        before = len(sent)
        desk._watch_alerts()
        if stale:
            assert len(sent) == before        # 过期缓存不推 ✓
        else:
            assert any('宏观临近' in row['title'] for row in sent)


# ------------------------------------------------------------ 回撤
def _feed(store, key, values):
    store.SAMPLE_GAP = 0
    for value in values:
        store._last.clear()                  # noqa: SLF001
        store.add(key, value, value)


def test_drawdown_needs_samples_from_this_run(desk, sent):
    """只有历史峰值、今天没采样 → 不算事件，不推 ✓"""
    ops = desk.ops_view()
    ops.alert_rules.save([{'id': 'strategy_drawdown', 'enabled': True,
                           'threshold': 10}])
    ops.equity_keys = ['acc']
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert sent == []
    _feed(ops.equity, 'acc', (110000, 88000))
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert '回撤' in sent[-1]['title']


def test_drawdown_fires_once_per_crossing(desk, sent):
    ops = desk.ops_view()
    # 去重窗口设 0：这里只验"每次破阈值推一次"的抖动逻辑（默认 1 小时）✓
    ops.alert_rules.save([{'id': 'strategy_drawdown', 'enabled': True,
                           'threshold': 10, 'min_interval': 0}])
    ops.equity_keys = ['acc']
    _feed(ops.equity, 'acc', (110000, 88000))
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    first = len(sent)
    desk._dd_at = 0
    desk._check_strategy_drawdown()          # 还在阈值上 → 不重复 ✓
    assert len(sent) == first
    # 回到阈值以下再破 → 再推一次
    _feed(ops.equity, 'acc', (100000,))
    ops.equity._last.clear()                 # noqa: SLF001
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert len(sent) == first                 # 已回到阈值下，只清状态 ✓
    _feed(ops.equity, 'acc', (120000, 90000))
    desk._dd_at = 0
    desk._check_strategy_drawdown()
    assert len(sent) == first + 1


# ------------------------------------------------------------ 持仓风险
def test_position_risk_fires_once(desk, sent):
    class FakeView:
        def tables(self, **kwargs):
            return {'positions': {'raw': [
                {'symbol': 'SHFE.ag2612', 'side': '多', 'volume': 3,
                 'avg': 12000.0, 'profit': -80000.0, 'value': 100000.0}]}}

    desk.account_view = lambda: FakeView()
    desk.tabs = {'SHFE.ag2612': {}}
    desk._risk_at = 0
    desk._check_position_risk()
    first = len(sent)
    assert first == 1
    desk._risk_at = 0
    desk._check_position_risk()              # 仍在阈值上 → 不刷屏 ✓
    assert len(sent) == first


# ------------------------------------------------------------ 策略启停
def test_shutdown_stop_is_silent(desk, sent):
    """关窗口停策略 ≠ 用户操作 → 不推「策略停止」✓"""
    class FakeLive:
        file = 'x.py'

        def stop(self):
            pass

        def status(self):
            return {'name': 'x', 'running': False, 'error': ''}

    desk.trading = True
    desk._strategy_lives = {'x': FakeLive()}
    desk.stop_strategy_live()
    assert not [row for row in sent if '策略停止' in row['title']]


def test_user_stop_still_notifies(desk, sent):
    class FakeLive:
        file = 'y.py'

        def stop(self):
            pass

        def status(self):
            return {'name': 'y', 'running': False, 'error': ''}

    desk.trading = True
    desk._strategy_lives = {'y': FakeLive()}
    desk._on_strategy_live_stop({'file': 'y.py'})
    assert any('策略停止' in row['title'] for row in sent)


def test_internal_restart_does_not_notify(desk, sent):
    """切账户时的自动重启不是用户操作 → 不推 ✓"""
    class FakeLive:
        running = True

        def stop(self):
            pass

        def start(self):
            return {'running': True}

    desk._strategy_lives = {'z': FakeLive()}
    desk._restart_strategy_live_all()
    assert sent == []

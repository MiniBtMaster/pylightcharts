"""资讯 / 财经日历（P0，v1.3.7-62）。

用户 2026-11-08 确认的设计：

* AkShare 做成**可选依赖**（`pip install minibt[news]`）；
* 只用封装库，不裸爬；主接口 + 备接口；
* 只落库「标题 + 时间 + 来源 + 链接 + 短摘要」；
* 首页事件日历用真实数据（取不到回退静态，不白屏）；
* MCP：`desk_news` / `desk_calendar`（只读）。
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import time

import pytest

from minibt.desk import tools, user_prefs
from minibt.desk.info import cache, providers, service

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, 'DB_FILE', str(tmp_path / 'info.db'))
    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        str(tmp_path / 'prefs.json'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    yield


class FakeFrame:
    """够用的 DataFrame 替身（`len / to_dict('records')` ✓）"""

    def __init__(self, rows):
        self.rows = list(rows)

    def __len__(self):
        return len(self.rows)

    def to_dict(self, orient='records'):
        assert orient == 'records'
        return [dict(row) for row in self.rows]


# ------------------------------------------------------------ 缓存
def test_cache_roundtrip_and_search():
    saved = cache.save_news([
        {'id': 'a', 'kind': 'flash', 'symbol': '', 'title': '降准落地',
         'summary': '央行宣布降准 0.5 个百分点', 'source': '新浪财经',
         'url': 'https://example.com/a', 'published': '2026-11-10 09:00'},
        {'id': 'b', 'kind': 'flash', 'symbol': '', 'title': '美联储讲话',
         'summary': '鲍威尔偏鹰', 'source': '新浪财经', 'url': '',
         'published': '2026-11-10 08:00'},
    ])
    assert saved == 2
    rows = cache.load_news('flash', limit=10)
    assert [row['id'] for row in rows] == ['a', 'b']       # 最新在前 ✓
    assert cache.search_news('降准')[0]['id'] == 'a'
    assert cache.load_news('market') == []


def test_cache_calendar_and_ttl():
    cache.save_calendar([
        {'id': 'e1', 'day': '2026-11-10', 'time': '20:30', 'region': '美国',
         'event': '初请失业金', 'actual': '22', 'forecast': '21',
         'previous': '20', 'importance': 2},
    ])
    rows = cache.load_calendar(['2026-11-10'])
    assert rows[0]['event'] == '初请失业金'
    assert cache.fresh('calendar:x', 'calendar') is False     # 没标记 → 不新鲜
    cache.meta_set('calendar:x', '1')
    assert cache.fresh('calendar:x', 'calendar') is True
    stats = cache.stats()
    assert stats['calendar'] == 1 and stats['news'] == 0
    cache.clear()
    assert cache.load_calendar() == []


# ------------------------------------------------------------ 归一化
def test_fetch_calendar_normalizes_rows(monkeypatch):
    # ★ 日期用**今天**（fetch_calendar 按 offset 生成日期，写死会过期 ✗）
    today = _dt.date.today().isoformat()
    rows = [{'日期': today, '时间': '20:30', '地区': '美国',
             '事件': '美国初请失业金人数', '公布': '22', '预期': '21',
             '前值': '20', '重要性': 2},
            {'日期': '2026-11-10', '时间': '', '地区': '',
             '事件': '', '公布': '', '预期': '', '前值': '',
             '重要性': 0}]
    monkeypatch.setattr(providers, '_call',
                        lambda name, **kwargs: FakeFrame(rows))
    items = providers.fetch_calendar(days=1)
    assert len(items) == 1                       # 空事件被丢掉 ✓
    item = items[0]
    assert item['day'] == today
    assert item['importance'] == 2
    assert item['forecast'] == '21'
    assert item['id']                            # 去重 id ✓


def test_fetch_news_flash_and_symbol(monkeypatch):
    def fake_call(name, *args, **kwargs):
        if name == 'stock_info_global_sina':
            return FakeFrame([{'时间': '2026-11-10 10:00', '内容': '沪指翻红'}])
        if name == 'stock_news_em':
            assert kwargs.get('symbol') == '600519'
            return FakeFrame([{'新闻标题': '茅台三季报', '新闻内容': '净利增长',
                               '发布时间': '2026-11-10 08:00',
                               '文章来源': '东方财富',
                               '新闻链接': 'https://x/y'}])
        raise AssertionError(name)

    monkeypatch.setattr(providers, '_call', fake_call)
    items = providers.fetch_news('flash', limit=5)
    assert items[0]['title'] == '沪指翻红'
    assert items[0]['published'] == '2026-11-10 10:00'
    stock = providers.fetch_news('symbol', '600519', limit=5)
    assert stock[0]['title'] == '茅台三季报'
    assert stock[0]['symbol'] == '600519'
    with pytest.raises(providers.ProviderError):
        providers.fetch_news('symbol', '')


def test_provider_error_when_akshare_missing(monkeypatch):
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': False, 'version': '',
                                 'error': 'ModuleNotFoundError',
                                 'hint': 'pip install minibt[news]'})

    def boom(name, **kwargs):
        raise providers.ProviderError('没装 AkShare')
    monkeypatch.setattr(providers, '_call', boom)
    with pytest.raises(providers.ProviderError):
        providers.fetch_calendar(days=1)
    assert providers.akshare_info()['installed'] is False


# ------------------------------------------------------------ 服务
def test_service_home_events_fallback_and_real(monkeypatch):
    monkeypatch.setattr(service, '_dt', service._dt)   # 保持真实日期
    # 缓存空 → 回退静态两条 ✓
    events = service.home_events()
    assert events and events[0]['text'].startswith('美国初请')
    today = service._dt.date.today().isoformat()
    cache.save_calendar([
        {'id': 'h1', 'day': today, 'time': '20:30', 'region': '美国',
         'event': '初请失业金', 'actual': '', 'forecast': '21',
         'previous': '20', 'importance': 2},
        {'id': 'h2', 'day': today, 'time': '00:00', 'region': '日本',
         'event': '例行调查', 'actual': '', 'forecast': '',
         'previous': '', 'importance': 0},
    ])
    events = service.home_events(2)
    assert events[0]['text'].endswith('初请失业金')
    assert events[0]['tone'] == 'amber'          # 高重要性 → 琥珀色 ✓


def test_service_news_cache_first(monkeypatch):
    cache.save_news([{'id': 'n1', 'kind': 'flash', 'symbol': '',
                      'title': '旧快讯', 'summary': '', 'source': 'x',
                      'url': '', 'published': '2026-11-10 09:00'}])
    data = service.news('flash', limit=5)
    assert data['count'] == 1 and data['stale'] is True
    cache.meta_set('flash', '1')
    assert service.news('flash', limit=5)['stale'] is False


def test_refresh_writes_cache_and_calls_back(monkeypatch):
    day = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    monkeypatch.setattr(providers, 'fetch_calendar',
                        lambda days: [{'id': 'c1', 'day': day,
                                       'time': '20:30', 'region': '美国',
                                       'event': '初请', 'actual': '',
                                       'forecast': '1', 'previous': '0',
                                       'importance': 2}])
    done = {}
    service.refresh_calendar(days=1, on_done=lambda p: done.setdefault('p', p))
    for _ in range(200):        # 限速 0.6s + 两次抓取 → 最多等 4 秒
        if done:
            break
        time.sleep(0.02)
    assert done['p']['result']['saved'] == 1
    assert cache.load_calendar([day])[0]['event'] == '初请'


# ------------------------------------------------------------ MCP 工具
class FakeDesk:
    def __init__(self):
        self.sent = []

    def push(self, payload):
        self.sent.append(payload)


def test_news_and_calendar_registered_readonly():
    assert 'desk_news' in tools.NAMES
    assert 'desk_calendar' in tools.NAMES
    assert 'desk_news' in tools.READONLY
    assert 'desk_calendar' in tools.READONLY


def test_desk_news_actions(monkeypatch):
    desk = FakeDesk()
    monkeypatch.setattr(providers, 'fetch_news',
                        lambda kind, symbol, limit: [{
                            'id': 'x1', 'kind': kind, 'symbol': symbol,
                            'title': '降准落地', 'summary': '央行降准',
                            'source': '新浪财经', 'url': 'https://x',
                            'published': '2026-11-10 09:00'}])
    data = json.loads(tools.call('desk_news', {
        'action': 'latest', 'limit': 3, 'refresh': True}, desk))
    assert data['ok'] is True
    assert data['items'][0]['title'] == '降准落地'
    assert data['items'][0]['time'] == '2026-11-10 09:00'
    # search 只搜缓存
    found = json.loads(tools.call('desk_news',
                                  {'action': 'search', 'query': '降准'}, desk))
    assert found['count'] == 1
    # 个股新闻必须有 symbol
    bad = json.loads(tools.call('desk_news', {'action': 'symbol'}, desk))
    assert bad['ok'] is False and 'symbol' in bad['error']


def test_desk_calendar_actions(monkeypatch):
    desk = FakeDesk()
    today = service._dt.date.today().isoformat()
    monkeypatch.setattr(providers, 'fetch_calendar',
                        lambda days: [{
                            'id': 'c1', 'day': today, 'time': '20:30',
                            'region': '美国', 'event': '初请失业金',
                            'actual': '', 'forecast': '21',
                            'previous': '20', 'importance': 2}])
    data = json.loads(tools.call('desk_calendar', {
        'action': 'today', 'limit': 10, 'refresh': True}, desk))
    assert data['ok'] is True
    assert data['count'] == 1
    assert data['items'][0]['importance'] == 2
    assert data['days'] == [today]
    bad = json.loads(tools.call('desk_calendar', {'action': 'day'}, desk))
    assert bad['ok'] is False


# ------------------------------------------------------------ 后端接线
def test_app_home_events_use_info_and_push(monkeypatch):
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('    def home_events(self) -> List[dict]:', 1)[1] \
        .split('    def _on_info_calendar_done', 1)[0]
    assert '_info.home_events(2)' in block
    assert 'refresh_calendar' in block
    assert 'fallback' in block                     # 取不到要有兜底 ✓
    for command in ('info_news', 'info_calendar', 'info_status', 'info_clear'):
        assert f"'{command}': self._on_{command}" in app


# ------------------------------------------------------------ 前端接线
def test_info_page_and_entries():
    page = (JSLIB / 'info-page.ts').read_text(encoding='utf-8')
    for token in ('info_news', 'info_calendar', "KIND_LABEL",
                  'showMenu', 'pi_send'):
        assert token in page, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert 'this.openInfo()' in app
    assert "case 'info_news':" in app
    assert 'setEvents?.(' in app                   # 首页事件日历跟着刷新 ✓
    settings = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    assert "'info-sources'" in settings
    assert 'setInfoStatus' in settings
    home = (JSLIB / 'home-page.ts').read_text(encoding='utf-8')
    assert 'setEvents(events' in home

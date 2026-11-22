"""资讯 P2：富途优先的个股资料 / 财务 / 公告 / 资金流 + FTS5 + 事件标记（v1.3.7-64）。

用户 2026-11-08：「优先使用富途获取信息，如果用户没连接富途才使用 AkShare」。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools, user_prefs
from minibt.desk.info import cache, futu_source, providers, service

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
    def __init__(self, rows):
        self.rows = list(rows)
        self.empty = not self.rows

    def __len__(self):
        return len(self.rows)

    def to_dict(self, orient='records'):
        assert orient == 'records'
        return [dict(row) for row in self.rows]


class FakeCtx:
    """富途 OpenQuoteContext 替身 ✓"""

    def __init__(self, snapshot=None, capital=None, flow=None, ret=0):
        self._snapshot = snapshot or {}
        self._capital = capital or {}
        self._flow = flow or {}
        self.ret = ret

    def get_market_snapshot(self, codes):
        rows = [self._snapshot[code] for code in codes
                if code in self._snapshot]
        return self.ret, FakeFrame(rows)

    def get_capital_distribution(self, code):
        return self.ret, FakeFrame([self._capital] if self._capital else [])

    def get_capital_flow(self, code):
        return self.ret, FakeFrame([self._flow] if self._flow else [])


class FakeDesk:
    def __init__(self, ctx=None):
        if ctx is not None:
            class Feed:
                api = type('Api', (), {'_ctx': ctx})()
            self.stocks = Feed()
        else:
            self.stocks = None


# ------------------------------------------------------------ 富途适配
def test_futu_snapshot_normalizes():
    ctx = FakeCtx(snapshot={
        'SH.600519': {'code': 'SH.600519', 'name': '贵州茅台',
                      'last_price': 1700.5, 'pe_ratio': 28.3,
                      'pb_ratio': 9.1, 'dividend_ratio_ttm': 1.6,
                      'total_market_val': 2.1e12, 'lot_size': 100,
                      'suspension': False},
    })
    data = futu_source.snapshot(FakeDesk(ctx), 'SSE.600519')
    assert data['source'] == 'futu'
    assert data['name'] == '贵州茅台'
    labels = {item['label']: item['value'] for item in data['items']}
    assert labels['市盈率'] == 28.3
    assert labels['每手'] == 100
    # 没有富途连接 → 空字典（调用方降级 ✓）
    assert futu_source.snapshot(FakeDesk(), 'SSE.600519') == {}
    assert futu_source.available(FakeDesk()) is False


def test_futu_capital_flow():
    ctx = FakeCtx(capital={'capital_in_super': 1.2e7,
                           'capital_out_super': 8.0e6},
                  flow={'inflow': 4.0e6})
    data = futu_source.capital_flow(FakeDesk(ctx), 'SSE.600519')
    assert data['source'] == 'futu'
    labels = {item['label']: item['value'] for item in data['items']}
    assert labels['超大单流入'] == 12000000.0
    assert data['inflow'] == 4000000.0


def test_stock_info_prefers_futu(monkeypatch):
    ctx = FakeCtx(snapshot={'SH.600519': {'code': 'SH.600519',
                                          'name': '贵州茅台',
                                          'pe_ratio': 28.3}},
                  flow={'inflow': 1.0})
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': True, 'version': '1.18.64'})
    monkeypatch.setattr(providers, 'fetch_stock_financials',
                        lambda symbol: {'items': [{'name': '净利',
                                                   'values': {'20260930': '1'}}],
                                        'periods': ['20260930']})
    monkeypatch.setattr(providers, 'fetch_notices',
                        lambda symbol: {'items': []})
    data = service.stock_info('SSE.600519', FakeDesk(ctx))
    assert data['ok'] is True and data['futu'] is True
    assert data['profile']['source'] == 'futu'
    assert data['profile']['name'] == '贵州茅台'
    assert data['capital']['inflow'] == 1.0
    assert data['financials']['periods'] == ['20260930']


def test_stock_info_falls_back_to_akshare(monkeypatch):
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': True, 'version': '1.18.64'})
    monkeypatch.setattr(providers, 'fetch_profile',
                        lambda symbol: {'symbol': symbol,
                                        'items': [{'label': '名称',
                                                   'value': '茅台'}]})
    monkeypatch.setattr(providers, 'fetch_stock_financials',
                        lambda symbol: {'items': [], 'periods': []})
    monkeypatch.setattr(providers, 'fetch_notices',
                        lambda symbol: {'items': []})
    data = service.stock_info('SSE.600519', FakeDesk())
    assert data['futu'] is False
    assert data['profile']['items'][0]['value'] == '茅台'
    assert '富途没连上' in data['profile_note']
    assert 'capital' not in data


# ------------------------------------------------------------ AkShare 兜底
def test_is_stock_and_codes():
    assert providers.is_stock('SSE.600519') is True
    assert providers.is_stock('HK.00700') is True
    assert providers.is_stock('SHFE.ag2612') is False
    assert providers.stock_code('SSE.600519') == '600519'


def test_fetch_stock_financials(monkeypatch):
    monkeypatch.setattr(providers, '_call', lambda name, **kwargs: FakeFrame([
        {'选项': '盈利能力', '指标': '净资产收益率',
         '20260930': 12.5, '20260630': 8.1},
        {'选项': '盈利能力', '指标': '销售毛利率',
         '20260930': 91.2, '20260630': 90.0},
    ]))
    data = providers.fetch_stock_financials('SSE.600519', limit=2)
    assert data['periods'] == ['20260930', '20260630']
    assert data['items'][0]['name'] == '净资产收益率'
    assert data['items'][0]['values']['20260930'] == '12.5'


def test_fetch_notices_filters_symbol(monkeypatch):
    def fake_call(name, **kwargs):
        return FakeFrame([
            {'代码': '600519', '名称': '贵州茅台', '公告标题': '三季报',
             '公告类型': '定期报告', '公告日期': '2026-11-09'},
            {'代码': '000001', '名称': '平安银行', '公告标题': '其它',
             '公告类型': '其它', '公告日期': '2026-11-09'},
        ])

    monkeypatch.setattr(providers, '_call', fake_call)
    data = providers.fetch_notices('SSE.600519')
    assert len(data['items']) == 1
    assert data['items'][0]['title'] == '三季报'


# ------------------------------------------------------------ FTS5 搜索
def test_fts_search_three_chars_and_short_fallback():
    cache.save_news([
        {'id': 'a', 'kind': 'flash', 'title': '央行宣布降准 0.5 个百分点',
         'summary': '释放长期资金约一万亿', 'source': '新浪',
         'published': '2026-11-10 09:00'},
        {'id': 'b', 'kind': 'flash', 'title': '美联储主席讲话',
         'summary': '偏鹰', 'source': '新浪', 'published': '2026-11-10 08:00'},
    ])
    # 3 个字 → FTS5 trigram
    assert [row['id'] for row in cache.search_news('央行宣布')] == ['a']
    # 2 个字 → 自动退回 LIKE ✓
    assert [row['id'] for row in cache.search_news('降准')] == ['a']
    assert [row['id'] for row in cache.search_news('美联储')] == ['b']


# ------------------------------------------------------------ 工具
def test_fundamentals_stock_payload(monkeypatch):
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': True, 'version': '1.18.64'})
    ctx = FakeCtx(snapshot={'SH.600519': {'code': 'SH.600519',
                                          'name': '贵州茅台',
                                          'pe_ratio': 28.3}},
                  flow={'inflow': 1.0})
    monkeypatch.setattr(providers, 'fetch_stock_financials',
                        lambda symbol: {'items': [], 'periods': []})
    monkeypatch.setattr(providers, 'fetch_notices',
                        lambda symbol: {'items': []})
    data = json.loads(tools.call('desk_fundamentals', {
        'symbol': 'SSE.600519'}, FakeDesk(ctx)))
    assert data['ok'] is True
    assert data['kind'] == 'stock'
    assert data['futu'] is True
    assert data['profile']['name'] == '贵州茅台'


def test_news_search_uses_cache():
    cache.save_news([{'id': 'n1', 'kind': 'flash', 'title': '原油大涨',
                      'summary': '', 'source': '新浪',
                      'published': '2026-11-10 09:00'}])
    data = json.loads(tools.call('desk_news', {
        'action': 'search', 'query': '原油'}, FakeDesk()))
    assert data['count'] == 1


# ------------------------------------------------------------ 前端
def test_symbol_info_uses_financial_widgets():
    """v1.3.7-67：标的资讯页用 pylightcharts 金融小插件拼（4 段）✓"""
    page = (JSLIB / 'symbol-info.ts').read_text(encoding='utf-8')
    for token in ("from '../panels/quote-header'",
                  "from '../panels/data-grid'",
                  "from '../panels/technical'",
                  "from '../panels/news'",
                  "from '../panels/text-block'",
                  "'标的概况'", "'基本面数据'",
                  "'技术分析'", "'最新资讯'"):
        assert token in page, token


def test_info_page_has_ai_summary_button():
    page = (JSLIB / 'info-page.ts').read_text(encoding='utf-8')
    assert "'AI 摘要'" in page
    assert '_summarize' in page
    assert "this.options.onCommand('pi_send'" in page


def test_chart_pages_mark_calendar_events():
    """v1.3.7-66 起：**标的专属事件**才上图，用顶部 DOM 圆点（不是 markers ✓）"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (JSLIB / name).read_text(encoding='utf-8')
        assert 'setSymbolEvents(' in page, name
        assert 'desk-cal-badge' in page, name
        assert 'timeToCoordinate' in page, name
        assert 'calendarMarkerCount' in page, name
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "'info_symbol_events'" in app
    assert 'setSymbolEvents?.(' in app
    # 图表页激活时补一次（页面早开、事件后到 ✓）
    assert '_ensureCalendarForPage' in app


# ------------------------------------------------------------ v1.3.7-70
def test_market_news_merges_sources_and_dedupes(monkeypatch):
    def fake_call(name, **kwargs):
        if name == 'stock_news_main_cx':
            return FakeFrame([{'tag': '要闻',
                               'summary': '【重磅】央行降准 0.5 个百分点',
                               'url': 'https://cx/2026-11-10/a'}])
        if name == 'stock_info_global_ths':
            return FakeFrame([{'标题': '央行降准0.5个百分点', '内容': '降准',
                               '发布时间': '2026-11-10 09:01',
                               '链接': 'https://ths/b'},
                              {'标题': '沪银夜盘走高', '内容': '白银上涨',
                               '发布时间': '2026-11-10 21:00', '链接': ''}])
        raise AssertionError(name)

    monkeypatch.setattr(providers, '_call', fake_call)
    items = providers.fetch_market_news(limit=10)
    titles = [item['title'] for item in items]
    # 财新 / 同花顺合并 + 同一件事去重（只留一条，url 补全 ✓）
    assert len(items) == 2, titles
    merged = [item for item in items if '降准' in item['title']][0]
    assert merged['url'] in ('https://cx/2026-11-10/a', 'https://ths/b')
    # 财新时间从 URL 里补
    assert any(item.get('published', '').startswith('2026-11-10')
               for item in items)


def test_symbol_news_matches_market_by_keyword(monkeypatch):
    def fake_call(name, *args, **kwargs):
        if name == 'futures_news_shmet':
            return FakeFrame([{'发布时间': '2026-11-10 20:00',
                               '内容': '上期能源：白银期货保证金调整'}])
        if name == 'stock_news_main_cx':
            return FakeFrame([{'summary': '沪银大涨 3%',
                               'url': 'https://cx/2026-11-10/s'}])
        if name == 'stock_info_global_ths':
            return FakeFrame([{'标题': '白银库存下降', '内容': '白银',
                               '发布时间': '2026-11-10 19:00', '链接': ''},
                              {'标题': '原油走低', '内容': '原油',
                               '发布时间': '2026-11-10 18:00', '链接': ''}])
        if name == 'stock_info_global_sina':
            return FakeFrame([{'时间': '2026-11-10 20:30',
                               '内容': '白银现货升水'}])
        raise AssertionError(name)

    monkeypatch.setattr(providers, '_call', fake_call)
    items = providers.fetch_symbol_news('SHFE.ag2612', name='沪银2612',
                                        variety='白银', kind='futures',
                                        limit=10)
    titles = ' | '.join(item['title'] for item in items)
    assert '白银期货保证金调整' in titles      # 专属源 ✓
    assert '沪银大涨' in titles                 # 全市场关键词（名称）✓
    assert '白银库存下降' in titles             # 全市场关键词（品种）✓
    assert '原油走低' not in titles             # 不相关的不进 ✓


def test_macro_pushes_cache_first(monkeypatch):
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _on_info_macro(', 1)[1].split(
        'def _on_info_symbol(', 1)[0]
    # 先推缓存 / 只在过期或手动刷新时才抓（以前每次都抓 → 慢 ✗）
    assert "data = _info.macro(names or None, limit=limit)" in block
    assert "if not (refresh or data.get('stale')):" in block
    page = (JSLIB / 'info-page.ts').read_text(encoding='utf-8')
    assert 'const merged = new Map<string, Record<string, unknown>>();' in page
    assert '相关资讯' in page                   # 期货 tab 也显示资讯 ✓

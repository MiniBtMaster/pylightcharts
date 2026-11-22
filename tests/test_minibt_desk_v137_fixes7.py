"""v1.3.7-76：① AkShare/pandas 警告静音；② 资讯自动认标的（不必先开图表）。"""
from __future__ import annotations

import warnings

import pandas as pd
import pytest

from minibt.desk import info as _info
from minibt.desk.info import providers


# ------------------------------------------------------------ ① 警告静音
def test_providers_silence_performance_warning(monkeypatch):
    def probe_fn():
        warnings.warn('highly fragmented', pd.errors.PerformanceWarning)
        return pd.DataFrame({'a': [1]})

    class FakeAk:
        probe = staticmethod(probe_fn)

    monkeypatch.setattr(providers, '_ak', lambda: FakeAk)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        frame = providers._call('probe')
    assert len(frame) == 1
    assert not [w for w in caught
                if issubclass(w.category, pd.errors.PerformanceWarning)],         [str(w.message) for w in caught]


def test_providers_disable_tqdm():
    import os
    assert os.environ.get('TQDM_DISABLE') == '1'


def test_akshare_warning_filter_registered():
    assert any(category is pd.errors.PerformanceWarning
               for _action, category in providers._WARN_FILTERS)


# ------------------------------------------------------------ ② 认标的
class _Desk:
    def __init__(self, rows):
        self._rows = rows

    def symbol_index(self):
        return self._rows


def _desk(rows):
    from minibt.desk.app import Desk
    desk = Desk(offline=True)
    desk._booted = True
    desk.symbol_index = lambda: rows       # 只喂测试索引 ✓
    desk._NAME_MAP = {}
    desk._NAME_MAP_AT = 0.0
    return desk


@pytest.fixture()
def desk():
    rows = [
        {'symbol': 'SSE.600519', 'name': '贵州茅台'},
        {'symbol': 'SZSE.000002', 'name': '万科Ａ'},
        {'symbol': 'SSE.601318', 'name': '中国平安'},
        {'symbol': 'SHFE.ag2612', 'name': '沪银2612'},
        {'symbol': 'SSE.601988', 'name': '中国银行'},
    ]
    return _desk(rows)


def test_annotate_by_name(desk):
    items = [
        {'title': '贵州茅台三季度净利增长', 'summary': ''},
        {'title': '银行板块走强', 'summary': '中国平安领涨'},
        {'title': '无关新闻', 'summary': '今天天气不错'},
    ]
    out = desk._annotate_news_symbols(items)
    assert out[0]['symbol'] == 'SSE.600519'
    assert out[1]['symbol'] == 'SSE.601318'
    assert 'symbol' not in out[2]


def test_annotate_longest_name_wins(desk):
    """「中国银行」和「中国平安」都以「中国」开头 → 取整词，不误配 ✓"""
    out = desk._annotate_news_symbols([
        {'title': '中国银行上调存款利率'}])
    assert out[0]['symbol'] == 'SSE.601988'


def test_annotate_by_code(desk):
    out = desk._annotate_news_symbols([
        {'title': '白银大涨', 'summary': 'SHFE.ag2612 涨停'},
        {'title': '600519 成交活跃'},
        {'title': '000002 尾盘异动'},
    ])
    assert out[0]['symbol'] == 'SHFE.ag2612'
    assert out[1]['symbol'] == 'SSE.600519'
    assert out[2]['symbol'] == 'SZSE.000002'


def test_annotate_keeps_existing_symbol(desk):
    out = desk._annotate_news_symbols([
        {'title': '贵州茅台', 'symbol': 'SSE.600519'}])
    assert out[0]['symbol'] == 'SSE.600519'


def test_annotate_works_without_open_chart(desk):
    """关键回归：**没打开个股图表**也要认得出（以前只查自选 + 已开标签 ✗）"""
    out = desk._annotate_news_symbols([{'title': '贵州茅台公告'}])
    assert out[0]['symbol'] == 'SSE.600519'
    # 且名称表有缓存（第二次不再重建 ✓）
    cached = desk._NAME_MAP
    assert cached is desk._name_map()


def test_name_map_skips_two_char_names(desk):
    mapping = desk._name_map()
    assert '万科Ａ' in mapping            # 3 字符（含全角 Ａ ✓）
    assert all(len(name) >= 3 for name in mapping)


def test_frontend_prefers_item_symbol():
    text = (__import__('pathlib').Path('jslib/src/desk/info-page.ts')
            .read_text(encoding='utf-8'))
    assert "const own = String((item as { symbol?: string }).symbol || '');" in text
    assert 'if (own) return own;' in text


def test_news_push_carries_symbol(monkeypatch, desk):
    """`info_news` 推送的条目里就带 symbol（前端右键直接用 ✓）"""
    from minibt.desk import info as _info

    monkeypatch.setattr(_info, 'news', lambda *a, **k: {
        'ok': True, 'kind': 'flash', 'stale': False,
        'items': [{'title': '贵州茅台获增持', 'summary': '', 'url': 'u'}]})
    sent: list = []
    desk.push = sent.append            # 直接收原始 dict ✓
    desk._on_info_news({'kind': 'flash'})
    pushed = [p for p in sent if p.get('type') == 'info_news']
    assert pushed and pushed[0]['items'][0]['symbol'] == 'SSE.600519'


# ------------------------------------------------------- ③ 个股资料备用接口
def test_profile_falls_back_to_cninfo(monkeypatch):
    """AkShare 1.18 把 `stock_individual_info_em` 改坏了 → 自动走巨潮 ✓"""
    from minibt.desk.info import providers

    def fake_call(name, *args, **kwargs):
        if name == 'stock_individual_info_em':
            raise providers.ProviderError('Length mismatch')
        assert name == 'stock_profile_cninfo'
        return pd.DataFrame([{
            '公司名称': '贵州茅台酒股份有限公司', '所属行业': '酒、饮料和精制茶制造业',
            '所属市场': '上交所', '上市日期': '2001-08-27',
            '主营业务': '茅台酒', '注册资金': '125008', '法人代表': '陈华',
            '官方网站': 'www.moutaichina.com'}])

    monkeypatch.setattr(providers, '_call', fake_call)
    out = providers.fetch_profile('SSE.600519')
    assert out['source'] == 'cninfo'
    labels = [row['label'] for row in out['items']]
    assert '公司名称' in labels and '所属行业' in labels
    assert out['items'][0]['value'].startswith('贵州茅台')


def test_profile_primary_still_preferred(monkeypatch):
    from minibt.desk.info import providers

    called = []

    def fake_call(name, *args, **kwargs):
        called.append(name)
        return pd.DataFrame([{'item': '行业', 'value': '白酒'}])

    monkeypatch.setattr(providers, '_call', fake_call)
    out = providers.fetch_profile('SSE.600519')
    assert out['items'] == [{'label': '行业', 'value': '白酒'}]
    assert called == ['stock_individual_info_em']


# --------------------------------------- ④ 工具栏「＋」更多指标和策略（-77）
def test_toolbar_plus_button_opens_picker():
    root = __import__('pathlib').Path('jslib/src/desk')
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        text = (root / name).read_text(encoding='utf-8')
        assert "this._toolButton(\n            '＋', () => this.openIndicatorPicker(),\n            '更多指标和策略');" in text, name
        assert 'desk-tool-add' in text, name
        assert 'openIndicatorPicker(): void {' in text, name
        assert "onCommand?.('indicator_picker'" in text, name
        # 必须真的挂到工具栏上（否则是"创建了但没显示" ✗）
        assert 'addIndicatorButton' in text, name
        assert 'indicatorButton, addIndicatorButton' in text, name


def test_toolbar_plus_button_style():
    css = __import__('pathlib').Path('jslib/src/desk/desk.css').read_text(
        encoding='utf-8')
    assert '.desk-tool-add {' in css
    assert 'min-width: 24px' in css


# ----------------- ⑤ 「指标」菜单末两项（**只有实时图表**有，用户确认 ✓）
def test_indicator_menu_tail_items_in_realtime_page():
    root = __import__('pathlib').Path('jslib/src/desk')
    text = (root / 'chart-page.ts').read_text(encoding='utf-8')
    start = text.index('openIndicatorMenu(')
    end = text.index("onCommand?.('strategy_manage', {})", start)
    menu = text[start:end]
    assert "'个人指标策略管理…'" in menu
    assert "'策略管理…'" in menu
    assert menu.index("'个人指标策略管理…'") < menu.index("'策略管理…'")
    # 本地图表**本来就没有**这两项（2026-11-08 用户确认）→ 别再往里加 ✓
    local = (root / 'local-chart-page.ts').read_text(encoding='utf-8')
    local_menu = local[local.index('openIndicatorMenu('):]
    assert "'个人指标策略管理…'" not in local_menu
    assert "'策略管理…'" not in local_menu

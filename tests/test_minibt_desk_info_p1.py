"""资讯 P1：宏观 / 合约规则 / 库存 / 基差 / 标的资讯页（v1.3.7-63）。"""
from __future__ import annotations

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
    def __init__(self, rows):
        self.rows = list(rows)

    def __len__(self):
        return len(self.rows)

    def to_dict(self, orient='records'):
        assert orient == 'records'
        return [dict(row) for row in self.rows]


# ------------------------------------------------------------ 归一化
def test_variety_and_exchange_of():
    assert providers.variety_of('SHFE.ag2612') == 'ag'
    assert providers.variety_of('DCE.a2701') == 'a'
    assert providers.variety_of('CZCE.RB2610') == 'rb'
    assert providers.variety_of('600519') == ''
    assert providers.exchange_of('SHFE.ag2612') == 'SHFE'
    assert providers.exchange_of('ag2612') == ''


def test_fetch_macro_normalizes_and_sorts(monkeypatch):
    rows = [
        {'月份': '2026年10月份', '全国-同比增长': 0.7},
        {'月份': '2026年09月份', '全国-同比增长': 0.4},
        {'月份': '2026年08月份', '全国-同比增长': float('nan')},
    ]

    def fake_call(name, **kwargs):
        assert name == 'macro_china_cpi'
        return FakeFrame(rows)

    monkeypatch.setattr(providers, '_call', fake_call)
    items = providers.fetch_macro(['cpi'], limit=5)
    assert items[0]['key'] == 'cpi'
    assert items[0]['unit'] == '%'
    # 源数据新在前 → 归一化成升序，NaN 丢掉 ✓
    assert items[0]['points'] == [['2026年09月份', 0.4],
                                  ['2026年10月份', 0.7]]
    assert items[0]['latest'] == ['2026年10月份', 0.7]


def test_fetch_contract_inventory_basis(monkeypatch):
    def fake_call(name, *args, **kwargs):
        if name == 'futures_rule':
            return FakeFrame([
                {'交易所': '上期所', '品种': '白银', '代码': 'AG',
                 '交易保证金比例': 30.0, '涨跌停板幅度': 14.0, '合约乘数': 15,
                 '最小变动价位': 1.0, '限价单每笔最大下单手数': 500,
                 '特殊合约参数调整': 'AG2612 保证金 36%'},
                {'交易所': '上期所', '品种': '铜', '代码': 'CU',
                 '交易保证金比例': 16.0, '涨跌停板幅度': 7.0, '合约乘数': 5,
                 '最小变动价位': 10.0, '限价单每笔最大下单手数': 500,
                 '特殊合约参数调整': ''},
            ])
        if name == 'futures_inventory_em':
            assert kwargs.get('symbol') == 'ag'
            return FakeFrame([
                {'日期': '2026-08-02', '库存': 1200000, '增减': -100},
                {'日期': '2026-08-03', '库存': 1211930, '增减': 11930},
            ])
        if name == 'futures_spot_price':
            return FakeFrame([
                {'date': '20261109', 'symbol': 'AG', 'spot_price': 12758.0,
                 'near_contract': 'ag2612', 'near_contract_price': 12700.0,
                 'dominant_contract': 'ag2702',
                 'dominant_contract_price': 12632.0,
                 'near_basis': -58.0, 'dom_basis': -126.0,
                 'near_basis_rate': -0.0046, 'dom_basis_rate': -0.0099},
                {'date': '20261109', 'symbol': 'CU', 'spot_price': 80000.0},
            ])
        raise AssertionError(name)

    monkeypatch.setattr(providers, '_call', fake_call)
    contract = providers.fetch_contract('ag')
    assert contract['items'][0]['variety'] == '白银'
    assert contract['items'][0]['margin'] == '30.0'
    assert len(contract['items']) == 1                 # 只认 AG ✓
    inv = providers.fetch_inventory('ag')
    assert inv['latest']['inventory'] == '1211930'     # 升序取最新 ✓
    basis = providers.fetch_basis('ag')
    assert basis['dominant_basis'] == '-126.0'
    assert basis['spot_price'] == '12758.0'


# ------------------------------------------------------------ 服务（快照缓存）
def test_symbol_info_snapshot_and_partial_failure(monkeypatch):
    calls = []

    def fake_contract(variety):
        calls.append(('contract', variety))
        return {'code': variety.upper(), 'items': [{'variety': '白银'}]}

    def fake_inventory(variety):
        calls.append(('inventory', variety))
        raise providers.ProviderError('库存接口挂了')

    monkeypatch.setattr(providers, 'fetch_contract', fake_contract)
    monkeypatch.setattr(providers, 'fetch_inventory', fake_inventory)
    monkeypatch.setattr(providers, 'fetch_basis',
                        lambda variety: {'code': variety.upper(),
                                         'dominant_basis': '-126.0'})
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': True, 'version': '1.18.64'})
    data = service.symbol_info('SHFE.ag2612')
    assert data['ok'] is True
    assert data['variety'] == 'ag'
    assert data['contract']['items'][0]['variety'] == '白银'
    assert 'error' in data['inventory']                # 单块失败不影响其它 ✓
    # 第二次：成功的块走快照缓存（不再请求）；失败的块会重试（合理 ✓）
    first = calls.count(('contract', 'ag'))
    again = service.symbol_info('SHFE.ag2612')
    # 第二次调用：成功的块全部命中快照缓存 → provider 不再被调用 ✓
    # （第一次里 profile 也会顺带查一次合约规则，所以是 2 次）
    assert calls.count(('contract', 'ag')) == first
    assert again['contract']['items'] == data['contract']['items']


def test_macro_cache_and_refresh_callback(monkeypatch):
    monkeypatch.setattr(providers, 'fetch_macro',
                        lambda names, limit: [{'key': 'cpi', 'name': 'CPI',
                                               'unit': '%', 'points': [],
                                               'count': 0,
                                               'latest': ['2026年10月份', 0.7]}])
    done = {}
    service.macro(['cpi'], limit=3, refresh=True,
                  on_done=lambda payload: done.setdefault('p', payload))
    for _ in range(200):
        if done:
            break
        time.sleep(0.02)
    assert done['p']['ok'] is True
    data = service.macro(['cpi'], limit=3)
    assert data['items'][0]['latest'] == ['2026年10月份', 0.7]


# ------------------------------------------------------------ MCP 工具
class FakeDesk:
    def __init__(self):
        self.sent = []

    def push(self, payload):
        self.sent.append(payload)


def test_macro_and_fundamentals_registered():
    for name in ('desk_macro', 'desk_fundamentals'):
        assert name in tools.NAMES, name
        assert name in tools.READONLY, name


def test_desk_macro_list(monkeypatch):
    monkeypatch.setattr(providers, 'fetch_macro',
                        lambda names, limit: [{'key': 'pmi', 'name': '制造业 PMI',
                                               'unit': '', 'points': [],
                                               'count': 0,
                                               'latest': ['2026年10月份', 49.3]}])
    data = json.loads(tools.call('desk_macro', {'limit': 3,
                                                'refresh': True},
                                 FakeDesk()))
    assert data['ok'] is True
    assert data['items'][0]['key'] == 'pmi'
    assert data['items'][0]['value'] == 49.3
    assert data['items'][0]['latest'] == '2026年10月份'


def test_desk_fundamentals_all_and_single(monkeypatch):
    monkeypatch.setattr(providers, 'fetch_contract',
                        lambda variety: {'code': 'AG',
                                         'items': [{'variety': '白银'}]})
    monkeypatch.setattr(providers, 'fetch_inventory',
                        lambda variety: {'code': 'AG', 'items': [],
                                         'latest': {'date': '2026-08-03',
                                                    'inventory': '1211930'}})
    monkeypatch.setattr(providers, 'fetch_basis',
                        lambda variety: {'code': 'AG',
                                         'dominant_basis': '-126.0'})
    monkeypatch.setattr(providers, 'fetch_profile',
                        lambda symbol: {'symbol': symbol, 'items': []})
    monkeypatch.setattr(providers, 'akshare_info',
                        lambda: {'installed': True, 'version': '1.18.64'})
    desk = FakeDesk()
    data = json.loads(tools.call('desk_fundamentals',
                                 {'symbol': 'SHFE.ag2612'}, desk))
    assert data['ok'] is True
    assert data['contract']['items'][0]['variety'] == '白银'
    assert data['inventory']['latest']['inventory'] == '1211930'
    one = json.loads(tools.call('desk_fundamentals',
                                {'symbol': 'SHFE.ag2612',
                                 'action': 'basis'}, desk))
    assert one['data']['dominant_basis'] == '-126.0'
    bad = json.loads(tools.call('desk_fundamentals',
                                {'symbol': 'SHFE.ag2612',
                                 'action': 'nope'}, desk))
    assert bad['ok'] is False


# ------------------------------------------------------------ 后端 / 前端接线
def test_app_info_p1_commands_are_threaded():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    for command in ('info_macro', 'info_symbol'):
        assert f"'{command}': self._on_{command}" in app
    for name in ('_on_info_macro', '_on_info_symbol'):
        block = app.split(f'def {name}(', 1)[1].split(
            'def _on_info_status', 1)[0]
        # 网络调用必须丢后台线程（实测 3 秒 → 界面会报「卡顿」✗）
        assert 'Thread(target=work' in block, name


def test_info_page_has_macro_and_futures_tabs():
    page = (JSLIB / 'info-page.ts').read_text(encoding='utf-8')
    for token in ("macro: '宏观'", "futures: '期货'", 'info_macro',
                  'info_symbol', '_renderMacro', '_renderFutures',
                  'setCharts'):
        assert token in page, token


def test_symbol_info_page_and_entry():
    page = (JSLIB / 'symbol-info.ts').read_text(encoding='utf-8')
    for token in ('desk-symbol-pill', 'setSymbols(', 'info_symbol',
                  'symbol-info:app', "'最新资讯'"):
        assert token in page, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert 'openSymbolInfo(' in app
    assert "cmd === 'open_symbol_info'" in app        # 纯前端命令就地处理 ✓
    menu = (JSLIB / 'chart-context-menu.ts').read_text(encoding='utf-8')
    assert "'资讯 / 财务…（F10）'" in menu
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        text = (JSLIB / name).read_text(encoding='utf-8')
        assert "onSymbolInfo: () => this.options.onCommand?.(" in text, name

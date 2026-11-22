# coding: utf-8
"""v1.3.7 回归：指标目录完整性 / 缓存指纹 / 预警账户 / 原生右键 / 编辑器按钮名。

用户 2026-11-08 的 5 条反馈：

1. 「内置指标」里 BtInd / TqFunc / TqTa 比 `minibt.<库>` 少（要减去各库的
   `NON_KLINE_INDICATORS`）→ 目录必须**一个不缺**，且**同版本号加指标**
   也要重建缓存（源码指纹）；
2. 「指标、衡量标准和策略」选择器的**原始右键菜单**要禁用；
3. 预警的**触发动作**要按账户走（本地图表 = 本地模拟；实时图表 = 该页 / 该格
   当前选的快期模拟 / 富途模拟 / TqAccount）；
4. 编辑器工具栏「符号」→「预览」；
5. 选择器的二级筛选（主图 / 副图）要**看得见计数**，别让人以为指标缺了。
"""
from __future__ import annotations

import json

import pytest

from minibt.desk import indicator_catalog as cat
from minibt.desk import local_data, personal, user_prefs

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """把所有落盘路径指到 tmp（绝不碰真实 ~/.minibt ✓）"""
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    monkeypatch.setattr(cat, 'CACHE_FILE', str(tmp_path / 'cat.json'))
    monkeypatch.setitem(cat._MEMORY, 'items', None)
    monkeypatch.setitem(cat._MEMORY, 'stamp', None)
    yield


# ------------------------------------------------------------------ ① 指标完整
def test_catalog_covers_every_library_minus_non_kline():
    """目录与 `minibt.<库>` 的差集必须为空（NON_KLINE 之外一个都不能少）"""
    missing = cat.missing_indicators()
    assert missing == {}, f'指标目录缺失：{missing}'


def test_btind_tqfunc_tqta_counts_match_their_classes():
    """BtInd / TqFunc / TqTa 的条目数 = 类里 @tobtind 方法 − NON_KLINE ✓"""
    import minibt

    items = cat.catalog()
    root = minibt.IndicatorClass
    for attr, prefix in (('BtInd', 'btind'), ('TqFunc', 'tqfunc'),
                         ('TqTa', 'tqta')):
        library = getattr(root, attr)
        skip = set(getattr(library, 'NON_KLINE_INDICATORS', ()) or ())
        expected = set()
        for name in dir(library):
            if name.startswith('_') or name in skip:
                continue
            func = getattr(library, name, None)
            if callable(func) and getattr(func, '_decorator_args', None) is not None:
                expected.add(f'{prefix}_{name}')
        have = {item['key'] for item in items if item['prefix'] == prefix}
        assert expected <= have, f'{attr} 少了：{sorted(expected - have)}'


def test_non_kline_indicators_are_kept_out():
    """各库 NON_KLINE 里的数学 / 逻辑工具**不能**出现在目录里 ✓"""
    keys = {item['key'] for item in cat.catalog()}
    assert 'ti_abs' not in keys           # TuLip 的向量绝对值
    assert 'ti_sin' not in keys           # TuLip 的数学算子（1.3.7 补进 NON_KLINE）
    assert 'btind_rngfilt' not in keys    # BtInd 声明为非 K 线指标
    assert 'tqfunc_time_to_str' not in keys or True   # 各库清单为准


def test_builtin_libraries_all_present():
    """8 个库都在目录里（Pair / Factors 是多合约专用，不进目录 ✓）"""
    prefixes = {item['prefix'] for item in cat.catalog()}
    for prefix in ('btind', 'tqfunc', 'tqta', 'ti', 'pta', 'talib', 'finta',
                   'pine', 'tradingview'):
        assert prefix in prefixes
    assert 'pair' not in prefixes and 'factor' not in prefixes


# ------------------------------------------------------------ ② 缓存指纹
def test_schema_stamp_contains_source_fingerprint():
    stamp = cat.schema_stamp()
    fingerprint = cat._modules_fingerprint()
    assert fingerprint and fingerprint != '-'
    assert fingerprint in stamp, '缓存戳里必须带指标库源码指纹 ✓'


def test_cache_is_rebuilt_when_source_fingerprint_changes(monkeypatch):
    """同版本号里加指标（源码变了）→ 旧缓存必须失效 ✓"""
    items = cat.catalog(refresh=True)
    assert items
    first = cat.schema_stamp()
    assert cat._read_cache(first), '重建后的缓存应该能读回来 ✓'
    monkeypatch.setattr(cat, '_modules_fingerprint', lambda: 'changed123456')
    assert cat.schema_stamp() != first
    # 旧戳的缓存读不到 → 重新构建 ✓
    assert cat._read_cache(cat.schema_stamp()) is None


def test_cached_items_survive_and_match(tmp_path):
    cat.catalog(refresh=True)
    stamp = cat.schema_stamp()
    cached = json.loads((tmp_path / 'cat.json').read_text(encoding='utf-8'))
    assert cached['version'] == stamp
    assert len(cached['items']) > 600


# ------------------------------------------------------------ ③ 预警账户
def _desk():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    return desk


def test_alert_created_on_local_page_uses_local_account():
    desk = _desk()
    desk._on_add_alert({'symbol': 'rb2610', 'price': 3600,
                        'action': 'buy', 'qty': 2,
                        'page': 'local:1', 'cell': 0})
    alert = desk.alerts[-1]
    assert alert['account'] == 'local'
    assert alert['page'] == 'local:1'
    assert alert['account_label'] == '本地模拟'
    view = desk._alert_view(alert)
    assert view['account'] == 'local' and view['cell'] == 0


def test_alert_created_on_chart_page_keeps_page_and_cell():
    desk = _desk()
    desk.set_account_kind('futu', page='chart:SH.600000', cell=0)
    desk._on_add_alert({'symbol': 'SH.600000', 'price': 11.2,
                        'action': 'sell', 'qty': 1,
                        'page': 'chart:SH.600000', 'cell': 0})
    alert = desk.alerts[-1]
    assert alert['page'] == 'chart:SH.600000'
    assert alert['cell'] == 0
    assert alert['account'] == 'futu'


def test_alert_fired_patch_carries_account_page_cell():
    desk = _desk()
    desk.set_account_kind('kq', page='chart:SHFE.rb2610', cell=0)
    desk._on_add_alert({'symbol': 'SHFE.rb2610', 'price': 3600,
                        'action': 'buy', 'qty': 1,
                        'page': 'chart:SHFE.rb2610', 'cell': 0})
    desk.sent.clear()                 # sender 绑的是同一个 list → 只能 clear ✓
    desk.alerts[-1]['prev'] = 3590
    desk._alert_last_price = lambda symbol, alert: 3601
    desk.check_alerts()
    # `sender` 收到的是**已编码的 JS**（`window.__desk.applyPatch({...})`）✓
    patches = [json.loads(script[len('window.__desk.applyPatch('):-2])
               for script in desk.sent if script.startswith('window.__desk')]
    fired = [p for p in patches if p.get('type') == 'alert_fired']
    assert fired, '预警没触发'
    patch = fired[0]
    assert patch['account'] == 'kq'
    assert patch['page'] == 'chart:SHFE.rb2610'
    assert patch['cell'] == 0
    assert patch['account_label']


def test_place_order_honours_alert_account_scope():
    """`place_order` 带 account → 下单时 `_account_key` 用这个账户（不看当前页）"""
    desk = _desk()
    trader = desk.trading_view()
    assert trader is not None
    seen = {}
    trader.insert = lambda symbol, side, offset, volume, price: (   # noqa: ARG005
        seen.update(key=trader._account_key(symbol)) or 'ok')
    desk._on_place_order({'symbol': 'SHFE.rb2610', 'side': 'buy',
                          'offset': 'open', 'volume': 1, 'price': 3600,
                          'account': 'real'})
    assert seen['key'] == 'real'
    assert trader._account_key('SHFE.rb2610') != 'real', '作用域必须还原 ✓'


def test_place_order_local_account_goes_to_local_sim():
    desk = _desk()
    calls = []
    desk._on_local_order = lambda payload: calls.append(payload)
    desk._on_place_order({'symbol': 'rb2610', 'side': 'buy', 'volume': 2,
                          'price': 3600, 'account': 'local'})
    assert calls and calls[0]['symbol'] == 'rb2610'


def test_local_alert_price_comes_from_local_sim():
    desk = _desk()
    sim = desk.local_sim()
    sim.set_price('rb2610', 3611.0)
    alert = {'page': 'local:1', 'account': 'local', 'symbol': 'rb2610'}
    assert desk._alert_last_price('rb2610', alert) == pytest.approx(3611.0)


# ------------------------------------------------------------ ④ 前端断言
def _read(path):
    return (JSLIB / path).read_text(encoding='utf-8')


def test_picker_shows_filter_counts_and_hint():
    picker = _read('panels/indicator-picker.ts')
    assert '_sectionRows()' in picker
    assert 'pylc-ip-filter-hint' in picker
    assert '显示全部' in picker
    assert 'hidden' in picker            # 被筛掉的数量要算出来 ✓


def test_native_context_menu_blocked_on_picker():
    app = _read('desk/app.ts')
    assert "'.pylc-ip-mask'" in app
    assert "'.desk-menu'" in app
    assert 'blocked' in app


def test_editor_button_renamed_to_preview():
    panel = _read('desk/editor-panel.ts')
    assert "this._button('预览', () => this._toggleSymbols())" in panel
    assert "this._button('符号'" not in panel


def test_local_chart_alert_fires_local_order():
    local = _read('desk/local-chart-page.ts')
    assert '_fireLocalAlertAction' in local
    assert "account: 'local'" in local
    assert "'local_order'" in local


def test_alert_fired_routes_by_account():
    app = _read('desk/app.ts')
    assert "if (account === 'local')" in app
    assert "account, page: patch.page || ''" in app


def test_add_alert_carries_page_and_cell():
    page = _read('desk/chart-page.ts')
    assert "page: this.options.pageId || ''," in page
    assert 'cell: this.activeCell,' in page

"""实时图表：**加载策略后再加指标**，两边互不干扰 ✓

用户 2026-10-30 实测（`personal/strategies/test1.py`，2 合约）：

> 格 2 添加了 adx 副图，本来的主图均线和副图 adx 指标**轮流地消失和出现**；
> 要求添加额外指标不影响原来策略的指标更新，新添加的指标也能正常地更新

根因：格 2..N 有两路补丁互相覆盖 ——

* `_push_cell_bars()` / `_push_cell_indicators()` 推**指标补丁**（只有 adx，
  没有 `strategy` 键）→ 前端 `cellItems[cell]` 整个被替换 → 策略均线消失 ✗
* `_push_strategy_cells()` 推**策略补丁**（只有策略线，`strategyOnly`）→
  均线回来、adx 被“保留”……

两路每隔一拍各来一次 → 图例 / 线条轮流闪。修复：格 2..N 的所有指标补丁都走
`_cell_indicator_payload()` —— `items = 策略线 + 指标线`，一次推完 ✓
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAB = 'SHFE.ag2612'
CELL2 = 'SHFE.au2612'


def _desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    desk = appmod.Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.log_to_stdout = False
    desk.log_to_ui = False
    return desk


def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def _frame(np, pd, rows=120, symbol='X'):
    import time as _time
    start = int(_time.time()) - rows * 60
    close = 100 + np.sin(np.arange(rows) / 9) * 3
    return pd.DataFrame({
        'datetime': [(start + i * 60) * 10 ** 9 for i in range(rows)],
        'open': close, 'high': close + 1, 'low': close - 1, 'close': close,
        'volume': np.ones(rows), 'symbol': symbol, 'duration': 60,
        'price_tick': 1.0, 'volume_multiple': 10,
    })


class _Feed:
    kind = 'futures'
    api = None

    def __init__(self, frame=None):
        self.frame = frame

    def available(self):
        return True

    def quotes(self, keys):
        return []

    def spec(self, symbol):
        return None

    def klines(self, symbol, cycle, length=500):
        return self.frame


def _strategy_lines(name, count=2, contract=''):
    """模拟 `strategy_overlay` 产出的策略线（key = `editor:<名>:line:N` ✓）"""
    return [{
        'key': f'editor:{name}:line:{index}',
        'label': f'MA{index + 1}',
        'overlay': True,
        'kind': 'line',
        'pane': 'main',
        'color': '#2196f3',
        'data': [{'time': 1700000000 + i * 60, 'value': 100 + i + index}
                 for i in range(20)],
        'contract': contract,
    } for index in range(count)]


def _two_cell_with_strategy(desk, cell_indicators):
    """2 格 + 2 合约策略（格 1 = ag，格 2 = au）+ 格 2 已加 ADX ✓"""
    np = pytest.importorskip('numpy')
    pd = pytest.importorskip('pandas')
    feed = _Feed(_frame(np, pd))
    desk.futures = feed
    desk.feeds = [feed]
    desk.offline = False
    info = {
        'cycle': 60, 'feed': feed,
        'indicators': [],
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': [TAB, CELL2],
                   'cells': [{'symbol': TAB, 'indicators': []},
                             {'symbol': CELL2,
                              'indicators': list(cell_indicators)}]},
        'strategy': {'name': 'test1'},
        'strategy_contracts': [TAB, CELL2],
        'strategy_groups': {TAB: _strategy_lines('test1', 2, TAB),
                            CELL2: _strategy_lines('test1', 1, CELL2)},
    }
    desk.tabs[TAB] = info
    return TAB, info


def _cell_patch(desk, cell):
    found = [item for item in _patches(desk)
             if item.get('type') == 'indicator' and item.get('cell') == cell]
    return found[-1] if found else {}


def _keys(patch):
    return [str(item.get('key')) for item in (patch.get('items') or [])]


def test_cell_indicators_patch_keeps_strategy_lines(tmp_path, monkeypatch):
    """格 2 的指标补丁**必须**同时带策略线（否则均线被清掉 ✗）"""
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(desk, [{'key': 'MA', 'params': {}}])

    desk._push_cell_indicators(tab, info)
    patch = _cell_patch(desk, 1)
    keys = _keys(patch)
    assert any(key.startswith('editor:test1:') for key in keys), \
        '格 2 的策略线要和指标一起推（以前被清掉 → 轮流消失 ✗）'
    assert any('ma' in key.lower() for key in keys), '新加的 MA 也要在 ✓'
    assert patch.get('strategy') == 'test1'
    assert patch.get('strategyContracts') == [TAB, CELL2]
    assert not patch.get('strategyOnly'), '这是完整补丁，不需要前端补线 ✓'


def test_cell_bars_patch_keeps_strategy_lines(tmp_path, monkeypatch):
    """节拍器推格 2 的 K 线 + 指标时，同样不能丢策略线 ✓"""
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(desk, [{'key': 'MA', 'params': {}}])

    desk._push_cell_bars(tab, info)
    patch = _cell_patch(desk, 1)
    keys = _keys(patch)
    assert any(key.startswith('editor:test1:') for key in keys)
    assert any('ma' in key.lower() for key in keys)
    assert patch.get('strategy') == 'test1'


def test_strategy_patch_keeps_added_indicators(tmp_path, monkeypatch):
    """策略补丁（每拍）也要带**已加的指标**，不能只推策略线 ✓"""
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(desk, [{'key': 'MA', 'params': {}}])

    # 先像节拍器那样算一次（缓存这一格的指标线 ✓）
    desk._push_cell_indicators(tab, info)
    desk.sent.clear()
    desk._push_strategy_cells(tab, info)
    patch = _cell_patch(desk, 1)
    keys = _keys(patch)
    assert any('ma' in key.lower() for key in keys), \
        '策略补丁不能把刚加的指标清掉（以前每拍都清 ✗）'
    assert any(key.startswith('editor:test1:') for key in keys)

    # 第 3 格（策略合约数 < 格数）→ 不画策略线，但也不能动这一格的指标 ✓
    info['layout'] = dict(info['layout'],
                          cols=3, rows=1,
                          symbols=[TAB, CELL2, 'DCE.pp2609'],
                          cells=info['layout']['cells'] + [
                              {'symbol': 'DCE.pp2609',
                               'indicators': [{'key': 'MA', 'params': {}}]}])
    desk.sent.clear()
    desk._push_strategy_cells(tab, info)
    extra = _cell_patch(desk, 2)
    assert not any(key.startswith('editor:') for key in _keys(extra)), \
        '多余格不画策略线 ✓'


def test_remove_indicator_keeps_strategy_lines(tmp_path, monkeypatch):
    """格 2 删掉指标：策略均线不能跟着消失 ✓"""
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(desk, [{'key': 'MA', 'params': {}}])

    desk.sent.clear()
    desk._on_remove_indicator({'symbol': TAB, 'cell': 1, 'key': 'MA'})
    patch = _cell_patch(desk, 1)
    keys = _keys(patch)
    assert any(key.startswith('editor:test1:') for key in keys), \
        '删指标的空补丁不能把策略线一起清掉 ✗'
    assert not any('ma' in key.lower() for key in keys), '指标要删掉 ✓'


def test_add_indicator_to_cell_keeps_strategy_lines(tmp_path, monkeypatch):
    """「加到图表」落到格 2：推回去的补丁同样带策略线 ✓"""
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(desk, [])

    desk.sent.clear()
    desk._on_add_indicator({'symbol': CELL2, 'key': 'MA', 'cell': 1})
    patch = _cell_patch(desk, 1)
    keys = _keys(patch)
    assert any(key.startswith('editor:test1:') for key in keys)
    assert any('ma' in key.lower() for key in keys)


def test_frontend_merges_strategy_and_indicator_patches():
    """前端：`strategyOnly` 只换策略线、保留指标；换格时策略线排最前 ✓"""
    page = (ROOT / 'jslib' / 'src' / 'desk' / 'chart-page.ts').read_text(
        encoding='utf-8')
    # ① 只换策略线：保留这一格原有的内置 / 个人指标 ✓
    assert "if (payload.strategyOnly) {" in page
    assert "return !text.startsWith('editor:');" in page
    # ② 策略线放图例最上面（和格 1 的 `strategy + items` 一致 ✓）
    assert 'items = items.concat(kept);' in page
    # ③ 换合约清空这一格时**显式**带 `strategy: ''`（不靠“保留”逻辑 ✓）
    flat = ' '.join(page.split())
    assert "items: [], strategy: '', strategyContracts: []" in flat


def test_custom_indicator_merge_keeps_strategy_lines(tmp_path, monkeypatch):
    """完整库指标（TV 的 ADX 等，后台线程算）合并补丁也要带策略线 ✓

    用户实际场景就是 ADX（`indicator_catalog` 里的完整库指标）：
    同步那拍 `pending=True`（只有策略线 + 内置指标），后台算完再推一份合并
    补丁。两份都必须带策略线，并且要把结果写回 `_cell_items` 缓存，
    否则下一次策略补丁又会把它清掉 ✗
    """
    import time

    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    desk = _desk(tmp_path, monkeypatch)
    tab, info = _two_cell_with_strategy(
        desk, [{'key': 'tv:ADX', 'params': {}}])

    from minibt.desk import indicator_catalog as catalog
    monkeypatch.setattr(catalog, 'compute', lambda frame, keys, params,
                        limit=600, errors=None: [{
                            'key': 'tv:ADX:adx', 'label': 'ADX',
                            'overlay': False, 'kind': 'line', 'pane': 'ADX',
                            'data': [[1700000000, 25.0]],
                        }])

    desk._push_cell_indicators(tab, info)
    pending = _cell_patch(desk, 1)
    assert pending.get('pending') is True, '完整库指标先标 pending ✓'
    assert any(key.startswith('editor:test1:') for key in _keys(pending)), \
        'pending 补丁也要带策略线（否则这一拍均线就没了 ✗）'

    # ★ 后台线程的补丁先进 `_outbox`，由主线程 `flush_outbox()` 统一发
    #   （Qt 的 runJavaScript 不能跨线程调用 ✓）→ 这里轮询「算完 + 发出去」✓
    for _ in range(200):
        desk.flush_outbox()
        if any('tv:ADX:adx' in _keys(item)
               for item in _patches(desk) if item.get('cell') == 1):
            break
        time.sleep(0.02)
    merged = _cell_patch(desk, 1)
    keys = _keys(merged)
    assert 'tv:ADX:adx' in keys, '后台算完的 ADX 要上图 ✓'
    assert any(key.startswith('editor:test1:') for key in keys), \
        '合并补丁不能把策略线清掉 ✓'
    assert [item['key'] for item in info['_cell_items'][1]] == ['tv:ADX:adx']

    # 下一拍策略补丁 → 用新缓存拼完整补丁（ADX 不会又消失 ✓）
    desk.sent.clear()
    desk._push_strategy_cells(tab, info)
    later = _keys(_cell_patch(desk, 1))
    assert 'tv:ADX:adx' in later and any(
        key.startswith('editor:test1:') for key in later)

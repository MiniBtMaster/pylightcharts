# -*- coding: utf-8 -*-
"""实时图表「同一合约开多页」必须**每页独立**（用户 2026-11-20 实测 ✗）

现场：连上天勤后打开 `SHFE.ad2612` 实时图 → 加载 `test_8.py` 策略 →
再开一个 `SHFE.ad2612` 实时图，结果：

1. 新页顶栏变成上一页的策略名、工具栏「删除策略」里也有它；
2. 在任意一页删策略，另一页跟着变；
3. 新页一开始只有 **2 根 K 线**，之后一会儿有一会儿没有（闪烁）。

根因：后端把实时页状态按**合约**存（`self.tabs[symbol]`、`page =
f'chart:{symbol}'`），而前端允许「同一合约开多页」（`chart:X~2`）→ 两页共享
同一份策略 / 布局；补丁又只喂「激活页」→ 另一页拿不到行情、或收到不属于它的
策略线。

修法（本文件护栏）：
* `page`（页签 id）随命令带上来 → 策略 / 布局存 `_page_infos[page]`；
* 行情 / 指标仍按合约共享（两页同一个合约，数据本来就一样）；
* `indicator_payload(symbol, page=...)` / `_remove_strategy_of(symbol, page=...)`
  只作用于那一页；
* 补丁带 `page` 时前端只给那一页，不带才按合约广播。
"""
import numpy as np
import pytest

from minibt.desk import protocol

pd = pytest.importorskip('pandas')

SYMBOL = 'SHFE.rb2610'


def _frame(rows: int = 200):
    rng = np.random.default_rng(7)
    close = 3600 + np.cumsum(rng.normal(0, 3, rows))
    return pd.DataFrame({
        'datetime': [(1_700_000_000 + index * 60) * 1_000_000_000
                     for index in range(rows)],
        'open': close - 1, 'high': close + 3, 'low': close - 3,
        'close': close, 'volume': rng.integers(10, 100, rows),
        'symbol': SYMBOL, 'duration': 60,
        'price_tick': 1.0, 'volume_multiple': 10,
    })


class _Feed:
    kind = 'futures'

    def __init__(self):
        self.frame = _frame()
        self.api = None

    def available(self):
        return True

    def contracts(self, ins_class, exchange):
        return [SYMBOL]

    def fill_names(self, symbols):
        return None

    def name_of(self, symbol):
        return '螺纹'

    def quotes(self, keys):
        return []

    def spec(self, symbol):
        return None

    def klines(self, symbol, cycle, length=500):
        return self.frame


def _desk():
    from minibt.desk.app import Desk

    desk = Desk(offline=True, allow_trading=False)
    desk.sent = []
    desk.sender = desk.sent.append
    desk.futures = _Feed()
    desk.feeds = [desk.futures]
    desk.offline = False
    desk._booted = True
    desk.filter = {'type': 'FUT', 'exchange': 'SHFE', 'text': ''}
    desk.tabs[SYMBOL] = {'feed': desk.futures, 'cycle': 60}
    desk._page_infos = {}
    return desk


def _patches(desk):
    import json
    out = []
    for script in desk.sent:
        if not script.startswith('window.__desk.applyPatch('):
            continue
        body = script[len('window.__desk.applyPatch('):-2]
        try:
            out.append(json.loads(body))
        except Exception:                                    # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------- 页级状态
def test_page_info_isolation():
    """`_page_info`：策略 / 布局本页独立，行情字段读合约级 ✓"""
    desk = _desk()
    desk.tabs[SYMBOL]['cycle'] = 60
    one = desk._page_info(f'chart:{SYMBOL}', SYMBOL)
    two = desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)

    one['strategy'] = {'name': 'KalmanFilterStrategy'}
    one['strategy_items'] = [{'key': 'editor:kalman'}]
    one['layout'] = {'cols': 2, 'rows': 1, 'symbols': ['A', 'B']}

    # 第二页：没有策略 / 没有自己的布局 → 回落到合约级（空）
    assert two.get('strategy') is None
    assert two.get('strategy_items') in (None, [])
    assert two.get('layout') is None
    # 行情字段仍共享 ✓
    assert two.get('cycle') == 60
    # 第一页自己的东西还在 ✓
    assert one.get('strategy_items') == [{'key': 'editor:kalman'}]


def test_page_symbol_from_tab_id():
    desk = _desk()
    assert desk._page_symbol(f'chart:{SYMBOL}') == SYMBOL
    assert desk._page_symbol(f'chart:{SYMBOL}~2') == SYMBOL
    assert desk._page_symbol('chart:SHFE.ag2612~3') == 'SHFE.ag2612'


def test_indicator_payload_is_per_page():
    """同一合约两页：`indicator_payload(page=…)` 只带**本页**的策略 ✓"""
    desk = _desk()
    one = desk._page_info(f'chart:{SYMBOL}', SYMBOL)
    one['strategy'] = {'name': 'KalmanFilterStrategy', 'path': 'x.py'}
    one['strategy_items'] = [{'key': f'editor:kalman:line:0',
                              'label': 'kalman', 'overlay': True,
                              'data': []}]

    payload_one = desk.indicator_payload(SYMBOL, page=f'chart:{SYMBOL}')
    payload_two = desk.indicator_payload(SYMBOL, page=f'chart:{SYMBOL}~2')
    assert payload_one['strategy'] == 'KalmanFilterStrategy'
    assert payload_one['items']
    # ★ 第二页不能继承第一页的策略（用户实测的"串联"）
    assert payload_two['strategy'] == ''
    assert not payload_two['items']
    # 补丁带 page（前端据此只喂这一页 ✓）
    assert payload_one['page'] == f'chart:{SYMBOL}'
    assert payload_two['page'] == f'chart:{SYMBOL}~2'


def test_remove_strategy_only_affects_one_page():
    desk = _desk()
    one = desk._page_info(f'chart:{SYMBOL}', SYMBOL)
    two = desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)
    for info in (one, two):
        info['strategy'] = {'name': 'S'}
        info['strategy_items'] = [{'key': 'editor:s'}]

    assert desk._remove_strategy_of(SYMBOL, page=f'chart:{SYMBOL}~2') is True
    assert not two.get('strategy_items')
    assert not two.get('strategy')
    # 另一页**不受影响** ✓
    assert one.get('strategy_items') == [{'key': 'editor:s'}]
    assert (one.get('strategy') or {}).get('name') == 'S'


def test_open_chart_tags_page_and_shares_market_data():
    """开第二页：行情补丁**不带** page（按合约广播），策略补丁**带** page ✓"""
    desk = _desk()
    desk.handle(protocol.encode_command({
        'cmd': 'open_chart',
        'payload': {'symbol': SYMBOL, 'page': f'chart:{SYMBOL}~2'},
    }))
    patches = _patches(desk)
    kinds = {}
    for patch in patches:
        kinds.setdefault(patch.get('type'), []).append(patch)
    # 开图必须给 K 线（不带 page → 同合约的每一页都吃 ✓）
    assert 'kline' in kinds
    assert kinds['kline'][-1].get('page') in (None, '')
    # 指标补丁带 page（只喂这一页）
    indicator = kinds.get('indicator') or []
    assert indicator, list(kinds)
    assert indicator[-1]['page'] == f'chart:{SYMBOL}~2'
    # 页级状态里没有策略（新页是干净的）
    info = desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)
    assert not info.get('strategy_items')


def test_duplicate_page_does_not_inherit_canonical_page():
    """用户 2026-11-20 第三次实测的真实场景 ✓

    第 1 页是**规范页**（`chart:SHFE.rb2610`，= 合约级 dict），策略 / 布局都写
    在那里；再从「＋ → 实时图表」开第 2 页（`…~2`）时：

    * 策略 / 布局**绝不能**回退读到合约级（否则新页继承 2 格布局 + 策略 + 持仓线 ✗）；
    * 行情字段（`cycle` / `feed` / K 线状态）仍要共享 ✓
    """
    desk = _desk()
    desk.tabs[SYMBOL]['cycle'] = 60
    one = desk._page_info(f'chart:{SYMBOL}', SYMBOL)      # 规范页 → 合约级
    one['strategy'] = {'name': 'KalmanFilterStrategy', 'path': 'x.py'}
    one['strategy_items'] = [{'key': 'editor:kalman'}]
    one['layout'] = {'cols': 2, 'rows': 1,
                     'symbols': ['DCE.l2701', 'DCE.pp2701'],
                     'cells': [{'symbol': 'DCE.l2701'},
                               {'symbol': 'DCE.pp2701'}]}
    one['strategy_contracts'] = ['DCE.l2701', 'DCE.pp2701']

    two = desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)
    assert two.get('strategy') is None            # ★ 不继承策略
    assert not two.get('strategy_items')
    assert two.get('layout') is None              # ★ 不继承 2 格布局
    assert not two.get('strategy_contracts')
    assert two.get('cycle') == 60                 # 行情共享 ✓
    # `'strategy' in info` 也不能被父级带进来
    assert 'strategy' not in two

    payload = desk.indicator_payload(SYMBOL, page=f'chart:{SYMBOL}~2')
    assert payload['strategy'] == ''
    assert not payload['items']


def test_refresh_indicators_pushes_one_payload_per_page():
    """行情节拍器重算指标时，**每页各推一份**（策略按页不同 ✓）

    以前只推一份（`page` 为空）→ 前端按合约广播 → 第二页也"长出"第一页的策略 ✗
    """
    desk = _desk()
    base = desk.tabs[SYMBOL]
    base['indicators'] = [{'key': 'MA'}]
    base['strategy'] = {'name': 'KalmanFilterStrategy', 'path': 'x.py'}
    base['strategy_items'] = [{'key': 'editor:kalman', 'overlay': True,
                              'data': []}]
    # 注册第二个页（用户在「＋ → 实时图表」里开出来的）
    desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)

    desk.sent.clear()
    desk._refresh_indicators(SYMBOL, base, [{'time': 1, 'close': 1.0}])
    patches = [p for p in _patches(desk)
               if p.get('type') == 'indicator'
               and 'strategy' in p]
    assert patches, '应至少推一份指标补丁'
    by_page = {str(p.get('page') or ''): p for p in patches}
    assert f'chart:{SYMBOL}' in by_page, by_page.keys()
    assert f'chart:{SYMBOL}~2' in by_page, by_page.keys()
    # 第一页带策略、第二页**不带**
    assert by_page[f'chart:{SYMBOL}']['strategy'] == 'KalmanFilterStrategy'
    assert by_page[f'chart:{SYMBOL}~2']['strategy'] == ''
    assert not [item for item in by_page[f'chart:{SYMBOL}~2']['items']
                if str(item.get('key') or '').startswith('editor:')]


def test_pages_of_lists_canonical_and_duplicates():
    desk = _desk()
    assert desk._pages_of(SYMBOL) == [f'chart:{SYMBOL}']
    desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)
    desk._page_info(f'chart:{SYMBOL}~3', SYMBOL)
    assert desk._pages_of(SYMBOL) == [f'chart:{SYMBOL}',
                                      f'chart:{SYMBOL}~2',
                                      f'chart:{SYMBOL}~3']
    # 别的合约不受影响
    assert desk._pages_of('SHFE.ag2612') == ['chart:SHFE.ag2612']


def test_cell_patches_are_page_tagged():
    """带 `cell` 的 K 线 / 持仓 / 挂单补丁必须带 `page`（规范页）✓

    以前不带 → 前端按合约广播 → 只开 1 格的第二页把 `cell=1` 的合约数据
    画进自己图上（表现为图上"多出 2 根不属于它的 K 线" + 一条 7991 的价格线 ✗）
    """
    desk = _desk()
    base = desk.tabs[SYMBOL]
    base['layout'] = {'cols': 2, 'rows': 1,
                      'symbols': [SYMBOL, 'DCE.l2701'],
                      'cells': [{'symbol': SYMBOL}, {'symbol': 'DCE.l2701'}],
                      'cycles': [60, 60]}
    desk._page_info(f'chart:{SYMBOL}~2', SYMBOL)      # 第二页（单格）
    desk.sent.clear()
    desk._push_cell_bars(SYMBOL, base)
    patches = _patches(desk)
    celled = [p for p in patches
              if isinstance(p.get('cell'), int) and int(p['cell']) >= 1]
    assert celled, [p.get('type') for p in patches]
    for patch in celled:
        assert patch.get('page') == f'chart:{SYMBOL}', patch.get('type')


def test_frontend_rename_sets_page_id_first():
    """`_renameChart` 必须**先** `setPageId(newId)` 再 `setSymbol(...)` ✓

    反过来的话：`setSymbol()` 内部会 `setCellSymbol()` / `_syncLayoutToBackend()`，
    那一刻 pageId 还是 `chart:<新合约>`（不带 `~N`）→ 把**这一页的布局**写进
    第一页 → 第一页格 2 变成这一页的合约（用户 2026-11-20 实测 ✗）
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    at = source.index('private _renameChart(')
    body = source[at:at + 2000]
    set_id = body.index('page.setPageId(newId);')
    set_symbol = body.index('page.setSymbol(newSymbol, name);')
    assert set_id < set_symbol, '必须先设 pageId 再 setSymbol'


def test_frontend_kline_routes_by_cell_index():
    """没带 `cell` 的 K 线补丁要按「该合约在这页布局里的格号」落位 ✓

    以前一律 `setBars()`（＝主图格 0）→ 第一页（格 0 = 策略合约 `DCE.l2701`）
    被另一页用的 `SHFE.ad2612` K 线覆盖 / 叠加 → "多了一个 ad2612"，且随行情
    一直存在（用户 2026-11-20 ✗）；不含该合约的多格页则**整条跳过** ✗
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    at = source.index("case 'kline': {")
    body = source[at:at + 1600]
    assert 'page.cellIndexOf(symbol)' in body
    assert 'page.cellCount > 1' in body and 'continue;' in body
    assert 'page.setCellBars(cell' in body


def test_chart_page_exposes_cell_count():
    """`ChartPage.cellCount`（多格页判定用 ✓）"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'jslib' / 'src' / 'desk' / 'chart-page.ts').read_text(
        encoding='utf-8')
    assert 'get cellCount(): number' in source


def test_frontend_open_tab_honors_page():
    """`open_tab` 补丁必须尊重 `page`（否则建第 2/3 个图表后跳回第一个 ✓）

    以前 `case 'open_tab'` 一律 `openChart(symbol)`（不带 forceNew）→ 按
    `chart:X` 去重 → `activate()` 第一页 → 用户点「＋ → 实时图表」建完
    界面自动跳回第一个实时图表（用户 2026-11-20 ✗）
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    at = source.index("case 'open_tab': {")
    body = source[at:at + 1200]
    assert 'this.pages.has(pageId)' in body and 'activate(pageId)' in body
    assert 'forceNew: !!pageId' in body
    # 补丁路由兜底：key 与 pageId 短暂不一致时按页面 `pageId` 再找一遍
    routing = source[source.index('private _pagesForPatch('):][:900]
    assert 'item.pageId === pageId' in routing


def test_strategy_progress_keeps_text_and_count():
    """参数优化进度：右上角「参数优化中… 0/30」必须随 trial 刷新 ✓

    以前前端 `if (text && total > 0)` 才写 `status`，而后端每个 trial 只推
    数字（`text` 为空）→ 文案**锁死在 0/30**，进度条都跑满了数字还是 0
    （用户 2026-11-20 ✗）
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    front = (root / 'jslib' / 'src' / 'desk' / 'strategy-lab-page.ts').read_text(
        encoding='utf-8')
    at = front.index('setProgress(current: number')
    body = front[at:at + 1600]
    assert '_progressText' in body
    assert 'if (text) this._progressText = text;' in body
    assert 'if (total > 0) {' in body

    back = (root / 'minibt' / 'desk' / 'strategy_lab.py').read_text(
        encoding='utf-8')
    at2 = back.index('def _push_progress(')
    body2 = back[at2:at2 + 900]
    assert "getattr(self, 'progress_text', '')" in body2


def test_optimize_warns_when_njobs_blocks_callbacks():
    """`n_jobs != 1` 时 Optuna 不回调 → 日志要说明（否则用户以为卡住了 ✓）"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    back = (root / 'minibt' / 'desk' / 'strategy_lab.py').read_text(
        encoding='utf-8')
    assert 'n_jobs != 1' in back and '不回调' in back

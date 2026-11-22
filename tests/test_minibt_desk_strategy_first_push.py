"""策略**第一次**加载就要把副图 / 各格策略线推全（v1.3.9-10）。

用户实测两条：

1. 第一次把策略加到图表 → **少一个副图指标**（第二次才齐）；
2. 多布局里第一次加载 → 只有主格有策略线。

根因：
* `_ind_cache` 以「最后一根 K 线时间 + close」做键；策略刚挂上时同一根 K 线
  没变 → `_refresh_indicators()` 直接 `return`，**新加的副图永远不推** ✗；
* 应用策略结果后只 `push(indicator_payload())`（主格），格 2..N 的
  `_push_cell_indicators()` 要等下一拍才发 ✗。
"""
from __future__ import annotations

import types

from minibt.desk.app import Desk


def _desk():
    desk = Desk.__new__(Desk)
    desk.pushed = []
    desk.logs = []
    desk.push = lambda patch: desk.pushed.append(patch)
    desk.push_log = lambda text, level='info': desk.logs.append((level, text))
    desk.tabs = {}
    desk._strategy_results = []
    desk._strategy_retries = []
    desk.tick_hooks = []
    return desk


def test_strategy_result_invalidates_indicator_cache():
    """应用策略结果后 `_ind_cache` 必须作废（否则同根 K 线跳过重算）✓"""
    desk = _desk()
    info = {'strategy': {'name': 'X', 'path': 'x.py'},
            'indicators': [{'key': 'PandasTa.macd'}],
            '_ind_cache': {'sig': 'a', 'time': 1, 'length': 10, 'close': 1.0}}
    desk.tabs['DCE.l2701'] = info
    item = {
        'symbol': 'DCE.l2701', 'path': 'x.py', 'cls': type('S', (), {}),
        'prepared': {'symbol': 'DCE.l2701', 'contracts': ['DCE.l2701']},
        'result': {'ok': True, 'items': [{'key': 'st:1'}],
                   'groups': {'DCE.l2701': [{'key': 'st:1'}]},
                   'name': 'X', 'runner': None},
        'live': False, 'payload': {},
    }
    desk.indicator_payload = lambda symbol, page='': {'type': 'indicator',
                                             'symbol': symbol, 'items': []}
    desk._push_cell_indicators = lambda symbol, info, page='': desk.pushed.append(
        {'type': 'cell_indicator', 'symbol': symbol})
    desk._apply_realtime_strategy_result(item)
    assert '_ind_cache' not in info, '策略挂上后没作废指标缓存 ✗'


def test_strategy_result_pushes_cell_indicators_immediately():
    """格 2..N 的策略线要**这一拍**就推，不依赖下一次 tick ✓"""
    desk = _desk()
    info = {'indicators': []}
    desk.tabs['DCE.l2701'] = info
    item = {
        'symbol': 'DCE.l2701', 'path': 'x.py', 'cls': type('S', (), {}),
        'prepared': {'symbol': 'DCE.l2701',
                     'contracts': ['DCE.l2701', 'DCE.pp2701']},
        'result': {'ok': True, 'items': [],
                   'groups': {'DCE.pp2701': [{'key': 'st:2'}]},
                   'name': 'X', 'runner': None},
        'live': False, 'payload': {},
    }
    desk.indicator_payload = lambda symbol, page='': {'type': 'indicator',
                                             'symbol': symbol}
    desk._push_cell_indicators = lambda symbol, info, page='': desk.pushed.append(
        {'type': 'cell_indicator', 'symbol': symbol})
    desk._apply_realtime_strategy_result(item)
    kinds = [patch.get('type') for patch in desk.pushed]
    assert 'cell_indicator' in kinds, kinds


def test_editor_minibt_path_applies_without_enable_flag(monkeypatch):
    """设置里**填了** minibt 路径就生效（以前必须再勾"启用"，用户以为无效 ✗）"""
    from minibt.desk import user_prefs as _prefs

    desk = _desk()
    monkeypatch.setattr(_prefs, 'settings',
                        lambda: {'editor_minibt_path':
                                 'C:/Users/Lenovo/Desktop/pylightcharts'})
    assert desk._editor_minibt_path() == 'C:/Users/Lenovo/Desktop/pylightcharts'

    # 显式关掉（勾选框取消）→ 不生效 ✓
    monkeypatch.setattr(_prefs, 'settings',
                        lambda: {'editor_minibt_path': 'C:/x',
                                 'editor_minibt_path_enabled': False})
    assert desk._editor_minibt_path() == ''

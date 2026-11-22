"""本地图表：应用布局要**先清空 + 可回滚**，且不要沿用旧策略（v1.3.9-15）。

用户实测 2026-11-16：

1. 两个**只存指标**的本地布局（pp_l_2609_60 / test1），应用时却弹出
   「策略合约不在本地数据里：DCE.l2701、DCE.pp2701」——
   那是**当前页面上一条策略**（test_8.py）的合约 ✗
   → 现在只认布局记录里真实保存的策略。
2. 应用第二个布局前没有清掉第一个布局的指标 → 图上**两套布局两套指标** ✗
   → 应用前 `_local_page_clear()`。
3. 加载中途出错应**回滚**到加载前 → `_local_page_snapshot()` /
   `_local_page_restore()`。
"""
from __future__ import annotations

from minibt.desk.app import Desk


def _desk():
    desk = Desk.__new__(Desk)
    desk.pushed = []
    desk.logs = []
    desk.push = lambda patch: desk.pushed.append(patch)
    desk.push_log = lambda text, level='info': desk.logs.append((level, text))
    desk.push_alert = lambda *a, **k: desk.logs.append(('alert', str(a[0])))
    desk._local_indicators = {'page1': {0: [{'key': 'PandasTa.sma'}]}}
    desk._local_strategies = {'page1': {'name': 'Kalman', 'path': '/x/y.py'}}
    desk._local_cell_names = {0: 'pp2609_60'}
    desk._active_local_page = 'page1'
    return desk


def test_snapshot_and_clear_and_restore():
    desk = _desk()
    snap = desk._local_page_snapshot()
    assert snap['items'][0][0]['key'] == 'PandasTa.sma'
    assert snap['strategy']['name'] == 'Kalman'

    desk._local_page_clear()
    assert desk._local_indicators['page1'] == {0: []}
    assert 'page1' not in desk._local_strategies
    assert desk._local_cell_names == {}
    # 清了就要把空补丁推给前端（否则旧线留在图上 ✓）
    assert any(patch.get('type') == 'local_indicator'
               and patch.get('items') == [] for patch in desk.pushed)

    desk._local_page_restore(snap)
    assert desk._local_indicators['page1'][0][0]['key'] == 'PandasTa.sma'
    assert desk._local_strategies['page1']['name'] == 'Kalman'
    assert desk._local_cell_names == {0: 'pp2609_60'}
    # 回滚必须说一声（warning 级别：不吓人但能看到 ✓）
    assert any(entry[1].startswith('布局加载失败') for entry in desk.logs)


def test_clear_pushes_per_cell_empty_patch():
    desk = _desk()
    desk._local_cell_names = {0: 'pp2609_60', 1: 'l2609_60'}
    desk._local_page_clear('page1')
    empties = [p for p in desk.pushed
               if p.get('type') == 'local_indicator' and p.get('items') == []]
    assert {p['symbol'] for p in empties} == {'pp2609_60', 'l2609_60'}
    assert all(p.get('page') == 'page1' for p in empties)

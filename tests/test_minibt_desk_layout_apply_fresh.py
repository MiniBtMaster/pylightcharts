"""应用布局：**先把旧合约的图清干净，再上新合约**（v1.3.9-13）。

用户实测（2026-11-16）：加载布局时如果当前图上的合约不是布局里的，
**旧合约的蜡烛会留在新图上**，要等下一次行情更新才消失 ✗。

两个原因：

1. **后端指纹没作废**：`_refresh_tabs` 判"要不要全量替换"看
   `_kline_bars_len` / `_kline_first_time`。两个合约同为 1 分钟、根数相同、
   首根时间也相同（很常见）时判不出变化 → 只推增量 2 根 → 旧蜡烛留着。
2. **前端把旧 K 线搬回新格**：`ChartPage.applyLayout()` 里有
   `keepBars`（为了"换布局预设但合约不变"时画面不闪），**换了合约也照搬** ✗。

修法：应用布局 / 换合约都 `_reset_kline_state()` + 清 `_cell_state`，
并**立刻**全量推格 1（`_push_cell0_bars()`）；前端只在该格合约未变时才保留旧 K 线，
变了就立刻清空。
"""
from __future__ import annotations

import types

from minibt.desk.app import Desk


class _Feed:
    kind = 'futures'
    api = None

    def __init__(self, frame):
        self._frame = frame

    def available(self):
        return True

    def klines(self, symbol, cycle, length):
        return self._frame


def _frame(n=30, base=9000.0):
    import pandas as pd
    times = pd.date_range('2026-11-16 09:00', periods=n, freq='1min',
                          tz='UTC')
    return pd.DataFrame({
        'datetime': times, 'open': [base] * n, 'high': [base + 1] * n,
        'low': [base - 1] * n, 'close': [base] * n, 'volume': [1] * n,
    })


def _desk(frame):
    desk = Desk.__new__(Desk)
    desk.feeds = [_Feed(frame)]
    desk.tabs = {}
    desk.pushed = []
    desk.logs = []
    desk.push = lambda patch: desk.pushed.append(patch)
    desk.push_log = lambda text, level='info': desk.logs.append((level, text))
    desk.data_length = lambda: 500
    desk.futures = None
    return desk


def test_push_cell0_bars_does_full_replace():
    """格 1 的新合约要**整份替换**（replace=True），不是增量 ✓"""
    desk = _desk(_frame())
    info = {'cycle': 60, 'feed': desk.feeds[0],
            'layout': {'symbols': ['DCE.pp2701'], 'cells': []}}
    ok = desk._push_cell0_bars('DCE.pp2701', info)
    assert ok is True
    kline = [p for p in desk.pushed if p.get('type') in ('kline', 'kline_batch')
             or 'bars' in p]
    assert kline, desk.pushed
    assert kline[-1].get('replace') is True, kline[-1].keys()
    # 指纹跟着更新（下一拍不会再全量重复推 ✓）
    assert info.get('_kline_bars_len') == 30
    assert info.get('_kline_first_time')


def test_push_cell0_bars_marks_cell_when_symbol_differs():
    """布局第 1 格不是 tab 名时，补丁要带 `cell: 0`（前端按格路由 ✓）"""
    desk = _desk(_frame())
    info = {'cycle': 60, 'feed': desk.feeds[0],
            'layout': {'symbols': ['DCE.l2701']}}
    desk._push_cell0_bars('DCE.pp2701', info)
    assert desk.pushed[-1].get('cell') == 0


def test_layout_apply_clears_fingerprints(monkeypatch):
    """应用布局时必须作废指纹（否则根数/首根时间相同 → 只推增量 ✗）"""
    desk = _desk(_frame())
    info = {'cycle': 60, 'feed': desk.feeds[0],
            '_kline_bars_len': 30, '_kline_first_time': 111,
            '_ind_cache': {'sig': 'x'}, '_cell_state': {1: (1, 2, 3)},
            '_cell_ind_at': {1: 1.0}}
    desk.tabs['DCE.pp2701'] = info
    # 打桩掉"需要真行情/偏好设置"的部分，只验指纹处理
    desk._push_cell_bars = lambda symbol, info: None
    desk._push_cell_indicators = lambda symbol, info: None
    desk._push_cell0_bars = lambda symbol, info: True
    desk.indicator_payload = lambda symbol: {'type': 'indicator'}
    monkeypatch.setattr('minibt.desk.user_prefs.find_layout',
                        lambda key, scope='realtime': {
                            'key': 'k1', 'name': '布局1', 'cols': 2,
                            'rows': 1, 'cycle': 60,
                            'cells': [{'symbol': 'DCE.l2701', 'indicators': []},
                                      {'symbol': 'DCE.pp2701',
                                       'indicators': []}]})
    desk._on_layout_apply({'key': 'k1', 'symbol': 'DCE.pp2701'})
    # 注意：`_on_layout_apply` 会 `dict(self.tabs[symbol])` 复制一份再写回
    info = desk.tabs['DCE.pp2701']
    assert '_kline_bars_len' not in info
    assert '_kline_first_time' not in info
    assert '_ind_cache' not in info
    assert '_cell_state' not in info
    assert '_cell_ind_at' not in info

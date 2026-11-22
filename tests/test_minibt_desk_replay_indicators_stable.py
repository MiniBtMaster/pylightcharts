"""回放反复切换时，第 2 格的指标不能越积越多（v1.3.9-20）。

用户实测 2026-11-17（K线回放.png）：在「K线回放」里不断切换时段，
第 2 格左上角的指标标签越来越多（`AdaptiveTrendTrail.*` 重复 4 遍）。

前端两条都修了：
* `setIndicators()` 回放分支以前**不看 `payload.cell`**，所有格的实时补丁都写进
  第 1 格的回放指标 → 换格就混两份；
* `setCellIndicators()` 里同一指标会以 `tv:X:line` / `X.line` 两种 key 口径进来
  → 图例两行 → 用 `dedupeIndicatorItems()` 去重。

这份测试盯**后端**：连开 3 次回放，payload 里每格的指标条数必须完全一致
（后端不能往布局的 indicators 里追加 ✗）。
"""
from __future__ import annotations

import os
import tempfile

import pandas as pd
import pytest

os.environ.setdefault('MINIBT_DESK_NO_INDEX', '1')


def _frame(count: int = 400) -> pd.DataFrame:
    index = range(count)
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': [8000.0 + i for i in index],
        'high': [8001.0 + i for i in index],
        'low': [7999.0 + i for i in index],
        'close': [8000.5 + i for i in index],
        'volume': [100 + i for i in index],
        'open_oi': [0] * count,
        'close_oi': [0] * count,
        'volume_multiple': [5.0] * count,
    })


class _Feed:
    def klines(self, symbol, cycle, count):
        return _frame(count)

    def spec(self, symbol):
        return None


@pytest.fixture()
def desk(monkeypatch):
    from minibt.desk import app as appmod, user_prefs

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        os.path.join(tmp, 'prefs.json'))
    desk = appmod.Desk(offline=True)
    sent: list = []
    desk.push = sent.append
    desk.push_log = lambda *a, **k: None
    desk.push_alert = lambda *a, **k: None
    feed = _Feed()
    symbol, cell_symbol = 'pp2609', 'l2609'
    indicators = [{'key': 'pta_sma', 'params': {'length': 10}}]
    cell_indicators = [{'key': 'tv:AdaptiveTrendTrail',
                        'params': {'trend_length': 34,
                                   'momentum_length': 12}}]
    desk.tabs = {symbol: {
        'cycle': 60, 'feed': feed, 'indicators': list(indicators),
        'layout': {'cells': [
            {'symbol': symbol, 'indicators': list(indicators)},
            {'symbol': cell_symbol, 'indicators': cell_indicators}]}}}
    desk.feeds = {symbol: feed}
    monkeypatch.setattr(appmod, 'pick_feed', lambda feeds, symbol: feed)
    desk.candles_length = lambda: 300
    desk.sent = sent
    return desk


def test_replay_payload_cell_counts_are_stable(desk):
    counts = []
    for _ in range(3):
        desk.sent.clear()
        desk._on_replay({'symbol': 'pp2609', 'count': 300, 'seek': 0.3})
        payload = next(p for p in desk.sent if p.get('type') == 'replay')
        counts.append([len(cell['indicators']) for cell in payload['cells']])
    assert counts[0] == counts[1] == counts[2], counts


def test_replay_does_not_grow_layout_indicators(desk):
    before = [len(cell['indicators'])
              for cell in desk.tabs['pp2609']['layout']['cells']]
    for _ in range(3):
        desk._on_replay({'symbol': 'pp2609', 'count': 300, 'seek': 0.3})
    after = [len(cell['indicators'])
             for cell in desk.tabs['pp2609']['layout']['cells']]
    assert after == before

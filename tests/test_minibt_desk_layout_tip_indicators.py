"""布局卡片里的指标清单：**每个指标一条**，框式指标（IndFrame）合并。

用户 2026-11-17：布局管理的悬停卡片把 `pta_adx` 的 4 条线
（adxx / adxr / dmp / dmn）全列出来，看不清有几个指标。
现在框式指标合并成 `pta_adx(14, 14, 100, rma, 1, 0)`，
单线指标（IndSeries）保持 `pta_sma:sma(10, true, 0)`。
"""
from __future__ import annotations

from minibt.desk.app import Desk

ADX_PARAMS = {'length': 14, 'lensig': 14, 'scalar': 100, 'mamode': 'rma',
              'drift': 1, 'offset': 0}


def _plain_ind(key: str, params: dict | None = None) -> dict:
    return {'key': key, 'params': dict(params or {})}


def test_single_line_series_keeps_line_name():
    items = [_plain_ind('pta_sma:sma',
                        {'length': 10, 'talib': True, 'offset': 0})]
    assert Desk._layout_tip_indicators(items) == ['pta_sma:sma(10, true, 0)']


def test_frame_indicator_merged_into_one_line():
    items = [_plain_ind(f'pta_adx:{name}', ADX_PARAMS)
             for name in ('adxx', 'adxr', 'dmp', 'dmn')]
    assert Desk._layout_tip_indicators(items) == [
        'pta_adx(14, 14, 100, rma, 1, 0)']


def test_mixed_series_and_frame_keep_order():
    items = [_plain_ind('pta_sma:sma',
                        {'length': 10, 'talib': True, 'offset': 0})]
    items += [_plain_ind(f'pta_adx:{name}', ADX_PARAMS)
              for name in ('adxx', 'adxr', 'dmp', 'dmn')]
    assert Desk._layout_tip_indicators(items) == [
        'pta_sma:sma(10, true, 0)', 'pta_adx(14, 14, 100, rma, 1, 0)']


def test_tradingview_multiline_merged():
    items = [_plain_ind(f'tv:AdaptiveTrendTrail:{name}',
                        {'trend_length': 34, 'momentum_length': 12})
             for name in ('trend', 'basis', 'inner_trail')]
    assert Desk._layout_tip_indicators(items) == [
        'tv:AdaptiveTrendTrail(34, 12)']


def test_strategy_lines_are_skipped():
    """策略线（editor: / st:）不进指标清单（策略单独一行 ✓）."""
    items = [_plain_ind('editor:CMOStrategy:line'),
             _plain_ind('st:pair:spread'),
             _plain_ind('pta_sma:sma', {'length': 10})]
    assert Desk._layout_tip_indicators(items) == ['pta_sma:sma(10)']


def test_long_params_are_truncated():
    params = {f'p{i}': i for i in range(16)}
    items = [_plain_ind(f'tv:Big:{name}', params) for name in ('a', 'b')]
    text = Desk._layout_tip_indicators(items)[0]
    assert text.startswith('tv:Big(0, 1, 2, 3, 4, 5, …+10)')
    assert text.count(',') <= 6


def test_layout_view_annotates_each_cell():
    record = {'key': 'k', 'name': 'pp_l_2609_60', 'scope': 'local',
              'cols': 1, 'rows': 1, 'cycle': 60,
              'cells': [{'symbol': 'pp_2609_60',
                         'indicators': [
                             _plain_ind('pta_sma:sma',
                                        {'length': 10, 'talib': True,
                                         'offset': 0})]
                         + [_plain_ind(f'pta_adx:{name}', ADX_PARAMS)
                            for name in ('adxx', 'adxr', 'dmp', 'dmn')]}]}
    view = Desk.__new__(Desk)._layout_view(record)
    cell = view['cells'][0]
    assert cell['tipIndicators'] == ['pta_sma:sma(10, true, 0)',
                                     'pta_adx(14, 14, 100, rma, 1, 0)']
    # 原始指标不能被改坏（应用布局还要用 ✓）
    assert len(cell['indicators']) == 5

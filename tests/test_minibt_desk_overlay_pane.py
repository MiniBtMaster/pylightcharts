"""主图叠加的条目：`pane` 必须是空（前端按 `overlay → paneIndex 0`）✓

后端多个链路都产出 ``{overlay, pane, ...}``：

* 指标目录 `indicator_catalog._to_items` / `_candle_item`
* 策略叠加 `strategy_overlay._candle_item_for` / 线条

以前 `strategy_overlay` 在 ``overlap=True`` 时仍写 ``pane='strategy'``，和指标
链路的 ``pane=''`` 不一致；前端目前先看 `overlay` 才没炸，但任何按 `pane`
走的渲染 / 老 bundle 都会把主图指标放进副图 ✗（用户 2026-11-2x 实测蜡烛主图
叠加失效）。
"""
from __future__ import annotations

import numpy as np


def _ohlc():
    return {'open': np.array([10.0, 11.0]),
            'high': np.array([12.0, 13.0]),
            'low': np.array([9.0, 10.0]),
            'close': np.array([11.0, 12.0])}


class _Spec:
    name = 'C'
    source = 'src'
    overlap = True
    candlestyle = {'bull': '#2196f3', 'bear': '#ff9800'}

    def __init__(self):
        self.ohlc = _ohlc()


def test_strategy_overlay_candle_pane_empty_on_overlay():
    from minibt.desk import strategy_overlay as overlay

    spec = _Spec()
    item = overlay._candle_item_for(spec, [100, 200])
    assert item is not None
    assert item['overlay'] is True
    assert item['pane'] == ''

    spec.overlap = False
    item = overlay._candle_item_for(spec, [100, 200])
    assert item['overlay'] is False
    assert item['pane'].startswith('strategy')


def test_catalog_candle_pane_empty_on_overlay():
    from minibt.desk import indicator_catalog as catalog

    columns = ['open', 'high', 'low', 'close']
    matrix = np.array([[10.0, 12.0, 9.0, 11.0],
                       [11.0, 13.0, 10.0, 12.0]])
    item = catalog._candle_item(columns, matrix, [100, 200],
                                {'name': 'C', 'overlap': True},
                                None, 'pi:x', np)
    assert item is not None
    assert item['overlay'] is True and item['pane'] == ''

    item = catalog._candle_item(columns, matrix, [100, 200],
                                {'name': 'C', 'overlap': False},
                                None, 'pi:x', np)
    assert item['overlay'] is False and item['pane'] == 'C'

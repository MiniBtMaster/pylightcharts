"""ZigZag 支撑 / 阻力线指标（v1.3.9-48，用户 2026-11-19 要求）。

* 用 `ZigZag` 找转折点（高低点）→ 最近一个转折点的价格画成**水平线**；
* 低点转折（1000）→ `support` = 1000，直到下一个高点出现；这期间 `resistance` 为 NaN；
* 高点转折（1100）→ `resistance` = 1100，直到下一个低点出现；这期间 `support` 为 NaN；
* 两条线：**3px 虚线**；
* 三处入口：`ta.ZigZag.zigzag_support_resistance` / `core.btind_zigzag_support_resistance`
  / `indicators/btind.zigzag_support_resistance` ✓
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _zigzag_frame() -> tuple[pd.DataFrame, pd.Series]:
    """造锯齿行情：1000 → 1100 → 1080 → 1200 → 1150 ✓"""
    prices = [1000, 1050, 1100, 1090, 1050, 1080, 1150, 1200, 1180, 1150]
    close = pd.Series([float(p) for p in prices])
    frame = pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=len(prices),
                                  freq='min'),
        'open': close, 'high': close + 5, 'low': close - 5, 'close': close,
        'volume': [100] * len(prices),
    })
    return frame, close


def test_support_then_resistance_flip():
    sys.path.insert(0, str(ROOT))
    from minibt.ta import ZigZag

    frame, _ = _zigzag_frame()
    sr = ZigZag.zigzag_support_resistance(
        frame.high, frame.low, frame.close, 0.01, 0.01, 1.)
    support = list(sr['support'].values)
    resistance = list(sr['resistance'].values)
    # 第 0 根是低点（995）→ 支撑 995，阻力 NaN ✓
    assert support[0] == 995.0 and math.isnan(resistance[0])
    assert support[1] == 995.0 and math.isnan(resistance[1])
    # 高点出现（1105）→ 阻力从这一根起 1105，支撑变 NaN ✓
    assert math.isnan(support[2]) and resistance[2] == 1105.0
    assert math.isnan(support[3]) and resistance[3] == 1105.0
    # 新的低点（1045）→ 支撑 1045，阻力 NaN ✓
    assert support[4] == 1045.0 and math.isnan(resistance[4])
    # 这段低点之后连续 3 根都保持支撑 1045 ✓
    assert support[5] == 1045.0 and support[6] == 1045.0
    # 新的高点（1205）→ 阻力 1205 ✓
    assert resistance[7] == 1205.0 and math.isnan(support[7])
    # 两条线**互斥**：任何一根最多只有一条有值 ✓
    for sup, res in zip(support, resistance):
        assert math.isnan(sup) or math.isnan(res)


def test_core_entry_and_btind_style():
    """三处入口都在，且线型是 3px 虚线 ✓"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    ta_src = (ROOT / 'minibt' / 'ta.py').read_text(encoding='utf-8')
    core_src = (ROOT / 'minibt' / 'core.py').read_text(encoding='utf-8')
    btind_src = (ROOT / 'minibt' / 'indicators' / 'btind.py').read_text(
        encoding='utf-8')
    assert 'def zigzag_support_resistance(' in ta_src
    assert 'def btind_zigzag_support_resistance(' in core_src
    assert 'def zigzag_support_resistance(' in btind_src
    # 3px 虚线（LineDash.dashed = 'dashed'）
    assert "line_width=3" in btind_src
    assert 'LineDash.dashed' in btind_src

    # 目录里能查到，且两条线都按 3px 虚线下发 ✓
    frame, _ = _zigzag_frame()
    items = cat.compute(frame, ['btind_zigzag_support_resistance'], {},
                        limit=len(frame))
    names = {item['key']: item for item in items}
    assert set(names) == {'btind_zigzag_support_resistance:support',
                          'btind_zigzag_support_resistance:resistance'}
    for item in names.values():
        assert item['kind'] == 'line'
        assert int(item['lineWidth']) == 3
        assert int(item['lineStyle']) == 2          # dashed ✓
        assert item['overlay'] is True              # 画在价格图上 ✓


def test_zigzag_sr_alias():
    sys.path.insert(0, str(ROOT))
    from minibt.ta import ZigZag

    assert ZigZag.zigzag_sr is not None
    frame, _ = _zigzag_frame()
    direct = ZigZag.zigzag_support_resistance(
        frame.high, frame.low, frame.close, 0.01, 0.01, 1.)
    alias = ZigZag.zigzag_sr(frame.high, frame.low, frame.close,
                            0.01, 0.01, 1.)
    assert np.allclose(direct['support'].fillna(-1),
                       alias['support'].fillna(-1))

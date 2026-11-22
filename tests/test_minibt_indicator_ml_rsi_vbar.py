"""`MachineLearningRSI`：副图 RSI 分段改成**柱体**（vbar_base=50，v1.3.9-41）。

用户 2026-11-18 要求：原来的分段**折线**改成柱体表示，柱底基线 50
（>50 向上、<50 向下），段色保留。
"""
from __future__ import annotations

import math
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _frame(count: int = 400) -> pd.DataFrame:
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': [8000.0 + (i % 20) for i in range(count)],
        'high': [8010.0 + (i % 20) for i in range(count)],
        'low': [7990.0 + (i % 20) for i in range(count)],
        'close': [8005.0 + (i % 20) for i in range(count)],
        'volume': [100] * count,
    })


def test_segments_are_bars_with_base_50():
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    items = cat.compute(_frame(), ['tv:MachineLearningRSI'], {}, limit=400)
    bars = {item['key'].rsplit(':', 1)[-1]: item for item in items
            if item.get('kind') == 'hist'}
    assert set(bars) >= {'rsi_bull', 'rsi_bear', 'rsi_neutral', 'rsi_gray'}
    for name, item in bars.items():
        assert float(item['base']) == 50.0, name          # vbar_base=50 ✓
        # 段色两侧同色（不跟 K 线涨跌色）
        assert item['upColor'] == item['downColor'], name
    assert bars['rsi_bull']['upColor'].upper() == '#00FFBB'
    assert bars['rsi_bear']['upColor'].upper() == '#FF1100'

    # 参考线 / 中轴仍是线（不是柱体 ✓）
    kinds = {item['key'].rsplit(':', 1)[-1]: item.get('kind')
             for item in items}
    for name in ('midline', 'upper', 'lower'):
        assert kinds[name] == 'line', name
    # RSI 本身仍是数据列（不画）
    assert kinds.get('rsi') in (None, 'line')


def test_segments_do_not_overlap():
    """分段柱体保留原来的"分段"语义（各自只在自己那段有值 ✓）"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    items = cat.compute(_frame(), ['tv:MachineLearningRSI'], {}, limit=400)
    spans = {}
    for item in items:
        if item.get('kind') != 'hist':
            continue
        values = [row[1] for row in item.get('data') or []]
        finite = [v for v in values
                  if isinstance(v, (int, float)) and math.isfinite(v)]
        spans[item['key'].rsplit(':', 1)[-1]] = finite
    assert spans['rsi_bull'] and spans['rsi_bear']
    assert min(spans['rsi_bull']) >= 50          # >50 的柱子朝上 ✓
    assert max(spans['rsi_bear']) <= 50          # <50 的柱子朝下 ✓

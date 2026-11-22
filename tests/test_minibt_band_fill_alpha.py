"""`BandStyle(fill_alpha=0.01)` 要真的生效（v1.3.9-47）。

用户 2026-11-19：`AdaptiveTrendTrail` 里
`bandstyle = BandStyle("basis", "depth_trail", fill_alpha=0.01,
                       fill_color=Colors.limegreen)`，填充看起来完全不透明。

根因：`indicator_catalog._rgba()` 只认 `#rrggbb` —— **命名色**（`limegreen`）
原样返回（没有 alpha）→ LWC 用不透明色填充，`fill_alpha` 形同虚设 ✗
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_rgba_handles_named_colors():
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    assert cat._rgba('limegreen', 0.01) == 'rgba(50,205,50,0.010)'
    assert cat._rgba('steelblue', 0.15) == 'rgba(70,130,180,0.150)'
    assert cat._rgba('#00ff00', 0.2) == 'rgba(0,255,0,0.200)'
    # 已经是 rgba（minibt 的 0~255 alpha）也要按**我们的** alpha 重写 ✓
    assert cat._rgba('rgba(39,157,130,100)', 0.3) == 'rgba(39,157,130,0.300)'
    # 认不出的原样返回（不崩 ✓）
    assert cat._rgba('not-a-color', 0.5) == 'not-a-color'


def test_adaptive_trend_trail_band_keeps_alpha():
    sys.path.insert(0, str(ROOT))
    import pandas as pd

    from minibt.desk import indicator_catalog as cat

    count = 200
    frame = pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': [8000.0 + (i % 7) for i in range(count)],
        'high': [8005.0 + (i % 7) for i in range(count)],
        'low': [7995.0 + (i % 7) for i in range(count)],
        'close': [8002.0 + (i % 7) for i in range(count)],
        'volume': [100] * count,
    })
    items = cat.compute(
        frame, ['tv:AdaptiveTrendTrail'],
        {'tv:AdaptiveTrendTrail': {'trend_length': 20,
                                   'momentum_length': 10}}, limit=count)
    bands = [item for item in items if item.get('kind') == 'band']
    assert bands, '没有算出色带'
    color = str(bands[0].get('color') or '')
    assert color.startswith('rgba('), color
    # 命名色（`steelblue`）也要带上 fill_alpha → 半透明（不能是实色）✓
    alpha = float(color.rsplit(',', 1)[1].rstrip(')'))
    assert 0 < alpha <= 0.2, color

"""进出回放 / 换合约时 `PlotInfo` 样式不能丢（v1.3.9-25）。

用户实测 2026-11-17：pp_l_2609_60 布局里 `AdaptiveTrendTrail` 有 `bandstyle`
色带，**进回放 / 退出回放后色带就没了**。

根因：`_dropEverything()`（交换约 / 进出回放时调用）只删序列，没清「挂在
序列上的样式」缓存（`bands` / `spans` / `tables` / `watermarks`）→ 序列重建后
`bands.has(key)` / `spanSig` 认为已经画过 → 直接 continue ✗

这份测试盯源码闸门 + 后端算出来的 band 条目（lowerKey / upperKey 必须齐 ✓）。
"""
from __future__ import annotations

import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / 'jslib' / 'src' / 'desk'


def test_drop_everything_clears_style_caches():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    body = layer.split('private _dropEverything(): void {', 1)[1]
    body = body.split('private ', 1)[0]
    for key in ('this.bands.clear();', 'this.spans.clear();',
                'this.spanSig.clear();', 'this.tables.clear();',
                'this.tableOffsets.clear();', 'this.watermarks.clear();'):
        assert key in body, key


def test_bandstyle_rebuilds_when_series_recreated():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    body = layer.split('private _applyBands(', 1)[1]
    body = body.split('private _applyTables(', 1)[0]
    # 挂在旧序列上的填充要拆掉重画（不是直接 continue ✓）
    assert 'const current = this._seriesOf(item.upperKey);' in body
    assert 'if (!current || current === cached.upper) continue;' in body
    assert 'this.bands.delete(item.key);' in body


def test_spanstyle_rebuilds_when_carrier_changed():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    body = layer.split('private _applySpans(', 1)[1]
    body = body.split('private _paneCarrier(', 1)[0]
    assert 'const live = this._liveCarrier();' in body
    assert 'drawnNow[0]?.series === live' in body
    # 只查不建（避免每拍多一条隐形载体 ✗）
    live = layer.split('private _liveCarrier(', 1)[1]
    live = live.split('private _paneCarrier(', 1)[0]
    assert 'addSeries' not in live


def test_backend_band_item_has_lower_and_upper():
    """`tv:AdaptiveTrendTrail` 的 bandstyle → `kind:'band'` + lowerKey/upperKey ✓"""
    import sys
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    count = 300
    frame = pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': [8000.0 + i for i in range(count)],
        'high': [8010.0 + i for i in range(count)],
        'low': [7990.0 + i for i in range(count)],
        'close': [8005.0 + i for i in range(count)],
        'volume': [100] * count,
    })
    params = {'trend_length': 34, 'momentum_length': 12, 'sensitivity': 0.35,
              'st_fast_length': 9, 'st_fast_factor': 1.45, 'st_mid_length': 14,
              'st_mid_factor': 1.9}
    items = cat.compute(frame, ['tv:AdaptiveTrendTrail'],
                        {'tv:AdaptiveTrendTrail': params}, limit=count)
    bands = [item for item in items if item.get('kind') == 'band']
    assert bands, '没有算出色带条目'
    assert bands[0].get('lowerKey') and bands[0].get('upperKey')

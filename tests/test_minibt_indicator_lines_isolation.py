"""指标线名**不能串到别的指标**（v1.3.9-51，用户 2026-11-19）。

用户实测：`G_Channels`（thresh=0，本该只有 a/b/avg 三条线）在 desk 上多出
`dsav` / `base_line` / `upper` / `lower` 4 条线。

根因：`next()` 里 `self.lines.xxx = ...` 写的是**源数据（KLine）**的
`_plotinfo.lines` —— 同一个 KLine 实例上**共享**的容器，上一个指标写过的线名
（`DynamicSwingAnchoredVWAP` 的 `dsav`、`Twin_Range_Filter` 的 base_line…）
不会消失 → 下一个指标凭空多出几条线 ✗

修法：跑指标前把它换成**本次指标的干净容器**（并带上 `__init__` 里写过的数据），
跑完**还原**，KLine 自己不被污染 ✓
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _kline(count: int = 150):
    sys.path.insert(0, str(ROOT))
    from minibt.indicators.core import KLine

    rng = np.random.default_rng(5)
    close = pd.Series(8000 + np.cumsum(rng.normal(0, 6, count)))
    frame = pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': close, 'high': close + 5, 'low': close - 5, 'close': close,
        'volume': [100] * count,
    })
    return KLine(frame, duration_seconds=60, data_length=None)


def test_g_channels_does_not_inherit_other_indicators_lines():
    from minibt.indicators import tradingview as tv

    kline = _kline()
    # 先跑一个会写 `dsav` 的指标（即使它内部报错，线名也可能被写进去）
    try:
        tv.DynamicSwingAnchoredVWAP(kline)
    except Exception:                                            # noqa: BLE001
        ...
    out = tv.G_Channels(kline, thresh=0.)
    columns = list(out.pandas_object.columns)
    assert columns == ['a', 'b', 'avg'], columns
    # thresh 在 (0,1) 时才多 `zig` ✓
    zig = tv.G_Channels(kline, thresh=0.5)
    assert list(zig.pandas_object.columns) == ['a', 'b', 'avg', 'zig']
    # 再跑一次 thresh=0 → 不会残留上一次的 zig ✓
    again = tv.G_Channels(kline, thresh=0.)
    assert list(again.pandas_object.columns) == ['a', 'b', 'avg']


def test_source_kline_lines_not_polluted():
    from minibt.indicators import tradingview as tv

    kline = _kline()
    before = list(getattr(kline, 'lines', []))
    try:
        tv.DynamicSwingAnchoredVWAP(kline)
    except Exception:                                            # noqa: BLE001
        ...
    tv.G_Channels(kline)
    assert list(getattr(kline, 'lines', [])) == before


def test_init_written_lines_still_work():
    """`__init__` 里 `self.lines.xxx = ...` 这种写法必须继续可用 ✓"""
    from minibt.indicators.base import tobtind
    from minibt.indicators.core import BtIndicator

    class ha_lines(BtIndicator):
        lines = ('open', 'high', 'low', 'close')

        def __init__(self):
            ha = self.ha()
            self.lines.open = ha.open
            self.lines.high = ha.high
            self.lines.low = ha.low
            self.lines.close = ha.close

    out = ha_lines(_kline())
    assert list(out.pandas_object.columns) == ['open', 'high', 'low', 'close']
    assert tobtind is not None

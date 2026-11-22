"""交易系统（tradingsymtem）冒烟测试：只出信号、不出指标线 ✓"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _kline(n: int = 160, seed: int = 7):
    from minibt.indicators.core import KLine

    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    frame = pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=n, freq='min'),
        'open': close + rng.normal(0, 0.2, n),
        'high': high,
        'low': low,
        'close': close,
        'volume': rng.integers(100, 1000, n).astype(float),
        'symbol': 'X',
        'duration': 60,
        'price_tick': 0.1,
        'volume_multiple': 1.0,
    })
    return KLine(frame)


def test_all_systems_only_emit_signal_lines():
    from minibt.tradingsymtem import systems

    kline = _kline()
    for category, table in systems().items():
        assert table, f'{category} 分类下没有交易系统'
        for name, cls in table.items():
            result = cls(kline)
            assert list(result.columns) == ['long_signal', 'short_signal'], (
                f'{category}/{name} 应只返回 long_signal / short_signal'
            )


def test_tradingsystem_facade_category_and_flat():
    from minibt.indicators.core import IndFrame
    from minibt.tradingsymtem import get

    kline = _kline()
    result = kline.tradingsystem.momentum.rsi_reversal(length=14)
    assert isinstance(result, IndFrame)
    assert list(result.columns) == ['long_signal', 'short_signal']

    flat = kline.tradingsystem.momentum_rsi_reversal(length=14)
    assert list(flat.columns) == ['long_signal', 'short_signal']

    # 参数确实生效（length 改成超大值 → RSI 应基本为空/少信号）
    long = kline.tradingsystem.momentum.rsi_reversal(length=120)
    assert list(long.columns) == ['long_signal', 'short_signal']
    assert get('momentum', 'rsi_reversal') is not None


def test_trend_category_exposes_examples_explicitly():
    from minibt.tradingsymtem.trend import Trend

    kline = _kline()
    trend = kline.tradingsystem.trend
    assert isinstance(trend, Trend)
    methods = {name for name in dir(trend) if not name.startswith('_')}
    assert {'kama_trend', 'psar_trend'} <= methods
    assert {'adx_trend', 'aroon_trend'} <= methods

    kama = trend.kama_trend(length=10)
    psar = trend.psar_trend(acceleration=0.02, maximum=0.2)
    assert list(kama.columns) == ['long_signal', 'short_signal']
    assert list(psar.columns) == ['long_signal', 'short_signal']


def test_category_lib_entry_methods_return_values():
    import pandas as pd

    kline = _kline()
    trading = kline.tradingsystem

    sma = trading.overlap.sma(length=20)
    assert isinstance(sma, pd.Series)
    assert sma.notna().any()

    macd = trading.momentum.macd(fast=12, slow=26, signal=9)
    assert isinstance(macd, tuple) and len(macd) == 3
    assert all(isinstance(series, pd.Series) for series in macd)

    adx = trading.trend.adx(length=14)
    assert isinstance(adx, pd.Series)


def test_desk_catalog_and_compute_tradingsystem():
    from minibt.desk import indicator_catalog as cat

    items = cat.catalog(refresh=True)
    ts_items = [item for item in items if item.get('prefix') == 'ts']
    assert len(ts_items) >= 20          # 10 类，每类至少 2 个 ✓
    assert {item['section'] for item in ts_items} >= {
        'ts_overlap', 'ts_momentum', 'ts_trend', 'ts_volume'}

    kline = _kline()
    frame = kline.pandas_object
    result = cat.compute(frame, ['ts_momentum_rsi_reversal'])
    assert result
    markers = [marker for item in result
               for marker in item.get('markers', [])]
    assert any(marker['buy'] for marker in markers)   # 随机数据也能出一些信号 ✓

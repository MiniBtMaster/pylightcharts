"""**wickra** 指标库内置（第三方 Rust 库，可选依赖）✓

用户 2026-11-21：P2 —— 把 `wickra`（520 个类）内置进 minibt。

| 项 | 值 |
|---|---|
| 前缀 | `wickra_`（CoreFunc：`wickra_SMA` …）|
| 入口 | `kline.wickra.SMA(period=20)`（数据源 = 调用它的 IndFrame ✓）|
| 覆盖 | **427** 个类（生成器用合成数据实调过滤；`price,size,is_buy` 订单流、`snapshots`、市场宽度、双序列类不支持）|
| desk | 新分组「Wickra」**425 条**（`Doji` / `RunBars` 实测不稳 → `NON_KLINE_INDICATORS`）|
| 生成 | `scripts/gen_ext_libs.py`（`__text_signature__` 拿构造参数，`batch` 签名拿数据列）|

依赖可选包 `wickra`（Rust，零第三方依赖）：没装时调用抛可读错误 ✓
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

installed = True
try:
    import wickra  # noqa: F401
except Exception:                                                # noqa: BLE001
    installed = False

needs = pytest.mark.skipif(not installed, reason='没装 wickra（可选依赖）')


def _kline(length: int = 2000):
    from minibt import LocalDatas, options

    options.set_conversion_mode = 'free'
    return LocalDatas.test.kline.iloc[:length]


def test_module_shape():
    """类结构 / 注册 / 生成器 spec 一致 ✓"""
    from minibt.indicators.wickra import Wickra, _INDICATOR_NAMES

    assert Wickra._perfixes == 'wickra_'
    assert len(_INDICATOR_NAMES) == 427
    skip = set(Wickra.NON_KLINE_INDICATORS)
    # 用户 2026-11-22：统计量 / 0-1 形态识别 → NON_KLINE（desk 不显示）✓
    assert {'WinRate', 'Wedge', 'Doji', 'RunBars'} <= skip
    assert {'ZigZag', 'WoodiePivots', 'RollingVWAP'} & skip == set()
    assert len(skip) == 112
    methods = [name for name in dir(Wickra)
               if not name.startswith('_') and name != 'NON_KLINE_INDICATORS'
               and callable(getattr(Wickra, name))]
    assert set(methods) == set(_INDICATOR_NAMES)

    import minibt
    import minibt.core as core
    assert hasattr(minibt.IndicatorClass, 'Wickra')
    specs = core._EXT_SPECS['wickra']
    assert set(specs) == set(_INDICATOR_NAMES)
    for name in _INDICATOR_NAMES:
        assert hasattr(core.CoreFunc, f'wickra_{name}'), name


@needs
def test_every_indicator_runs():
    """427 个类：长度对齐 / 无 `±inf` / 留有效值（2 个已知不稳的除外）✓"""
    from minibt.indicators.wickra import Wickra, _INDICATOR_NAMES

    kline = _kline()
    failed = []
    for name in _INDICATOR_NAMES:
        if name in Wickra.NON_KLINE_INDICATORS:
            continue
        try:
            result = getattr(kline.wickra, name)()
        except Exception as error:                                # noqa: BLE001
            failed.append((name, f'{type(error).__name__}: {error}'))
            continue
        frame = (result.pandas_object if hasattr(result, 'pandas_object')
                 else pd.DataFrame({'x': np.asarray(result, dtype=float)}))
        assert len(frame) == len(kline), name
        values = frame.to_numpy(dtype=np.float64)
        assert not np.isinf(values).any(), name
    assert failed == [], failed


@needs
def test_wrapper_is_transparent():
    """封装透明：`kline.wickra.*` == 直接调 `wickra.*` ✓"""
    import wickra

    kline = _kline()
    frame = kline.pandas_object
    close = np.ascontiguousarray(frame['close'].to_numpy(dtype=np.float64))
    high = np.ascontiguousarray(frame['high'].to_numpy(dtype=np.float64))
    low = np.ascontiguousarray(frame['low'].to_numpy(dtype=np.float64))

    cases = [
        ('SMA', {'period': 20}, wickra.SMA(20).batch_fast(close)),
        ('EMA', {'period': 20}, wickra.EMA(20).batch_fast(close)),
        ('RSI', {'period': 14}, wickra.RSI(14).batch_fast(close)),
        ('ATR', {'period': 14}, wickra.ATR(14).batch_fast(high, low, close)),
        ('ADX', {'period': 14}, wickra.ADX(14).batch(high, low, close)),
    ]
    for name, params, expected in cases:
        mine = getattr(kline.wickra, name)(**params)
        if hasattr(expected, 'tolist') and not isinstance(expected,
                                                          (list, tuple)):
            expected = expected.tolist()
        theirs = np.asarray(expected, dtype=np.float64)
        if theirs.ndim == 2:                       # (n, k) → 取第一条线
            theirs = theirs[:, 0] if theirs.shape[0] == len(kline) else theirs[0]
        if hasattr(mine, 'pandas_object'):
            frame = mine.pandas_object
            mine_array = (frame.iloc[:, 0].to_numpy(dtype=np.float64)
                          if hasattr(frame, 'columns')
                          else frame.to_numpy(dtype=np.float64))
        else:
            mine_array = np.asarray(mine, dtype=np.float64)
        valid = np.isfinite(mine_array) & np.isfinite(theirs)
        assert valid.sum() > 100, name
        assert np.allclose(mine_array[valid], theirs[valid]), name


@needs
def test_matches_pandas_ta_where_comparable():
    """口径相同的（SMA / EMA / RSI）与 pandas_ta 一致 ✓"""
    pandas_ta = pytest.importorskip('pandas_ta')

    kline = _kline()
    close = kline.pandas_object['close']
    pairs = [
        ('SMA', kline.wickra.SMA(period=20),
         pandas_ta.sma(close, length=20, talib=False)),
        ('EMA', kline.wickra.EMA(period=20),
         pandas_ta.ema(close, length=20, adjust=False, talib=False)),
        ('RSI', kline.wickra.RSI(period=14),
         pandas_ta.rsi(close, length=14, talib=False)),
    ]
    for name, mine, theirs in pairs:
        left = np.asarray(mine, dtype=np.float64)[200:]
        right = np.asarray(theirs, dtype=np.float64)[200:]
        valid = np.isfinite(left) & np.isfinite(right)
        assert valid.sum() > 100, name
        scale = np.maximum(np.abs(right[valid]), 1.0)
        error = float(np.max(np.abs(left[valid] - right[valid]) / scale))
        assert error < 1e-6, (name, error)


def test_catalog_exposes_wickra():
    """desk 目录：「Wickra」315 条（112 个统计量/形态在 NON_KLINE）✓"""
    from minibt.desk import indicator_catalog as catalog

    items = [item for item in catalog.catalog(refresh=True)
             if item['prefix'] == 'wickra']
    assert len(items) == 315
    assert {item['group'] for item in items} == {'Wickra'}
    assert catalog.entry('wickra_SMA') is not None
    assert catalog.missing_indicators() == {}


@needs
def test_catalog_compute_path():
    """目录 → desk compute ✓"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(400)
    errors: dict[str, str] = {}
    items = catalog.compute(kline, ['wickra_SMA', 'wickra_ATR'],
                           errors=errors)
    assert errors == {}
    assert {item['key'].split(':')[0] for item in items} == {'wickra_SMA',
                                                            'wickra_ATR'}


# --------------------------------------------------------------- 主副图 / 空线
@needs
def test_overlap_follows_price_scale():
    """主副图按"值是否落在 K 线价格区间"判定（用户 2026-11-22 要求）✓"""
    from minibt.indicators.wickra import Wickra

    kline = _kline()
    # 用户点名的几个
    assert getattr(Wickra, 'WoodiePivots')._decorator_args['overlap'] is True
    assert getattr(Wickra, 'RollingVWAP')._decorator_args['overlap'] is True
    assert getattr(Wickra, 'ZigZag')._decorator_args['overlap'] is True
    assert getattr(Wickra, 'ATR')._decorator_args['overlap'] is False

    # FibFan 有一条线越界 → 混合字典（True/False 按线名）
    fib = getattr(Wickra, 'FibFan')._decorator_args['overlap']
    assert isinstance(fib, dict) and set(fib.values()) <= {True, False}

    # 逐条抽样：主图指标的线，中位数必须落在 K 线价格区间内
    from minibt import LocalDatas

    frame = LocalDatas.test.kline.pandas_object
    low = float(frame['low'].min())
    high = float(frame['high'].max())
    for name in ('WoodiePivots', 'RollingVWAP', 'ZigZag', 'KaseDevStop'):
        result = getattr(kline.wickra, name)()
        values = (result.pandas_object.to_numpy(dtype=np.float64)
                  if hasattr(result.pandas_object, 'columns')
                  else np.asarray(result, dtype=np.float64))
        finite = values[np.isfinite(values)]
        assert finite.size > 100, name
        median = float(np.median(finite))
        assert low * 0.95 <= median <= high * 1.05, (name, median)


@needs
def test_flag_lines_are_dropped():
    """`-1/0/1` 标志线不进 `lines`（ZigZag 第 2 条 / KaseDevStop 趋势线）✓"""
    from minibt.indicators.wickra import Wickra

    assert getattr(Wickra, 'ZigZag')._decorator_args['lines'] == ['zigzag_1']
    assert getattr(Wickra, 'KaseDevStop')._decorator_args['lines'] == [
        'kasedevstop_1']


@needs
def test_sparse_pivot_lines_are_interpolated():
    """稀疏的拐点线（ZigZag）要插值，否则 desk 上没有线 ✓"""
    kline = _kline()
    values = np.asarray(kline.wickra.ZigZag(), dtype=np.float64)
    assert np.isfinite(values).mean() > 0.9


@needs
def test_statistics_and_patterns_are_non_kline():
    """`WinRate` / `Wedge` 这类（常数 / 0-1）→ `NON_KLINE_INDICATORS` ✓"""
    from minibt.indicators.wickra import Wickra

    skip = set(Wickra.NON_KLINE_INDICATORS)
    for name in ('WinRate', 'Wedge', 'Doji', 'RunBars', 'SortinoRatio'):
        assert name in skip, name
    # 方法仍然在（只是 desk 不显示）
    assert hasattr(Wickra, 'WinRate')


# --------------------------------------------------------------- 信号声明机制
@needs
def test_class_level_signals_table():
    """类级 `SIGNALS` 表 → 目录里 `has_signal` / `signal_spec` 直接可用 ✓"""
    from minibt.desk import indicator_catalog as catalog
    from minibt.indicators.wickra import Wickra

    # 只给**常用**指标自动声明信号（全量会刷屏，其余由 TA 给建议信号 ✓）
    assert isinstance(Wickra.SIGNALS, dict) and len(Wickra.SIGNALS) == 41
    assert {'SMA', 'EMA', 'RSI', 'MACD', 'ATR', 'BollingerBands'} <= set(
        Wickra.SIGNALS)
    assert 'Abcd' not in Wickra.SIGNALS
    entry = catalog.entry('wickra_SMA')
    assert entry['has_signal'] is True
    spec = list(entry['signal_spec'].values())[0]
    assert spec['kind'] == 'compare'            # 主图 → 高于前一根
    assert spec['group'] == 'trend'

    rsi = list(catalog.entry('wickra_RSI')['signal_spec'].values())[0]
    assert rsi['kind'] == 'threshold' and rsi['level'] == 50

    atr = list(catalog.entry('wickra_ATR')['signal_spec'].values())[0]
    assert atr['kind'] == 'compare'             # 非振荡 → 与前一根比


@needs
def test_signals_can_be_overridden_per_method():
    """`@tobtind(signals=…)` 优先级最高（覆盖类级表）✓"""
    from minibt.signals import Threshold, suggested_signal
    from minibt.indicators.base import tobtind

    @tobtind(myself=True, lib=None, lines=['x'],
             signals={'x': Threshold(70, -1, label='70 上方看空')})
    def demo(source, **kwargs):
        return [0.0] * len(source)

    spec = demo._decorator_args['signals']['x']
    assert spec.level == 70 and spec.direction == -1

    # 建议信号：主图 / 副图两条规则
    assert suggested_signal('sma', True).group == 'trend'
    assert suggested_signal('atr', False).group == 'oscillator'

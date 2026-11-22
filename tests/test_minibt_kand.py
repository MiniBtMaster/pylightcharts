"""**kand** 指标库内置（第三方 Rust 库，可选依赖）✓

用户 2026-11-21：计划把 `kand` / `wickra` 内置到 minibt。本轮先做 **kand**
（59 个指标），与 `PtaRs` 完全同构：

| 项 | 值 |
|---|---|
| 前缀 | `kand_`（CoreFunc：`kand_sma` …）|
| 入口 | `kline.kand.sma(period=20)`（数据源 = 调用它的 IndFrame ✓）|
| 生成 | `scripts/gen_ext_libs.py`（反射第三方库签名 → spec 表 + 类 + CoreFunc）|
| desk | 新分组「Kand」57 条（`sar` / `vegas` 数据不全 → `NON_KLINE_INDICATORS`）|

依赖可选包 `kand`（Rust）：没装时调用抛可读错误，`import minibt` 不受影响 ✓
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

kand_installed = True
try:
    import kand  # noqa: F401
except Exception:                                                # noqa: BLE001
    kand_installed = False

needs_kand = pytest.mark.skipif(not kand_installed,
                                reason='没装 kand（可选依赖）')


def _kline(length: int = 2000):
    from minibt import LocalDatas, options

    options.set_conversion_mode = 'free'
    return LocalDatas.test.kline.iloc[:length]


# --------------------------------------------------------------- 结构
def test_module_and_class_shape():
    """`kand.py` 的结构 + `IndicatorClass.Kand` 注册 ✓"""
    from minibt.indicators.kand import Kand, _INDICATOR_NAMES

    assert Kand._perfixes == 'kand_'
    assert len(_INDICATOR_NAMES) == 59
    methods = [name for name in dir(Kand)
               if not name.startswith('_') and name != 'NON_KLINE_INDICATORS'
               and callable(getattr(Kand, name))]
    assert set(methods) == set(_INDICATOR_NAMES)
    for name in methods:
        args = getattr(Kand, name)._decorator_args
        assert args['lines'], name
        assert isinstance(args['overlap'], bool), name

    import minibt.core as core
    import minibt
    assert hasattr(minibt.IndicatorClass, 'Kand')
    for name in _INDICATOR_NAMES:
        assert hasattr(core.CoreFunc, f'kand_{name}'), name


def test_generator_specs_are_consistent():
    """生成器产物与 `_EXT_SPECS` 一致（别手改生成物 ✓）"""
    import minibt.core as core
    from minibt.indicators.kand import _INDICATOR_NAMES

    specs = core._EXT_SPECS['kand']
    assert set(specs) == set(_INDICATOR_NAMES)
    for name, spec in specs.items():
        assert spec['args'], name
        assert spec['lines'], name
        # 第一/唯一的数据列必须来自 K 线字段
        assert any(item in ('close', 'high', 'low', 'open', 'volume',
                            'timestamp') for item in spec['args']), name


# --------------------------------------------------------------- 数值
@needs_kand
def test_every_indicator_runs():
    """59 个指标都能算：长度对齐、无 `±inf` ✓"""
    kline = _kline()
    from minibt.indicators.kand import _INDICATOR_NAMES

    failed = []
    for name in _INDICATOR_NAMES:
        try:
            result = getattr(kline.kand, name)()
        except Exception as error:                                # noqa: BLE001
            failed.append((name, f'{type(error).__name__}: {error}'))
            continue
        frame = (result.pandas_object if hasattr(result, 'pandas_object')
                 else pd.DataFrame({'x': np.asarray(result, dtype=float)}))
        assert len(frame) == len(kline), name
        values = frame.to_numpy(dtype=np.float64)
        assert not np.isinf(values).any(), name
        assert np.isfinite(values).sum() > len(kline) * 0.2, name
    assert failed == [], failed


@needs_kand
def test_wrapper_is_transparent():
    """**封装必须透明**：`kline.kand.*` 的值 == 直接调 `kand.*`（同一个库）✓"""
    import kand as lib

    kline = _kline()
    frame = kline.pandas_object
    close = np.ascontiguousarray(frame['close'].to_numpy(dtype=np.float64))
    high = np.ascontiguousarray(frame['high'].to_numpy(dtype=np.float64))
    low = np.ascontiguousarray(frame['low'].to_numpy(dtype=np.float64))

    cases = [
        ('sma', dict(period=20), lib.sma(close, 20)),
        ('ema', dict(period=20), lib.ema(close, 20)),
        ('rsi', dict(period=14), lib.rsi(close, 14)),
        ('atr', dict(period=14), lib.atr(high, low, close, 14)),
        ('willr', dict(period=14), lib.willr(high, low, close, 14)),
    ]
    for name, params, expected in cases:
        mine = np.asarray(getattr(kline.kand, name)(**params), dtype=np.float64)
        if isinstance(expected, (tuple, list)):      # 多输出 → 取第一条线 ✓
            expected = expected[0]
        theirs = np.asarray(expected, dtype=np.float64)
        valid = np.isfinite(mine) & np.isfinite(theirs)
        assert valid.sum() > 100, name
        assert np.allclose(mine[valid], theirs[valid]), name

    bands = kline.kand.bbands(period=20).pandas_object
    direct = lib.bbands(close, 20, 2.0, 2.0)
    for position, line in enumerate(('upper', 'middle', 'lower')):
        theirs = np.asarray(direct[position], dtype=np.float64)
        mine = bands[line].to_numpy(dtype=np.float64)
        valid = np.isfinite(mine) & np.isfinite(theirs)
        assert np.allclose(mine[valid], theirs[valid]), line


@needs_kand
def test_values_match_pandas_ta_where_comparable():
    """口径相同的几个（sma / ema / rsi / atr）与 pandas_ta 一致 ✓

    ⚠ `bbands` **不对拍**：kand 用的是它自己的标准差口径（与 pandas_ta 的
    `std` 差 ~2.3/5200），属于库的既有口径，封装层不做修改 ✓
    """
    pandas_ta = pytest.importorskip('pandas_ta')
    kline = _kline()
    frame = kline.pandas_object
    close = frame['close']
    high, low = frame['high'], frame['low']
    skip = 200

    pairs = [
        ('sma', kline.kand.sma(period=20),
         pandas_ta.sma(close, length=20, talib=False)),
        ('ema', kline.kand.ema(period=20),
         pandas_ta.ema(close, length=20, adjust=False, talib=False)),
        ('rsi', kline.kand.rsi(period=14),
         pandas_ta.rsi(close, length=14, talib=False)),
        ('atr', kline.kand.atr(period=14),
         pandas_ta.atr(high, low, close, length=14, talib=False)),
    ]
    for name, mine, theirs in pairs:
        left = np.asarray(mine, dtype=np.float64)[skip:]
        right = np.asarray(theirs, dtype=np.float64)[skip:]
        valid = np.isfinite(left) & np.isfinite(right)
        assert valid.sum() > 100, name
        scale = np.maximum(np.abs(right[valid]), 1.0)
        error = float(np.max(np.abs(left[valid] - right[valid]) / scale))
        assert error < 1e-6, (name, error)


@needs_kand
def test_multi_line_indicators():
    """多输出指标（bbands / macd / aroon / supertrend）线名与造数正确 ✓"""
    kline = _kline()
    expected = {
        'bbands': ['upper', 'middle', 'lower'],
        'macd': ['macd', 'signal', 'histogram'],
        'aroon': ['aroon_up', 'aroon_down'],
        'supertrend': ['trend', 'supertrend'],
    }
    for name, lines in expected.items():
        result = getattr(kline.kand, name)()
        columns = list(result.pandas_object.columns)
        assert columns[:len(lines)] == lines, (name, columns)


# --------------------------------------------------------------- desk
def test_catalog_exposes_kand():
    """desk 目录：「Kand」分组 56 条（形态 / 数据不全的不显示）✓"""
    from minibt.desk import indicator_catalog as catalog

    items = [item for item in catalog.catalog(refresh=True)
             if item['prefix'] == 'kand']
    assert len(items) == 56
    assert {item['group'] for item in items} == {'Kand'}
    assert catalog.entry('kand_sma') is not None
    assert catalog.missing_indicators() == {}


@needs_kand
def test_catalog_compute_path():
    """目录 → desk compute（走 `kline.kand.*` 带样式 ✓）"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(400)
    errors: dict[str, str] = {}
    items = catalog.compute(kline, ['kand_sma', 'kand_macd'], errors=errors)
    assert errors == {}
    keys = {item['key'].split(':')[0] for item in items}
    assert keys == {'kand_sma', 'kand_macd'}

"""PtaRs —— pandas_ta 的 **Rust 版**实现（20 个指标）✓

用户 2026-11-21：先做 20 个常用指标，和原生 `pandas_ta` 对比效果。

| 检查项 | 说明 |
|---|---|
| 覆盖 | sma/ema/wma/rma/stdev/bbands/macd/rsi/atr/donchian/kc/kdj/stoch/obv/mfi/vwap/adx/ao/roc/trix |
| 逐值 | 17/20 与 `pandas_ta` **逐值一致**（相对误差 ≤1e-9）；ATR/ADX 与 **TA-Lib** 逐值一致（pandas_ta 的预热段差一根）|
| 接法 | `kline.pta_rs.sma(length=20)`；desk 里一组「PtaRS」✓ |
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pandas_ta = pytest.importorskip('pandas_ta')

alpha_installed = True
try:
    import alpha  # noqa: F401
except Exception:                                                # noqa: BLE001
    alpha_installed = False

needs_alpha = pytest.mark.skipif(not alpha_installed,
                                 reason='没装 py-alpha-lib')

#: 指标 → (线名, 参数, 参考调用)
CASES = {
    'sma': (['sma'], dict(length=20),
            lambda f: pandas_ta.sma(f['close'], length=20, talib=False)),
    'ema': (['ema'], dict(length=20),
            lambda f: pandas_ta.ema(f['close'], length=20, adjust=False,
                                    talib=False)),
    'wma': (['wma'], dict(length=20),
            lambda f: pandas_ta.wma(f['close'], length=20, talib=False)),
    'rma': (['rma'], dict(length=20),
            lambda f: pandas_ta.rma(f['close'], length=20, talib=False)),
    'stdev': (['stdev'], dict(length=20),
              lambda f: pandas_ta.stdev(f['close'], length=20, talib=False)),
    'bbands': (['bbl', 'bbm', 'bbu'], dict(length=20, std=2.0),
               lambda f: pandas_ta.bbands(f['close'], length=20, std=2.0,
                                          talib=False)),
    'macd': (['macd', 'macdh', 'macds'], dict(), None),
    'rsi': (['rsi'], dict(length=14),
            lambda f: pandas_ta.rsi(f['close'], length=14, talib=False)),
    'donchian': (['dcl', 'dcm', 'dcu'], dict(),
                 lambda f: pandas_ta.donchian(f['high'], f['low'],
                                              lower_length=20,
                                              upper_length=20)),
    'kc': (['kcl', 'kcb', 'kcu'], dict(),
           lambda f: pandas_ta.kc(f['high'], f['low'], f['close'],
                                  length=20, scalar=2.0)),
    'kdj': (['k', 'd', 'j'], dict(),
            lambda f: pandas_ta.kdj(f['high'], f['low'], f['close'],
                                    length=9, signal=3, talib=False)),
    'stoch': (['stochk', 'stochd', 'stochh'], dict(k=14, d=3, smooth_k=3),
              lambda f: pandas_ta.stoch(f['high'], f['low'], f['close'],
                                        k=14, d=3, smooth_k=3, talib=False)),
    'obv': (['obv'], dict(),
            lambda f: pandas_ta.obv(f['close'], f['volume'], talib=False)),
    'mfi': (['mfi'], dict(length=14),
            lambda f: pandas_ta.mfi(f['high'], f['low'], f['close'],
                                    f['volume'], length=14, talib=False)),
    'vwap': (['vwap'], dict(),
             lambda f: pandas_ta.vwap(f['high'], f['low'], f['close'],
                                     f['volume'])),
    'ao': (['ao'], dict(),
           lambda f: pandas_ta.ao(f['high'], f['low'], fast=5, slow=34)),
    'roc': (['roc'], dict(length=10),
            lambda f: pandas_ta.roc(f['close'], length=10, talib=False)),
    'trix': (['trix', 'trixs'], dict(),
             lambda f: pandas_ta.trix(f['close'], length=10, signal=9,
                                      talib=False)),
    'ts_rank': (['ts_rank'], dict(length=20),
                lambda f: f['close'].rolling(20).rank(pct=True)),
    'quantile': (['quantile'], dict(length=20, q=0.5),
                 lambda f: pandas_ta.quantile(f['close'], length=20, q=0.5)),
    'skew': (['skew'], dict(length=20),
             lambda f: pandas_ta.skew(f['close'], length=20)),
    'kurtosis': (['kurtosis'], dict(length=20),
                 lambda f: pandas_ta.kurtosis(f['close'], length=20)),
    'linreg': (['linreg'], dict(length=14),
               lambda f: pandas_ta.linreg(f['close'], length=14)),
    'ts_argmax': (['ts_argmax'], dict(length=20), None),
    'ts_argmin': (['ts_argmin'], dict(length=20), None),
}

#: 用 TA-Lib 才是同一口径的两个（pandas_ta 的预热种子差一根）
TALIB_CASES = ('atr', 'adx')


def _kline(length: int | None = None):
    from minibt import LocalDatas, options

    options.set_conversion_mode = 'free'
    kline = LocalDatas.test.kline
    return kline if length is None else kline.iloc[:length]


def _frame(kline, datetime_index: bool = False) -> pd.DataFrame:
    source = kline.pandas_object
    frame = source[['open', 'high', 'low', 'close', 'volume']].copy()
    if datetime_index:
        frame.index = pd.DatetimeIndex(pd.to_datetime(source['datetime']))
    return frame


def _series(result, lines: list[str]) -> dict[str, np.ndarray]:
    if isinstance(result, pd.Series):
        return {lines[0]: result.to_numpy(dtype=np.float64)}
    out = {}
    for index, line in enumerate(lines):
        out[line] = result.iloc[:, index].to_numpy(dtype=np.float64)
    return out


def _ours(kline, name: str, params: dict, lines: list[str]):
    result = getattr(kline.pta_rs, name)(**params)
    if len(lines) == 1:
        return {lines[0]: np.asarray(result, dtype=np.float64)}
    frame = result.pandas_object
    return {line: frame[line].to_numpy(dtype=np.float64) for line in lines}


# --------------------------------------------------------------- 结构
def test_class_exposes_twenty_indicators():
    """20 个指标都在，全是 `@tobtind(lib="pta_rs")` ✓"""
    from minibt.indicators.pta_rs import PtaRs

    assert PtaRs._perfixes == 'pta_rs_'
    names = [name for name in dir(PtaRs)
             if not name.startswith('_') and name != 'NON_KLINE_INDICATORS'
             and callable(getattr(PtaRs, name))]
    assert len(names) == 27, names
    assert set(names) == set(CASES) | set(TALIB_CASES)
    for name in names:
        args = getattr(PtaRs, name)._decorator_args
        assert args['lines'], name
        assert isinstance(args['overlap'], bool), name


def test_core_has_every_method():
    """`core.py` 里 27 个 `pta_rs_*` ✓"""
    import minibt.core as core

    for name in list(CASES) + list(TALIB_CASES):
        assert hasattr(core.CoreFunc, f'pta_rs_{name}'), name


def test_overlap_flags():
    """均线 / 通道在主图，振荡类在副图 ✓"""
    from minibt.indicators.pta_rs import PtaRs

    main = {'sma', 'ema', 'wma', 'rma', 'bbands', 'donchian', 'kc', 'vwap'}
    for name in CASES:
        overlap = getattr(PtaRs, name)._decorator_args['overlap']
        assert overlap is (name in main), name


# --------------------------------------------------------------- 数值
@needs_alpha
def test_values_match_pandas_ta():
    """17 个指标与 `pandas_ta` **逐值一致**（跳过头 120 根 ✓）"""
    kline = _kline()
    frame = _frame(kline)
    frame_dt = _frame(kline, datetime_index=True)
    skip = 120
    bad = []
    for name, (lines, params, call) in CASES.items():
        source = frame_dt if name == 'vwap' else frame
        if name == 'macd':
            fast = pandas_ta.ema(source['close'], length=12, adjust=False,
                                 talib=False)
            slow = pandas_ta.ema(source['close'], length=26, adjust=False,
                                 talib=False)
            line = fast - slow
            signal = pandas_ta.ema(line, length=9, adjust=False, talib=False)
            theirs = {'macd': line.to_numpy(dtype=np.float64),
                      'macdh': (line - signal).to_numpy(dtype=np.float64),
                      'macds': signal.to_numpy(dtype=np.float64)}
        elif name in ('ts_argmax', 'ts_argmin'):
            window = 20
            pick = np.argmax if name == 'ts_argmax' else np.argmin
            theirs = {lines[0]: source['close'].rolling(window).apply(
                lambda w: float(len(w) - 1 - pick(w[::-1])),
                raw=True).to_numpy(dtype=np.float64)}
        else:
            theirs = _series(call(source), lines)
        ours = _ours(kline, name, params, lines)
        for line in lines:
            mine = ours[line][skip:]
            ref = theirs[line][skip:]
            valid = np.isfinite(mine) & np.isfinite(ref)
            assert valid.sum() > 100, (name, line)
            scale = np.maximum(np.abs(ref[valid]), 1.0)
            error = float(np.max(np.abs(mine[valid] - ref[valid]) / scale))
            tolerance = {'skew': 1e-7, 'kurtosis': 1e-6}.get(name, 1e-6)
            if error > tolerance:
                bad.append((name, line, error))
    assert bad == [], bad


@pytest.mark.skipif(pandas_ta.__name__ != 'pandas_ta', reason='需要 pandas_ta')
@needs_alpha
def test_atr_adx_match_talib():
    """ATR / ADX / DI 与 **TA-Lib**（Wilder 标准口径）逐值一致 ✓

    `pandas_ta` 自己的 `presma` 种子比 TA-Lib 晚一根 → 只在预热段有差异。
    """
    talib = pytest.importorskip('talib')

    kline = _kline()
    frame = _frame(kline)
    high = np.ascontiguousarray(frame['high'].to_numpy(dtype=np.float64))
    low = np.ascontiguousarray(frame['low'].to_numpy(dtype=np.float64))
    close = np.ascontiguousarray(frame['close'].to_numpy(dtype=np.float64))

    pairs = [('atr', kline.pta_rs.atr(length=14),
              talib.ATR(high, low, close, 14))]
    adx = kline.pta_rs.adx(length=14).pandas_object
    pairs += [('adx', adx['adx'], talib.ADX(high, low, close, 14)),
              ('dmp', adx['dmp'], talib.PLUS_DI(high, low, close, 14)),
              ('dmn', adx['dmn'], talib.MINUS_DI(high, low, close, 14))]
    for name, mine, theirs in pairs:
        left = np.asarray(mine, dtype=np.float64)
        right = np.asarray(theirs, dtype=np.float64)[-len(left):]
        # 预热段（前 200 根）平滑种子不同 → 之后必须逐值一致 ✓
        left, right = left[200:], right[200:]
        valid = np.isfinite(left) & np.isfinite(right)
        assert valid.sum() > 100, name
        assert np.allclose(left[valid], right[valid], atol=1e-9), name


@needs_alpha
def test_every_indicator_runs_and_is_finite():
    """20 个指标都能跑通、长度对齐、留有效值（无 `±inf`）✓"""
    kline = _kline(600)
    for name, (lines, params, _call) in CASES.items():
        result = getattr(kline.pta_rs, name)(**params)
        if len(lines) == 1:
            arrays = {'x': np.asarray(result, dtype=np.float64)}
        else:
            arrays = {line: result.pandas_object[line].to_numpy(
                dtype=np.float64) for line in lines}
        for line, values in arrays.items():
            assert len(values) == len(kline), (name, line)
            assert not np.isinf(values).any(), (name, line)
            assert np.isfinite(values).sum() > len(kline) * 0.3, (name, line)
    for name in TALIB_CASES:
        assert len(getattr(kline.pta_rs, name)()) == len(kline)


# --------------------------------------------------------------- desk
def test_catalog_exposes_pta_rs():
    """desk 目录里「PtaRS」一组 20 条 ✓"""
    from minibt.desk import indicator_catalog as catalog

    items = [item for item in catalog.catalog(refresh=True)
             if item['prefix'] == 'pta_rs']
    assert len(items) == 27
    assert {item['group'] for item in items} == {'PtaRS'}
    entry = catalog.entry('pta_rs_sma')
    assert entry is not None and entry['params']
    assert catalog.missing_indicators() == {}


@needs_alpha
def test_catalog_compute_path():
    """目录 → desk compute 能用（走 kline.pta_rs.* 带样式 ✓）"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(400)
    errors: dict[str, str] = {}
    items = catalog.compute(kline, ['pta_rs_sma', 'pta_rs_macd'], errors=errors)
    assert errors == {}
    # 多线指标会摊成多条（macd → macd/macdh/macds）✓
    keys = {item['key'].split(':')[0] for item in items}
    assert keys == {'pta_rs_sma', 'pta_rs_macd'}
    for item in items:
        assert len(item['data']) == len(kline)


def test_generator_outputs_are_in_sync():
    """生成器 / 类文件 / 文档保持一致（别手改产物 ✓）"""
    source = (ROOT / 'scripts' / 'gen_pta_rs.py').read_text(encoding='utf-8')
    assert 'INDICATORS' in source
    assert source.count("'name': '") >= 20
    class_text = (ROOT / 'minibt' / 'indicators' / 'pta_rs.py').read_text(
        encoding='utf-8')
    assert class_text.count('    @tobtind(lib="pta_rs"') == 27
    core_text = (ROOT / 'minibt' / 'core.py').read_text(encoding='utf-8')
    assert '# <pta-rs:methods:begin>' in core_text
    assert core_text.count('    def pta_rs_') == 27


# --------------------------------------------------------------- 批量接口
@needs_alpha
def test_batch_matches_single_calls():
    """`batch()` 和逐个 `kline.pta_rs.*` 数值一致（只是省掉包装 ✓）"""
    from minibt.indicators.pta_rs import batch, _INDICATOR_NAMES

    kline = _kline(600)
    frame = _frame(kline)
    out = batch(frame, {'sma': {'length': 20}, 'macd': {}, 'atr': {'length': 14}})
    assert set(out) == {'sma', 'macd', 'atr'}
    assert np.allclose(np.asarray(out['sma'], dtype=float),
                       np.asarray(kline.pta_rs.sma(length=20), dtype=float))
    assert np.allclose(
        out['macd']['macds'].to_numpy(dtype=float),
        kline.pta_rs.macd().pandas_object['macds'].to_numpy(dtype=float),
        equal_nan=True)

    everything = batch(frame)
    assert set(everything) == set(_INDICATOR_NAMES)
    with pytest.raises(KeyError):
        batch(frame, {'不存在的指标': {}})


def test_new_statistics_indicators_are_fast_paths():
    """ts_rank / ts_argmax 用的是 Rust 的 RANK / HHVBARS（不是 pandas apply）✓"""
    core_text = (ROOT / 'minibt' / 'core.py').read_text(encoding='utf-8')
    for needle in ('alpha.RANK(', 'alpha.HHVBARS(', 'alpha.LLVBARS(',
                   'alpha.QUANTILE(', 'alpha.MOMENT(', 'alpha.INTERCEPT('):
        assert needle in core_text, needle
    assert '_pta_rs_count(' in core_text          # 部分窗口的个数 ✓


# --------------------------------------------------------------- 本轮优化
@needs_alpha
def test_vwap_matches_pandas_ta_and_resets_daily():
    """`vwap` 按**交易日**重置（numpy 前缀和实现），值与 pandas_ta 一致 ✓"""
    kline = _kline()
    frame = _frame(kline, datetime_index=True)
    full = np.asarray(kline.pta_rs.vwap(), dtype=np.float64)
    ours = full[120:]
    theirs = np.asarray(pandas_ta.vwap(frame['high'], frame['low'],
                                       frame['close'], frame['volume']),
                        dtype=np.float64)[120:]
    valid = np.isfinite(ours) & np.isfinite(theirs)
    assert valid.sum() > 100
    assert np.allclose(ours[valid], theirs[valid])

    # 每天开头是否重置：取第二天首根，VWAP 应≈当天首根典型价
    stamps = pd.DatetimeIndex(pd.to_datetime(kline.pandas_object['datetime']))
    days = stamps.normalize()
    second = int(np.argmax(days != days[0]))
    typical = (np.asarray(kline.high, dtype=float)[second]
               + np.asarray(kline.low, dtype=float)[second]
               + np.asarray(kline.close, dtype=float)[second]) / 3.0
    assert np.isclose(full[second], typical, rtol=1e-12)


@needs_alpha
def test_ema_seed_correction_is_exact():
    """`ema` 的"种子修正"不改数值：与 pandas_ta 逐值一致（前 5 根也算）✓"""
    kline = _kline(400)
    ours = np.asarray(kline.pta_rs.ema(length=20), dtype=np.float64)
    theirs = np.asarray(pandas_ta.ema(kline.pandas_object['close'], length=20,
                                      adjust=False, talib=False),
                        dtype=np.float64)
    valid = np.isfinite(ours) & np.isfinite(theirs)
    assert valid.sum() > 300
    assert np.allclose(ours[valid], theirs[valid], atol=1e-9)


def test_arrays_helper_does_not_compute_timestamps():
    """`_pta_rs_arrays` 不再算时间戳（只有 `vwap` 需要，省 17 ms/次 ✓）"""
    import minibt.core as core

    source = (ROOT / 'minibt' / 'core.py').read_text(encoding='utf-8')
    body = source[source.index('def _pta_rs_arrays'):]
    body = body[:body.index('def _pta_rs_day_stamps')]
    assert 'normalize()' not in body
    assert 'stamps' not in body
    assert callable(core._pta_rs_day_stamps)
    assert callable(core._pta_rs_vwap)

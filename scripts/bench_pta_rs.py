"""PtaRs vs 原生 pandas_ta：**逐值对比 + 速度基准**（`scripts/bench_pta_rs.py` ✓）

用法：

    py -3.12 scripts/bench_pta_rs.py            # 真实数据（内置 5 分钟 K 线）
    py -3.12 scripts/bench_pta_rs.py --fast     # 只跑值对比，不跑 100 万点基准
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

import pandas_ta as pta
from minibt import LocalDatas, options

options.set_conversion_mode = 'free'

def _macd_reference(frame):
    """pandas_ta 的 `macd()` 内部用 `ema(adjust=True)`；为了口径可比，
    这里用它的 `ema(adjust=False)` 基元拼出参考值 ✓"""
    fast = pta.ema(frame['close'], length=12, adjust=False, talib=False)
    slow = pta.ema(frame['close'], length=26, adjust=False, talib=False)
    line = fast - slow
    signal = pta.ema(line, length=9, adjust=False, talib=False)
    return pd.DataFrame({'macd': line, 'macdh': line - signal,
                         'macds': signal})


def _argmax_reference(frame, length: int = 20):
    """窗口最高点位置（**并列取最近的一次**，和 `alpha.HHVBARS` 一致 ✓）"""
    return frame['close'].rolling(length).apply(
        lambda window: float(len(window) - 1 - np.argmax(window[::-1])),
        raw=True)


def _argmin_reference(frame, length: int = 20):
    return frame['close'].rolling(length).apply(
        lambda window: float(len(window) - 1 - np.argmin(window[::-1])),
        raw=True)


#: (指标, 线名, pandas_ta 调用, 参数)
CASES = [
    ('sma', ['sma'], lambda f: pta.sma(f['close'], length=20, talib=False),
     dict(length=20)),
    ('ema', ['ema'],
     lambda f: pta.ema(f['close'], length=20, adjust=False, talib=False),
     dict(length=20)),
    ('wma', ['wma'], lambda f: pta.wma(f['close'], length=20, talib=False),
     dict(length=20)),
    ('rma', ['rma'], lambda f: pta.rma(f['close'], length=20, talib=False),
     dict(length=20)),
    ('stdev', ['stdev'], lambda f: pta.stdev(f['close'], length=20,
                                             talib=False), dict(length=20)),
    ('bbands', ['bbl', 'bbm', 'bbu'],
     lambda f: pta.bbands(f['close'], length=20, std=2.0, talib=False),
     dict(length=20, std=2.0)),
    ('macd', ['macd', 'macdh', 'macds'], _macd_reference, dict()),
    ('rsi', ['rsi'], lambda f: pta.rsi(f['close'], length=14, talib=False),
     dict(length=14)),
    ('atr', ['atr'], lambda f: pta.atr(f['high'], f['low'], f['close'],
                                       length=14, talib=False), dict(length=14)),
    ('donchian', ['dcl', 'dcm', 'dcu'],
     lambda f: pta.donchian(f['high'], f['low'], lower_length=20,
                            upper_length=20), dict()),
    ('kc', ['kcl', 'kcb', 'kcu'],
     lambda f: pta.kc(f['high'], f['low'], f['close'], length=20, scalar=2.0),
     dict()),
    ('kdj', ['k', 'd', 'j'],
     lambda f: pta.kdj(f['high'], f['low'], f['close'], length=9, signal=3,
                       talib=False), dict()),
    ('stoch', ['stochk', 'stochd', 'stochh'],
     lambda f: pta.stoch(f['high'], f['low'], f['close'], k=14, d=3,
                         smooth_k=3, talib=False), dict(k=14, d=3,
                                                        smooth_k=3)),
    ('obv', ['obv'], lambda f: pta.obv(f['close'], f['volume'], talib=False),
     dict()),
    ('mfi', ['mfi'], lambda f: pta.mfi(f['high'], f['low'], f['close'],
                                       f['volume'], length=14, talib=False),
     dict(length=14)),
    ('vwap', ['vwap'], lambda f: pta.vwap(f['high'], f['low'], f['close'],
                                          f['volume']), dict()),
    ('adx', ['adx', 'dmp', 'dmn'],
     lambda f: pta.adx(f['high'], f['low'], f['close'], length=14,
                       talib=False).iloc[:, [0, 2, 3]], dict()),
    # ↑ pta.adx 的列顺序是 ADX / ADXR / DMP / DMN（第 1 列是 ADXR，别拿错 ✗）
    ('ao', ['ao'], lambda f: pta.ao(f['high'], f['low'], fast=5, slow=34),
     dict()),
    ('roc', ['roc'], lambda f: pta.roc(f['close'], length=10, talib=False),
     dict(length=10)),
    ('trix', ['trix', 'trixs'],
     lambda f: pta.trix(f['close'], length=10, signal=9, talib=False),
     dict()),
    ('ts_rank', ['ts_rank'],
     lambda f: f['close'].rolling(20).rank(pct=True), dict(length=20)),
    ('quantile', ['quantile'],
     lambda f: pta.quantile(f['close'], length=20, q=0.5),
     dict(length=20, q=0.5)),
    ('skew', ['skew'],
     lambda f: pta.skew(f['close'], length=20), dict(length=20)),
    ('kurtosis', ['kurtosis'],
     lambda f: pta.kurtosis(f['close'], length=20), dict(length=20)),
    ('linreg', ['linreg'],
     lambda f: pta.linreg(f['close'], length=14), dict(length=14)),
    ('ts_argmax', ['ts_argmax'], _argmax_reference, dict(length=20)),
    ('ts_argmin', ['ts_argmin'], _argmin_reference, dict(length=20)),
]


def _frame(kline, datetime_index: bool = False) -> pd.DataFrame:
    """KLine → 普通 DataFrame

    ⚠ 索引很关键：`pandas_ta` 里 `tr[0:length]` 这种写法在 **DatetimeIndex**
    上会变成标签切片（返回空 → presma 种子失效 ✗），而 minibt 内部用的是
    RangeIndex —— 所以默认用 RangeIndex 对比；`vwap` 需要 DatetimeIndex ✓
    """
    source = kline.pandas_object
    frame = source[['open', 'high', 'low', 'close', 'volume']].copy()
    if datetime_index:
        frame.index = pd.DatetimeIndex(pd.to_datetime(source['datetime']))
    return frame


def _columns(result, lines: list[str]) -> dict[str, np.ndarray]:
    """pandas_ta 结果 → {线名: 数组}（按位置对应 ✓）"""
    if isinstance(result, pd.Series):
        return {lines[0]: result.to_numpy(dtype=np.float64)}
    frame = result
    out = {}
    for index, name in enumerate(lines):
        out[name] = frame.iloc[:, index].to_numpy(dtype=np.float64)
    return out


def _mine(kline, name: str, params: dict, lines: list[str]):
    result = getattr(kline.pta_rs, name)(**params)
    if len(lines) == 1:
        return {lines[0]: np.asarray(result, dtype=np.float64)}
    frame = result.pandas_object
    return {line: frame[line].to_numpy(dtype=np.float64) for line in lines}


def compare(skip: int = 120) -> list[dict]:
    kline = LocalDatas.test.kline
    frame = _frame(kline)
    frame_dt = _frame(kline, datetime_index=True)
    rows = []
    for name, lines, call, params in CASES:
        source = frame_dt if name == 'vwap' else frame
        theirs = _columns(call(source), lines)
        ours = _mine(kline, name, params, lines)
        detail = []
        for line in lines:
            mine = ours[line][skip:]
            other = theirs[line][skip:]
            valid = np.isfinite(mine) & np.isfinite(other)
            if valid.sum() < 10:
                detail.append((line, None, 0, 0.0))
                continue
            diff = np.abs(mine[valid] - other[valid])
            scale = np.maximum(np.abs(other[valid]), 1.0)   # 近 0 值用绝对误差 ✓
            detail.append((line, float(diff.max()),
                           int(valid.sum()), float((diff / scale).max())))
        rows.append({'name': name, 'detail': detail})
    return rows


def compare_talib() -> list[tuple[str, bool, float]]:
    """ATR / ADX 是 Wilder 标准口径 → 和 **TA-Lib（C）** 对拍才是同一个定义 ✓"""
    import talib

    kline = LocalDatas.test.kline
    frame = _frame(kline)
    high = np.ascontiguousarray(frame['high'].to_numpy(dtype=np.float64))
    low = np.ascontiguousarray(frame['low'].to_numpy(dtype=np.float64))
    close = np.ascontiguousarray(frame['close'].to_numpy(dtype=np.float64))
    ours = kline.pta_rs.atr(length=14)
    theirs = talib.ATR(high, low, close, 14)
    rows = [('atr', ours, theirs)]
    adx = kline.pta_rs.adx(length=14).pandas_object
    rows.append(('adx', adx['adx'], talib.ADX(high, low, close, 14)))
    rows.append(('dmp', adx['dmp'], talib.PLUS_DI(high, low, close, 14)))
    rows.append(('dmn', adx['dmn'], talib.MINUS_DI(high, low, close, 14)))
    out = []
    for name, mine, theirs in rows:
        left = np.asarray(mine, dtype=np.float64)
        right = np.asarray(theirs, dtype=np.float64)[-len(left):]
        valid = np.isfinite(left) & np.isfinite(right)
        scale = np.maximum(np.abs(right[valid]), 1e-9)
        out.append((name, bool(np.allclose(left[valid], right[valid])),
                    float(np.max(np.abs(left[valid] - right[valid]) / scale))))
    return out


def bench(bars: int = 1_000_000):
    rng = np.random.default_rng(7)
    close = np.cumsum(rng.normal(0, 1, bars)) + 5000
    high = close + np.abs(rng.normal(0, 1, bars))
    low = close - np.abs(rng.normal(0, 1, bars))
    volume = np.abs(rng.normal(1000, 50, bars))
    stamps = pd.date_range('2024-01-01', periods=bars, freq='5min')
    frame = pd.DataFrame({
        'datetime': stamps, 'open': close, 'high': high, 'low': low,
        'close': close, 'volume': volume,
    })
    frame_range = frame.set_index('datetime').reset_index(drop=True)
    frame_dt = frame_range.copy()
    frame_dt.index = pd.DatetimeIndex(stamps)
    kline = type(LocalDatas.test.kline)(frame)
    rows = []
    for name, lines, call, params in CASES:
        def run_mine():
            getattr(kline.pta_rs, name)(**params)

        def run_theirs():
            call(frame_dt if name == 'vwap' else frame_range)

        def timed(func, repeat=3):
            best = 1e9
            for _ in range(repeat):
                start = time.perf_counter()
                func()
                best = min(best, time.perf_counter() - start)
            return best * 1000

        rows.append({'name': name, 'rust': timed(run_mine),
                     'pandas_ta': timed(run_theirs)})
    return rows


def bench_algo(bars: int = 1_000_000):
    """**算法级**基准：直接调 `CoreFunc.pta_rs_*`（绕过 `@tobtind` 的固定开销 ✓）"""
    import minibt.core as core

    rng = np.random.default_rng(7)
    close = np.cumsum(rng.normal(0, 1, bars)) + 5000
    high = close + np.abs(rng.normal(0, 1, bars))
    low = close - np.abs(rng.normal(0, 1, bars))
    volume = np.abs(rng.normal(1000, 50, bars))
    frame = pd.DataFrame({'open': close, 'high': high, 'low': low,
                          'close': close, 'volume': volume})
    frame_dt = frame.copy()
    frame_dt.index = pd.DatetimeIndex(pd.date_range('2024-01-01',
                                                    periods=bars, freq='5min'))

    rows = []
    for name, lines, call, params in CASES:
        func = getattr(core.CoreFunc, f'pta_rs_{name}')

        def run_mine():
            func(frame)

        def timed(func, repeat=3):
            best = 1e9
            for _ in range(repeat):
                start = time.perf_counter()
                func()
                best = min(best, time.perf_counter() - start)
            return best * 1000

        rows.append({'name': name, 'rust': timed(run_mine),
                     'pandas_ta': timed(
                         lambda: call(frame_dt if name == 'vwap'
                                      else frame))})
    return rows


def main() -> None:
    print('== 逐值对比（内置 5 分钟 K 线，跳过头 60 根）')
    failures = 0
    for row in compare():
        text = []
        for line, max_abs, count, max_rel in row['detail']:
            if count == 0:
                text.append(f'{line}: 无法对比')
                continue
            tolerance = {'skew': 1e-7, 'kurtosis': 1e-6}.get(row['name'], 1e-6)
            ok = max_rel < tolerance
            failures += 0 if ok else 1
            text.append(f"{line}: {'✓' if ok else '✗'} "
                        f"(最大相对误差 {max_rel:.2e})")
        print(f"  {row['name']:<9} " + ' | '.join(text))
    print(f'\n不一致的线：{failures}')

    if '--fast' in sys.argv:
        return
    print('\n== 速度基准（100 万根，3 次取最好，单位 ms）')
    print(f'{"指标":<10}{"PtaRs(Rust)":>14}{"pandas_ta":>12}{"加速":>8}')
    rows = bench()
    speedups = []
    for row in rows:
        speed = row['pandas_ta'] / max(row['rust'], 1e-9)
        speedups.append((row['name'], speed))
        print(f"{row['name']:<10}{row['rust']:>14.1f}"
              f"{row['pandas_ta']:>12.1f}{speed:>7.1f}x")
    slowest = sorted(speedups, key=lambda item: -item[1])[:3]
    fastest = sorted(speedups, key=lambda item: item[1])[:3]
    print('\n最快的一批：', ', '.join(f'{n} {s:.1f}x' for n, s in slowest))
    print('最慢的一批：', ', '.join(f'{n} {s:.2f}x' for n, s in fastest))

    print('\n== 算法级基准（直接调 CoreFunc.pta_rs_*，绕过 @tobtind 包装 ✓）')
    print(f'{"指标":<10}{"Rust 算法":>12}{"pandas_ta":>12}{"加速":>8}')
    algo = bench_algo()
    for row in algo:
        speed = row['pandas_ta'] / max(row['rust'], 1e-9)
        print(f"{row['name']:<10}{row['rust']:>12.1f}"
              f"{row['pandas_ta']:>12.1f}{speed:>7.1f}x")
    print('\n== 批量接口 `batch()`（一次算全部 27 个指标，100 万根）')
    from minibt.indicators.pta_rs import batch
    big_rng = np.random.default_rng(7)
    big_close = np.cumsum(big_rng.normal(0, 1, 1_000_000)) + 5000
    big = pd.DataFrame({
        'open': big_close, 'high': big_close + 1, 'low': big_close - 1,
        'close': big_close,
        'volume': np.abs(big_rng.normal(1000, 50, 1_000_000))})
    from minibt.indicators.pta_rs import _INDICATOR_NAMES
    specs = {name: {} for name in _INDICATOR_NAMES}
    batch(big, {'sma': {}})                      # 预热

    def timed(func, repeat=3):
        best = 1e9
        for _ in range(repeat):
            start = time.perf_counter()
            func()
            best = min(best, time.perf_counter() - start)
        return best * 1000

    big_ms = timed(lambda: batch(big, specs))
    print(f'  1 000 000 根：batch {big_ms:.0f} ms（{big_ms / 27:.1f} ms/个）')
    for bars in (5000, 500):
        kline = type(LocalDatas.test.kline)(
            LocalDatas.test.kline.pandas_object.iloc[:bars].reset_index(
                drop=True))
        frame = kline.pandas_object
        fast = timed(lambda: batch(frame, specs))
        slow = timed(lambda: [getattr(kline.pta_rs, name)() for name in
                              _INDICATOR_NAMES], repeat=1)
        print(f'  {bars:>6} 根：batch {fast:.0f} ms | 逐个 @tobtind {slow:.0f} ms'
              f' → {slow / fast:.1f}×')

    ratio = [(row['pandas_ta'] / max(row['rust'], 1e-9), row['name'])
             for row in algo]
    best = max(ratio)
    worst = min(ratio)
    print(f'\n算法级最快：{best[1]} {best[0]:.1f}x | '
          f'最慢：{worst[1]} {worst[0]:.2f}x')


if __name__ == '__main__':
    main()

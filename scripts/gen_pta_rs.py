"""生成 **PtaRs**（pandas_ta 的 Rust 版实现，20 个指标）✓

思路：pandas_ta 的算法核心都是"滚动算子组合"，而 `py-alpha-lib`（`alpha`）
用 Rust 实现了这些算子 → 用它能 1:1 拼出 pandas_ta 的公式。

产物：

* `minibt/indicators/pta_rs.py` —— `class PtaRs`（前缀 `pta_rs_`，副图/主图按指标定）
* `minibt/core.py` —— `pta_rs_*` CoreFunc 方法 + 公共助手（标记块包裹）

用法：

    py -3.12 scripts/gen_pta_rs.py           # 只看清单
    py -3.12 scripts/gen_pta_rs.py --write   # 写文件
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NL = chr(10)

#: 20 个指标：名字 / 线名 / 主图 / 参数 / 中文说明 / 公式 / 实现体（用助手）
INDICATORS: list[dict] = [
    {
        'name': 'sma', 'lines': ['sma'], 'overlap': True,
        'params': [('length', 'int', 10)],
        'title': '简单移动平均（SMA）',
        'desc': '窗口内收盘价等权平均；和 `pandas_ta.sma` 等价。',
        'formula': 'SMA = alpha.MA(close, length)',
        'body': [
            "return pd.Series(alpha.MA(close, length), index=index)",
        ],
    },
    {
        'name': 'ema', 'lines': ['ema'], 'overlap': True,
        'params': [('length', 'int', 10)],
        'title': '指数移动平均（EMA）',
        'desc': 'α = 2/(length+1) 的指数平滑，**前 n 根均值当种子**（TA-Lib / '
                'pandas_ta 口径）。',
        'formula': 'EMA = SMA 种子 + α·x + (1-α)·EMA₋₁',
        'body': [
            "return pd.Series(_pta_rs_ema(close, length), index=index)",
        ],
    },
    {
        'name': 'wma', 'lines': ['wma'], 'overlap': True,
        'params': [('length', 'int', 10)],
        'title': '加权移动平均（WMA）',
        'desc': '窗口内按 1..n 线性加权；和 `pandas_ta.wma` 等价。',
        'formula': 'WMA = alpha.LWMA(close, length)',
        'body': [
            "return pd.Series(alpha.LWMA(close, length), index=index)",
        ],
    },
    {
        'name': 'rma', 'lines': ['rma'], 'overlap': True,
        'params': [('length', 'int', 10)],
        'title': "Wilder 平滑（RMA）",
        'desc': 'α = 1/length 的指数平滑（Wilder），ATR/RSI/ADX 的平滑内核。',
        'formula': 'RMA = alpha.SMA(close, length, 1)',
        'body': [
            "return pd.Series(_pta_rs_rma(close, length), index=index)",
        ],
    },
    {
        'name': 'stdev', 'lines': ['stdev'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '滚动标准差（总体口径）',
        'desc': "pandas_ta 的 `stdev` 默认 `ddof=1`（样本）→ 和 `alpha.STDDEV` "
                "口径一致。",
        'formula': 'STDEV = alpha.STDDEV(close, n)（ddof=1 ✓）',
        'body': [
            "return pd.Series(alpha.STDDEV(close, length), index=index)",
        ],
    },
    {
        'name': 'bbands', 'lines': ['bbl', 'bbm', 'bbu'], 'overlap': True,
        'params': [('length', 'int', 20), ('std', 'float', 2.0)],
        'title': '布林带（BBANDS）',
        'desc': '中轨 = SMA，上下轨 = 中轨 ± k × 标准差（ddof=1，同 pandas_ta）。',
        'formula': 'BBM = MA(close, n)；BBU/BBL = BBM ± k·STDDEV',
        'body': [
            "mid = alpha.MA(close, length)",
            "band = alpha.STDDEV(close, length) * float(std)",
            "return pd.DataFrame({'bbl': mid - band, 'bbm': mid,",
            "                     'bbu': mid + band}, index=index)",
        ],
    },
    {
        'name': 'macd', 'lines': ['macd', 'macdh', 'macds'], 'overlap': False,
        'params': [('fast', 'int', 12), ('slow', 'int', 26),
                   ('signal', 'int', 9)],
        'title': 'MACD（12/26/9）',
        'desc': '快慢 EMA 差 + 其 EMA 信号线 + 柱状差。',
        'formula': 'MACD = EMA(close,f) - EMA(close,s)；'
                   'MACDs = EMA(MACD, sig)；MACDh = MACD - MACDs',
        'body': [
            "line = _pta_rs_ema(close, fast) - _pta_rs_ema(close, slow)",
            "# pandas_ta 的 MA 预热让 macd 前 slow-1 根是 NaN → 信号线从那里起算 ✓",
            "warm = np.where(np.arange(line.size) >= int(slow) - 1, line, np.nan)",
            "signal_line = _pta_rs_ema(warm, signal)",
            "return pd.DataFrame({'macd': line, 'macdh': line - signal_line,",
            "                     'macds': signal_line}, index=index)",
        ],
    },
    {
        'name': 'rsi', 'lines': ['rsi'], 'overlap': False,
        'params': [('length', 'int', 14)],
        'title': '相对强弱（RSI）',
        'desc': '涨幅 / 跌幅的 Wilder 平滑之比（`alpha.SMA(x,n,1)` 就是 RMA）。',
        'formula': 'RSI = 100·RMA(gain,n)/(RMA(gain,n)+|RMA(loss,n)|)',
        'body': [
            "delta = close - _pta_rs_delay(close, 1)",
            "gain = _pta_rs_rma(np.maximum(delta, 0.0), length)",
            "loss = _pta_rs_rma(np.maximum(-delta, 0.0), length)",
            "total = gain + np.abs(loss)",
            "rsi = 100.0 * gain / np.where(total == 0, np.nan, total)",
            "return pd.Series(np.where(np.isfinite(gain), rsi, np.nan),",
            "                 index=index)",
        ],
    },
    {
        'name': 'atr', 'lines': ['atr'], 'overlap': False,
        'params': [('length', 'int', 14)],
        'title': '平均真实波幅（ATR）',
        'desc': 'TR = max(H-L, |H-C₋₁|, |C₋₁-L|)，前 n 根均值当种子后 Wilder 平滑'
                '（和 pandas_ta 的 `presma=True` 一致）。',
        'formula': 'ATR = RMA(TR, n)',
        'body': [
            "return pd.Series(_pta_rs_atr(high, low, close, length),",
            "                 index=index)",
        ],
    },
    {
        'name': 'donchian', 'lines': ['dcl', 'dcm', 'dcu'], 'overlap': True,
        'params': [('lower_length', 'int', 20), ('upper_length', 'int', 20)],
        'title': '唐奇安通道（DONCHIAN）',
        'desc': '上下轨 = 区间最高 / 最低，中轨取两者均值。',
        'formula': 'DCU = HHV(high,u)；DCL = LLV(low,l)；DCM = (DCU+DCL)/2',
        'body': [
            "upper = alpha.HHV(high, upper_length)",
            "lower = alpha.LLV(low, lower_length)",
            "return pd.DataFrame({'dcl': lower, 'dcm': (upper + lower) / 2,",
            "                     'dcu': upper}, index=index)",
        ],
    },
    {
        'name': 'kc', 'lines': ['kcl', 'kcb', 'kcu'], 'overlap': True,
        'params': [('length', 'int', 20), ('scalar', 'float', 2.0)],
        'title': '肯特纳通道（KC）',
        'desc': '中轨 = EMA(close)，带宽 = EMA(TR)，上下轨 = 中轨 ± k×带宽。',
        'formula': 'KCB = EMA(close,n)；KCB ± k·EMA(TR,n)',
        'body': [
            "basis = _pta_rs_ema(close, length)",
            "tr = _pta_rs_true_range(high, low, close)",
            "band = _pta_rs_ema(tr, length) * float(scalar)",
            "return pd.DataFrame({'kcl': basis - band, 'kcb': basis,",
            "                     'kcu': basis + band}, index=index)",
        ],
    },
    {
        'name': 'kdj', 'lines': ['k', 'd', 'j'], 'overlap': False,
        'params': [('length', 'int', 9), ('signal', 'int', 3)],
        'title': 'KDJ',
        'desc': 'RSV = (C-LLV)/(HHV-LLV)×100，K/D 用 RMA 平滑，J = 3K-2D。',
        'formula': 'K = RMA(RSV, sig)；D = RMA(K, sig)；J = 3K - 2D',
        'body': [
            "lowest = alpha.LLV(low, length)",
            "highest = alpha.HHV(high, length)",
            "span = np.where(highest == lowest, np.nan, highest - lowest)",
            "rsv = 100 * (close - lowest) / span",
            "k = _pta_rs_rma(rsv, signal)",
            "d = _pta_rs_rma(k, signal)",
            "return pd.DataFrame({'k': k, 'd': d, 'j': 3 * k - 2 * d},",
            "                     index=index)",
        ],
    },
    {
        'name': 'stoch', 'lines': ['stochk', 'stochd', 'stochh'],
        'overlap': False,
        'params': [('k', 'int', 14), ('d', 'int', 3), ('smooth_k', 'int', 3)],
        'title': '随机指标（STOCH）',
        'desc': 'K = SMA(%K, smooth_k)，D = SMA(K, d)，H = K - D。',
        'formula': '%K = 100(C-LLV)/(HHV-LLV)；K = SMA(%K,sm)；D = SMA(K,d)',
        'body': [
            "lowest = alpha.LLV(low, int(k))",
            "highest = alpha.HHV(high, int(k))",
            "span = np.where(highest == lowest, np.nan, highest - lowest)",
            "fast = 100 * (close - lowest) / span",
            "stoch_k = alpha.MA(fast, int(smooth_k))",
            "stoch_d = alpha.MA(stoch_k, int(d))",
            "return pd.DataFrame({'stochk': stoch_k,"
            " 'stochd': stoch_d,",
            "                     'stochh': stoch_k - stoch_d}, index=index)",
        ],
    },
    {
        'name': 'obv', 'lines': ['obv'], 'overlap': False, 'params': [],
        'title': '能量潮（OBV）',
        'desc': '收盘涨则加成交量、跌则减，逐根累加（第一根按缺失处理）。',
        'formula': 'OBV = cumsum(sign(Δclose) * volume)',
        'body': [
            "sign = np.sign(close - _pta_rs_delay(close, 1))",
            "signed = np.where(np.isnan(sign), 0.0, sign) * volume",
            "values = np.cumsum(signed)",
            "values[0] = np.nan",
            "return pd.Series(values, index=index)",
        ],
    },
    {
        'name': 'mfi', 'lines': ['mfi'], 'overlap': False,
        'params': [('length', 'int', 14)],
        'title': '资金流量（MFI）',
        'desc': '典型价 × 量按涨跌定号，窗口内正 / 负流量比 → 0~100。',
        'formula': 'MFI = 100·Σpos/(Σpos+Σneg)',
        'body': [
            "tp = (high + low + close) / 3.0",
            "rising = tp > _pta_rs_delay(tp, 1)",
            "direction = np.where(rising, 1.0, -1.0)",
            "direction[0] = np.nan",
            "flow = np.where(np.isnan(direction), 0.0, direction) * tp * volume",
            "gain = alpha.SUM(np.maximum(flow, 0.0), length)",
            "loss = alpha.SUM(np.maximum(-flow, 0.0), length)",
            "total = gain + loss",
            "ratio = np.where(total == 0, np.nan, 100 * gain / total)",
            "return pd.Series(ratio, index=index)",
        ],
    },
    {
        'name': 'vwap', 'lines': ['vwap'], 'overlap': True, 'params': [],
        'title': '成交量加权均价（VWAP）',
        'desc': '典型价 × 量的累计 / 成交量累计；按**交易日**分组重置'
                '（时间索引从 IndFrame 的 datetime 列取）。',
        'formula': 'VWAP = Σ(tp·vol) / Σ(vol)（按日重置）',
        'body': [
            "tp = (high + low + close) / 3.0",
            "values = _pta_rs_vwap(tp, volume, _pta_rs_day_stamps(self))",
            "return pd.Series(values, index=index)",
        ],
    },
    {
        'name': 'adx', 'lines': ['adx', 'dmp', 'dmn'], 'overlap': False,
        'params': [('length', 'int', 14), ('signal_length', 'int', 14)],
        'title': '趋向指标（ADX / DI）',
        'desc': '方向运动 DM± / ATR → DI± → DX → RMA 平滑成 ADX。',
        'formula': 'DI± = 100·RMA(DM±,n)/ATR；'
                   'DX = 100·|DI+-DI-|/(DI++DI-)；ADX = RMA(DX,sig)',
        'body': [
            "prev_high = _pta_rs_delay(high, 1)",
            "prev_low = _pta_rs_delay(low, 1)",
            "up = high - prev_high",
            "down = prev_low - low",
            "pos = np.where((up > down) & (up > 0), up, 0.0)",
            "neg = np.where((down > up) & (down > 0), down, 0.0)",
            "atr = _pta_rs_atr(high, low, close, length)",
            "scale = 100.0 / np.where(atr == 0, np.nan, atr)",
            "dmp = scale * _pta_rs_rma(pos, length)",
            "dmn = scale * _pta_rs_rma(neg, length)",
            "total = dmp + dmn",
            "dx = 100.0 * np.abs(dmp - dmn) / np.where(total == 0, np.nan,",
            "                                             total)",
            "adx = _pta_rs_rma(dx, signal_length)",
            "return pd.DataFrame({'adx': adx, 'dmp': dmp, 'dmn': dmn},",
            "                     index=index)",
        ],
    },
    {
        'name': 'ao', 'lines': ['ao'], 'overlap': False,
        'params': [('fast', 'int', 5), ('slow', 'int', 34)],
        'title': '动量震荡（AO）',
        'desc': '(H+L)/2 的快慢 SMA 差。',
        'formula': 'AO = SMA((H+L)/2, fast) - SMA((H+L)/2, slow)',
        'body': [
            "median = (high + low) / 2.0",
            "return pd.Series(alpha.MA(median, fast) - alpha.MA(median, slow),",
            "                 index=index)",
        ],
    },
    {
        'name': 'roc', 'lines': ['roc'], 'overlap': False,
        'params': [('length', 'int', 10)],
        'title': '变动率（ROC）',
        'desc': 'n 根涨跌幅（百分比）。',
        'formula': 'ROC = (close/REF(close,n) - 1) * 100',
        'body': [
            "base = _pta_rs_delay(close, length)",
            "return pd.Series((close / base - 1) * 100, index=index)",
        ],
    },
    {
        'name': 'ts_rank', 'lines': ['ts_rank'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '窗口排名百分比（TS_RANK）',
        'desc': '当前值在最近 n 根里的排名（并列取平均名次）÷ 窗口个数 → 0~1。'
                'pandas 的 `rolling.apply(rank)` 要几十倍时间。',
        'formula': 'rank_pct = (min_rank + max_rank) / 2 / count',
        'body': [
            "count = _pta_rs_count(close.size, length)",
            "low = alpha.RANK(close, int(length))",
            "high = count - alpha.RANK("
            "np.ascontiguousarray(-close), int(length)) + 1",
            "return pd.Series((low + high) / 2.0 / count, index=index)",
        ],
    },
    {
        'name': 'quantile', 'lines': ['quantile'], 'overlap': False,
        'params': [('length', 'int', 20), ('q', 'float', 0.5)],
        'title': '窗口分位数（QUANTILE）',
        'desc': '最近 n 根的 q 分位值（线性插值），中位数 q=0.5。',
        'formula': 'quantile = alpha.QUANTILE(close, n, q)',
        'body': [
            "window = max(1, int(length))",
            "values = alpha.QUANTILE(close, window, float(q))",
            "return pd.Series(values, index=index)",
        ],
    },
    {
        'name': 'skew', 'lines': ['skew'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '窗口偏度（SKEW）',
        'desc': '分布左右偏斜程度（与 pandas `rolling.skew()` 一致）；'
                '三阶矩 + 样本标准差组合算。',
        'formula': 'skew = n/((n-1)(n-2)) · (M3·n / std³)',
        'body': [
            "values = _pta_rs_skew(close, max(3, int(length)))",
            "return pd.Series(values, index=index)",
        ],
    },
    {
        'name': 'kurtosis', 'lines': ['kurtosis'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '窗口超额峰度（KURTOSIS）',
        'desc': '尾部厚度（>0 尖峰厚尾）；超额峰度口径与 pandas `rolling.kurt()` 一致。',
        'formula': 'kurt = n(n+1)/((n-1)(n-2)(n-3))·(M4·n/std⁴)'
                   ' - 3(n-1)²/((n-2)(n-3))',
        'body': [
            "values = _pta_rs_skew(close, max(4, int(length)), fourth=True)",
            "return pd.Series(values, index=index)",
        ],
    },
    {
        'name': 'linreg', 'lines': ['linreg'], 'overlap': False,
        'params': [('length', 'int', 14)],
        'title': '线性回归终点（LINREG）',
        'desc': '最近 n 根线性回归直线在**当前这根**的取值'
                '（= 截距 + 斜率·(n-1)，同 TA-Lib LINEARREG）。',
        'formula': 'LINREG = INTERCEPT(close,n) + SLOPE(close,n)·(n-1)',
        'body': [
            "window = max(2, int(length))",
            "intercept = alpha.INTERCEPT(close, window)",
            "slope = alpha.SLOPE(close, window)",
            "return pd.Series(intercept + slope * (window - 1), index=index)",
        ],
    },
    {
        'name': 'ts_argmax', 'lines': ['ts_argmax'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '最高点在窗口里的位置（TS_ARGMAX）',
        'desc': '最近 n 根里最高点距今几根（0 = 当前这根），'
                '**并列时取最近的一次**。',
        'formula': 'ts_argmax = (count-1) - HHVBARS(close, n)',
        'body': [
            "count = _pta_rs_count(close.size, length)",
            "bars = alpha.HHVBARS(close, int(length))",
            "return pd.Series((count - 1) - bars, index=index)",
        ],
    },
    {
        'name': 'ts_argmin', 'lines': ['ts_argmin'], 'overlap': False,
        'params': [('length', 'int', 20)],
        'title': '最低点在窗口里的位置（TS_ARGMIN）',
        'desc': '最近 n 根里最低点距今几根（0 = 当前这根），并列时取最近的一次。',
        'formula': 'ts_argmin = (count-1) - LLVBARS(close, n)',
        'body': [
            "count = _pta_rs_count(close.size, length)",
            "bars = alpha.LLVBARS(close, int(length))",
            "return pd.Series((count - 1) - bars, index=index)",
        ],
    },
    {
        'name': 'trix', 'lines': ['trix', 'trixs'], 'overlap': False,
        'params': [('length', 'int', 10), ('signal', 'int', 9)],
        'title': '三重指数平滑均线变动率（TRIX）',
        'desc': '三重 EMA 的单根变动率 + 其 SMA 信号线。',
        'formula': 'TRIX = 100·(EMA₃/REF(EMA₃,1)-1)；TRIXs = SMA(TRIX,sig)',
        'body': [
            "ema1 = _pta_rs_ema(close, length)",
            "ema2 = _pta_rs_ema(ema1, length)",
            "ema3 = _pta_rs_ema(ema2, length)",
            "trix = 100 * (ema3 / _pta_rs_delay(ema3, 1) - 1)",
            "return pd.DataFrame({'trix': trix,",
            "                     'trixs': alpha.MA(trix, signal)},",
            "                     index=index)",
        ],
    },
]

BATCH = '''

def batch(frame, specs: dict | None = None) -> dict:
    """**一次算多个 PtaRs 指标**（绕过 `@tobtind` 的包装开销 ✓）

    `@tobtind` 每个指标有 ~40–60 ms 的固定开销（取数 / 校验 / 构造
    `IndSeries` / `_plotinfo`）—— 研究场景一次算几十个指标时先把它绕掉：

    >>> from minibt.indicators.pta_rs import batch
    >>> out = batch(kline.pandas_object,
    ...             {'sma': {'length': 20}, 'macd': {}, 'atr': {'length': 14}})
    >>> out['macd']                  # → DataFrame（macd / macdh / macds）

    Args:
        frame: K 线 DataFrame（open/high/low/close/volume，可带 datetime）
        specs: ``{指标名: 参数字典}``；``None`` → 按默认参数全算一遍

    Returns:
        dict: ``{指标名: pd.Series | pd.DataFrame}``（没有 plotinfo ——
        画图仍然走 `kline.pta_rs.*` ✓）
    """
    from ..core import CoreFunc          # 惰性导入，避免循环依赖

    if specs is None:
        specs = {name: {} for name in _INDICATOR_NAMES}
    out: dict = {}
    for name, params in specs.items():
        func = getattr(CoreFunc, f"pta_rs_{name}", None)
        if func is None:
            raise KeyError(f"没有这个 PtaRs 指标：{name!r}")
        out[name] = func(frame, **dict(params or {}))
    return out
'''


BATCH = '''


def batch(frame, specs: dict | None = None) -> dict:
    """**一次算多个 PtaRs 指标**（绕过 `@tobtind` 的包装开销 ✓）

    `@tobtind` 每个指标有 ~40–60 ms 的固定开销（取数 / 校验 / 构造
    `IndSeries` / `_plotinfo`）—— 研究场景一次算几十个指标时先把它绕掉：

    >>> from minibt.indicators.pta_rs import batch
    >>> out = batch(kline.pandas_object,
    ...             {'sma': {'length': 20}, 'macd': {}, 'atr': {'length': 14}})
    >>> out['macd']                  # → DataFrame（macd / macdh / macds）

    Args:
        frame: K 线 DataFrame（open/high/low/close/volume，可带 datetime）
        specs: ``{指标名: 参数字典}``；``None`` → 按默认参数全算一遍

    Returns:
        dict: ``{指标名: pd.Series | pd.DataFrame}``（没有 plotinfo ——
        画图仍然走 `kline.pta_rs.*` ✓）
    """
    from ..core import CoreFunc          # 惰性导入，避免循环依赖

    if specs is None:
        specs = {name: {} for name in _INDICATOR_NAMES}
    out: dict = {}
    for name, params in specs.items():
        func = getattr(CoreFunc, f"pta_rs_{name}", None)
        if func is None:
            raise KeyError(f"没有这个 PtaRs 指标：{name!r}")
        out[name] = func(frame, **dict(params or {}))
    return out
'''


HELPER = '''# <pta-rs:helpers:begin>  ← gen_pta_rs.py 生成，勿手改
# ------------------------------------------------------- PtaRs（pandas_ta 的 Rust 版）
def _pta_rs_arrays(core) -> dict:
    """取 OHLCV（**连续 float64**，`alpha` 只吃这种 ✓）+ 时间戳"""
    frame = getattr(core, "_df", core)
    out: dict = {"index": getattr(frame, "index", None)}
    for key in ("open", "high", "low", "close", "volume"):
        try:
            values = np.asarray(frame[key], dtype=np.float64)
        except Exception:                                        # noqa: BLE001
            values = None
        if values is not None:
            out[key] = np.ascontiguousarray(values.ravel())
    return out


def _pta_rs_day_stamps(core):
    """交易日的**日期前缀**（只有 `vwap` 用；别的指标不算，省 17 ms/次 ✓）"""
    frame = getattr(core, "_df", core)
    try:
        if isinstance(frame.index, pd.DatetimeIndex):
            return pd.Series(frame.index).dt.normalize().to_numpy()
        if "datetime" in frame:
            return pd.to_datetime(pd.Series(frame["datetime"])).dt.normalize(
                ).to_numpy()
    except Exception:                                            # noqa: BLE001
        return None
    return None


def _pta_rs_ema(values, length):
    """EMA（**SMA 种子**，α = 2/(n+1)）—— 和 TA-Lib / pandas_ta 完全一致 ✓

    `alpha.EMA` 是"从第一个值开始递归"，而 pandas_ta/TA-Lib 是"前 n 根均值当
    种子、从第 n 根开始递归"。把种子的位置替换掉再交给 Rust 即可 ✓
    """
    from .ta_ import _LazyModule

    alpha = _LazyModule("alpha")
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())
    window = max(1, int(length))
    valid = np.isfinite(array)
    first = 0 if valid.all() else (int(np.argmax(valid)) if valid.any()
                                  else array.size)
    out = np.full(array.shape, np.nan, dtype=np.float64)
    start = first + window - 1
    if start >= array.size:
        return out
    view = array[start:]                     # 连续**视图**，不拷数据 ✓
    raw = np.asarray(alpha.EMA(view, window), dtype=np.float64)
    # EMA 对种子是线性的：正确种子 = 前 n 根均值 → 用衰减项修正前若干根
    # （(1-α)^k < 1e-12 之后可以忽略，所以只改开头几百个点，零成本 ✓）
    seed = float(np.mean(array[first:start + 1]))
    smoothing = 2.0 / (window + 1)
    if smoothing < 1.0 and seed != float(view[0]):
        span = int(np.ceil(np.log(1e-12) / np.log1p(-smoothing)))
        limit = min(view.size, max(window, span))
        decay = np.power(1.0 - smoothing, np.arange(limit))
        raw[:limit] += (seed - float(view[0])) * decay
    out[start:] = raw
    return out


def _pta_rs_expand(func, values, length):
    """`alpha.EMA` 系列：**跳过开头的缺失值**再算，前面补 NaN ✓

    pandas 的 `ewm(min_periods=length)` 会从**第一个有效值**开始递归、前面留 NaN；
    `alpha.EMA` 见到 NaN 会整条中毒 → 这里先切掉开头的无效段。
    """
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())
    valid = np.isfinite(array)
    if valid.all():
        return func(array, int(length))
    first = int(np.argmax(valid)) if valid.any() else array.size
    out = np.full(array.shape, np.nan, dtype=np.float64)
    if first < array.size:
        out[first:] = func(np.ascontiguousarray(array[first:]), int(length))
    return out


def _pta_rs_rma(values, length):
    """Wilder 平滑 = 通达信式 `SMA(x, n, 1)`（同样跳过开头缺失）✓"""
    from .ta_ import _LazyModule

    alpha = _LazyModule("alpha")
    array = np.array(values, dtype=np.float64).ravel()      # 一次拷贝
    valid = np.isfinite(array)
    if valid.all():
        return alpha.SMA(array, int(length), 1)
    first = int(np.argmax(valid)) if valid.any() else array.size
    out = np.full(array.shape, np.nan, dtype=np.float64)
    if first < array.size:
        out[first:] = alpha.SMA(array[first:], int(length), 1)   # 视图 ✓
    return out


def _pta_rs_popstd(values, length):
    """**总体**标准差（pandas_ta 的口径）＝ 样本 std × √((n-1)/n) ✓"""
    from .ta_ import _LazyModule

    alpha = _LazyModule("alpha")
    window = max(2, int(length))
    sample = alpha.STDDEV(np.ascontiguousarray(np.asarray(values,
                                                          dtype=np.float64)),
                          window)
    return sample * np.sqrt((window - 1) / window)


#: numba（可选）—— 有就用 JIT 版滚动偏度/峰度，没有就回落 MOMENT 组合 ✓
try:                                                             # noqa: SIM105
    from numba import njit as _pta_rs_njit
except Exception:                                                # noqa: BLE001
    _pta_rs_njit = None


if _pta_rs_njit is not None:

    @_pta_rs_njit(cache=True)
    def _pta_rs_skew_kurt_numba(values, window, fourth):     # noqa: D401
        """滚动偏度 / 超额峰度（adjust=False 的 Fisher 修正，和 pandas 一致 ✓）"""
        size = values.size
        out = np.full(size, np.nan)
        if window < (4 if fourth else 3):
            return out
        for index in range(window - 1, size):
            start = index - window + 1
            total = 0.0
            for offset in range(start, index + 1):
                total += values[offset]
            mean = total / window
            sum2 = 0.0
            sum3 = 0.0
            sum4 = 0.0
            for offset in range(start, index + 1):
                delta = values[offset] - mean
                square = delta * delta
                sum2 += square
                if fourth:
                    sum4 += square * square
                else:
                    sum3 += square * delta
            variance = sum2 / (window - 1)
            if variance <= 0.0:
                continue
            std = np.sqrt(variance)
            if fourth:
                count = float(window)
                term = (count * (count + 1.0)
                        / ((count - 1) * (count - 2) * (count - 3))
                        * (sum4 / std ** 4))
                out[index] = term - (3.0 * (count - 1) ** 2
                                     / ((count - 2) * (count - 3)))
            else:
                count = float(window)
                out[index] = (count / ((count - 1) * (count - 2))
                              * (sum3 / std ** 3))
        return out


def _pta_rs_skew(values, window, fourth: bool = False) -> np.ndarray:
    """滚动偏度（`fourth=False`）/ 超额峰度（`fourth=True`）✓

    优先用 numba 的滑窗实现（单遍 O(n·w)），没有 numba 时回落
    "MOMENT + STDDEV 组合"（纯 Rust 算子，精度同样 ≤1e-6）。
    """
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())
    size = max(1, int(window))
    if _pta_rs_njit is not None and array.size > 200:
        return _pta_rs_skew_kurt_numba(array, size, bool(fourth))
    from .ta_ import _LazyModule

    alpha = _LazyModule("alpha")
    std = np.asarray(alpha.STDDEV(array, size), dtype=np.float64)
    scale = np.where(std == 0, np.nan, std)
    count = float(size)
    if fourth:
        moment = np.asarray(alpha.MOMENT(array, size, 4), dtype=np.float64)
        term = (count * (count + 1.0)
                / ((count - 1) * (count - 2) * (count - 3))
                * (moment * count / scale ** 4))
        return term - 3 * (count - 1) ** 2 / ((count - 2) * (count - 3))
    moment = np.asarray(alpha.MOMENT(array, size, 3), dtype=np.float64)
    return count / ((count - 1) * (count - 2)) * (moment * count / scale ** 3)


def _pta_rs_vwap(typical, volume, days=None) -> np.ndarray:
    """VWAP（**按交易日重置**）：numpy 前缀和实现，比 pandas `groupby.cumsum` 快 ✓"""
    size = typical.size
    wp = np.cumsum(typical * volume)
    cum_vol = np.cumsum(volume)
    if days is None or len(days) != size:
        out = wp / np.where(cum_vol == 0, np.nan, cum_vol)
        return out
    change = np.empty(size, dtype=bool)
    change[0] = True
    change[1:] = days[1:] != days[:-1]
    starts = np.flatnonzero(change)
    counts = np.diff(np.append(starts, size))
    base_index = np.maximum(starts - 1, 0)
    base_wp = np.where(starts > 0, wp[base_index], 0.0)
    base_vol = np.where(starts > 0, cum_vol[base_index], 0.0)
    group_wp = wp - np.repeat(base_wp, counts)
    group_vol = cum_vol - np.repeat(base_vol, counts)
    return group_wp / np.where(group_vol == 0, np.nan, group_vol)


def _pta_rs_count(size: int, length) -> np.ndarray:
    """每根 K 线的**实际窗口个数**（min(n, i+1)）→ 部分窗口也能算 ✓"""
    return np.minimum(max(1, int(length)),
                      np.arange(1, int(size) + 1)).astype(np.float64)


def _pta_rs_delay(values, periods: int = 1):
    """**pandas 的 `shift()`**：前面补 NaN（`alpha.REF` 是补首值 ✗ 不能直接用）"""
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())
    step = max(0, int(periods))
    if step == 0:
        return array
    out = np.full(array.shape, np.nan, dtype=np.float64)
    if step < array.size:
        out[step:] = array[:-step]
    return out


def _pta_rs_atr(high, low, close, length):
    """ATR（**含 pandas_ta 的 `presma` 种子**：前 n 根均值当首值 ✓）"""
    from .ta_ import _LazyModule

    alpha = _LazyModule("alpha")
    tr = _pta_rs_true_range(high, low, close)
    window = max(2, int(length))
    work = np.array(tr, dtype=np.float64, copy=True)
    seed = np.nanmean(work[:window])
    work[:window - 1] = np.nan
    work[window - 1] = seed
    out = np.full(work.shape, np.nan, dtype=np.float64)
    out[window - 1:] = alpha.SMA(
        np.ascontiguousarray(work[window - 1:]), window, 1)
    # pandas_ta / TA-Lib 都把"种子那一根"丢掉（`min_periods=n`）→ 对齐 ✓
    out[window - 1] = np.nan
    return out


def _pta_rs_true_range(high, low, close, drift: int = 1):
    """TR = max(H-L, |H-C₋₁|, |C₋₁-L|)；第一根缺失（和 pandas_ta 一致 ✓）"""
    previous = _pta_rs_delay(close, int(drift))
    return np.maximum(np.maximum(high - low, np.abs(high - previous)),
                      np.abs(low - previous))
# <pta-rs:helpers:end>
'''


def build_class() -> str:
    head = '''"""**PtaRs** —— pandas_ta 的 Rust 版实现（__COUNT__ 个常用指标）✓

pandas_ta 的算法核心都是"滚动算子组合"，用 `py-alpha-lib`（Rust）的算子
1:1 拼出来即可；本模块是把公式落到 minibt 指标上的外壳：

| 事项 | 说明 |
|---|---|
| 前缀 | `pta_rs_`（CoreFunc：`pta_rs_sma` …） |
| 入口 | `kline.pta_rs.sma(length=20)`（数据源 = 调用它的 IndFrame ✓） |
| 口径 | 与 `pandas_ta` **逐值一致**（尾巴对齐；开头因窗口口径差异更早出值）|
| 生成 | `scripts/gen_pta_rs.py`（别手改本文件 ✓） |

包含：__NAMES__

依赖可选包 `py-alpha-lib`（Rust）：没装时调用抛可读错误，
`import minibt` 不受影响 ✓
"""

from __future__ import annotations

from .base import tobtind
from ..utils import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_ import *
    from .core import *


class PtaRs:
    """## PtaRs（pandas_ta 的 Rust 版）

    - __COUNT__ 个常用指标，全部 `@tobtind(lib="pta_rs")`，参数名和 pandas_ta 一致；
    - 均值/通道类在主图（`overlap=True`），振荡类在副图；
    - 数值口径与 pandas_ta 对齐（总体标准差、Wilder 平滑、MACD 三线…）✓
    """
    _perfixes: str = "pta_rs_"
    _df: IndFrame | IndSeries

    def __init__(self, data):
        self._df = data
'''
    names = tuple(item['name'] for item in INDICATORS)
    head = (head.replace('__COUNT__', str(len(INDICATORS)))
                .replace('__NAMES__', ' / '.join(names)))
    head = head.replace(
        NL + NL + 'class PtaRs:',
        NL + NL + '#: 全部指标名（`batch()` 用 ✓），顺序 = 定义顺序' + NL
        + f'_INDICATOR_NAMES = {names!r}' + NL + NL + NL + 'class PtaRs:', 1)
    blocks = [head]
    for item in INDICATORS:
        args = ', '.join(f'{name}: {kind} = {default!r}'
                         for name, kind, default in item['params'])
        signature = f'self, {args}, **kwargs' if args else 'self, **kwargs'
        lines = [
            f'    @tobtind(lib="pta_rs", overlap={item["overlap"]}, '
            f'lines={item["lines"]!r})',
            f'    def {item["name"]}({signature}) -> '
            'IndSeries | IndFrame:',
            '        """' + NL.join([
                f'{item["title"]}',
                '---------',
                f'    {item["desc"]}',
                '',
                '计算方法:',
                '---------',
                f'>>> {item["formula"]}',
                '',
                '参数:',
                '---------',
                *([f'>>> {name} ({kind}): 默认: {default!r}'
                   for name, kind, default in item['params']] or ['>>> 无']),
                '',
                '说明:',
                '---------',
                '    - 口径与 `pandas_ta` 一致（尾部逐值相同）；',
                '    - 窗口是**扩张式**：比 pandas 的 `rolling(n)` 更早出值；',
                '    - 计算走 Rust（py-alpha-lib，可选依赖）✓',
            ]) + '"""',
            '        ...',
            '',
        ]
        blocks.append(NL.join(lines) + NL)
    blocks.append('    #: 全部都不是"数学工具"，都能上图 ✓\n'
                  '    NON_KLINE_INDICATORS = []\n')
    blocks.append(BATCH)
    return ''.join(blocks)


def build_core() -> str:
    out = ['# <pta-rs:methods:begin>  ← gen_pta_rs.py 生成，勿手改']
    for item in INDICATORS:
        args = ', '.join(f'{name}: {kind} = {default!r}'
                         for name, kind, default in item['params'])
        signature = f'self, {args}, **kwargs' if args else 'self, **kwargs'
        doc = [
            f'        """{item["title"]}（pandas_ta 的 Rust 版）',
            '',
            f'        {item["formula"]}',
            '',
            f'        参数：{args or "无"}',
            '        """',
        ]
        out += ['', f'    def pta_rs_{item["name"]}({signature}):']
        out += doc
        out += ['        from .ta_ import _LazyModule', '',
                '        alpha = _LazyModule("alpha")',
                '        rs = _pta_rs_arrays(self)',
                '        index = rs["index"]',
                '        close = rs.get("close")',
                '        high = rs.get("high")',
                '        low = rs.get("low")',
                '        volume = rs.get("volume")']
        out += ['        ' + line for line in item['body']]
    out.append('# <pta-rs:methods:end>')
    return NL.join(out) + NL


def splice(text: str, begin: str, end: str, block: str, anchor: str) -> str:
    if begin in text and end in text:
        head = text[:text.index(begin)]
        tail = text[text.index(end) + len(end):]
        return head + block.rstrip(NL) + tail
    index = text.index(anchor) + len(anchor)
    return text[:index] + NL + block + text[index:]


def main() -> None:
    print(f'PtaRs：{len(INDICATORS)} 个指标 → '
          + ', '.join(item['name'] for item in INDICATORS))
    if '--write' not in sys.argv:
        print('（加 --write 写文件）')
        return
    target = ROOT / 'minibt' / 'indicators' / 'pta_rs.py'
    target.write_text(build_class(), encoding='utf-8')

    core = ROOT / 'minibt' / 'core.py'
    text = core.read_text(encoding='utf-8')
    text = splice(text, '# <pta-rs:helpers:begin>', '# <pta-rs:helpers:end>',
                  HELPER,
                  '    _ALPHA_SIGNATURE_CACHE[name] = out' + NL
                  + '    return out' + NL)
    text = splice(text, '# <pta-rs:methods:begin>', '# <pta-rs:methods:end>',
                  build_core(),
                  '        return _alpha_apply(self, "ZSCORE", locals(),'
                  ' **kwargs)' + NL)
    core.write_text(text, encoding='utf-8')
    print(f'已写 {target} + core.py（pta_rs_*）')


if __name__ == '__main__':
    main()

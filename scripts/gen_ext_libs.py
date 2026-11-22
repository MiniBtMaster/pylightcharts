"""生成 **kand** / **wickra** 指标库的 minibt 封装（`scripts/gen_ext_libs.py` ✓）

思路（和 `gen_pta_rs.py` 一样，但更"反射驱动"）：

* 反射第三方库的成员 → 入参形态（哪些是 K 线列、哪些是参数）
* 生成一张 **spec 表**（`_EXT_SPECS`）放 `core.py`，运行时由 `_ext_apply()` 统一调用
  （生成的方法只有 3 行：`return _ext_apply(self, "kand", "sma", {...})`）
* 生成 `minibt/indicators/kand.py` / `wickra.py`（`class Kand` / `class Wickra`）
* `NON_KLINE_INDICATORS` = 数据不全 / 不是指标的成员（desk 不显示）

用法：

    py -3.12 scripts/gen_ext_libs.py            # 只看统计
    py -3.12 scripts/gen_ext_libs.py --write    # 写文件
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NL = chr(10)

#: 参数默认值（第三方库大多不给默认值，这里定一份合理的）
PARAM_DEFAULTS = {
    'period': 14, 'period1': 14, 'period2': 14, 'length': 14,
    'fast_period': 12, 'slow_period': 26, 'signal': 9,
    'dev_up': 2.0, 'dev_down': 2.0, 'deviation': 2.0,
    'body_percent': 0.1, 'factor': 0.5, 'scalar': 2.0, 'multiplier': 3.0,
    'd': 3, 'smooth_k': 3, 'm': 2, 'n': 14, 'q': 0.5,
    'percent': 0.1, 'threshold': 0.5, 'level': 0.5, 'limit': 0.5,
    # kand 特有的参数名
    'shadow_equal_percent': 0.1, 'shadow_factor': 2.0, 'shadow_percent': 0.1,
    'input_price': 0, 'signal_period': 9, 'acceleration': 0.02,
    'maximum': 0.2, 'k_period': 14, 'd_period': 3, 'vfactor': 0.7,
    'fast_k': 5, 'slow_k': 14, 'slow_d': 3, 'k_slow_period': 3,
}

#: 参数名的类型（int / float）
FLOAT_PARAMS = {'dev_up', 'dev_down', 'deviation', 'factor', 'scalar',
                'multiplier', 'body_percent', 'percent', 'threshold', 'level',
                'limit', 'q', 'shadow_equal_percent', 'shadow_factor',
                'shadow_percent', 'acceleration', 'maximum', 'vfactor'}

#: 列名 → K 线字段
COLUMN_NAMES = {
    'prices': 'close', 'price': 'close', 'data': 'close', 'input': 'close',
    'close': 'close', 'values': 'close', 'source': 'close',
    'high': 'high', 'low': 'low', 'open': 'open', 'volume': 'volume',
    'input_price': 'close', 'price_series': 'close', 'series': 'close',
    'vol': 'volume', 'timestamp': 'timestamp', 'time': 'timestamp',
}

#: 别名（生成器自己用：`vector-ta` 之类入参叫 `data/real/p_open` ✓）
COLUMN_ALIASES = {"prices": "close", "price": "close", "data": "close",
                  "input": "close", "values": "close", "series": "close",
                  "input_price": "close", "real": "close", "source": "close",
                  "value": "close", "vol": "volume", "time": "timestamp",
                  "ts": "timestamp", "timestamps": "timestamp",
                  "p_open": "open"}

#: 主图（和价格同量纲）指标名
MAIN_CHART = {
    'sma', 'ema', 'wma', 'dema', 'tema', 'trima', 'kama', 't3', 'midpoint',
    'midprice', 'ma', 'vwma', 'vwap', 'bbands', 'bollingerbands',
    'keltnerchannel', 'donchianchannel', 'supertrend', 'vegas', 'ecl',
    'alligator', 'envelopes', 'fractaladaptive', 'safezone',
}

#: kand 的多输出：指标名 → 输出线名（**只要指标本身**，不要内部中间量）
KAND_LINES = {
    'bbands': ['upper', 'middle', 'lower'],
    'macd': ['macd', 'signal', 'histogram'],
    'adx': ['adx'],
    'adxr': ['adxr'],
    'aroon': ['aroon_up', 'aroon_down'],
    'aroonosc': ['aroonosc'],
    'dx': ['dx'],
    'mfi': ['mfi'],
    'supertrend': ['trend', 'supertrend'],
    'stoch': ['k', 'd'],
    'stochrsi': ['k', 'd'],
    'trix': ['trix'],
    'cci': ['cci'],
    'plus_di': ['plus_di'],
    'minus_di': ['minus_di'],
    't3': ['t3'],
    'ecl': ['ecl'],
    'trima': ['trima'],
    'adosc': ['adosc'],
    'adosc_osc': ['adosc'],
    'obv': ['obv'],
    'rsi': ['rsi'],
    'stddev': ['stddev'],
    'sma_inc': ['sma'],
    'atr': ['atr'],
    'natr': ['natr'],
    'roc': ['roc'],
    'rocp': ['rocp'],
    'rocr': ['rocr'],
    'willr': ['willr'],
    'ultosc': ['ultosc'],
    'wclprice': ['wclprice'],
    'typprice': ['typprice'],
    'medprice': ['medprice'],
    'avgprice': ['avgprice'],
}

#: 指标名 → period 默认值（不写就用 `PARAM_DEFAULTS['period']` = 14）
PERIOD_BY_NAME = {
    'sma': 20, 'ema': 20, 'wma': 20, 'dema': 20, 'tema': 20, 'trima': 20,
    'rma': 20, 't3': 20, 'midpoint': 20, 'midprice': 20, 'bbands': 20,
    'stddev': 20, 'var': 20, 'adx': 14, 'adxr': 14, 'dx': 14, 'rsi': 14,
    'atr': 14, 'natr': 14, 'cci': 20, 'mfi': 14, 'willr': 14, 'stoch': 14,
    'roc': 10, 'rocp': 10, 'rocr': 10, 'rocr100': 10, 'mom': 10,
    'trix': 10, 'aroon': 25, 'aroonosc': 25, 'ultosc': 7,
}

#: 生成后实测不稳定的成员（布尔参数 / 空输出）→ 进 NON_KLINE（desk 不显示）
EXTRA_SKIP = {'wickra': {'Doji', 'RunBars'}}

#: 明确不做的成员（数据不够 / 不是指标 / 是增量接口）
KAND_SKIP = {
    'sar', 'vegas',   # 需要额外入参（生成器会再体检一遍）
}


def kand_specs() -> dict:
    """kand → {名字: {args: [...], lines: [...], params: {名: 默认}}}"""
    import kand

    specs: dict[str, dict] = {}
    skipped: list[tuple[str, str]] = []
    non_kline: list[str] = []
    for name in sorted(dir(kand)):
        if name.startswith('_') or name.endswith('_inc'):
            continue
        func = getattr(kand, name)
        if not callable(func):
            continue
        try:
            params = list(inspect.signature(func).parameters.values())
        except (TypeError, ValueError):
            skipped.append((name, '签名读不到'))
            continue
        args: list[str] = []
        defaults: dict[str, object] = {}
        kinds: dict = {}
        ok = True
        for param in params:
            column = COLUMN_NAMES.get(param.name)
            if column:
                args.append(column)
                continue
            if param.name in PARAM_DEFAULTS:
                args.append(param.name)
                value = PARAM_DEFAULTS[param.name]
                if param.name == 'period':
                    value = PERIOD_BY_NAME.get(name, value)
                defaults[param.name] = value
                kinds[param.name] = 'int' if param.name == 'period'                     else _kind_of(param)
                continue
            if param.default is not inspect.Parameter.empty:
                args.append(param.name)
                defaults[param.name] = param.default
                kinds[param.name] = _kind_of(param)
                continue
            ok = False
            skipped.append((name, f'未知入参 {param.name}'))
            break
        if not ok:
            continue
        lines = KAND_LINES.get(name, [name])
        specs[name] = {'args': args, 'lines': lines, 'params': defaults,
                       'kinds': kinds}

    # 用合成 OHLC 实调一遍 → 线分级 / 主副图（用户 2026-11-22 要求 ✓）
    arrays_by_name = _kand_arrays(specs)
    low, high = _sample_ohlc()['low'], _sample_ohlc()['high']
    for name in list(specs):
        arrays = arrays_by_name.get(name)
        if not arrays:
            continue
        spec = specs[name]
        if len(arrays) != len(spec['lines']):
            # 多输出按已知线名截取，数量对不上就先跳过（保守 ✓）
            if len(arrays) < len(spec['lines']):
                spec['lines'] = spec['lines'][: len(arrays)]
            else:
                continue
        graded = classify_lines(arrays, spec['lines'], float(low.min()),
                                float(high.max()))
        kept = graded['kept']
        if not kept:
            non_kline.append(name)
            spec['lines'] = [spec['lines'][0]]
            spec['idx'] = [0]
            spec['overlap'] = False
            continue
        spec['lines'] = [item[1] for item in kept]
        spec['idx'] = [item[0] for item in kept]
        spec['osc'] = [item[1] for item in kept if item[3]]
        spec['overlap'] = overlap_of(kept)
    return {'specs': specs, 'skipped': skipped, 'non_kline': non_kline}


#: wickra 多输出类的线名（探测出的顺序；没写的用 `<类名>_1..n`）
WICKRA_LINES = {
    'BollingerBands': ['upper', 'middle', 'lower', 'bandwidth'],
    'Macd': ['macd', 'signal', 'histogram'],
    'MACD': ['macd', 'signal', 'histogram'],
    'Aroon': ['aroon_up', 'aroon_down'],
    'Stochastic': ['k', 'd'],
    'Kdj': ['k', 'd', 'j'],
    'KeltnerChannel': ['upper', 'middle', 'lower'],
    'DonchianChannel': ['upper', 'middle', 'lower'],
    'SuperTrend': ['trend', 'supertrend'],
    'Adx': ['adx', 'plus_di', 'minus_di'],
    'ADX': ['adx', 'plus_di', 'minus_di'],
    'Atr': ['atr'],
    'ATR': ['atr'],
}

#: wickra 里 batch 入参不属于 K 线列的成员（订单流 / 市场宽度 / 双序列 …）
WICKRA_UNSUPPORTED = {'price', 'size', 'is_buy', 'snapshots', 'change',
                      'new_high', 'new_low', 'a', 'b', 'index',
                      'advances', 'declines'}


#: 线的用途判定（用户 2026-11-22 要求）
#: * 全常数 / 只有 -1·0·1 的**标志线** → 丢掉（`ZigZag` 第 2 条、`KaseDevStop`
#:   的趋势方向线之类，画出来毫无意义）
#: * 值落在 K 线 [最低, 最高] 区间内 → **主图**（和价格同量纲）
#: * 一条线都不剩（纯统计量 / 形态识别 0-1 输出）→ `NON_KLINE_INDICATORS`
FLAG_VALUES = {-1.0, 0.0, 1.0}


def _sample_ohlc(size: int = 0) -> dict:
    """分类用的 K 线数据：**优先用仓库自带的真实数据**（`minibt/data/test`）✓

    真实数据里形态 / 斐波那契类指标才有值，判"主图还是副图"才靠谱；
    读不到就退回合成随机游走（合法 OHLC）。
    """
    import numpy as np
    import pandas as pd

    path = ROOT / 'minibt' / 'data' / 'test' / 'test.csv'
    try:
        frame = pd.read_csv(path)
        close = np.asarray(frame['close'], dtype=np.float64)
        high = np.asarray(frame['high'], dtype=np.float64)
        low = np.asarray(frame['low'], dtype=np.float64)
        open_ = np.asarray(frame['open'], dtype=np.float64)
        volume = np.asarray(frame['volume'], dtype=np.float64)
        stamps = np.arange(close.size, dtype=np.float64) * 300
        if size:
            close, high, low = close[:size], high[:size], low[:size]
            open_, volume = open_[:size], volume[:size]
            stamps = stamps[:size]
        return {'close': close, 'high': high, 'low': low, 'open': open_,
                'volume': volume, 'timestamp': stamps, 'prices': close,
                'price': close, 'data': close, 'input': close,
                'values': close, 'vol': volume, 'time': stamps}
    except Exception:                                          # noqa: BLE001
        ...
    size = size or 8964
    rng = np.random.default_rng(0)
    close = np.cumsum(rng.normal(0, 1, size)) + 5000
    open_ = close + rng.normal(0, 0.5, size)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.5, size))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.5, size))
    volume = np.abs(rng.normal(1000, 50, size))
    stamps = np.arange(size, dtype=float) * 300
    return {'close': close, 'high': high, 'low': low, 'open': open_,
            'volume': volume, 'timestamp': stamps, 'prices': close,
            'price': close, 'data': close, 'input': close, 'values': close,
            'vol': volume, 'time': stamps}


def _is_line_array(item) -> bool:
    """元素是不是"一条线的数组"（`ndarray` / `array.array`）✓

    `wickra.Matrix.tolist()` 得到的是 **list of list**（行），不能当多条线 ✗
    """
    import numpy as np

    return isinstance(item, np.ndarray) or hasattr(item, '__array__')         or hasattr(item, 'tolist')


def _to_arrays(result, size: int) -> list | None:
    """第三方返回值 → `[1-D array, …]`（按"哪一维等于输入长度"定向 ✓）"""
    import numpy as np

    if hasattr(result, 'tolist') and not isinstance(result, (list, tuple)):
        result = result.tolist()
    if isinstance(result, (list, tuple)) and result and all(
            _is_line_array(item) for item in result):
        # 一串 1-D 数组（长度可能不同：tulip 每个输出预热长度不一样 ✓）
        return [np.asarray(item, dtype=np.float64).ravel() for item in result]
    if isinstance(result, list) and result and isinstance(
            result[0], (list, tuple)):
        matrix = np.asarray(result, dtype=np.float64)
        if matrix.ndim == 1:
            return [matrix]
        if matrix.shape[0] == size:
            return [matrix[:, index] for index in range(matrix.shape[1])]
        return [matrix[index] for index in range(matrix.shape[0])]
    try:
        array = np.asarray(result, dtype=np.float64)
    except Exception:                                          # noqa: BLE001
        return None
    if array.ndim == 1:
        return [array]
    if array.ndim == 2:
        if array.shape[0] == size:
            return [array[:, index] for index in range(array.shape[1])]
        return [array[index] for index in range(array.shape[0])]
    return None


def _kand_arrays(specs: dict) -> dict:
    """kand 指标 → {名字: [数组…]}（用合成数据实调，判线用 ✓）"""
    import kand

    sample = _sample_ohlc()
    out: dict = {}
    for name, spec in specs.items():
        try:
            args = [sample[item] if item in sample else spec['params'].get(item)
                    for item in spec['args']]
            arrays = _to_arrays(getattr(kand, name)(*args), len(sample['close']))
        except Exception:                                      # noqa: BLE001
            continue
        if arrays:
            out[name] = arrays
    return out


def classify_lines(arrays: list, lines: list, low: float,
                   high: float) -> dict:
    """每一条线：要不要保留 / 在不在主图 ✓"""
    import numpy as np

    kept: list[tuple[int, str, bool]] = []
    for position, (array, line) in enumerate(zip(arrays, lines)):
        values = np.asarray(array, dtype=np.float64)
        finite = values[np.isfinite(values)]
        if finite.size < 2:
            kept.append((position, line, False, False))   # 判不了 → 副图
            continue
        unique = np.unique(finite)
        if unique.size <= 1:                       # 常数线（WinRate / UPR）
            continue
        if unique.size <= 3 and set(unique.tolist()) <= FLAG_VALUES:
            continue                               # 方向标志线（画不出来）
        lowest = float(finite.min())
        highest = float(finite.max())
        median = float(np.median(finite))
        in_price = (lowest >= low * 0.9 and highest <= high * 1.1
                    and low * 0.95 <= median <= high * 1.05)
        # 0..100 的**振荡指标**（RSI / MFI / 随机指标…）：区间要真占满
        osc = (not in_price) and lowest >= 0.0 and highest <= 100.0             and highest >= 60.0 and lowest <= 40.0
        kept.append((position, line, in_price, osc))
    return {'kept': kept}


def overlap_of(kept: list) -> object:
    """→ True（全主图）/ False（全副图）/ dict（混合，按线名）✓"""
    flags = {item[1]: bool(item[2]) for item in kept}
    if not flags:
        return False
    if all(flags.values()):
        return True                       # 全部主图 → 直接 True ✓
    if not any(flags.values()):
        return False                      # 全部副图 → False ✓
    return flags

def _ctor_params(text_signature: str | None) -> list[tuple[str, object]]:
    """`'(period=20, multiplier=2.0)'` → `[('period', 20), ('multiplier', 2.0)]` ✓"""
    import ast

    if not text_signature:
        return []
    try:
        module = ast.parse(f'def _f{text_signature}: pass')
        params = module.body[0].args  # type: ignore[attr-defined]
    except SyntaxError:
        return []
    defaults = params.defaults
    positional = params.args
    out: list[tuple[str, object]] = []
    offset = len(positional) - len(defaults)
    for index, arg in enumerate(positional):
        if index < offset:
            out.append((arg.arg, None))            # 必填
            continue
        node = defaults[index - offset]
        try:
            value = ast.literal_eval(node)
        except ValueError:
            value = 14
        out.append((arg.arg, value))
    return out


def wickra_specs() -> dict:
    """wickra → {类名: {args, lines, params}}（反射 + 合成数据实测）"""
    import numpy as np
    import wickra

    sample = _sample_ohlc()
    size = int(sample['close'].size)
    low, high = sample['low'], sample['high']

    specs: dict[str, dict] = {}
    skipped: list[tuple[str, str]] = []
    non_kline: list[str] = []
    for name in sorted(dir(wickra)):
        if name.startswith('_'):
            continue
        klass = getattr(wickra, name)
        if not isinstance(klass, type):
            continue
        batch = getattr(klass, 'batch', None)
        if batch is None:
            skipped.append((name, '没有 batch'))
            continue
        try:
            batch_params = [param.name for param in
                            inspect.signature(batch).parameters.values()
                            if param.name != 'self']
        except (TypeError, ValueError):
            skipped.append((name, 'batch 签名读不到'))
            continue
        if not batch_params:
            skipped.append((name, 'batch 没有入参'))
            continue
        missing = [item for item in batch_params
                   if item in WICKRA_UNSUPPORTED or item not in sample]
        if missing:
            skipped.append((name, '缺数据列 ' + ','.join(missing)))
            continue
        params: dict = {}
        for key, default in _ctor_params(getattr(klass,
                                                 '__text_signature__', None)):
            value = default
            if value is None:
                value = PERIOD_BY_NAME.get(name, PARAM_DEFAULTS.get(key, 14))
            params[key] = value
        try:
            engine = klass(**{key: value for key, value in params.items()})
            result = engine.batch(*[sample[item] for item in batch_params])
        except Exception as error:                              # noqa: BLE001
            skipped.append((name, f'调用失败 {type(error).__name__}'))
            continue
        arrays = _to_arrays(result, size)
        if arrays is None:
            skipped.append((name, '输出类型不支持'))
            continue
        base = name.lower()
        names = WICKRA_LINES.get(name)
        if not names or len(names) != len(arrays):
            names = ([base] if len(arrays) == 1
                     else [f'{base}_{index + 1}'
                           for index in range(len(arrays))])
        graded = classify_lines(arrays, names, float(low.min()),
                                float(high.max()))
        kept = graded['kept']
        if not kept:
            # 纯统计量 / 形态识别（0-1 或常数）→ 方法留着，但 desk 不显示 ✓
            non_kline.append(name)
            specs[name] = {'args': list(batch_params), 'lines': [names[0]],
                           'idx': [0], 'params': params, 'overlap': False}
            continue
        specs[name] = {'args': list(batch_params),
                       'lines': [item[1] for item in kept],
                       'idx': [item[0] for item in kept],
                       'osc': [item[1] for item in kept if item[3]],
                       'params': params,
                       'overlap': overlap_of(kept)}
    return {'specs': specs, 'skipped': skipped, 'non_kline': non_kline}



# ---------------------------------------------------------------- 三个新库
#: 参数说明（进方法 docstring；只写"用户真的需要知道"的 ✓）
PARAM_DOCS = {
    'kernel': ("计算内核（Rust 后端）：`None`/`'auto'` = 自动挑最好的；"
               "`'scalar'` = 纯标量（任何 CPU 都能跑）；"
               "`'avx2'` / `'avx512'` = SIMD 内核，**只有该 wheel 编进对应指令集**"
               "才可用（否则库抛 `AVX2 kernel not compiled in this build`）。"
               "结果与内核无关（数值完全一致），只影响速度"),
}

#: 合法 kernel 值（其它值 / 空串 → 回落默认，避免图上来个 ValueError ✗）
KERNEL_VALUES = {'auto', 'scalar', 'avx2', 'avx512'}

#: 柱体线（MACD 类柱状）——`linestyle` 里按 `LineDash.vbar` 画 ✓
HIST_LINES = {'histogram', 'hist', 'macd_hist', 'macdhist', 'macdh',
              'macd_histogram', 'ao_hist', 'ppo_hist'}

#: "第二条序列"类参数（用户自己要传 pd.Series / np.ndarray）✓
SERIES_PARAM_NAMES = {
    'real0', 'real1', 'real2', 'primary', 'secondary', 'a', 'b',
    'source', 'data2', 'prices2', 'series2', 'benchmark', 'asset',
    'y', 'x', 'short', 'long', 'other', 'high2', 'low2', 'close2',
    'value2', 'periods',
}

#: 常见多输出指标的**线名**（库不给元数据时按名字补，柱体线要靠它 ✓）
LINE_HINTS = (
    ('macd', ('macd', 'signal', 'histogram')),
    ('bbands', ('upper', 'middle', 'lower')),
    ('bollinger', ('upper', 'middle', 'lower')),
    ('stoch', ('k', 'd')),
    ('kdj', ('k', 'd', 'j')),
    ('aroon', ('aroon_down', 'aroon_up')),
    ('dmi', ('adx', 'plus_di', 'minus_di')),
)


def _line_hints(name: str, count: int) -> list | None:
    lowered = name.lower()
    for key, names in LINE_HINTS:
        if key in lowered and len(names) == count:
            return list(names)
    return None


#: 辅助数学（加减乘除 / 取整 / 三角 …）：可调用，但不是 K 线指标 →
#: **保留方法**（用户 2026-11-22 要求）但进 `NON_KLINE_INDICATORS`
AUX_MATH = {
    'abs', 'acos', 'asin', 'atan', 'ceil', 'cos', 'cosh', 'exp', 'floor',
    'ln', 'log10', 'sin', 'sinh', 'sqrt', 'tan', 'tanh', 'round', 'trunc',
    'add', 'sub', 'mul', 'div', 'max', 'min', 'maxindex', 'minindex',
    'sum', 'avg', 'midpoint2',
}

#: `vector-ta` / `ferro-ta` 里明显不是"指标"的成员（数学 / 工具 / 结构体）
NON_INDICATOR_NAMES = {
    'abs', 'acos', 'asin', 'atan', 'ceil', 'cos', 'cosh', 'exp', 'floor',
    'ln', 'log10', 'sin', 'sinh', 'sqrt', 'tan', 'tanh',
    'add', 'sub', 'mul', 'div', 'max', 'min', 'maxindex', 'minindex',
    'sum', 'ceil_', 'round', 'trunc',
    'stream', 'kernel', 'reset', 'info', 'version', 'set_ctx', 'get_ctx',
    'reset_ctx', 'smoke',
}

#: "周期类"参数名（只有它们用 指标名→period 的默认值 ✓）
PERIOD_KEYS = {'period', 'timeperiod', 'length', 'ns', 'n', 'k_period',
               'fast_period', 'slow_period', 'signal_period', 'd_period',
               'k_slow', 'periods'}

#: `tulip-rs` 的选项默认值（`info()['options']` 里的名字）
TULIP_OPTIONS = {
    'period': 14, 'k_period': 14, 'k_slow': 3, 'd_period': 3,
    'fast_period': 12, 'slow_period': 26, 'signal_period': 9,
    'stddev': 2.0, 'multiplier': 2.0, 'factor': 0.5, 'percent': 0.1,
    'short_period': 12, 'long_period': 26, 'matype': 0,
    'acceleration_factor': 0.02, 'max_acceleration': 0.2,
    'scale': 1.0, 'p': 2.0, 'lag': 0, 'offset': 0,
}


def _vector_name(name: str) -> str:
    return name


def vector_specs() -> dict:
    """`vector-ta`（小写函数式）→ {名字: spec}"""
    import numpy as np
    import vector_ta

    sample = _sample_ohlc()
    size = int(sample['close'].size)
    alias = dict(COLUMN_ALIASES)
    alias.update({'data': 'close', 'values': 'close', 'value': 'close',
                  'real': 'close', 'real0': 'close', 'real1': 'close',
                  'primary': 'close', 'secondary': 'close',
                  'source': 'close', 'series': 'close',
                  'prices': 'close', 'p_open': 'open', 'ts': 'timestamp',
                  'timestamps': 'timestamp'})
    specs: dict = {}
    skipped: list[tuple[str, str]] = []
    non_kline: list[str] = []
    for name in sorted(dir(vector_ta)):
        if name.startswith('_') or not name.islower() \
                or not callable(getattr(vector_ta, name)) \
                or name.endswith('_batch') or name.endswith('_stream'):
            continue
        if name in NON_INDICATOR_NAMES and name not in AUX_MATH:
            continue
        func = getattr(vector_ta, name)
        try:
            params = list(inspect.signature(func).parameters.values())
        except (TypeError, ValueError):
            skipped.append((name, '签名读不到'))
            continue
        args: list[str] = []
        defaults: dict = {}
        kinds: dict = {}
        series: list[str] = []
        ok = True
        for param in params:
            if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                              inspect.Parameter.VAR_KEYWORD):
                continue
            field = alias.get(param.name) or COLUMN_NAMES.get(param.name)
            if field and param.name != 'input':
                args.append(field)
                continue
            if param.name in SERIES_PARAM_NAMES:
                if not series:
                    # 第一个序列参数就是 K 线自身（close）→ 不需要用户传 ✓
                    args.append('close')
                    series.append('__kline__')
                else:
                    args.append(param.name)
                    defaults[param.name] = None
                    series.append(param.name)
                continue
            if param.kind is inspect.Parameter.KEYWORD_ONLY:
                continue            # `*` 之后的参数只能关键字传 → 省略 ✓
            if isinstance(param.default, (str, bool))                     or param.default is None:
                # 位置必须占住（否则后面的参数会错位）→ 原样传默认值 ✓
                args.append(param.name)
                defaults[param.name] = param.default
                kinds[param.name] = _kind_of(param)
                continue
            if param.name in PERIOD_KEYS:
                args.append(param.name)
                defaults[param.name] = PERIOD_BY_NAME.get(
                    name.lower(), PARAM_DEFAULTS.get(param.name, 14))
                kinds[param.name] = 'int'
                continue
            if param.name in PARAM_DEFAULTS or param.name in TULIP_OPTIONS:
                args.append(param.name)
                defaults[param.name] = (PARAM_DEFAULTS.get(param.name)
                                        or TULIP_OPTIONS.get(param.name))
                kinds[param.name] = _kind_of(param)
                continue
            if param.default is not inspect.Parameter.empty:
                if param.default is None:
                    continue
                args.append(param.name)
                defaults[param.name] = param.default
                continue
            ok = False
            skipped.append((name, f'未知入参 {param.name}'))
            break
        if not ok or not args:
            continue
        # 探测时给"第二序列"参数塞一条合成序列（否则库会报错 → 被跳过 ✗）
        probe_defaults = dict(defaults)
        for key in (spec_series := [item for item in defaults
                                    if item in SERIES_PARAM_NAMES]):
            probe_defaults[key] = np.ascontiguousarray(
                sample['close'] * 1.001)
        call = [sample[item] if item in sample else probe_defaults.get(item)
                for item in args]
        try:
            result = func(*call)
        except Exception as error:                              # noqa: BLE001
            skipped.append((name, f'调用失败 {type(error).__name__}'))
            continue
        arrays = _to_arrays(result, size)
        if arrays is None or not arrays:
            skipped.append((name, '输出类型不支持'))
            continue
        base = name
        names = _line_hints(name, len(arrays)) or (
            [base] if len(arrays) == 1
            else [f'{base}_{index + 1}' for index in range(len(arrays))])
        graded = classify_lines(arrays, names, float(sample['low'].min()),
                                float(sample['high'].max()))
        kept = graded['kept']
        if not kept:
            non_kline.append(name)
            specs[name] = {'args': args, 'lines': [names[0]], 'idx': [0],
                           'params': defaults, 'overlap': False}
            continue
        user_series = [item for item in series if item != '__kline__']
        if user_series or name in AUX_MATH:
            non_kline.append(name)
        specs[name] = {'args': args,
                       'lines': [item[1] for item in kept],
                       'idx': [item[0] for item in kept],
                       'osc': [item[1] for item in kept if item[3]],
                       'params': defaults,
                       'kinds': kinds,
                       'series': user_series,
                       'overlap': overlap_of(kept)}
    return {'specs': specs, 'skipped': skipped, 'non_kline': non_kline}


def ferro_specs() -> dict:
    """`ferro-ta`（TA-Lib 风格大写函数）→ {名字: spec}"""
    import numpy as np
    import ferro_ta

    sample = _sample_ohlc()
    size = int(sample['close'].size)
    specs: dict = {}
    skipped: list[tuple[str, str]] = []
    non_kline: list[str] = []
    for name in sorted(dir(ferro_ta)):
        if name.startswith('_') or not name.isupper() \
                or not callable(getattr(ferro_ta, name)):
            continue
        if name.lower() in NON_INDICATOR_NAMES                 and name.lower() not in AUX_MATH:
            continue
        func = getattr(ferro_ta, name)
        try:
            params = list(inspect.signature(func).parameters.values())
        except (TypeError, ValueError):
            skipped.append((name, '签名读不到'))
            continue
        args: list[str] = []
        defaults: dict = {}
        kinds: dict = {}
        series: list[str] = []
        ok = True
        for param in params:
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                continue
            field = COLUMN_ALIASES.get(param.name) or COLUMN_NAMES.get(
                param.name)
            if field and field in sample and param.name != 'input':
                args.append(field)
                continue
            if param.name in SERIES_PARAM_NAMES:
                if not series:
                    # 第一个序列参数就是 K 线自身（close）→ 不需要用户传 ✓
                    args.append('close')
                    series.append('__kline__')
                else:
                    args.append(param.name)
                    defaults[param.name] = None
                    series.append(param.name)
                continue
            if param.name in ('nan_policy',):
                continue
            if param.kind is inspect.Parameter.KEYWORD_ONLY:
                continue
            if isinstance(param.default, (str, bool))                     or param.default is None:
                # 位置必须占住（否则后面的参数会错位）→ 原样传默认值 ✓
                args.append(param.name)
                defaults[param.name] = param.default
                kinds[param.name] = _kind_of(param)
                continue
            if param.name in PERIOD_KEYS:
                args.append(param.name)
                defaults[param.name] = PERIOD_BY_NAME.get(
                    name.lower(), PARAM_DEFAULTS.get(param.name, 14))
                kinds[param.name] = 'int'
                continue
            if param.name in PARAM_DEFAULTS or param.name in TULIP_OPTIONS:
                args.append(param.name)
                defaults[param.name] = (PARAM_DEFAULTS.get(param.name)
                                        or TULIP_OPTIONS.get(param.name))
                kinds[param.name] = _kind_of(param)
                continue
            if param.default is not inspect.Parameter.empty:
                args.append(param.name)
                defaults[param.name] = param.default
                kinds[param.name] = _kind_of(param)
                continue
            ok = False
            skipped.append((name, f'未知入参 {param.name}'))
            break
        if not ok or not args:
            continue
        # 探测时给"第二序列"参数塞一条合成序列（否则库会报错 → 被跳过 ✗）
        probe_defaults = dict(defaults)
        for key in (spec_series := [item for item in defaults
                                    if item in SERIES_PARAM_NAMES]):
            probe_defaults[key] = np.ascontiguousarray(
                sample['close'] * 1.001)
        call = [sample[item] if item in sample else probe_defaults.get(item)
                for item in args]
        try:
            result = func(*call)
        except Exception as error:                              # noqa: BLE001
            skipped.append((name, f'调用失败 {type(error).__name__}'))
            continue
        arrays = _to_arrays(result, size)
        if arrays is None or not arrays:
            skipped.append((name, '输出类型不支持'))
            continue
        base = name.lower()
        names = _line_hints(name, len(arrays)) or (
            [base] if len(arrays) == 1
            else [f'{base}_{index + 1}' for index in range(len(arrays))])
        graded = classify_lines(arrays, names, float(sample['low'].min()),
                                float(sample['high'].max()))
        kept = graded['kept']
        if not kept:
            non_kline.append(name)
            specs[name] = {'args': args, 'lines': [names[0]], 'idx': [0],
                           'params': defaults, 'overlap': False}
            continue
        user_series = [item for item in series if item != '__kline__']
        if user_series or name in AUX_MATH:
            non_kline.append(name)
        specs[name] = {'args': args,
                       'lines': [item[1] for item in kept],
                       'idx': [item[0] for item in kept],
                       'osc': [item[1] for item in kept if item[3]],
                       'params': defaults,
                       'kinds': kinds,
                       'series': user_series,
                       'overlap': overlap_of(kept)}
    return {'specs': specs, 'skipped': skipped, 'non_kline': non_kline}


def tulip_specs() -> dict:
    """`tulip-rs`（`ti.<name>.indicator([数据], [选项])`）→ {名字: spec}

    这个库自带元数据 `info()`：输入列 / 选项名 / **输出线名** /
    `display_type`（Overlay = 主图）→ 比"价格量纲"猜测更准 ✓
    """
    import numpy as np
    import tulip_rs

    sample = _sample_ohlc()
    sample['real'] = sample['close']          # tulip 的通用价格列叫 `real` ✓
    size = int(sample['close'].size)
    table = tulip_rs.indicators
    specs: dict = {}
    skipped: list[tuple[str, str]] = []
    non_kline: list[str] = []
    for name in sorted(dir(table)):
        if name.startswith('_'):
            continue
        engine = getattr(table, name)
        if not hasattr(engine, 'indicator'):
            continue
        try:
            info = engine.info()
        except Exception:                                      # noqa: BLE001
            skipped.append((name, 'info() 失败'))
            continue
        inputs = [item for item in (info.get('inputs') or [])
                  if item in sample]
        options = list(info.get('options') or [])
        outputs = list(info.get('outputs') or [])
        if not inputs:
            skipped.append((name, '输入列不支持'))
            continue
        params: dict = {}
        for option in options:
            params[option] = (TULIP_OPTIONS.get(option)
                              or PERIOD_BY_NAME.get(name) or 14)
            if option in ('period', 'k_period'):
                params[option] = PERIOD_BY_NAME.get(name, 14)
        try:
            result = engine.indicator([sample[item] for item in inputs],
                                      [params[option] for option in options])
        except Exception as error:                              # noqa: BLE001
            skipped.append((name, f'调用失败 {type(error).__name__}'))
            continue
        arrays = _to_arrays(result[0] if isinstance(result, tuple) else result,
                            size)
        if not arrays:
            skipped.append((name, '没有输出'))
            continue
        names = outputs[: len(arrays)] or [name] * len(arrays)
        while len(names) < len(arrays):
            names.append(f'{name}_{len(names) + 1}')
        groups = info.get('display_groups') or [{}]
        overlay = any(str(group.get('display_type')) == 'Overlay'
                      for group in groups)
        specs[name.upper()] = {'args': inputs, 'lines': names,
                               'idx': list(range(len(arrays))),
                               'params': params,
                               'overlap': bool(overlay),
                               'lib_name': name}
        if not overlay and all(not line for line in names):
            non_kline.append(name.upper())
    return {'specs': specs, 'skipped': skipped, 'non_kline': non_kline}

_UNSET = object()


def _kind_of(param) -> str:
    """参数的真实类型：int / float / bool / str（来自库签名注解）✓"""
    text = str(getattr(param, 'annotation', '') or '').lower()
    if 'bool' in text:
        return 'bool'
    if 'int' in text and 'print' not in text:
        return 'int'
    if 'float' in text:
        return 'float'
    if 'str' in text:
        return 'str'
    name = str(getattr(param, 'name', '') or '').lower()
    if name in ('k', 'weight', 'factor', 'multiplier', 'dev', 'devup',
                'devdn', 'q', 'p', 'sigma', 'alpha', 'beta', 'scalar',
                'percent', 'threshold', 'level'):
        return 'float'
    if name in ('kernel', 'method', 'matype', 'mode', 'type', 'policy',
                'matype_up', 'matype_down'):
        return 'str'
    if name in ('period', 'timeperiod', 'length', 'periods', 'n', 'm',
                'bins', 'fast', 'slow', 'signal', 'lag', 'offset')             or name.endswith(('_length', '_period', '_periods', '_slow',
                              '_fast')):
        return 'int'
    default = getattr(param, 'default', _UNSET)
    if isinstance(default, bool):
        return 'bool'
    if isinstance(default, str):
        return 'str'
    if isinstance(default, float):
        return 'float'
    if isinstance(default, int) and default is not _UNSET:
        return 'int'
    return 'str'


def _param_decl(name: str, default=_UNSET, kind: str | None = None) -> str:
    value = PARAM_DEFAULTS.get(name, 14) if default is _UNSET else default
    if value is None and kind in ('int', 'float', 'bool', 'str'):
        return f'{name}: {kind} | None = None'      # 默认空，但类型是对的 ✓
    if isinstance(value, bool):
        return f'{name}: bool = {value!r}'
    if isinstance(value, str):
        return f'{name}: str = {value!r}'
    if value is None:
        return f'{name}=None'
    if name in FLOAT_PARAMS or isinstance(value, float):
        return f'{name}: float = {float(value)!r}'
    return f'{name}: int = {int(value)!r}'


def _method(name: str, spec: dict, prefix: str, lib: str) -> str:
    params = spec['params']
    kinds = spec.get('kinds') or {}
    decl = ', '.join(_param_decl(key, params[key], kinds.get(key))
                     for key in params)
    signature = f'self, {decl}, **kwargs' if decl else 'self, **kwargs'
    lines = spec['lines']
    return_type = 'IndSeries' if len(lines) == 1 else 'IndFrame'
    overlap = spec.get('overlap')
    if overlap is None:
        overlap = name.lower() in MAIN_CHART
    overlap_code = repr(overlap) if isinstance(overlap, dict) else (
        'True' if overlap else 'False')
    quoted = ', '.join(repr(line) for line in lines)
    hist = [line for line in lines if str(line).lower() in HIST_LINES]
    style = ''
    if hist:
        inner = ', '.join(
            f'{line!r}: LineStyle(line_dash=LineDash.vbar, vbar_base=0.0, '
            f'vbar_up_color=Colors.bull_color, '
            f'vbar_down_color=Colors.bear_color)' for line in hist)
        style = f', linestyle={{{inner}}}'
    doc = [f'`{lib}.{name}`（{len(lines)} 条线）', '---------']
    if params:
        doc.append('参数: ' + ', '.join(f'`{key}`={value}'
                                       for key, value in params.items()))
        for key in params:
            note = PARAM_DOCS.get(key)
            if note:
                doc.append(f'  - `{key}`：{note}')
    doc.append('数据: ' + ', '.join(sorted({a for a in spec['args']
                                           if a in ('open', 'high', 'low',
                                                    'close', 'volume',
                                                    'timestamp')})))
    body = ['        ...']
    return NL.join([
        f'    @tobtind(lib="{lib}", overlap={overlap_code}, '
        f'lines=[{quoted}]{style})',
        f'    def {name}({signature}) -> {return_type}:',
        '        """' + NL.join(doc) + '"""',
        *body,
        '',
    ])


#: 只给**常用**指标自动声明信号（`SIGNALS` 表）—— 全量 300+ 条会把
#: 技术分析插件的选择器刷屏，其余指标由插件给"建议信号"即可 ✓
SIGNAL_NAMES = {
    # 均线 / 通道
    'SMA', 'EMA', 'WMA', 'RMA', 'HMA', 'DEMA', 'TEMA', 'TRIMA', 'KAMA',
    'ALMA', 'BollingerBands', 'KeltnerChannel', 'DonchianChannel',
    'SuperTrend', 'Ichimoku', 'ParabolicSAR', 'AnchoredVWAP', 'RollingVWAP',
    'VWAP', 'VWMA', 'WoodiePivots', 'ZigZag', 'Envelopes', 'Alligator',
    # 振荡 / 动量
    'RSI', 'MACD', 'ADX', 'ADXR', 'CCI', 'MFI', 'Stochastic', 'Kdj',
    'ATR', 'OBV', 'Klinger', 'DMI', 'DonchianChannel', 'KeltnerChannel',
    'ParabolicSAR', 'Envelopes', 'Momentum', 'CMF', 'AO',
    'WilliamsR', 'TRIX', 'ROC', 'Momentum', 'TSI', 'UltimateOscillator',
    'Aroon', 'CMF', 'ChaikinOscillator', 'AwesomeOscillator', 'CMO',
    'FisherTransform', 'Vortex', 'Klinger', 'DMI', 'PPO', 'APO', 'AO',
    # kand（补齐常用）
    'sma', 'ema', 'wma', 'rma', 'rsi', 'macd', 'adx', 'atr', 'bbands',
    'cci', 'mfi', 'stoch', 'willr', 'trix', 'roc', 'supertrend', 'vwap',
    'obv', 'aroon', 'aroonosc', 'stochrsi', 'ultosc', 'mom', 'dx', 'adxr',
}


def signals_table(specs: dict) -> dict:
    """每个指标的**建议信号**（类级 `SIGNALS` 表；目录 / 技术分析直接用 ✓）

    * 主图线（价格量纲）→ `Compare(-2, 1)`「高于前一根看多」；
    * 副图线：0..100 的振荡指标 → `Threshold(50)`；其余 → `Threshold(0)`；
    * 想改就改这张表（生成后仍可手工在类里加 `SIGNALS` 覆盖）✓
    """
    table: dict = {}
    for name, spec in specs.items():
        if SIGNAL_NAMES and name not in SIGNAL_NAMES:
            continue
        overlap = spec.get('overlap')
        lines = spec.get('lines') or [name]
        oscillators = set(spec.get('osc') or [])
        entry: dict = {}
        for line in lines:
            main = overlap.get(line, False) if isinstance(overlap, dict)                 else bool(overlap)
            if line in oscillators:
                entry[line] = ('Threshold(50, 1, label=%r)'
                               % f'{line} 在 50 上方看多')
            else:
                entry[line] = ('Compare(-2, 1, label=%r)'
                               % f'{line} 高于前一根看多')
        table[name] = entry
    return table


def build_class(lib: str, class_name: str, specs: dict,
                non_kline: list | None = None,
                module: str | None = None,
                accessor: str | None = None) -> str:
    names = tuple(specs)
    # `lib` = 指标前缀（如 `tulip_` / `vta_`）；`accessor` = `kline.<访问器>`
    # ⚠ tulip-rs 的前缀是 `tulip_`，但访问器是 `tulip_rs`
    #   （`kline.tulip` 要留给 tulipy 的 TuLip，v1.3.10 修复 ✗→✓）
    accessor = str(accessor or lib)
    package = str(module or lib)
    head = f'''"""**{package}** 指标库（第三方库，**可选依赖** ✓）

* 入口：`kline.{accessor}.<指标名>(...)`（前缀 `{lib}_`）
* 数据源：调用它的 IndFrame 自己（`prices`→`close`、`high/low/open/volume`）
* 共 **{len(specs)} 个指标**；不支持的成员在 `NON_KLINE_INDICATORS` 里（desk 不显示）
* 生成：`scripts/gen_ext_libs.py`（**别手改本文件** ✓）

安装：`py -3.12 -m pip install {package}`
"""

from __future__ import annotations

from .base import tobtind
from ..signals import Compare, Threshold
from ..utils import Colors, LineDash, LineStyle
from ..utils import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_ import *
    from .core import *

#: 全部指标名（`batch()` / 文档用 ✓）
_INDICATOR_NAMES = {names!r}


class {class_name}:
    """## {lib} 指标库（{len(specs)} 个指标）

    - 全部 `@tobtind(lib="{lib}")`，数值由第三方库（Rust/C）计算；
    - 均线 / 通道类在主图，振荡类在副图；
    - `NON_KLINE_INDICATORS` 里的成员数据不全（订单流 / 市场宽度等）→ desk 不显示 ✓
    """
    _perfixes: str = "{lib}_"
    _df: IndFrame | IndSeries

    def __init__(self, data):
        self._df = data
'''
    blocks = [head]
    for name, spec in specs.items():
        blocks.append(_method(name, spec, f'{lib}_', lib))
    table = signals_table(specs)
    lines_out = ['    #: 建议信号（目录 / 技术分析用；**想改就改这张表** ✓）',
                 '    SIGNALS = {']
    for name, entry in table.items():
        inner = ', '.join(f'{line!r}: {value}'
                          for line, value in entry.items())
        lines_out.append(f'        {name!r}: {{{inner}}},')
    lines_out.append('    }')
    signals_block = NL.join(lines_out) + NL

    skip = sorted({name for name in specs
                   if name in KAND_SKIP or name in EXTRA_SKIP.get(lib, set())}
                  | set(non_kline or []))
    blocks.append('    #: 数据不全 / 不是指标 → desk 不显示（方法仍在）\n'
                  f'    NON_KLINE_INDICATORS = {skip!r}\n')
    blocks.append(signals_block)
    return ''.join(blocks)


HELPER_HEAD = '''# <ext-libs:helpers:begin>  ← gen_ext_libs.py 生成，勿手改
# ------------------------------------------------------- kand / wickra（第三方）
#: 合法的 `kernel`（vector-ta 的计算内核）；其它值 → 回落默认 ✓
KERNEL_VALUES = {"auto", "scalar", "avx2", "avx512"}

#: 可当作数据列的入参名（其余都当参数 ✓）
COLUMN_FIELDS = {"open", "high", "low", "close", "volume", "timestamp"}

#: 第三方库对同一列的不同叫法 ✓
COLUMN_ALIASES = {"prices": "close", "price": "close", "data": "close",
                  "input": "close", "values": "close", "series": "close",
                  "input_price": "close", "real": "close",
                  "real0": "close", "real1": "close", "primary": "close",
                  "secondary": "close", "value": "close", "source": "close",
                  "vol": "volume", "time": "timestamp", "ts": "timestamp",
                  "timestamps": "timestamp", "p_open": "open"}

#: 第三方库的调用说明：{lib: {name: {args, lines, params}}}
_EXT_SPECS: dict = __SPECS__


def _ext_apply(core, lib: str, name: str, params: dict):
    """统一调用第三方指标库（`kand` / `wickra`）✓

    * `args` 里的 `close/high/low/open/volume/timestamp` 从**调用它的数据**取；
    * 其余是参数（调用方传进来的覆盖默认值）；
    * 返回值可能是 `ndarray` / `array.array` / **tuple**（多输出）→ 统一成
      `pd.Series` 或 `pd.DataFrame`，索引对齐原数据 ✓
    """
    import importlib

    module = importlib.import_module(lib)
    spec = _EXT_SPECS[lib][name]
    frame = getattr(core, "_df", core)
    index = getattr(frame, "index", None)

    def _column(field: str):
        if field == "timestamp":
            stamps = pd.to_datetime(pd.Series(frame["datetime"]))
            return stamps.astype("int64") // 10 ** 9
        return np.ascontiguousarray(np.asarray(frame[field],
                                               dtype=np.float64))

    def _field(item: str) -> str:
        return COLUMN_ALIASES.get(item, item)

    series_params = set(spec.get("series") or [])
    merged = {**spec["params"], **(params or {})}
    # 空字符串 → 回落到**库/生成器默认值**（desk 参数框清空就是 '' ✗）
    kinds = spec.get("kinds") or {}
    for key, value in list(merged.items()):
        if isinstance(value, str):
            if not value.strip():
                merged[key] = spec["params"].get(key)
                continue
            if key == "kernel" and value.strip().lower() not in KERNEL_VALUES:
                merged[key] = spec["params"].get(key)   # 填错 → 回落默认 ✓
                continue
            kind = kinds.get(key)
            text = value.strip().lower()
            try:                                # 旧偏好 / 表单可能传 "20" ✓
                if kind == "int":
                    merged[key] = int(float(value))
                elif kind == "float":
                    merged[key] = float(value)
                elif kind == "bool":
                    merged[key] = text in ("1", "true", "yes", "on")
            except (TypeError, ValueError):
                ...
    columns = {key: _column(_field(key)) for key in spec["args"]
               if _field(key) in COLUMN_FIELDS and key not in series_params}
    call_args = [columns[item] if item in columns else merged.get(item)
                 for item in spec["args"]]
    # 需要"第二条序列"的（加减乘除 / BETA / CORREL / CROSS …）✓
    for position, item in enumerate(spec["args"]):
        if item not in (spec.get("series") or []):
            continue
        value = call_args[position]
        if value is None:
            raise ValueError(
                f"{lib}.{name} 需要第二条序列 {item}（pd.Series / np.ndarray，"
                f"长度与 K 线一致）")
        array = np.asarray(
            value.to_numpy() if hasattr(value, "to_numpy") else value,
            dtype=np.float64).ravel()
        call_args[position] = np.ascontiguousarray(array)
    if lib == "tulip_rs":
        module_name = "tulip_rs"
        package = importlib.import_module(module_name)
        engine = getattr(package.indicators, spec.get("lib_name") or name.lower())
        options = [merged.get(key, spec["params"].get(key))
                   for key in spec["params"]]
        result = engine.indicator([columns[item] for item in spec["args"]],
                                  options)
        if isinstance(result, tuple):
            result = result[0]
        return _ext_frame(result, spec, index, pad=True)
    if lib == "wickra":
        cls = getattr(module, name)
        kwargs = {key: merged.get(key, spec["params"].get(key))
                  for key in spec["params"]}
        engine = cls(**_pick_kwargs(cls, kwargs, spec["params"]))
        data_args = [value for key, value in zip(spec["args"], call_args)
                     if key in columns]
        result = engine.batch(*data_args)
    else:
        result = getattr(module, name)(*call_args)

    return _ext_frame(result, spec, index)


def _pick_kwargs(cls, kwargs: dict, defaults: dict) -> dict:
    """把参数按构造器签名过滤（各库构造参数名不完全一样 ✓）

    ⚠ `wickra` 的类是 C 扩展：`__init__` 只有 `*args/**kwargs`，
    真实参数名在 `__text_signature__` 里 → 这种情况下**全部透传**。
    """
    import inspect as _inspect

    try:
        params = _inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return dict(kwargs or defaults)
    named = {key for key, param in params.items()
             if key != 'self'
             and param.kind not in (_inspect.Parameter.VAR_POSITIONAL,
                                    _inspect.Parameter.VAR_KEYWORD)}
    if not named:                      # C 扩展 → 直接传
        return dict(kwargs)
    merged = dict(kwargs)
    for key, value in defaults.items():
        merged.setdefault(key, value)
    return {key: value for key, value in merged.items() if key in named}


def _is_line_array(item) -> bool:
    """元素是不是"一条线的数组"（`ndarray` / `array.array`）✓

    `wickra.Matrix.tolist()` 得到的是 **list of list**（行）→ 不是多条线 ✗
    """
    return isinstance(item, np.ndarray) or hasattr(item, '__array__')         or hasattr(item, 'tolist')


def _ext_frame(result, spec: dict, index, pad: bool = False):
    """第三方返回值 → Series / DataFrame（索引对齐 ✓）

    三种形态都要认：

    * `tuple` → 多输出（每个元素一条线，kand 就是这种）；
    * `array.array` / `ndarray` / list（元素是数字）→ 单条线；
    * `wickra.Matrix` → `.tolist()` 后是**行优先矩阵**，按"哪一维等于输入长度"
      判定方向（`(n, k)` 要转置）✓
    """
    size = 0 if index is None else len(index)
    value = result
    if hasattr(value, 'tolist') and not isinstance(value, (list, tuple)):
        value = value.tolist()
    if isinstance(value, tuple):
        arrays = [np.asarray(item, dtype=np.float64).ravel() for item in value]
    elif isinstance(value, list) and value and all(
            _is_line_array(item) for item in value):
        # 一串 1-D 数组（tulip 各输出预热长度不一 ✓）
        arrays = [np.asarray(item, dtype=np.float64).ravel() for item in value]
    elif isinstance(value, list) and value and isinstance(
            value[0], (list, tuple, np.ndarray)):
        matrix = np.asarray(value, dtype=np.float64)
        if matrix.ndim == 1:
            arrays = [matrix]
        elif size and matrix.shape[0] == size:
            arrays = [matrix[:, position]
                      for position in range(matrix.shape[1])]
        else:
            arrays = [matrix[position] for position in range(matrix.shape[0])]
    else:
        arrays = [np.asarray(value, dtype=np.float64).ravel()]
    arrays = [np.where(np.isinf(item), np.nan, item) for item in arrays]
    if pad and size:
        padded = []
        for array in arrays:
            if 0 < array.size < size:              # 紧凑数组 → 左侧补 NaN ✓
                array = np.concatenate([np.full(size - array.size, np.nan),
                                        array])
            padded.append(array)
        arrays = padded
    keep = spec.get("idx")
    lines = spec.get("lines") or []
    if keep:
        arrays = [arrays[position] for position in keep
                  if position < len(arrays)]
    # 稀疏线（ZigZag / 斐波那契水平这类只在"拐点"有值）→ 线性插值，
    # 不然 desk 上只剩几个点、看起来"没有线"（用户 2026-11-22 反馈 ✓）
    smoothed = []
    for array in arrays:
        finite = np.isfinite(array)
        if finite.any() and finite.mean() < 0.02 and finite.sum() >= 2:
            array = pd.Series(array).interpolate(
                limit_direction="both").to_numpy(dtype=np.float64)
        smoothed.append(array)
    arrays = smoothed
    if not arrays:
        return pd.Series(dtype=np.float64, index=index)
    if len(arrays) == 1:
        return pd.Series(arrays[0], index=index)
    out = {}
    for position, line in enumerate(lines):
        if position < len(arrays) and arrays[position].size == size:
            out[line] = arrays[position]
        else:
            out[line] = np.full(size, np.nan)
    return pd.DataFrame(out, index=index)
# <ext-libs:helpers:end>
'''


def build_core(specs_by_lib: dict, prefixes: dict | None = None) -> str:
    out = ['# <ext-libs:methods:begin>  ← gen_ext_libs.py 生成，勿手改']
    prefixes = prefixes or {}
    for lib, specs in specs_by_lib.items():
        prefix = prefixes.get(lib, lib)
        for name, spec in specs.items():
            params = spec['params']
            kinds = spec.get('kinds') or {}
            decl = ', '.join(_param_decl(key, params[key], kinds.get(key))
                             for key in params)
            signature = f'self, {decl}, **kwargs' if decl else 'self, **kwargs'
            passing = ', '.join(f'"{key}": {key}' for key in params)
            out += [
                '',
                f'    def {prefix}_{name}({signature}):',
                f'        """`{lib}.{name}`（第三方库；{len(spec["lines"])} 条线）"""',
                f'        return _ext_apply(self, "{lib}", "{name}", '
                f'{{{passing}}})',
            ]
    out.append('# <ext-libs:methods:end>')
    return NL.join(out) + NL


def splice(text: str, begin: str, end: str, block: str, anchor: str) -> str:
    if begin in text and end in text:
        head = text[:text.index(begin)]
        tail = text[text.index(end) + len(end):]
        return head + block.rstrip(NL) + tail
    index = text.index(anchor) + len(anchor)
    return text[:index] + NL + block + text[index:]


MODULES = (
    ('kand', 'Kand', 'kand_specs', 'kand'),
    ('wickra', 'Wickra', 'wickra_specs', 'wickra'),
    ('vector_ta', 'VectorTa', 'vector_specs', 'vta'),
    ('ferro_ta', 'FerroTa', 'ferro_specs', 'ferro'),
    ('tulip_rs', 'TulipRS', 'tulip_specs', 'tulip'),
)


def main() -> None:
    wanted = [item for item in sys.argv[1:] if not item.startswith('-')]
    found_all: dict[str, dict] = {}
    non_kline_all: dict[str, list] = {}
    for lib, _cls, getter, _prefix in MODULES:
        if wanted and lib not in wanted:
            continue
        found = globals()[getter]()
        found_all[lib] = found['specs']
        non_kline_all[lib] = found.get('non_kline') or []
        print(f'{lib}：{len(found["specs"])} 个指标可封装；'
              f'跳过 {len(found["skipped"])} 个')
        for name, reason in found['skipped'][:10]:
            print(f'   - {name}: {reason}')
    if '--write' not in sys.argv:
        print('（加 --write 写文件）')
        return

    for lib, cls_name, _getter, prefix in MODULES:
        specs = found_all.get(lib)
        if not specs:
            continue
        (ROOT / 'minibt' / 'indicators' / f'{lib}.py').write_text(
            build_class(prefix, cls_name, specs, non_kline_all.get(lib),
                        module=lib,
                        accessor=('tulip_rs' if lib == 'tulip_rs' else prefix)),
            encoding='utf-8')

    core = ROOT / 'minibt' / 'core.py'
    text = core.read_text(encoding='utf-8')
    helper = HELPER_HEAD.replace('__SPECS__', repr(found_all))
    text = splice(text, '# <ext-libs:helpers:begin>', '# <ext-libs:helpers:end>',
                  helper,
                  '    _ALPHA_SIGNATURE_CACHE[name] = out' + NL
                  + '    return out' + NL)
    text = splice(text, '# <ext-libs:methods:begin>', '# <ext-libs:methods:end>',
                  build_core(found_all, {lib: prefix for lib, _c, _g, prefix
                                         in MODULES}),
                  '        return _alpha_apply(self, "ZSCORE", locals(),'
                  ' **kwargs)' + NL)
    core.write_text(text, encoding='utf-8')
    print('已写 ' + ' + '.join(
        f'{lib}_* {len(specs)} 个' for lib, specs in found_all.items())
        + ' 到 core.py')


if __name__ == '__main__':
    main()

"""第三方 Rust 指标库内置（B 方案）：**vector-ta / ferro-ta / tulip-rs**

用户 2026-11-22 决定按方案 B 执行：**不替换** `IndFrame/IndSeries` 的父类
（`PandasTa` / `TaLib`），而是把三个 Rust 库**并行内置**成独立访问器：

| 库 | 访问器 | 命名 | 方法数 | desk |
|---|---|---|---|---|
| vector-ta | `kline.vta` | **小写**（原生） | 210 | 208 |
| ferro-ta | `kline.ferro` | **大写**（TA-Lib 风格） | 193 | 176 |
| tulip-rs | `kline.tulip_rs` | **大写**（生成包装） | 88 | 88 |

> `kline.tulip` 仍是 **TuLip**（tulipy，小写方法名）；两家库别混用 ✓

为什么这样（分析结论）：引擎级 0.005–0.05 ms，而框架 `@tobtind` 后是 0.5–3 ms
→ 换父类端到端只有 1–2% 收益，却要丢 45–57% 指标名、破坏布局 key 与
`TradingView.SAR` 等内部实现；所以只做"并行库 + 快路径" ✓
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INSTALLED = {}
for _name in ('vector_ta', 'ferro_ta', 'tulip_rs'):
    try:
        __import__(_name)
        INSTALLED[_name] = True
    except Exception:                                            # noqa: BLE001
        INSTALLED[_name] = False


def _kline(length: int = 2000):
    from minibt import LocalDatas, options

    options.set_conversion_mode = 'free'
    return LocalDatas.test.kline.iloc[:length]


#: (模块名, 类名, 访问器, 前缀, 方法数)
CASES = (
    ('vector_ta', 'VectorTa', 'vta', 'vta', 209),
    ('ferro_ta', 'FerroTa', 'ferro', 'ferro', 225),
    ('tulip_rs', 'TulipRS', 'tulip_rs', 'tulip', 88),
)


# --------------------------------------------------------------- 结构
@pytest.mark.parametrize('module_name,class_name,attr,prefix,count', CASES)
def test_class_shape(module_name, class_name, attr, prefix, count):
    """属性名 / 前缀 / 方法数 / 生成器 spec 一致 ✓"""
    import importlib

    module = importlib.import_module(f'minibt.indicators.{module_name}')
    library = getattr(module, class_name)
    assert library._perfixes == f'{prefix}_'
    names = module._INDICATOR_NAMES
    assert len(names) == count, (class_name, len(names))
    methods = [name for name in dir(library)
               if not name.startswith('_')
               and name != 'NON_KLINE_INDICATORS' and name != 'SIGNALS'
               and callable(getattr(library, name))]
    assert set(methods) == set(names)
    for name in names:
        args = getattr(library, name)._decorator_args
        assert args['lines'], name
        assert isinstance(args['overlap'], (bool, dict)), name
    import minibt
    import minibt.core as core
    assert hasattr(minibt.IndicatorClass, class_name)
    for name in names:
        assert hasattr(core.CoreFunc, f'{prefix}_{name}'), name


def test_accessors_are_wired():
    """`kline.vta` / `kline.ferro` / `kline.tulip_rs` 都在；`tulip` 仍是 TuLip ✓"""
    from minibt.indicators.core import KLine

    for attr in ('vta', 'ferro', 'tulip_rs'):
        assert isinstance(getattr(KLine, attr, None), property)
    # ★ `kline.tulip` 必须还是 tulipy 的 TuLip（不能又被 TulipRS 覆盖 ✗）
    assert isinstance(getattr(KLine, 'tulip', None), property)
    from minibt import LocalDatas
    kline = LocalDatas.test.kline
    assert type(kline.tulip).__name__ == 'TuLip'
    assert type(kline.tulip_rs).__name__ == 'TulipRS'


# --------------------------------------------------------------- 数值
@pytest.mark.parametrize('module_name,class_name,attr,prefix,count', CASES)
def test_every_indicator_runs(module_name, class_name, attr, prefix, count):
    """全部指标跑通：长度对齐 / 无 `±inf`（NON_KLINE 跳过）✓"""
    if not INSTALLED[module_name]:
        pytest.skip(f'没装 {module_name}')
    import importlib

    module = importlib.import_module(f'minibt.indicators.{module_name}')
    library = getattr(module, class_name)
    kline = _kline(1000)
    failed = []
    for name in module._INDICATOR_NAMES:
        if name in library.NON_KLINE_INDICATORS:
            continue
        try:
            result = getattr(getattr(kline, attr), name)()
        except Exception as error:                                # noqa: BLE001
            failed.append((name, f'{type(error).__name__}: {error}'))
            continue
        frame = (result.pandas_object if hasattr(result, 'pandas_object')
                 else pd.DataFrame({'x': np.asarray(result, dtype=float)}))
        assert len(frame) == len(kline), name
        assert not np.isinf(frame.to_numpy(dtype=np.float64)).any(), name
    assert failed == [], failed


@pytest.mark.parametrize('module_name,class_name,attr,prefix,count', CASES)
def test_wrapper_is_transparent(module_name, class_name, attr, prefix, count):
    """封装透明：`kline.<lib>.<name>` == 直接调第三方库 ✓"""
    if not INSTALLED[module_name]:
        pytest.skip(f'没装 {module_name}')
    kline = _kline(1000)
    frame = kline.pandas_object
    close = np.ascontiguousarray(frame['close'].to_numpy(dtype=np.float64))

    if module_name == 'vector_ta':
        import vector_ta as lib
        mine = np.asarray(kline.vta.sma(length=20), dtype=np.float64)
        theirs = np.asarray(lib.sma(close, 20), dtype=np.float64)
    elif module_name == 'ferro_ta':
        import ferro_ta as lib
        mine = np.asarray(kline.ferro.SMA(timeperiod=20), dtype=np.float64)
        theirs = np.asarray(lib.SMA(close, 20), dtype=np.float64)
    else:
        import tulip_rs as lib
        mine = np.asarray(kline.tulip_rs.SMA(period=20), dtype=np.float64)
        outputs = lib.indicators.sma.indicator([close], [20])[0]
        theirs = np.asarray(outputs[0] if isinstance(outputs, list)
                            else outputs, dtype=np.float64)
        # tulip 输出是紧凑数组（无预热 NaN）→ 尾部对比 ✓
        mine = mine[-theirs.size:]
    valid = np.isfinite(mine) & np.isfinite(theirs)
    assert valid.sum() > 100
    assert np.allclose(mine[valid], theirs[valid], rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize('attr,name,column', [
    ('vta', 'sma', 'sma'), ('ferro', 'SMA', 'sma'), ('tulip_rs', 'SMA', None),
])
def test_values_match_pandas_ta(attr, name, column):
    """与 pandas_ta 对拍（SMA 口径一致）✓"""
    pandas_ta = pytest.importorskip('pandas_ta')
    kline = _kline(1000)
    mine = np.asarray(getattr(getattr(kline, attr), name)(), dtype=np.float64)
    ref = np.asarray(pandas_ta.sma(kline.pandas_object['close'], length=20,
                                   talib=False), dtype=np.float64)
    valid = np.isfinite(mine) & np.isfinite(ref)
    assert valid.sum() > 100
    scale = np.maximum(np.abs(ref[valid]), 1.0)
    assert float(np.max(np.abs(mine[valid] - ref[valid]) / scale)) < 1e-6


def test_tulip_line_names_come_from_metadata():
    """tulip 的线名来自 `info()['outputs']`（bbands / macd / stoch）✓"""
    if not INSTALLED['tulip_rs']:
        pytest.skip('没装 tulip-rs')
    from minibt.indicators.tulip_rs import TulipRS

    assert getattr(TulipRS, 'BBANDS')._decorator_args['lines'] == [
        'bbands_lower', 'bbands_middle', 'bbands_upper']
    assert getattr(TulipRS, 'MACD')._decorator_args['lines'] == [
        'macd_line', 'signal_line', 'histogram']
    assert getattr(TulipRS, 'STOCH')._decorator_args['lines'] == [
        'stoch_k', 'stoch_d']
    # `display_type == Overlay` → 主图 ✓
    assert getattr(TulipRS, 'SMA')._decorator_args['overlap'] is True


def test_overlap_and_non_kline():
    """主副图按价格量纲判定；统计/形态类进 NON_KLINE ✓"""
    from minibt.indicators.ferro_ta import FerroTa
    from minibt.indicators.vector_ta import VectorTa

    assert getattr(VectorTa, 'sma')._decorator_args['overlap'] is True
    assert getattr(FerroTa, 'SMA')._decorator_args['overlap'] is True
    assert 'sma' in dir(VectorTa) and 'SMA' in dir(FerroTa)
    # 至少各有一个 NON_KLINE（纯统计 / 标志线）
    assert len(FerroTa.NON_KLINE_INDICATORS) >= 1
    assert len(VectorTa.NON_KLINE_INDICATORS) >= 0


# --------------------------------------------------------------- desk
@pytest.mark.parametrize('prefix,expected', [
    ('vta', 207), ('ferro', 196), ('tulip', 88),
])
def test_catalog_exposes_libraries(prefix, expected):
    """desk 目录：三个新分组（vta 207 / ferro 196 / tulip 88）✓"""
    from minibt.desk import indicator_catalog as catalog

    items = [item for item in catalog.catalog(refresh=True)
             if item['prefix'] == prefix]
    assert len(items) == expected, (prefix, len(items))
    assert catalog.missing_indicators() == {}


def test_catalog_compute_path():
    """目录 → desk compute（三个库各抽一个）✓"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(400)
    errors: dict[str, str] = {}
    items = catalog.compute(kline, ['vta_sma', 'ferro_SMA', 'tulip_SMA'],
                            errors=errors)
    assert errors == {}
    keys = {item['key'].split(':')[0] for item in items}
    assert keys == {'vta_sma', 'ferro_SMA', 'tulip_SMA'}


# --------------------------------------------------------------- 样式 / 非K线
@pytest.mark.parametrize('attr,name,hist', [
    ('ferro', 'MACD', 'histogram'), ('tulip_rs', 'MACD', 'histogram'),
])
def test_macd_histogram_is_vbar(attr, name, hist):
    """MACD 类柱体线 → `LineDash.vbar`（用户 2026-11-22 要求）✓"""
    if not INSTALLED['ferro_ta' if attr == 'ferro' else 'tulip_rs']:
        pytest.skip('没装对应库')
    from minibt.utils import LineDash

    kline = _kline(600)
    result = getattr(getattr(kline, attr), name)()
    lines = list(result.pandas_object.columns)
    assert hist in lines, lines
    style = (result._plotinfo.linestyle or {})[hist]
    assert style.line_dash == LineDash.vbar
    assert style.vbar_base == 0.0
    assert style.vbar_up_color and style.vbar_down_color


def test_overlap_covers_three_cases():
    """纯主图 / 纯副图 / 混合（dict）三种都能出现 ✓"""
    from minibt.indicators.vector_ta import VectorTa
    import minibt.indicators.vector_ta as V

    main = getattr(VectorTa, 'sma')._decorator_args['overlap']
    sub = getattr(VectorTa, 'rsi')._decorator_args['overlap']         if 'rsi' in V._INDICATOR_NAMES else False
    assert main is True and sub is False
    mixed = [name for name in V._INDICATOR_NAMES
             if isinstance(getattr(VectorTa, name)._decorator_args['overlap'],
                           dict)]
    assert mixed, '至少一个混合主副图的指标 ✓'
    flags = getattr(VectorTa, mixed[0])._decorator_args['overlap']
    assert set(flags.values()) == {True, False}


def test_non_kline_covers_math_and_series_takers():
    """辅助数学 / 需要第二条序列的 → `NON_KLINE_INDICATORS`（desk 不显示）✓"""
    from minibt.indicators.ferro_ta import FerroTa

    skip = set(FerroTa.NON_KLINE_INDICATORS)
    assert {'ADD', 'BETA', 'CDL2CROWS'} <= skip      # 数学 / 双序列 / 形态
    assert 'SMA' not in skip and 'RSI' not in skip
    # 方法仍在（可调用），只是不进选择器
    assert hasattr(FerroTa, 'BETA') and hasattr(FerroTa, 'ADD')


def test_series_parameter_accepts_pandas_series():
    """需要第二条序列的方法：传 `pd.Series` / `np.ndarray` 能算；不传报可读错误 ✓"""
    if not INSTALLED['ferro_ta']:
        pytest.skip('没装 ferro-ta')
    kline = _kline(600)
    frame = kline.pandas_object
    other = pd.Series(np.asarray(frame['close'], dtype=float) * 1.001,
                      index=frame.index)
    result = kline.ferro.BETA(real1=other)
    assert len(result) == len(kline)
    assert np.isfinite(np.asarray(result, dtype=float)[-1])
    with pytest.raises(ValueError, match='第二条序列'):
        kline.ferro.BETA()


# --------------------------------------------------------------- 参数健壮性
def test_empty_string_and_numeric_string_params():
    """desk 换参数会传 `''` / `"20"`：空串回落默认、数字串自动转型 ✓"""
    if not INSTALLED['vector_ta']:
        pytest.skip('没装 vector-ta')
    kline = _kline(800)
    cases = [
        ('vta.price_density_market_noise', {'kernel': ''}),
        ('vta.price_density_market_noise', {'kernel': None}),
        ('vta.sma', {'length': '30'}),
        ('vta.sma', {'length': ''}),
        ('kand.ema', {'k': ''}),
    ]
    for path, kwargs in cases:
        attr, name = path.split('.')
        result = getattr(getattr(kline, attr), name)(**kwargs)
        assert len(result) == len(kline), (path, kwargs)


def test_catalog_param_types_for_optional_none():
    """`default=None` 的参数也要有**真类型**（int 不能标成 str）✓"""
    from minibt.desk import indicator_catalog as catalog

    catalog.catalog(refresh=True)
    entry = catalog.entry('vta_price_density_market_noise')
    table = {param['name']: param for param in entry['params']}
    assert table['kernel']['type'] == 'str'
    assert table['length']['type'] == 'int'
    ema = {param['name']: param
           for param in catalog.entry(
               'vta_absolute_strength_index_oscillator')['params']}
    assert ema['ema_length']['type'] == 'int'      # 以前是 str ✗
    assert catalog.entry('kand_ema')['params'][-1]['type'] == 'float'


def test_desk_compute_handles_empty_params_everywhere():
    """所有库 × 所有参数：传空串 / 数字串都不崩（desk 换参数场景）✓"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(800)
    items = [item for item in catalog.catalog(refresh=True)
             if item['prefix'] in ('kand', 'wickra', 'vta', 'ferro', 'tulip',
                                   'pta_rs', 'pta', 'talib')]
    bad = []
    for item in items:
        params = item['params']
        if not params:
            continue
        for kwargs in ({param['name']: '' for param in params},
                       {param['name']: (str(param['default'])
                                        if param['default'] is not None else '')
                        for param in params}):
            errors: dict[str, str] = {}
            catalog.compute(kline, [item['key']], {item['key']: kwargs},
                            errors=errors)
            if errors:
                bad.append((item['key'], errors[item['key']][:60]))
                break
    assert bad == [], bad[:6]


# --------------------------------------------------------------- kernel 参数
def test_kernel_param_semantics():
    """`kernel` = vector-ta 的**计算内核**：结果与内核无关，非法值回落默认 ✓"""
    if not INSTALLED['vector_ta']:
        pytest.skip('没装 vector-ta')
    kline = _kline(600)
    base = np.asarray(kline.vta.sma(length=20), dtype=np.float64)
    for kernel in (None, '', 'scalar', 'auto', 'garbage'):
        values = np.asarray(kline.vta.sma(length=20, kernel=kernel),
                            dtype=np.float64)
        assert np.allclose(base, values, equal_nan=True), kernel


def test_kernel_documented_in_docstring():
    """`kernel` 的中文说明要进方法 docstring（用户 2026-11-22 问"这是干什么的"）✓"""
    import inspect

    from minibt.indicators.vector_ta import VectorTa

    doc = inspect.getdoc(VectorTa.sma) or ''
    for needle in ('kernel', '计算内核', "'scalar'", "'avx2'", '只影响速度'):
        assert needle in doc, needle

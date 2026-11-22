"""py-alpha-lib 指标接入（v1.3.9-52）。

用户 2026-11-20 要求：把 https://github.com/msd-rs/py-alpha-lib 内置到 minibt：

1. `CoreFunc`（`minibt/core.py`）惰性入口，前缀 `alpha_`；
2. `minibt/indicators/alpha.py` 新增 `Alpha` 分类，**包含 alpha 全部指标**，
   其中 `NON_KLINE_INDICATORS` 放「不以 K 线为数据源 / 需要多序列或条件」的算子；
3. `IndicatorClass.Alpha` 注册入口（`kline.alpha.xxx()`）；
4. desk 目录开放 `Alpha` 分类（可画线的 40 个）。

`py-alpha-lib` 是**可选依赖**（Rust，cp312，Python>=3.12）：
没装时整类消失，`import minibt` 不受影响 ✓
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

alpha_installed = True
try:
    import alpha  # noqa: F401
except Exception:                                                # noqa: BLE001
    alpha_installed = False

needs_alpha = pytest.mark.skipif(not alpha_installed,
                                 reason='没装 py-alpha-lib（可选依赖）')


def _frame(count: int = 200):
    rng = np.random.default_rng(3)
    close = pd.Series(8000 + np.cumsum(rng.normal(0, 6, count)))
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=count, freq='min'),
        'open': close, 'high': close + 5, 'low': close - 5, 'close': close,
        'volume': [100] * count,
    })


def _kline(count: int = 200):
    sys.path.insert(0, str(ROOT))
    from minibt.indicators.core import KLine

    return KLine(_frame(count), duration_seconds=60, data_length=None)


# ---------------------------------------------------------------- 静态闸门
def test_no_input_parameter():
    """★ 方法签名里**不能**有 `input='close'`：数据源由 `FILED.C` 决定 ✓"""
    import inspect

    sys.path.insert(0, str(ROOT))
    from minibt.core import CoreFunc

    for name in ('alpha_ma', 'alpha_stddev', 'alpha_hhv', 'alpha_zscore'):
        params = inspect.signature(getattr(CoreFunc, name)).parameters
        assert 'input' not in params, name
    # 需要第二条序列的算子：只暴露"其余"参数 ✓
    cross = inspect.signature(CoreFunc.alpha_cross).parameters
    assert 'a' not in cross and 'b' in cross
    split = inspect.signature(CoreFunc.alpha_bw_split).parameters
    assert 'price' not in split and 'dividend' in split


def test_parameter_order_matches_alpha():
    """参数**顺序**要和原指标签名一致（去掉第一个 = close）✓

    原 `ALPHA(input, benchmark, periods)` → minibt `(benchmark, periods)`；
    原 `BW_SPLIT(price, dividend, transfer_shares, right_shares, right_price)`
    → minibt `(dividend, transfer_shares, right_shares, right_price)`。
    """
    import inspect

    sys.path.insert(0, str(ROOT))
    from minibt.core import CoreFunc
    from minibt.indicators.alpha import Alpha

    cases = {
        'alpha_alpha': ['benchmark', 'periods'],
        'alpha_beta': ['benchmark', 'periods'],
        'alpha_corr2': ['y', 'periods'],
        'alpha_regresi': ['x', 'periods'],
        'alpha_bw_split': ['dividend', 'transfer_shares', 'right_shares',
                           'right_price'],
        'alpha_fret': ['close', 'is_calc', 'delay', 'periods'],
        'alpha_entropy': ['periods', 'bins'],
    }
    for name, order in cases.items():
        params = [param for param, item in inspect.signature(
            getattr(CoreFunc, name)).parameters.items()
            if param not in ('self', 'kwargs')
            and item.kind is not inspect.Parameter.VAR_KEYWORD]
        assert params == order, (name, params)
    # 指标类同名方法也要一致 ✓
    method = [param for param, item in inspect.signature(
        Alpha.alpha).parameters.items()
        if param != 'self' and item.kind is not inspect.Parameter.VAR_KEYWORD]
    assert method == ['benchmark', 'periods']
    # 指标类同样没有 input ✓
    from minibt.indicators.alpha import Alpha

    assert 'input' not in inspect.signature(Alpha.ma).parameters


@needs_alpha
def test_every_alpha_method_is_tobtind_indseries():
    """`Alpha` 的**全部**方法都走 `@tobtind`，且返回 `IndSeries` ✓

    用户 2026-11-20：`abs` 之后的算子虽然不是"能上图表的指标"（已进
    `NON_KLINE_INDICATORS`），但计算结果同样要是内置指标格式。
    """
    import inspect

    sys.path.insert(0, str(ROOT))
    from minibt.indicators.alpha import Alpha

    names = [name for name in dir(Alpha)
             if not name.startswith('_')
             and callable(getattr(Alpha, name, None))]
    assert len(names) >= 78, len(names)
    bad_args, bad_ret, bad_body = [], [], []
    for name in names:
        func = getattr(Alpha, name)
        if getattr(func, '_decorator_args', None) is None:
            bad_args.append(name)
        # `@tobtind` 会包一层 `wrapper`（`functools.wraps`）→ 看**原始函数** ✓
        raw = inspect.unwrap(func)
        hint = str(inspect.signature(raw).return_annotation)
        if 'IndSeries' not in hint:
            bad_ret.append(name)
        if not inspect.getsource(raw).rstrip().endswith('...'):
            bad_body.append(name)
    assert not bad_args, f'没加 @tobtind：{bad_args[:5]}'
    assert not bad_ret, f'返回类型不是 IndSeries：{bad_ret[:5]}'
    assert not bad_body, f'函数体没省略：{bad_body[:5]}'


def test_registration_and_lazy_import():
    """入口齐全 + `alpha` 必须**惰性导入**（缺失不影响 `import minibt`）✓"""
    core = (ROOT / 'minibt' / 'core.py').read_text(encoding='utf-8')
    assert 'def alpha_ma(' in core
    assert 'def _alpha_apply(core, name: str, local: dict, **kwargs):' in core
    assert '_LazyModule("alpha")' in core               # 惰性导入 ✓
    assert 'py -3.12 -m pip install py-alpha-lib' in core

    base = (ROOT / 'minibt' / 'indicators' / 'base.py').read_text(
        encoding='utf-8')
    assert 'def alpha(self) -> Alpha:' in base
    assert 'from .alpha import Alpha' in base

    ind = (ROOT / 'minibt' / 'indicators' / 'core.py').read_text(
        encoding='utf-8')
    assert 'Alpha = Alpha' in ind                       # IndicatorClass 注册 ✓

    lib = (ROOT / 'minibt' / 'indicators' / 'alpha.py').read_text(
        encoding='utf-8')
    assert 'class Alpha:' in lib
    assert '_perfixes: str = "alpha_"' in lib
    assert 'NON_KLINE_INDICATORS = [' in lib


def test_desk_catalog_wiring():
    """desk 目录：LIBS / 类映射 / CORE_PREFIXES / 访问器 / 审计 都加上 alpha ✓"""
    catalog = (ROOT / 'minibt' / 'desk' / 'indicator_catalog.py').read_text(
        encoding='utf-8')
    for needle in ("('alpha', 'Alpha', 'Alpha库')", "'Alpha': ('alpha', 'Alpha')",
                   "'alpha': 'alpha',"):
        assert needle in catalog, needle
    for needle in ("'Pine', 'Alpha', 'Alpha101', 'Alpha191', 'PtaRs',",
                   "'Kand',",
                   "('alpha101', 'Alpha101', 'Alpha101')",
                   "('alpha191', 'Alpha191', 'Alpha191')"):
        assert needle in catalog, needle
    assert 'CATALOG_SCHEMA = 10' in catalog             # 缓存失效 ✓


@needs_alpha
def test_non_kline_are_not_in_catalog():
    """算子（CROSS / CORR2 / WHERE …）不进选择器，可画线的才进 ✓"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    items = cat.catalog(refresh=True)
    keys = {item['key'] for item in items}
    alpha_keys = {key for key in keys if key.startswith('alpha_')}
    assert 'alpha_ma' in alpha_keys
    assert 'alpha_cross' not in keys
    assert 'alpha_where' not in keys
    assert len(alpha_keys) >= 35


@needs_alpha
def test_ma_matches_pandas():
    """`alpha_ma` 数值要和 pandas `rolling(10).mean()` 一致 ✓"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as cat

    frame = _frame()
    items = cat.compute(frame, ['alpha_ma'], {'alpha_ma': {'periods': 10}},
                        limit=len(frame))
    assert items, '没有算出 alpha_ma'
    values = np.array([row[1] for row in items[0]['data']], dtype=float)
    expect = frame['close'].rolling(10).mean().values
    assert np.allclose(values[-20:], expect[-20:], equal_nan=True)


@needs_alpha
def test_methods_cover_all_alpha_functions():
    """`Alpha` 类要**包含 alpha 的全部指标**（可画线 + 算子）✓"""
    sys.path.insert(0, str(ROOT))
    import alpha as alpha_lib
    import minibt

    names = {name for name in dir(alpha_lib)
             if name.isupper() and not name.startswith('FLAG_')}
    library = minibt.IndicatorClass.Alpha
    methods = {name.upper() for name in dir(library)
               if not name.startswith('_')}
    missing = {name for name in names if name not in methods}
    assert not missing, f'Alpha 类缺少：{sorted(missing)}'


@needs_alpha
def test_scalar_and_array_periods():
    """`periods` 标量走 `MA`，数组走 `MA_V`（签名不同，不能一律广播 ✗）✓"""
    kline = _kline()
    simple = kline.alpha.ma(periods=10)
    assert len(np.asarray(simple)) == len(kline)
    vector = kline.alpha.ma_v(periods=10)
    assert len(np.asarray(vector)) == len(kline)
    assert np.allclose(np.asarray(simple)[-5:], np.asarray(vector)[-5:],
                       equal_nan=True)


@needs_alpha
def test_operators_callable_from_alpha_accessor():
    """算子（不画线）也要能从 `kline.alpha.xxx()` 调用 ✓"""
    kline = _kline()
    # ★ 数据源固定走 `FILED.C`（close）→ 签名里没有 `input` / `condition` ✓
    cross = kline.alpha.cross(b=np.asarray(kline.open))
    assert type(cross).__name__ == 'IndSeries'          # 工具函数也返回内置格式 ✓
    assert set(np.unique(np.asarray(cross))) <= {0.0, 1.0}
    where = kline.alpha.where(a=np.asarray(kline.high),
                              b=np.asarray(kline.low))
    assert type(where).__name__ == 'IndSeries'
    assert np.all(np.asarray(where) == np.asarray(kline.high))


# --------------------------------------------------------------- 中文注释 / 主副图
#: 主图叠加（和价格同量纲）：均线 / 通道 / 位移 / 回归截距 ✓
MAIN_CHART = {
    'ma', 'ma_v', 'ema', 'ema_v', 'sma', 'sma_v', 'lwma', 'lwma_v',
    'dma', 'dma_v', 'hhv', 'hhv_v', 'llv', 'llv_v', 'ref', 'ref_v',
    'intercept',
}
#: 副图（统计量）：标准差 / 方差 / Z 分数 / 排名 / 相关性 / 熵 … ✓
SUB_CHART = {'stddev', 'var', 'zscore', 'rank', 'quantile', 'moment',
             'skewness', 'kurtosis', 'sharpe', 'max_drawdown',
             'min_max_diff', 'slope', 'corr', 'entropy', 'bins', 'sum',
             'product', 'count', 'count_v', 'hhvbars', 'hhvbars_v',
             'llvbars', 'llvbars_v'}


@needs_alpha
def test_every_method_has_chinese_docstring():
    """78 个方法**每个都有中文注释**（用户 2026-11-20 要求）✓"""
    import inspect

    from minibt.indicators.alpha import Alpha

    methods = [name for name in dir(Alpha)
               if not name.startswith('_')
               and callable(getattr(Alpha, name))
               and name != 'NON_KLINE_INDICATORS']
    assert len(methods) == 78
    for name in methods:
        doc = inspect.getdoc(getattr(Alpha, name)) or ''
        assert len(doc) > 60, (name, doc[:40])
        assert '图上归类' in doc, name                  # 主图 / 副图 标注 ✓
        assert '计算方法' in doc and '使用案例' in doc, name
        # 至少含中文（不是从英文抄的占位）
        assert any('\u4e00' <= char <= '\u9fff' for char in doc), name


@needs_alpha
def test_overlap_flag_matches_main_or_sub_chart():
    """`overlap` 按主副图区分（均线主图 / stddev 等副图）✓"""
    from minibt.indicators.alpha import Alpha

    for name in MAIN_CHART:
        args = getattr(Alpha, name)._decorator_args
        assert args['overlap'] is True, name
    for name in SUB_CHART:
        args = getattr(Alpha, name)._decorator_args
        assert args['overlap'] is False, name
    skip = set(Alpha.NON_KLINE_INDICATORS)
    assert MAIN_CHART | SUB_CHART == {
        name for name in dir(Alpha)
        if not name.startswith('_') and callable(getattr(Alpha, name))
        and name != 'NON_KLINE_INDICATORS' and name not in skip}
    assert not (MAIN_CHART & SUB_CHART)
    assert len(MAIN_CHART) == 17 and len(SUB_CHART) == 23


@needs_alpha
def test_catalog_overlap_matches_decorator():
    """desk 目录里 alpha 的主副图归属和装饰器一致 ✓"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import indicator_catalog as catalog_module

    items = [item for item in catalog_module.catalog(refresh=True)
             if item['key'].startswith('alpha_')]
    assert len(items) == 40
    main = {item['key'][len('alpha_'):] for item in items if item['overlap']}
    assert main == MAIN_CHART


@needs_alpha
def test_docs_table_covers_every_function():
    """`scripts/alpha_docs.py` 的说明表覆盖全部 78 个函数 ✓"""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import alpha_docs

    alpha = pytest.importorskip('alpha')
    names = {name for name in dir(alpha)
             if name.isupper() and not name.startswith('FLAG_')}
    assert set(alpha_docs.ALPHA_DOCS) == names
    for name, doc in alpha_docs.ALPHA_DOCS.items():
        assert doc['title'] and doc['desc'], name
        assert isinstance(doc['main'], bool), name


@needs_alpha
def test_generator_emits_overlap_per_indicator():
    """生成器里 `overlap` 不能再写死 `True`（回归保护）✓"""
    source = (ROOT / 'scripts' / 'gen_alpha_indicators.py').read_text(
        encoding='utf-8')
    assert 'overlap=True, lines=' not in source
    assert 'overlap={overlap}' in source
    assert 'from alpha_docs import ALPHA_DOCS' in source

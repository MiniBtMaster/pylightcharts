"""Alpha101 / Alpha191 因子内置（v1.3.9-58 改版）。

用户 2026-11-20 改版要求：

1. 按 alpha 的形式内置，前缀分别是 `alpha101_` / `alpha191_`；
2. **数据源就是 IndFrame 自己**，入口挂在 IndFrame 上 →
   `self.kline.alpha101.alpha001()` / `self.kline.alpha191.alpha191()`；
3. `alpha101.py`（`class Alpha101`）+ `alpha191.py`（`class Alpha191`）
   包含**全部** 292 个因子，全部副图；
4. `core.py` 对应 `alpha101_*` / `alpha191_*`，`self` 就是计算用的数据，
   数据不对**不拦**，由 alpha 抛原生错误；
5. 横截面 / 缺外部数据的因子进 `NON_KLINE_INDICATORS` → desk 只显示纯时序部分
   （18 + 120 = 138）。
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 上游示例放在仓库里（逐值比对用 ✓）
EXAMPLES = ROOT / 'py-alpha-lib-main' / 'examples'
for _sub in ('wq101/al', 'gtja191/al'):
    _path = str(EXAMPLES / _sub)
    if pathlib.Path(_path).is_dir() and _path not in sys.path:
        sys.path.insert(0, _path)

alpha_installed = True
try:
    import alpha  # noqa: F401
    import alpha101 as upstream101  # noqa: F401
    import alpha191 as upstream191  # noqa: F401
except Exception:                                                # noqa: BLE001
    alpha_installed = False

needs_alpha = pytest.mark.skipif(not alpha_installed,
                                 reason='没装 py-alpha-lib')


def _kline(length: int = 240):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from minibt import LocalDatas, options

    options.set_conversion_mode = 'free'
    return LocalDatas.test.kline.iloc[:length]


def _factors():
    from minibt.indicators import _alpha_factors as factors

    return factors


def _panel(kline, securities: int = 3, **extra) -> pd.DataFrame:
    """3 个标的的假面板（横截面因子用 ✓）"""
    rows = []
    for security in range(securities):
        part = kline.copy()
        scale = 1 + security * 0.01
        for column in ('open', 'high', 'low', 'close'):
            part[column] = part[column] * scale
        part['securityid'] = security
        part['tradetime'] = np.arange(len(part))
        rows.append(part[['securityid', 'tradetime', 'open', 'high', 'low',
                          'close', 'volume']])
    panel = pd.concat(rows, ignore_index=True).rename(
        columns={'volume': 'vol'})
    for key, value in extra.items():
        panel[key] = value
    return panel


# --------------------------------------------------------------- 注册表
def test_registry_counts_and_formulas():
    """292 个因子全在注册表里，公式注释一个都不能缺 ✓"""
    factors = _factors()
    counts = {family: len(items) for family, items in factors.FACTORS.items()}
    assert counts == {'wq101': 101, 'gtja191': 191}
    assert len(factors.TS_NUMBERS['wq101']) == 18
    assert len(factors.TS_NUMBERS['gtja191']) == 120
    for family, items in factors.FACTORS.items():
        for no, meta in items.items():
            assert meta['kind'] in ('ts', 'cross', 'external'), (family, no)
            assert len(meta['formula']) > 3, (family, no)
            assert meta['method'] == f'alpha{no:03d}'


def test_vendored_modules_untouched_by_generator():
    """vendor 的因子文件只加头注释，函数体保持上游原样 ✓"""
    folder = ROOT / 'minibt' / 'indicators' / '_alpha_factors'
    for family, prefix in (('wq101', 'alpha101'), ('gtja191', 'alpha191')):
        text = (folder / f'{family}.py').read_text(encoding='utf-8')
        assert 'BSD-2-Clause' in text
        assert f'examples/{family}/al/{prefix}.py' in text
        assert text.count('\ndef alpha_') == len(_factors().FACTORS[family])


# --------------------------------------------------------------- 类结构
def test_classes_expose_every_factor():
    """`Alpha101` / `Alpha191` 包含**全部**因子，前缀 + 副图 + 纯时序清单 ✓"""
    from minibt.indicators.alpha101 import Alpha101
    from minibt.indicators.alpha191 import Alpha191

    for library, count, prefix, pure in ((Alpha101, 101, 'alpha101_', 18),
                                         (Alpha191, 191, 'alpha191_', 120)):
        assert library._perfixes == prefix
        skip = set(library.NON_KLINE_INDICATORS)
        methods = [name for name in dir(library)
                   if not name.startswith('_') and name != 'NON_KLINE_INDICATORS'
                   and callable(getattr(library, name))]
        assert len(methods) == count, (library.__name__, len(methods))
        assert len(skip) == count - pure
        assert len(library.PURE_INDICATORS) == pure
        for name in methods:
            args = getattr(library, name)._decorator_args
            assert args['overlap'] is False, name          # 全部副图 ✓
            assert args['lines'] == [name], name


def test_non_kline_matches_registry_kind():
    """`NON_KLINE_INDICATORS` 必须正好是「非纯时序」那些因子 ✓"""
    from minibt.indicators.alpha101 import Alpha101
    from minibt.indicators.alpha191 import Alpha191

    factors = _factors()
    for family, library in (('wq101', Alpha101), ('gtja191', Alpha191)):
        expected = {meta['method'] for meta in factors.FACTORS[family].values()
                    if meta['kind'] != 'ts'}
        assert set(library.NON_KLINE_INDICATORS) == expected
        assert set(library.PURE_INDICATORS) == {
            no for no, meta in factors.FACTORS[family].items()
            if meta['kind'] == 'ts'}                   # 存的是**编号** ✓


def test_core_has_every_factor():
    """`core.py` 的 `alpha101_*` / `alpha191_*` 一个不少 ✓"""
    import minibt.core as core

    factors = _factors()
    for family, prefix in (('wq101', 'alpha101_'), ('gtja191', 'alpha191_')):
        for meta in factors.FACTORS[family].values():
            assert hasattr(core.CoreFunc, f'{prefix}{meta["method"]}')
    assert not [name for name in dir(core.CoreFunc) if name.startswith('af_')]


def test_legacy_alpha_factor_module_removed():
    """旧的 `alpha_factor.py`（AlphaFactor / `af` 访问器）已删掉 ✓"""
    assert not (ROOT / 'minibt' / 'indicators' / 'alpha_factor.py').exists()
    base = (ROOT / 'minibt' / 'indicators' / 'base.py').read_text(
        encoding='utf-8')
    assert 'def af(self)' not in base
    assert 'AlphaFactor' not in base


# --------------------------------------------------------------- 单标的
@needs_alpha
def test_every_time_series_factor_runs():
    """138 个纯时序因子逐个跑通（长度对齐 ✓）"""
    kline = _kline(240)
    factors = _factors()
    failed, empty = [], []
    for family, numbers in factors.TS_NUMBERS.items():
        for no in numbers:
            try:
                series = factors.compute_series(kline, family, no)
            except Exception as error:                            # noqa: BLE001
                failed.append((family, no, f'{type(error).__name__}: {error}'))
                continue
            assert len(series) == len(kline), (family, no)
            if np.isfinite(np.asarray(series, dtype=np.float64)).sum() == 0:
                # 上游用**递归 SMA** 且种子是 NaN 的因子（#23 / #160 / #174 …）
                # → 一辈子都是 NaN，上游同样行为，不算我们的 bug ✓
                empty.append((family, no))
    assert failed == []
    assert len(empty) <= 6, empty


@needs_alpha
def test_accessor_path():
    """`self.kline.alpha101.alpha001()` / `alpha191.alpha191()` 可用 ✓"""
    kline = _kline(240)

    simple = kline.alpha191.alpha002()
    assert type(simple).__name__ == 'IndSeries'
    assert len(simple) == len(kline)

    last = kline.alpha191.alpha191()
    assert type(last).__name__ == 'IndSeries'
    assert np.isfinite(np.asarray(last, dtype=np.float64)[-1])

    # 横截面因子在**单标的**上也能跑（不拦错）—— `RANK` 分组只有 1 个，
    # 有值的地方会退化成常数 0.5，这就是 alpha 的原生行为 ✓
    cross = kline.alpha101.alpha001()
    values = np.asarray(cross, dtype=np.float64)
    finite = values[np.isfinite(values)]
    assert finite.size > 0 and np.allclose(finite, 0.5)

    assert not hasattr(kline, 'af')                 # 旧入口已删 ✓


@needs_alpha
def test_factor_values_match_upstream():
    """和上游 `alpha101.py` / `alpha191.py` **逐值一致**（不偷改公式 ✓）"""
    from alpha.context import Context, ExecContext

    kline = _kline(240)
    factors = _factors()
    frame = factors.factor_frame(kline)
    samples = {'wq101': [6, 7, 12, 101], 'gtja191': [2, 3, 143, 191]}
    for family, numbers in samples.items():
        module = factors.__dict__[family]
        context = ExecContext(frame.copy())
        for no in numbers:
            meta = factors.FACTORS[family][no]
            with Context(groups=1):
                expected = np.asarray(getattr(module, meta['func'])(context),
                                      dtype=np.float64)
            got = np.asarray(factors.compute_series(kline, family, no),
                             dtype=np.float64)
            assert np.allclose(got, expected, equal_nan=True), (family, no)


@needs_alpha
def test_no_future_leak():
    """截断到前 N 根 → 重叠区间的因子值不能变（没有未来函数 ✓）"""
    kline = _kline(240)
    factors = _factors()
    short = kline.iloc[:150]
    for family, no in (('gtja191', 2), ('gtja191', 191), ('wq101', 101)):
        full = np.asarray(factors.compute_series(kline, family, no),
                          dtype=np.float64)
        part = np.asarray(factors.compute_series(short, family, no),
                          dtype=np.float64)
        assert np.allclose(full[:150], part, equal_nan=True, atol=1e-9), (
            family, no)


@needs_alpha
def test_data_comes_from_the_frame_itself():
    """数据源 = 传进来的 IndFrame（换数据 → 因子值跟着变 ✓）"""
    from minibt import LocalDatas

    head = LocalDatas.test.kline.iloc[:200]
    tail = LocalDatas.test.kline.iloc[200:400]
    first = np.asarray(head.alpha191.alpha002(), dtype=np.float64)
    second = np.asarray(tail.alpha191.alpha002(), dtype=np.float64)
    assert first.shape == second.shape
    assert not np.allclose(first, second, equal_nan=True)   # 换数据就变 ✓

    # 横截面因子：面板列齐全时按 securityid 真的分组 ✓
    panel = _panel(_kline(120), 3)
    values = _factors().panel_values(panel, 'wq101', 101)
    assert len(values) == len(panel)
    assert values.round(6).nunique() > 1


@needs_alpha
def test_context_restored_after_compute():
    """跑完因子要把 `alpha` 的线程上下文还回去（别污染别的调用 ✓）"""
    kline = _kline(120)
    factors = _factors()
    before = alpha.get_ctx()
    factors.compute_series(kline, 'gtja191', 2)
    kline.alpha101.alpha006()
    assert alpha.get_ctx() == before


# --------------------------------------------------------------- desk
def test_catalog_only_exposes_pure_factors():
    """desk：Alpha101 18 条 + Alpha191 120 条，横截面因子不出现 ✓"""
    from minibt.desk import indicator_catalog as catalog

    items = catalog.catalog(refresh=True)
    keys = {item['key']: item for item in items}
    from minibt.indicators.alpha101 import Alpha101
    from minibt.indicators.alpha191 import Alpha191

    for library, prefix, count in ((Alpha101, 'alpha101_', 18),
                                   (Alpha191, 'alpha191_', 120)):
        mine = [key for key in keys if key.startswith(prefix)]
        assert len(mine) == count, (prefix, len(mine))
        assert all(not keys[key]['overlap'] for key in mine)   # 全副图 ✓
        allowed = {f'{prefix}alpha{no:03d}'
                   for no in library.PURE_INDICATORS}
        assert set(mine) == allowed
        for name in library.NON_KLINE_INDICATORS:              # 算子不进选择器 ✓
            assert f'{prefix}{name}' not in keys
    assert {keys[key]['group'] for key in keys
            if key.startswith(('alpha101_', 'alpha191_'))} == {'Alpha101',
                                                             'Alpha191'}
    assert catalog.missing_indicators() == {}


def _factors_classes():
    from minibt.indicators.alpha101 import Alpha101
    from minibt.indicators.alpha191 import Alpha191

    return Alpha101, Alpha191


@needs_alpha
def test_catalog_compute_path():
    """目录 → desk compute 能算出因子（走 `kline.alpha1xx.*` 带样式 ✓）"""
    from minibt.desk import indicator_catalog as catalog

    kline = _kline(200)
    errors: dict[str, str] = {}
    items = catalog.compute(kline, ['alpha191_alpha002', 'alpha101_alpha101'],
                           errors=errors)
    assert errors == {}
    assert len(items) == 2
    for item in items:
        assert len(item['data']) == len(kline)


def test_factor_helpers():
    """`minibt.factor.available()` / `numbers()` / `formula()` ✓"""
    import minibt

    info = minibt.factor.available('gtja191')
    assert info['gtja191']['count'] == 191
    assert info['gtja191']['factors'][191]['kind'] == 'ts'
    assert set(minibt.factor.numbers('gtja191')) == set(
        _factors().TS_NUMBERS['gtja191'])
    assert 'CLOSE' in minibt.factor.formula('gtja191', 191).upper()
    with pytest.raises(ValueError, match='kind'):
        minibt.factor.numbers('gtja191', 'unknown')


@needs_alpha
def test_panel_api_for_cross_sectional_factors():
    """`minibt.factor.panel`：横截面因子在多标的面板上真的分组 ✓"""
    import minibt

    kline = _kline(120)
    panel = _panel(kline, 3, indclass=101500)
    values = minibt.factor.panel(panel, 'wq101', 101)
    assert len(values) == len(panel)
    assert values.round(6).nunique() > 1
    single = minibt.factor.panel(panel, 'gtja191', 191)
    assert len(single) == len(panel)


@needs_alpha
def test_panel_without_ids_treated_as_single_security():
    """只有 close 的 DataFrame → 当**单标的**算（不拦，alpha 原生行为 ✓）"""
    import minibt

    kline = _kline(60)
    frame = pd.DataFrame({'close': np.asarray(kline.close, dtype=np.float64)})
    values = minibt.factor.panel(frame, 'gtja191', 2)
    assert len(values) == len(frame)


def test_generated_methods_have_chinese_docs():
    """292 个方法都要中文 docstring（数据来源 / 说明）✓"""
    import inspect

    for library in _factors_classes():
        for name in dir(library):
            if name.startswith('_') or name in (
                    'NON_KLINE_INDICATORS', 'PURE_INDICATORS'):
                continue
            func = getattr(library, name)
            if not callable(func):
                continue
            doc = inspect.getdoc(func) or ''
            assert '数据来源' in doc, name
            assert any('\u4e00' <= char <= '\u9fff' for char in doc), name


# --------------------------------------------------------------- 图上有线
@needs_alpha
def test_recursive_sma_skips_non_finite_samples():
    """通达信 `SMA` 遇到 NaN / ±inf 时**跳过该样本**（别让整条线中毒 ✓）

    用户 2026-11-21 实测：`Alpha191.alpha028` 在 desk 上没有线 —— 公式里
    `MAX(HIGH,9) - TSMAX(LOW,9)` 在平价 K 线上会除零 → `±inf` 进递归 SMA →
    之后永远是 inf/NaN。修法：非有限样本保持上一个值（输入全有限时和上游
    **逐值一致**）。
    """
    import alpha
    import minibt.indicators._alpha_factors.context as context_module

    factors = _factors()
    frame = factors.factor_frame(_kline(60))
    ctx = context_module._context(frame)

    finite = np.linspace(1.0, 60.0, 60)
    ours = np.asarray(ctx.SMA(finite, 3, 1), dtype=np.float64)
    theirs = np.asarray(alpha.SMA(finite, 3, 1), dtype=np.float64)
    assert np.allclose(ours, theirs)                    # 全有限 → 完全一致 ✓

    dirty = finite.copy()
    dirty[5] = np.nan
    dirty[6] = np.inf
    dirty[7] = -np.inf
    cleaned = np.asarray(ctx.SMA(dirty, 3, 1), dtype=np.float64)
    assert np.isfinite(cleaned[7:]).all()               # 不再永久中毒 ✓
    assert cleaned[5] == cleaned[4]                     # 缺样本保持上一个值 ✓
    assert np.isclose(cleaned[8], (1 * dirty[8] + 2 * cleaned[7]) / 3)


@needs_alpha
def test_no_inf_and_most_finite_on_builtin_data():
    """三套内置 K 线：138 个纯时序因子都不能出 `±inf`，且有大半有值 ✓"""
    from minibt import LocalDatas

    factors = _factors()
    for name in ('test', 'l2609_60', 'pp2609_60'):
        kline = getattr(LocalDatas, name).kline
        for family, numbers in factors.TS_NUMBERS.items():
            for no in numbers:
                values = np.asarray(factors.compute_series(kline, family, no),
                                    dtype=np.float64)
                assert not np.isinf(values).any(), (name, family, no)
                assert np.isfinite(values).sum() > len(values) * 0.5, (
                    name, family, no)


@needs_alpha
def test_alpha028_draws_a_line():
    """用户报的 `Alpha191.alpha028`：有值、有变化、desk 能画 ✓"""
    from minibt import LocalDatas
    from minibt.desk import indicator_catalog as catalog

    kline = LocalDatas.test.kline
    series = kline.alpha191.alpha028()
    values = np.asarray(series, dtype=np.float64)
    assert np.isfinite(values).sum() > len(values) * 0.95
    assert np.unique(np.round(values[np.isfinite(values)], 6)).size > 10

    errors: dict[str, str] = {}
    items = catalog.compute(kline.iloc[:600], ['alpha191_alpha028'],
                           errors=errors)
    assert errors == {}
    points = items[0]['data']
    assert len(points) == 600
    numbers = [point[1] for point in points[-50:] if point[1] is not None]
    assert len(numbers) >= 45            # 尾部几乎每个点都有数值 ✓

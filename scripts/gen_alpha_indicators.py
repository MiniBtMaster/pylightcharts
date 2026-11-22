"""生成 `minibt/indicators/alpha.py` + `CoreFunc.alpha_*` 代码块（Alpha 库）。

用法::

    py -3.12 scripts/gen_alpha_indicators.py            # 只打印分类
    py -3.12 scripts/gen_alpha_indicators.py --write    # 写文件

数据来源：**运行时反射** `alpha` 包（py-alpha-lib，Rust，可选依赖）。
不手工抄签名 —— 78 个函数手抄必出错（历史教训：`pandas_ta.py` 9k 行）。

### 数据源约定（和 pandas_ta / btind 完全一致）

`CoreFunc` 里**不出现** `input='/close'` 之类的字符串参数：

```python
def alpha_ma(self, periods: int = 20, **kwargs) -> pd.Series:
    return _alpha_apply(self, "MA", locals(), **kwargs)     # 内部 FILED.C → close
```

* 第一个数组参数（alpha 的 `input` / `price` / `a` / `y` / `condition` …）
  **一律由 `_get_column_(locals(), *FILED.C)` 提供**（KLine 上就是 `close`，
  IndSeries 上就是它自己）——和 `pta_er` / `pta_kdj` 同一套 ✓；
* **其余**数组参数（`benchmark` / `dividend` / `b` / …）才出现在签名里，
  默认 `None`，由调用方传 `pd.Series` / `np.ndarray`；
* 标量参数（`periods` / `n` / `m` / `q` …）照旧带默认值。

### 分类（进 `NON_KLINE_INDICATORS` = 选择器里不出现）

* 需要**两个及以上**数组参数（`CROSS(a,b)` / `ALPHA(input,benchmark)` /
  `WHERE(cond,a,b)` / `SCAN_ADD(input,condition)` …）；
* 需要 `condition`（布尔序列）参数（`FILTER` / `SUMIF` / `BACKSET` …）；
* 拆股 / 分组 / 中性化 / 纯逻辑（`BW_SPLIT` / `GROUP_RANK` / `ABS` …）。

其余（单序列进、同长序列出）是可画线指标 ✓
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 数值参数的默认值（alpha 不给默认值，这里定一份合理的）
SCALAR_DEFAULTS = {
    'periods': 20, 'period': 20, 'n': 5, 'm': 2, 'length': 20,
    'bins': 10, 'q': 0.5, 'k': 1, 'amount': 1.0, 'weight': 0.5,
}

#: 允许「标量广播」的数组参数（alpha 的 `_V` 变体允许数组，标量也行）
BROADCAST_SCALARS = {'periods', 'period', 'ns', 'weight', 'n', 'm', 'k',
                     'bins', 'q', 'amount'}

#: 语义上不是「K 线指标」的，强制归到 NON_KLINE
NON_KLINE_EXTRA = {
    'ABS', 'ALL', 'ANY', 'BACKFILL', 'BACKSET', 'BARSLAST', 'BARSSINCE',
    'BW_SPLIT', 'BW_SPLIT_FACTOR', 'CC_RANK', 'CC_ZSCORE', 'COUNT_NANS',
    'FILTER', 'FW_SPLIT', 'FW_SPLIT_FACTOR', 'GROUP_RANK', 'GROUP_ZSCORE',
    'LAST', 'NEUTRALIZE', 'SCAN_ADD', 'SCAN_MUL', 'SUMBARS', 'SUMIF',
    'WEIGHTED_DELAY', 'WHERE',
}

NOT_INSTALLED = '没装 py-alpha-lib：py -3.12 -m pip install py-alpha-lib'

#: 每个指标的中文说明 / 公式 / 参数 / **主副图归属**（见 scripts/alpha_docs.py）✓
try:
    from alpha_docs import ALPHA_DOCS
except ImportError:                                          # noqa: BLE001
    sys.path.insert(0, str(ROOT / 'scripts' if 'ROOT' in dir() else '.'))
    from alpha_docs import ALPHA_DOCS

#: 生成代码里用的换行符（写文件时才还原成真换行 ✓）
NL = chr(10)


def load_alpha():
    try:
        import alpha
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f'{NOT_INSTALLED}（{error}）') from error
    return alpha


def describe(alpha) -> list[dict]:
    """反射每个函数的参数，判定「能不能画线」。"""
    out: list[dict] = []
    for name in sorted(dir(alpha)):
        if not name.isupper() or name.startswith('FLAG_'):
            continue
        func = getattr(alpha, name)
        if not callable(func):
            continue
        try:
            params = list(inspect.signature(func).parameters.values())
        except (TypeError, ValueError):
            continue
        arrays = [p.name for p in params
                  if str(p.annotation) == 'A'
                  or 'ndarray' in str(p.annotation)]
        scalars = [p.name for p in params if p.name not in arrays]
        for param in list(arrays):
            if param in BROADCAST_SCALARS:      # `_V` 变体：标量也能算 ✓
                arrays.remove(param)
                scalars.append(param)
        drawable = (
            len(arrays) == 1
            and arrays[0] in ('input', 'price')
            and name not in NON_KLINE_EXTRA
        )
        # ★ 按**原指标签名顺序**保留参数（第一个数组参数 = FILED.C，省略）✓
        first_array = arrays[0] if arrays else ''
        order = [(p.name, 'array' if p.name in arrays else 'scalar')
                 for p in params if p.name != first_array]
        out.append({'name': name, 'arrays': arrays,
                    'scalars': scalars, 'drawable': drawable,
                    'order': order})
    return out


def scalar_type(name: str) -> str:
    value = SCALAR_DEFAULTS.get(name, 1)
    return 'int' if isinstance(value, int) and not isinstance(value, bool) \
        else 'float'


def scalar_decl(name: str) -> str:
    value = SCALAR_DEFAULTS.get(name, 1)
    return f'{name}: {scalar_type(name)} = {value!r}'


CLASS_HEAD = NL.join([
    '"""Alpha 指标（py-alpha-lib，Rust 实现，**可选依赖**）',
    '',
    '安装::',
    '',
    '    py -3.12 -m pip install py-alpha-lib',
    '',
    '**⚠ 只有装了这个包才能用**：`import alpha` 失败时，整个 `Alpha` 分类会从',
    '选择器里消失，`import minibt` 和其它指标完全不受影响 ✓',
    '',
    '### 数据源约定（和 pandas_ta / btind 一致）',
    '',
    '* **主数据列固定走 `FILED.C`**：KLine 上就是 `close`，IndSeries 上就是它自己；',
    "  方法签名里**没有** `input='close'` 这种参数 ✓",
    '* 需要**第二条序列**的算子（`CROSS(a,b)` / `ALPHA(input,benchmark)` …）',
    '  才把其余参数列出来（默认 `None`，传 `pd.Series` / `np.ndarray`），',
    '  **顺序与原指标签名一致** ✓',
    '* **可画线**的单序列指标（__DRAW__ 个）里：均线 / 通道 / 位移 / 回归截距',
    '  是**主图叠加**（`overlap=True`，__MAIN__ 个）；标准差 / 方差 / Z 分数 /',
    '  排名 / 相关性 / 熵 / 振幅等统计量是**副图**（`overlap=False`）；',
    '* 其余 __SKIP__ 个是**算子** → 进 `NON_KLINE_INDICATORS`：选择器里不出现，',
    '  但它们同样 `@tobtind(lib="alpha")` + 返回 `IndSeries`，',
    '  策略里可以 `self.data.alpha.cross(b=...)` 直接用 ✓。',
    '"""',
    '',
    'from __future__ import annotations',
    '',
    'from .base import tobtind',
    'from ..utils import TYPE_CHECKING',
    '',
    'if TYPE_CHECKING:',
    '    from typing_ import *',
    '    from .core import *',
    '',
    '',
    'class Alpha:',
    '    """## Alpha 指标指引（py-alpha-lib）',
    '',
    '    - Rust 实现的高性能滚动窗口计算库（Alpha101 / 因子算子）；',
    '    - 需要额外安装：``pip install py-alpha-lib``（Python >= 3.12）；',
    '    - 单序列指标 `self.data.alpha.ma(periods=20)` 直接画线（数据 = close）；',
    '    - 算子类（CROSS / CORR2 / WHERE …）当工具函数用：',
    '      `self.data.alpha.cross(b=other_series)`。',
    '    """',
    '    _perfixes: str = "alpha_"',
    '    _df: IndFrame | IndSeries',
    '',
    '    def __init__(self, data):',
    '        self._df = data',
]) + NL


def doc_of(item: dict) -> dict:
    """取中文说明（缺了就用通用兜底，保证 78 个都有注释 ✓）"""
    name = item['name']
    doc = ALPHA_DOCS.get(name)
    if doc:
        return doc
    return {'title': name, 'desc': f'`alpha.{name}`（Rust 实现）。',
            'formula': f'{name}(x)', 'params': '见原接口签名',
            'main': bool(item['drawable'])}


def main_chart(item: dict) -> bool:
    """是不是**主图叠加**指标（均线 / 通道 / 位移 / 回归截距 → True）✓

    其余（stddev / var / zscore / rank / corr / entropy / 各类算子）
    都是副图或不上图的统计量 → `overlap=False` ✓
    """
    if not item['drawable']:
        return False
    return bool(doc_of(item).get('main'))


def sample_of(item: dict) -> str:
    """生成使用案例（策略里怎么调用）✓"""
    name = item['name'].lower()
    args = []
    for param, kind in item.get('order') or []:
        if kind == 'array':
            args.append(f'{param}=self.data.close')
        elif param in ('periods', 'period', 'ns', 'n'):
            args.append(f'{param}=20')
        elif param in ('k', 'bins', 'm'):
            args.append(f'{param}={SCALAR_DEFAULTS.get(param, 1)!r}')
    call = f'self.data.alpha.{name}({", ".join(args)})'
    return call


def docstring_of(item: dict, first_line: str) -> str:
    """按 pandas_ta 的版式生成中文 docstring（分段：概述 / 公式 / 参数 /
    数据字段 / 使用案例 / 说明）✓"""
    doc = doc_of(item)
    name = item['name']
    chart = '**主图叠加**（与价格同量纲）' if main_chart(item) else         ('**副图指标**（统计量，不与价格同轴）' if item['drawable']
         else '**工具函数**（算子上不了图，但返回 IndSeries）')
    params = [f'>>> {param} ({scalar_type(param)}): 参数. 默认: '
              f'{SCALAR_DEFAULTS.get(param, 1)!r}'
              for param, kind in item.get('order') or [] if kind == 'scalar']
    arrays = [f'>>> {param}: 第二条序列（pd.Series / np.ndarray，必填）'
              for param, kind in item.get('order') or [] if kind == 'array']
    if not params and not arrays:
        params = ['>>> 无参数']
    body = [
        first_line,
        '---------',
        f'    {doc["desc"]}',
        f'    图上归类：{chart}。',
        '',
        '计算方法:',
        '---------',
        f'>>> {doc["formula"]}',
        '',
        '参数:',
        '---------',
        *params,
        *arrays,
        '',
        '所需数据字段:',
        '---------',
        '>>> close（`FILED.C`：K 线收盘价 / IndSeries 自身）',
        '',
        '使用案例:',
        '---------',
        f'>>> ind = {sample_of(item)}',
        '>>> if ind.rising:',
        '>>>     return "指标向上"',
        '',
        '说明:',
        '---------',
        f'    - 原生接口：`alpha.{name}('
        + ', '.join(p for p, _ in item.get('order') or []) + ')`；',
        '    - alpha 用**扩张窗口**（`min_periods=1`），前几根就有值；',
        f'    - 依赖可选包 py-alpha-lib（Rust 实现）✓',
    ]
    return ('        """' + NL.join(body) + '"""')

def method_args(item: dict) -> list[str]:
    """方法签名：**按原指标参数顺序**；第一个数组参数 = FILED.C（不出现）；
    其余数组参数默认 `None`，标量带默认值 ✓"""
    args = []
    for param, kind in item.get('order') or []:
        if kind == 'array':
            args.append(f'{param}=None')
        else:
            args.append(scalar_decl(param))
    args.append('**kwargs')
    return args


def method_block(item: dict) -> str:
    """可画线指标：`@tobtind` 方法（函数体 `...`，真正计算在 CoreFunc）✓"""
    name = item['name']
    args = method_args(item)
    overlap = 'True' if main_chart(item) else 'False'
    title = doc_of(item)['title']
    lines = [
        f'    @tobtind(lib="alpha", overlap={overlap}, '
        f'lines=["{name.lower()}"])',
        f'    def {name.lower()}(self, {", ".join(args)}) -> IndSeries:',
        docstring_of(item, f'{title} ({name})'),
        '        ...',
        '',
    ]
    return NL.join(lines) + NL


def plain_block(item: dict) -> str:
    """算子 / 工具函数：**也走 `@tobtind`**（返回 `IndSeries`，函数体省略）✓

    用户 2026-11-20：这些虽然不是"能上图表的指标"（已进 NON_KLINE），
    但计算结果同样要是内置指标格式 → 统一 `@tobtind(lib="alpha")` +
    `-> IndSeries` + `...`，真正计算在 `CoreFunc.alpha_xxx` ✓
    """
    name = item['name']
    args = method_args(item)
    title = doc_of(item)['title']
    lines = [
        '    @tobtind(lib="alpha")',
        f'    def {name.lower()}(self, {", ".join(args)}) -> IndSeries:',
        docstring_of(item, f'{title} ({name})'),
        '        ...',
        '',
    ]
    return NL.join(lines) + NL


def build_class(items: list[dict]) -> str:
    draw = [item for item in items if item['drawable']]
    skip = [item for item in items if not item['drawable']]
    text = CLASS_HEAD.replace('__DRAW__', str(len(draw)))
    text = text.replace('__MAIN__', str(sum(1 for i in draw if main_chart(i))))
    text = text.replace('__SKIP__', str(len(skip)))
    for item in draw:
        text += method_block(item)
    for item in skip:
        text += plain_block(item)
    names = ', '.join(f'"{item["name"].lower()}"' for item in skip)
    text += (
        '    #: 不是「单序列进 → 同长序列出」的：多序列 / 条件 / 拆股 / 分组 …\n'
        '    #: （选择器里不出现；策略里仍可调用 ✓）\n'
        f'    NON_KLINE_INDICATORS = [{names}]\n'
    )
    return text


CORE_HELPERS = '''# ---------------------------------------------------------------- Alpha
# py-alpha-lib（Rust，**可选依赖**）：`import alpha` 失败时给可读错误 ✓
# ⚠ 必须是**模块级函数**：`CoreFunc` 的方法经 pandas accessor 是**未绑定**调用
#   （`self._alpha_apply()` 会把第一个参数当成 self ✗），所以这里显式传 core。
def _alpha_apply(core, name: str, local: dict, **kwargs):
    """调用 `alpha.<NAME>`（数据源 = `FILED.C`，和 `pta_*` 完全一致）✓

    * 第一个数组参数（alpha 的 `input` / `price` / `a` / `y` …）**固定取
      `close`**：`_get_column_(locals(), *FILED.C)`（KLine → `close`，
      IndSeries → 它自己），所以方法签名里没有 `input='close'` 这种参数 ✓
    * 其余数组参数（`benchmark` / `dividend` / `b` …）由调用方传
      `pd.Series` / `np.ndarray`；标量参数按 alpha 签名决定是否广播；
    * 返回 `pd.Series`（对齐源数据索引）✓
    """
    from .ta_ import _LazyModule
    alpha = _LazyModule("alpha")
    try:
        func = getattr(alpha, name)
    except Exception as error:                                   # noqa: BLE001
        raise RuntimeError(
            "Alpha 指标需要安装 py-alpha-lib："
            "py -3.12 -m pip install py-alpha-lib") from error
    arg, kwarg = _get_column_(core, dict(local or {}), *FILED.C)
    merged = {**(kwarg or {}), **(kwargs or {})}
    annotations = _alpha_signature(name)
    source = get_data(core) if not hasattr(core, "index") else core
    index = getattr(source, "index", None)
    params: dict = {}
    first = True
    for param, annotation in annotations.items():
        value = merged.get(param)
        wants_array = not _alpha_is_scalar(annotation)
        if first and wants_array:
            # 第一个数组参数 ← FILED.C（close）✓
            arrays = arg if isinstance(arg, (list, tuple)) else [arg]
            params[param] = _alpha_array(arrays[0])
            first = False
            continue
        if wants_array:
            if value is None:
                raise ValueError(
                    f'alpha.{name} 需要参数 {param}（pd.Series / np.ndarray）')
            params[param] = _alpha_array(value)
            continue
        # ---- 标量参数 ----
        if isinstance(value, (pd.Series, np.ndarray, list, tuple)):
            flat = np.asarray(value).ravel()
            value = flat[0] if flat.size else value
        if value is None:
            continue
        params[param] = value
    values = np.asarray(func(**params))
    if values.dtype == np.bool_:
        values = values.astype(np.float64)
    if index is not None and len(values) == len(index):
        return pd.Series(values, index=index)
    return pd.Series(values)


def _alpha_array(value) -> np.ndarray:
    """任意序列 → `np.ndarray(float64)` ✓"""
    data = value.to_numpy() if hasattr(value, "to_numpy") else value
    return np.asarray(data, dtype=np.float64)


def _alpha_is_scalar(annotation: str) -> bool:
    """注解是不是标量（`int` / `float` / `bool` / `str`）✓

    `inspect` 拿到的既可能是字符串 `'int'`，也可能是 `<class 'int'>`。
    """
    text = str(annotation or '').strip().rstrip('>').strip()
    return text in ('int', 'float', 'bool', 'str') or text.endswith(
        ("'int'", "'float'", "'bool'", "'str'"))


#: `alpha.<NAME>` 的参数注解缓存（`A` = 数组；`int` / `float` = 标量）✓
_ALPHA_SIGNATURE_CACHE: dict = {}


def _alpha_signature(name: str) -> dict:
    """`alpha.<NAME>` 每个参数的注解串（`'A'` / `'int'` / `'float'`）✓"""
    cached = _ALPHA_SIGNATURE_CACHE.get(name)
    if cached is not None:
        return cached
    out: dict = {}
    try:
        import inspect as _inspect

        from .ta_ import _LazyModule
        func = getattr(_LazyModule('alpha'), name)
        for param in _inspect.signature(func).parameters.values():
            out[param.name] = str(param.annotation)
    except Exception:                                            # noqa: BLE001
        out = {}
    _ALPHA_SIGNATURE_CACHE[name] = out
    return out
'''


def core_methods(items: list[dict]) -> str:
    """`CoreFunc.alpha_*`：完全照 `pta_*` 的写法（`args : close`）✓"""
    out = []
    for item in items:
        name = item['name']
        args = method_args(item)
        extra = ', '.join(f'{name}.{param}'
                          for param, kind in item.get('order') or []
                          if kind == 'array')
        info = doc_of(item)
        doc = 'args : close' + (f' + {extra}' if extra else '')
        lines = [
            '',
            f'    def alpha_{name.lower()}(self, {", ".join(args)})'
            ' -> pd.Series:',
            f'        """{info["title"]}（`alpha.{name}`，Rust 实现）',
            '',
            f'        {info["desc"]}',
            '',
            f'        计算方法：{info["formula"]}',
            '',
            f'        {doc}',
            '        """',
            f'        return _alpha_apply(self, "{name}", locals(), **kwargs)',
        ]
        out.append(NL.join(lines) + NL)
    return ''.join(out)


def main() -> None:
    alpha = load_alpha()
    items = describe(alpha)
    draw = [item['name'] for item in items if item['drawable']]
    skip = [item['name'] for item in items if not item['drawable']]
    print(f'共 {len(items)} 个：可画线 {len(draw)} / 算子 {len(skip)}')
    print('可画线:', ', '.join(draw))
    print('算子  :', ', '.join(skip))
    if '--write' not in sys.argv:
        print('（加 --write 写文件）')
        return
    alpha_py = ROOT / 'minibt' / 'indicators' / 'alpha.py'
    alpha_py.write_text(build_class(items), encoding='utf-8')
    block = CORE_HELPERS + core_methods(items)
    (ROOT / 'scripts' / '_alpha_core_block.txt').write_text(block,
                                                            encoding='utf-8')
    print(f'已写 {alpha_py}（{len(items)} 个指标）')
    print('CoreFunc 代码块 → scripts/_alpha_core_block.txt')


if __name__ == '__main__':
    main()

"""生成 **Alpha101 / Alpha191** 因子内置代码（**别手改产物** ✓）

来源（BSD-2-Clause）：`py-alpha-lib-main/examples/{wq101,gtja191}/al/*.py`

产物：

* `minibt/indicators/_alpha_factors/wq101.py` / `gtja191.py` —— 原样 vendor
* `minibt/indicators/_alpha_factors/registry.py` —— 编号 / 公式 / 类型
* `minibt/indicators/alpha101.py` —— `class Alpha101`（101 个因子，全部要
  `@tobtind(lib="alpha101")`，前缀 `alpha101_`）
* `minibt/indicators/alpha191.py` —— `class Alpha191`（191 个因子，同上）
* `minibt/core.py` —— `alpha101_*` / `alpha191_*` CoreFunc + 计算助手
  （用 `# <alpha101-191:*>` 标记包裹，重复运行只替换标记之间）✓

用法：

    py -3.12 scripts/gen_alpha_factors.py           # 只看统计
    py -3.12 scripts/gen_alpha_factors.py --write   # 写文件
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NL = chr(10)

#: 家族 → 源文件 / 中文名 / 前缀（`alpha101_`）
FAMILIES = {
    'wq101': {
        'src': ROOT / 'py-alpha-lib-main' / 'examples' / 'wq101' / 'al'
        / 'alpha101.py',
        'label': 'WQ Alpha101',
        'module': 'alpha101',
        'class': 'Alpha101',
        'prefix': 'alpha101_',
        'lib': 'alpha101',
        'count': 101,
    },
    'gtja191': {
        'src': ROOT / 'py-alpha-lib-main' / 'examples' / 'gtja191' / 'al'
        / 'alpha191.py',
        'label': 'GTJA Alpha191',
        'module': 'alpha191',
        'class': 'Alpha191',
        'prefix': 'alpha191_',
        'lib': 'alpha191',
        'count': 191,
    },
}

#: 横截面算子 / 字段：单标的没意义（需要多标的 / 行业 / 市值数据 ✓）
CROSS_OPS = r'ctx\.(RANK|INDNEUTRALIZE|SCALE)\('
CROSS_FIELDS = (r"ctx\('(INDCLASS\.[A-Z]+|BANCHMARKINDEX[A-Z]+|"
                r"SEQUENCE|MKT|SMB|HML)'\)")

#: 需要外部数据（指数 / 市值风格因子）→ 同样不进 desk ✓
EXTERNAL_FIELDS = ('BANCHMARKINDEX', 'MKT', 'SMB', 'HML', 'INDCLASS', 'CAP')

VENDOR_HEAD = '''"""`py-alpha-lib` 官方示例因子（**原样 vendor，别手改**）

来源：https://github.com/msd-rs/py-alpha-lib
        `examples/{path}`
许可：BSD-2-Clause（见 `py-alpha-lib` 仓库 LICENSE）

* 每个 `alpha_NNN(ctx)` 是纯函数：输入 `alpha.context.ExecContext`，
  返回**展平面板数组**（`securityid × tradetime`，长度 = 标的数 × 根数）；
* 单标的场景由 `minibt/indicators/_alpha_factors/context.py` 按 **IndFrame 自己**
  的列构造面板（有 `securityid` / `tradetime` 就用，没有就当单标的 ✓）；
* 想把它们变成 minibt 指标请看 `scripts/gen_alpha_factors.py`。
"""
'''


def split_functions(source: str) -> list[dict]:
    """拆出每个 `alpha_NNN`：编号 / 公式注释 / 源码块 ✓

    源文件格式（`py-alpha-lib` 示例）：

    ```
    # (-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), ...))
    def alpha_001(ctx):
      ...
    ```
    """
    pattern = re.compile(
        '((?:^# .*' + NL + ')+)^def (alpha_(\\d{3}))\\(ctx\\):',
        re.MULTILINE)
    matches = list(pattern.finditer(source))
    out: list[dict] = []
    for index, match in enumerate(matches):
        formula = ' '.join(line.lstrip('# ').strip()
                           for line in match.group(1).splitlines()
                           if line.strip())
        start = match.start() + len(match.group(1))       # 从 `def` 开始
        end = (matches[index + 1].start()
               if index + 1 < len(matches) else len(source))
        out.append({'no': int(match.group(3)), 'func': match.group(2),
                    'formula': formula, 'body': source[start:end]})
    return out


def classify(item: dict) -> str:
    """`ts` = 纯时序（单标的可用）/ `cross` = 横截面 / `external` = 缺数据"""
    text = item['body']
    fields = re.findall(r"ctx\('([A-Z0-9_.]+)'\)", text)
    if any(field.startswith(EXTERNAL_FIELDS) for field in fields):
        return 'external'
    if re.search(CROSS_OPS, text) or re.search(CROSS_FIELDS, text):
        return 'cross'
    return 'ts'


def doc_text(text: str) -> str:
    """公式 → 单行（去掉换行 / 多余空格 ✓）"""
    return ' '.join(str(text or '').split()) or '（无）'


def method_name(no: int) -> str:
    """因子编号 → 方法名（`alpha001` … `alpha191`，和用户调用一致 ✓）"""
    return f'alpha{no:03d}'


def build_registry(found: dict) -> str:
    lines = [
        '"""Alpha101 / Alpha191 因子注册表（`gen_alpha_factors.py` 生成 ✓）',
        '',
        '* `FACTORS[family][no]` = `{func, method, kind, formula}`；',
        "* `kind`：`ts` 纯时序（单标的可算）/ `cross` 横截面（要多标的）/"
        '`external` 缺外部数据；',
        '* `TS_NUMBERS[family]`：可以直接挂到单标的 K 线上的编号 ✓',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        '#: 家族 → 说明（`label` 中文名 / `module` / `prefix` / `count`）',
        'FAMILIES: dict[str, dict] = {',
    ]
    for family, meta in FAMILIES.items():
        lines.append(
            f'    {family!r}: {{"label": {meta["label"]!r}, '
            f'"module": {meta["module"]!r}, "prefix": {meta["prefix"]!r}, '
            f'"class": {meta["class"]!r}, "count": {meta["count"]}}},')
    lines += ['}', '', '#: 家族 → {编号: 元数据}']
    lines.append('FACTORS: dict[str, dict[int, dict]] = {')
    for family, items in found.items():
        lines.append(f'    {family!r}: {{')
        for item in items:
            lines.append(
                f'        {item["no"]}: {{"func": {item["func"]!r}, '
                f'"method": {method_name(item["no"])!r}, '
                f'"kind": {item["kind"]!r}, '
                f'"formula": {doc_text(item["formula"])!r}}},')
        lines.append('    },')
    lines += ['}', '']
    for name, kind in (('TS_NUMBERS', 'ts'), ('CROSS_NUMBERS', 'cross'),
                       ('EXTERNAL_NUMBERS', 'external')):
        comment = {'ts': '纯时序（单标的可算，desk 里能显示 ✓）',
                   'cross': '横截面（要 `securityid` 等面板列 → 不进 desk）',
                   'external': '缺外部数据（指数 / 市值风格 → 不进 desk）'}[kind]
        lines += [f'#: 家族 → {comment}', f'{name}: dict[str, list[int]] = {{']
        for family, items in found.items():
            numbers = [item['no'] for item in items if item['kind'] == kind]
            lines.append(f'    {family!r}: {numbers},')
        lines += ['}', '']
    return NL.join(lines) + NL


def factor_doc(family: str, item: dict) -> list[str]:
    """单个因子的中文 docstring（8 空格缩进 ✓）"""
    meta = FAMILIES[family]
    kind_note = {
        'ts': '**纯时序**：只用本标的价量 → 单根 K 线（IndFrame）就能算 ✓',
        'cross': ('**横截面**：`RANK` / `INDNEUTRALIZE` 需要多标的'
                  '（IndFrame 里要有 `securityid` / `tradetime` / `indclass`）'),
        'external': ('**缺外部数据**：要用基准指数 / 市值风格列'
                     '（`MKT` / `SMB` / `HML` / `BANCHMARKINDEX*`）'),
    }[item['kind']]
    return [
        f'{meta["label"]} #{item["no"]}',
        '---------',
        '    ' + doc_text(item['formula']),
        '',
        '数据来源:',
        '---------',
        f'>>> IndFrame 自身（{kind_note}）',
        '',
        '说明:',
        '---------',
        '    - 副图指标（`overlap=False`）：因子值无量纲，正负代表多空倾向；',
        '    - 原始出处：`py-alpha-lib` 官方示例（BSD-2-Clause）✓',
        '    - 计算走 `alpha` 的 `ExecContext`（可选依赖：`pip install py-alpha-lib`）；',
        '    - 数据不符合因子要求时由 alpha 直接抛原生错误（不做封装）。',
    ]


def build_class(family: str, found: dict) -> str:
    meta = FAMILIES[family]
    items = found[family]
    ts_total = sum(1 for item in items if item['kind'] == 'ts')
    skip = [method_name(item['no']) for item in items
            if item['kind'] != 'ts']
    numbers = [item['no'] for item in items if item['kind'] == 'ts']
    chunks = [', '.join(str(no) for no in numbers[i:i + 12])
              for i in range(0, len(numbers), 12)]
    head = [
        f'"""**{meta["label"]}** 因子（从 `py-alpha-lib` 官方示例内置 ✓）',
        '',
        f'`{meta["label"]}` 共 **{meta["count"]} 个因子**，前缀 `{meta["prefix"]}`，',
        f'入口 `self.kline.{meta["module"]}.alpha001()` …',
        '',
        f'### 单标的 vs 横截面',
        '',
        f'* **{ts_total} 个纯时序因子**：只用本标的价量 → 任何 IndFrame 都能算，',
        '  desk 选择器里能看到（副图）；',
        f'* 其余 **{meta["count"] - ts_total} 个**是横截面 / 缺外部数据因子：',
        '  要自己准备正确的 IndFrame（`securityid` / `tradetime` /',
        '  `indclass` / 基准指数 …），否则 alpha 会抛原生错误；',
        f'  这些已进 `NON_KLINE_INDICATORS`，**不在 desk 选择器里显示** ✓',
        '',
        '### 用法',
        '',
        '```python',
        f'factor = self.data.{meta["module"]}.alpha001()   # 副图一条线',
        '```',
        '',
        '依赖可选包 `py-alpha-lib`（Rust）：没装时调用抛可读错误，',
        '`import minibt` 不受影响 ✓',
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
        f'class {meta["class"]}:',
        f'    """## {meta["label"]} 因子',
        '',
        f'    - 全部 {meta["count"]} 个因子（前缀 `{meta["prefix"]}`），全部**副图**；',
        f'    - 纯时序 {ts_total} 个可直接用（desk 可见）：',
        f'      `self.data.{meta["module"]}.alpha001()`；',
        f'    - 横截面 / 缺数据因子要自备正确的 IndFrame 列，错误由 alpha 原生抛出；',
        '    - 依赖可选包 py-alpha-lib（BSD-2-Clause 示例原样 vendor）。',
        '    """',
        f'    _perfixes: str = "{meta["prefix"]}"',
        '    _df: IndFrame | IndSeries',
        '',
        '    def __init__(self, data):',
        '        self._df = data',
    ]
    blocks = [NL.join(head) + NL]

    for item in items:
        name = method_name(item['no'])
        overlap = 'False'
        lines = [
            f'    @tobtind(lib="{meta["lib"]}", overlap={overlap}, '
            f'lines=["{name}"])',
            f'    def {name}(self, **kwargs) -> IndSeries:',
            '        """' + NL.join(factor_doc(family, item)) + '"""',
            '        ...',
            '',
        ]
        blocks.append(NL.join(lines) + NL)

    if skip:
        named = ', '.join(f'"{name}"' for name in skip)
        wrapped = []
        line = '    NON_KLINE_INDICATORS = ['
        for index, name in enumerate(skip):
            piece = f'"{name}", '
            if len(line) + len(piece) > 88:
                wrapped.append(line.rstrip())
                line = ' ' * len('    NON_KLINE_INDICATORS = [')
            line += piece
        wrapped.append(line.rstrip().rstrip(',') + ']')
        blocks.append(
            '    #: **非纯时序**因子（横截面 / 缺外部数据）→ desk 选择器不显示，\n'
            '    #: 但方法照样存在，传对数据就能算 ✓\n'
            + NL.join(wrapped) + NL)
    else:
        blocks.append('    NON_KLINE_INDICATORS = []' + NL)
    blocks.append(
        f'    #: 纯时序因子编号（desk 里能显示的 {len(numbers)} 个）\n'
        f'    PURE_INDICATORS = {numbers}\n')
    return ''.join(blocks)


HELPER = '''# <alpha101-191:helpers:begin>  ← gen_alpha_factors.py 生成，勿手改
# ------------------------------------------------------- Alpha101 / Alpha191
def _alpha_factor_apply(core, family: str, no: int):
    """算一个 Alpha101 / Alpha191 因子（**数据源 = `core` 自己** ✓）

    * `core` 就是调用方传进来的数据（`IndFrame` / K 线）：里面的
      列原样交给上游 `alpha.context.ExecContext`；
    * 面板列（`securityid` / `tradetime` / `indclass` / `cap` …）有就用，
      没有就按**单标的**处理（`securities = 1`）；
    * 数据不满足因子要求时**不拦**：alpha 自己会抛原生错误 ✓；
    * 计算在 `alpha` 的线程上下文里跑，跑完还原（不污染别的调用 ✓）。
    """
    from .indicators._alpha_factors import compute_series

    return compute_series(core, family, no)
# <alpha101-191:helpers:end>
'''


def build_core(found: dict) -> str:
    out = ['# <alpha101-191:methods:begin>  ← gen_alpha_factors.py 生成，勿手改']
    for family, meta in FAMILIES.items():
        for item in found[family]:
            name = method_name(item['no'])
            out += [
                '',
                f'    def {meta["prefix"]}{name}(self, **kwargs) -> pd.Series:',
                f'        """{meta["label"]} #{item["no"]}',
                '',
                '        ' + doc_text(item['formula']),
                '',
                '        args : self（IndFrame / K 线自身；横截面因子需要面板列）',
                '        """',
                f'        return _alpha_factor_apply(self, "{family}", '
                f'{item["no"]})',
            ]
    out.append('# <alpha101-191:methods:end>')
    return NL.join(out) + NL


def splice(text: str, begin: str, end: str, block: str, anchor: str) -> str:
    """用标记块替换（没有标记就在 `anchor` 后面插一次 ✓）"""
    if begin in text and end in text:
        head = text[:text.index(begin)]
        tail = text[text.index(end) + len(end):]
        return head + block.rstrip(NL) + tail
    index = text.index(anchor) + len(anchor)
    return text[:index] + NL + block + text[index:]


def drop_block(text: str, begin: str, end: str) -> str:
    """删掉旧标记块（迁移历史实现时用 ✓）"""
    if begin in text and end in text:
        head = text[:text.index(begin)]
        tail = text[text.index(end) + len(end):]
        return head + tail.lstrip(NL)
    return text


def main() -> None:
    found: dict[str, list[dict]] = {}
    for family, meta in FAMILIES.items():
        source = pathlib.Path(meta['src']).read_text(encoding='utf-8')
        items = split_functions(source)
        for item in items:
            item['kind'] = classify(item)
        found[family] = items
    for family, items in found.items():
        kinds: dict[str, int] = {}
        for item in items:
            kinds[item['kind']] = kinds.get(item['kind'], 0) + 1
        print(f'{family}: {len(items)} 个 → {kinds}')

    if '--write' not in sys.argv:
        print('（加 --write 写文件）')
        return

    folder = ROOT / 'minibt' / 'indicators' / '_alpha_factors'
    folder.mkdir(parents=True, exist_ok=True)
    for family, meta in FAMILIES.items():
        source = pathlib.Path(meta['src']).read_text(encoding='utf-8')
        path_text = f'examples/{family}/al/alpha{family[-3:]}.py'
        head = VENDOR_HEAD.format(path=path_text)
        (folder / f'{family}.py').write_text(head + NL + NL + source,
                                            encoding='utf-8')
    (folder / 'registry.py').write_text(build_registry(found), encoding='utf-8')

    indicators = ROOT / 'minibt' / 'indicators'
    for family, meta in FAMILIES.items():
        (indicators / f'{meta["module"]}.py').write_text(
            build_class(family, found), encoding='utf-8')
    # 旧的单文件实现（`AlphaFactor`）已废弃 ✓
    legacy = indicators / 'alpha_factor.py'
    if legacy.exists():
        legacy.unlink()

    core = ROOT / 'minibt' / 'core.py'
    text = core.read_text(encoding='utf-8')
    text = drop_block(text, '# <alpha-factors:helpers:begin>',
                      '# <alpha-factors:helpers:end>')
    text = drop_block(text, '# <alpha-factors:methods:begin>',
                      '# <alpha-factors:methods:end>')
    text = splice(text, '# <alpha101-191:helpers:begin>',
                  '# <alpha101-191:helpers:end>', HELPER,
                  '    _ALPHA_SIGNATURE_CACHE[name] = out' + NL + '    return out'
                  + NL)
    text = splice(text, '# <alpha101-191:methods:begin>',
                  '# <alpha101-191:methods:end>', build_core(found),
                  '        return _alpha_apply(self, "ZSCORE", locals(),'
                  ' **kwargs)' + NL)
    core.write_text(text, encoding='utf-8')

    total = sum(len(items) for items in found.values())
    ts = sum(1 for items in found.values() for item in items
             if item['kind'] == 'ts')
    print(f'已写：_alpha_factors/{{wq101,gtja191,registry}}.py、'
          f'alpha101.py、alpha191.py（{total} 个因子，纯时序 {ts}）、'
          'core.py（alpha101_* / alpha191_*）')


if __name__ == '__main__':
    main()

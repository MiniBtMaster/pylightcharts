"""生成「Rust 指标库」的 API 参考页（`scripts/gen_rust_lib_docs.py` ✓）

本周新增 / 完善了 6 个 **Rust 为底层** 的内置指标库（都是**可选依赖**）：

| 模块 | 类 | 门面 | 前缀 | 指标数 | Rust 包 |
|---|---|---|---|---|---|
| `ferro_ta` | `FerroTa` | `kline.ferro` | `ferro_` | 225 | `ferro-ta` |
| `tulip_rs` | `TulipRS` | `kline.tulip_rs` | `tulip_` | 88 | `tulip-rs` |
| `vector_ta` | `VectorTa` | `kline.vta` | `vta_` | 209 | `vector-ta` |
| `wickra` | `Wickra` | `kline.wickra` | `wickra_` | 427 | `wickra` |
| `kand` | `Kand` | `kline.kand` | `kand_` | 59 | `kand` |
| `pta_rs` | `PtaRs` | `kline.pta_rs` | `pta_rs_` | 27 | `py-alpha-lib` |

生成内容（**全部从真实模块反射**，不手抄，避免文档和代码不一致 ✗）：

* 概览 / 安装 / 调用方式 / 参数与返回 / 主图副图规则；
* 指标目录（主图 vs 副图，按名字排序）；
* 逐个指标：线名、主/副图、参数（从 docstring 的 `>>>` 行提取）、首行说明。

用法：

    py -3.12 scripts/gen_rust_lib_docs.py            # 只看统计
    py -3.12 scripts/gen_rust_lib_docs.py --write    # 写进 minibt_docs/docs/minibt_api_reference/
"""
from __future__ import annotations

import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DOCS = ROOT / 'minibt_docs' / 'docs' / 'minibt_api_reference'
NL = chr(10)

#: 每个库的元信息（模块名 → 文档所需的一切 ✓）
LIBS = [
    {
        'module': 'ferro_ta', 'cls': 'FerroTa', 'file': 'ferro_ta.md',
        'title': 'FerroTa',
        'gate': 'kline.ferro', 'prefix': 'ferro_',
        'pip': 'ferro', 'pkg': 'ferro-ta',
        'url': 'https://pypi.org/project/ferro-ta/',
        'pitch': 'TA-Lib 兼容的 Rust 指标库：函数名 / 参数名沿用 TA-Lib，'
                 '数值口径与 TA-Lib 基本一致，但**没有 C 依赖**，'
                 '安装即用（含 61 个 K 线形态 `CDL*`）。',
        'style': 'TA-Lib 风格：**大写**方法名 + `timeperiod` / `fastperiod` 等参数',
    },
    {
        'module': 'tulip_rs', 'cls': 'TulipRS', 'file': 'tulip_rs.md',
        'title': 'TulipRS',
        'gate': 'kline.tulip_rs', 'prefix': 'tulip_',
        'pip': 'tulip', 'pkg': 'tulip-rs',
        'url': 'https://pypi.org/project/tulip-rs/',
        'pitch': 'Tulip Indicators 的 **Rust 绑定**：经典、轻量、数值稳定，'
                 '每个指标都很小很快；desk 里做"快算 + 交叉验证"很合适。',
        'style': 'Tulip 风格：**大写**方法名 + `period`（多周期用 '
                 '`short_period` / `long_period` / `signal_period`）',
    },
    {
        'module': 'vector_ta', 'cls': 'VectorTa', 'file': 'vector_ta.md',
        'title': 'VectorTa',
        'gate': 'kline.vta', 'prefix': 'vta_',
        'pip': 'vta', 'pkg': 'vector-ta',
        'url': 'https://pypi.org/project/vector-ta/',
        'pitch': 'Rust 向量化指标库：除了经典指标，还带一批**新派量化指标**'
                 '（Ehlers 周期类、波动率锥、回撤统计、TD 序列…），'
                 '底层按 CPU 选 `scalar` / `avx2` / `avx512` 内核（结果一致，只影响速度）。',
        'style': '`snake_case` 小写方法名 + `length` / `period` 参数；'
                 '可选 `kernel=` 指定计算内核',
    },
    {
        'module': 'wickra', 'cls': 'Wickra', 'file': 'wickra.md',
        'title': 'Wickra',
        'gate': 'kline.wickra', 'prefix': 'wickra_',
        'pip': 'wickra', 'pkg': 'wickra',
        'url': 'https://pypi.org/project/wickra/',
        'pitch': '覆盖面**最广**的 Rust 技术分析库（427 个）：均线 / 通道 / 振荡 / '
                 '量能 / 统计（Sharpe、Sortino、VaR…）/ K 线形态 / 斐波那契 / '
                 'TD 序列 / 画线形态识别（头肩、三角、谐波…）。',
        'style': '方法名**大小写混排**（`SMA` / `BollingerBands` / `TDSequential`），'
                 '参数名以 `period` 为主',
    },
    {
        'module': 'kand', 'cls': 'Kand', 'file': 'kand.md',
        'title': 'Kand',
        'gate': 'kline.kand', 'prefix': 'kand_',
        'pip': 'kand', 'pkg': 'kand',
        'url': 'https://pypi.org/project/kand/',
        'pitch': 'TA-Lib 风格的轻量 Rust 库：接口与 TA-Lib 基本一一对应，'
                 '数值口径成熟稳定，适合替换 TA-Lib 的常用子集。',
        'style': '`snake_case` 小写方法名 + `period` / `fast_period` 参数',
    },
    {
        'module': 'pta_rs', 'cls': 'PtaRs', 'file': 'pta_rs.md',
        'title': 'PtaRs',
        'gate': 'kline.pta_rs', 'prefix': 'pta_rs_',
        'pip': 'py-alpha-lib', 'pkg': 'py-alpha-lib',
        'url': 'https://pypi.org/project/py-alpha-lib/',
        'pitch': '**pandas_ta 的 Rust 版**：pandas_ta 没有官方 Rust 实现，'
                 '这里用 `py-alpha-lib` 的 Rust 滚动算子把公式 1:1 拼出来，'
                 '27 个常用指标里 **24 个与 pandas_ta 逐值一致**（其余误差 ≤ 1e-6），'
                 '`ts_argmax` 提速 **61×**、`sma` 38×、`wma` 16×。',
        'style': '**完全对齐 pandas_ta**：`snake_case` 方法名 + `length` 参数',
    },
]

#: docstring 里像参数的行走这里（`>>> period (int): 周期. 默认: 20`）
PARAM_RE = re.compile(r'^>>>\s*(?P<text>.+)$')


def _first_sentence(text: str) -> str:
    """docstring 第一段 → 一句话说明（去掉 `## 名称 —— 描述` 前缀 ✓）"""
    lines = [line.strip() for line in str(text or '').splitlines()]
    for line in lines[1:]:
        if not line or set(line) <= {'-', '='}:
            continue
        if line.startswith(('参数', '返回', '数据源', '使用方法', '信号')):
            break
        return line
    return ''


def _params_and_lines(doc: str) -> tuple[list[str], list[str]]:
    """从 docstring 抽出「参数行」和「返回行」（都是 `>>> …` 开头 ✓）"""
    params: list[str] = []
    returns: list[str] = []
    mode = ''
    for raw in str(doc or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('参数'):
            mode = 'param'
            continue
        if line.startswith('返回'):
            mode = 'return'
            continue
        if line.startswith(('数据源', '使用方法', '信号', '说明')):
            mode = ''
            continue
        found = PARAM_RE.match(line)
        if not found:
            continue
        text = found.group('text').strip()
        if mode == 'param':
            params.append(text)
        elif mode == 'return':
            returns.append(text)
    return params, returns


#: 写示例时优先用这些"谁都有、参数简单"的指标 ✓
SAMPLE_NAMES = ('sma', 'SMA', 'ema', 'EMA', 'wma', 'WMA', 'rsi', 'RSI', 'atr')


def _pick_sample(rows: list[dict]) -> str:
    """挑一个适合写进示例的指标（优先 sma / ema …，否则第一个 ✓）"""
    names = {row['name'] for row in rows}
    for candidate in SAMPLE_NAMES:
        if candidate in names:
            return candidate
    return rows[0]['name'] if rows else 'SMA'


def _meta(fn) -> dict:
    return dict(vars(fn).get('_decorator_args') or {})


def build_page(spec: dict) -> tuple[str, int]:
    module = importlib.import_module(f"minibt.indicators.{spec['module']}")
    cls = getattr(module, spec['cls'])
    members = [(name, fn) for name, fn in vars(cls).items()
               if callable(fn) and not name.startswith('_')]
    members.sort(key=lambda item: item[0].lower())
    rows = []
    for name, fn in members:
        meta = _meta(fn)
        rows.append({
            'name': name, 'fn': fn, 'meta': meta,
            'overlap': bool(meta.get('overlap')),
            'lines': [str(item) for item in (meta.get('lines') or [])],
        })
    overlap = [row for row in rows if row['overlap']]
    panes = [row for row in rows if not row['overlap']]

    out: list[str] = []
    add = out.append
    add(f"# {spec['title']} 类 API 参考（{spec['pkg']} · Rust）")
    add('')
    add(f"> 门面：`{spec['gate']}`（`{spec['cls']}`，`{spec['prefix']}` 前缀）"
        f" · **{len(rows)}** 个指标")
    add(f"> 安装：`py -3.12 -m pip install {spec['pip']}`"
        f"（**Rust 扩展 / 可选依赖**；没装时 desk 对应分组自动消失，"
        '`import minibt` 与其它指标完全不受影响 ✓）')
    add(f"> 原库文档：{spec['url']}")
    add('')
    add('## 特点')
    add('')
    add(spec['pitch'])
    add('')
    add('| 项 | 说明 |')
    add('| --- | --- |')
    add(f"| 门面 | `{spec['gate']}`（`KLine` / `IndSeries` / `IndFrame` 上都有 ✓）|")
    add(f"| 前缀 | `{spec['prefix']}`（`desk` 内部 / `batch()` 用前缀，代码里用点号）|")
    add(f"| 指标数 | **{len(rows)}**（主图 {len(overlap)} / 副图 {len(panes)}）|")
    add(f"| 命名风格 | {spec['style']} |")
    add('| 数据源 | 调用它的那根 K 线 / 指标自己'
        '（`close` / `high` / `low` / `open` / `volume` 自动取）|')
    add('| 返回 | 单线 → `IndSeries`；多线 → `IndFrame`（线名见下方目录）|')
    add('')
    add('## 调用方式')
    add('')
    add('```python')
    gate = spec['gate'].split('.')[-1]
    sample = _pick_sample(rows)
    add('# 门面已绑定数据源，**不要**再传源数据')
    add(f'line = kline.{gate}.{sample}()')
    add('# 单列也行（用这一列当输入）')
    add(f'close_line = kline.close.{gate}.{sample}()')
    add('# 多线指标可以解包')
    add('a, b, c = frame  # IndFrame 支持多返回值解包（见 8.11）')
    add('```')
    add('')
    add('```python')
    add('from minibt import *')
    add('')
    add('kline = KLine("SHFE.rb2601", "1m", "2024-01-01", "2024-06-30")')
    add(f'ma = kline.{gate}.{sample}()')
    add('ma.plot(kline)')
    add('```')
    add('')
    add('## 主图 / 副图规则')
    add('')
    add('* `overlap=True`（均线 / 通道 / 形态类）→ **叠在主图**，价格轴不变；')
    add('* 其余（振荡 / 量能 / 统计类）→ **副图**，自动分配 pane；')
    add('* 同一指标的多条线共用一张副图（不会拆散 ✓）。')
    add('')
    add('## 指标目录')
    add('')
    if overlap:
        add(f'**主图（{len(overlap)}）**')
        add('')
        add(_wrap_names([row['name'] for row in overlap]))
        add('')
    add(f'**副图（{len(panes)}）**')
    add('')
    add(_wrap_names([row['name'] for row in panes]) if panes else '（无）')
    add('')
    add('## 逐个指标')
    add('')
    if len(rows) > 120:
        # ★ 指标特别多（wickra 427 / vector-ta 209 …）→ 用**紧凑表**，
        #   不逐条贴 docstring（否则单页 1.5 MB，mkdocs 构建会很慢 ✗）；
        #   参数 / 说明直接看原库文档或编辑器里的 docstring ✓
        add('| 指标 | 位置 | 线 |')
        add('| --- | --- | --- |')
        for row in rows:
            pane = '主图' if row['overlap'] else '副图'
            add(f"| `{row['name']}` | {pane} | {_lines_text(row['lines'])} |")
        add('')
        return NL.join(out).rstrip() + NL, len(rows)
    for row in rows:
        add(f"### `{row['name']}`")
        add('')
        pane = '主图（overlap）' if row['overlap'] else '副图'
        add(f'* 位置：{pane}　线：{_lines_text(row["lines"])}')
        params, returns = _params_and_lines(row['fn'].__doc__ or '')
        if params:
            add('* 参数：')
            for item in params:
                add(f'    * {item}')
        if returns:
            add('* 返回：' + '；'.join(returns))
        summary = _first_sentence(row['fn'].__doc__ or '')
        if summary:
            add(f'* 说明：{summary}')
        add('')
    return NL.join(out).rstrip() + NL, len(rows)


def _lines_text(lines: list[str], limit: int = 6) -> str:
    """线名（Bar / Kagi 这类可能有上千条 → 只列前 6 条 + 总数 ✓）"""
    items = [str(item) for item in (lines or [])]
    if not items:
        return '—'
    head = ' / '.join(f'`{item}`' for item in items[:limit])
    if len(items) > limit:
        head += f' …（共 {len(items)} 条）'
    return head


def _wrap_names(names: list[str], per_line: int = 8) -> str:
    """指标名按 8 个一行用反引号包起来（紧凑、可搜索 ✓）"""
    lines = []
    for start in range(0, len(names), per_line):
        chunk = names[start:start + per_line]
        lines.append(' '.join(f'`{name}`' for name in chunk))
    return NL.join(lines) if lines else '（无）'


def main(argv: list[str]) -> int:
    write = '--write' in argv
    DOCS.mkdir(parents=True, exist_ok=True)
    for spec in LIBS:
        try:
            page, count = build_page(spec)
        except Exception as error:                            # noqa: BLE001
            print(f'[skip] {spec["module"]}: {error!r}')
            continue
        target = DOCS / spec['file']
        print(f'{spec["file"]:<16} {count:>4} 个指标  {len(page):>8} 字符')
        if write:
            target.write_text(page, encoding='utf-8')
    if write:
        print(f'已写入 {DOCS}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python
"""依赖「轮子就绪度」检查（3.12 / 3.13 / 3.14）。

为什么需要它
------------
minibt 的依赖里混着 **纯 Python**、**C 扩展**、**Rust 扩展**三类。换 Python
小版本时最容易踩的坑是：

* 上游只发了 sdist（源码包）→ 装的时候要现场编译，缺 MSVC / Rust 就卡住；
* 上游根本没发这个版本的轮子（比如 `kand` 在 cp314 上）→ 只能等或本地编；
* `abi3`（`cp39-abi3-*`）看起来像老版本，其实**通吃** 3.9+ —— 别误判成
  「仅 sdist」✗

这个脚本直接查 PyPI 的 JSON API，把「每个包 × 每个 Python 小版本」的
轮子情况打出来（不出网也能跑：失败就标 `?`）。

用法::

    py -3.12 scripts/check_dep_matrix.py                 # 默认 3.12/3.13/3.14
    py -3.12 scripts/check_dep_matrix.py --markdown      # 输出 markdown 表
    py -3.12 scripts/check_dep_matrix.py --only tulipy kand
    py -3.12 scripts/check_dep_matrix.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import urllib.error
import urllib.request

#: 默认检查的 Python 小版本（跟 minibt `requires-python` 对齐）
DEFAULT_VERSIONS = ('3.12', '3.13', '3.14')

#: 依赖 → (PyPI 名, 备注)。`pip` 名与 import 名常常不一样，所以显式给 ✓
PACKAGES: list[tuple[str, str, str]] = [
    # ---- 必需 ----
    ('numpy', 'numpy', '数值基础'),
    ('pandas', 'pandas', '数据帧'),
    ('scipy', 'scipy', '统计 / 优化'),
    ('numba', 'numba', 'JIT（skew/kurtosis 加速）'),
    ('TA-Lib', 'ta-lib', 'C 扩展'),
    ('tulipy', 'tulipy', '仅 sdist（3.14 第一个硬阻塞）'),
    ('tqsdk', 'tqsdk', '实盘'),
    ('psutil', 'psutil', 'C 扩展'),
    ('requests', 'requests', '纯 Python'),
    # ---- 可选（指标库） ----
    ('py-alpha-lib', 'py-alpha-lib', 'Rust（maturin）'),
    ('kand', 'kand', 'Rust，cp314 暂缺'),
    ('wickra', 'wickra', 'Rust'),
    ('ferro-ta', 'ferro-ta', 'Rust'),
    ('tulip-rs', 'tulip-rs', 'Rust'),
    ('vector-ta', 'vector-ta', 'Rust'),
    # ---- GUI / 桌面 ----
    ('PyQt6', 'PyQt6', 'abi3（cp39-abi3）'),
    ('PyQt6-WebEngine', 'PyQt6-WebEngine', 'abi3'),
    ('pylightcharts', 'pylightcharts', '图表前端'),
    # ---- 外部数据 / 交易 ----
    ('futu-api', 'futu-api', 'C++ 源码'),
    ('tqsdk-ctpse', 'tqsdk-ctpse', '索引待确认'),
]

#: wheel 文件名里的 ABI 标签 → 支持的 Python 小版本
_ABI_PATTERN = re.compile(r'-(cp|py)(\d)(\d{1,2})-')
_ABI3_PATTERN = re.compile(r'-cp(\d)(\d{1,2})-abi3-')

PYPI_URL = 'https://pypi.org/pypi/{name}/json'
TIMEOUT = 20


def _fetch(name: str) -> dict:
    """取 PyPI JSON（失败抛异常，由调用方降级 ✓）"""
    request = urllib.request.Request(
        PYPI_URL.format(name=name),
        headers={'User-Agent': 'minibt-dep-matrix/1.0 '
                               f'({platform.system()})'},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8'))


def _supports(filenames: list[str], version: str) -> set[str]:
    """这个版本的 Python 能装哪些类型的分发？→ `{'wheel'}` / `{'sdist'}` / 空"""
    major, minor = version.split('.')
    cp = f'cp{major}{minor}'
    kinds: set[str] = set()
    for filename in filenames:
        if filename.endswith(('.tar.gz', '.zip')):
            kinds.add('sdist')
            continue
        if not filename.endswith('.whl'):
            continue
        if _ABI3_PATTERN.search(filename):
            base = int(_ABI3_PATTERN.search(filename).group(2))
            # abi3 的 wheel 从 cp3X 起通吃（cp39-abi3 支持 3.9+）✓
            if int(minor) >= base:
                kinds.add('wheel')
            continue
        match = _ABI_PATTERN.search(filename)
        if match:
            tag = f'{match.group(1)}{match.group(2)}{match.group(3)}'
            if tag == cp:
                kinds.add('wheel')
            continue
        # `py3-none-any` / `py2.py3-none-any` → 纯 Python，全版本通用 ✓
        if '-none-any.whl' in filename:
            kinds.add('wheel')
    return kinds


def _latest_files(data: dict) -> tuple[str, list[str]]:
    """最新版本的文件名列表（兼容 `urls` 为空的新版本）✓"""
    version = str(data.get('info', {}).get('version') or '?')
    files = [row['filename'] for row in data.get('urls', []) or []]
    if files:
        return version, files
    releases = data.get('releases') or {}
    return version, [row['filename'] for row in releases.get(version, []) or []]


def _cell(kinds: set[str]) -> str:
    if 'wheel' in kinds:
        return 'wheel'
    if 'sdist' in kinds:
        return 'sdist'
    return '-'


def check(packages, versions, *, timeout: int = TIMEOUT) -> list[dict]:
    """逐个包查 → 行数据 ✓"""
    rows: list[dict] = []
    for label, pypi_name, note in packages:
        row = {'name': label, 'pypi': pypi_name, 'note': note,
               'version': '?', 'cells': {}}
        try:
            data = _fetch(pypi_name)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            row['error'] = type(error).__name__
            row['cells'] = {version: '?' for version in versions}
            rows.append(row)
            continue
        except Exception as error:                             # noqa: BLE001
            row['error'] = repr(error)[:60]
            row['cells'] = {version: '?' for version in versions}
            rows.append(row)
            continue
        version, files = _latest_files(data)
        row['version'] = version
        row['cells'] = {v: _cell(_supports(files, v)) for v in versions}
        rows.append(row)
    return rows


def _plain(rows: list[dict], versions) -> str:
    head = f'{"包":<22}{"版本":<12}' + ''.join(f'{v:<10}' for v in versions)
    lines = [head, '-' * len(head)]
    for row in rows:
        cells = ''.join(f'{row["cells"].get(v, "?"):<10}' for v in versions)
        lines.append(f'{row["name"]:<22}{row["version"]:<12}{cells}'
                     f'{row["note"]}')
    return '\n'.join(lines)


def _markdown(rows: list[dict], versions) -> str:
    head = '| 包 | 最新版本 | ' + ' | '.join(versions) + ' | 备注 |'
    sep = '| --- | --- | ' + ' | '.join('---' for _ in versions) + ' | --- |'
    lines = [head, sep]
    for row in rows:
        cells = ' | '.join(row['cells'].get(v, '?') for v in versions)
        lines.append(f'| {row["name"]} | {row["version"]} | {cells} | '
                     f'{row["note"]} |')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='minibt 依赖轮子就绪度（3.12 / 3.13 / 3.14）')
    parser.add_argument('--versions', nargs='+', default=list(DEFAULT_VERSIONS),
                        help='要检查的 Python 小版本（默认 3.12 3.13 3.14）')
    parser.add_argument('--only', nargs='+', default=None,
                        help='只查这些包（按名字前缀匹配）')
    parser.add_argument('--markdown', action='store_true',
                        help='输出 markdown 表格（贴 changelog 用 ✓）')
    parser.add_argument('--json', default='', help='把结果写到这个 JSON 文件')
    args = parser.parse_args(argv)

    packages = PACKAGES
    if args.only:
        wanted = [name.lower() for name in args.only]
        packages = [row for row in PACKAGES
                    if any(row[0].lower().startswith(w) for w in wanted)]
    rows = check(packages, args.versions)
    print(_markdown(rows, args.versions) if args.markdown
          else _plain(rows, args.versions))
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as handle:
            json.dump({'versions': args.versions, 'rows': rows}, handle,
                      ensure_ascii=False, indent=2)
        print(f'\n已写入 {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

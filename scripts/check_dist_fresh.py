#!/usr/bin/env python
"""打包**之后**的资料一致性检查：sdist 里的文件必须与工作区**逐字节一致**。

为什么要这个脚本
----------------
`python -m build` 之后如果再改一个会被 sdist 收录的文件（`docs/changelog.md`、
`README.md`、`CHANGELOG.md`、`RELEASE_NOTES.md`、`RELEASING.md` ……），
打出来的包就**落后于仓库**了 —— 用户拿到 sdist 看到的还是旧文档 ✗。
实测踩过两次（minibt 1.3.7 的 CHANGELOG、pylightcharts 0.2.0 的
`docs/changelog.md`），所以把它固化成一条命令。

用法
----
```
# pylightcharts（仓库根就是项目根）
python scripts/check_dist_fresh.py dist/pylightcharts-0.2.0.tar.gz

# minibt（项目根是 minibt/ 子目录）
python scripts/check_dist_fresh.py minibt/dist/minibt-1.3.7.tar.gz --root minibt

# 只想看有没有过期（CI 用）：过期返回 1
```
`--root` 默认是当前目录；`--quiet` 只输出结论。
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import tarfile

#: 这些是**构建过程自己生成**的，工作区里本来就没有（不算过期 ✓）
GENERATED = {'PKG-INFO', 'setup.cfg', 'pyproject.toml.orig'}
GENERATED_DIRS = ('egg-info/', '.egg-info/', 'build/')


def _is_generated(rel: str) -> bool:
    name = rel.rsplit('/', 1)[-1]
    if name in GENERATED:
        return True
    return any(part in rel for part in GENERATED_DIRS)


def check(sdist: pathlib.Path, root: pathlib.Path) -> tuple[int, list[str]]:
    """返回 (比对文件数, 不一致列表) ✓"""
    checked = 0
    problems: list[str] = []
    prefix = sdist.name.replace('.tar.gz', '')
    with tarfile.open(sdist) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            rel = member.name.split('/', 1)[1] if '/' in member.name \
                else member.name
            if rel == prefix:
                continue
            if _is_generated(rel):
                continue
            target = root / rel
            if not target.is_file():
                problems.append(f'工作区缺失：{rel}')
                continue
            checked += 1
            packaged = archive.extractfile(member)
            if packaged is None:
                continue
            if packaged.read() != target.read_bytes():
                problems.append(f'内容已过期：{rel}')
    return checked, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdist', help='要检查的 .tar.gz（或 dist/ 目录）')
    parser.add_argument('--root', default='.',
                        help='项目根目录（默认当前目录；minibt 用 minibt）')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    target = pathlib.Path(args.sdist)
    if target.is_dir():
        found = sorted(target.glob('*.tar.gz'))
        if not found:
            print(f'✗ {target} 里没有 sdist ✗')
            return 2
        target = found[-1]
    if not target.is_file():
        print(f'✗ 找不到 {target} ✗')
        return 2

    checked, problems = check(target, root)
    if problems:
        print(f'✗ {target.name} 与工作区不一致（{len(problems)} 处）：')
        for line in problems[:40]:
            print('   ', line)
        print('\n改完资料后要重新 `python -m build` ✗')
        return 1
    if not args.quiet:
        print(f'✓ {target.name}：{checked} 个文件与工作区逐字节一致 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())

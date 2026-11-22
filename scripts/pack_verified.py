#!/usr/bin/env python
"""**可验证**的仓库打包 / 解包 / 目录比对（替代"右键 → 360 压缩"）。

为什么需要它
------------
360 压缩、资源管理器"发送到压缩文件夹"、`Compress-Archive` 在下面这些情况
是**静默跳过**的（不写日志、不报错，第二天才发现少了东西 ✗）：

* 文件正被占用（desk / Jupyter / pytest 还开着，`*.pyd`、`*.log`、`qwebchannel.js`）；
* 杀毒软件的实时防护拦下（`.pyd` `.c` `.dll` `.exe`）；
* 路径超过 260 字符（`node_modules` / `.git` 深处）；
* 勾了"忽略隐藏 / 系统文件"（`.git` `.github` `.vscode`）；
* 分卷只解了第一卷；解压到**已存在**的旧目录时"跳过同名"；
* 目标盘空间不足 / FAT32 单文件 4GB 上限。

本脚本的做法：**打包时就把清单写进包里，解包后再逐字节校验**，
不一致立刻报错 —— 把"第二天才发现"变成"当场就知道"✓

用法::

    # 1) 打包（自动生成 MANIFEST.sha256 放进包内）
    python scripts/pack_verified.py pack --out D:/bak/pylightcharts-1119.tar.gz

    # 2) 解包后校验（也可以直接校验别人给的包）
    python scripts/pack_verified.py verify D:/bak/pylightcharts-1119.tar.gz

    # 3) 两个目录/包比对 → 列出"少了哪些文件"（排查丢文件用）
    python scripts/pack_verified.py compare . D:/pylightcharts备/pylightcharts20261119/pylightcharts

约定
----
* 清单文件 `MANIFEST.sha256`：每行 `sha256  大小  相对路径`（UTF-8）✓
* 默认排除构建产物（`--all` 关掉排除，把一切都打进去）；
* Windows 长路径自动加 ``\\\\?\\`` 前缀，不会因为 260 字符截断 ✓
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import os
import sys
import tarfile
import tempfile

#: 默认排除（构建产物 / 依赖 / 缓存）：不进包，省体积也避免绝对路径中间物
DEFAULT_EXCLUDES = (
    '*/node_modules/*', 'node_modules/*',
    '*/__pycache__/*', '__pycache__/*',
    '*.pyc', '*.pyo',
    '.git/*', '*/.git/*',
    '*/build/*', 'build/*',
    '*/dist/*', 'dist/*',
    '*.egg-info/*', '*/*.egg-info/*',
    '*/site/*', 'site/*',
    '*/results/*', 'results/*',
    '*.log',
)

MANIFEST = 'MANIFEST.sha256'
LONG_PREFIX = '\\\\?\\'


def _long(path: str) -> str:
    """Windows 长路径前缀（>260 字符也能读写 ✓）"""
    if os.name != 'nt':
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith(LONG_PREFIX):
        return absolute
    if absolute.startswith('\\\\'):
        return '\\\\?\\UNC\\' + absolute[2:]
    return LONG_PREFIX + absolute


def _excluded(rel: str, patterns) -> bool:
    rel = rel.replace('\\', '/')
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def walk(root: str, patterns=DEFAULT_EXCLUDES, only=()):
    """遍历文件 → [(相对路径, 绝对路径, 大小)]（已按路径排序 ✓）"""
    root = os.path.abspath(root)
    out = []
    for folder, dirs, files in os.walk(_long(root)):
        dirs[:] = [d for d in dirs
                   if not _excluded(os.path.join(
                       os.path.relpath(folder, _long(root)), d), patterns)]
        for name in files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, _long(root)).replace('\\', '/')
            if _excluded(rel, patterns):
                continue
            if only and not any(fnmatch.fnmatch(rel, pat) for pat in only):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            out.append((rel, full, size))
    out.sort()
    return out


def digest(path: str) -> str:
    sha = hashlib.sha256()
    with open(_long(path), 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def manifest_of(root: str, patterns=DEFAULT_EXCLUDES, only=()) -> dict:
    """目录 → {相对路径: (sha256, 大小)} ✓"""
    rows = {}
    for rel, full, size in walk(root, patterns, only):
        rows[rel] = (digest(full), size)
    return rows


def write_manifest(rows: dict) -> bytes:
    lines = ['# minibt 打包清单（sha256  大小  相对路径）']
    for rel in sorted(rows):
        sha, size = rows[rel]
        lines.append(f'{sha}  {size}  {rel}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def read_manifest(data: bytes) -> dict:
    rows = {}
    for line in data.decode('utf-8', 'replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('  ', 2)
        if len(parts) != 3:
            continue
        sha, size, rel = parts
        try:
            rows[rel] = (sha, int(size))
        except ValueError:
            continue
    return rows


def _report(left: dict, right: dict, left_name: str, right_name: str,
            show: int = 40) -> int:
    """比对两份清单 → 返回差异条数（0 = 完全一致 ✓）"""
    missing = sorted(set(right) - set(left))
    extra = sorted(set(left) - set(right))
    changed = sorted(rel for rel in set(left) & set(right)
                     if left[rel][0] != right[rel][0])
    total = len(missing) + len(extra) + len(changed)
    print(f'[{left_name}] {len(left)} 个文件   '
          f'[{right_name}] {len(right)} 个文件')
    if not total:
        print('✅ 完全一致（逐文件 sha256 相同）')
        return 0
    for title, rows in ((f'❌ 只有 {right_name} 有（{left_name} 缺）', missing),
                        (f'⚠ 只有 {left_name} 有（{right_name} 缺）', extra),
                        ('⚠ 内容不同', changed)):
        if not rows:
            continue
        print(f'\n{title}：{len(rows)} 个')
        for rel in rows[:show]:
            print('   ', rel)
        if len(rows) > show:
            print(f'    … 还有 {len(rows) - show} 个')
    return total


# ---------------------------------------------------------------- 子命令
def cmd_pack(args) -> int:
    root = args.root or '.'
    patterns = () if args.all else tuple(args.exclude or DEFAULT_EXCLUDES)
    rows = manifest_of(root, patterns, tuple(args.only or ()))
    if not rows:
        print('❌ 没有可打包的文件（检查 --only / --exclude）')
        return 2
    out = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    prefix = args.prefix or os.path.basename(os.path.abspath(root))
    print(f'打包 {len(rows)} 个文件 → {out}（前缀 {prefix}/）…')
    with tarfile.open(out, 'w:gz') as tar:
        data = write_manifest(rows)
        info = tarfile.TarInfo(f'{prefix}/{MANIFEST}')
        info.size = len(data)
        info.mtime = int(os.path.getmtime(__file__))
        tar.addfile(info, io.BytesIO(data))
        base = os.path.abspath(root)
        for rel in sorted(rows):
            full = os.path.normpath(os.path.join(base, rel))
            # 太长（>240）才加 `\?\` 前缀；短路径保持原样，避免
            # `tarfile` 里的 `os.lstat` 被混合分隔符卡住 ✓
            tar.add(full if len(full) < 240 else _long(full),
                    arcname=f'{prefix}/{rel}', recursive=False)
    print(f'✅ 已写入 {out}（{os.path.getsize(out) / 1e6:.1f} MB，'
          f'含 {MANIFEST}）')
    return 0


def cmd_verify(args) -> int:
    archive = args.archive
    with tarfile.open(archive, 'r:*') as tar:
        try:
            handle = tar.extractfile(f'{args.prefix}/{MANIFEST}'
                                     if args.prefix else MANIFEST)
        except KeyError:
            # 前缀未知 → 找第一个 MANIFEST.sha256
            handle = None
            for member in tar.getmembers():
                if member.name.endswith(MANIFEST):
                    handle = tar.extractfile(member)
                    break
        if handle is None:
            print(f'❌ 包里没有 {MANIFEST}（不是本脚本打的包，无法校验内容）')
            return 2
        expected = read_manifest(handle.read())
        print(f'清单：{len(expected)} 个文件，开始逐个校验 sha256 …')
        actual = {}
        with tempfile.TemporaryDirectory() as temp:
            tar.extractall(temp)
            base = temp
            roots = [d for d in os.listdir(temp)
                     if os.path.isdir(os.path.join(temp, d))]
            if len(roots) == 1:
                base = os.path.join(temp, roots[0])
            for rel in expected:
                path = os.path.normpath(os.path.join(base,
                                                     rel.replace('/', os.sep)))
                if not os.path.isfile(path):
                    continue
                actual[rel] = (digest(path), os.path.getsize(path))
    bad = _report(actual, expected, '包内实际', '清单声明')
    if bad:
        print('\n❌ 校验失败：包里的内容与清单不一致（打包时就有文件被跳过）')
        return 1
    print('\n✅ 校验通过：包完整，可放心解压')
    return 0


def cmd_compare(args) -> int:
    patterns = () if args.all else tuple(args.exclude or DEFAULT_EXCLUDES)
    only = tuple(args.only or ())
    left = manifest_of(args.left, patterns, only)
    right = manifest_of(args.right, patterns, only)
    bad = _report(left, right, args.left, args.right, show=args.show)
    return 0 if not bad else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='可验证的打包 / 解包校验 / 目录比对（防静默丢文件）')
    sub = parser.add_subparsers(dest='command', required=True)

    pack = sub.add_parser('pack', help='打包（自动写入 MANIFEST.sha256）')
    pack.add_argument('--root', default='.', help='要打包的目录（默认当前目录）')
    pack.add_argument('--out', required=True, help='输出 .tar.gz')
    pack.add_argument('--prefix', default='', help='包内顶层目录名（默认=目录名）')
    pack.add_argument('--only', nargs='+', default=None,
                      help='只打这些路径（支持通配符）')
    pack.add_argument('--exclude', nargs='+', default=None,
                      help='额外排除（默认已排除 build/node_modules/缓存）')
    pack.add_argument('--all', action='store_true', help='不做任何排除')
    pack.set_defaults(func=cmd_pack)

    verify = sub.add_parser('verify', help='校验包内容与清单是否一致')
    verify.add_argument('archive')
    verify.add_argument('--prefix', default='', help='包内顶层目录名')
    verify.set_defaults(func=cmd_verify)

    compare = sub.add_parser('compare', help='两个目录比对（找缺失文件）')
    compare.add_argument('left')
    compare.add_argument('right')
    compare.add_argument('--only', nargs='+', default=None)
    compare.add_argument('--exclude', nargs='+', default=None)
    compare.add_argument('--all', action='store_true')
    compare.add_argument('--show', type=int, default=40,
                         help='每类最多列多少条（默认 40）')
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

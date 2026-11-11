"""`scripts/check_dist_fresh.py`：打包后再改资料 → sdist 过期，要能查出来 ✓"""
from __future__ import annotations

import importlib.util
import io
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        'check_dist_fresh', ROOT / 'scripts' / 'check_dist_fresh.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_sdist(path: pathlib.Path, files: dict[str, bytes], prefix='pkg-1.0') -> None:
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f'{prefix}/{name}')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_fresh_sdist_passes(tmp_path):
    module = _script()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'changelog.md').write_text('新内容', encoding='utf-8')
    sdist = tmp_path / 'pkg-1.0.tar.gz'
    _make_sdist(sdist, {'docs/changelog.md': '新内容'.encode('utf-8')})
    checked, problems = module.check(sdist, tmp_path)
    assert checked == 1
    assert problems == []


def test_stale_sdist_is_reported(tmp_path):
    """打完包又改了 changelog → 必须报「内容已过期」✓"""
    module = _script()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'changelog.md').write_text('改了', encoding='utf-8')
    sdist = tmp_path / 'pkg-1.0.tar.gz'
    _make_sdist(sdist, {'docs/changelog.md': '旧的'.encode('utf-8')})
    _, problems = module.check(sdist, tmp_path)
    assert problems == ['内容已过期：docs/changelog.md']
    assert module.main([str(sdist), '--root', str(tmp_path), '--quiet']) == 1


def test_generated_files_are_ignored(tmp_path):
    """`PKG-INFO` / `egg-info` 是构建自己生成的，不算过期 ✓"""
    module = _script()
    sdist = tmp_path / 'pkg-1.0.tar.gz'
    _make_sdist(sdist, {'PKG-INFO': b'Meta',
                        'pkg.egg-info/SOURCES.txt': b'x',
                        'setup.cfg': b'[metadata]'})
    checked, problems = module.check(sdist, tmp_path)
    assert checked == 0
    assert problems == []


def test_missing_file_is_reported(tmp_path):
    module = _script()
    sdist = tmp_path / 'pkg-1.0.tar.gz'
    _make_sdist(sdist, {'docs/gone.md': b'x'})
    _, problems = module.check(sdist, tmp_path)
    assert problems == ['工作区缺失：docs/gone.md']


def test_cli_on_real_dist_if_present(tmp_path):
    """仓库里已有 dist（打过包）→ 必须与工作区一致 ✓（没打就跳过）"""
    dist = ROOT / 'dist'
    sdists = sorted(dist.glob('*.tar.gz')) if dist.is_dir() else []
    if not sdists:
        return
    module = _script()
    checked, problems = module.check(sdists[-1], ROOT)
    assert checked > 100
    assert problems == []

"""编辑器（LSP/jedi）的 sys.path：`minibt` 的悬停 / 补全 / 跳转定义（2026-10-31）

用户反馈：编辑器里**当前文件内定义**的类 / 函数有悬停注释，但 `minibt.xxx`
的类 / 方法悬停是空的（而且此时 py3.12 里已经把 minibt 卸载了，只有仓库里那份）。

根因（jedi 的默认环境）：
* `jedi.get_default_environment()` 是 `SameEnvironment`，它的 `get_sys_path()`
  是在**子进程**里算的（jedi 文档原话：*Does not include potential modifications
  from e.g. appending to sys.path*）→ 运行时插进 `sys.path` 的**源码仓库根**
  它看不到；
* 所以「源码跑 desk、minibt 没装进 site-packages」时编辑器解析不到 `minibt`
  → 悬停 / 补全全空 ✗；装进 site-packages 的用户本来就正常（site-packages
  一直在 sys.path 上），但源码仓库也应该稳。

修法：`minibt/desk/lsp.py`
* `editor_sys_path()` 显式拼 sys.path：**源码仓库根 → 进程 sys.path →
  文件/工作区目录 → PYTHONPATH → 用户 site-packages**（只留真实存在的目录）；
* `_editor_environment()` 用 `InterpreterEnvironment` 子类把这份 sys.path
  **直接喂给 jedi**（进程内推断，不启子进程）；
* `_LanguageEngine.refresh_paths()`：换文件时补上该文件所在目录；
* `info()` 带上 `minibt_path` / `sys_path_count`，编辑器徽标 tooltip 直接显示
  「minibt → 路径」，找不到时给出提示。
"""
from __future__ import annotations

import os
import sys

import pytest

from minibt.desk import lsp

REPO = os.path.dirname(os.path.dirname(os.path.abspath(lsp.__file__)))


def test_editor_sys_path_covers_repo_and_site_packages():
    paths = lsp.editor_sys_path()
    assert paths, 'sys.path 空了'
    # 源码仓库根（`minibt/__init__.py` 的上一级）必须在里面
    assert any(os.path.isfile(os.path.join(p, 'minibt', '__init__.py'))
               for p in paths), paths[:6]
    # 去重 + 只留真实存在的目录
    assert len(paths) == len(set(paths))
    assert all(os.path.isdir(p) for p in paths)


def test_editor_sys_path_puts_source_before_site_packages():
    """源码仓库排在前面：机器上装着**旧版** minibt 也不能抢先 ✓"""
    paths = lsp.editor_sys_path()
    source = [i for i, p in enumerate(paths)
              if os.path.isfile(os.path.join(p, 'minibt', '__init__.py'))]
    site = [i for i, p in enumerate(paths)
            if p.replace('\\', '/').endswith('site-packages')]
    assert source, paths[:6]
    if site:
        assert min(source) < min(site), (source, site)


def _make_fake_repo(tmp_path, folder='owen'):
    """造一个「搬家后」的仓库：``<tmp>/owen/minibt/__init__.py`` ✓"""
    root = tmp_path / folder
    package = root / 'minibt'
    package.mkdir(parents=True)
    source = chr(10).join([
        '"""假的 minibt（搬家后的仓库）"""',
        '',
        '',
        'class Bt:',
        '    """## 搬家后的 Bt（声明来自这里）"""',
        '',
        '    def run(self, plot=True):',
        '        """跑一个回测（假）"""',
        '',
    ])
    (package / '__init__.py').write_text(source, encoding='utf-8')
    (root / 'tutorials' / 'basic').mkdir(parents=True)
    target = root / 'tutorials' / 'basic' / 'x.py'
    target.write_text(chr(10).join(['from minibt import Bt', '',
                                    'bt = Bt()', 'bt.', '']),
                      encoding='utf-8')
    return root, target


def test_find_repo_roots_walks_up_from_the_file(tmp_path):
    """仓库**搬家 / 改名**（pylightcharts → owen）后仍能找到根 ✓"""
    root, target = _make_fake_repo(tmp_path, 'owen')
    assert lsp.find_repo_roots(str(target)) == [str(root)]
    assert lsp.find_repo_roots(str(target.parent)) == [str(root)]
    # 找不到（没 marker）→ 空；不存在的路径也不炸
    assert lsp.find_repo_roots(str(tmp_path / 'nope')) == []
    assert lsp.find_repo_roots('') == []


def test_moved_repository_is_first_in_sys_path(tmp_path):
    root, target = _make_fake_repo(tmp_path, 'owen')
    paths = lsp.editor_sys_path(str(target.parent))
    assert str(root) in paths
    assert paths[0] == str(root), paths[:3]      # 源码仓库排在 site-packages 前 ✓


def test_editor_follows_the_moved_repository(tmp_path):
    """搬家后的仓库能被真正解析：悬停 / 补全都来自**新地址**那份 ✓"""
    root, target = _make_fake_repo(tmp_path, 'owen')
    engine = lsp._LanguageEngine(str(root))
    code = target.read_text(encoding='utf-8')
    hover = engine.hover(code, str(target), 0, 19)
    assert hover, '搬家后的 minibt 悬停为空'
    value = hover['contents']['value']
    assert '搬家后的 Bt' in value, value[:200]
    labels = [item.get('label') for item in
              engine.completion(code, str(target), 3, 3)]
    assert 'run' in labels, labels[:10]


def test_editor_sys_path_includes_extra_dirs(tmp_path):
    target = str(tmp_path)
    assert target in lsp.editor_sys_path(target)
    # 不存在的目录不加（避免 jedi 白跑）
    assert str(tmp_path / 'nope') not in lsp.editor_sys_path(
        str(tmp_path / 'nope'))


@pytest.fixture()
def clean_paths(monkeypatch):
    """把仓库根从 sys.path 里摘掉，模拟「minibt 只在仓库里、没装包」✓"""
    monkeypatch.setattr(
        sys, 'path',
        [p for p in sys.path
         if os.path.abspath(p or os.getcwd()) != REPO])
    return None


def test_hover_finds_minibt_even_without_site_packages(clean_paths, tmp_path):
    assert REPO not in [os.path.abspath(p or os.getcwd()) for p in sys.path]
    engine = lsp._LanguageEngine(REPO)
    assert REPO in engine.sys_path                     # 我们自己补回来了 ✓
    assert REPO in engine.environment.get_sys_path()

    code = 'from minibt import Bt\n\nbt = Bt()\n'
    path = tmp_path / 'demo.py'
    path.write_text(code, encoding='utf-8')
    hover = engine.hover(code, str(path), 0, 19)        # `Bt`
    assert hover, 'minibt.Bt 悬停为空'
    value = hover['contents']['value']
    assert 'minibt.bt.Bt' in value
    assert 'Bt(auto=' in value or '回测' in value


def test_completion_and_definition_work_for_minibt(clean_paths, tmp_path):
    engine = lsp._LanguageEngine(REPO)
    code = 'from minibt import Bt\n\nbt = Bt()\nbt.\n'
    path = tmp_path / 'demo2.py'
    path.write_text(code, encoding='utf-8')
    items = engine.completion(code, str(path), 3, 3)
    labels = {item.get('label') for item in items}
    assert 'addstrategy' in labels or 'add_strategy' in labels, sorted(labels)[:10]
    # `Bt` 是 minibt 里的类 → 跳转定义指向仓库里的文件
    locations = engine.definition(code, str(path), 0, 19)
    assert locations, '跳转定义没结果'
    assert any('minibt' in (item.get('uri') or '') for item in locations)


def test_refresh_paths_picks_up_file_directory(clean_paths, tmp_path):
    engine = lsp._LanguageEngine('')
    before = list(engine.sys_path)
    engine.refresh_paths(str(tmp_path))
    assert str(tmp_path) in engine.sys_path
    # 幂等：再刷一次不重复
    engine.refresh_paths(str(tmp_path))
    assert engine.sys_path.count(str(tmp_path)) == 1
    assert len(before) <= len(engine.sys_path)


def test_info_reports_minibt_path():
    service = lsp.LspService(root=REPO)
    info = service.info()
    assert info['type'] == 'lsp'
    assert info['sys_path_count'] == len(service.engine.sys_path)
    assert info['minibt_path'].endswith('minibt'), info
    assert os.path.isfile(os.path.join(info['minibt_path'], '__init__.py'))


def test_unknown_name_hover_is_none_not_crash(tmp_path):
    """空白处 / 注释上悬停 → None（前端不弹框），不能抛异常 ✓"""
    engine = lsp._LanguageEngine(REPO)
    code = '\n\n# 只有注释\n'
    path = tmp_path / 'demo3.py'
    path.write_text(code, encoding='utf-8')
    assert engine.hover(code, str(path), 0, 0) is None
    assert engine.hover(code, str(path), 2, 4) is None

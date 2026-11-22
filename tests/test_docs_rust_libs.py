"""「Rust 指标库」文档护栏（2026-11 ✓）

本周新增 / 完善了 6 个 Rust 为底层的指标库，API 参考页必须：

1. `minibt_docs/docs/minibt_api_reference/` 下**每一页都存在**；
2. 都挂进 `mkdocs.yml` 的 nav（否则站点里点不到）；
3. `docs/index.md` 的「API参考」完整目录里也能点到；
4. 页面里的**指标数量、前缀、门面**和真实模块一致（`scripts/gen_rust_lib_docs.py`
   反射生成，文档不能和代码漂移 ✗）。
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCS = REPO / 'minibt_docs' / 'docs'
REF = DOCS / 'minibt_api_reference'
MKDOCS = REPO / 'minibt_docs' / 'mkdocs.yml'
INDEX = DOCS / 'index.md'

#: 模块 → (类名, 门面, 前缀, 页面)
LIBS = {
    'ferro_ta': ('FerroTa', 'kline.ferro', 'ferro_', 'ferro_ta.md'),
    'tulip_rs': ('TulipRS', 'kline.tulip_rs', 'tulip_', 'tulip_rs.md'),
    'vector_ta': ('VectorTa', 'kline.vta', 'vta_', 'vector_ta.md'),
    'wickra': ('Wickra', 'kline.wickra', 'wickra_', 'wickra.md'),
    'kand': ('Kand', 'kline.kand', 'kand_', 'kand.md'),
    'pta_rs': ('PtaRs', 'kline.pta_rs', 'pta_rs_', 'pta_rs.md'),
}


@pytest.mark.parametrize('module', sorted(LIBS))
def test_rust_lib_page_matches_module(module):
    cls_name, gate, prefix, page = LIBS[module]
    path = REF / page
    assert path.is_file(), f'缺页面：{page}'
    text = path.read_text(encoding='utf-8')
    mod = importlib.import_module(f'minibt.indicators.{module}')
    cls = getattr(mod, cls_name)
    count = len(getattr(mod, '_INDICATOR_NAMES', ()) or ())
    assert f'**{count}** 个指标' in text, f'{page} 里的指标数量过期'
    assert gate in text
    assert prefix in text
    # 主图 / 副图都统计了（= 方法总数）
    methods = [name for name, fn in vars(cls).items()
               if callable(fn) and not name.startswith('_')]
    assert len(methods) == count


def test_rust_pages_registered_in_nav_and_index():
    nav = MKDOCS.read_text(encoding='utf-8')
    home = INDEX.read_text(encoding='utf-8')
    for _cls, _gate, _prefix, page in LIBS.values():
        rel = f'minibt_api_reference/{page}'
        assert rel in nav, f'mkdocs.yml 少了 {rel}'
        assert rel in home, f'index.md 少了 {rel}'


def test_api_index_lists_rust_libs():
    api_index = (DOCS / 'api' / 'index.md').read_text(encoding='utf-8')
    for _cls, _gate, _prefix, page in LIBS.values():
        assert f'minibt_api_reference/{page}' in api_index


def test_indicator_libs_chapter_mentions_rust():
    """`api/04_indicator_libs.md` 里要有「Rust 指标库」总表（tablib 口径对照 ✓）"""
    text = (DOCS / 'api' / '04_indicator_libs.md').read_text(encoding='utf-8')
    assert '## Rust 指标库' in text
    for cls, gate, _prefix, _page in LIBS.values():
        assert f'`{cls}`' in text and f'`{gate}`' in text


def test_changelog_simple_is_the_main_entry():
    """★ 更新日志默认显示**简单版**，完整版从简单版里点进去 ✓

    （用户 2026-11-22：nav 改成 `changelog_simple.md`，简单版里给完整版入口）
    """
    nav = MKDOCS.read_text(encoding='utf-8')
    assert 'MiniBT更新日志: changelog_simple.md' in nav
    # 完整版仍要在 nav 里（mkdocs --strict 下没有孤儿页 ✓）
    assert 'changelog.md' in nav
    simple = (DOCS / 'changelog_simple.md').read_text(encoding='utf-8')
    head = simple[:900]
    assert '(changelog.md)' in head          # 详细日志入口 ✓
    detail = (DOCS / 'changelog.md').read_text(encoding='utf-8')
    assert '(changelog_simple.md)' in detail[:600]   # 完整版也能返回 ✓
    home = (DOCS / 'index.md').read_text(encoding='utf-8')
    assert 'changelog_simple.md' in home

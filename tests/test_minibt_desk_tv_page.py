"""「指标和策略」页（仿 TradingView，只针对 minibt 的 tv: 指标 ✓ 2026-11-02）

* 卡片列表 = 指标目录里 `tv:` 组（114 个），分组 / 关键词 / 收藏 / 分页；
* 卡片缩略图：本地没有就**现场生成 SVG**（也可以手动「重新截图」）；
* 点卡片 → **新开一个页签**（本地图表组件，preset `tv`：工具栏只留
  商品搜索框 / 周期（禁用）/ 图表类型，左侧画线导航栏默认显示）；
* 页签右键「查看原始码（只读）」= desk 的 CodeMirror 只读视图；
* 「商品搜索框」连了行情时可在线搜合约并替换本页数据（`tv_live`）；
* 入口：首页左侧「工作区」、顶栏「＋」菜单、命令面板。
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK_TS = ROOT / 'jslib' / 'src' / 'desk'


def _read(path) -> str:
    return pathlib.Path(path).read_text(encoding='utf-8')


@pytest.fixture()
def tv(tmp_path, monkeypatch):
    from minibt.desk import tv_page as mod

    monkeypatch.setattr(mod, 'CARD_DIR', str(tmp_path / 'cards'))
    monkeypatch.setattr(mod, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(mod, '_FRAME_CACHE', {'frame': None})
    return mod


# ------------------------------------------------------------------ 目录
def test_catalog_only_tradingview_indicators(tv):
    items = tv.catalog()
    assert items, '指标目录里没有 tv: 组'
    assert all(item['key'].startswith('tv:') for item in items)
    assert len(items) >= 100
    first = items[0]
    for field in ('key', 'name', 'group', 'desc', 'params', 'overlap'):
        assert field in first
    # 简介 / 参数来自类本身 ✓
    ut = next(item for item in items if item['key'] == 'tv:UT_Bot_Alerts')
    assert ut['name'] == 'UT_Bot_Alerts'
    assert isinstance(ut['params'], dict) and ut['params']


def test_list_payload_paginates_and_filters(tv):
    page1 = tv.list_payload({'page': 1})
    assert page1['total'] >= 100
    assert page1['size'] == tv.TV_PAGE_SIZE
    assert len(page1['items']) == min(tv.TV_PAGE_SIZE, page1['total'])
    assert page1['pages'] >= 2
    page2 = tv.list_payload({'page': 2})
    assert page2['page'] == 2
    assert page2['items'][0]['key'] != page1['items'][0]['key']
    # 关键词过滤（名称 / 分组 / 简介）
    found = tv.list_payload({'query': 'ut_bot'})
    assert any('UT_Bot' in item['key'] for item in found['items'])
    assert found['total'] == len(found['items'])
    # 空结果
    assert tv.list_payload({'query': 'zzz-not-exists'})['total'] == 0


def test_star_and_comment_roundtrip(tv):
    key = 'tv:UT_Bot_Alerts'
    assert tv.star_payload({'key': key, 'on': True})['ok'] is True
    starred = tv.list_payload({'star': True})
    assert [item['key'] for item in starred['items']] == [key]
    assert tv.star_payload({'key': key, 'on': False})['ok'] is True
    assert tv.list_payload({'star': True})['total'] == 0

    added = tv.comment_payload({'key': key, 'action': 'add', 'text': '很准'})
    assert added['ok'] and len(added['comments']) == 1
    cid = added['comments'][0]['id']
    detail = tv.detail_payload({'key': key})
    assert detail['comments'][0]['text'] == '很准'
    removed = tv.comment_payload({'key': key, 'action': 'remove', 'id': cid})
    assert removed['ok'] and removed['comments'] == []
    # 空评论不允许 ✓
    assert tv.comment_payload({'key': key, 'text': '  '})['ok'] is False


# ---------------------------------------------------------------- 缩略图
def test_snapshot_is_generated_on_demand(tv, tmp_path):
    key = 'tv:UT_Bot_Alerts'
    assert tv._existing_card(key) == ''          # 还没生成 ✓
    data = tv.snapshot_payload({'key': key})
    assert data['ok'] is True
    assert data['dataUrl'].startswith('data:image/svg+xml;base64,')
    assert pathlib.Path(data['path']).is_file()
    assert tv._existing_card(key) == data['path']  # 之后列表就带图了 ✓
    # force=True 会重新生成 ✓
    again = tv.snapshot_payload({'key': key, 'force': True})
    assert again['ok'] is True


def test_thumbnail_svg_has_candles_and_labels(tv):
    svg = tv.thumbnail_svg('tv:UT_Bot_Alerts', 'light')
    assert svg.startswith('<svg') and '<rect' in svg
    assert svg.count('<line') > 50               # K 线影线 ✓
    assert '指标' in svg                          # 角标 ✓
    assert 'UT_Bot_Alerts' in svg                # 名称 ✓
    dark = tv.thumbnail_svg('tv:UT_Bot_Alerts', 'dark')
    assert '#0f1115' in dark


# ------------------------------------------------------------------ 图表
def test_chart_html_has_kline_and_indicator(tv):
    html = tv.chart_html('tv:UT_Bot_Alerts', 'light')
    assert len(html) > 100_000
    assert 'desk-sl-driver' in html              # 和回测图同一套驱动 ✓
    assert 'createHistogramSeries' in html or 'addSeries' in html
    # Qt 壳：临时文件 + file:// ✓
    url = tv.chart_file('tv:UT_Bot_Alerts', 'light')
    assert url.startswith('file://')


def test_hot_sort_and_newest_comment_first(tv):
    key = 'tv:UT_Bot_Alerts'
    plain = tv.list_payload({'page': 1})
    assert plain['items'][0]['key'] != key
    # 收藏 → 排到第一（「热门」= 我收藏的 > 评论多 > 名字 ✓）
    tv.star_payload({'key': key, 'on': True})
    hot = tv.list_payload({'page': 1})
    assert hot['items'][0]['key'] == key
    assert hot['items'][0]['star'] is True
    tv.star_payload({'key': key, 'on': False})
    # 评论多的排前面 ✓
    other = tv.list_payload({'page': 1})['items'][1]['key']
    tv.comment_payload({'key': other, 'text': '第一条'})
    tv.comment_payload({'key': other, 'text': '第二条'})
    ranked = tv.list_payload({'page': 1})
    assert ranked['items'][0]['key'] == other
    assert ranked['items'][0]['comments'] == 2
    # 评论新的在前（详情 / 提交返回都一致 ✓）
    detail = tv.detail_payload({'key': other})
    assert [row['text'] for row in detail['comments']] == ['第二条', '第一条']
    added = tv.comment_payload({'key': other, 'text': '第三条'})
    assert [row['text'] for row in added['comments']][0] == '第三条'


def test_detail_chart_params_and_dataset(tv):
    # 详情页要给前端「可选数据集」+ 当前数据集 ✓
    detail = tv.detail_payload({'key': 'tv:UT_Bot_Alerts'})
    assert detail['symbols'] and 'test' in detail['symbols']
    assert detail['symbol'] == 'test'
    assert tv.available_symbols()[0] == 'test'
    # 换数据集 / 改参数都能出图（参数走 `indicator_catalog.compute` 的覆盖 ✓）
    html = tv.chart_html('tv:UT_Bot_Alerts', 'light',
                         params={'length': 14}, symbol='test')
    assert len(html) > 100_000
    # 不存在的参数也不会炸（指标自己忽略 ✓）
    html2 = tv.chart_html('tv:UT_Bot_Alerts', 'dark',
                          params={'nope': 1}, symbol='test')
    assert len(html2) > 100_000
    assert tv.chart_file('tv:UT_Bot_Alerts', 'light',
                         params={'length': 14}, symbol='test'
                         ).startswith('file://')


# ------------------------------------------------------------- 后端接线
def test_app_commands_and_web_route():
    app = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    for cmd in ('tv_list', 'tv_detail', 'tv_snapshot', 'tv_star',
                'tv_comment', 'tv_chart'):
        assert f"'{cmd}': self._on_{cmd}" in app, cmd
    assert 'def tv_chart_html(' in app
    # 图表命令透传 参数 / 数据集（Qt 壳 + 浏览器壳都要 ✓）
    assert "def tv_chart_html(self, key: str, theme: str = 'light'," in app
    assert 'params=params, symbol=symbol' in app
    web = _read(ROOT / 'minibt' / 'desk' / 'web.py')
    assert "if path == '/tv_chart':" in web
    assert "query.get('params')" in web and "query.get('symbol')" in web


# --------------------------------------------------------------- 前端
def test_frontend_list_page_and_entries():
    page = _read(DESK_TS / 'tv-page.ts')
    for marker in ('export class TvPage', '指标和策略', '_cardHtml',
                   'data-tv-open', 'data-tv-star', 'data-tv-use',
                   'tv_snapshot', 'tv_star', 'data-tv-tab',
                   'onOpen', 'PAGE_SIZE = 24',
                   'desk-tv-card-tag'):
        assert marker in page, marker
    # ★ 列表页不再内嵌详情（简介 / 评论区 / 图表 iframe 都已删除 ✓）
    for gone in ('_detailHtml', 'desk-tv-frame', '评论区', '指标简介',
                 '返回列表', 'data-tv-comment'):
        assert gone not in page, gone
    app = _read(DESK_TS / 'app.ts')
    assert 'openTvPage(): TvPage' in app
    assert "openTvIndicator(key: string, name = '', kind = 'indicator'): void" in app
    assert "onOpen: (key, name, kind) => this.openTvIndicator(" in app
    assert "case 'tv_source':" in app and 'openReadonlySource' in app
    assert "preset: 'tv'" in app
    assert "this.send('local_load', { name: dataset, cell: 0, page: id })" in app
    assert "label: '指标和策略（TradingView 指标库）'" in app
    assert "{ label: '指标和策略', hint: 'TradingView 指标库'" in app
    assert '_showTabMenu' in app and '查看原始码（只读）' in app
    home = _read(DESK_TS / 'home-page.ts')
    assert 'data-nav="tv"' in home and 'onOpenTv' in home
    css = _read(DESK_TS / 'desk.css')
    for selector in ('.desk-tv-grid', '.desk-tv-card', '.desk-tv-card-use',
                     '.desk-tv-card-tag', '.desk-tv-source'):
        assert selector in css, selector
    # 详情页那套（iframe / 简介 / 评论）样式已经删掉 ✓
    for gone in ('.desk-tv-frame', '.desk-tv-comments', '.desk-tv-code'):
        assert gone not in css, gone


def test_thumbnail_cache_version_prevents_double_badge(tv):
    """旧缩略图缓存（烘焙着角标的那批）必须自动失效，否则**双重标注** ✗

    用户 2026-11-03 实测：手动截图（PNG）只有 1 个「指标」角标，
    默认生成的 SVG 却有 2 个 —— 因为磁盘上的旧 SVG 还烘焙着角标，
    新加的 HTML 角标叠在上面。
    """
    svg = tv.thumbnail_svg('tv:SuperTrend', 'light')
    assert f'minibt-thumb:{tv.THUMB_VERSION}' in svg
    assert 'text-anchor="middle"' not in svg        # 不再烘焙角标 ✓
    # 老格式（没有版本标记）→ 当作"没图"，前端会请求重新生成 ✓
    legacy = pathlib.Path(tv.CARD_DIR) / 'tv_SuperTrend.svg'
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        '<svg><rect/><text text-anchor="middle">指标</text></svg>',
        encoding='utf-8')
    assert tv._existing_card('tv:SuperTrend', 'light') == ''
    assert tv.snapshot_path('tv:SuperTrend', 'light') == str(legacy)
    assert tv._svg_is_current(str(legacy)) is True
    assert tv._existing_card('tv:SuperTrend', 'light') == str(legacy)


def test_card_tag_is_html_overlay(tv):
    """卡片右上角「指标 / 策略」标记用 **HTML** 画：手动截图（PNG 封面）也有 ✓

    用户 2026-11-03 实测：从卡片打开的图表页截图后回到列表，卡片右上角的
    「指标 / 策略」标记不见了 —— 那个标记原本烘焙在自动生成的 SVG 里，
    截图把封面换成 PNG 之后就没有了 ✗
    """
    page = _read(DESK_TS / 'tv-page.ts')
    assert 'desk-tv-card-tag' in page
    assert 'const tag = item.user' in page
    css = _read(DESK_TS / 'desk.css')
    assert '.desk-tv-card-tag {' in css
    assert 'right: 10px; top: 10px;' in css
    # SVG 里不再烘焙右上角方块（类型挪到页脚，信息不丢 ✓）
    source = _read(ROOT / 'minibt' / 'desk' / 'tv_page.py')
    assert 'tag_width' not in source
    assert '指标' in tv.thumbnail_svg('tv:SuperTrend', 'light')


def test_chart_page_is_full_local_chart():
    """点卡片 = **完整的本地图表**（不裁剪工具栏 ✓ 用户 2026-11-02 第二次要求）"""
    lc = _read(DESK_TS / 'local-chart-page.ts')
    assert "preset?: 'tv';" in lc
    # 不再裁剪工具栏 / 不再强制展开画线导航栏 ✓
    assert 'const keep = new Set<Element>' not in lc
    assert "classList.add('desk-tv-chart')" not in lc
    # 连了行情 → 商品搜索框走在线搜索；否则照旧本地 ✓
    assert "options.preset === 'tv' && options.online?.()" in lc
    assert 'online?: () => boolean;' in lc
    # 源码只读视图（页签右键）还在 ✓
    assert 'openReadonlySource' in lc and 'readOnly: true' in lc

    app = _read(DESK_TS / 'app.ts')
    # 打开页面后：底部面板展开 + 生成/加载持久化脚本 ✓
    assert 'page.openEditor();' in app
    assert "this.send('tv_script', { page: id, key });" in app
    assert "online: () => !!(this.markets.futures || this.markets.stocks)" in app


def test_script_file_is_persistent_personal_indicator(tv, tmp_path, monkeypatch):
    from minibt.desk import personal
    monkeypatch.setattr(personal, 'PERSONAL_ROOT',
                        str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE',
                        str(tmp_path / 'personal.json'))
    data = tv.script_payload({'key': 'tv:UT_Bot_Alerts'})
    assert data['ok'] and data['created'] is True
    text = data['text']
    lines = text.splitlines()
    # ★ 类定义前面就是用户要求的两行 ✓
    assert lines[0] == '# coding: utf-8'
    assert lines[1] == 'from minibt import *'
    assert any(line.startswith('class UT_Bot_Alerts') for line in lines[2:6])
    # 落在 minibt 默认的个人指标目录 ✓
    assert pathlib.Path(data['path']).parent == tmp_path / 'personal'         / 'indicators'
    # 语法能过（header 让它能独立 import ✓）
    import py_compile
    py_compile.compile(data['path'], doraise=True)
    # 第二次打开：**不覆盖**，直接加载磁盘上的版本 ✓
    again = tv.script_payload({'key': 'tv:UT_Bot_Alerts'})
    assert again['created'] is False
    assert again['text'] == text
    # 用户改过内容 → 保留用户的 ✓
    with open(data['path'], 'a', encoding='utf-8') as handle:
        handle.write('# user edit' + chr(10))
    third = tv.script_payload({'key': 'tv:UT_Bot_Alerts'})
    assert '# user edit' in third['text']
    # 未知指标不写文件 ✓
    assert tv.script_payload({'key': 'tv:Nope'})['ok'] is False


def test_local_chart_page_keeps_absolute_layout():
    """★ 本地图表页必须由 `.desk-stack > *` 绝对铺满（2026-11-02 回归 ✓）

    之前给 `.desk-chart-page` 加了 `position: relative`（为了放只读源码浮层），
    它的优先级和 `.desk-stack > *` 相同、又写在后面 → 覆盖了
    `position: absolute; inset: 0`，页面高度变成**内容高度**
    （实测 1253px > 窗口 865px）→ 底部「交易/编辑器」被顶到窗口外
    （要最大化才看得到）、编辑器滚动区也在窗口外（滚不动 ✗）。
    """
    css = _read(DESK_TS / 'desk.css')
    assert '.desk-stack > * { position: absolute; inset: 0; }' in css
    start = css.index('.desk-chart-page {')
    rule = css[start:css.index('}', start)]
    assert 'position' not in rule, rule        # 不能再改定位 ✓
    # 3:1 = 底部面板占页面高度的 1/4 ✓
    lc = _read(DESK_TS / 'local-chart-page.ts')
    assert 'this.dockRatio = 1 / 4;' in lc
    # 代码长了要能滚（编辑器自己的 CSS）✓
    panel = _read(DESK_TS / 'editor-panel.ts')
    assert '.desk-editor-host .cm-scroller { overflow: auto; }' in panel
    assert '.desk-editor-host { flex: 1 1 auto; min-height: 0; overflow: hidden;' in panel


def test_backend_script_command():
    app = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    assert "'tv_script': self._on_tv_script" in app
    assert 'def _on_tv_script(self, payload=None)' in app
    assert "'type': 'editor_file'" in app


def test_close_tab_goes_to_neighbour():
    """关页签 → 跳**后一个**；是最后一个就跳**前一个**（不回首页 ✓）"""
    ts = _read(DESK_TS / 'app.ts')
    body = ts.split('closeTab(id: string): void {', 1)[1][:4000]
    assert 'const order = [...this.tabs.keys()];' in body
    assert 'const neighbour = order[index + 1] || order[index - 1]' in body
    assert 'if (neighbour && neighbour !== HOME_TAB_ID)' in body


def test_back_top_button_is_css_anchored():
    """「回到顶部」圆钮用 CSS `fixed; right/bottom`，不能靠 JS 算 left/top ✓

    用户 2026-11-03 实测：设置里调过**界面缩放**（`ui_zoom ≠ 1`，desk 根节点带
    `transform: scale()`）后，圆钮被切掉一半 —— `position: fixed` 的定位基准是
    那个**被缩放过的根节点**，而 JS 用 `getBoundingClientRect()`（视口坐标）算的
    left/top 会被再缩放一次 ✗（zoom 1.1 实测按钮跑到 1263,781，视口只有 1200×720）。
    """
    page = _read(DESK_TS / 'tv-page.ts')
    body = page.split('private _syncTopButton()', 1)[1][:1500]
    assert 'button.style.left' not in body
    assert 'button.style.top' not in body
    css = _read(DESK_TS / 'desk.css')
    block = css.split('.desk-tv-top {', 1)[1].split('}', 1)[0]
    assert 'position: fixed;' in block
    assert 'right: 22px;' in block and 'bottom: 22px;' in block
    # ★ 箭头用 SVG（20px）+ 40px 圆：文字 `↑` 太小且垂直居中不稳（用户反馈 ✗）
    assert 'width: 40px; height: 40px;' in block
    assert "'<svg viewBox=\"0 0 24 24\" width=\"20\" height=\"20\"" in page
    assert '.desk-tv-top svg { display: block;' in css


def test_backend_source_and_live_commands():
    app = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    assert "'tv_source': self._on_tv_source" in app
    assert "'tv_live': self._on_tv_live" in app
    assert 'def _on_tv_source(self, payload=None)' in app
    assert 'def _on_tv_live(self, payload=None)' in app
    # 在线数据缓存 → 指标按缓存重算（没有 CSV 也能算 ✓）
    assert "live = (getattr(self, '_tv_frames', {}) or {}).get(" in app


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

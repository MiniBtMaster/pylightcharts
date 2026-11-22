"""首页：自选分组管理 + 事件日历（用户需求 2026-11-21）✓

1. 侧栏「自选分组」＋ 左边有『分组管理』按钮 → 打开管理页；
2. 管理页列出所有分组：**最近打开 / 收藏 / 自选**等系统分组不可重命名 / 删除；
   自建分组悬停出现「重命名 / 删除」；
3. 管理页与首页同步（删除 / 新建 / 重命名两边都变）；
4. 管理页里的「＋」与首页「＋」同一个动作；
5. 显示每个分组的标的数量；
6. 中间自选表格右上角「管理」也打开分组管理页；
7. 事件日历用「资讯中心 → 日历」的数据，行格式「时间 事件 前值」，
   只显示**还没发生**的事件、按时间升序、可滚动；
8. 「事件日历 今天」后面有刷新按钮；只在打开首页 / 切回首页 / 点刷新时更新。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding='utf-8')


# ---------------------------------------------------------------- 分组管理
def test_home_has_group_manage_button_left_of_add():
    """侧栏「自选分组」：⚙ 管理按钮在 ＋ **左边** ✓"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    at = source.index('<span>自选分组</span>')
    block = source[at:at + 700]
    assert 'data-group-manage' in block
    assert 'data-group-add' in block
    assert block.index('data-group-manage') < block.index('data-group-add')


def test_middle_watch_table_manage_opens_group_manager():
    """中间自选表格右上角「管理」→ 打开**分组管理**页 ✓"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    assert 'data-act="manage"' in source
    at = source.index("if (name === 'manage')") if "if (name === 'manage')" in source \
        else source.index("name === 'manage'")
    block = source[at:at + 400]
    assert 'openGroupManager()' in block


def test_group_manager_system_groups_have_no_icons():
    """★ 系统分组（含「收藏」）**不能有删除按钮** ✓（用户 2026-11-21）"""
    source = _read('jslib', 'src', 'desk', 'watch-groups.ts')
    assert "if (!row.system)" in source
    # 「收藏 / 最近打开」也不能有 `清空`（那本质就是删除按钮）
    assert '清空收藏' not in source and '清空最近打开' not in source
    assert 'CLEAR_ICON' not in source
    # 只有 `if (!row.system)` 分支里才创建按钮 ✓
    at = source.index("if (!row.system) {")
    block = source[at:at + 1400]
    assert '重命名这个分组' in block and '删除这个分组' in block
    assert '清空收藏' not in source


def test_user_groups_come_first():
    """用户新建的分组优先排在前面（首页侧栏 + 管理页同一顺序 ✓）"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    assert 'custom.concat(defaults)' in source or 'custom as HomeGroup[]' in source


def test_four_filter_groups_removed():
    """★ 「黑色系 / 有色金属 / 股指期货 / 能源化工」彻底删除 ✓"""
    store = _read('jslib', 'src', 'desk', 'watch-store.ts')
    home = _read('jslib', 'src', 'desk', 'home-page.ts')
    for gid in ('black', 'metal', 'index', 'energy'):
        assert f"id: '{gid}'" not in store, gid
        assert f"id: '{gid}'" not in home, gid
    # BUILTIN_GROUPS 只剩「自选」
    at = store.index('export const BUILTIN_GROUPS')
    block = store[at:store.index('];', at)]
    assert block.count('id:') == 1


def test_group_manager_lists_all_groups_with_counts():
    """管理页：列出全部分组 + 标的数量；系统分组不可改名 / 删除 ✓"""
    source = _read('jslib', 'src', 'desk', 'watch-groups.ts')
    assert 'export class WatchGroupManager' in source
    assert 'system: boolean' in source
    assert '个标的' in source
    assert '重命名这个分组' in source and '删除这个分组' in source
    assert "if (!row.system)" in source          # 系统分组没图标 ✓
    # 悬停才出现（CSS）
    css = _read('jslib', 'src', 'desk', 'desk.css')
    assert '.desk-wg-list .desk-lg-item:hover .desk-wg-icon' in css


def test_group_manager_create_rename_delete_wired():
    """新建 / 重命名 / 删除 → 与首页同步（走 watch-store + refreshWatch）✓"""
    home = _read('jslib', 'src', 'desk', 'home-page.ts')
    assert 'openGroupManager()' in home
    assert 'storeRenameGroup' in home and 'storeDeleteGroup' in home
    assert 'refreshWatch()' in home
    store = _read('jslib', 'src', 'desk', 'watch-store.ts')
    assert 'export function renameGroup' in store
    assert 'export function deleteGroup' in store


def test_group_manager_refreshes_on_store_change():
    """管理页开着时，存储变更（别处增删）也要刷新 ✓"""
    home = _read('jslib', 'src', 'desk', 'home-page.ts')
    at = home.index('window.addEventListener(WATCH_EVENT')
    assert 'groupManager?.refresh()' in home[at:at + 260]
    assert 'groupManager?.refresh()' in home[home.index('refreshWatch(): void'):][:400]


# ---------------------------------------------------------------- 事件日历
def test_home_calendar_service_shows_everything_sorted():
    """★ 首页事件日历 = 资讯中心日历**全量**数据（不过滤），按时间升序 ✓"""
    from minibt.desk.info import service  # noqa: PLC0415

    data = service.home_calendar()
    assert data['ok'] is True
    items = data['items']
    times = [item['time'] for item in items]
    assert times == sorted(times)
    assert data['day'], data                   # 标题用的日期（如 2026-11-23 ✓）
    for item in items:
        assert 'previous' in item                # 「前值」列 ✓
        assert item['text']


def test_home_calendar_rows_layout():
    """前端：行 = 时间 / 事件 / 前值，可滚动，刷新按钮在标题后面 ✓"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    block = source[source.index('desk-home-calendar'):][:2000]
    assert 'data-calendar-refresh' in block
    assert 'data-open-info' in block            # 「资讯中心」在刷新左边 ✓
    assert block.index('data-open-info') < block.index('data-calendar-refresh')
    assert '时间' in block and '前值' in block
    assert '<div class="desk-home-calendar-list">' in block
    # 标题不写"今天"，用后端给的日期 ✓
    assert '今天' not in block
    assert 'this._calendarTitle()' in block
    # 全量渲染（不 slice ✓）
    assert 'this.events.map(' in block
    css = _read('jslib', 'src', 'desk', 'desk.css')
    assert '.desk-home-calendar-list { max-height: 126px; overflow-y: auto;' in css


def test_home_calendar_refresh_hooks():
    """只在打开 / 切回首页、点刷新时更新 ✓"""
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert "case 'home_calendar':" in app
    # activate 里：切到首页 → 刷新一次
    at = app.index('activate(id: string)')
    assert "this.send('home_calendar', {})" in app[at:]
    # 点刷新按钮 → refresh: true
    home = _read('jslib', 'src', 'desk', 'home-page.ts')
    at2 = home.index('data-calendar-refresh')
    assert "home_calendar', { refresh: true }" in home[at2:at2 + 900]

    backend = _read('minibt', 'desk', 'app.py')
    assert "'home_calendar': self._on_home_calendar" in backend
    at3 = backend.index('def _on_home_calendar')
    body = backend[at3:at3 + 1500]
    assert "refresh = bool(payload.get('refresh'))" in body
    assert '_info.refresh_calendar' in body


def test_watch_row_has_delete_button_right_of_star():
    """自选行「收藏」右侧有「删除」图标 → 从**当前分组**移除 ✓"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    at = source.index('data-fav="${esc(row.symbol)}"')
    block = source[at:at + 700]
    assert 'data-watch-remove' in block, block
    # 行内顺序：收藏按钮在前，删除按钮在后 ✓（都在同一行模板里）
    row = source[source.index('<div class="desk-home-tr desk-home-row'):]
    row = row[:row.index('</div>`')]
    assert row.index('data-fav=') < row.index('data-watch-remove')
    assert '_removeFromCurrentGroup' in source
    css = _read('jslib', 'src', 'desk', 'desk.css')
    assert '.desk-home-del' in css
    # 13 列（收藏 + 删除各占一列，否则按钮会挤歪表格 ✗）
    assert '1.15fr 24px 24px;' in css


def test_main_groups_have_no_delete_and_manage_disabled():
    """主力行情（4 个交易所）：管理按钮不可用 + 行内没有删除按钮 ✓"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    at = source.index("const fixed = group.kind === 'main';")
    block = source[at:at + 300]
    assert 'manage.disabled = fixed' in block
    at2 = source.index("${group.kind === 'main' ? '' : `<button class=\"desk-home-del\"")
    assert 'data-watch-remove' in source[at2:at2 + 300]


def test_remove_from_group_store():
    """watch-store：按分组移除标的（收藏 / 自建 / 内置 pins 三条路 ✓）"""
    store = _read('jslib', 'src', 'desk', 'watch-store.ts')
    at = store.index('export function removeFromGroup')
    body = store[at:at + 1400]
    assert "group.kind === 'favorites'" in body
    assert "group.kind === 'custom'" in body
    assert 'pins()' in body


def test_group_manager_foot_buttons_single_line():
    """「＋ 新建分组」按钮不能被压成两行（用户 2026-11-22 ✗）

    `.desk-lg-btn` 默认 `flex: 1` → 和管理页提示文字抢宽度 → 文字换行；
    现在改成按内容撑开 + `white-space: nowrap` ✓
    """
    css = _read('jslib', 'src', 'desk', 'desk.css')
    at = css.index('.desk-wg .desk-lg-foot > .desk-lg-btn')
    block = css[at:at + 200]
    assert 'flex: 0 0 auto' in block
    assert 'white-space: nowrap' in block


def test_recent_list_routes_local_vs_realtime():
    """★ 「最近打开」双击 / 单击要**分开**：本地数据 → 本地图表，其它 → 实时图表 ✓

    以前双击只看 `[data-watch-row]` → 最近打开里的**本地 CSV** 也被当成实时合约
    打开（提示"切换合约失败" / 跑进实时图表 ✗ 用户 2026-11-22）。
    """
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    # ★ 2026-11-22 用户要求：加入「最近打开」时**就记来源**，打开时只看来源
    at = source.index('private _recentTarget(')
    block = source[at:at + 500]
    assert "source === 'local'" in block
    assert "source === 'chart'" in block
    # 写入时按 kind 定来源：local / replay → 本地 ✓
    rec = source[source.index('recordRecent(symbol: string'):][:1200]
    assert "const source: 'local' | 'chart' =" in rec
    assert "(kind === 'local' || kind === 'replay') ? 'local' : 'chart'" in rec
    assert '{ symbol, name, kind, source, at: Date.now() }' in rec
    # 存储键升级（旧数据没有 source → 不再复用 ✓）
    assert "minibt.desk.home.recent.v2" in source
    assert 'RECENT_KEY_V1' in source
    # 双击最近打开 → 走统一逻辑（不再是"全实时"）
    dbl = source[source.index("addEventListener('dblclick'"):][:900]
    assert "closest<HTMLElement>('[data-recent-row]')" in dbl
    assert '_openRecent(' in dbl
    # 单击最近打开也走统一逻辑 ✓
    click = source[source.index("data-open-symbol"):][:2500]
    assert 'open.dataset.recentRow' in click
    assert '_openRecent(' in click
    # 行上带类型标记 ✓
    assert 'data-recent-row="1"' in source
    assert 'data-recent-kind=' in source


def test_recent_contract_code_guard():
    """★ 来源记错也能纠正：**不是合约代码** → 一定走本地图表 ✓

    事故现场：`test`（本地 CSV）被记成 `source='chart'` → 双击发 `open_chart`
    → 后端报「打开图表：test 不是合法合约代码」✗（用户 2026-11-22）
    实时图表只能打开带交易所前缀的合约，所以用"合法性"兜底是安全的。
    """
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    at = source.index('private _isContractCode(')
    block = source[at:at + 500]
    assert r'/^KQ\./' in block
    assert r'[A-Za-z]{2,8}\.' in block
    # 判定顺序：source 是 local → 本地；否则先看是不是合约代码 ✓
    at2 = source.index('private _recentTarget(')
    order = source[at2:at2 + 700]
    assert order.index("source === 'local'") < order.index('_isContractCode')
    # 打开时自动纠正记错的来源 ✓
    at3 = source.index('private _openRecent(')
    heal = source[at3:at3 + 900]
    assert 'stored.source = target' in heal
    # 本地图表周期按钮是**禁用**的（周期由 CSV 决定 ✓）
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    assert 'cycleButton.disabled = true;' in page


def test_local_chart_cycle_button_disabled():
    """本地图表：**周期不可切换**（由 CSV 的 duration 决定 ✓）

    截图里 `test` 页面的周期菜单能打开 → 说明那是**实时图表**页（路由错的
    症状）。修好路由后应该落到本地图表，周期按钮就是禁用的。
    """
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    at = page.index('const cycleButton = document.createElement')
    block = page[at:at + 800]
    assert 'cycleButton.disabled = true;' in block
    assert 'desk-tool-disabled' in block
    assert '周期由数据决定（不可切换）' in block


def test_openchart_routes_local_datasets():
    """★ `openChart()` 命中**本地数据集名字** → 自动改走本地图表 ✓

    事故：首页双击 `pp2609_60`（本地 CSV）→ `openChart()` 新建了一个**实时
    图表**标签 `pp2609_60`，后端报「不是合法合约代码」✗（用户 2026-11-22）
    """
    app = _read('jslib', 'src', 'desk', 'app.ts')
    # 后端 `local_data` 补丁 → 记下数据集名字
    at = app.index("case 'local_data': {")
    block = app[at:at + 900]
    assert 'this.localDataNames = new Set(' in block
    # openChart 入口拦截 ✓
    at2 = app.index('openChart(symbol: string')
    head = app[at2:at2 + 700]
    assert 'this.localDataNames.has(symbol)' in head
    assert 'return this.openLocalChart(symbol);' in head


def test_home_all_entry_points_use_unified_open():
    """首页所有"打开名字"的入口都走 `_openSymbol`（本地 → 本地图表 ✓）"""
    source = _read('jslib', 'src', 'desk', 'home-page.ts')
    assert 'private _openSymbol(' in source
    # 双击自选行 / 单击普通行 / 最近打开 都走统一入口
    dbl = source[source.index("addEventListener('dblclick'"):][:1200]
    assert '_openSymbol(' in dbl
    assert 'this.options.onOpenChart(' not in dbl
    at = source.index('private _openRecent(')
    assert '_openSymbol(' in source[at:at + 900] or '_recentTarget(' in source[at:at + 900]

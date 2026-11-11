"""图表右键菜单 / 原生右键禁用 / 截图落盘 / 关窗后不再 runJavaScript

用户 2026-11-02 要求：

1. **策略回测 / 参数优化页**的「合约图表」「回测结果」图表右键要有菜单：
   `全部K线` / `最新K线（300根）` / `画线` / `清除画线` / `截图`；
   其它控件（工具栏 / 指标卡 / 表格）**禁用原生右键菜单**；
2. 主界面**顶栏**禁用原生右键；
3. 本地图表 / 实时图表：**工具栏**、**左侧画线导航条**、**右侧二级报价**禁用原生右键；
4. 关 desk 时终端刷 `runJavaScript: disabled in Discarded state` → 关窗后
   不再往已 discard 的页面发脚本（顺带把截图改成后端落盘 ✓）。
"""
from __future__ import annotations

import base64
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK_TS = ROOT / 'jslib' / 'src' / 'desk'


def _read(path) -> str:
    target = pathlib.Path(path)
    if not target.exists():
        target = DESK_TS / path
    return target.read_text(encoding='utf-8')


# ------------------------------------------------- 图表 iframe 驱动（子页面）
def test_driver_has_chart_menu_commands():
    from minibt.desk import miniqt_backtest_chart as mod

    js = mod.DESK_DRIVER_JS
    # 菜单动作 → 驱动命令 ✓
    for cmd in ("case 'fitAll':", "case 'visibleLast':", "case 'screenshot':"):
        assert cmd in js, cmd
    assert 'function showLast(h, bars)' in js
    assert 'setVisibleLogicalRange' in js
    assert 'takeScreenshot' in js
    # 右键：禁止原生菜单 + 通知父页面弹自己的菜单 ✓
    assert 'function onContextMenu(event)' in js
    assert "parent.postMessage({" in js and "__deskSL: 'chartMenu'" in js
    assert "window.addEventListener('contextmenu', onContextMenu, true)" in js
    # 截图不在 iframe 里直接下载（Qt 不处理下载）→ 交回父页面 ✓
    assert "parent.postMessage({ __deskSL: 'screenshotData'" in js


def test_driver_dismisses_menu_on_left_click_or_wheel():
    """图内左键 / 滚轮 → 让父页面收起右键菜单（否则菜单一直挂着 ✗）"""
    from minibt.desk import miniqt_backtest_chart as mod

    js = mod.DESK_DRIVER_JS
    assert 'function notifyMenuClose()' in js
    assert "__deskSL: 'chartMenuClose'" in js
    # 左键 / 中键才收起；右键交给 contextmenu（会重开菜单 ✓）
    assert "if (event && event.button === 2) return;" in js
    assert "window.addEventListener('pointerdown', onChartPointerDown, true);" in js
    # 滚轮也收起（缩放时菜单别挡着 ✓）
    assert "window.addEventListener('wheel', notifyMenuClose" in js


# ------------------------------------------------------ 父页面：菜单 + 事件
def test_lab_page_shows_the_chart_menu():
    page = _read(DESK_TS / 'strategy-lab-page.ts')
    assert "import { closeMenu, showMenu } from './menu';" in page
    assert 'private _showChartMenu(' in page
    block = page.split('private _showChartMenu(', 1)[1]
    block = block.split('/** 进回放时要放出的根数', 1)[0]
    for label in ('全部K线', '最新K线（300根）', '画线', '清除画线', '截图'):
        assert label in block, label
    # 菜单动作都发给 iframe 里的驱动 ✓
    assert "send('fitAll')" in block
    assert "send('visibleLast', { bars: 300 })" in block
    assert "send('toolbox', { show: true })" in block
    assert "send('clearDrawings')" in block
    assert "send('screenshot')" in block
    # iframe 消息 → 弹菜单 / 截图回传 ✓
    assert "data.__deskSL === 'chartMenu'" in page
    assert "data.__deskSL === 'screenshotData'" in page
    assert "this.options.onCommand('screenshot', { dataUrl: url });" in page


def test_lab_page_closes_menu_on_frame_click():
    page = _read(DESK_TS / 'strategy-lab-page.ts')
    assert "import { closeMenu, showMenu } from './menu';" in page
    assert "data.__deskSL === 'chartMenuClose'" in page
    block = page.split("data.__deskSL === 'chartMenuClose'", 1)[1]
    block = block.split('return;', 1)[0]
    assert 'closeMenu();' in block
    # 弹菜单时先关掉上一个（showMenu 内部也会关，但入口显式一点 ✓）
    show = page.split('private _showChartMenu(', 1)[1]
    assert "showMenu(anchorX, anchorY," in show


def test_lab_page_disables_native_menu_except_charts_and_inputs():
    page = _read(DESK_TS / 'strategy-lab-page.ts')
    block = page.split("this.element.addEventListener('contextmenu'", 1)[1]
    block = block.split('});', 1)[0]
    assert 'event.preventDefault()' in block
    # 输入框 / 下拉 / 可编辑区保留原生菜单 ✓
    assert "input, textarea, select" in block
    assert '.cm-editor' in block


# ---------------------------------------------- 顶栏 / 工具栏 / 导航条 / 报价
def test_topbar_toolbars_rail_book_block_native_menu():
    app = _read(DESK_TS / 'app.ts')
    assert 'private _blockNativeMenus(): void {' in app
    block = app.split('private _blockNativeMenus(): void {', 1)[1]
    block = block.split('private _showEditorHelp', 1)[0]
    for selector in ('.desk-topbar', '.desk-chart-toolbar',
                     '.desk-draw-rail', '.desk-book',
                     '.desk-strategy-lab'):
        assert f"'{selector}'" in block, selector
    assert "document.addEventListener('contextmenu'" in block
    assert 'event.preventDefault()' in block
    # 编辑器 / 输入框保留 ✓
    assert '.desk-editor-body' in block and ".cm-editor" in block
    # 装上（构建顶栏时调一次 ✓）
    assert 'this._blockNativeMenus();' in app


# --------------------------------------------------------- 截图：后端落盘
@pytest.fixture()
def desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    monkeypatch.setattr(appmod, 'EXPORTS_DIR', str(tmp_path / 'exports'))
    monkeypatch.setattr(user_prefs, 'record_export',
                        lambda *a, **k: [])
    d = appmod.Desk(offline=True)
    d.sent = []
    d.sender = d.sent.append
    d._booted = True
    d.log_to_stdout = False
    d.log_to_ui = False
    return d, pathlib.Path(tmp_path / 'exports')


def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def test_screenshot_command_writes_png(desk):
    d, folder = desk
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 64
    url = 'data:image/png;base64,' + base64.b64encode(png).decode()
    d._on_screenshot({'dataUrl': url, 'name': 'chart.png'})
    files = list(folder.glob('*.png'))
    assert files, '截图没落盘'
    assert files[0].read_bytes() == png
    patches = _patches(d)
    assert any(item.get('type') == 'toast'
               and '已保存截图' in str(item.get('text') or '')
               for item in patches)
    # 有「打开文件 / 打开文件夹」两个按钮 ✓
    toast = [item for item in patches if item.get('type') == 'toast'][-1]
    labels = [action.get('label') for action in toast.get('actions') or []]
    assert labels == ['打开文件', '打开文件夹']


def test_screenshot_command_rejects_empty_data(desk):
    d, folder = desk
    d._on_screenshot({'dataUrl': ''})
    assert not list(folder.glob('*.png')) if folder.exists() else True
    patches = _patches(d)
    assert any('截图失败' in str(item.get('text') or '') for item in patches)


def test_screenshot_command_is_registered():
    app = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    assert "'screenshot': self._on_screenshot" in app
    assert 'def _on_screenshot(' in app
    assert 'def _write_export_binary(' in app


# ------------------------------------------------ 关窗后不再 runJavaScript
def test_optimization_rows_use_one_based_trial():
    """`trial` / `number` 统一成 **1 基**（图上「Trial 26」= 表格 `trial` 26 ✓）

    以前引擎给的是 0 基（表格 0..29），图上 tooltip 显示 N+1 → 差 1，
    用户找 `Trial 26` 在表格里找不到（那行写着 25 ✗，2026-11-02 实测）。
    """
    from minibt.desk.strategy_lab import _normalize_opt_rows

    grid_rows = _normalize_opt_rows(
        [{'trial': 0, 'sharpe': 0.1}, {'trial': 25, 'sharpe': 0.2}],
        ['sharpe'], None)
    assert [row['trial'] for row in grid_rows] == [1, 26]
    assert [row['number'] for row in grid_rows] == [1, 26]
    # optuna CSV 的 `number` 也是 0 基 → 同样 +1 ✓
    csv_rows = _normalize_opt_rows(
        [{'number': 0, 'value': 0.3}, {'number': 7, 'value': 0.4}],
        ['sharpe'], None)
    assert [row['number'] for row in csv_rows] == [1, 8]
    # 两列都没有 → 行号（1 基）
    assert _normalize_opt_rows([{'sharpe': 1.0}], ['sharpe'],
                               None)[0]['number'] == 1
    # 前端 tooltip 直接用行里的值（不再 +1 ✓）
    page = _read(DESK_TS / 'strategy-lab-page.ts')
    block = page.split('private _trialLabel(', 1)[1]
    block = block.split('private _equityKey(', 1)[0]
    assert 'return String(Math.round(value));' in block
    assert 'Math.round(value) + 1' not in block


def test_js_alive_helper_and_close_guard():
    QtWebEngineCore = pytest.importorskip('PyQt6.QtWebEngineCore')
    QPage = QtWebEngineCore.QWebEnginePage
    from minibt.desk import app_window as win

    class _Page:
        def __init__(self, state):
            self._state = state

        def lifecycleState(self):            # noqa: N802
            return self._state

    assert win._js_alive(_Page(QPage.LifecycleState.Active)) is True
    assert win._js_alive(_Page(QPage.LifecycleState.Discarded)) is False
    assert win._js_alive(None) is False
    # 没有 lifecycleState 的对象不炸（老 Qt / 假页面 ✓）
    assert win._js_alive(object()) is True

    source = _read(ROOT / 'minibt' / 'desk' / 'app_window.py')
    assert 'def _install_js_guard(' in source
    assert 'def _guard_script(' in source
    assert '_js_alive = True' in source
    # close() 里先标记不可用 + 停发件箱定时器（关窗后不再推脚本 ✓）
    close_block = source.split('    def close(self) -> None:', 1)[1]
    close_block = close_block.split('    def ', 1)[0]
    assert 'self._js_alive = False' in close_block
    assert '_outbox_timer' in close_block


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))


# ------------------- 右键补工具栏入口（v1.3.7-60）
def test_chart_context_menu_has_toolbar_entries():
    """右键要能用：更多指标 / 模板 / 策略管理 / 保存当前布局（用户 2026-11-08）"""
    menu = _read('chart-context-menu.ts')
    for label in ("'更多指标…'", "'模板'", "'策略管理…'", "'保存当前布局…'"):
        assert label in menu, label
    for hook in ('onMoreIndicators', 'onTemplates', 'onStrategyManage',
                 'onSaveLayout'):
        assert f'{hook}?: () => void;' in menu, hook
    # 保存当前布局紧跟在「收藏布局」后面（已保存的布局下面 ✓）
    favorite = menu.index("label: '收藏布局'")
    save_layout = menu.index("label: '保存当前布局…'")
    assert save_layout > favorite
    # 两个图表页都要接上（实时 + 本地）
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(name)
        assert 'onMoreIndicators:' in page, name
        assert 'onTemplates: () => this.openTemplatePicker(),' in page, name
        assert "onStrategyManage: () => this.options.onCommand?.(" in page, name
        assert 'onSaveLayout: () => this.openSaveLayout(),' in page, name
    # 策略管理走和编辑器「策略管理」按钮同一条命令 ✓
    editor = _read('editor-panel.ts')
    assert "this.options.onCommand('strategy_manage', {});" in editor

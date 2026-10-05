"""miniqt 左侧导航里的 qtvscode 页面（VS Code Web 工作台）。

这些断言都是**源码/行为级**的，不启动 GUI：

* ``main_window.py`` 必须把页面挂进左侧导航，并在关闭时回收 Node 子进程；
* 页面必须**懒启动**（``showEvent`` 里才起服务），否则 miniqt 启动会多花几秒、
  多占几百 MB；
* 仓库根目录里有个同名 ``qtvscode/`` 文件夹，会让 ``import qtvscode`` 拿到
  "命名空间包"（``unknown location``），所以页面要先把内层包的父目录塞进
  ``sys.path``；这条用子进程验证，避免污染测试进程的 ``sys.modules``；
* qtvscode 的 Qt 绑定必须**跟随宿主**（miniqt 是 PyQt6，而 qtvscode 默认偏向
  PySide6；混用两套绑定会在跨绑定传 QWidget 时炸）；
* 主动 ``stop()`` 不能上报成"启动失败"（terminate/kill 会让 QProcess 报
  ``Crashed``，宿主会因此弹一个莫名其妙的错误提示）。

    pytest tests/test_miniqt_qtvscode.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MAIN_WINDOW = REPO / 'miniqt' / 'app' / 'view' / 'main_window.py'
PAGE = REPO / 'miniqt' / 'app' / 'view' / 'qtvscode_interface.py'
WIDGET = REPO / 'qtvscode' / 'qtvscode' / 'widget.py'
SERVER = REPO / 'qtvscode' / 'qtvscode' / 'server.py'
QTCOMPAT = REPO / 'qtvscode' / 'qtvscode' / 'qtcompat.py'

pytestmark = pytest.mark.skipif(
    not PAGE.exists(), reason='需要仓库里的 miniqt 源码')


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding='utf-8')


def test_navigation_has_the_qtvscode_page():
    """左侧导航要有 qtvscode 一项，并且用的是 DEVELOPER_TOOLS 图标。"""
    source = _read(MAIN_WINDOW)
    assert 'from .qtvscode_interface import' in source
    assert 'NavContextMenuFilter' in source
    assert 'QtvscodeInterface' in source
    assert 'self.qtvscodeInterface = QtvscodeInterface(self)' in source
    assert 'self.addSubInterface(self.qtvscodeInterface,' in source
    assert 'FIF.DEVELOPER_TOOLS' in source


def test_main_window_recycles_the_editor_on_close():
    """miniqt 退出时要停掉 Node 服务，否则留下几百 MB 的孤儿进程。"""
    source = _read(MAIN_WINDOW)
    close_event = source.split('def closeEvent(self, e)', 1)[-1]
    assert 'qtvscodeInterface' in close_event
    assert 'stop_editor()' in close_event


def test_the_page_starts_the_server_lazily():
    """服务只在第一次显示页面时启动（__init__ 里不能有 start_editor）。"""
    source = _read(PAGE)
    assert 'def showEvent(self, event):' in source
    assert 'QTimer.singleShot(0, self.start_editor)' in source
    init_body = source.split('def __init__(self, parent=None):', 1)[1]
    init_body = init_body.split('\n    def ', 1)[0]
    assert 'start_editor(' not in init_body
    assert 'QtVscodeWidget(' not in init_body


def test_the_page_has_no_toolbar():
    """顶栏按需求去掉了：整个页面区域都留给编辑器。

    重载入口搬到左侧导航图标的右键菜单里，页面自己不再放按钮。
    """
    source = _read(PAGE)
    for gone in ('TransparentToolButton', 'CaptionLabel', 'statusLabel',
                 'reloadButton', 'browserButton', 'folderButton',
                 'QHBoxLayout'):
        assert gone not in source, f'页面里还留着顶栏元素: {gone}'


def test_nav_right_click_menu_has_exactly_one_action():
    """导航图标右键 → 菜单里只有「重载编辑器页面」一项。"""
    import ast

    source = _read(MAIN_WINDOW)
    assert 'self.show_qtvscode_menu' in source
    assert 'installEventFilter(' in source

    tree = ast.parse(source)
    menu_function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == 'show_qtvscode_menu')
    body = ast.unparse(menu_function)
    assert 'menu.addAction(action)' in body
    assert body.count('menu.addAction(') == 1
    assert 'Action(FluentIcon.SYNC' in body
    assert '重载编辑器页面' in body
    assert ('action.triggered.connect('
            'self.qtvscodeInterface.reload)') in body
    assert 'menu.exec(global_pos)' in body


def test_right_click_does_not_switch_the_page():
    """用事件过滤器搞定两件事：右键不切页 + 右键菜单能弹到。

    qfluentwidgets 的 ``NavigationWidget.mouseReleaseEvent`` 对任何鼠标键都会
    发 ``clicked``；导航项内部又还有一个 ``itemWidget``（真正接鼠标的那层），
    所以过滤器要父子两层都装。用真实事件对象验证过滤逻辑
    （``QMouseEvent`` / ``QContextMenuEvent`` 都不需要 QApplication）。
    """
    from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
    from PyQt6.QtGui import QContextMenuEvent, QMouseEvent

    module = _load_page_module()
    calls = []
    guard = module.NavContextMenuFilter(lambda pos: calls.append(pos))
    watched = QObject()
    no_modifier = Qt.KeyboardModifier.NoModifier

    def click(kind, button):
        point = QPointF(1.0, 1.0)
        return QMouseEvent(kind, point, point, button, button, no_modifier)

    press = QEvent.Type.MouseButtonPress
    release = QEvent.Type.MouseButtonRelease
    right = Qt.MouseButton.RightButton
    left = Qt.MouseButton.LeftButton

    assert guard.eventFilter(watched, click(press, right)) is True
    assert guard.eventFilter(watched, click(release, right)) is True
    assert guard.eventFilter(watched, click(press, left)) is False
    assert guard.eventFilter(watched, click(release, left)) is False

    menu_event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                                   QPoint(3, 4), QPoint(30, 40))
    assert guard.eventFilter(watched, menu_event) is True
    assert [pos.x() for pos in calls] == [30]
    assert [pos.y() for pos in calls] == [40]
    # 其它事件必须放行
    assert guard.eventFilter(watched, QEvent(QEvent.Type.Enter)) is False


def test_the_nav_filter_is_installed_on_both_layers():
    """导航项本身和它的 itemWidget 都要装过滤器（鼠标事件落在后者）。"""
    source = _read(MAIN_WINDOW)
    block = source.split('_qtvscode_menu_filter = ', 1)[1]
    block = block.split(chr(10) + chr(10), 1)[0]
    assert 'NavContextMenuFilter(' in block
    assert "getattr(qtvscode_item, 'itemWidget', None)" in block
    assert block.count('installEventFilter(') == 1


def test_the_page_has_a_unique_route_object_name():
    """导航页的 objectName 是路由键，写错了 FluentWindow 会跳转失败。"""
    assert "setObjectName('qtvscodeInterface')" in _read(PAGE)


def test_reload_starts_a_never_started_editor():
    """从右键菜单重载时页面可能还没启动过 —— reload 要负责把它拉起来。"""
    source = _read(PAGE)
    reload_body = source.split('def reload(self):', 1)[1]
    reload_body = reload_body.split(chr(10) + '    def ', 1)[0]
    assert 'if self._editor is None:' in reload_body
    assert 'self.start_editor()' in reload_body
    assert 'self._editor.view.reload()' in reload_body


def test_default_workspace_prefers_tutorials(monkeypatch):
    """默认工作区优先 tutorials（策略脚本目录），且必须是真实存在的目录。"""
    monkeypatch.delenv('MINIQT_QTVSCODE_WORKSPACE', raising=False)
    module = _load_page_module()
    workspace = module.default_workspace()
    assert os.path.isdir(workspace)
    assert pathlib.Path(workspace).is_relative_to(REPO)


def test_default_workspace_honours_the_environment(tmp_path, monkeypatch):
    """MINIQT_QTVSCODE_WORKSPACE 指到哪就用哪。"""
    monkeypatch.setenv('MINIQT_QTVSCODE_WORKSPACE', str(tmp_path))
    module = _load_page_module()
    assert module.default_workspace() == str(tmp_path)

    monkeypatch.setenv('MINIQT_QTVSCODE_WORKSPACE', str(tmp_path / 'missing'))
    assert module.default_workspace() != str(tmp_path / 'missing')


def _load_page_module():
    """导入页面模块的函数部分（只用到纯 Python 工具函数，不建 QWidget）。"""
    pytest.importorskip('PyQt6')
    sys.path.insert(0, str(REPO))
    try:
        from miniqt.app.view import qtvscode_interface
    finally:
        sys.path.remove(str(REPO))
    return qtvscode_interface


BACKTEST_TAB = REPO / 'miniqt' / 'app' / 'windows' / 'backtest_result_tab.py'


def test_page_registers_the_backtest_bridge_method():
    """编辑器 Run ▾ →「程序内回测」走 bridge 的 ``minibtBacktest`` 方法。"""
    source = _read(PAGE)
    assert "bridge.register('minibtBacktest', self._backtest)" in source
    assert 'backtestRequested = pyqtSignal(str)' in source
    # 必须**立刻**返回：等一次完整回测会让扩展侧 RPC 超时
    body = source.split('def _backtest(self, params: dict) -> dict:', 1)[1]
    body = body.split(chr(10) + '    def ', 1)[0]
    assert 'self.backtestRequested.emit(path)' in body
    assert "'started': True" in body


def test_new_backtest_tab_is_started():
    """回归：新建结果标签页时必须**真的发起回测**。

    之前只 ``addTab`` 没 ``start()``，标签页开出来是空的（用户报过“没有数据”）。
    """
    import ast

    tree = ast.parse(_read(MAIN_WINDOW))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'open_backtest_result_tab')
    body = ast.unparse(function)
    assert 'self.titleBar.addTab(tab)' in body
    assert 'tab.start()' in body
    # 同文件复用分支也要能重跑 + 全局单实例守卫
    assert body.count('.start()') >= 2
    assert 'isRunning' in body


def test_main_window_waits_for_backtests_on_exit():
    """退出前要 ``stop_and_wait``：QThread 还在跑时被销毁会直接崩。"""
    source = _read(MAIN_WINDOW)
    assert "getattr(widget, 'stop_and_wait', None)" in source


def test_backtest_tab_logs_to_a_file():
    """minibt 会劫持 stdout，诊断必须写文件（否则什么都看不到）。"""
    source = _read(BACKTEST_TAB)
    assert "'backtest.log'" in source
    assert 'open(LOG_PATH' in source
    assert 'sys.__stderr__' in source
    assert '标签页创建' in source and '启动回测线程' in source
    assert '回测完成 instances=' in source


def test_backtest_tab_embeds_a_pylightcharts_chart():
    """回测页只嵌一张 pylightcharts 图（K 线 + 策略指标），不再套结果面板。

    嵌入方式与主图表窗口/图表页一致：``ci.get_chart_class()`` 建图 →
    ``get_webview()`` 加进布局；数据里 ``time`` 必须 datetime64；
    而且**先把视图挂上去、延后一拍再 set**（页面没跑起来就送数据，
    pylightcharts 的批量脚本会全丢 —— 导航页能出图就是因为它建图时页面已可见）。
    """
    source = _read(BACKTEST_TAB)
    assert '_BacktestWorker' in source               # 回测仍在后台线程跑
    assert 'get_chart_class' in source
    assert 'get_webview()' in source
    assert 'strategy_candles' in source
    assert 'extract_minibt_indicators' in source      # 策略真指标
    assert 'QTimer.singleShot' in source              # 延后送数据
    assert 'self.symbol = ' in source                 # CustomTitleBar 当标签名


def test_backtest_tab_refuses_to_close_while_running():
    """回测进行中不让关（Python 线程没法安全强杀）。"""
    source = _read(BACKTEST_TAB)
    body = source.split('def closeEvent(self, event):', 1)[1]
    assert 'if self.isRunning():' in body
    assert 'event.ignore()' in body
    assert 'stop_and_wait' in source


def test_repo_layout_would_shadow_the_package_without_the_helper():
    """复现坑：仓库根在 sys.path 里时 ``import qtvscode`` 会拿到空壳。"""
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(REPO)!r})
        import qtvscode
        print('HAS_WIDGET', hasattr(qtvscode, 'QtVscodeWidget'))
        print('LOCATION', getattr(qtvscode, '__file__', None))
    """)
    result = _run(script)
    assert 'HAS_WIDGET False' in result.stdout


def test_ensure_qtvscode_importable_fixes_the_shadowing():
    """页面里的 ensure_qtvscode_importable() 把真包暴露出来。"""
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(REPO)!r})
        from miniqt.app.view import qtvscode_interface as page
        page.ensure_qtvscode_importable()
        import qtvscode
        print('HAS_WIDGET', hasattr(qtvscode, 'QtVscodeWidget'))
        print('HAS_BRIDGE', hasattr(qtvscode, 'QtvscodeBridge'))
    """)
    result = _run(script)
    assert 'HAS_WIDGET True' in result.stdout
    assert 'HAS_BRIDGE True' in result.stdout


def test_qtcompat_follows_the_host_binding():
    """宿主先导入 PyQt6 时，qtvscode 必须也用 PyQt6（不能混用两套绑定）。"""
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(REPO / 'qtvscode')!r})
        import PyQt6.QtCore                       # 模拟 miniqt
        from qtvscode.qtcompat import QT_API
        print('QT_API', QT_API)
    """)
    result = _run(script)
    assert 'QT_API PyQt6' in result.stdout


def test_qtcompat_honours_the_environment_override():
    """QTVSCODE_QT_API 可以强制绑定。"""
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(REPO / 'qtvscode')!r})
        os.environ['QTVSCODE_QT_API'] = 'PyQt6'
        from qtvscode.qtcompat import QT_API
        print('QT_API', QT_API)
    """)
    result = _run(script)
    assert 'QT_API PyQt6' in result.stdout


def test_widget_exposes_ready_and_failed_signals():
    """宿主页面靠这两个信号更新状态栏，缺了就只能显示白屏。"""
    source = _read(WIDGET)
    assert 'serverReady = Signal(str)' in source
    assert 'serverFailed = Signal(str)' in source
    assert 'self.serverReady.emit(' in source


def test_stopping_the_server_is_not_reported_as_a_failure():
    """主动 stop() 时 QProcess 会报 Crashed，必须用 _stopping 屏蔽掉。"""
    source = _read(SERVER)
    stop_body = source.split('def stop(self, timeout_ms', 1)[1]
    stop_body = stop_body.split('\n    def ', 1)[0]
    assert 'self._stopping = True' in stop_body
    assert 'self._stopping = False' in stop_body
    error_body = source.split('def _on_error(self, _error) -> None:', 1)[1]
    assert 'if self._stopping:' in error_body.split('\n    def ', 1)[0]
    assert 'self._stopping = False' in _read(SERVER).split(
        'def start(self) -> None:', 1)[1].split('\n    def ', 1)[0]


def test_qtvscode_is_installed_or_importable_from_the_repo():
    """要么装了 qtvscode，要么仓库里的源码可导入 —— 否则页面起不来。"""
    has_repo_copy = (REPO / 'qtvscode' / 'qtvscode' / '__init__.py').exists()
    if has_repo_copy:
        return
    pytest.importorskip('qtvscode')


def _run(script: str) -> subprocess.CompletedProcess:
    """在干净的子进程里跑脚本（避免 sys.modules 互相污染）。"""
    env = dict(os.environ)
    env.pop('QTVSCODE_QT_API', None)
    env.pop('MINIQT_QTVSCODE_WORKSPACE', None)
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=str(REPO), env=env,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=180)
    if result.returncode != 0:
        pytest.fail(f'子进程失败（{result.returncode}）:\n'
                    f'{result.stdout}\n{result.stderr}')
    return result

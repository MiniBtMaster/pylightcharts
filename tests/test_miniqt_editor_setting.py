# coding: utf-8
"""编辑器设置：同目录模式开关 + 两种模式（共享 / 独立）✓。

用户要求：
* 设置页新增「编辑器设置」，一个「同目录编辑器」开关（默认开）；
* 开 = 所有代码编辑器共用一个目录 / 看盘+回测共用一个编辑器进程（省内存）；
* 关 = 每个编辑器各自独立目录 / 进程（多目录-多开销）；
* 改后**重启程序**才生效，选择时弹提醒。

    pytest tests/test_miniqt_editor_setting.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO / 'miniqt' / 'app' / 'common' / 'config.py'
SETTING = REPO / 'miniqt' / 'app' / 'view' / 'setting_interface.py'
PAGE = REPO / 'miniqt' / 'app' / 'windows' / 'qtvscode_page.py'
NAV = REPO / 'miniqt' / 'app' / 'view' / 'qtvscode_interface.py'

pytestmark = pytest.mark.skipif(
    not CONFIG.exists(), reason='需要仓库里的 miniqt 源码')


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding='utf-8')


def _run(script: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=str(REPO), env=env,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=180)
    if result.returncode != 0:
        pytest.fail(f'子进程失败（{result.returncode}）:\n'
                    f'{result.stdout}\n{result.stderr}')
    return result


# ---- 配置 / 设置页 ------------------------------------------------------
def test_config_has_same_dir_default_true_and_snapshot():
    source = _read(CONFIG)
    assert 'editorSameDir = ConfigItem("Editor", "SameDir", True' in source
    assert 'EDITOR_SAME_DIR_AT_STARTUP' in source
    assert 'def editor_same_dir(' in source


def test_setting_page_has_editor_interface_and_restart_hint():
    source = _read(SETTING)
    assert 'class EditorSettingInterface' in source
    assert 'cfg.editorSameDir' in source
    assert 'addSubInterface(self.editorSettingInterface' in source
    # 副标题带上「多目录多开销」；详细影响说明段落已按用户要求删除 ✓
    assert '关闭则各自独立目录（多目录多开销）' in source
    assert 'explainLabel' not in source
    # 重启提醒
    assert '重启' in source
    assert 'valueChanged.connect(self.__onSameDirChanged)' in source


# ---- 两种模式的源码约束 -------------------------------------------------
def test_qtvscode_page_implements_both_modes():
    source = _read(PAGE)
    assert 'def _same_dir_mode(' in source
    assert 'def _own_user_data_dir(' in source
    assert 'def _start_shared_editor(' in source
    assert 'def _start_own_editor(' in source
    assert 'def _teardown_own_editor(' in source
    # OFF 模式：每页独立 user-data-dir（否则多台 server 抢目录 ✗）
    assert "'qtvscode_pages'" in source
    # 独立编辑器真的被创建 + serverReady 连接
    assert 'QtVscodeWidget(' in source
    assert 'editor.serverReady.connect(self._on_ready)' in source


def test_nav_follows_the_shared_directory():
    source = _read(NAV)
    assert 'def shared_dock_workspace(' in source
    assert 'editor_same_dir()' in source


# ---- 功能：默认开启 = 共享 ---------------------------------------------
def test_default_mode_uses_the_shared_editor():
    script = (
        "import os\n"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
        "import PyQt6.QtWebEngineWidgets  # noqa\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "import miniqt.app.windows.qtvscode_page as qp\n"
        "print('MODE', qp._same_dir_mode())\n"
        "d1 = qp._own_user_data_dir()\n"
        "d2 = qp._own_user_data_dir()\n"
        "print('UNIQUE_DIRS', d1 != d2)\n"
    )
    out = _run(script).stdout
    assert 'MODE True' in out                 # 默认同目录（共享）✓
    assert 'UNIQUE_DIRS True' in out          # OFF 模式的独立目录各不相同 ✓


# ---- 功能：关闭 = 每页自建编辑器 ---------------------------------------
def test_ensure_started_dispatches_by_mode():
    """开关开 → 用共享编辑器；关 → 走独立编辑器（``_start_own_editor``）✓。"""
    script = (
        "import os\n"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
        "import PyQt6.QtWebEngineWidgets  # noqa\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "import miniqt.app.common.config as config\n"
        "config.EDITOR_SAME_DIR_AT_STARTUP = False   # 模拟“关闭后重启”\n"
        "import miniqt.app.windows.qtvscode_page as qp\n"
        "calls = []\n"
        "# 要 patch **类方法**（ensure_started 走 self.xxx，不是模块全局 ✗）\n"
        "qp.QtvscodePage._start_shared_editor = (\n"
        "    lambda self: calls.append('shared'))\n"
        "qp.QtvscodePage._start_own_editor = (\n"
        "    lambda self: calls.append('own'))\n"
        "page = qp.QtvscodePage(mode='edit')\n"
        "page.ensure_started()\n"
        "print('MODE', qp._same_dir_mode())\n"
        "print('CALLS', calls)\n"
        "config.EDITOR_SAME_DIR_AT_STARTUP = True\n"
        "calls2 = []\n"
        "qp.QtvscodePage._start_own_editor = (\n"
        "    lambda self: calls2.append('own'))\n"
        "qp.QtvscodePage._start_shared_editor = (\n"
        "    lambda self: calls2.append('shared'))\n"
        "page2 = qp.QtvscodePage(mode='edit')\n"
        "page2.ensure_started()\n"
        "print('CALLS2', calls2)\n"
        "# 独立编辑器关闭时必须真正拆掉（不依赖 _bridge 已存在）\n"
        "page2._editor = None\n"
        "page2._teardown_own_editor()\n"
        "print('TEARDOWN_OK', page2._editor is None)\n"
    )
    out = _run(script).stdout
    assert 'MODE False' in out
    assert "CALLS ['own']" in out
    assert "CALLS2 ['shared']" in out
    assert 'TEARDOWN_OK True' in out

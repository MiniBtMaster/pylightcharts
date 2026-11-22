# coding: utf-8
"""v1.3.7-40：AI 悬浮对话窗（PiFloat）。

设计要点（用户 2026-11-08）：
1. 发到**会话**里（多轮 / 可追溯），不是一次性问答；
2. 简化界面：输入框 + 发送 + 模型 chip；底部**执行中才出现**的进度条；
3. 贴主窗口四边（<28px）→ 自动收起成小圆标，点图标恢复；
4. 只有「pi 已安装 + 模型已配置」才激活输入；入口 = ＋菜单 + `Ctrl+Alt+A`。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


def test_float_component_basics():
    code = _read('pi-float.ts')
    for token in ('export class PiFloat', 'desk-pi-float-input',
                  'desk-pi-float-send', 'desk-pi-float-model',
                  'desk-pi-float-progress', 'desk-pi-float-icon',
                  'setTheme(', 'piOnPatch('):
        assert token in code, token
    # 发到会话（不是一次性问答）
    assert "this.options.onCommand('pi_send'" in code
    assert 'pi_new_session' in code           # 没有会话时用首句建一个 ✓
    assert "onCommand('pi_history'" in code


def test_float_progress_bar_only_while_running():
    code = _read('pi-float.ts')
    assert 'private _showProgress(text: string): void {' in code
    assert 'private _hideProgress(): void {' in code
    # 事件驱动：start/delta → 显示；done/stopped/error → 收起 ✓
    for token in ("kind === 'start'", "kind === 'delta'",
                  "kind === 'done' || kind === 'stopped'", "kind === 'error'"):
        assert token in code, token
    assert 'this.progress.style.display = ' in code


def test_float_gating_requires_pi_and_model():
    code = _read('pi-float.ts')
    assert 'private _syncReady(): void {' in code
    assert 'this.ready = installed && hasModel;' in code
    assert 'this.input.disabled = !this.ready;' in code
    assert 'this.sendButton.disabled = !this.ready;' in code
    assert '没有检测到 pi' in code and '还没选择模型' in code


def test_float_edge_snap_and_restore():
    code = _read('pi-float.ts')
    for token in ('const EDGE = 28;', 'private _endDrag(): void {',
                  'collapse(edge = \'right\', offset?: number): void {',
                  'expand(): void {',
                  'nearLeft', 'nearRight', 'nearTop', 'nearBottom',
                  'desk.pi.float.pos', 'desk.pi.float.collapsed'):
        assert token in code, token
    # 贴边才收起（不是随便拖就收 ✓）
    assert 'if (!(nearLeft || nearRight || nearTop || nearBottom)) return;' \
        in code


def test_float_entries_and_shortcut():
    app = _read('app.ts')
    assert "import { PiFloat } from './pi-float';" in app
    assert 'openPiFloat(): PiFloat {' in app
    # ★ 用户 2026-11-08：`Ctrl+Alt+A` 被微信截图抢走 → 改 **F1**
    assert "'AI 悬浮窗（对话 / 快捷键 F1）'" in app
    assert "event.key === 'F1'" in app
    assert 'this.piFloat?.piOnPatch(patch);' in app
    assert 'this.piFloat?.setTheme(theme);' in app
    # ★ 顺手补上：`pi_status` 以前没路由 → PI 按钮不会禁用 ✗
    assert "case 'pi_status':" in app


def test_float_css_present():
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    for token in ('.desk-pi-float {', '.desk-pi-float-progress',
                  '.desk-pi-float-icon', '@keyframes desk-pi-float-run'):
        assert token in css, token


# ------------------------- 建议 1~3（v1.3.7-41：@文件 / 会话下拉 / 自动隐藏）
def test_float_supports_at_files():
    code = _read('pi-float.ts')
    assert 'setFiles(items: Array<Record<string, unknown>>): void {' in code
    assert "onCommand('ai_files'" in code
    assert "const matched = /(^|" + chr(92) + "s)@" in code
    assert 'desk-pi-float-files' in code
    app = _read('app.ts')
    # ★ ai_files 以前连编辑器都没路由（@文件其实不生效 ✗）→ 现在补上
    assert "case 'ai_files':" in app


def test_float_session_dropdown():
    code = _read('pi-float.ts')
    assert 'private _sessionMenu(): void {' in code
    assert "'会话 ▾'" in code
    assert 'this.sessions = items.map((row) => ({' in code
    assert "onCommand('pi_history'" in code
    assert 'desk-pi-float-session' in code
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-pi-float-session' in css
    assert '.desk-pi-float-file' in css


def test_float_ball_and_pin():
    """（v1.3.7-53）小球成为常态 → 贴边自动收起已废弃，钉住按钮保留 ✓"""
    code = _read('pi-float.ts')
    for token in ('private _cancelAutoHide(): void {',
                  'private _togglePin(): void {',
                  'desk.pi.float.pinned',
                  'showBall(): void {',
                  'openCard(): void {'):
        assert token in code, token
    # 离开窗口不再自动收起（否则对话窗口一移开鼠标就没了 ✗）
    assert 'private _scheduleAutoHide' not in code
    assert 'this.edge = edge;' not in code


# ------------------------- 下一步 1、2（v1.3.7-42：独立浮窗 + 会话搜索）
def test_detached_float_window_module():
    path = ROOT / 'minibt' / 'desk' / 'float_window.py'
    code = path.read_text(encoding='utf-8')
    for token in ('def open_float(desk)', 'def close_float(', 'pi=float',
                  'WindowStaysOnTopHint', "_STATE['senders']",
                  'desk.sender = both', 'def _attach_sender(desk)'):
        assert token in code, token
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'pi_detach_float': self._on_pi_detach_float" in app
    assert 'def _on_pi_detach_float(' in app
    assert 'float_window.close_float(self)' in app


def test_detach_without_qt_reports_cleanly(tmp_path, monkeypatch):
    """没有 Qt（浏览器壳 / 测试）→ 只提示，不崩 ✓"""
    import json as _json

    from minibt.desk import local_data, personal, pi as pi_mod, user_prefs
    from minibt.desk.app import Desk

    monkeypatch.setattr(pi_mod, 'MODELS_FILE', str(tmp_path / 'm.json'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._on_pi_detach_float({})            # 不该抛异常 ✓
    rows = [_json.loads(item[len('window.__desk.applyPatch('):-2])
            for item in desk.sent if item.startswith('window.__desk')]
    texts = ' '.join(str(row.get('text') or '') for row in rows)
    assert '浮窗' in texts


def test_float_mode_render_only_float():
    index = (JSLIB / 'index.ts').read_text(encoding='utf-8')
    assert "const FLOAT_MODE = /(?:^|[?&])pi=float/.test(window.location.search)"         in index
    assert 'function startFloat(): void {' in index
    assert 'if (FLOAT_MODE) {' in index
    assert 'desk-float-detached' in index
    assert 'desk-pi-float-max' in index
    assert '__deskFloat' in index


def test_float_detach_button_and_session_search():
    code = _read('pi-float.ts')
    assert 'detach(): void {' in code
    assert "onCommand('pi_detach_float', {})" in code
    assert "'浮到窗口外（独立置顶小窗）'" in code
    # 会话搜索
    assert 'desk-pi-float-search' in code
    assert 'renderRows(search.value)' in code
    assert "row.title.toLowerCase().includes(needle)" in code
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    for token in ('.desk-pi-float-max', 'body.desk-float-detached',
                  '.desk-pi-float-search'):
        assert token in css, token

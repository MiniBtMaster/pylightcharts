# coding: utf-8
"""v1.3.7-38：**PI 独立界面**（对话 + 编辑代码，不用先开图表）。

用户要求：
1. 以编辑器实例为基础（同一套代码），隐藏桌面专属功能；
2. 工具栏隐藏「加到图表 … 参数优化」和「帮助」；
3. 右键菜单隐藏「加到图表」（只隐藏，代码保留）；
4. 两个入口：首页工作区（预警中心下面）+ 顶栏「＋ → PI 助手」（去掉「零 npm 依赖」）；
5. 左侧栏是会话列表，右侧是初始化页（**不是页签**）；
   初始化页发送 = 新建会话；没有页签时显示初始化页；
6. 新建会话先显示初始化界面（这时已经有页签），发送即在会话里对话。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


def test_pi_page_reuses_editor_with_variant():
    page = _read('pi-page.ts')
    assert "variant: 'pi'" in page
    assert 'new EditorPanel(' in page
    assert 'allowLive: false' in page
    assert 'export class PiPage' in page
    # 兼容图表页接口（app.ts 统一调 setSettings / openEditor ✓）
    for token in ('setSettings(', 'openEditor(', 'applyTheme('):
        assert token in page, token


def test_toolbar_hides_desktop_only_buttons():
    editor = _read('editor-panel.ts')
    assert 'variant?: \'desk\' | \'pi\';' in editor
    assert 'this.piOnly = options.variant === \'pi\';' in editor
    # 8 个按钮被「隐藏」（不是删除 ✓）
    assert 'for (const button of [this.addButton, this.overlayButton,' in editor
    block = editor[editor.index('if (this.piOnly) {'):][:600]
    for token in ('this.addButton', 'this.overlayButton', 'this.manageButton',
                  'this.backtestButton', 'this.optimizeButton',
                  'this.liveButton', 'this.stopLiveButton', 'helpButton'):
        assert token in block, token
    assert "button.style.display = 'none';" in block
    # 右键菜单里的「加到图表」隐藏（代码保留）
    assert '...(this.piOnly ? [] : [' in editor
    assert "if (!this.piOnly) items.push({" in editor


def test_welcome_component_matches_pi_agent_web():
    welcome = _read('pi-welcome.ts')
    for token in ("'PI 助手'", '用简单的话讲清楚', 'desk v', 'pi v',
                  '→ 发送', 'desk-pi-welcome-composer', 'setModel',
                  'onSend(text)'):
        assert token in welcome, token
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    for token in ('.desk-pi-welcome', '.desk-pi-welcome-composer',
                  '.desk-pi-welcome-send', '.desk-pi-welcome-chip',
                  '.desk-pi-page'):
        assert token in css, token


def test_editor_shows_welcome_when_no_tabs():
    editor = _read('editor-panel.ts')
    assert 'private welcome: PiWelcome | null = null;' in editor
    assert 'private pendingPiSend = \'\';' in editor
    assert 'this.welcome = new PiWelcome({' in editor
    assert 'private _syncWelcome(): void {' in editor
    assert 'private _sendFromWelcome(text: string): void {' in editor
    # 初始化页发送 = 新建会话 ✓
    assert "this.options.onCommand('pi_new_session', { cwd: this.root });" \
        in editor
    # 新会话建好后把这句话发出去 ✓
    assert 'this.piTabs.get(id)?.chat.sendText(text);' in editor
    # 关闭会话后重新同步（没有页签 → 回到初始化页 ✓）
    assert editor.count('this._syncWelcome();') >= 2


def test_chat_send_text_and_inline_welcome():
    chat = _read('pi-chat.ts')
    assert 'sendText(text: string): void {' in chat
    assert 'desk-pi-welcome-inline' in chat


def test_app_entries_and_routing():
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "const PI_TAB_ID = 'pi:app';" in app
    assert 'openPiWorkspace(): PiPage' in app
    assert "'PI 助手（对话 / 编辑代码）'" in app
    # 去掉「零 npm 依赖」字样 ✓
    assert '零 npm 依赖' not in app
    # 首页入口
    assert 'onOpenPi: () => this.openPiWorkspace(),' in app
    # 补丁路由：所有带编辑器的页面（含 PI 独立界面）都能收到 ✓
    assert 'private _editorPanels(): EditorPanelLike[] {' in app
    assert 'panel.piOnPatch?.(patch);' in app
    home = _read('home-page.ts')
    alerts = home.index('data-nav="alerts"')
    pi_nav = home.index('data-nav="pi"')
    assert pi_nav > alerts                    # PI 在「预警中心」下面 ✓
    assert 'onOpenPi?: () => void;' in home


def test_welcome_flow_source_contract():
    """初始化页 → **先建会话（落盘）→ 再问模型**（v1.3.7-59 收口）✓

    用户 2026-11-08：初始化页对话"能聊但会话没保存" —— 根因是前端
    `pi_new_session` + 等补丁发文字（中间任何一环没回来就只剩前端在聊）。
    现在只走一条路：`pi_send{id:""}`，由后端先 `create_session` +
    `save_session` + 推 `pi_session`，然后才开始跑模型。
    """
    editor = _read('editor-panel.ts')
    welcome_send = editor[editor.index('private _sendFromWelcome'):][:900]
    assert 'this.pendingPiSend = value;' in welcome_send
    assert "this.options.onCommand('pi_send'" in welcome_send
    assert "id: ''" in welcome_send
    assert 'title: value.slice(0, 40)' in welcome_send
    # 兜底定时器已删（两边都建 → 重复会话 ✗）
    assert 'welcomeFallback' not in welcome_send
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    # ★ 只看 `_on_pi_send`（别被 `_on_ai_summary` 里同样的 load_session 抢先 ✓）
    block = app.split('def _on_pi_send(', 1)[1][:2400]
    assert 'title=str(payload.get(' in block
    assert '_push_pi_sessions()' in block


# ---------------------------------------- 建议 1~5（v1.3.7-39）
def test_welcome_recent_sessions_and_drag():
    welcome = _read('pi-welcome.ts')
    assert 'setRecent(rows' in welcome
    assert "'最近会话'" in welcome
    assert 'onOpenSession' in welcome
    assert "addEventListener('drop'" in welcome
    assert "addEventListener('dragover'" in welcome
    assert '暂不支持直接粘贴图片' in welcome
    editor = _read('editor-panel.ts')
    assert 'this.welcome?.setRecent(this.piRows as never[]);' in editor
    assert 'onOpenSession: (id) => this.openPiSession(id),' in editor


def test_pi_root_is_separate_from_explorer_root(tmp_path, monkeypatch):
    """PI 独立界面记住自己的目录（`pi_root`），不影响资源管理器 ✓"""
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
    target = tmp_path / 'pi_dir'
    target.mkdir()
    desk._apply_explorer_root(str(target), pi_only=True)
    settings = user_prefs.settings()
    assert settings.get('pi_root') == str(target)
    assert settings.get('explorer_root') in (None, '')
    assert desk._pi_root() == str(target)
    # 全局切目录仍然只改 explorer_root ✓
    other = tmp_path / 'chart_dir'
    other.mkdir()
    desk._apply_explorer_root(str(other))
    assert user_prefs.settings().get('explorer_root') == str(other)
    assert user_prefs.settings().get('pi_root') == str(target)


def test_new_session_title_and_pin(tmp_path, monkeypatch):
    """首句话直接当标题 + 会话可置顶（排最前）✓"""
    import json

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

    def patches(kind):
        return [json.loads(item[len('window.__desk.applyPatch('):-2])
                for item in desk.sent
                if item.startswith('window.__desk')
                and f'"type":"{kind}"' in item]

    desk._on_pi_new_session({'cwd': str(tmp_path), 'title': '第一个问题'})
    session = patches('pi_session')[-1]['session']
    assert session['title'] == '第一个问题'
    desk._on_pi_new_session({'cwd': str(tmp_path), 'title': '第二个问题'})
    second = patches('pi_session')[-1]['session']
    desk._on_pi_pin({'id': second['id'], 'on': True})
    rows = patches('pi_sessions')[-1]['items']
    assert rows[0]['id'] == second['id'] and rows[0]['pinned'] is True
    pinned_ids = patches('pi_sessions')[-1]['pins']
    assert pinned_ids == [second['id']]
    desk._on_pi_pin({'id': second['id'], 'on': False})
    assert patches('pi_sessions')[-1]['pins'] == []


def test_welcome_send_carries_title():
    editor = _read('editor-panel.ts')
    block = editor[editor.index('private _sendFromWelcome'):][:520]
    assert 'title: value.slice(0, 40),' in block
    chat = _read('pi-chat.ts')
    assert 'sendText(text: string): void {' in chat


def test_pi_panel_pin_button():
    panel = _read('pi-panel.ts')
    assert 'onPin?: (id: string, on: boolean) => void;' in panel
    assert "pinned ? '★' : '☆'" in panel
    assert "label: pinned ? '取消置顶' : '置顶'," in panel
    assert "row.pinned === true" in panel
    editor = _read('editor-panel.ts')
    assert "onPin: (id, on) => this.options.onCommand('pi_pin', { id, on }),"         in editor


# ------------------- 反馈修复（v1.3.7-43：PI 页会话 / 布局）
def test_pi_page_does_not_override_payload_id():
    """PI 页的 `onCommand` **不能**把 payload.id 改成页签 id（会话 id 会丢 ✗）"""
    app = _read('app.ts')
    block = app[app.index('openPiWorkspace(): PiPage {'):][:1600]
    assert 'this.send(cmd, payload)' in block
    # 不允许把 payload.id 覆盖成页签 id（这是会话 id ✗）
    handler = block.split('onCommand:')[1][:120]
    assert 'payload.id' not in handler
    assert '...((payload' not in handler
    # 页签先用已知标题（不要先显示 "PI" ✓）
    editor = _read('editor-panel.ts')
    assert 'const known = this.piRows.find((row) => row.id === key);' in editor
    assert 'tab = { id: key, name: title, button, chat };' in editor


def test_local_layout_command():
    from minibt.desk import tools

    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'local_layout': self._on_local_layout" in app
    assert 'def _on_local_layout(' in app
    # 工具：local + symbols → 走本地布局 ✓
    code = (ROOT / 'minibt' / 'desk' / 'tools.py').read_text(encoding='utf-8')
    assert "_on_local_layout({'symbols': symbols" in code
    assert "'symbols': {'type': 'array'" in code
    names = tools.NAMES
    assert 'desk_set_layout' in names


def test_local_layout_pushes_layout_and_loads(tmp_path, monkeypatch):
    import json as _json

    from minibt.desk import local_data, personal, pi as pi_mod, user_prefs
    from minibt.desk.app import Desk

    monkeypatch.setattr(pi_mod, 'MODELS_FILE', str(tmp_path / 'm.json'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    user_prefs.set_setting('ai_desk_allow', True)
    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._active_local_page = 'local:1'
    desk._on_local_layout({'symbols': ['test', 'l2609_60'],
                           'page': 'local:1'})
    rows = [_json.loads(item[len('window.__desk.applyPatch('):-2])
            for item in desk.sent if item.startswith('window.__desk')]
    layout = [row for row in rows if row.get('type') == 'layout']
    assert layout and layout[0]['local'] is True
    assert layout[0]['symbols'] == ['test', 'l2609_60']
    assert layout[0]['count'] == 2
    klines = [row for row in rows if row.get('type') == 'local_kline']
    assert len(klines) >= 2


def test_float_syncs_theme_and_pin_across_windows():
    code = _read('pi-float.ts')
    assert "addEventListener('storage'" in code
    assert "key === 'minibt.desk.theme'" in code
    assert 'const PINNED_KEY' in code
    assert 'private _syncPinButton(): void {' in code
    index = (JSLIB / 'index.ts').read_text(encoding='utf-8')
    assert 'desk-pi-float-max' in index


# ---------------------------------------- PI 首页三项（v1.3.7-60）
def test_welcome_model_chip_gets_active_model():
    """左下角模型不能用「未选择模型」敷衍（配置里其实早选好了 ✓）"""
    editor = _read('editor-panel.ts')
    block = editor[editor.index("if (kind === 'pi_models') {"):][:700]
    assert 'this.welcome?.setModel(' in block
    assert 'patch.active' in block
    # PI 页第一次显示就主动拉一次配置（不然 chip 一直是默认文案 ✗）
    show = editor[editor.index('    show(): void {'):][:900]
    assert "this.options.onCommand('pi_models', {})" in show


def test_welcome_version_is_pi_version_not_minibt():
    """`pi v1.3.7` 用的是 minibt 版本 ✗ → 要 `pi --version`（1.5.1 ✓）"""
    welcome = _read('pi-welcome.ts')
    assert 'piVersion' in welcome
    assert 'setVersions(' in welcome
    assert 'pi v1.3.7' not in welcome
    editor = _read('editor-panel.ts')
    block = editor[editor.index("if (kind === 'pi_status') {"):][:500]
    assert 'setVersions(' in block
    assert 'patch.piVersion' in block
    app = _read('app.ts')
    assert 'this._piVersion' in app


def test_welcome_recent_only_three_and_opens_existing():
    """最近会话只列 3 个，点击 = 打开那个会话（新建走左栏「＋」✓）"""
    welcome = _read('pi-welcome.ts')
    block = welcome[welcome.index('setRecent(rows'):][:1200]
    assert 'slice(0, 3)' in block
    assert 'onOpenSession?.(id)' in block          # 打开已有会话 ✓
    assert 'pi_new_session' not in block           # 不再顺手新建 ✗

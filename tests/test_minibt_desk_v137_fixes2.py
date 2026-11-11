# coding: utf-8
"""v1.3.7-29：用户反馈的一批修复（复制 / 滚动 / 历史 / 旧代码 / 本地图表 / 排队）。

对应用户 2026-11-08 的 10 条反馈里能直接修的部分：

1. 结论处「复制」不生效 → 走**后端**系统剪贴板（`clipboard_set`）
2. 本地图表加指标失败 → 工具没带 `page`（存到了 CSV 名下，前端不认）
3. 参数优化用旧代码 → `Bt._load_strategies` 命中 `sys.modules`/`.pyc` 缓存
4. 切到对话页没滚到底 → `scrollToBottom()`
5. 输入框 ↑↓ 历史（PI / 终端 / REPL）
6. 本地图表切换合约失败 → 走新的 `local_switch`
7. 执行中再发消息插不进去 → 排队（`queued`）
"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import agent, tools
from minibt.desk import local_data, personal, pi, user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, 'SESSIONS_DIR', str(tmp_path / 'sessions'))
    monkeypatch.setattr(pi, 'MODELS_FILE', str(tmp_path / 'models.json'))
    monkeypatch.setattr(pi, 'SKILLS_DIR', str(tmp_path / 'skills'))
    monkeypatch.setattr(pi, 'SKILL_STATE', str(tmp_path / 'skills.json'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    agent.RUNS.clear()
    yield tmp_path
    agent.RUNS.clear()


def _desk(root: str = '.'):
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.explorer_root = lambda: root
    return desk


# ---------------------------------------------------------- 1. 复制走后端
def test_copy_uses_backend_clipboard():
    """QtWebEngine 里 `navigator.clipboard` 常失败 → 复制必须走后端 ✓"""
    chat = (JSLIB / 'desk' / 'pi-chat.ts').read_text(encoding='utf-8')
    assert "send('clipboard_set', { text })" in chat
    assert 'copyText(message.content, this._send)' in chat
    assert 'copyText(text, this._send)' in chat
    # 后端命令早就有（复用 editor「复制地址」那套 ✓）
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'clipboard_set': self._on_clipboard_set" in app


# ------------------------------------------------- 2/6. 本地图表：指标 / 换数据集
class FakeLocalDesk:
    def __init__(self):
        self.calls = []
        self._local_pages = {'local:1': {0: 'test'}}
        self._active_local_page = 'local:1'
        self._local_indicators = {}
        self.tabs = {}

    def _on_local_add_indicator(self, payload):
        self.calls.append(('add', dict(payload)))
        return True

    def _on_local_remove_indicator(self, payload):
        self.calls.append(('remove', dict(payload)))

    def _on_local_switch(self, payload):
        self.calls.append(('switch_local', dict(payload)))

    def _on_switch_symbol(self, payload):
        self.calls.append(('switch', dict(payload)))

    def _on_remove_indicator(self, payload):
        self.calls.append(('remove_watch', dict(payload)))

    def _on_clear_drawings(self, payload):
        self.calls.append(('clear_drawings', dict(payload)))

    def local_store(self):
        class _Store:
            def items(self):
                return [{'name': 'test'}, {'name': 'l2609_60'}]
        return _Store()

    def _local_items(self, name, cell=0, page=''):
        return [{'key': 'MA'}, {'key': 'MACD'}]


def test_add_indicator_passes_page():
    desk = FakeLocalDesk()
    result = json.loads(tools.call('desk_add_indicator', {
        'key': 'pta_sma', 'symbol': 'test', 'local': True,
        'page': 'local:1'}, desk))
    assert result['ok'] is True
    assert desk.calls[-1][0] == 'add'
    assert desk.calls[-1][1]['page'] == 'local:1'
    # 别名 / 多义：`MA` 太泛 → 回候选（v1.3.7-44 ✓）
    ambiguous = json.loads(tools.call('desk_add_indicator', {
        'key': 'MA', 'local': True}, desk))
    assert ambiguous.get('need_key_choice') is True


def test_local_pages_and_clear_indicators():
    desk = FakeLocalDesk()
    data = json.loads(tools.call('desk_local', {'action': 'pages'}, desk))
    assert data['active'] == 'local:1'
    assert data['pages'][0]['cells'] == {'0': 'test'}
    result = json.loads(tools.call('desk_clear_indicators', {
        'symbol': 'test', 'local': True}, desk))
    assert result['count'] == 2
    assert {call[1]['key'] for call in desk.calls if call[0] == 'remove'} == {
        'MA', 'MACD'}


def test_switch_symbol_routes_local_dataset_to_local_switch():
    desk = FakeLocalDesk()
    data = json.loads(tools.call('desk_switch_symbol', {
        'symbol': 'test', 'local': True}, desk))
    assert data['local'] is True
    assert desk.calls[-1][0] == 'switch_local'
    # 不是数据集 → 走行情路径 ✓
    tools.call('desk_switch_symbol', {'symbol': 'DCE.a2701'}, desk)
    assert desk.calls[-1][0] == 'switch'


def test_app_local_switch_pushes_kline_and_symbol():
    desk = _desk('.')
    desk._local_pages = {'local:1': {0: 'test'}}
    desk._active_local_page = 'local:1'
    desk._on_local_switch({'from': 'pp2609_60', 'to': 'test',
                           'page': 'local:1'})
    desk.flush_outbox()
    kinds = []
    for script in desk.sent:
        if not script.startswith('window.__desk'):
            continue
        kinds.append(json.loads(script[len('window.__desk.applyPatch('):-2]
                                ).get('type'))
    assert 'local_kline' in kinds
    assert 'switch_symbol' in kinds


def test_frontend_uses_local_switch_for_dataset():
    page = (JSLIB / 'desk' / 'local-chart-page.ts').read_text(encoding='utf-8')
    assert "onCommand?.('local_switch'" in page
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'local_switch': self._on_local_switch" in app
    assert 'def _on_local_switch(' in app


# ---------------------------------------------------------- 3. 回测读最新代码
def test_strategy_file_is_reloaded_every_run(isolated):
    """改了策略再跑，必须读到**新**代码（以前命中缓存 ✗）"""
    from minibt.bt import Bt

    path = isolated / 'demo_strategy.py'
    path.write_text('from minibt import Strategy\n\n\n'
                    'class Demo(Strategy):\n    tag = 1\n', encoding='utf-8')
    first = Bt()._load_strategies(str(path))
    assert [item.tag for item in first] == [1]
    path.write_text('from minibt import Strategy\n\n\n'
                    'class Demo(Strategy):\n    tag = 2\n', encoding='utf-8')
    again = Bt()._load_strategies(str(path))
    assert [item.tag for item in again] == [2]
    code = (ROOT / 'minibt' / 'bt.py').read_text(encoding='utf-8')
    assert 'exec(compile(source' in code           # 直接读源码，绕开 .pyc ✓
    assert 'sys.modules.pop(module_name, None)' in code


# ---------------------------------------------------------- 4/5. 滚动 + 历史
def test_pi_chat_scrolls_and_keeps_history():
    chat = (JSLIB / 'desk' / 'pi-chat.ts').read_text(encoding='utf-8')
    assert 'scrollToBottom(): void {' in chat
    assert 'this.history.push(text || ' in chat      # 只有附件也能发 ✓
    assert "event.key === 'ArrowUp'" in chat and "event.key === 'ArrowDown'" in chat
    assert 'private readonly history: string[] = [];' in chat
    editor = (JSLIB / 'desk' / 'editor-panel.ts').read_text(encoding='utf-8')
    assert 'tab.chat.scrollToBottom();' in editor
    assert 'this._activatePi' in editor
    # 终端 / REPL 的 ↑↓
    assert 'private _historyStep(' in editor
    assert "this._historyStep(this.terminalInput, this.terminalHistory" in editor
    assert "this._historyStep(this.replInput, this.replHistory" in editor


# ---------------------------------------------------------- 7. 执行中排队
def test_pi_send_queues_while_running():
    pi.save_models({'providers': {'deepseek': {
        'base': 'http://127.0.0.1:1/v1', 'apiKey': 'k',
        'models': ['deepseek-chat']}},
        'active': {'provider': 'deepseek', 'model': 'deepseek-chat'}})
    desk = _desk('.')
    desk._on_pi_new_session({})
    desk.flush_outbox()
    session_id = json.loads(
        [item for item in desk.sent if '"pi_session"' in item][-1]
        [len('window.__desk.applyPatch('):-2])['session']['id']

    class _Run:
        cancelled = False

        def __init__(self, sid: str):
            self.session_id = sid
            self.pending = []

        def append_user(self, text):
            self.pending.append(text)
            return True

    run = _Run(session_id)
    agent.RUNS[session_id] = run                    # 假装上一轮还在跑 ✓
    desk._on_pi_send({'id': session_id, 'text': '插一句'})
    desk.flush_outbox()
    rows = [json.loads(item[len('window.__desk.applyPatch('):-2])
            for item in desk.sent if item.startswith('window.__desk')]
    appended = [row for row in rows if row.get('event') == 'appended']
    assert appended, '执行中插话应该**追加到这一轮**（不重启）✓'
    assert run.pending == ['插一句']
    agent.RUNS.clear()
    chat = (JSLIB / 'desk' / 'pi-chat.ts').read_text(encoding='utf-8')
    assert "kind === 'queued'" in chat
    code = (ROOT / 'minibt' / 'desk' / 'agent.py').read_text(encoding='utf-8')
    assert 'flush_pi_queue' in code

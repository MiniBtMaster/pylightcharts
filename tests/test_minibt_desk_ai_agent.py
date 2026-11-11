# coding: utf-8
"""v1.3.7-4：**内置** AI 助手（会话 + 多开对话 + 工具），零 npm 依赖。

用户 2026-11-08：pi-web / pi-agent-studio 都要 Node + `npm install`，太重；
改成 desk 自带（Python）会话 + 对话窗口，走任意 OpenAI 兼容接口 ✓

这里用一个**假 OpenAI 服务**（`http.server`，SSE 流式 + 工具调用）验证：
会话存储 / 流式补丁 / 工具执行 / 沙箱 / 前端入口，不需要真的模型。
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from minibt.desk import agent
from minibt.desk import local_data, personal, user_prefs

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


class _FakeOpenAI(BaseHTTPRequestHandler):
    """最小 `/v1/chat/completions`：第一次回工具调用，第二次回流式文本 ✓"""

    calls: list = []

    def log_message(self, *args):                                 # noqa: D102
        pass

    def _sse(self, chunks):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f'data: {json.dumps(chunk, ensure_ascii=False)}\n\n'
                             .encode('utf-8'))
            self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()

    def do_POST(self):                                            # noqa: N802
        size = int(self.headers.get('Content-Length') or 0)
        payload = json.loads(self.rfile.read(size) or b'{}')
        _FakeOpenAI.calls.append(payload)
        has_tool_reply = any(
            str(message.get('role')) == 'tool'
            for message in payload.get('messages') or [])
        if not has_tool_reply and payload.get('tools'):
            self._sse([
                {'choices': [{'delta': {'role': 'assistant'}}]},
                {'choices': [{'delta': {'tool_calls': [{
                    'index': 0, 'id': 'call-1', 'type': 'function',
                    'function': {'name': 'list_dir', 'arguments': '{}'},
                }]}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]},
            ])
            return
        self._sse([
            {'choices': [{'delta': {'content': '我看了一下目录，'}}]},
            {'choices': [{'delta': {'content': '里面有这些文件：'}}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            # ★ 最后一块带 usage（OpenAI 的 include_usage ✓）
            {'choices': [], 'usage': {'prompt_tokens': 1200,
                                      'completion_tokens': 80,
                                      'total_tokens': 1280}},
        ])


@pytest.fixture()
def fake_llm():
    _FakeOpenAI.calls = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}/v1', _FakeOpenAI.calls
    server.shutdown()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """所有落盘都指到 tmp（会话 / 个人目录 / 设置 ✓）"""
    monkeypatch.setattr(agent, 'SESSIONS_DIR', str(tmp_path / 'sessions'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    agent.RUNS.clear()
    yield


def _desk(cwd: str = ''):
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.explorer_root = lambda: cwd or str(ROOT)
    return desk


def _all(desk):
    try:
        desk.flush_outbox()
    except Exception:                                            # noqa: BLE001
        pass
    return [json.loads(script[len('window.__desk.applyPatch('):-2])
            for script in desk.sent if script.startswith('window.__desk')]


def _patch(desk, kind: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        matched = [row for row in _all(desk) if row.get('type') == kind]
        if matched:
            return matched
        time.sleep(0.1)
    return []


def _events(desk, timeout: float = 20.0):
    """等一次对话跑完（`done` / `error` / `stopped`），返回全部 ai_event ✓"""
    deadline = time.time() + timeout
    rows = []
    while time.time() < deadline:
        rows = [row for row in _all(desk) if row.get('type') == 'ai_event']
        names = {row.get('event') for row in rows}
        if names & {'done', 'error', 'stopped'}:
            return rows
        time.sleep(0.1)
    return rows


# ------------------------------------------------------------ ① 会话存储
def test_session_crud(tmp_path):
    session = agent.create_session(str(tmp_path), '测试会话')
    assert session['id'] and session['cwd'] == str(tmp_path)
    agent.save_session({**session, 'messages': [
        {'role': 'user', 'content': '第一行提问'}]})
    rows = agent.list_sessions()
    assert rows and rows[0]['id'] == session['id']
    assert rows[0]['count'] == 1
    assert '第一行' in rows[0]['preview']
    renamed = agent.rename_session(session['id'], '改过名')
    assert renamed and renamed['title'] == '改过名'
    assert agent.delete_session(session['id']) is True
    assert agent.list_sessions() == []


def test_session_titles_auto_from_first_message():
    session = agent.create_session('.')
    assert session['title'] == '新会话'
    agent.save_session({**session, 'title': '新会话', 'messages': [
        {'role': 'user', 'content': '请帮我看看这个策略的回撤为什么这么大'}]})
    # `save_session` 不改标题；`AgentRun.save` 才会 —— 直接用 run 的 save ✓
    run = agent.AgentRun(_desk(), session, {}, '请帮我看看回撤为什么这么大')
    run.save([{'role': 'user', 'content': '请帮我看看回撤为什么这么大'}])
    loaded = agent.load_session(session['id'])
    assert loaded['title'].startswith('请帮我看看')


# ------------------------------------------------------------ ② 工具
def test_tools_are_sandboxed(tmp_path):
    (tmp_path / 'a.py').write_text('print(1)\n', encoding='utf-8')
    assert 'a.py' in agent.run_tool('list_dir', {}, str(tmp_path))
    assert 'print(1)' in agent.run_tool('read_file', {'path': 'a.py'},
                                        str(tmp_path))
    assert 'a.py' in agent.run_tool('grep', {'pattern': 'print'},
                                    str(tmp_path))
    blocked = agent.run_tool('read_file', {'path': '../secret.txt'},
                             str(tmp_path))
    assert '超出工作区' in blocked
    assert '超出工作区' in agent.run_tool(
        'write_file', {'path': '../../x.py', 'content': 'x'}, str(tmp_path))
    written = agent.run_tool('write_file',
                             {'path': 'b.py', 'content': 'x = 1\n'},
                             str(tmp_path))
    assert '已写入' in written
    assert (tmp_path / 'b.py').read_text(encoding='utf-8') == 'x = 1\n'


def test_run_command_returns_output(tmp_path):
    out = agent.run_tool('run_command', {'command': 'echo hello-tool'},
                         str(tmp_path))
    assert 'hello-tool' in out


# ------------------------------------------------------------ ③ 流式 + 工具循环
def test_chat_streams_and_calls_tools(fake_llm, tmp_path):
    base, calls = fake_llm
    (tmp_path / 'demo.py').write_text('x = 1\n', encoding='utf-8')
    user_prefs.set_setting('ai_base_url', base)
    user_prefs.set_setting('ai_api_key', 'test-key')
    user_prefs.set_setting('ai_model', 'fake-model')
    desk = _desk(str(tmp_path))
    desk._on_ai_new_session({})
    session_id = _patch(desk, 'ai_session')[0]['session']['id']
    desk.sent.clear()
    desk._on_ai_send({'id': session_id, 'text': '看看目录'})

    events = _events(desk)
    names = [row.get('event') for row in events]
    assert 'start' in names
    assert 'tool' in names and 'tool_result' in names
    assert 'done' in names
    streamed = ''.join(str(row.get('text') or '')
                       for row in events if row.get('event') == 'delta')
    assert '里面有这些文件' in streamed
    # 工具结果要回给模型（第二次请求里有 role=tool ✓）
    assert any(any(str(m.get('role')) == 'tool'
                   for m in (payload.get('messages') or []))
               for payload in calls)
    # 会话落盘：user + assistant + tool + assistant
    saved = agent.load_session(session_id)
    roles = [str(item.get('role')) for item in saved['messages']]
    assert roles.count('user') == 1
    assert 'tool' in roles


def test_chat_requires_api_key(tmp_path):
    user_prefs.set_setting('ai_api_key', '')
    desk = _desk(str(tmp_path))
    desk._on_ai_new_session({})
    session_id = _patch(desk, 'ai_session')[0]['session']['id']
    desk.sent.clear()
    desk._on_ai_send({'id': session_id, 'text': 'hi'})
    events = _events(desk)
    assert events and events[0]['event'] == 'error'
    assert 'API Key' in str(events[0].get('error'))


def test_stop_cancels_run(tmp_path):
    desk = _desk(str(tmp_path))
    session = agent.create_session(str(tmp_path))
    run = agent.AgentRun(desk, session, {}, 'x')
    agent.register(run)
    assert agent.cancel(session['id']) is True
    assert run.cancelled is True


# ------------------------------------------------------------ ③b 用量 / 成本
def test_usage_and_cost_are_tracked(fake_llm, tmp_path):
    base, _calls = fake_llm
    user_prefs.set_setting('ai_base_url', base)
    user_prefs.set_setting('ai_api_key', 'k')
    user_prefs.set_setting('ai_model', 'gpt-4o-mini')
    desk = _desk(str(tmp_path))
    desk._on_ai_new_session({})
    session_id = _patch(desk, 'ai_session')[0]['session']['id']
    desk.sent.clear()
    desk._on_ai_send({'id': session_id, 'text': '看看目录'})
    events = _events(desk)
    usage = [row for row in events if row.get('event') == 'usage']
    assert usage, '应该有 ai_event:usage'
    last = usage[-1]
    assert last['usage']['calls'] >= 1
    assert last['usage']['prompt'] >= 1200        # 服务返回的 usage 优先 ✓
    assert last['usage']['cost'] > 0              # gpt-4o-mini 非零单价
    assert last['window'] > 0 and last['percent'] >= 0
    saved = agent.load_session(session_id)
    assert saved['usage']['calls'] >= 1


def test_cost_and_tokens_helpers():
    assert agent.estimate_tokens('你好世界') >= 4
    assert agent.estimate_tokens('hello world') >= 2
    cost = agent.cost_of({'prompt_tokens': 1_000_000,
                          'completion_tokens': 0},
                         {'price_in': 0.15, 'price_out': 0.6})
    assert abs(cost - 0.15) < 1e-9
    config = agent.settings_of({'ai_model': 'deepseek-chat'})
    assert config['price_in'] > 0 and config['window'] >= 65536
    local = agent.settings_of({'ai_model': 'qwen2.5-coder:7b'})
    assert local['price_in'] == 0 and local['price_out'] == 0


# ------------------------------------------------------------ ③c 会话分支
def test_branch_session_truncates_and_drops_dangling_tools(tmp_path):
    session = agent.create_session(str(tmp_path), '原会话')
    messages = [
        {'role': 'user', 'content': 'q1'},
        {'role': 'assistant', 'content': 'a1'},
        {'role': 'user', 'content': 'q2'},
        {'role': 'assistant', 'content': '',
         'tool_calls': [{'id': 'c1', 'type': 'function',
                         'function': {'name': 'list_dir',
                                      'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'c1', 'name': 'list_dir',
         'content': 'a.py'},
        {'role': 'assistant', 'content': 'a2'},
    ]
    agent.save_session({**session, 'messages': messages})
    branch = agent.branch_session(session['id'], 3)
    assert branch is not None
    roles = [item['role'] for item in branch['messages']]
    # index=3 是带 tool_calls 的 assistant → 尾部 tool 已丢，assistant 也丢
    assert roles == ['user', 'assistant', 'user']
    assert branch['usage'] == {}            # 分支不继承花费 ✓
    assert branch['branchOf'] == session['id']
    assert agent.load_session(session['id'])['messages'] == messages  # 原会话不动 ✓


def test_branch_command_pushes_new_session(tmp_path):
    desk = _desk(str(tmp_path))
    session = agent.create_session(str(tmp_path), '父会话')
    agent.save_session({**session, 'messages': [
        {'role': 'user', 'content': 'q1'},
        {'role': 'assistant', 'content': 'a1'},
    ]})
    desk._on_ai_branch({'id': session['id'], 'index': 1})
    rows = _patch(desk, 'ai_session')
    assert rows and rows[0]['session']['title'].startswith('父会话')
    assert len(rows[0]['session']['messages']) == 2
    assert len(agent.list_sessions()) == 2


# ------------------------------------------------------------ ③d 前端断言
# ------------------------------------------------------------ ④ desk 命令
def test_context_builds_prompt_and_creates_session(tmp_path):
    desk = _desk(str(tmp_path))
    user_prefs.set_setting('ai_api_key', 'test-key')
    desk._on_ai_context({'kind': 'selection', 'code': 'x = 1',
                         'path': 'demo.py', 'question': '有问题吗？'})
    sessions = _patch(desk, 'ai_session')
    assert sessions, 'ai_context 应自动建会话'
    events = _events(desk)
    assert any(row.get('event') == 'user' for row in events)
    text = [row.get('text') for row in events
            if row.get('event') == 'user'][0]
    assert 'demo.py' in text and 'x = 1' in text and '有问题吗' in text


def test_ai_sessions_and_status_commands(tmp_path):
    desk = _desk(str(tmp_path))
    desk._on_ai_sessions({})
    assert _patch(desk, 'ai_sessions')
    desk._on_ai_status({})
    status = _patch(desk, 'ai_status')[0]
    assert 'model' in status and 'tools' in status
    assert agent.SESSIONS_DIR in str(status.get('sessionsDir'))


# ------------------------------------------------------------ ⑤ 后端（前端已改 PI）
def test_ai_backend_still_available_for_pi():
    """PI 页面复用 `agent.py` 的后端能力（会话 / 工具 / 流式 ✓）"""
    from minibt.desk import pi as pi_mod

    assert hasattr(pi_mod, 'install_skill')
    assert hasattr(pi_mod, 'parse_pi_session')
    assert hasattr(agent, 'start_run')
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'pi_sessions': self._on_pi_sessions" in app

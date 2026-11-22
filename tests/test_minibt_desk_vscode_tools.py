"""v1.3.8-5：两个新工具 `desk_pi` / `desk_vscode`（VS Code 集成）。

* `desk_pi`：VS Code 的原生对话 / 会话树通过本机桥调它 —— 用 **desk 进程里**的
  agent 跑一轮，所以 PI 的工具作用在用户眼前的看盘窗口上，会话文件和 desk 的
  PI 页面共用（`~/.minibt/ai/sessions/*.json`）。
* `desk_vscode`：反过来让 AI 操作 VS Code（打开 / 读 / 插入 / 跑命令），
  服务端是扩展起的 127.0.0.1 + 一次性 token 小服务（`vscode_bridge.json`）。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import agent as desk_agent
from minibt.desk import tools as desk_tools

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def fake_desk(monkeypatch, tmp_path):
    """只实现工具需要的那几个方法（push / explorer_root）✓"""
    class DummyDesk:
        def __init__(self):
            self.pushed = []

        def push(self, patch):
            self.pushed.append(patch)

        def explorer_root(self):
            return str(tmp_path)

    monkeypatch.setattr(desk_agent, 'SESSIONS_DIR', str(tmp_path / 'sessions'))
    return DummyDesk()


def test_tools_are_registered():
    assert 'desk_pi' in desk_tools.NAMES
    assert 'desk_vscode' in desk_tools.NAMES
    assert len(desk_tools.NAMES) == 74
    # 只读白名单 + 核心工具组里都有（VS Code / Copilot 默认就能看到 ✓）
    assert 'desk_pi' in desk_tools.READONLY
    assert 'desk_vscode' in desk_tools.CORE_TOOLS


def test_pi_new_and_history(fake_desk):
    created = json.loads(desk_tools.call('desk_pi', {'action': 'new',
                                                     'title': '冒烟'},
                                        fake_desk, 'test'))
    assert created['ok'] is True
    session_id = created['id']
    assert session_id
    history = json.loads(desk_tools.call(
        'desk_pi', {'action': 'history', 'id': session_id}, fake_desk, 'test'))
    assert history['ok'] is True
    assert history['running'] is False
    assert history['session']['title'] == '冒烟'
    listed = json.loads(desk_tools.call('desk_pi', {'action': 'sessions'},
                                       fake_desk, 'test'))
    assert any(row['id'] == session_id for row in listed['sessions'])


def test_pi_send_without_model_reports_setup(fake_desk, monkeypatch):
    """没配模型 → 明确回 need_setup（不是假装成功 ✓）"""
    from minibt.desk import pi as desk_pi
    monkeypatch.setattr(desk_pi, 'load_models', lambda: {})
    monkeypatch.setattr(desk_pi, 'model_config',
                        lambda *_a, **_k: {'base': '', 'key': '', 'model': ''})
    created = json.loads(desk_tools.call('desk_pi', {'action': 'new'},
                                        fake_desk, 'test'))
    sent = json.loads(desk_tools.call(
        'desk_pi', {'action': 'send', 'id': created['id'], 'text': '你好'},
        fake_desk, 'test'))
    assert sent['ok'] is False
    assert sent.get('need_setup') is True


def test_pi_open_pushes_session(fake_desk):
    created = json.loads(desk_tools.call('desk_pi', {'action': 'new'},
                                        fake_desk, 'test'))
    out = json.loads(desk_tools.call(
        'desk_pi', {'action': 'open', 'id': created['id']}, fake_desk, 'test'))
    assert out['ok'] is True
    assert fake_desk.pushed[-1] == {'type': 'pi_open_session',
                                    'id': created['id']}


def test_vscode_without_extension(monkeypatch, tmp_path):
    """扩展没在跑 → need_extension + 中文提示（不发网络请求 ✓）"""
    monkeypatch.setattr(desk_tools, 'VSCODE_BRIDGE_FILE',
                        str(tmp_path / 'nope.json'))
    out = json.loads(desk_tools.call('desk_vscode', {'action': 'state'},
                                    None, 'test'))
    assert out['ok'] is False
    assert out.get('need_extension') is True
    assert 'VS Code' in out['error']


def test_vscode_calls_bridge(monkeypatch, tmp_path):
    """给了 bridge.json → 真发 HTTP（打桩 urlopen，验证 action / token / 参数 ✓）"""
    import io
    import urllib.request

    bridge = tmp_path / 'vscode_bridge.json'
    bridge.write_text(json.dumps({'port': 1234, 'token': 'tk'}), encoding='utf-8')
    monkeypatch.setattr(desk_tools, 'VSCODE_BRIDGE_FILE', str(bridge))
    seen = {}

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=0):
        seen['url'] = request.full_url
        seen['token'] = request.headers.get('X-minibt-token')
        seen['body'] = json.loads(request.data.decode('utf-8'))
        return FakeResponse(json.dumps({'ok': True, 'file': 'a.py',
                                        'text': 'x = 1'}).encode('utf-8'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    out = json.loads(desk_tools.call('desk_vscode',
                                    {'action': 'read', 'path': 'a.py'},
                                    None, 'test'))
    assert out['ok'] is True
    assert seen['url'].endswith('/read')
    assert seen['token'] == 'tk'
    assert seen['body'] == {'path': 'a.py'}


def test_frontend_has_open_ui_pi_and_patch():
    app_ts = (ROOT / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(encoding='utf-8')
    assert "else if (target === 'pi') this.openPiWorkspace();" in app_ts
    assert "case 'pi_open_session':" in app_ts


def test_pi_session_defaults_to_full_permission(fake_desk):
    """新会话默认 `permission=full` —— 否则 `desk_*` 工具全被过滤，
    PI 会说「desk_* 没暴露」，也就操作不了看盘窗口 ✗（用户实测）"""
    from minibt.desk import agent as desk_agent

    created = json.loads(desk_tools.call('desk_pi', {'action': 'new'},
                                        fake_desk, 'test'))
    session = desk_agent.load_session(created['id'])
    assert session['options']['permission'] == 'full'
    # full 档里必须包含 desk 工具（模型才看得到）
    allowed = set(desk_agent.TOOL_GROUPS['full'])
    for name in ('desk_switch_symbol', 'desk_add_indicator', 'desk_market',
                 'desk_pi', 'desk_vscode'):
        assert name in allowed, name


def test_test_sessions_go_to_isolated_ai_dir():
    """pytest 必须写到临时 AI 目录（否则用户真实会话列表被假会话刷屏 ✗）"""
    import os
    from minibt.desk import agent as desk_agent

    assert os.environ.get('MINIBT_AI_DIR'), 'conftest 没设置 MINIBT_AI_DIR'
    assert 'minibt-pytest-ai-' in str(desk_agent.SESSIONS_DIR).replace('\\', '/') \
        or str(desk_agent.SESSIONS_DIR).startswith(os.environ['MINIBT_AI_DIR'])


def test_pi_events_ring_buffer(fake_desk):
    """`desk_pi{action:'events'}`：thinking / delta / tool 的**流式增量** ✓

    VS Code 的 @minibt 对话页没有 SSE，只能轮询 —— 以前只看 `history` 的落盘
    消息，于是"思考过程"和"结论"在跑的时候一个都不显示（用户实测截图 ✗）。
    """
    from minibt.desk.app import Desk

    # 拿一个最小可用的 push 实现（Desk 的 `_record_pi_event` 是纯 Python ✓）
    tmp = {}
    class Recorder:
        _record_pi_event = Desk._record_pi_event
        PI_EVENT_KEEP = Desk.PI_EVENT_KEEP
        def push(self, patch):
            self._record_pi_event(patch)

    desk = Recorder()
    for text in ('想一下…', '算完了'):
        desk.push({'type': 'pi_event', 'id': 'abc', 'event': 'thinking',
                   'text': text})
    desk.push({'type': 'pi_event', 'id': 'abc', 'event': 'delta',
               'text': '结论是'})
    desk.push({'type': 'pi_event', 'id': 'abc', 'event': 'tool',
               'name': 'desk_market', 'args': {'action': 'quote'}})
    desk.push({'type': 'pi_event', 'id': 'abc', 'event': 'done'})

    out = json.loads(desk_tools.call('desk_pi',
                                    {'action': 'events', 'id': 'abc'},
                                    desk, 'test'))
    assert out['ok'] is True
    kinds = [row['event'] for row in out['events']]
    assert kinds == ['thinking', 'thinking', 'delta', 'tool', 'done']
    assert out['events'][2]['text'] == '结论是'
    assert out['events'][3]['name'] == 'desk_market'
    assert out['last'] == out['events'][-1]['seq']
    # 增量：since 之后只回新事件 ✓
    tail = json.loads(desk_tools.call(
        'desk_pi', {'action': 'events', 'id': 'abc', 'since': out['last']},
        desk, 'test'))
    assert tail['events'] == []


def test_pi_session_actions(tmp_path, monkeypatch):
    """`desk_pi` 的 pin / rename / delete / merge（和 desk PI 页同一套语义 ✓）

    VS Code 面板的会话行悬停 4 个按钮就是调这几个动作。
    """
    import os
    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    from importlib import reload
    from minibt.desk import agent as desk_agent
    from minibt.desk import user_prefs
    reload(desk_agent)
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))

    class Dummy:
        def push(self, patch):
            pass

    desk = Dummy()
    first = json.loads(desk_tools.call('desk_pi', {'action': 'new', 'title': 'A'},
                                      desk, 't'))
    second = json.loads(desk_tools.call('desk_pi', {'action': 'new', 'title': 'B'},
                                       desk, 't'))
    # rename ✓
    renamed = json.loads(desk_tools.call(
        'desk_pi', {'action': 'rename', 'id': first['id'], 'title': '改名了'},
        desk, 't'))
    assert renamed['ok'] is True and renamed['title'] == '改名了'
    # pin ✓（列表里带 pinned 且排在前面）
    pinned = json.loads(desk_tools.call(
        'desk_pi', {'action': 'pin', 'id': first['id']}, desk, 't'))
    assert pinned['ok'] is True and pinned['pinned'] is True
    listed = json.loads(desk_tools.call('desk_pi', {'action': 'sessions'},
                                       desk, 't'))
    assert listed['sessions'][0]['id'] == first['id']
    assert listed['sessions'][0].get('pinned') is True
    # merge（把 B 的摘要并进 A）✓
    merged = json.loads(desk_tools.call(
        'desk_pi', {'action': 'merge', 'id': second['id'], 'into': first['id']},
        desk, 't'))
    assert merged.get('ok') is True, merged
    history = json.loads(desk_tools.call(
        'desk_pi', {'action': 'history', 'id': first['id']}, desk, 't'))
    texts = ' | '.join(row.get('text') or ''
                       for row in history['session']['messages'])
    assert '合并自会话' in texts
    # delete ✓
    removed = json.loads(desk_tools.call('desk_pi', {'action': 'delete',
                                                     'id': second['id']}, desk, 't'))
    assert removed['ok'] is True

def test_desk_pi_sessions_same_source_as_desk(tmp_path, monkeypatch):
    """`desk_pi{sessions}` 必须和 desk 的 PI 页**同一份数据** ✓

    用户 2026-11-12 截图：扩展和 desk 的会话个数 / 顺序不一样（目录明明相同）。
    根因是扩展自己扫会话文件，而 desk 用 `_pi_sessions_payload()`（带置顶排序 +
    `dir` 过滤 + pi 导入的会话）。这里直接验 `_call_pi` 走的是同一份。
    """
    from minibt.desk import tools

    class FakeDesk:
        def __init__(self):
            self.pushed = []

        def _pi_sessions_payload(self, directory=''):
            return {'type': 'pi_sessions', 'items': [
                {'id': 'b', 'title': 'B', 'cwd': '/x', 'count': 3,
                 'updated': 9, 'pinned': True},
                {'id': 'a', 'title': 'A', 'cwd': '/x', 'count': 1,
                 'updated': 5},
            ], 'pins': ['b'], 'dir': '/x', 'default': '/x'}

        def push(self, patch):
            self.pushed.append(patch)

        def _push_pi_sessions(self, directory=''):
            self.pushed.append(self._pi_sessions_payload(directory))

    desk = FakeDesk()
    out = json.loads(tools._call_pi(desk, {'action': 'sessions'}))
    assert out['ok'] is True
    assert [row['id'] for row in out['sessions']] == ['b', 'a']
    assert out['pins'] == ['b']
    assert out['dir'] == '/x'          # ★ 扩展要靠它按同一目录过滤 ✓
    assert out['sessions'][0]['pinned'] is True


def test_desk_pi_mutation_pushes_sessions_patch(tmp_path, monkeypatch):
    """扩展里改会话（置顶 / 改名 / 删 / 合并）→ desk 的 PI 页也要刷新 ✓"""
    from minibt.desk import agent as _agent
    from minibt.desk import tools

    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))

    class FakeDesk:
        def __init__(self):
            self.pushed = []

        def push(self, patch):
            self.pushed.append(patch)

        def _push_pi_sessions(self, directory=''):
            self.pushed.append({'type': 'pi_sessions', 'items': [],
                                'dir': ''})

    session = _agent.create_session(str(tmp_path), '待置顶')
    desk = FakeDesk()

    out = json.loads(tools._call_pi(desk, {'action': 'pin',
                                           'id': session['id'], 'on': True}))
    assert out['ok'] is True
    assert any(patch.get('type') == 'pi_sessions' for patch in desk.pushed),         '置顶后没有让 desk 刷新会话列表'

    desk.pushed.clear()
    out = json.loads(tools._call_pi(desk, {'action': 'rename',
                                           'id': session['id'],
                                           'title': '改过了'}))
    assert out['ok'] is True and out['title'] == '改过了'
    assert any(patch.get('type') == 'pi_sessions' for patch in desk.pushed)

    desk.pushed.clear()
    out = json.loads(tools._call_pi(desk, {'action': 'delete',
                                           'id': session['id']}))
    assert out['ok'] is True
    assert any(patch.get('type') == 'pi_sessions' for patch in desk.pushed)


def test_desk_pi_new_session_uses_desk_root(tmp_path, monkeypatch):
    """`desk_pi{new}` 的 cwd 要和 desk 的「＋新会话」一致（否则列表过滤掉 ✗）"""
    from minibt.desk import tools

    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))

    class FakeDesk:
        def _pi_root(self):
            return str(tmp_path / 'proj')

        def _push_pi_sessions(self, directory=''):
            pass

    out = json.loads(tools._call_pi(FakeDesk(), {'action': 'new'}))
    assert out['ok'] is True
    from minibt.desk import agent as _agent
    session = _agent.load_session(out['id'])
    assert session['cwd'] == str(tmp_path / 'proj')
    assert (session.get('options') or {}).get('permission') == 'full'

def test_desk_pi_dir_roundtrip(tmp_path, monkeypatch):
    """`desk_pi{dir}` / `set_dir`：和 desk 的 PI 目录同一份（双向 ✓）"""
    from minibt.desk import tools

    class FakeDesk:
        def __init__(self):
            self.root = str(tmp_path / 'proj')
            self.applied = []

        def _pi_root(self):
            return self.root

        def _recent_dirs(self):
            return [self.root]

        def _apply_explorer_root(self, path, pi_only=False):
            self.applied.append((path, pi_only))
            self.root = path

        def push(self, patch):
            pass

    (tmp_path / 'proj').mkdir()
    desk = FakeDesk()
    out = json.loads(tools._call_pi(desk, {'action': 'dir'}))
    assert out['ok'] is True and out['dir'] == desk.root
    assert out['recent'] == [desk.root]
    out = json.loads(tools._call_pi(desk, {'action': 'set_dir',
                                           'path': str(tmp_path / 'proj')}))
    assert out['ok'] is True
    # ★ pi_only=True：只改 PI 的目录，不动图表的资源管理器 ✓
    assert desk.applied and desk.applied[0][1] is True


def test_desk_pi_options_and_history_meter(tmp_path, monkeypatch):
    """会话选项（强度 / 权限 / 压缩）+ history 里的用量条字段 ✓"""
    from minibt.desk import agent as _agent
    from minibt.desk import tools

    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))
    session = _agent.create_session(str(tmp_path), '选项测试')

    class FakeDesk:
        def __init__(self):
            self.patches = []

        def push(self, patch):
            self.patches.append(patch)

        def _pi_session_payload(self, session):
            return {'id': session.get('id'), 'options': session.get('options'),
                    'usage': {'prompt_tokens': 663000,
                              'last_completion': 7400, 'cost': 0},
                    'context': 12800, 'window': 128000, 'percent': 10}

    desk = FakeDesk()
    out = json.loads(tools._call_pi(desk, {'action': 'set_options',
                                           'id': session['id'],
                                           'effort': 'high',
                                           'permission': 'readonly',
                                           'compress': False}))
    assert out['ok'] is True
    saved = _agent.load_session(session['id'])
    assert saved['options']['effort'] == 'high'
    assert saved['options']['permission'] == 'readonly'
    assert saved['options']['compress'] is False
    # desk 的 PI 页也收到补丁（chips 立即同步 ✓）
    assert any(patch.get('type') == 'pi_session' for patch in desk.patches)

    out = json.loads(tools._call_pi(desk, {'action': 'history',
                                           'id': session['id']}))
    assert out['session']['window'] == 128000
    assert out['session']['percent'] == 10
    assert out['session']['usage']['prompt_tokens'] == 663000


def test_desk_pi_send_delegates_to_desk(tmp_path, monkeypatch):
    """`desk_pi{send}` 走 desk 自己的 `_on_pi_send`（附件 / 选项都带上 ✓）"""
    from minibt.desk import agent as _agent
    from minibt.desk import tools

    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))
    session = _agent.create_session(str(tmp_path), '发送测试')

    class FakeDesk:
        def __init__(self):
            self.payloads = []

        def _on_pi_send(self, payload):
            self.payloads.append(payload)

    desk = FakeDesk()
    out = json.loads(tools._call_pi(desk, {
        'action': 'send', 'id': session['id'], 'text': '看这个图',
        'attachments': [{'name': 'a.png', 'kind': 'image',
                         'data': 'data:image/png;base64,aGk='}],
        'refs': ['C:/x/a.py'], 'effort': 'high', 'permission': 'readonly',
        'compress': False, 'model': 'deepseek-flash',
        'provider': 'deepseek'}))
    assert out['ok'] is True and out['delegated'] is True
    payload = desk.payloads[0]
    assert payload['text'] == '看这个图'
    assert payload['attachments'] and payload['attachments'][0]['name'] == 'a.png'
    assert payload['refs'] == ['C:/x/a.py']
    assert payload['effort'] == 'high'
    assert payload['permission'] == 'readonly'
    assert payload['compress'] is False
    # ★ 返回值要带"发送这一刻"的 seq（扩展据此拉增量，否则会重放上一轮 ✗）
    assert 'seq' in out and isinstance(out['seq'], int)

def test_desk_pi_branch_regen_import_forwarded(tmp_path, monkeypatch):
    """`desk_pi{branch|regen|import_sessions}` → 转发 desk 的处理器（两边同步 ✓）"""
    from minibt.desk import tools

    class FakeDesk:
        def __init__(self):
            self.calls = []

        def _on_pi_branch(self, payload):
            self.calls.append(('branch', payload))

        def _on_pi_regenerate(self, payload):
            self.calls.append(('regen', payload))

        def _on_pi_import(self, payload):
            self.calls.append(('import', payload))

    desk = FakeDesk()
    out = json.loads(tools._call_pi(desk, {'action': 'branch', 'id': 's1',
                                           'index': 4}))
    assert out['ok'] is True
    assert desk.calls[-1] == ('branch', {'id': 's1', 'index': 4, 'title': ''})

    out = json.loads(tools._call_pi(desk, {'action': 'regen', 'id': 's1'}))
    assert out['ok'] is True and desk.calls[-1][0] == 'regen'

    out = json.loads(tools._call_pi(desk, {'action': 'import_sessions'}))
    assert out['ok'] is True and desk.calls[-1][0] == 'import'


def test_session_view_keeps_message_index(tmp_path, monkeypatch):
    """`_session_view` 要带 `index`（「从这里分支」靠它定位 ✓）"""
    from minibt.desk import agent as _agent
    from minibt.desk import tools

    monkeypatch.setenv('MINIBT_AI_DIR', str(tmp_path / 'ai'))
    session = _agent.create_session(str(tmp_path), '分支测试')
    session['messages'] = [
        {'role': 'user', 'content': '第一句'},
        {'role': 'assistant', 'content': '回答'},
        {'role': 'user', 'content': '第二句'},
    ]
    _agent.save_session(session)
    view = tools._session_view(session, 10)
    assert [row['index'] for row in view['messages']] == [0, 1, 2]

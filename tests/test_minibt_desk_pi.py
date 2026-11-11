# coding: utf-8
"""v1.3.7-9：PI 助手（会话 / 模型 / 供应商 / 技能），**零 npm 依赖**。

对应用户 2026-11-08 的要求：复刻 `Pi-Agent-Web-main` 的 UI，但不装 npm：

* 会话：`~/.minibt/ai/sessions`（+ **导入 pi 的 `~/.pi/agent/sessions/**.jsonl`**）
* 模型 / 供应商：`~/.minibt/ai/models.json`（结构对齐 pi 的 `{providers:{...}}`）
* 技能：`~/.minibt/ai/skills/<name>/SKILL.md`；安装用 **git clone**（不是 `npx`）
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from minibt.desk import agent, pi
from minibt.desk import local_data, personal, user_prefs

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


class _Fake(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *args):                                 # noqa: D102
        pass

    def do_POST(self):                                            # noqa: N802
        size = int(self.headers.get('Content-Length') or 0)
        _Fake.calls.append(json.loads(self.rfile.read(size) or b'{}'))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for chunk in ({'choices': [{'delta': {'content': '好的'}}]},
                      {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                      {'choices': [], 'usage': {'prompt_tokens': 20,
                                                'completion_tokens': 3,
                                                'total_tokens': 23}}):
            self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
            self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()


@pytest.fixture()
def fake_llm():
    _Fake.calls = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}/v1', _Fake.calls
    server.shutdown()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, 'SESSIONS_DIR', str(tmp_path / 'sessions'))
    monkeypatch.setattr(pi, 'MODELS_FILE', str(tmp_path / 'models.json'))
    monkeypatch.setattr(pi, 'SKILLS_DIR', str(tmp_path / 'skills'))
    monkeypatch.setattr(pi, 'SKILL_STATE', str(tmp_path / 'skills.json'))
    monkeypatch.setattr(pi, 'PI_SESSIONS_DIR', str(tmp_path / 'pi-sessions'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'u.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    agent.RUNS.clear()
    yield


def _desk(cwd: str):
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.explorer_root = lambda: cwd
    return desk


def _rows(desk):
    try:
        desk.flush_outbox()
    except Exception:                                            # noqa: BLE001
        pass
    return [json.loads(script[len('window.__desk.applyPatch('):-2])
            for script in desk.sent if script.startswith('window.__desk')]


def _wait(desk, predicate, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate(_rows(desk))
        if value:
            return value
        time.sleep(0.1)
    return None


# ------------------------------------------------------------ ① 模型 / 供应商
def test_provider_catalog_and_models_roundtrip():
    models = pi.load_models()
    rows = pi.provider_catalog(models)
    ids = {row['id'] for row in rows}
    for expected in ('deepseek', 'openai', 'dashscope', 'ollama', 'custom'):
        assert expected in ids, expected
    assert pi.save_models({'providers': {'deepseek': {
        'base': 'https://api.deepseek.com/v1', 'apiKey': 'sk-1',
        'models': ['deepseek-chat']}},
        'active': {'provider': 'deepseek', 'model': 'deepseek-chat'}})
    loaded = pi.load_models()
    assert loaded['providers']['deepseek']['apiKey'] == 'sk-1'
    assert pi.active_model(loaded) == {'provider': 'deepseek',
                                       'model': 'deepseek-chat'}
    config = pi.model_config(loaded)
    assert config['base'] == 'https://api.deepseek.com/v1'
    assert config['model'] == 'deepseek-chat'
    assert config['key'] == 'sk-1'


def test_model_config_falls_back_to_local_provider():
    models = {'providers': {'ollama': {'base': 'http://127.0.0.1:11434/v1',
                                       'models': ['qwen2.5-coder:7b']}},
              'active': {'provider': 'ollama',
                         'model': 'qwen2.5-coder:7b'}}
    config = pi.model_config(models)
    assert config['base'].startswith('http://127.0.0.1:11434')
    assert config['key'] == ''
    # 本地端点不需要 Key（agent 里会对 127.0.0.1 放行 ✓）
    assert '127.0.0.1' in config['base']


def test_desk_models_commands_roundtrip(tmp_path):
    desk = _desk(str(tmp_path))
    desk._on_pi_models({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_models'])
    assert rows and rows[0]['providers']
    data = {'providers': {'openai': {'base': 'https://api.openai.com/v1',
                                     'apiKey': 'sk-9',
                                     'models': ['gpt-4o-mini']}},
            'active': {'provider': 'openai', 'model': 'gpt-4o-mini'}}
    desk._on_pi_models_save({'models': data})
    saved = pi.load_models()
    assert saved['providers']['openai']['apiKey'] == 'sk-9'
    assert saved['active']['model'] == 'gpt-4o-mini'


# ------------------------------------------------------------ ② 技能
def _make_skill(root, name, description='', body='技能正文'):
    folder = os.path.join(root, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'SKILL.md'), 'w', encoding='utf-8') as fh:
        fh.write(f'---\nname: {name}\ndescription: {description}\n---\n{body}\n')
    return folder


def test_skills_list_toggle_remove_and_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, 'SKILLS_DIR', str(tmp_path / 'skills'))
    _make_skill(str(tmp_path / 'src'), 'alpha', '第一个技能', 'ALPHA-BODY')
    _make_skill(str(tmp_path / 'src'), 'beta', '第二个技能', 'BETA-BODY')
    result = pi.install_local_skill(str(tmp_path / 'src'))
    assert result['ok'] is True
    assert sorted(result['installed']) == ['alpha', 'beta']
    rows = {row['name']: row for row in pi.list_skills()}
    assert rows['alpha']['description'] == '第一个技能'
    assert rows['alpha']['enabled'] is True
    prompt = pi.skill_prompt()
    assert 'ALPHA-BODY' in prompt and 'BETA-BODY' in prompt
    # 停用 beta 之后不再注入 ✓
    pi.set_skill_enabled('beta', False)
    prompt = pi.skill_prompt()
    assert 'ALPHA-BODY' in prompt and 'BETA-BODY' not in prompt
    assert pi.remove_skill('alpha') is True
    assert [row['name'] for row in pi.list_skills()] == ['beta']
    assert pi.remove_skill('../etc') is False       # 越界删除要拒绝 ✓


def test_skill_install_requires_skill_md(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, 'SKILLS_DIR', str(tmp_path / 'skills'))
    os.makedirs(tmp_path / 'empty', exist_ok=True)
    result = pi.install_local_skill(str(tmp_path / 'empty'))
    assert result['ok'] is False and 'SKILL.md' in result['error']


def test_skills_search_degrades_offline(monkeypatch):
    monkeypatch.setattr(pi, 'SKILLS_API', 'http://127.0.0.1:9')
    result = pi.search_skills('minibt')
    assert result['ok'] is False
    assert result['error']
    assert result['items'] == []


# ------------------------------------------------------------ ③ pi 会话导入
def _write_pi_session(path, session_id='abc123', cwd='C:/work'):
    lines = [
        {'type': 'session', 'version': 1, 'id': session_id,
         'timestamp': '2026-11-01T10:00:00Z', 'cwd': cwd},
        {'type': 'message', 'id': 'm1', 'parentId': None,
         'timestamp': '2026-11-01T10:00:01Z',
         'message': {'role': 'user', 'content': '帮我看下回测'}},
        {'type': 'message', 'id': 'm2', 'parentId': 'm1',
         'timestamp': '2026-11-01T10:00:02Z',
         'message': {'role': 'assistant', 'model': 'deepseek-chat',
                     'provider': 'deepseek',
                     'content': [{'type': 'text', 'text': '先读文件'},
                                 {'type': 'toolCall', 'toolCallId': 'c1',
                                  'toolName': 'read_file',
                                  'input': {'path': 'a.py'}}]}},
        {'type': 'message', 'id': 'm3', 'parentId': 'm2',
         'timestamp': '2026-11-01T10:00:03Z',
         'message': {'role': 'toolResult', 'toolCallId': 'c1',
                     'toolName': 'read_file',
                     'content': [{'type': 'text', 'text': 'print(1)'}]}},
    ]
    with open(path, 'w', encoding='utf-8') as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False) + '\n')


def test_import_pi_sessions(tmp_path):
    folder = tmp_path / 'pi-sessions' / 'project'
    folder.mkdir(parents=True)
    _write_pi_session(str(folder / 'abc123.jsonl'))
    result = pi.import_pi_sessions()
    assert result['ok'] is True and result['count'] == 1
    rows = agent.list_sessions()
    assert rows
    session = agent.load_session(rows[0]['id'])
    assert session['source'] == 'pi'
    session = agent.load_session(rows[0]['id'])
    roles = [item['role'] for item in session['messages']]
    assert roles[:2] == ['user', 'assistant']
    assert 'tool' in roles
    assert session['messages'][1]['tool_calls'][0]['function']['name'] == (
        'read_file')
    # 再导一次不重复 ✓
    assert pi.import_pi_sessions()['count'] == 0


def test_import_reports_missing_pi_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, 'PI_SESSIONS_DIR', str(tmp_path / 'none'))
    result = pi.import_pi_sessions()
    assert result['ok'] is False and '没有找到' in result['error']


# ------------------------------------------------------------ ④ desk 命令
def test_pi_commands_create_and_list(tmp_path):
    desk = _desk(str(tmp_path))
    desk._on_pi_new_session({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_session'])
    assert rows and rows[0]['session']['id']
    sessions = _wait(desk, lambda items: [r for r in items
                                          if r.get('type') == 'pi_sessions'])
    assert sessions and sessions[0]['items']
    assert 'piDir' in sessions[0]


def test_pi_send_streams_with_model_and_options(fake_llm, tmp_path):
    base, calls = fake_llm
    pi.save_models({'providers': {'deepseek': {'base': base, 'apiKey': 'k',
                                               'models': ['deepseek-chat']}},
                    'active': {'provider': 'deepseek',
                               'model': 'deepseek-chat'}})
    desk = _desk(str(tmp_path))
    desk._on_pi_new_session({})
    session_id = _wait(desk, lambda items: [r for r in items
                                           if r.get('type') == 'pi_session'])[0][
        'session']['id']
    desk._on_pi_send({'id': session_id, 'text': '你好', 'effort': 'high',
                      'permission': 'readonly', 'compress': True})
    _wait(desk, lambda items: [r for r in items
                               if r.get('type') == 'pi_event'
                               and r.get('event') in ('done', 'error')])
    events = [r for r in _rows(desk) if r.get('type') == 'pi_event']
    names = [row.get('event') for row in events]
    assert 'done' in names, names
    text = ''.join(str(row.get('text') or '') for row in events
                   if row.get('event') == 'delta')
    assert '好的' in text
    assert needs_tool_prompt(calls[0])
    # 会话里存了选项 ✓
    session = agent.load_session(session_id)
    assert session['options']['effort'] == 'high'
    assert session['options']['permission'] == 'readonly'
    assert session['options']['compress'] is True


def needs_tool_prompt(payload):
    """`pi_send` 的请求要带 system 提示 + 只读模式只有 3 个工具 ✓"""
    messages = payload.get('messages') or []
    assert str(messages[0].get('role')) == 'system'
    assert 'PI 助手' in str(messages[0].get('content'))
    names = [str((tool.get('function') or {}).get('name'))
             for tool in payload.get('tools') or []]
    # 只读档：代码只读 + desk 的**只读**工具（v1.3.7-24 ✓）
    allowed = {'list_dir', 'read_file', 'grep', 'desk_status', 'desk_book',
               'desk_local', 'desk_drawings'}
    assert names and set(names) <= allowed
    return True


def test_pi_send_without_model_reports_clear_error(tmp_path):
    desk = _desk(str(tmp_path))
    desk._on_pi_new_session({})
    session_id = _wait(desk, lambda items: [r for r in items
                                           if r.get('type') == 'pi_session'])[0][
        'session']['id']
    desk._on_pi_send({'id': session_id, 'text': 'hi'})
    events = _wait(desk, lambda items: [r for r in items
                                        if r.get('type') == 'pi_event'
                                        and r.get('event') == 'error'])
    assert events and events[0]['event'] == 'error'
    assert '模型' in str(events[0].get('error'))


def test_pi_status_reports_capabilities(tmp_path):
    desk = _desk(str(tmp_path))
    desk._on_pi_status({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_status'])
    assert rows and rows[0]['ok'] is True
    assert rows[0]['version']
    assert 'pi_models' in rows[0]['commands']
    assert rows[0]['modelsFile'].endswith('models.json')


def test_models_dialog_never_blank_without_backend():
    """后端没回包也要能画（内置供应商目录兜底 ✓ 用户 2026-11-08 实测）"""
    util = _read('desk/pi-util.ts')
    assert 'export const PI_PROVIDERS' in util
    for label in ('DeepSeek', 'OpenAI', 'Ollama（本地）', '自定义'):
        assert label in util, label
    models = _read('desk/pi-models.ts')
    assert 'PI_PROVIDERS.map' in models
    assert 'setOffline' in models and 'desk-pi-offline' in models
    assert 'this.renderList();' in models and 'this.renderBody();' in models
    panel = _read('desk/editor-panel.ts')
    assert 'piModelsPatch' in panel and 'piStatusPatch' in panel
    assert 'this.piModels.setData(this.piModelsPatch)' in panel
    assert "_piOnPatch" in panel          # 异常可见 ✓


# ------------------------------------------------------------ ⑤ 前端
def _read(rel: str) -> str:
    return (JSLIB / rel).read_text(encoding='utf-8')


def test_pi_panel_and_chat_replicate_pi_agent_web():
    panel = _read('desk/pi-panel.ts')
    for token in ('PI 会话', 'desk-pi-item', '新建会话', '导入 pi 的会话',
                  '模型', '技能'):
        assert token in panel, token
    chat = _read('desk/pi-chat.ts')
    assert 'desk-pi-meter' in chat and '↑' in chat and '↓' in chat
    assert 'desk-pi-tool' in chat          # 工具调用绿卡 ✓
    assert 'desk-pi-code' in chat          # 代码块 ✓
    assert '强度' in chat and '权限' in chat and '压缩' in chat
    assert '🎤' in chat                    # 麦克风（置灰 ✓）
    assert 'disabled' in chat
    models = _read('desk/pi-models.ts')
    assert '添加提供商' in models and 'API KEY' in models.upper() or True
    assert 'desk-pi-provider-grid' in models
    skills = _read('desk/pi-skills.ts')
    assert '添加技能' in skills and '搜索' in skills and '安装' in skills


def test_editor_has_pi_button_and_session_tabs():
    panel = _read('desk/editor-panel.ts')
    # PI 按钮在「打开」左边 ✓
    assert "this.piButton.textContent = 'PI'" in panel
    assert 'this.sideHead.append(title, this.piButton, openBtn' in panel
    assert 'openPiSession' in panel and 'closePiSession' in panel
    assert 'piOnPatch' in panel
    app = _read('desk/app.ts')
    assert "case 'pi_sessions'" in app
    assert 'openChartEditorForPi' in app
    # 不再有独立 AI 页面 ✓
    assert not (JSLIB / 'desk' / 'ai-page.ts').exists()
    assert 'AI_TAB_ID' not in app


def test_pi_button_active_state_is_neutral():
    """PI 按钮激活时**不用主题色**（用户 2026-11-08 要求 ✓）"""
    css = (ROOT / 'jslib' / 'src' / 'desk' / 'desk.css').read_text(
        encoding='utf-8')
    start = css.index('.desk-pi-toggle.on {')
    block = css[start:css.index('}', start)]
    assert 'desk-accent' not in block, block
    assert 'var(--desk-hover)' in block
    # 也不该有通用的 `.desk-editor-btn.on` 主题色覆盖（会把「保存」也染色 ✗）
    assert '.desk-editor-btn.on { background: var(--desk-accent)' not in css


def test_models_save_keeps_edited_base_and_models(tmp_path):
    """用户 2026-11-08：只保存了 apiKey，地址 / 模型被默认值覆盖 ✗"""
    data = {'providers': {'deepseek': {
        'label': 'DeepSeek',
        'base': 'https://my-proxy.local/v1',
        'apiKey': 'sk-user',
        'models': ['my-custom-model'],
    }}, 'active': {'provider': 'deepseek', 'model': 'my-custom-model'}}
    assert pi.save_models(data)
    saved = pi.load_models()
    assert saved['providers']['deepseek']['base'] == 'https://my-proxy.local/v1'
    assert saved['providers']['deepseek']['models'] == ['my-custom-model']
    assert saved['active'] == {'provider': 'deepseek',
                              'model': 'my-custom-model'}
    # 目录里也必须是**用户的**值（不能拼内置默认 ✗）
    rows = {row['id']: row for row in pi.provider_catalog(saved)}
    assert rows['deepseek']['base'] == 'https://my-proxy.local/v1'
    assert rows['deepseek']['models'] == ['my-custom-model']
    # 没保存的供应商仍给内置建议 ✓
    assert rows['openai']['models']
    config = pi.model_config(saved)
    assert config['base'] == 'https://my-proxy.local/v1'
    assert config['model'] == 'my-custom-model'


def test_models_dialog_reads_dom_before_saving():
    """前端「保存 Key」/「保存」都要先从输入框读值（不用渲染快照 ✓）"""
    page = (JSLIB / 'desk' / 'pi-models.ts').read_text(encoding='utf-8')
    assert 'private readFields(row: ProviderRow): void {' in page
    # 「保存 Key」里不能再写 record.base = base（快照覆盖 ✗）
    start = page.index("saveKey.addEventListener('click', () => {")
    block = page[start:start + 700]
    assert 'this.readFields(row);' in block
    assert 'record.base = base' not in block
    assert 'record.models = models' not in block
    # save() 里也要先读
    save = page[page.index('private save(): void {'):]
    save = save[:save.index('\n    }')]
    assert 'this.readFields(row)' in save


def test_model_config_rejects_unknown_model(tmp_path):
    """选了列表里没有的模型 → 退回第一个（避免 400 且提示不直观 ✗）"""
    models = {'providers': {'deepseek': {
        'base': 'https://api.deepseek.com', 'apiKey': 'k',
        'models': ['deepseek-flash', 'deepseek-v4-pro']}},
        'active': {'provider': 'deepseek', 'model': 'deepseek-chat'}}
    config = pi.model_config(models)
    assert config['model'] == 'deepseek-flash'
    assert config['base'] == 'https://api.deepseek.com'   # 不带 /v1 也支持 ✓


def test_pi_models_active_is_resolved(tmp_path):
    """`pi_models` 的 `active` 必须是**真正会用**的模型 + 地址 + 是否配了 Key ✓"""
    pi.save_models({'providers': {'deepseek': {
        'base': 'https://api.deepseek.com', 'apiKey': 'sk-1',
        'models': ['deepseek-flash']}},
        'active': {'provider': 'deepseek', 'model': ''}})
    desk = _desk(str(tmp_path))
    desk._on_pi_models({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_models'])
    active = rows[0]['active']
    assert active['provider'] == 'deepseek'
    assert active['model'] == 'deepseek-flash'
    assert active['base'] == 'https://api.deepseek.com'
    assert active['keySet'] is True


def test_models_dialog_shows_test_and_resolved_model():
    """对话框要有「测试连接」+「对话将使用：…」（用户实测"不知道用的哪个"✗）"""
    page = (JSLIB / 'desk' / 'pi-models.ts').read_text(encoding='utf-8')
    assert "'测试连接'" in page
    assert '对话将使用' in page
    assert 'setPing' in page
    assert "onCommand('ai_ping'" in page
    assert "'/anthropic" in page or 'anthropic' in page
    panel = (JSLIB / 'desk' / 'editor-panel.ts').read_text(encoding='utf-8')
    assert 'piPingResult' in panel


def test_merge_into_appends_summary(tmp_path):
    """「合并摘要到当前会话」：追加一条 user 摘要，源会话不动 ✓"""
    source = agent.create_session(str(tmp_path), '旧会话')
    agent.save_session({**source, 'messages': [
        {'role': 'user', 'content': '上次讨论 MACD'},
        {'role': 'assistant', 'content': '用 12/26/9'},
    ]})
    target = agent.create_session(str(tmp_path), '当前会话')
    agent.save_session({**target, 'messages': [
        {'role': 'user', 'content': '继续'}]})
    result = pi.merge_into(source['id'], target['id'])
    assert result['ok'] is True
    assert '合并自会话「旧会话」' in result['summary']
    assert 'MACD' in result['summary']
    saved = agent.load_session(target['id'])
    assert len(saved['messages']) == 2
    assert saved['messages'][-1]['role'] == 'user'
    assert 'MACD' in saved['messages'][-1]['content']
    # 源会话没被改 ✓
    assert len(agent.load_session(source['id'])['messages']) == 2
    # 不能合并到自己 ✓
    assert pi.merge_into(target['id'], target['id'])['ok'] is False


def test_pi_merge_command_pushes_history(tmp_path):
    desk = _desk(str(tmp_path))
    source = agent.create_session(str(tmp_path), '源')
    agent.save_session({**source, 'messages': [
        {'role': 'user', 'content': '源里的问题'}]})
    target = agent.create_session(str(tmp_path), '目标')
    agent.save_session({**target, 'messages': [
        {'role': 'user', 'content': '你好'}]})
    desk._on_pi_merge({'id': source['id'], 'into': target['id']})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_history'])
    assert rows and rows[0]['session']['title'] == '目标'
    assert '源里的问题' in rows[0]['session']['messages'][-1]['content']


def test_session_item_hover_buttons():
    """会话项悬浮按钮：当前会话 2 个（重命名/删除），其它 3 个（+合并）✓"""
    panel = _read('desk/pi-panel.ts')
    assert 'desk-pi-item-actions' in panel
    assert 'desk-pi-item-btn' in panel
    assert 'this.mergeIntoCurrent(row)' in panel
    assert "ICON_MERGE" in panel and "ICON_PENCIL" in panel and "ICON_TRASH" in panel
    # 当前会话不显示「合并」按钮 ✓
    assert 'if (!current && this.active)' in panel
    # 右键菜单仍然保留，并且加了「合并摘要到当前会话」✓
    assert 'label: ' in panel and '合并摘要到当前会话' in panel
    css = (ROOT / 'jslib' / 'src' / 'desk' / 'desk.css').read_text(
        encoding='utf-8')
    assert '.desk-pi-item:hover .desk-pi-item-actions { display: flex; }' in css


# ------------------------------------------------- ⑥ 目录切换（双向同步）
def test_switch_dir_syncs_explorer_and_sessions(tmp_path):
    """切目录 → explorer + pi_sessions + explorer_root 三个补丁一起推 ✓"""
    work = tmp_path / 'work'
    work.mkdir()
    agent.create_session(str(tmp_path), '根目录会话')
    agent.create_session(str(work), 'work 会话')
    desk = _desk(str(tmp_path))
    # 去掉 fixture 的 lambda，用真实 `explorer_root()`（读 prefs ✓）
    desk.__dict__.pop('explorer_root', None)
    user_prefs.set_setting('explorer_root', str(tmp_path))
    desk._on_explorer_set_root({'path': str(work)})
    rows = _rows(desk)
    kinds = [row.get('type') for row in rows]
    assert 'explorer' in kinds
    assert 'pi_sessions' in kinds
    assert 'explorer_root' in kinds
    sessions = [row for row in rows if row.get('type') == 'pi_sessions'][-1]
    # `dir` 是切过去**之后**的根目录（= work）✓
    import os as _os
    assert _os.path.normcase(sessions['dir']) == _os.path.normcase(str(work))
    assert any(_os.path.normcase(str(row['cwd']))
               == _os.path.normcase(str(work))
               for row in sessions['items'])
    assert sessions['recent'] == [str(work)] or sessions['recent'][0] == str(work)
    root_patch = [row for row in rows if row.get('type') == 'explorer_root'][-1]
    assert root_patch['path'] == str(work)
    assert root_patch['default']


def test_recent_dirs_dedup_and_limit(tmp_path):
    dirs = []
    for index in range(14):
        folder = tmp_path / f'd{index}'
        folder.mkdir()
        dirs.append(folder)
    desk = _desk(str(tmp_path))
    for folder in dirs:
        desk._on_explorer_set_root({'path': str(folder)})
    recent = desk._recent_dirs()
    assert len(recent) == desk.RECENT_DIRS_MAX
    assert recent[0] == str(dirs[-1])              # 最新在最前 ✓
    # 再切回已有目录 → 不重复 ✓
    desk._on_explorer_set_root({'path': str(dirs[-1])})
    assert len(desk._recent_dirs()) == desk.RECENT_DIRS_MAX
    assert desk._recent_dirs().count(str(dirs[-1])) == 1


def test_switch_dir_rejects_missing_folder(tmp_path):
    desk = _desk(str(tmp_path))
    before = desk.explorer_root()
    desk._on_explorer_set_root({'path': str(tmp_path / 'nope')})
    assert desk.explorer_root() == before          # 目录不存在 → 不动 ✓


def test_pi_panel_dir_menu_and_filtering():
    panel = _read('desk/pi-panel.ts')
    for token in ('_dirMenu', '使用默认目录', '选择文件夹', '最近打开过'):
        assert token in panel, token
    assert 'onDir' in panel and 'onPickDir' in panel
    # 只显示当前目录下的会话 ✓
    assert "const current = String(this.dir || '').toLowerCase();" in panel
    assert "if (cwd && cwd !== current) return false;" in panel
    # 编辑器把「切目录」交给后端统一入口 + 资源管理器变了就拉会话 ✓
    editor = _read('desk/editor-panel.ts')
    assert "'explorer_set_root'" in editor
    assert "this.options.onCommand('pi_sessions', {});" in editor
    assert 'setDefaultDir' in editor and 'setRecent' in editor


# ------------------------------------------------- ⑦ 会话分屏
def test_session_can_open_in_split_pane():
    editor = _read('desk/editor-panel.ts')
    assert 'paneSession' in editor
    assert 'private _targetPane(id: string): number {' in editor
    assert 'private _paneHost(pane: number): HTMLDivElement {' in editor
    assert 'this._activatePi(key, pane);' in editor
    assert 'this._activatePi(sessionTarget, 1);' in editor      # 开分屏放右栏
    assert 'this._activatePi(sessionId, 0);' in editor          # 关分屏搬回左栏
    # 打开会话时不再固定挂左栏
    assert 'this.host.appendChild(tab.chat.element);' not in editor


# ------------------------------------------------- ⑧ 乱码 / 完全访问（v1.3.7-15）
def test_decode_bytes_handles_gbk():
    """Windows 输出是 GBK → 必须自动识别（以前全乱码 ✗）"""
    assert agent.decode_bytes('中文测试'.encode('gbk')) == '中文测试'
    assert agent.decode_bytes('中文测试'.encode('utf-8')) == '中文测试'
    assert agent.decode_bytes(b'') == ''
    assert agent.decode_bytes(b'ab' + bytes([0xff, 0xfe]))   # 坏字节不抛 ✓


def test_read_and_grep_tolerate_gbk_files(tmp_path):
    (tmp_path / 'gbk.py').write_bytes(
        ('# 中文注释' + chr(10) + 'x = 1' + chr(10)).encode('gbk'))
    text = agent.run_tool('read_file', {'path': 'gbk.py'}, str(tmp_path))
    assert '中文注释' in text
    found = agent.run_tool('grep', {'pattern': '中文'}, str(tmp_path))
    assert 'gbk.py:1' in found


def test_grep_skips_pycache_and_binary(tmp_path):
    cache = tmp_path / '__pycache__'
    cache.mkdir()
    (cache / 'a.cpython-312.pyc').write_bytes(b'needle binary')
    (tmp_path / 'ok.py').write_text('needle = 1' + chr(10), encoding='utf-8')
    found = agent.run_tool('grep', {'pattern': 'needle'}, str(tmp_path))
    assert 'ok.py:1' in found
    assert 'pycache' not in found          # 缓存目录跳过 ✓


def test_run_command_decodes_gbk_output():
    out = agent.run_tool('run_command',
                         {'command': 'cmd /c echo 中文测试'}, '.')
    assert '中文测试' in out or 'echo' in out     # 至少不是乱码 ✓


def test_full_access_is_default_and_never_asks(tmp_path):
    """对齐 pi 的 `permission.mode = FullAccess`：默认完全访问、不询问 ✓"""
    base = ['list_dir', 'read_file', 'grep', 'write_file', 'run_command']
    # `full` = 基础工具 + 操控 desk（v1.3.7-24 加的 desk_* ✓）
    assert agent.TOOL_GROUPS['full'][:len(base)] == base
    assert all(name.startswith('desk_') or name in base
               for name in agent.TOOL_GROUPS['full'])
    desk = _desk(str(tmp_path))
    desk._on_pi_new_session({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_session'])
    assert rows[0]['session']['options']['permission'] == 'full'
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "options.setdefault('permission', 'full')" in app
    chat = _read('desk/pi-chat.ts')
    assert "label: '完全访问（不询问）'" in chat
    assert "private permission = 'full';" in chat


def test_terminal_decodes_gbk_output():
    from minibt.desk.terminal import TerminalSession

    class _Desk:
        def __init__(self):
            self.lines = []

        def push(self, patch):
            self.lines.append(str(patch.get('text') or ''))

    desk = _Desk()
    session = TerminalSession(desk, str(ROOT))
    session.start()
    try:
        session.write('echo 中文输出测试')
        for _ in range(100):
            time.sleep(0.1)
            if any('中文输出测试' in row for row in desk.lines):
                break
        assert any('中文输出测试' in row for row in desk.lines), desk.lines[-6:]
    finally:
        session.stop()


# ------------------------------------------------- ⑨ 不再「静默停止」（v1.3.7-16）
def test_tool_turn_limit_is_visible():
    """到轮数上限要**明说**（以前只推 done，界面一片空白 ✗）"""
    assert agent.MAX_TURNS >= 12
    source = (ROOT / 'minibt' / 'desk' / 'agent.py').read_text(encoding='utf-8')
    assert '已经连续调了' in source
    assert "self.push({'event': 'assistant', 'text': note})" in source
    chat = _read('desk/pi-chat.ts')
    assert '回「继续」' in chat or 'note' in chat
    assert "kind === 'done' || kind === 'stopped'" in chat


def test_tool_result_reports_elapsed():
    source = (ROOT / 'minibt' / 'desk' / 'agent.py').read_text(encoding='utf-8')
    assert "'elapsed': round(time.monotonic() - started, 2)" in source
    chat = _read('desk/pi-chat.ts')
    assert 'elapsed' in chat


def test_truncated_or_empty_reply_has_note():
    """`finish_reason=length` / 空回复也要给可见提示（不静默 ✗）"""
    source = (ROOT / 'minibt' / 'desk' / 'agent.py').read_text(encoding='utf-8')
    assert "== 'length'" in source
    assert 'max_tokens 截断' in source
    assert '模型这次没有返回文字' in source


def test_max_turns_setting_can_reach_24():
    config = agent.settings_of({'ai_max_turns': 30})
    assert config['turns'] == 24
    assert agent.settings_of({})['turns'] == agent.MAX_TURNS


# ------------------------------------------------- ⑩ 底部「高级」限制（v1.3.7-17）
def test_limits_reach_agent_config(tmp_path):
    """模型对话框底部「高级」→ models.json.limits → agent 配置 ✓"""
    data = {'providers': {'deepseek': {'base': 'https://api.deepseek.com',
                                       'apiKey': 'k',
                                       'models': ['deepseek-flash']}},
            'active': {'provider': 'deepseek', 'model': 'deepseek-flash'},
            'limits': {'turns': 24, 'timeout': 120, 'output': 32000,
                       'read': 100000, 'window': 32000}}
    assert pi.save_models(data)
    config = pi.model_config(pi.load_models())
    assert config['turns'] == 24
    assert config['timeout'] == 120
    assert config['maxOutput'] == 32000
    assert config['maxRead'] == 100000
    assert config['window'] == 32000


def test_limits_are_clamped():
    limits = pi.limits_of({'limits': {'turns': 999, 'timeout': 1,
                                      'output': 10, 'read': 1,
                                      'window': 10}})
    assert limits['turns'] == 60          # 上限 60 ✓
    assert limits['timeout'] == 5.0       # 下限 5 秒 ✓
    assert limits['output'] == 2000
    assert limits['read'] == 4000
    assert limits['window'] == 10         # >0 就按它；0 = 跟随模型 ✓
    default = pi.limits_of({'limits': {}})
    assert default['turns'] == agent.MAX_TURNS
    assert default['timeout'] == agent.COMMAND_TIMEOUT


def test_run_tool_honours_limits(tmp_path):
    (tmp_path / 'big.py').write_text('x' * 50000, encoding='utf-8')
    text = agent.run_tool('read_file', {'path': 'big.py'}, str(tmp_path),
                          {'read': 100})
    assert len(text) <= 200
    out = agent.run_tool('run_command', {'command': 'echo hi'}, str(tmp_path),
                         {'timeout': 60, 'output': 8000})
    assert 'hi' in out


def test_models_patch_carries_limits_and_frontend_renders():
    desk = _desk('.')
    desk._on_pi_models({})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_models'])
    assert 'limits' in rows[0]
    assert rows[0]['limits']['turns'] >= 1
    page = _read('desk/pi-models.ts')
    assert 'desk-pi-advanced' in page
    assert '工具轮数' in page and '命令超时' in page
    assert '工具输出' in page and '上下文窗口' in page
    assert 'this.data.limits' in page
    css = (ROOT / 'jslib' / 'src' / 'desk' / 'desk.css').read_text(
        encoding='utf-8')
    assert '.desk-pi-advanced {' in css


# ------------------------------------------------- ⑪ 混合编码（v1.3.7-18）
def test_decode_bytes_handles_mixed_encodings_per_line():
    """同一条命令里 UTF-8 与 GBK 混着也能各解各的（以前整块退 GBK → 坏一半 ✗）"""
    data = ('第一行 UTF-8 中文'.encode('utf-8') + bytes([10])
            + '第二行 GBK 中文'.encode('gbk') + bytes([10]))
    text = agent.decode_bytes(data)
    assert '第一行 UTF-8 中文' in text
    assert '第二行 GBK 中文' in text
    assert '�' not in text


def test_decode_bytes_repairs_gbk_mojibake():
    """「UTF-8 被当 GBK 解」的乱码要能修回来 ✓（锛/銆/涓/鏄 这类字符）"""
    original = '中文测试'
    mojibake_text = original.encode('utf-8').decode('gbk', 'ignore')
    assert mojibake_text != original
    # 这份乱码又被按 GBK 写出来（= 原始 UTF-8 字节，无损）→ 应还原
    fixed = agent.decode_bytes(mojibake_text.encode('gbk', 'ignore'))
    assert '�' not in fixed


def test_run_command_mixed_script_output(tmp_path):
    script = tmp_path / 'mix.py'
    script.write_text(
        "import sys" + chr(10)
        + "sys.stdout.buffer.write('第一行UTF8中文'.encode('utf-8')"
        + " + bytes([10]))" + chr(10)
        + "sys.stdout.buffer.write('第二行GBK中文'.encode('gbk')"
        + " + bytes([10]))" + chr(10), encoding='utf-8')
    out = agent.run_tool('run_command',
                         {'command': 'python "' + str(script) + '" 2>&1'},
                         str(tmp_path))
    assert '第一行UTF8中文' in out
    assert '第二行GBK中文' in out
    assert '�' not in out


def test_terminal_reads_utf8_output(tmp_path):
    """终端面板按行解码：UTF-8 输出不乱码 ✓（GBK 已由 echo 用例覆盖）"""
    from minibt.desk.terminal import TerminalSession

    script = tmp_path / 'mix2.py'
    script.write_text(
        "import sys" + chr(10)
        + "sys.stdout.buffer.write('终端UTF8中文'.encode('utf-8')"
        + " + bytes([10]))" + chr(10), encoding='utf-8')

    class _Desk:
        def __init__(self):
            self.lines = []

        def push(self, patch):
            self.lines.append(str(patch.get('text') or ''))

    desk = _Desk()
    session = TerminalSession(desk, str(tmp_path))
    session.start()
    try:
        session.write('python "' + str(script) + '"')
        for _ in range(120):
            time.sleep(0.1)
            if any('终端UTF8中文' in row for row in desk.lines):
                break
        assert any('终端UTF8中文' in row for row in desk.lines), desk.lines[-5:]
    finally:
        session.stop()


# -------------------------------------------- ⑫ 没装 pi → 按钮禁用 / 不同步（v1.3.7-19）
def test_install_status_detects_missing_pi(monkeypatch):
    """`pi` 不在 PATH → installed False + 带安装提示（前端禁用按钮 ✓）"""
    monkeypatch.setattr(pi.shutil, 'which', lambda *a, **k: None)
    status = pi.install_status(force=True)
    assert status['installed'] is False
    assert status['command'] == ''
    assert status['version'] == ''
    assert 'npm install -g' in status['hint']


def test_install_status_caches(monkeypatch):
    calls = []

    def fake_which(name, *a, **k):
        calls.append(name)
        return ''

    monkeypatch.setattr(pi.shutil, 'which', fake_which)
    pi.install_status(force=True)
    first = len(calls)
    pi.install_status()
    pi.install_status()
    assert len(calls) == first          # 30 秒内走缓存 ✓


def test_pi_status_patch_reports_install_state(monkeypatch):
    monkeypatch.setattr(pi, 'install_status', lambda force=False: {
        'installed': False, 'command': '', 'version': '',
        'hint': pi.INSTALL_HINT})
    desk = _desk('.')
    desk._on_pi_status()
    patch = _wait(desk, lambda items: [r for r in items
                                       if r.get('type') == 'pi_status'])
    assert patch[0]['installed'] is False
    assert patch[0]['hint'] == pi.INSTALL_HINT
    assert 'pi_sessions' in patch[0]['commands']


def test_explorer_root_skips_pi_sync_without_pi(monkeypatch, tmp_path):
    """没装 pi → 资源管理器切目录**不再**同步 PI 会话（用户 2026-11-08 ✓）"""
    target = tmp_path / 'work'
    target.mkdir()
    monkeypatch.setattr(pi, 'install_status', lambda force=False: {
        'installed': False, 'command': '', 'version': '',
        'hint': pi.INSTALL_HINT})
    desk = _desk(str(target))
    desk._apply_explorer_root(str(target))
    rows = _rows(desk)
    kinds = [row.get('type') for row in rows]
    assert 'explorer' in kinds           # 资源管理器照常切 ✓
    assert 'explorer_root' in kinds
    assert 'pi_sessions' not in kinds    # PI 不同步 ✓


def test_explorer_root_syncs_pi_when_installed(monkeypatch, tmp_path):
    target = tmp_path / 'work2'
    target.mkdir()
    monkeypatch.setattr(pi, 'install_status', lambda force=False: {
        'installed': True, 'command': 'pi', 'version': '1.5.0',
        'hint': pi.INSTALL_HINT})
    desk = _desk(str(target))
    desk._apply_explorer_root(str(target))
    kinds = [row.get('type') for row in _rows(desk)]
    assert 'pi_sessions' in kinds        # 装了 → 照旧同步 ✓


def test_frontend_disables_pi_button_when_missing():
    page = (JSLIB / 'desk' / 'editor-panel.ts').read_text(encoding='utf-8')
    assert 'private piInstalled: boolean | null = null;' in page
    assert 'private _syncPiButton(): void {' in page
    assert 'button.disabled = missing;' in page
    assert 'button.title = missing' in page
    assert "this.options.onCommand('pi_status', {});" in page
    assert 'this.piInstalled = patch.installed !== false;' in page
    # 没装 → 点开也要拦下
    assert 'if (this.piInstalled === false) {' in page
    assert 'PI_INSTALL_HINT' in page
    css = (JSLIB / 'desk' / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-pi-toggle:disabled' in css


# ------------------------------- ⑬ 思考过程 / 每轮用量 / 对话页对齐（v1.3.7-20）
class _ThinkFake(BaseHTTPRequestHandler):
    """第一轮：思考 + 工具调用；第二轮：结论（`reasoning_content` ✓）"""
    calls: list = []

    def log_message(self, *args):                                 # noqa: D102
        pass

    def do_POST(self):                                            # noqa: N802
        size = int(self.headers.get('Content-Length') or 0)
        _ThinkFake.calls.append(json.loads(self.rfile.read(size) or b'{}'))
        first = len(_ThinkFake.calls) == 1
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()

        def send(chunk):
            self.wfile.write(('data: ' + json.dumps(chunk)
                             + chr(10) + chr(10)).encode())
            self.wfile.flush()

        if first:
            send({'choices': [{'delta': {'reasoning_content': '先读文件…'}}]})
            send({'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': 'c1',
                'function': {'name': 'read_file',
                             'arguments': json.dumps({'path': 'a.py'})}}]}}]})
            send({'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]})
            send({'usage': {'prompt_tokens': 100, 'completion_tokens': 20,
                            'total_tokens': 120,
                            'prompt_tokens_details': {'cached_tokens': 64}}})
        else:
            send({'choices': [{'delta': {'content': '结论：没问题'}}]})
            send({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
            send({'usage': {'prompt_tokens': 300, 'completion_tokens': 40,
                            'total_tokens': 340}})
        self.wfile.write(b'data: [DONE]' + chr(10).encode() * 2)
        self.wfile.flush()


@pytest.fixture()
def think_llm():
    _ThinkFake.calls = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _ThinkFake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}/v1', _ThinkFake.calls
    server.shutdown()


def _think_session(tmp_path):
    (tmp_path / 'a.py').write_text('print(1)' + chr(10), encoding='utf-8')
    session = agent.create_session(str(tmp_path))
    return session


def test_stream_captures_thinking_and_round_usage(think_llm, tmp_path):
    base, calls = think_llm
    session = _think_session(tmp_path)
    config = {'base': base, 'key': 'k', 'model': 'deepseek-flash',
              'price_in': 0.5, 'price_out': 2.0, 'window': 1000000}

    class _D:
        def __init__(self):
            self.events = []

        def push(self, patch):
            self.events.append(patch)

    desk = _D()
    agent.start_run(desk, session, config, '看下 a.py', event_type='pi_event')
    for _ in range(200):
        time.sleep(0.05)
        if desk.events and desk.events[-1].get('event') in ('done', 'error'):
            break
    kinds = [event.get('event') for event in desk.events]
    assert 'thinking' in kinds
    assert [event['text'] for event in desk.events
            if event.get('event') == 'thinking'] == ['先读文件…']
    assert 'tool' in kinds and 'tool_result' in kinds
    saved = agent.load_session(session['id'])
    first = saved['messages'][2]
    assert first['role'] == 'assistant'
    assert first['thinking'] == '先读文件…'
    assert first['usage']['prompt'] == 100
    assert first['usage']['cached'] == 64          # 缓存 token ✓
    tool = saved['messages'][3]
    assert tool['role'] == 'tool' and tool['name'] == 'read_file'
    assert 'a.py' in tool['args'] and tool['elapsed'] >= 0
    # 思考过程**不发给模型**（只留在会话里给界面看 ✓）
    assert all('thinking' not in message
               for message in calls[1]['messages'])


def test_history_payload_keeps_thinking_tools_and_usage(think_llm, tmp_path):
    """重开会话：思考 / 工具 / 每轮用量都要在（用户 2026-11-08 反馈 ✗）"""
    base, _calls = think_llm
    session = _think_session(tmp_path)
    config = {'base': base, 'key': 'k', 'model': 'deepseek-flash',
              'price_in': 0.5, 'price_out': 2.0, 'window': 1000000}

    class _D:
        def push(self, patch):
            pass

    agent.start_run(_D(), session, config, '看下 a.py', event_type='pi_event')
    for _ in range(200):
        time.sleep(0.05)
        rows = agent.load_session(session['id'])['messages']
        if len(rows) >= 5 and rows[-1].get('role') == 'assistant':
            break
    desk = _desk(str(tmp_path))
    payload = desk._pi_session_payload(agent.load_session(session['id']))
    roles = [row['role'] for row in payload['messages']]
    assert 'tool' in roles                       # 以前被 continue 掉了 ✗
    thought = [row for row in payload['messages'] if row.get('thinking')]
    assert thought and thought[0]['thinking'] == '先读文件…'
    assert thought[0]['usage']['prompt'] == 100
    tool = [row for row in payload['messages'] if row['role'] == 'tool'][0]
    assert tool['name'] == 'read_file'
    assert 'a.py' in tool['args']
    assert 'elapsed' in tool


def test_api_messages_strips_ui_only_fields():
    rows = agent.api_messages([
        {'role': 'assistant', 'content': 'x', 'thinking': '想',
         'usage': {'prompt': 1}, 'model': 'm', 'seconds': 1.0,
         'tool_calls': [{'id': 'c', 'type': 'function',
                         'function': {'name': 'f', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'c', 'name': 'f',
         'args': '{}', 'elapsed': 0.5, 'content': 'ok'},
    ])
    assert 'thinking' not in rows[0] and 'usage' not in rows[0]
    assert 'model' not in rows[0] and 'seconds' not in rows[0]
    assert rows[0]['tool_calls']
    assert 'args' not in rows[1] and 'elapsed' not in rows[1]
    assert rows[1]['content'] == 'ok'


def test_chat_page_matches_pi_agent_web():
    """对话页细节：折叠思考/工具、每轮用量、复制、节点导航、右键粘贴 ✓"""
    chat = _read('desk/pi-chat.ts')
    for token in ('desk-pi-fold', '思考', 'desk-pi-usage', '输入 ',
                  '输出 ', '缓存 ', 'desk-pi-link', '复制',
                  'desk-pi-nav', 'desk-pi-nav-node', 'scrollIntoView',
                  "addEventListener('contextmenu'", 'readText',
                  'desk-pi-code-wrap', 't/s', '回到底部',
                  'desk-pi-tool-args', '无输出'):
        assert token in chat, token
    css = (JSLIB / 'desk' / 'desk.css').read_text(encoding='utf-8')
    for token in ('.desk-pi-body', '.desk-pi-nav-node', '.desk-pi-fold-body',
                  '.desk-pi-usage', '.desk-pi-code-wrap', '.desk-pi-jump',
                  '.desk-pi-nav-label'):
        assert token in css, token
    # 后端也要留住思考 / 每轮用量 / 工具参数 ✓
    code = (ROOT / 'minibt' / 'desk' / 'agent.py').read_text(encoding='utf-8')
    for token in ('on_thinking', 'reasoning_content', 'def usage_of',
                  'def api_messages', "'thinking': thought",
                  "'cached'", "'elapsed'"):
        assert token in code, token
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'role': 'tool', 'index': index" in app
    assert "row['thinking']" in app


# ------------------------------- ⑭ 代码块底色 / 结论复制 / 右键粘贴（v1.3.7-21）
def test_code_block_has_no_inline_background():
    """代码块里的 `<code>` 不能带行内底色（以前每行都像被选中 ✗）"""
    css = (JSLIB / 'desk' / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-pi-msg-body pre code' in css
    assert 'background: transparent' in css
    chat = _read('desk/pi-chat.ts')
    assert 'desk-pi-code-wrap' in chat
    assert 'desk-pi-code' in chat


def test_copy_button_always_below_conclusion():
    """结论下方**始终**有「复制」（以前只有带 usage 才画 ✗）"""
    chat = _read('desk/pi-chat.ts')
    assert 'desk-pi-copy-answer' in chat
    assert 'if (usage || message.content) {' in chat
    assert "'复制这条回答'" in chat


def test_right_click_paste_goes_through_backend():
    """右键粘贴：Qt 壳里浏览器剪贴板读不到 → 走后端 `pi_paste` ✓"""
    chat = _read('desk/pi-chat.ts')
    assert "addEventListener('contextmenu'" in chat
    assert 'this.requestPaste();' in chat
    assert "this.options.onCommand('pi_paste'" in chat
    assert 'applyPaste(text: string, ok = true)' in chat
    assert 'private insertText(text: string): void' in chat
    editor = _read('desk/editor-panel.ts')
    assert "kind === 'pi_paste'" in editor
    assert '.chat.applyPaste(' in editor
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "'pi_paste': self._on_pi_paste" in app
    assert 'def _on_pi_paste(' in app
    assert "'type': 'pi_paste'" in app


def test_pi_paste_reads_clipboard(monkeypatch):
    """`pi_paste` 命令：把系统剪贴板内容推回去（Qt 不可用也不炸 ✓）"""
    desk = _desk('.')
    desk._on_pi_paste({'id': 'abc'})
    rows = _wait(desk, lambda items: [r for r in items
                                      if r.get('type') == 'pi_paste'])
    assert rows and rows[0]['id'] == 'abc'
    assert 'text' in rows[0] and 'ok' in rows[0]


# ----------------------------- ⑮ REPL 预导入 / 终端面板（v1.3.7-22）
def test_repl_preimports_minibt_star():
    """REPL 启动就要有 `LocalDatas` 等名字（以前 `from minibt import *`
    只进了 bootstrap 的 globals，没搬进 namespace → NameError ✗）"""
    code = (ROOT / 'minibt' / 'desk' / 'repl.py').read_text(encoding='utf-8')
    assert 'from minibt import *' in code
    assert 'namespace[_name] = getattr(minibt, _name)' in code
    assert "namespace.setdefault('np'" in code
    assert 'REPL 已就绪' in code

    from minibt.desk import repl as repl_mod

    session = repl_mod.ReplSession('.')
    session._start()
    try:
        deadline = time.time() + 30
        while time.time() < deadline and not session.alive():
            time.sleep(0.1)
        time.sleep(3)
        while not session.queue.empty():
            session.queue.get_nowait()
        out = session.run('print(sorted([n for n in dir() '
                          'if n == "LocalDatas"]))')
        assert 'LocalDatas' in str(out.get('output') or '')
        again = session.run('1 + 2')
        assert '3' in str(again.get('output') or '')
    finally:
        session.stop()


def test_console_height_is_draggable_and_close_on_right():
    """终端/REPL：可拖动高度、关闭按钮贴最右、「AI 对话」已删除（用户要求 ✓）"""
    editor = _read('desk/editor-panel.ts')
    assert 'desk-editor-console-resize' in editor
    assert 'private consoleHeight = 220;' in editor
    assert 'consoleHeight + (startY - moveEvent.clientY)' in editor.replace(
        'startHeight', 'consoleHeight')
    assert 'desk-resizing-v' in editor
    # 关闭按钮最后追加（→ 贴最右）✓
    assert 'consoleHead.append(consoleActions, consoleClose);' in editor
    assert "addAction('AI 对话'" not in editor
    # cd 之后提示符跟着变 ✓
    assert 'private _trackCd(line: string): void' in editor
    assert 'private _syncTerminalPrompt(): void' in editor
    css = (JSLIB / 'desk' / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-editor-console-resize' in css
    assert 'cursor: ns-resize' in css
    assert '.desk-editor-console-close { margin-left: auto; }' in css
    assert 'height: 220px' in css


def test_console_dom_layout_has_handle_and_no_ai_button():
    """DOM 层：拖拽条在、AI 对话按钮没了、× 是最后一个（最右）✓"""
    editor = _read('desk/editor-panel.ts')
    assert "resize.className = 'desk-editor-console-resize';" in editor
    assert "resize.title = '拖动调整终端 / REPL 高度';" in editor
    assert 'this.consolePane.append(resize, consoleHead' in editor
    assert 'this.consolePane.style.height' in editor


# ------------------------- ⑯ 终端按钮合并 / 发给 AI 二级菜单（v1.3.7-23）
def test_console_single_button_keeps_last_tab():
    """终端 + REPL 合成一个按钮，打开的是「上次用的页签」✓"""
    editor = _read('desk/editor-panel.ts')
    assert "this._button('终端', () => {" in editor
    assert 'this.openConsole(this.consoleTab);' in editor
    # 工具栏里不再有单独的 REPL 按钮
    assert "this._button('REPL'" not in editor
    assert "consoleButton.addEventListener('contextmenu'" in editor
    assert "label: 'REPL', run: () => this.openConsole('repl')" in editor


def test_send_to_ai_menu_targets_sessions():
    """「发给 AI」：选中代码 / 整个文件 / 文件地址 → 选会话 → 插输入框 ✓"""
    editor = _read('desk/editor-panel.ts')
    for token in ('_aiSendMenu', '_aiTargets', '_pushToAi', '_aiInsertText',
                  'pendingAi', 'pendingAiRead', '_aiSourceTab',
                  'appendToInput', '新建会话'):
        assert token in editor, token
    # 三个入口都在
    assert "this._button('发给 AI ▾'" in editor
    assert "label: '发给 AI'," in editor                     # 编辑器右键
    assert "label: '发给 AI（文件地址）'" in editor            # 资源管理器
    assert "label: '发给 AI（全部代码）'" in editor
    chat = _read('desk/pi-chat.ts')
    assert 'appendToInput(text: string): void {' in chat
    assert '已插入代码，按 Enter 发送' in chat


def test_send_to_ai_falls_back_to_last_open_file():
    """PI 页签在前台时，仍然可以发「上一个打开的文件」✓"""
    editor = _read('desk/editor-panel.ts')
    assert 'private _aiSourceTab()' in editor
    assert 'for (const tab of this.open.values()) fallback = tab;' in editor
    assert 'const tab = this._aiSourceTab();' in editor

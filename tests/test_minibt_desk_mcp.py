# coding: utf-8
"""v1.3.7-27：MCP 服务端（方案 M4）。

覆盖：
* `initialize` / `ping` / `tools/list` / `tools/call` / 未知方法 / 解析错误
* 通知（没有 `id`）不回包
* `tools/list` 的 schema 转换（`parameters` → `inputSchema`）
* `tools/call` 用工具桥（成功 / 未知工具 / 失败时 `isError`）
* `--config`：生成 / 合并 `mcp.json`
* `serve()`：逐行读写（模拟客户端）
"""
from __future__ import annotations

import io
import json
import pathlib

import pytest

from minibt.desk import bridge, mcp, mcp_client, tools

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FakeDesk:
    def __init__(self):
        self.calls = []
        self.tabs = {}
        self.last_symbol = 'DCE.a2701'

    def _on_switch_symbol(self, payload):
        self.calls.append(('switch', payload))

    def _on_set_layout(self, payload):
        self.calls.append(('layout', payload))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from minibt.desk import user_prefs

    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(mcp, 'CONFIG_FILE', str(tmp_path / 'mcp.json'))
    monkeypatch.setattr(bridge, 'INFO_FILE', str(tmp_path / 'bridge.json'))
    monkeypatch.setattr(mcp_client, 'CONFIG_FILE', str(tmp_path / 'mcp.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    mcp_client.stop_all()
    yield tmp_path
    bridge.stop()
    mcp_client.stop_all()


FAKE_MCP = ROOT / 'tests' / 'fake_mcp_server.py'


def _write_fake_server(path, extra=None):
    """最小的假 MCP server（tools/list + tools/call）✓"""
    servers = {'fake': {'command': 'python', 'args': [str(FAKE_MCP)],
                        'env': {}}}
    servers.update(extra or {})
    path.write_text(json.dumps({'mcpServers': servers}), encoding='utf-8')


def test_bridge_serves_tools_and_call():
    """本机桥：health / tools / call / token 校验 / 关掉后信息文件消失 ✓"""
    import urllib.error
    import urllib.request

    desk = FakeDesk()
    info = bridge.start(desk)
    assert info and info['port']
    base = f"http://127.0.0.1:{info['port']}"
    health = json.loads(urllib.request.urlopen(f'{base}/health', timeout=5)
                        .read())
    assert health['ok'] is True and health['pid'] == __import__('os').getpid()

    def post(path, payload, token=None):
        request = urllib.request.Request(
            base + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json',
                     'X-Minibt-Token': token if token is not None
                     else info['token']})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    rows = post('/tools', {})
    assert 'desk_switch_symbol' in rows['tools']
    result = post('/call', {'name': 'desk_switch_symbol',
                            'arguments': {'symbol': 'SHFE.rb2601'}})
    assert json.loads(result['text'])['ok'] is True
    assert desk.calls[-1][0] == 'switch'
    # token 不对 → 401 ✓
    with pytest.raises(urllib.error.HTTPError) as error:
        post('/call', {'name': 'desk_status'}, token='bad')
    assert error.value.code == 401
    # 关掉后信息文件删除、`read_info` 为空 ✓
    assert bridge.read_info()['port'] == info['port']
    bridge.stop()
    assert bridge.read_info() == {}
    assert bridge.call('desk_status', {}).startswith('没有连上')


def test_mcp_forwards_to_running_desk():
    """MCP 没有本地 desk → 走桥，改的是**正在运行**的那个 desk ✓"""
    desk = FakeDesk()
    bridge.start(desk)
    server = mcp.McpServer(None)
    reply = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                           'params': {'name': 'desk_switch_symbol',
                                      'arguments': {'symbol': 'DCE.a2701'}}})
    result = reply['result']
    assert result['isError'] is False
    assert json.loads(result['content'][0]['text'])['ok'] is True
    assert desk.calls[-1][1]['to'] == 'DCE.a2701'


def test_mcp_client_reads_config_and_calls(isolated):
    """反向 MCP：外部 server 的工具 → `mcp__<server>__<tool>` ✓"""
    _write_fake_server(isolated / 'mcp.json',
                       {'minibt-desk': {'command': 'python',
                                        'args': ['-m', 'minibt.desk.mcp']}})
    assert list(mcp_client.servers()) == ['fake']        # 跳过自己 ✓
    rows = mcp_client.specs(force=True)
    assert [row['function']['name'] for row in rows] == ['mcp__fake__echo']
    assert rows[0]['function']['description'].startswith('[MCP:fake]')
    assert mcp_client.names() == ['mcp__fake__echo']
    assert mcp_client.call_tool('mcp__fake__echo',
                                {'text': '你好'}) == 'echo:你好'
    assert '没有配置外部 MCP server' in mcp_client.call_tool('mcp__nope__x',
                                                              {})
    mcp_client.stop_all()
    assert mcp_client._CLIENTS == {}


def test_mcp_client_skips_broken_server(isolated):
    (isolated / 'mcp.json').write_text(json.dumps({'mcpServers': {
        'broken': {'command': 'definitely-not-a-real-command-xyz'},
    }}), encoding='utf-8')
    assert mcp_client.specs(force=True) == []
    assert '起不来' in mcp_client.call_tool('mcp__broken__x', {})


def test_agent_uses_external_tools(isolated, monkeypatch):
    """外部工具注册进 TOOLS，`run_tool` 能路由 ✓"""
    from minibt.desk import agent

    _write_fake_server(isolated / 'mcp.json')
    mcp_client._SPECS = None
    monkeypatch.setattr(mcp_client, 'CONFIG_FILE',
                        str(isolated / 'mcp.json'))
    rows = agent.external_tools(force=True)
    assert [row['function']['name'] for row in rows] == ['mcp__fake__echo']
    text = agent.run_tool('mcp__fake__echo', {'text': 'hi'}, '.')
    assert text == 'echo:hi'
    # 只读权限不挂外部工具（它们可能写数据 / 花钱 ✓）
    assert 'mcp__fake__echo' not in agent.TOOL_GROUPS['readonly']


# ---------------------------------------------------------------- 协议
def test_initialize_and_ping():
    server = mcp.McpServer(FakeDesk())
    reply = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                           'params': {'protocolVersion': '2024-11-05'}})
    result = reply['result']
    assert result['protocolVersion'] == mcp.PROTOCOL
    assert result['serverInfo']['name'] == 'minibt-desk'
    assert 'tools' in result['capabilities']
    pong = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})
    assert pong['result'] == {}


def test_notifications_do_not_reply():
    server = mcp.McpServer(FakeDesk())
    assert server.handle({'jsonrpc': '2.0',
                          'method': 'notifications/initialized'}) is None


def test_unknown_method_and_bad_requests():
    server = mcp.McpServer(FakeDesk())
    reply = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'nope'})
    assert reply['error']['code'] == -32601
    reply = server.handle(['bad'])
    assert reply['error']['code'] == -32600
    reply = server.handle({'jsonrpc': '2.0', 'id': 4})
    assert reply['error']['code'] == -32600


# ---------------------------------------------------------------- 工具
def test_tools_list_shape():
    rows = mcp.tools_list()
    assert len(rows) == len(tools.SPECS) >= 17
    names = [row['name'] for row in rows]
    assert names == tools.NAMES
    first = rows[0]
    assert set(first) == {'name', 'description', 'inputSchema'}
    assert first['inputSchema']['type'] == 'object'
    reply = mcp.McpServer(FakeDesk()).handle(
        {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/list'})
    assert len(reply['result']['tools']) == len(rows)


def test_tools_call_routes_to_bridge():
    desk = FakeDesk()
    server = mcp.McpServer(desk)
    reply = server.handle({
        'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call',
        'params': {'name': 'desk_switch_symbol',
                   'arguments': {'symbol': 'SHFE.rb2601', 'cell': 1}},
    })
    result = reply['result']
    assert result['isError'] is False
    payload = json.loads(result['content'][0]['text'])
    assert payload['ok'] is True
    assert desk.calls[-1] == ('switch', {'from': 'DCE.a2701',
                                         'to': 'SHFE.rb2601', 'cell': 1,
                                         'local': False})


def test_tools_call_unknown_and_failure():
    server = mcp.McpServer(FakeDesk())
    reply = server.handle({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                           'params': {'name': 'desk_nope'}})
    assert reply['result']['isError'] is True
    assert '未知工具' in reply['result']['content'][0]['text']
    # 既没有本地 desk、也没有桥 → 明确说明并标 isError ✓
    reply = mcp.McpServer(None).handle({
        'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
        'params': {'name': 'desk_status', 'arguments': {}}})
    assert reply['result']['isError'] is True
    assert '没有连上正在运行的 minibt desk' in         reply['result']['content'][0]['text']


# ---------------------------------------------------------------- serve
def test_serve_reads_and_writes_lines():
    source = io.StringIO(
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        'not-json\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n')
    sink = io.StringIO()
    assert mcp.McpServer(FakeDesk()).serve(source, sink) == 0
    rows = [json.loads(line) for line in sink.getvalue().strip().splitlines()]
    assert rows[0]['result']['serverInfo']['name'] == 'minibt-desk'
    assert rows[1]['error']['code'] == -32700          # 解析错误 ✓
    assert len(rows[2]['result']['tools']) >= 17


def test_write_config_creates_and_merges(isolated):
    path = mcp.write_config()
    assert pathlib.Path(path).exists()
    data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    entry = data['mcpServers']['minibt-desk']
    assert entry['args'][:2] == ['-m', 'minibt.desk.mcp']
    assert entry['env']['MINIBT_DESK_MCP'] == '1'
    # 已有别的 server → 合并，不覆盖 ✓
    data['mcpServers']['other'] = {'command': 'x'}
    pathlib.Path(path).write_text(json.dumps(data), encoding='utf-8')
    mcp.write_config()
    again = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    assert 'other' in again['mcpServers']
    assert 'minibt-desk' in again['mcpServers']


def test_main_config_and_list(capsys, isolated):
    assert mcp.main(['--config']) == 0
    out = capsys.readouterr().out
    assert 'MCP 配置' in out and 'mcpServers' in out
    assert mcp.main(['--list']) == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data['tools']) >= 17


def test_docs_have_plan_and_usage():
    """方案稿（设计）+ 使用文档（manual/13.29）都要在 ✓"""
    base = ROOT / 'minibt_docs' / 'docs' / 'minibt_desk'
    plan = (base / '13.29_pi_mcp_desk_control.md').read_text(encoding='utf-8')
    assert 'M4' in plan and 'minibt.desk.mcp' in plan
    usage = (base / 'manual' / '13.29_pi_mcp_usage.md').read_text(
        encoding='utf-8')
    for token in ('介绍与使用', 'python -m minibt.desk.mcp --config',
                  '允许 PI 操控 desk', 'need_confirm', 'audit.jsonl',
                  '13.30'):
        assert token in usage, token
    # mkdocs 目录两条都在，且方案稿不在 manual 下 ✓
    index = (ROOT / 'minibt_docs' / 'mkdocs.yml').read_text(encoding='utf-8')
    assert 'minibt_desk/manual/13.29_pi_mcp_usage.md' in index
    assert 'minibt_desk/13.29_pi_mcp_desk_control.md' in index
    assert 'minibt_desk/manual/13.29_pi_mcp_desk_control.md' not in index


def test_agent_skips_external_tools_when_disabled(isolated, monkeypatch):
    from minibt.desk import agent, user_prefs

    _write_fake_server(isolated / 'mcp.json')
    mcp_client._SPECS = None
    monkeypatch.setattr(mcp_client, 'CONFIG_FILE',
                        str(isolated / 'mcp.json'))
    assert agent.external_tools(force=True)
    user_prefs.set_setting('ai_mcp_tools', False)
    assert agent.external_tools(force=True) == []
    user_prefs.set_setting('ai_mcp_tools', True)


def test_settings_page_exposes_mcp_switches():
    page = (ROOT / 'jslib' / 'src' / 'desk' / 'settings-page.ts').read_text(
        encoding='utf-8')
    for token in ('ai_mcp_bridge', 'ai_mcp_tools', 'MCP 本机桥',
                  '接入外部 MCP 工具'):
        assert token in page, token

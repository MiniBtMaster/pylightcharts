"""v1.3.7-90：命令行操作 desk（`python -m minibt.desk.cli`）。"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from minibt.desk import cli


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ('MINIBT_DESK_TOKEN', 'MINIBT_TOKEN', 'MINIBT_DESK_URL'):
        monkeypatch.delenv(key, raising=False)


def parse(*args):
    return cli.build_parser().parse_args(list(args))


class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ------------------------------------------------------------ 地址 / token
def test_base_url_default_and_env(monkeypatch):
    assert cli.base_url(parse('status')) == 'http://127.0.0.1:8765'
    monkeypatch.setenv('MINIBT_DESK_URL', '10.0.0.2:9000')
    assert cli.base_url(parse('status')) == 'http://10.0.0.2:9000'
    assert cli.base_url(parse('status', '--url', 'https://x/y/')) \
        == 'https://x/y'


def test_token_priority(monkeypatch, tmp_path):
    args = parse('status', '--token', 'from-arg')
    assert cli.token_of(args) == 'from-arg'
    monkeypatch.setenv('MINIBT_DESK_TOKEN', 'from-env')
    assert cli.token_of(args) == 'from-env'
    monkeypatch.delenv('MINIBT_DESK_TOKEN')
    path = tmp_path / 'tk.txt'
    path.write_text('from-file\n', encoding='utf-8')
    args = parse('status', '--token-file', str(path))
    assert cli.token_of(args) == 'from-file'
    with pytest.raises(cli.CliError):
        cli.token_of(parse('status'))


# ------------------------------------------------------------ payload
def test_parse_payload_variants(tmp_path):
    args = parse('rpc', 'x', '--payload', '{"a":1}', '--set', 'b=true',
                 '--set', 'c=3.5', '--set', 'd=text')
    assert cli.parse_payload(args) == {'a': 1, 'b': True, 'c': 3.5,
                                       'd': 'text'}
    path = tmp_path / 'p.json'
    path.write_text(json.dumps({'name': '任务'}), encoding='utf-8')
    assert cli.parse_payload(parse('rpc', 'x', '--file', str(path))) == {
        'name': '任务'}
    # 整段 rpc 文件（含 cmd / payload）也认 ✓
    path2 = tmp_path / 'rpc.json'
    path2.write_text(json.dumps({'cmd': 'ops_task_run',
                                 'payload': {'name': 'A'}}), encoding='utf-8')
    assert cli.parse_payload(parse('rpc', 'x', '--file', str(path2))) == {
        'name': 'A'}


def test_parse_payload_rejects_bad_input(tmp_path):
    with pytest.raises(cli.CliError):
        cli.parse_payload(parse('rpc', 'x', '--payload', '{oops'))
    with pytest.raises(cli.CliError):
        cli.parse_payload(parse('rpc', 'x', '--payload', '[1,2]'))
    with pytest.raises(cli.CliError):
        cli.parse_payload(parse('rpc', 'x', '--set', 'novalue'))


# ------------------------------------------------------------ 请求
def test_request_headers_and_method(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=15):
        seen['url'] = request.full_url
        seen['method'] = request.get_method()
        seen['headers'] = dict(request.headers)
        seen['data'] = request.data
        return _Resp(b'{"ok": true, "data": {"ready": true}}')

    monkeypatch.setattr(cli.urllib.request, 'urlopen', fake_urlopen)
    out = cli.request(parse('status', '--token', 'tk'), '/api/status')
    assert out['data']['ready'] is True
    assert seen['url'].endswith('/api/status')
    assert seen['method'] == 'GET'
    assert seen['headers'].get('X-desk-token') == 'tk' \
        or seen['headers'].get('X-Desk-Token') == 'tk'

    cli.request(parse('rpc', 'ops', '--token', 'tk'), '/api/rpc',
                {'cmd': 'ops', 'payload': {}})
    assert seen['method'] == 'POST'
    assert json.loads(seen['data'].decode('utf-8'))['cmd'] == 'ops'


def test_request_error_messages(monkeypatch):
    def http_error(code, body):
        def fake(request, timeout=15):
            raise urllib.error.HTTPError(request.full_url, code, 'x', {},
                                         io.BytesIO(body))
        return fake

    monkeypatch.setattr(cli.urllib.request, 'urlopen',
                        http_error(403, b'{"error":"invalid token"}'))
    with pytest.raises(cli.CliError) as info:
        cli.request(parse('status', '--token', 'tk'), '/api/status')
    assert 'HTTP 403' in str(info.value) and 'scope' in str(info.value)

    monkeypatch.setattr(cli.urllib.request, 'urlopen',
                        http_error(400, b'{"error":"command not allowed"}'))
    with pytest.raises(cli.CliError) as info:
        cli.request(parse('status', '--token', 'tk'), '/api/status')
    assert '白名单' in str(info.value)


def test_request_connection_refused(monkeypatch):
    def fake(request, timeout=15):
        raise urllib.error.URLError('refused')

    monkeypatch.setattr(cli.urllib.request, 'urlopen', fake)
    with pytest.raises(cli.CliError) as info:
        cli.request(parse('status', '--token', 'tk'), '/api/status')
    assert 'headless' in str(info.value)


def test_rpc_raises_on_business_error(monkeypatch):
    monkeypatch.setattr(
        cli, 'request',
        lambda args, path, payload=None: {'ok': False, 'error': 'boom'})
    with pytest.raises(cli.CliError) as info:
        cli.rpc(parse('rpc', 'x', '--token', 'tk'), 'x')
    assert 'boom' in str(info.value)


# ------------------------------------------------------------ 输出
def test_show_tasks_table(monkeypatch, capsys):
    snapshot = {'tasks': {'tasks': [
        {'name': '开盘简报', 'enabled': True,
         'action': {'kind': 'ai'}, 'trigger': {'kind': 'daily',
                                               'at': '08:55',
                                               'days': 'mon-fri'},
         'last_status': 'ok'},
        {'name': '资讯刷新', 'enabled': False,
         'action': {'kind': 'tool', 'tool': 'desk_news'},
         'trigger': {'kind': 'interval', 'every': 600},
         'last_status': 'error', 'last_error': 'boom'},
    ]}}
    monkeypatch.setattr(cli, 'rpc', lambda args, cmd, payload=None: snapshot)
    assert cli.show_tasks(parse('tasks', '--token', 'tk'), False) == 0
    out = capsys.readouterr().out
    assert '开盘简报' in out and 'AI' in out and '每天 08:55' in out
    assert '工具·desk_news' in out and 'boom' in out


def test_main_status_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'request',
                        lambda args, path, payload=None:
                        {'ok': True, 'data': {'ready': True}})
    assert cli.main(['status', '--token', 'tk', '--json']) == 0
    out = capsys.readouterr().out
    assert json.loads(out.strip())['data']['ready'] is True


def test_main_push_only_command(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'rpc', lambda args, cmd, payload=None: None)
    assert cli.main(['rpc', 'ops_task_run', '--token', 'tk',
                     '--set', 'name=x']) == 0
    assert '只推补丁' in capsys.readouterr().out


def test_main_error_returns_nonzero(monkeypatch, capsys):
    def boom(args, path, payload=None):
        raise cli.CliError('没有 token')

    monkeypatch.setattr(cli, 'request', boom)
    assert cli.main(['status']) == 1
    assert '没有 token' in capsys.readouterr().err

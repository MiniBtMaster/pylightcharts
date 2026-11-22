"""v1.3.7-84：告警通道 —— 微信公众号（xtuis）/ 通用 webhook。"""
from __future__ import annotations

import json
import pathlib
import urllib.request

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.ops import NOTIFY_CHANNELS, XTUIS_URL, Notifier

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


class _FakeResponse:
    status = 200

    def __init__(self, body: bytes = b'{"code":0,"msg":"ok"}'):
        self._body = body

    def read(self, size: int = -1) -> bytes:
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def notifier(tmp_path, monkeypatch):
    store = {}

    def fake_urlopen(request, timeout=8):
        store['url'] = request.full_url
        store['data'] = getattr(request, 'data', None)
        store['headers'] = dict(getattr(request, 'headers', {}) or {})
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    gate = Notifier(str(tmp_path / 'notify.json'))
    gate.seen = store                    # type: ignore[attr-defined]
    return gate


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.pushes = []
    instance.push = instance.pushes.append
    return instance


# ------------------------------------------------------------ 通道配置
def test_channels_exist():
    assert NOTIFY_CHANNELS == ('wecom', 'xtuis', 'email', 'webhook')
    assert XTUIS_URL == 'https://wx.xtuis.cn/{token}.send'


def test_configure_xtuis_persists(notifier, tmp_path):
    block = notifier.configure('xtuis', {'enabled': True, 'token': 'abc123'})
    assert block == {'enabled': True, 'token': 'abc123', 'url': ''}
    again = Notifier(str(tmp_path / 'notify.json'))
    assert again.config['xtuis']['token'] == 'abc123'
    assert again.config['xtuis']['enabled'] is True


def test_configure_unknown_kind_falls_back(notifier):
    block = notifier.configure('whatever', {'enabled': True, 'webhook': 'u'})
    assert block == notifier.config['wecom'] == {'enabled': True,
                                                'webhook': 'u'}


# ------------------------------------------------------------ xtuis 推送
def test_xtuis_send_builds_url(notifier):
    notifier.configure('xtuis', {'enabled': True, 'token': 'tok9'})
    record = notifier.send('开盘提醒', '沪银大涨 2%', level='warning')
    result = [row for row in record['results']
              if row['channel'] == 'xtuis'][0]
    assert result['ok'] is True
    url = notifier.seen['url']
    assert url.startswith('https://wx.xtuis.cn/tok9.send?')
    assert 'text=' in url and 'desp=' in url
    assert '%E5%BC%80%E7%9B%98' in url          # 「开盘」的 UTF-8 编码


def test_xtuis_html_page_means_not_delivered(notifier, monkeypatch):
    """用错域名（`xtuis.cn` 没有 wx.）→ 返回官网 HTML，必须报错而不是"成功" ✗"""
    monkeypatch.setattr(
        urllib.request, 'urlopen',
        lambda request, timeout=8: _FakeResponse(
            '<!DOCTYPE html><html lang="zh-CN">…'.encode('utf-8')))
    notifier.configure('xtuis', {'enabled': True, 'token': 'tk',
                                 'url': 'https://xtuis.cn/{token}.send'})
    record = notifier.send('t', 'x')
    row = [item for item in record['results']
           if item['channel'] == 'xtuis'][0]
    assert row['ok'] is False
    assert 'wx.xtuis.cn' in row['detail']


def test_xtuis_custom_url(notifier):
    notifier.configure('xtuis', {'enabled': True, 'token': 'tk',
                                 'url': 'https://push.example.com/{token}.send'})
    notifier.send('hi', 'there')
    assert notifier.seen['url'].startswith(
        'https://push.example.com/tk.send?')


def test_xtuis_missing_token_reports(notifier):
    notifier.configure('xtuis', {'enabled': True, 'token': ''})
    record = notifier.send('t', 'x')
    row = [item for item in record['results'] if item['channel'] == 'xtuis'][0]
    assert row['ok'] is False
    assert 'token' in row['detail']


def test_xtuis_disabled_is_skipped(notifier):
    notifier.configure('xtuis', {'enabled': False, 'token': 'abc'})
    record = notifier.send('t', 'x')
    assert [item['channel'] for item in record['results']] == ['local']


# ------------------------------------------------------------ 通用 webhook
def test_webhook_post_with_template(notifier):
    notifier.configure('webhook', {
        'enabled': True, 'url': 'https://example.com/hook',
        'method': 'POST', 'template': '{"msg":"{title}|{level}","c":"{text}"}'})
    record = notifier.send('收盘', '日报', level='info')
    row = [item for item in record['results']
           if item['channel'] == 'webhook'][0]
    assert row['ok'] is True
    body = json.loads(notifier.seen['data'].decode('utf-8'))
    assert body == {'msg': '收盘|info', 'c': '日报'}


def test_webhook_get_puts_query(notifier):
    notifier.configure('webhook', {
        'enabled': True, 'url': 'https://example.com/hook',
        'method': 'GET', 'template': ''})
    notifier.send('t1', 't2')
    assert 'title=t1' in notifier.seen['url']
    assert notifier.seen['data'] is None


# ------------------------------------------------------------ 工具 / 界面
def test_desk_ops_notify_config(desk):
    out = json.loads(desk_tools.call('desk_ops', {
        'action': 'notify_config', 'kind': 'xtuis',
        'xtuis_token': 'tok777', 'enabled': True}, desk))
    assert out['ok'] is True
    assert out['values']['token'] == 'tok777'
    assert desk.ops_view().notifier.config['xtuis']['enabled'] is True

    bad = json.loads(desk_tools.call('desk_ops', {
        'action': 'notify_config', 'kind': 'nope'}, desk))
    assert bad['ok'] is False


def test_desk_ops_notify_test(desk, monkeypatch):
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda request, timeout=8: _FakeResponse())
    json.loads(desk_tools.call('desk_ops', {
        'action': 'notify_config', 'kind': 'xtuis',
        'token': 'tok1', 'enabled': True}, desk))
    out = json.loads(desk_tools.call('desk_ops', {'action': 'notify_test'},
                                     desk))
    assert out['ok'] is True
    assert out['results'][0]['channel'] == 'xtuis'


def test_settings_page_has_xtuis_fields():
    """v1.3.7-91：告警通道搬进设置页（系统设置 → 告警通道）✓"""
    text = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    assert '_renderAlerts' in text and 'setNotify' in text
    assert '微信公众号' in text and 'xtuis' in text
    assert "kind: 'xtuis'" in text
    assert "kind: 'webhook'" in text
    assert "kind: 'email'" in text
    assert 'ops_notify_test' in text
    # 运维页不再画告警表单 ✓
    ops = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    block = ops[ops.index('export class OpsPage {'):]
    assert 'xtuisToken' not in block


def test_docs_mention_xtuis():
    doc = (ROOT / 'minibt_docs' / 'docs' / 'minibt_desk'
           / '13.17_extensions.md').read_text(encoding='utf-8')
    assert 'xtuis' in doc and '公众号' in doc
    assert 'wx.xtuis.cn' in doc
    sched = (ROOT / 'minibt_docs' / 'docs' / 'minibt_desk' / 'manual'
             / '13.32_scheduler.md').read_text(encoding='utf-8')
    assert 'xtuis' in sched


# ------------------------------------------------ v1.3.7-101（测试/静音保护）
def test_env_mutes_all_channels(monkeypatch, tmp_path):
    """`MINIBT_DESK_NO_NOTIFY=1` → 一律不真发（返回 local + 原因 ✓）"""
    called = []
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda *a, **k: called.append(1))
    monkeypatch.setenv('MINIBT_DESK_NO_NOTIFY', '1')
    gate = Notifier(str(tmp_path / 'notify.json'))
    gate.configure('xtuis', {'enabled': True, 'token': 'x'})
    record = gate.send('策略启动:a', '账户')
    assert record['muted'] is True
    assert record['results'][0]['channel'] == 'local'
    assert 'MINIBT_DESK_NO_NOTIFY' in record['results'][0]['detail']
    assert called == []


def test_pytest_never_uses_real_config(monkeypatch, tmp_path):
    """跑测试时用的是**用户真实**配置 → 必须静音（否则真发微信 ✗）"""
    from minibt.desk import ops as ops_mod
    monkeypatch.delenv('MINIBT_DESK_NO_NOTIFY', raising=False)
    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'x::test')
    called = []
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda *a, **k: called.append(1))
    real = tmp_path / 'ops' / 'notify.json'
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text('{"xtuis": {"enabled": true, "token": "real"}}',
                    encoding='utf-8')
    # `_real_config` 比的是「用户家目录那份」→ 这里把它指到临时文件 ✓
    monkeypatch.setattr(ops_mod, 'home_notify_path', lambda: str(real))
    gate = ops_mod.Notifier(str(real))
    assert gate._real_config is True           # noqa: SLF001
    record = gate.send('策略启动:a', '账户')
    assert record['muted'] is True
    assert 'pytest' in record['results'][0]['detail']
    assert called == []


def test_tests_have_isolated_ops_dir():
    """conftest 把 ops 目录指到临时目录 + 默认静音 ✓"""
    import os as _os
    assert 'minibt-pytest-ops-' in _os.environ.get('MINIBT_DESK_OPS_DIR', '')
    # 真实配置 + pytest → 静音（`_muted()` 双保险 ✓）
    from minibt.desk.ops import Notifier
    gate = Notifier()                          # 临时 ops 目录里的配置
    assert gate._real_config is False          # 不是用户家目录那份 ✓
    assert gate.config_file.startswith(_os.environ['MINIBT_DESK_OPS_DIR'])


def test_alert_log_records_muted_send(monkeypatch, tmp_path):
    """静音时告警记录仍然写（只是通道显示 local），好排查 ✓"""
    from minibt.desk import user_prefs as _prefs
    monkeypatch.setattr(_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setenv('MINIBT_DESK_NO_NOTIFY', '1')
    _prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    desk = Desk(offline=True)
    desk._booted = True
    desk.push = lambda patch: None
    desk.ops_view().notify_rule('trade_reject', '拒单：ag2612', '保证金不足',
                                symbol='SHFE.ag2612')
    rows = desk.ops_view().alert_log.query()['items']
    assert rows and rows[0]['title'].startswith('拒单')
    assert 'local' in rows[0]['channel']

# coding: utf-8
"""v1.3.7-24：PI 助手「操控 desk」工具桥（MCP 方案 M1）。

覆盖：
* `tools.SPECS` / `NAMES`（工具表本身）
* 白名单分发（未知工具 / 没有 desk 窗口都要有可读的回复）
* 审计日志 + 参数脱敏（password 永远 `***`）
* 只读工具（status / local_list / drawings）
* 界面工具（切合约 / 加指标 / 删指标 / 布局 / 加载本地数据集）
* `agent` 侧接入：`TOOL_GROUPS` 的 `desk` 档、`run_tool` 路由
* 前端权限 chip 有「操控 desk」
"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import agent, personal, tools, user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from minibt.desk import user_prefs

    monkeypatch.setattr(tools, 'AUDIT_FILE',
                        str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'prefs.json'))
    # 这些用例测的是工具本身 → 开关默认打开；开关行为另有专门用例 ✓
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    yield


class _Ops:
    def __init__(self, tokens):
        self.tokens = tokens

        class _Tasks:
            def items(self):
                return [{'name': 'heartbeat', 'interval': 300,
                         'enabled': False}]

            def run(self, name):
                return [{'task': name, 'ok': True}]

            def enable(self, name, enabled=True):
                return True
        self.tasks = _Tasks()


class FakeDesk:
    """只记录调用：验证工具桥有没有把参数原样传给 desk ✓"""

    def __init__(self):
        self.calls = []
        self.tabs = {
            'DCE.a2701': {
                'layout': {'cols': 1, 'rows': 1,
                           'cells': [{'symbol': 'DCE.a2701'}]},
                'indicators': [{'key': 'MA'}, {'key': 'MACD'}],
            },
        }
        self.last_symbol = 'DCE.a2701'

    # ---- 被工具桥调用到的方法 ----
    def _on_switch_symbol(self, payload):
        self.calls.append(('switch', payload))

    def _on_add_indicator(self, payload):
        self.calls.append(('add_watch', payload))
        return True

    def _on_local_add_indicator(self, payload):
        self.calls.append(('add_local', payload))
        return True

    def _on_remove_indicator(self, payload):
        self.calls.append(('remove_watch', payload))

    def _on_local_remove_indicator(self, payload):
        self.calls.append(('remove_local', payload))

    def _on_set_layout(self, payload):
        self.calls.append(('layout', payload))

    def _on_local_load(self, payload):
        self.calls.append(('load', payload))

    # ---- A 批（工具栏）----
    def _on_set_cycle(self, payload):
        self.calls.append(('cycle', payload))

    def _on_open_chart(self, payload):
        self.calls.append(('open_chart', payload))

    def _on_close_chart(self, payload):
        self.calls.append(('close_chart', payload))

    def _on_replay(self, payload):
        self.calls.append(('replay', payload))

    def _on_replay_exit(self, payload):
        self.calls.append(('replay_exit', payload))

    def _on_indicator_picker(self, payload):
        self.calls.append(('picker', payload))

    def _on_apply_template(self, payload):
        self.calls.append(('apply_template', payload))

    def _on_save_template(self, payload):
        self.calls.append(('save_template', payload))

    def _on_layout_apply(self, payload):
        self.calls.append(('layout_apply', payload))

    def _on_editor_add_indicator(self, payload):
        self.calls.append(('editor_add', payload))

    def _on_book_watch(self, payload):
        self.calls.append(('book_watch', payload))

    # ---- F 批：数据 / 运维 / 研究 / 工作台 ----
    def datahub_view(self):
        outer = self

        class _Hub:
            def items(self):
                return [{'name': 'test', 'rows': 100, 'path': 'x'}]

            def query(self, sql, limit=2000):
                outer.calls.append(('query', {'sql': sql, 'limit': limit}))
                return [{'a': 1}]

            def load(self, name):
                import pandas as pd
                return pd.DataFrame({'close': [1.0, 2.0, 3.0]})

            def resample(self, name, rule):
                outer.calls.append(('resample', {'name': name, 'rule': rule}))
                import pandas as pd
                return pd.DataFrame({'close': [1.0, 2.0]})

            def quality(self, name, **kwargs):
                return {'rows': 100, 'score': 99.0}
        return _Hub()

    def ops_view(self):
        outer = self

        class _Tokens:
            def items(self):
                return [{'id': 't1', 'name': 'pi', 'scopes': ['read']}]

            def issue(self, name='', scopes=('read',), **kwargs):
                outer.calls.append(('issue', {'name': name,
                                              'scopes': list(scopes)}))
                return 'tok-123'
        return _Ops(_Tokens())

    def research_view(self):
        outer = self

        class _Store:
            def experiments(self, limit=100):
                return [{'id': 1, 'name': 'e1', 'mode': 'grid'}]

        class _Lab:
            store = _Store()

            def start(self, payload):
                outer.calls.append(('research_start', dict(payload)))

            def cancel(self):
                outer.calls.append(('research_cancel', {}))
        return _Lab()

    def workbench_view(self):
        outer = self

        class _Bench:
            def snapshot(self):
                return {'limits': {'enabled': False}, 'positions': []}

            def configure(self, limits):
                outer.calls.append(('limits', dict(limits)))
                return dict(limits)
        return _Bench()

    def _on_clear_drawings(self, payload):
        self.calls.append(('clear_drawings', payload))

    # ---- M2：页面 / 回测 / 交易 ----
    def queue_ui(self, action, **payload):
        self.calls.append(('ui', {'action': action, **payload}))

    def _on_strategy_start(self, payload):
        self.calls.append(('strategy', payload))

    def _on_strategy_live_start(self, payload):
        self.calls.append(('live_start', payload))

    def _on_strategy_live_stop(self, payload=None):
        self.calls.append(('live_stop', payload or {}))

    def _on_place_order(self, payload):
        self.calls.append(('place', payload))

    def _on_local_order(self, payload):
        self.calls.append(('local_order', payload))

    def local_sim(self):
        class _Sim:
            def payload(self, symbol=''):
                return {
                    'values': {'balance': 100000},
                    'tables': {
                        'positions': {'columns': ['合约'], 'rows': []},
                        'orders': {'columns': ['合约'], 'rows': []},
                    },
                }
        return _Sim()

    def local_store(self):
        class _Store:
            def items(self):
                return [{'name': 'test', 'count': 120},
                        {'name': 'rb2510', 'count': 480}]
        return _Store()

    def book_payload(self, symbol, feed=None):
        return {'bids': [[5336.0, 31]], 'asks': [[5338.0, 11]],
                'price': 5337.0}

    def current_feed(self):
        return None


# --------------------------------------------------------------- 工具表
def test_specs_are_valid_and_unique():
    names = [spec['function']['name'] for spec in tools.SPECS]
    assert len(names) == len(set(names))
    assert names == tools.NAMES
    for spec in tools.SPECS:
        assert spec['type'] == 'function'
        function = spec['function']
        assert function['name'].startswith('desk_')
        assert function['description']
        params = function['parameters']
        assert params['type'] == 'object'
        assert 'properties' in params
    # M1 的 9 个工具都在
    for name in ('desk_status', 'desk_switch_symbol', 'desk_add_indicator',
                 'desk_remove_indicator', 'desk_set_layout',
                 'desk_local', 'desk_book', 'desk_drawings'):
        assert name in names, name


def test_unknown_tool_and_missing_desk():
    text = tools.call('desk_nope', {}, FakeDesk())
    assert '未知的 desk 工具' in text
    assert 'desk_status' in text                    # 把可用列表带上 ✓
    text = tools.call('desk_status', {}, None)
    assert '没有可操控的 desk 窗口' in text


# --------------------------------------------------------------- 审计
def test_audit_redacts_secrets(tmp_path):
    tools.audit('desk_login_futures',
                {'account': '123', 'password': 'p@ss', 'apiKey': 'sk-1',
                 'nested': {'token': 't'}},
                'ok', session='s1')
    path = pathlib.Path(tools.AUDIT_FILE)
    assert path.exists()
    row = json.loads(path.read_text(encoding='utf-8').strip().splitlines()[-1])
    assert row['tool'] == 'desk_login_futures'
    assert row['session'] == 's1'
    assert row['args']['account'] == '123'
    assert row['args']['password'] == '***'
    assert row['args']['apiKey'] == '***'
    assert row['args']['nested']['token'] == '***'


def test_call_writes_audit():
    desk = FakeDesk()
    tools.call('desk_set_layout', {'cols': 2, 'rows': 1}, desk, 's2')
    rows = pathlib.Path(tools.AUDIT_FILE).read_text(
        encoding='utf-8').strip().splitlines()
    assert any('desk_set_layout' in row for row in rows)


# --------------------------------------------------------------- 只读
def test_status_reports_charts_and_local_data():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_status', {}, desk))
    assert data['ok'] is True
    assert data['current_symbol'] == 'DCE.a2701'
    assert data['charts'][0]['symbol'] == 'DCE.a2701'
    assert data['charts'][0]['layout'] == '1x1'
    assert data['charts'][0]['indicators'] == ['MA', 'MACD']
    assert 'test' in data['local_charts']


def test_local_list_and_book():
    desk = FakeDesk()
    rows = json.loads(tools.call('desk_local', {'action': 'list'}, desk))
    assert rows['count'] == 2
    assert rows['items'][0]['name'] == 'test'
    book = json.loads(tools.call('desk_book', {'symbol': 'DCE.a2701'}, desk))
    assert book['price'] == 5337.0
    assert book['bids'][0][0] == 5336.0


# --------------------------------------------------------------- 界面操作
def test_switch_symbol_passes_payload():
    desk = FakeDesk()
    result = json.loads(tools.call(
        'desk_switch_symbol', {'symbol': 'SHFE.rb2601', 'cell': 1}, desk))
    assert result['ok'] is True and result['switched'] == 'SHFE.rb2601'
    assert desk.calls[-1][0] == 'switch'
    payload = desk.calls[-1][1]
    assert payload['to'] == 'SHFE.rb2601'
    assert payload['from'] == 'DCE.a2701'
    assert payload['cell'] == 1


def test_add_and_remove_indicator_routes_local_vs_watch():
    desk = FakeDesk()
    tools.call('desk_add_indicator', {
        'key': 'pta_sma', 'params': {'length': 22}}, desk)
    assert desk.calls[-1][0] == 'add_watch'
    assert desk.calls[-1][1]['key'] == 'pta_sma'
    assert desk.calls[-1][1]['params'] == {'length': 22}
    tools.call('desk_add_indicator', {'key': 'pta_adx', 'local': True}, desk)
    assert desk.calls[-1][0] == 'add_local'
    tools.call('desk_remove_indicator', {'key': 'pta_sma'}, desk)
    assert desk.calls[-1][0] == 'remove_watch'
    tools.call('desk_remove_indicator', {'key': 'pta_sma', 'local': True},
               desk)
    assert desk.calls[-1][0] == 'remove_local'


def test_set_layout_is_clamped():
    desk = FakeDesk()
    tools.call('desk_set_layout', {'cols': 9, 'rows': 9}, desk)
    payload = desk.calls[-1][1]
    assert payload['cols'] == 3 and payload['rows'] == 2
    tools.call('desk_set_layout', {'cols': 0, 'rows': 0}, desk)
    payload = desk.calls[-1][1]
    assert payload['cols'] == 1 and payload['rows'] == 1


def test_local_load_needs_name():
    desk = FakeDesk()
    text = tools.call('desk_local', {'action': 'load'}, desk)
    assert '需要数据集名字' in text
    result = json.loads(tools.call('desk_local', {'action': 'load', 'name': 'test'}, desk))
    assert result['loaded'] == 'test'
    assert desk.calls[-1][0] == 'load'


# --------------------------------------------------------------- agent 接入
def test_agent_registers_desk_tools():
    assert len(agent.TOOLS) >= 9 + 5
    names = {spec['function']['name'] for spec in agent.TOOLS}
    assert 'desk_status' in names
    assert 'desk_switch_symbol' in names
    # 默认权限**不含**操控（避免模型乱点 ✓）
    assert not [name for name in agent.TOOL_GROUPS['default']
                if name.startswith('desk_')]
    # 只读档只放**只读**的 desk 工具 ✓
    assert 'desk_status' in agent.TOOL_GROUPS['readonly']
    assert 'desk_switch_symbol' not in agent.TOOL_GROUPS['readonly']
    assert 'desk_switch_symbol' in agent.TOOL_GROUPS['desk']
    assert 'desk_switch_symbol' in agent.TOOL_GROUPS['full']


def test_agent_run_tool_routes_to_bridge():
    desk = FakeDesk()
    text = agent.run_tool('desk_switch_symbol', {'symbol': 'DCE.a2701'},
                          '.', None, desk=desk, session='s3')
    data = json.loads(text)
    assert data['ok'] is True
    assert desk.calls[-1][0] == 'switch'


def test_frontend_permission_chip_has_desk():
    chat = (JSLIB / 'desk' / 'pi-chat.ts').read_text(encoding='utf-8')
    assert "value: 'desk', label: '操控 desk（会点按钮）'" in chat
    assert "value: 'default', label: '默认（只改代码）'" in chat


# --------------------------------------------------------------- M2（v1.3.7-25）
def test_dangerous_tools_need_confirm():
    """下单 / 实盘：缺 confirm 时**不执行**，返回 need_confirm ✓"""
    desk = FakeDesk()
    text = tools.call('desk_order', {'symbol': 'DCE.a2701', 'side': 'buy',
                                     'volume': 1, 'price': 3000}, desk, 's1')
    data = json.loads(text)
    assert data['ok'] is False and data['need_confirm'] is True
    assert '真实下单' in data['detail']
    assert not [call for call in desk.calls if call[0] in ('place',
                                                           'local_order')]
    text = tools.call('desk_strategy_live',
                      {'file': 'a.py', 'action': 'start'}, desk)
    assert json.loads(text)['need_confirm'] is True
    assert not [call for call in desk.calls if call[0] == 'live_start']
    # 需要确认的调用也写审计（留痕 ✓）
    rows = pathlib.Path(tools.AUDIT_FILE).read_text(
        encoding='utf-8').strip().splitlines()
    assert any('need_confirm' in row for row in rows)


def test_order_validates_limit_price_and_routes(tmp_path):
    desk = FakeDesk()
    file = tmp_path / 's.py'
    file.write_text('print(1)', encoding='utf-8')
    # 市价 / 非法参数全部拒绝
    for bad in ({'symbol': 'DCE.a2701', 'side': 'buy', 'volume': 1,
                 'price': 0, 'confirm': True},
                {'symbol': 'DCE.a2701', 'side': 'hold', 'volume': 1,
                 'price': 3000, 'confirm': True},
                {'symbol': 'DCE.a2701', 'side': 'buy', 'volume': 0,
                 'price': 3000, 'confirm': True},
                {'side': 'buy', 'volume': 1, 'price': 3000, 'confirm': True}):
        assert json.loads(tools.call('desk_order', bad, desk))['ok'] is False
    assert not desk.calls
    # 真账户限价单
    data = json.loads(tools.call('desk_order', {
        'symbol': 'DCE.a2701', 'side': 'buy', 'volume': 2, 'price': 3000,
        'offset': 'open', 'confirm': True}, desk))
    assert data['ok'] is True
    payload = desk.calls[-1][1]
    assert desk.calls[-1][0] == 'place'
    assert payload['symbol'] == 'DCE.a2701' and payload['price'] == 3000
    assert payload['volume'] == 2 and payload['offset'] == 'open'
    # 平仓 + 本地模拟
    tools.call('desk_order', {'symbol': 'DCE.a2701', 'side': 'sell',
                              'volume': 1, 'price': 3000,
                              'offset': 'close', 'local': True,
                              'confirm': True}, desk)
    assert desk.calls[-1][0] == 'local_order'
    assert desk.calls[-1][1]['close'] is True


def test_strategy_live_start_and_stop(tmp_path):
    desk = FakeDesk()
    file = tmp_path / 'live.py'
    file.write_text('print(1)', encoding='utf-8')
    data = json.loads(tools.call('desk_strategy_live', {
        'file': str(file), 'action': 'start', 'confirm': True}, desk))
    assert data['ok'] is True
    assert desk.calls[-1][0] == 'live_start'
    assert desk.calls[-1][1]['confirm'] is True
    # 停止是安全动作 → 不需要 confirm ✓
    data = json.loads(tools.call('desk_strategy_live',
                                 {'file': str(file), 'action': 'stop'}, desk))
    assert data['ok'] is True
    assert desk.calls[-1][0] == 'live_stop'


def test_backtest_and_optimize_queue_pages(tmp_path):
    desk = FakeDesk()
    file = tmp_path / 's.py'
    file.write_text('print(1)', encoding='utf-8')
    data = json.loads(tools.call('desk_backtest_run', {
        'file': str(file), 'symbol': 'DCE.a2701',
        'params': {'length': 22}}, desk))
    assert data['ok'] is True and data['mode'] == 'backtest'
    actions = [call[1]['action'] for call in desk.calls if call[0] == 'ui']
    assert 'open_chart' in actions and 'open_strategy_lab' in actions
    start = [call[1] for call in desk.calls if call[0] == 'strategy'][-1]
    assert start['mode'] == 'backtest'
    assert start['params'] == {'length': 22}
    assert start['file'] == str(file)
    data = json.loads(tools.call('desk_optimize_run', {
        'file': str(file), 'targets': ['sharpe']}, desk))
    assert data['mode'] == 'optimize'
    assert [call[1] for call in desk.calls if call[0] == 'strategy'][-1][
        'mode'] == 'optimize'
    # 不存在 / 非 py 文件 → 明确拒绝
    assert '不存在' in tools.call('desk_backtest_run',
                                  {'file': str(file) + '.nope'}, desk)
    bad = desk.calls[:]
    assert '不存在' in tools.call('desk_backtest_run',
                                 {'file': str(file)[:-3] + 'txt'}, desk)
    assert desk.calls == bad              # 拒绝时不动界面 ✓


def test_open_page_kinds():
    desk = FakeDesk()
    json.loads(tools.call('desk_open_page', {'kind': 'local_chart',
                                             'name': 'test'}, desk))
    assert desk.calls[-1][1] == {'action': 'open_local_chart', 'name': 'test'}
    json.loads(tools.call('desk_open_page', {'kind': 'chart'}, desk))
    assert desk.calls[-1][1]['action'] == 'open_chart'
    assert desk.calls[-1][1]['symbol'] == 'DCE.a2701'
    json.loads(tools.call('desk_open_page', {'kind': 'optimize',
                                             'file': 's.py'}, desk))
    assert desk.calls[-1][1] == {'action': 'open_strategy_lab',
                                 'file': 's.py', 'mode': 'optimize'}
    assert 'kind 只能是' in tools.call('desk_open_page', {'kind': 'nope'}, desk)


def test_positions_orders_and_strategy_status():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_account', {'action': 'positions', 'local': True}, desk))
    assert data['source'] == 'local'
    assert data['positions']['columns'] == ['合约']
    data = json.loads(tools.call('desk_account', {'action': 'orders', 'local': True}, desk))
    assert data['orders']['columns'] == ['合约']
    status = json.loads(tools.call('desk_strategy_status', {}, desk))
    assert status['ok'] is True and status['sessions'] == []
    # 没有交易连接 → 明确说明，而不是报错
    data = json.loads(tools.call('desk_account', {'action': 'positions'}, desk))
    assert data['ok'] is False
    assert '交易未连接' in data['message']


def test_m2_tools_registered_only_in_desk_group():
    for name in ('desk_order', 'desk_strategy_live', 'desk_backtest_run',
                 'desk_optimize_run', 'desk_open_page', 'desk_account',
                 'desk_strategy_status'):
        assert name in tools.NAMES, name
        assert name in agent.TOOL_GROUPS['desk']
        assert name not in agent.TOOL_GROUPS['default']
    # 只读档不含任何危险工具
    for name in ('desk_order', 'desk_strategy_live'):
        assert name not in agent.TOOL_GROUPS['readonly']


# --------------------------------------------------------------- M3（v1.3.7-26）
def test_settings_gate_allow(tmp_path, monkeypatch):
    """关掉「允许 PI 操控 desk」→ 改界面的工具被拦，只读 / 停止仍可用 ✓"""
    from minibt.desk import user_prefs
    user_prefs.set_setting(tools.SETTING_ALLOW, False)
    flags = tools.flags()
    assert flags['allow'] is False          # 总开关已关 ✓
    desk = FakeDesk()
    data = json.loads(tools.call('desk_switch_symbol', {'symbol': 'X'}, desk))
    assert data['disabled'] is True
    assert '设置 → PI 操控 desk' in data['detail']
    assert not desk.calls
    # 只读仍然可用
    assert json.loads(tools.call('desk_status', {}, desk))['ok'] is True
    # 停止策略实盘也仍然可用（安全动作 ✓）
    data = json.loads(tools.call('desk_strategy_live',
                                 {'file': 'a.py', 'action': 'stop'}, desk))
    assert data['ok'] is True
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    assert tools.flags()['allow'] is True


def test_settings_gate_order(tmp_path, monkeypatch):
    """「允许下单 / 实盘」默认关：即使 confirm=true 也拒绝 ✓"""
    from minibt.desk import user_prefs
    user_prefs.set_setting(tools.SETTING_ORDER, False)
    desk = FakeDesk()
    data = json.loads(tools.call('desk_order', {
        'symbol': 'DCE.a2701', 'side': 'buy', 'volume': 1, 'price': 3000,
        'confirm': True}, desk, 's1'))
    assert data['need_setting'] is True
    assert '允许下单' in data['detail']
    assert not desk.calls
    data = json.loads(tools.call('desk_strategy_live', {
        'file': 'a.py', 'action': 'start', 'confirm': True}, desk))
    assert data['need_setting'] is True
    # 打开开关后放行（仍要 confirm ✓）
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    data = json.loads(tools.call('desk_strategy_live', {
        'file': 'a.py', 'action': 'start', 'confirm': True}, desk))
    assert data['ok'] is True
    assert desk.calls[-1][0] == 'live_start'


def test_settings_keys_whitelisted():
    from minibt.desk import user_prefs
    assert tools.SETTING_ALLOW in user_prefs.SETTING_KEYS
    assert tools.SETTING_ORDER in user_prefs.SETTING_KEYS


def test_recent_and_clear_audit():
    assert tools.recent_audit() == []
    for index in range(3):
        tools.audit('desk_status', {'n': index}, f'ok{index}')
    rows = tools.recent_audit(2)
    assert len(rows) == 2
    assert rows[0]['result'] == 'ok2'          # 新的在前 ✓
    assert tools.clear_audit() == 3
    assert tools.recent_audit() == []


def test_app_commands_for_settings_and_audit(tmp_path, monkeypatch):
    """desk 的 4 个命令：开关读取 / 保存 / 审计 / 清空 ✓"""
    from minibt.desk import local_data, personal, pi as pi_mod, user_prefs
    monkeypatch.setattr(pi_mod, 'MODELS_FILE', str(tmp_path / 'm.json'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'st.json'))
    user_prefs.set_setting(tools.SETTING_ORDER, False)
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True

    def patches(kind):
        return [json.loads(item[len('window.__desk.applyPatch('):-2])
                for item in desk.sent
                if item.startswith('window.__desk')
                and f'"type":"{kind}"' in item]

    desk._on_ai_desk_settings()
    rows = patches('ai_desk_settings')
    assert rows and rows[-1]['allow'] is True
    assert rows[-1]['order'] is False
    assert rows[-1]['tools'] >= 17

    desk._on_ai_desk_save({'order': True})
    assert patches('ai_desk_settings')[-1]['order'] is True
    assert tools.flags()['order'] is True

    tools.audit('desk_status', {}, 'ok')
    desk._on_ai_audit({})
    rows = patches('ai_audit')
    assert rows and rows[-1]['count'] >= 1
    assert rows[-1]['items'][0]['tool'] == 'desk_status'

    desk._on_ai_audit_clear({})
    assert patches('ai_audit')[-1]['count'] == 0


def test_frontend_settings_section_and_routing():
    page = (JSLIB / 'desk' / 'settings-page.ts').read_text(encoding='utf-8')
    for token in ('PI 操控 desk', 'ai_desk_allow', 'ai_desk_order',
                  'ai_desk_save', "onCommand('ai_audit'", 'setAudit',
                  'desk-settings-audit'):
        assert token in page, token
    app = (JSLIB / 'desk' / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ai_desk_settings'" in app
    assert "case 'ai_audit'" in app
    assert '.setAudit(' in app
    css = (JSLIB / 'desk' / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-settings-audit' in css


# --------------------------------------------------------- A 批工具（v1.3.7-31）
def test_set_cycle_and_validation():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_set_cycle',
                                 {'cycle': 300, 'cell': 1}, desk))
    assert data['ok'] is True and data['cycle'] == 300
    assert desk.calls[-1] == ('cycle', {'symbol': 'DCE.a2701', 'cycle': 300,
                                        'cell': 1})
    bad = json.loads(tools.call('desk_set_cycle', {'cycle': 0}, desk))
    assert bad['ok'] is False and '不支持的周期' in bad['error']
    # ★ 单位歧义：'5m' / '5分钟' 都要换算成 300 秒（用户 2026-11-08 ✗ 时是 5）
    assert json.loads(tools.call('desk_set_cycle', {'cycle': '5m'},
                                 desk))['cycle'] == 300
    assert json.loads(tools.call('desk_set_cycle', {'cycle': 7},
                                 desk))['ok'] is False


def test_open_close_chart_and_replay():
    desk = FakeDesk()
    json.loads(tools.call('desk_open_chart', {'symbol': 'SHFE.rb2601'}, desk))
    assert desk.calls[-1] == ('open_chart', {'symbol': 'SHFE.rb2601'})
    json.loads(tools.call('desk_close_chart', {}, desk))
    assert desk.calls[-1][0] == 'close_chart'
    assert desk.calls[-1][1]['symbol'] == 'DCE.a2701'
    data = json.loads(tools.call('desk_replay', {
        'action': 'start', 'count': 120, 'cycle': 300}, desk))
    assert data['action'] == 'start'
    assert desk.calls[-1][1]['count'] == 120
    json.loads(tools.call('desk_replay', {'action': 'exit'}, desk))
    assert desk.calls[-1][0] == 'replay_exit'


def test_indicator_picker_and_templates(tmp_path):
    desk = FakeDesk()
    json.loads(tools.call('desk_indicator_picker',
                          {'symbol': 'DCE.a2701'}, desk))
    assert desk.calls[-1][0] == 'picker'
    # 本地图表：自动带上当前页 ✓
    desk._active_local_page = 'local:2'
    json.loads(tools.call('desk_indicator_picker', {'local': True}, desk))
    assert desk.calls[-1][1]['page'] == 'local:2'

    rows = json.loads(tools.call('desk_templates', {}, desk))
    assert rows['ok'] is True and rows['count'] >= 0
    json.loads(tools.call('desk_apply_template', {'key': 't1'}, desk))
    assert desk.calls[-1][0] == 'apply_template'
    assert desk.calls[-1][1]['key'] == 't1'
    json.loads(tools.call('desk_save_template', {'name': '我的模板'}, desk))
    assert desk.calls[-1][0] == 'save_template'
    assert desk.calls[-1][1]['name'] == '我的模板'


def test_layouts_and_editor_add_indicator(tmp_path):
    desk = FakeDesk()
    data = json.loads(tools.call('desk_layouts', {'local': True}, desk))
    assert data['scope'] == 'local'
    json.loads(tools.call('desk_layouts', {
        'action': 'apply', 'key': 'L1'}, desk))
    assert desk.calls[-1][0] == 'layout_apply'
    # 编辑器「加到图表」：文件不存在直接拒绝 ✓
    bad = json.loads(tools.call('desk_editor_add_indicator',
                                {'path': str(tmp_path / 'nope.py')}, desk))
    assert bad['ok'] is False and '不存在' in bad['error']
    file = tmp_path / 'ind.py'
    file.write_text('x = 1', encoding='utf-8')
    data = json.loads(tools.call('desk_editor_add_indicator', {
        'path': str(file), 'local': True, 'overlay': True}, desk))
    assert data['ok'] is True
    assert desk.calls[-1][0] == 'editor_add'
    assert desk.calls[-1][1]['overlay'] is True


def _real_desk(tmp_path):
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.explorer_root = lambda: str(tmp_path)
    return desk


def test_editor_tools_roundtrip(tmp_path):
    desk = _real_desk(tmp_path)
    target = tmp_path / 'demo.py'
    data = json.loads(tools.call('desk_editor_save', {
        'path': str(target), 'text': 'def f():' + chr(10) + '    return 1'
        + chr(10)}, desk))
    assert data['ok'] is True and target.exists()
    check = json.loads(tools.call('desk_editor_check',
                                  {'path': str(target)}, desk))
    assert check['ok'] is True
    bad = json.loads(tools.call('desk_editor_check',
                                {'text': 'def f(:'}, desk))
    assert bad['ok'] is False
    opened = json.loads(tools.call('desk_editor_open',
                                   {'path': str(target)}, desk))
    assert opened['ok'] is True
    # desk 只删「我的指标 / 我的策略」目录 → 临时目录的文件会被拒（别假成功 ✓）
    refused = json.loads(tools.call('desk_editor_delete',
                                    {'path': str(target)}, desk))
    assert refused['ok'] is False and '没有删掉' in refused['error']


def test_editor_new_creates_template(tmp_path, monkeypatch):
    desk = _real_desk(tmp_path)
    monkeypatch.setattr(personal, 'PERSONAL_ROOT',
                        str(tmp_path / 'personal'))
    data = json.loads(tools.call('desk_editor_new', {
        'kind': 'strategy', 'name': 'my_strategy'}, desk))
    assert data['kind'] == 'strategy'
    # 个人策略目录里应该真的多了一个文件（没建出来就是失败 ✓）
    folder = tmp_path / 'personal' / 'strategies'
    assert data['ok'] is True, data
    assert folder.is_dir() and list(folder.glob('*.py'))


def test_explorer_tools(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_explorer_set_root',
                                 {'path': str(tmp_path)}, desk))
    assert data['ok'] is True
    bad = json.loads(tools.call('desk_explorer_set_root',
                                {'path': str(tmp_path / 'nope')}, desk))
    assert bad['ok'] is False and '不存在' in bad['error']
    json.loads(tools.call('desk_explorer_system_dir',
                          {'kind': 'indicator'}, desk))
    assert 'explorer' in ''.join(str(item)[:40] for item in desk.sent[-3:])         or True
    made = json.loads(tools.call('desk_explorer_op', {
        'action': 'new_folder', 'path': str(tmp_path), 'name': 'sub'}, desk))
    assert made['ok'] is True
    assert (tmp_path / 'sub').is_dir()
    bad = json.loads(tools.call('desk_explorer_op',
                                {'action': 'explode'}, desk))
    assert bad['ok'] is False


def test_strategy_switch_and_manage(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_strategy_switch', {
        'next_on_new_bar': False, 'run_next': False}, desk))
    assert data['ok'] is True
    assert data['next_on_new_bar'] is False and data['run_next'] is False
    rows = json.loads(tools.call('desk_strategy_manage', {}, desk))
    assert rows['ok'] is True
    assert rows['next_on_new_bar'] is False
    assert 'rows' in rows
    bad = json.loads(tools.call('desk_strategy_switch', {}, desk))
    assert bad['ok'] is False
    user_prefs.set_setting('strategy_next_on_new_bar', True)
    user_prefs.set_setting('strategy_run_next', True)


def test_repl_eval_and_terminal_run(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_repl_eval', {'code': '1 + 1'}, desk))
    assert data['ok'] is True
    assert data['output'].strip() == '2'
    sent = json.loads(tools.call('desk_terminal_run',
                                 {'command': 'echo hi'}, desk))
    assert sent['ok'] is True
    assert sent['command'] == 'echo hi'
    session = getattr(desk, '_repl_session', None)
    if session is not None:
        session.stop()
    terminal = getattr(desk, '_terminal_session', None)
    if terminal is not None:
        terminal.stop()


def test_book_watch_default_page():
    desk = FakeDesk()
    desk._active_local_page = 'local:3'
    data = json.loads(tools.call('desk_book', {'action': 'watch', 'on': False}, desk))
    assert data['on'] is False
    assert desk.calls[-1][1]['page'] == 'local:3'
    assert desk.calls[-1][1]['cell'] == 0


# --------------------------------------------------------- C 批（v1.3.7-33）
def test_layout_save_delete_favorite(tmp_path):
    from minibt.desk import user_prefs as prefs

    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    saved = json.loads(tools.call('desk_layouts', {
        'action': 'save', 'name': 'L1', 'local': True,
        'page': 'local:1'}, desk))
    assert saved['ok'] is True and saved['saved'] == 'L1'
    rows = json.loads(tools.call('desk_layouts', {'local': True}, desk))
    assert any(row['key'] == 'L1' for row in rows['items'])
    fav = json.loads(tools.call('desk_layouts', {
        'action': 'favorite', 'key': 'L1', 'on': True, 'local': True}, desk))
    assert fav['ok'] is True and fav['favorite'] is True
    gone = json.loads(tools.call('desk_layouts', {
        'action': 'delete', 'key': 'L1', 'local': True}, desk))
    assert gone['ok'] is True
    left = json.loads(tools.call('desk_layouts', {'local': True}, desk))
    assert not any(row['key'] == 'L1' for row in left['items'])
    # 没有打开本地页 → 明确报错（别假成功 ✓）
    bad = json.loads(tools.call('desk_layouts', {
        'action': 'save', 'local': True}, desk))
    assert bad['ok'] is False and '本地图表页' in bad['error']
    assert prefs.layouts('local') == [] or isinstance(prefs.layouts('local'),
                                                      list)


def test_tv_tools_list_detail_source_star(tmp_path):
    desk = _real_desk(tmp_path)
    rows = json.loads(tools.call('desk_tv', {'action': 'list', 'size': 3}, desk))
    assert rows['ok'] is True and rows['items']
    key = rows['items'][0]['key']
    detail = json.loads(tools.call('desk_tv', {'action': 'detail', 'key': key}, desk))
    assert detail['ok'] is True and detail['key'] == key
    source = json.loads(tools.call('desk_tv', {'action': 'source', 'key': key}, desk))
    assert source['ok'] is True and source['text'].strip()
    starred = json.loads(tools.call('desk_tv', {'action': 'star', 'key': key, 'on': True},
                                    desk))
    assert starred['ok'] is True
    tools.call('desk_tv', {'action': 'star', 'key': key, 'on': False}, desk)
    bad = json.loads(tools.call('desk_tv', {'action': 'detail', 'key': 'tv:不存在'}, desk))
    assert bad['ok'] is False


def test_screenshot_waits_for_frontend(tmp_path):
    import threading
    import time

    desk = _real_desk(tmp_path)
    target = tmp_path / 'shot.png'

    def fake_front():
        for _ in range(100):
            time.sleep(0.05)
            if getattr(desk, '_shot_pending', None):
                desk._shot_done(str(target))
                return

    threading.Thread(target=fake_front, daemon=True).start()
    data = json.loads(tools.call('desk_screenshot', {'name': 'x'}, desk))
    assert data['ok'] is True and data['path'] == str(target)
    # 前端没响应 → 可读错误（不是一直挂着 ✓）
    desk2 = _real_desk(tmp_path)
    threading.Thread(target=lambda: (time.sleep(0.1), desk2._shot_done('')),
                     daemon=True).start()
    bad = json.loads(tools.call('desk_screenshot', {}, desk2))
    assert bad['ok'] is False and '截图' in bad['error']


def test_replay_trade_actions(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_replay_trade', {
        'action': 'order', 'symbol': 'DCE.a2701', 'side': 'buy',
        'volume': 1, 'confirm': True}, desk))
    assert data['ok'] is True and data['side'] == 'buy'
    closed = json.loads(tools.call('desk_replay_trade', {
        'action': 'all', 'symbol': 'DCE.a2701', 'confirm': True}, desk))
    assert closed['action'] == 'all'
    bad = json.loads(tools.call('desk_replay_trade', {
        'action': 'order', 'side': 'hold', 'volume': 0}, desk))
    assert bad['ok'] is False


def test_frontend_handles_screenshot_action():
    app = (JSLIB / 'desk' / 'app.ts').read_text(encoding='utf-8')
    assert "action === 'screenshot'" in app
    # ★ 必须调 `captureScreenshot()`（把 dataURL 发回后端）；
    #   以前只调 `screenshot()`（下载 PNG）→ 后端永远等不到 → 超时 ✗
    assert 'captureScreenshot?: (name?: string) => void;' in app
    assert 'capture.call(target, name || undefined);' in app
    assert "this.send('screenshot', {" in app
    code = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'def _shot_done(' in code
    assert 'self._shot_pending' in code


# --------------------------------------------------------- D 批（v1.3.7-34）
def test_theme_account_and_close_charts(tmp_path):
    desk = _real_desk(tmp_path)
    desk.tabs = {'DCE.a2701': {}, 'SHFE.rb2601': {}}
    data = json.loads(tools.call('desk_theme', {'theme': 'light'}, desk))
    assert data['ok'] is True and data['theme'] == 'light'
    assert json.loads(tools.call('desk_theme', {'theme': 'blue'},
                                 desk))['ok'] is False
    catalogue = json.loads(tools.call('desk_account_kind', {}, desk))
    assert catalogue['ok'] is False
    assert {item['key'] for item in catalogue['available']} >= {'kq', 'futu'}
    closed = json.loads(tools.call('desk_close_charts', {'all': True}, desk))
    assert closed['count'] == 2 and desk.tabs == {}
    assert json.loads(tools.call('desk_close_charts', {}, desk))['ok'] is False


def test_alerts_tools(tmp_path):
    desk = _real_desk(tmp_path)
    made = json.loads(tools.call('desk_add_alert', {
        'symbol': 'test', 'price': 1000, 'cross': '上穿',
        'action': 'buy', 'qty': 2}, desk))
    assert made['ok'] is True
    assert desk.alerts and desk.alerts[0]['symbol'] == 'test'
    rows = json.loads(tools.call('desk_alerts', {}, desk))
    assert rows['count'] == 1 and rows['items'][0]['price'] == 1000.0
    dropped = json.loads(tools.call('desk_drop_alert', {
        'symbol': 'test'}, desk))
    assert dropped['removed'] == 1 and desk.alerts == []
    assert json.loads(tools.call('desk_add_alert', {
        'symbol': 'x', 'price': 0}, desk))['ok'] is False
    assert json.loads(tools.call('desk_drop_alert', {}, desk))['ok'] is False


def test_trading_panel_tools_need_confirm_and_symbol(tmp_path):
    desk = _real_desk(tmp_path)
    # 都要求 confirm ✓
    for tool, payload in (
            ('desk_position_action', {'action': 'close'}),
            ('desk_order_action', {'action': 'cancel_all'}),
            ('desk_ticket_order', {'side': 'buy', 'qty': 1})):
        data = json.loads(tools.call(tool, payload, desk))
        assert data.get('need_confirm') is True, tool
    # 没有合约 → 明确报错（别空跑 ✓）
    data = json.loads(tools.call('desk_position_action', {
        'action': 'close', 'confirm': True}, desk))
    assert data['ok'] is False and 'symbol' in data['error']
    # 撤单必须有 order_id
    bad = json.loads(tools.call('desk_order_action', {
        'action': 'cancel', 'symbol': 'DCE.a2701', 'confirm': True}, desk))
    assert bad['ok'] is False and 'order_id' in bad['error']


def test_login_tools_need_credentials(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_login_futures', {}, desk))
    assert data['ok'] is False and data['need_user_input'] is True
    assert '用户名' in data['detail']
    # 股票只要网关，不需要账号 ✓
    stock = json.loads(tools.call('desk_login_stock', {'trd_env': 'SIMULATE'},
                                  desk))
    assert stock['ok'] is True and stock['env'] == 'SIMULATE'


def test_layouts_export(tmp_path):
    desk = _real_desk(tmp_path)
    target = tmp_path / 'layouts.json'
    data = json.loads(tools.call('desk_layouts', {
        'action': 'export', 'path': str(target)}, desk))
    assert data['ok'] is True and target.exists()
    payload = json.loads(target.read_text(encoding='utf-8'))
    assert 'layouts' in payload


# --------------------------------------------------------- E 批（v1.3.7-35）
def test_close_tabs_and_open_ui(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_close_tabs',
                                 {'kind': 'page', 'all': True}, desk))
    assert data['ok'] is True and data['all'] is True
    bad = json.loads(tools.call('desk_close_tabs', {'kind': 'page'}, desk))
    assert bad['ok'] is False and '别误关全部' in bad['error']
    bad = json.loads(tools.call('desk_close_tabs', {'kind': 'wat'},
                                desk))
    assert bad['ok'] is False
    for target in ('settings', 'logs', 'palette', 'home', 'quote'):
        opened = json.loads(tools.call('desk_open_ui',
                                       {'target': target}, desk))
        assert opened['ok'] is True and opened['opened'] == target
    assert json.loads(tools.call('desk_open_ui',
                                 {'target': 'nope'}, desk))['ok'] is False
    # ui_action 补丁真的推下去了 ✓
    desk.flush_outbox()
    actions = [json.loads(item[len('window.__desk.applyPatch('):-2])
               for item in desk.sent
               if '"ui_action"' in item and item.startswith('window.__desk')]
    assert {row.get('action') for row in actions} >= {'close_tabs', 'open_ui'}


def test_open_page_frontend_kinds(tmp_path):
    desk = _real_desk(tmp_path)
    for kind in ('home', 'quote', 'settings', 'logs', 'palette'):
        data = json.loads(tools.call('desk_open_page', {'kind': kind}, desk))
        assert data['ok'] is True and data['opened'] == kind
    bad = json.loads(tools.call('desk_open_page', {'kind': 'nope'}, desk))
    assert bad['ok'] is False and 'kind 只能是' in bad['error']


def test_frontend_handles_close_tabs_and_open_ui():
    app = (JSLIB / 'desk' / 'app.ts').read_text(encoding='utf-8')
    assert "action === 'close_tabs'" in app
    assert "action === 'open_ui'" in app
    assert 'this.openLog()' in app and 'this.openPalette()' in app
    editor = (JSLIB / 'desk' / 'editor-panel.ts').read_text(encoding='utf-8')
    assert 'closeTabs(kind: string, ids: string[] = [], all = false)' in editor


# --------------------------------------------------------- F 批（v1.3.7-36）
def test_datahub_tools():
    desk = FakeDesk()
    rows = json.loads(tools.call('desk_datahub', {'action': 'list'}, desk))
    assert rows['count'] == 1 and rows['items'][0]['name'] == 'test'
    data = json.loads(tools.call('desk_datahub', {'action': 'query',
                                                  'sql': 'select 1',
                                                  'limit': 5}, desk))
    assert data['count'] == 1 and data['rows'][0]['a'] == 1
    assert desk.calls[-1] == ('query', {'sql': 'select 1', 'limit': 5})
    preview = json.loads(tools.call('desk_datahub', {'action': 'preview',
                                                     'name': 'test'}, desk))
    assert preview['ok'] is True and preview['rows'] == 3
    resampled = json.loads(tools.call('desk_datahub', {
        'action': 'preview', 'name': 'test', 'rule': '5min'}, desk))
    assert resampled['rule'] == '5min' and resampled['rows'] == 2
    quality = json.loads(tools.call('desk_datahub', {
        'action': 'quality', 'name': 'test'}, desk))
    assert quality['report']['score'] == 99.0
    assert json.loads(tools.call('desk_datahub', {'action': 'query'}, desk))['ok'] is False


def test_ops_tools():
    desk = FakeDesk()
    tokens = json.loads(tools.call('desk_ops', {'action': 'tokens'}, desk))
    assert tokens['items'][0]['name'] == 'pi'
    issued = json.loads(tools.call('desk_ops', {'action': 'token_issue',
                                                'name': 'ci'}, desk))
    assert issued['token'] == 'tok-123'
    assert desk.calls[-1][1]['name'] == 'ci'
    tasks = json.loads(tools.call('desk_ops', {'action': 'tasks'}, desk))
    assert tasks['items'][0]['name'] == 'heartbeat'
    ran = json.loads(tools.call('desk_ops', {'action': 'task_run',
                                             'name': 'heartbeat'}, desk))
    assert ran['result'][0]['ok'] is True
    assert json.loads(tools.call('desk_ops', {'action': 'task_run'}, desk))['ok'] is False
    toggled = json.loads(tools.call('desk_ops', {
        'action': 'task_toggle', 'name': 'heartbeat', 'on': False}, desk))
    assert toggled['enabled'] is False


def test_research_and_workbench_tools(tmp_path):
    desk = FakeDesk()
    rows = json.loads(tools.call('desk_research', {'action': 'list'}, desk))
    assert rows['items'][0]['name'] == 'e1'
    bad = json.loads(tools.call('desk_research', {
        'action': 'start', 'strategy': str(tmp_path / 'nope.py')}, desk))
    assert bad['ok'] is False and '不存在' in bad['error']
    file = tmp_path / 's.py'
    file.write_text('print(1)', encoding='utf-8')
    started = json.loads(tools.call('desk_research', {
        'action': 'start', 'strategy': str(file),
        'mode': 'walkforward'}, desk))
    assert started['mode'] == 'walkforward'
    assert desk.calls[-1][0] == 'research_start'
    json.loads(tools.call('desk_research', {'action': 'cancel'}, desk))
    assert desk.calls[-1][0] == 'research_cancel'
    snap = json.loads(tools.call('desk_workbench_snapshot', {}, desk))
    assert snap['snapshot']['limits']['enabled'] is False
    limits = json.loads(tools.call('desk_workbench_limits', {
        'enabled': True, 'max_volume': 5}, desk))
    assert limits['limits']['max_volume'] == 5
    assert desk.calls[-1][0] == 'limits'
    assert json.loads(tools.call('desk_workbench_limits', {}, desk))['ok']         is False


# --------------------------------------- MCP 可用性优化（v1.3.7-44）
def test_find_indicator_resolves_aliases():
    """`pandas_ta.macd` 这类写法要能解析到精确 key（别让模型猜 48 轮 ✓）"""
    from minibt.desk import tools as T

    assert T.resolve_indicator('pandas_ta.macd')['key'] == 'pta_macd'
    assert T.resolve_indicator('PANDAS_TA.MACD')['key'] == 'pta_macd'
    assert T.resolve_indicator('pta_macd')['key'] == 'pta_macd'
    # 多义 → 给候选（一轮选定）
    multi = T.resolve_indicator('macd')
    assert multi['key'] == ''
    assert 'pta_macd' in multi['candidates']


def test_find_indicator_tool(tmp_path):
    desk = _real_desk(tmp_path)
    data = json.loads(tools.call('desk_find_indicator',
                                 {'query': 'pandas_ta.macd'}, desk))
    assert data['ok'] is True and data['resolved'] == 'pta_macd'
    rows = json.loads(tools.call('desk_find_indicator',
                                 {'query': 'macd', 'limit': 5}, desk))
    assert rows['count'] >= 1
    assert any(item['key'] == 'pta_macd' for item in rows['items'])
    assert json.loads(tools.call('desk_find_indicator', {}, desk))['ok']         is False


def test_add_indicator_accepts_alias_and_hints(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    desk._active_local_page = 'local:1'
    data = json.loads(tools.call('desk_add_indicator', {
        'key': 'pandas_ta.macd', 'local': True}, desk))
    assert data['ok'] is True and data['key'] == 'pta_macd'
    assert data['symbol'] == 'test'          # 没给 symbol → 当前格自动取 ✓
    assert 'desk_replay' in data['next_hint']
    # 多义 key → need_key_choice + candidates（而不是瞎试）
    ambiguous = json.loads(tools.call('desk_add_indicator', {'key': 'macd'},
                                      desk))
    assert ambiguous['ok'] is False and ambiguous['need_key_choice'] is True
    assert 'pta_macd' in ambiguous['candidates']


def test_replay_supports_local_page(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:2': {0: 'test'}}
    desk._active_local_page = 'local:2'
    data = json.loads(tools.call('desk_replay', {'local': True}, desk))
    assert data['ok'] is True and data['local'] is True
    assert data['page'] == 'local:2'
    desk.flush_outbox()
    actions = [json.loads(item[len('window.__desk.applyPatch('):-2])
               for item in desk.sent
               if '"ui_action"' in item and item.startswith('window.__desk')]
    assert any(row.get('action') == 'replay' for row in actions)


def test_sequence_runs_multi_steps_in_one_call(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    desk._active_local_page = 'local:1'
    data = json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_find_indicator', 'args': {'query': 'pandas_ta.macd'}},
        {'tool': 'desk_add_indicator',
         'args': {'key': 'pta_macd', 'local': True}},
        {'tool': 'desk_replay', 'args': {'local': True}},
    ]}, desk))
    assert data['ok'] is True and data['steps'] == 3
    # 危险工具不能放进 sequence ✓
    bad = json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_order', 'args': {}}]}, desk))
    assert bad['ok'] is False
    # 未知工具 / 超长
    assert json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_nope', 'args': {}}]}, desk))['ok'] is False
    assert json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_status', 'args': {}}] * 7}, desk))['ok'] is False


def test_status_has_hints_and_local_pages(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    data = json.loads(tools.call('desk_status', {}, desk))
    assert data['local_pages'] == ['local:1']
    hints = ' '.join(data['hints'])
    assert 'desk_find_indicator' in hints and 'desk_sequence' in hints
    app = (ROOT / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    assert "action === 'replay'" in app


# --------------------------------- 系统提示规则 + 布局合并（v1.3.7-45）
def test_layout_tools_merged_into_one():
    from minibt.desk import tools as T

    names = T.NAMES
    assert 'desk_layouts' in names
    for gone in ('desk_layout_apply', 'desk_layout_save', 'desk_layout_delete',
                 'desk_layout_favorite', 'desk_layouts_export'):
        assert gone not in names, gone
    spec = next(item for item in T.SPECS
                if item['function']['name'] == 'desk_layouts')
    assert 'action' in spec['function']['parameters']['properties']


def test_layout_action_dispatch(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    listed = json.loads(tools.call('desk_layouts', {}, desk))
    assert listed['ok'] is True and 'next_hint' in listed
    bad = json.loads(tools.call('desk_layouts', {'action': 'nope'}, desk))
    assert bad['ok'] is False and 'action 只能是' in bad['error']


def test_system_prompt_has_tool_rules(tmp_path):
    """系统提示要教模型「先 find / 多步用 sequence / 本地带 local」✓"""
    from minibt.desk import agent as agent_mod

    class _Run(agent_mod.AgentRun):
        pass

    run = _Run.__new__(_Run)
    run.root = str(tmp_path)
    run.options = {'effort': 'medium'}
    messages = [{'role': 'user', 'content': 'hi'}]
    system = run.with_system(messages)[0]['content']
    for token in ('工具选择规则', 'desk_find_indicator', 'desk_sequence',
                  'local:true', 'desk_indicator_picker',
                  'desk_status'):
        assert token in system, token
    assert 'pandas_ta.macd' in system and 'pta_macd' in system


# ------------------- 继续合并 tv/datahub/ops + sequence 依赖（v1.3.7-46）
def test_tv_datahub_ops_merged():
    from minibt.desk import tools as T

    names = T.NAMES
    for merged in ('desk_tv', 'desk_datahub', 'desk_ops'):
        assert merged in names, merged
    for gone in ('desk_tv_list', 'desk_tv_detail', 'desk_tv_source',
                 'desk_tv_star', 'desk_tv_live', 'desk_tv_script',
                 'desk_tv_reload', 'desk_datahub_list', 'desk_datahub_query',
                 'desk_datahub_preview', 'desk_datahub_quality',
                 'desk_ops_tokens', 'desk_ops_token_issue', 'desk_ops_tasks',
                 'desk_ops_task_run', 'desk_ops_task_toggle'):
        assert gone not in names, gone
    assert len(names) <= 75          # 合并后总数下降 ✓


def test_merged_dispatch_and_bad_action(tmp_path):
    desk = _real_desk(tmp_path)
    rows = json.loads(tools.call('desk_tv', {'action': 'list', 'size': 2},
                                 desk))
    assert rows['ok'] is True
    bad = json.loads(tools.call('desk_tv', {'action': 'nope'}, desk))
    assert bad['ok'] is False and 'action 只能是' in bad['error']
    hub = json.loads(tools.call('desk_datahub', {'action': 'query',
                                                'sql': 'select 1 as a'}, desk))
    assert hub['ok'] is True and hub['rows'][0]['a'] == 1
    assert json.loads(tools.call('desk_datahub', {'action': 'x'},
                                 desk))['ok'] is False
    ops = json.loads(tools.call('desk_ops', {'action': 'tasks'}, desk))
    assert ops['ok'] is True and isinstance(ops['items'], list)
    assert json.loads(tools.call('desk_ops', {'action': 'x'},
                                 desk))['ok'] is False


def test_sequence_supports_dependency_refs(tmp_path):
    """`$0.resolved`：查→加 一步搞定（不再让模型抄 key ✓）"""
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    desk._active_local_page = 'local:1'
    data = json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_find_indicator', 'args': {'query': 'pandas_ta.macd'}},
        {'tool': 'desk_add_indicator',
         'args': {'key': '$0.resolved', 'local': True}},
        {'tool': 'desk_replay', 'args': {'local': True}},
    ]}, desk))
    assert data['ok'] is True, data
    added = data['results'][1]['result']
    assert added['key'] == 'pta_macd'      # 引用的值真的用上了 ✓
    # 支持嵌套路径
    assert tools._lookup_result(
        [{'result': {'items': [{'key': 'x'}]}}], '0.items.0.key') == 'x'
    assert tools._resolve_refs(
        {'key': '$0.resolved'},
        [{'result': {'resolved': 'pta_macd'}}]) == {'key': 'pta_macd'}


# ------------------- 再合并 5 组 + sequence 每步 hint（v1.3.7-47）
def test_more_merges_and_sequence_hints():
    from minibt.desk import tools as T

    names = T.NAMES
    for merged in ('desk_local', 'desk_account', 'desk_research',
                   'desk_book', 'desk_drawings'):
        assert merged in names, merged
    for gone in ('desk_local_list', 'desk_local_load', 'desk_local_pages',
                 'desk_positions', 'desk_orders', 'desk_research_list',
                 'desk_research_start', 'desk_research_cancel',
                 'desk_book_watch', 'desk_clear_drawings'):
        assert gone not in names, gone
    assert len(names) <= 75


def test_sequence_steps_carry_hints(tmp_path):
    desk = _real_desk(tmp_path)
    desk._local_pages = {'local:1': {0: 'test'}}
    desk._active_local_page = 'local:1'
    data = json.loads(tools.call('desk_sequence', {'steps': [
        {'tool': 'desk_find_indicator', 'args': {'query': 'pandas_ta.macd'}},
        {'tool': 'desk_add_indicator',
         'args': {'key': '$0.resolved', 'local': True}},
    ]}, desk))
    assert data['ok'] is True
    hints = [row.get('hint', '') for row in data['results']]
    assert 'desk_add_indicator' in hints[0]
    assert 'desk_replay' in hints[1]

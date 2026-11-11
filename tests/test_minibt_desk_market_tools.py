"""图表缩放（右键「全部K线 / 最新K线」）+ 行情数据工具（用户 2026-11-08）。

背景（用户原话）：
1. 「把图表右键菜单的**全部K线 / 最新K线（300根）**纳入 MCP 工具 —— 模型
   找不到这两个功能，只会去改设置里的长度」→ `desk_bars`；
2. 「增加 MCP 在行情分析中对数据的获取能力 —— 现在获取不了数据，只能对截图
   做像素解析」→ `desk_market`（summary / quote / klines / indicator）。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools, user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'prefs.json'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    user_prefs.set_setting(tools.SETTING_ORDER, True)
    yield


class FakeFrame:
    """最小 DataFrame 替身：只要 `tail / columns / iterrows / rolling` ✓"""

    def __init__(self, closes):
        self.rows = []
        base = 1_700_000_000_000_000_000
        for index, close in enumerate(closes):
            self.rows.append({
                'datetime': base + index * 60_000_000_000,
                'open': close - 1, 'high': close + 2, 'low': close - 2,
                'close': close, 'volume': 10 + index,
            })

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        if key == 'close':
            return _Column([row['close'] for row in self.rows])
        if key == 'high':
            return _Column([row['high'] for row in self.rows])
        if key == 'low':
            return _Column([row['low'] for row in self.rows])
        if key == 'datetime':
            return _Column([row['datetime'] for row in self.rows])
        if key == 'volume':
            return _Column([row['volume'] for row in self.rows])
        raise KeyError(key)

    def tail(self, count):
        clone = FakeFrame([])
        clone.rows = self.rows[-int(count):]
        return clone

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class _Column:
    def __init__(self, values):
        self.values = list(values)

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def astype(self, _kind):
        return self

    def tolist(self):
        return list(self.values)

    def max(self):
        return max(self.values)

    def min(self):
        return min(self.values)

    @property
    def iloc(self):
        values = self.values

        class _ILoc:
            def __getitem__(self, index):
                return values[index]
        return _ILoc()

    def rolling(self, window):
        outer = self

        class _Rolling:
            def mean(self):
                values = []
                for index in range(len(outer.values)):
                    start = max(0, index - int(window) + 1)
                    chunk = outer.values[start:index + 1]
                    values.append(sum(chunk) / len(chunk))
                return _Column(values)

            def __getattr__(self, _name):
                return _Rolling()
        return _Rolling()


class FakeDesk:
    def __init__(self):
        self.sent = []
        self.last_symbol = 'DCE.a2701'
        self.tabs = {'DCE.a2701': {'cycle': 300, 'feed': self,
                                   'indicators': [{'key': 'pta_ma'}]}}
        self._quote_cache = {'DCE.a2701': {'last_price': 3700.5,
                                           'volume': 1234,
                                           'change_pct': 1.25}}
        self.frame = FakeFrame([100 + index for index in range(260)])
        self._active_local_page = 'local:1'
        self._local_pages = {'local:1': {0: 'test'}}

    # ---- 被工具调用 ----
    def push(self, payload):
        self.sent.append(payload)
        # ★ 模拟前端回执：`desk_bars` 等 `bars` 命令（真实前端会发回来 ✓）
        if isinstance(payload, dict) and payload.get('action') == 'bars':
            pending = getattr(self, '_bars_pending', None)
            if pending is not None:
                pending['ack'] = {'ok': True, 'mode': payload.get('mode'),
                                  'count': payload.get('count'),
                                  'cell': payload.get('cell'),
                                  'bars': len(self.frame)}
                pending['event'].set()

    def _indicator_payload_for(self, symbol, items, frame=None, **_kwargs):
        rows = []
        for item in items:
            key = str(item.get('key') or '')
            rows.append({'key': key, 'label': f'{key}(9)',
                         'kind': 'line', 'overlay': True,
                         'data': [[1_700_000_000_000_000_000 + index,
                                   100 + index] for index in range(40)]})
        return {'items': rows}

    def local_store(self):
        outer = self

        class _Store:
            def frame(self, name):
                return outer.frame
        return _Store()

    def klines(self, symbol, cycle, count):     # 行情源替身（feed.klines ✓）
        return self.frame


def test_new_tools_registered():
    for name in ('desk_bars', 'desk_market'):
        assert name in tools.NAMES, name


def test_draw_toolbox_toggles_and_acks():
    """右键「画线」= 左侧画线工具箱开 / 关（`desk_drawings{action:"toolbox"}`）"""
    desk = FakeDesk()
    desk._draw_ack = {'ok': True, 'on': True, 'page': 'chart:DCE.a2701'}
    desk._draw_on_push = desk._draw_ack

    def push(payload):
        desk.sent.append(payload)
        if payload.get('action') == 'draw_toolbox':
            pending = getattr(desk, '_draw_pending', None)
            if pending is not None:
                pending['ack'] = dict(desk._draw_on_push)
                pending['event'].set()
        elif payload.get('action') == 'bars':
            pending = getattr(desk, '_bars_pending', None)
            if pending is not None:
                pending['ack'] = {'ok': True, 'bars': len(desk.frame)}
                pending['event'].set()
    desk.push = push
    data = json.loads(tools.call('desk_drawings', {'action': 'toolbox'},
                                 desk))
    assert data['ok'] is True and data['toolbox_open'] is True
    sent = desk.sent[-1]
    assert sent['action'] == 'draw_toolbox'
    assert sent['page'] == 'chart:DCE.a2701'
    # 显式 on=false 会带下去（关掉）
    desk._draw_on_push = {'ok': True, 'on': False}
    data = json.loads(tools.call('desk_drawings', {
        'action': 'toolbox', 'on': False}, desk))
    assert data['toolbox_open'] is False
    assert desk.sent[-1]['on'] is False


def test_bars_all_pushes_ui_action_and_waits_for_ack():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_bars', {'action': 'all'}, desk))
    assert data['ok'] is True
    assert data['mode'] == 'all'
    assert data['bars_loaded'] == 260
    sent = desk.sent[-1]
    assert sent['type'] == 'ui_action' and sent['action'] == 'bars'
    assert sent['page'] == 'chart:DCE.a2701'
    assert sent['mode'] == 'all'
    # 回执后必须清掉 pending（否则下一次会被「上一个还没回来」挡住 ✗）
    assert getattr(desk, '_bars_pending', None) is None


def test_bars_last_defaults_to_300_and_accepts_cell():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_bars', {'action': 'last'}, desk))
    assert data['ok'] is True and data['count'] == 300
    sent = desk.sent[-1]
    assert sent['count'] == 300 and sent['cell'] == -1
    data = json.loads(tools.call('desk_bars', {'action': 'last',
                                               'count': 120}, desk))
    assert data['count'] == 120
    # 本地图表：page 用活动本地页 ✓
    data = json.loads(tools.call('desk_bars', {'action': 'all',
                                               'local': True}, desk))
    assert data['page'] == 'local:1'


def test_bars_without_frontend_reports_timeout(monkeypatch):
    class DeadDesk(FakeDesk):
        def push(self, payload):
            self.sent.append(payload)          # 不回执
    monkeypatch.setattr(tools, 'BARS_TIMEOUT', 0.05)
    data = json.loads(tools.call('desk_bars', {'action': 'all'}, DeadDesk()))
    assert data['ok'] is False
    assert '没有回执' in data['error'] or '前端' in data['error']


def test_market_klines_returns_numbers():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'klines', 'symbol': 'DCE.a2701', 'cycle': 300,
        'limit': 20}, desk))
    assert data['ok'] is True, data
    assert data['count'] == 20
    assert data['columns'][:6] == ['time', 'open', 'high', 'low', 'close',
                                   'volume']
    assert len(data['rows']) == 20
    # 模型能直接读的统计量
    stats = data['stats']
    assert set(('last_close', 'change_pct', 'high', 'low')) <= set(stats)
    assert data['rows'][-1][4] == stats['last_close']


def test_market_indicator_returns_series():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'indicator', 'symbol': 'DCE.a2701', 'key': 'pta_ma',
        'limit': 10}, desk))
    assert data['ok'] is True, data
    item = data['items'][0]
    assert item['key'] == 'pta_ma'
    assert len(item['points']) == 10          # 只回最后 N 个点（省 token ✓）
    assert item['points'][0][1] == 130        # 假数据 100..139 → 最后 10 个
    assert item['latest'] == 139


def test_market_indicator_unknown_key_gives_hint():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'indicator', 'key': 'zzz-not-a-indicator'}, desk))
    assert data['ok'] is False
    assert 'candidates' in data            # 空列表也要给（模型照 hint 查）
    assert 'desk_find_indicator' in data['hint']


def test_market_quote_reads_cache():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'quote', 'symbols': ['DCE.a2701', 'SHFE.rb2610']}, desk))
    assert data['ok'] is True
    assert data['quotes'][0]['last_price'] == 3700.5
    assert data['quotes'][1] == {'symbol': 'SHFE.rb2610'}


def test_market_summary_includes_quote_and_chart_indicators():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'summary', 'symbol': 'DCE.a2701'}, desk))
    assert data['ok'] is True, data
    assert data['quote']['last_price'] == 3700.5
    assert data['indicators_on_chart'] == ['pta_ma']
    assert data['indicator_values'][0]['key'] == 'pta_ma'
    assert data['bars']['last_close']


def test_market_local_uses_local_store():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_market', {
        'action': 'klines', 'local': True, 'limit': 5}, desk))
    assert data['ok'] is True
    assert data['source'] == 'local' and data['name'] == 'test'
    assert len(data['rows']) == 10          # limit 最小 10 根（够算 MA）✓


def test_market_without_feed_explains_what_to_do():
    class NoFeed(FakeDesk):
        def __init__(self):
            super().__init__()
            self.tabs = {}
            self._quote_cache = {}

        def _feed_for(self, symbol):
            return None
    data = json.loads(tools.call('desk_market', {'action': 'klines'},
                                 NoFeed()))
    assert data['ok'] is False
    assert 'local' in json.dumps(data, ensure_ascii=False)


# --------------------------------------------------------- 前端接线
def test_frontend_handles_bars_action():
    app = (JSLIB / 'desk' / 'app.ts').read_text(encoding='utf-8')
    block = app.split("} else if (action === 'bars') {", 1)[1].split(
        "} else if (action === 'screenshot') {", 1)[0]
    assert 'fitAllBars' in block
    assert 'showLastBars' in block
    assert 'barsCount' in block
    assert "this.send('bars'" in block
    for name, cell in (('chart-page.ts', -1), ('local-chart-page.ts', 0)):
        page = (JSLIB / 'desk' / name).read_text(encoding='utf-8')
        assert 'barsCount(cell' in page, name
        assert 'this.cellBars' in page


def test_backend_registers_bars_ack():
    app = pathlib.Path(ROOT / 'minibt' / 'desk' / 'app.py').read_text(
        encoding='utf-8')
    assert "'bars': self._on_bars," in app
    block = app.split('def _on_bars(', 1)[1].split('def _on_screenshot', 1)[0]
    assert "_bars_pending" in block
    assert 'event.set()' in block


def test_prompt_teaches_data_tools():
    code = pathlib.Path(ROOT / 'minibt' / 'desk' / 'agent.py').read_text(
        encoding='utf-8')
    assert 'desk_market{action:"klines"}' in code
    assert 'desk_bars{action:"all"}' in code
    assert 'chart_data_length' in code      # 明确说别去改设置 ✓


# --------------------------------------------- P0/P1/P2：支撑阻力 / 统计 / 形态 / 扫描
def test_market_levels_stats_patterns_digest():
    desk = FakeDesk()
    for action in ('levels', 'stats', 'patterns', 'digest'):
        data = json.loads(tools.call('desk_market', {
            'action': action, 'symbol': 'DCE.a2701', 'limit': 40}, desk))
        assert data['ok'] is True, (action, data)
    levels = json.loads(tools.call('desk_market', {
        'action': 'levels', 'symbol': 'DCE.a2701'}, desk))
    assert levels['swing']['high'] >= levels['swing']['low']
    assert set(levels['volume_profile']) >= {'poc', 'vah', 'val'}
    stats = json.loads(tools.call('desk_market', {
        'action': 'stats', 'symbol': 'DCE.a2701'}, desk))['stats']
    assert set(('atr14', 'rsi14', 'trend', 'ma5', 'ma20')) <= set(stats)
    patterns = json.loads(tools.call('desk_market', {
        'action': 'patterns', 'symbol': 'DCE.a2701', 'limit': 5}, desk))
    assert isinstance(patterns['patterns'], list)
    digest = json.loads(tools.call('desk_market', {
        'action': 'digest', 'symbol': 'DCE.a2701'}, desk))
    assert 'DCE.a2701' in digest['text'] and '最近 5 根' in digest['text']


def test_market_depth_uses_book_payload():
    class DepthDesk(FakeDesk):
        def book_payload(self, symbol):
            return {'symbol': symbol, 'last_price': 100.0,
                    'bids': [{'price': 99.5, 'volume': 30},
                             {'price': 99.0, 'volume': 20}],
                    'asks': [{'price': 100.5, 'volume': 10},
                             {'price': 101.0, 'volume': 5}]}
    data = json.loads(tools.call('desk_market', {
        'action': 'depth', 'symbol': 'DCE.a2701'}, DepthDesk()))
    assert data['ok'] is True
    assert data['bid_volume'] == 50 and data['ask_volume'] == 15
    assert data['pressure'] == '买盘偏强'
    assert data['spread'] == 1.0
    # 没有 book_payload 的旧后端 → 明确报错（不假装成功 ✓）
    plain = json.loads(tools.call('desk_market', {
        'action': 'depth', 'symbol': 'DCE.a2701'}, FakeDesk()))
    assert plain['ok'] is False


def test_scan_finds_matches_and_needs_threshold():
    desk = FakeDesk()
    data = json.loads(tools.call('desk_scan', {
        'symbols': ['DCE.a2701'], 'key': 'pta_ma', 'op': 'gt',
        'value': 0}, desk))
    assert data['ok'] is True
    assert data['scanned'] == 1
    assert data['matched'] == 1
    assert data['matches'][0]['symbol'] == 'DCE.a2701'
    bad = json.loads(tools.call('desk_scan', {
        'symbols': ['DCE.a2701'], 'key': 'pta_ma', 'op': 'gt'}, desk))
    assert bad['ok'] is False and 'value' in bad['error']


def test_scan_cross_up_uses_prev_and_last():
    assert tools._scan_match([{'last': 10.0, 'prev': 5.0}], 'cross_up', 8) is True
    assert tools._scan_match([{'last': 6.0, 'prev': 9.0}], 'cross_up', 8) is False
    assert tools._scan_match([{'last': 6.0, 'prev': 9.0}], 'cross_down', 8) is True


def test_strategy_data_reports_missing_backtest():
    data = json.loads(tools.call('desk_strategy_data', {}, FakeDesk()))
    assert data['ok'] is False
    assert 'desk_backtest_run' in data['error']


def test_strategy_data_summary_trades_signals():
    import types

    class Lab:
        file = '/tmp/demo_strategy.py'
        mode = 'backtest'

        def __init__(self):
            self._instances = [object()]

        def _extract(self, _strategy):
            return {
                'name': 'demo',
                'metrics': {'profit': 1234.0, 'drawdown': -56.0,
                            'winrate': 0.5, 'trades': 2},
                'equity': [[1, 100.0], [2, 130.0]],
                'pnl': [],
                'contracts': [{
                    'symbol': 'SHFE.ag2612', 'contract': 'SHFE.ag2612_60',
                    'bars': [1, 2, 3], 'trade_count': 2,
                    'trades': [{'time': 1, 'side': '多', 'pnl': 10.0},
                               {'time': 2, 'side': '空', 'pnl': -4.0}],
                    'signals': [{'time': 1, 'text': 'B'}],
                }],
            }

    desk = FakeDesk()
    desk._strategy_labs = {'lab1': Lab()}
    summary = json.loads(tools.call('desk_strategy_data', {}, desk))
    assert summary['ok'] is True
    assert summary['metrics']['profit'] == 1234.0
    assert summary['contracts'][0]['trade_count'] == 2
    trades = json.loads(tools.call('desk_strategy_data',
                                   {'action': 'trades'}, desk))
    assert trades['count'] == 2 and trades['trades'][-1]['pnl'] == -4.0
    signals = json.loads(tools.call('desk_strategy_data',
                                    {'action': 'signals'}, desk))
    assert signals['count'] == 1
    equity = json.loads(tools.call('desk_strategy_data',
                                   {'action': 'equity'}, desk))
    assert equity['points'] == 2
    bad = json.loads(tools.call('desk_strategy_data',
                                {'action': 'nope'}, desk))
    assert bad['ok'] is False


def test_market_analysis_one_call_returns_everything():
    """`analysis`：一次取数给全套（比连调 3 次 / sequence 都省）✓"""
    desk = FakeDesk()
    calls = []
    real = desk._indicator_payload_for

    def spy(symbol, items, frame=None, **kwargs):
        calls.append(symbol)
        return real(symbol, items, frame=frame, **kwargs)
    desk._indicator_payload_for = spy
    data = json.loads(tools.call('desk_market', {
        'action': 'analysis', 'symbol': 'DCE.a2701', 'limit': 30}, desk))
    assert data['ok'] is True, data
    assert set(('levels', 'stats', 'patterns', 'text')) <= set(data)
    # 单边行情可能没有前高前低 → 只要求结构字段齐全 ✓
    assert set(('support', 'resistance', 'fib', 'volume_profile',
                'pivot_highs', 'pivot_lows')) <= set(data['levels'])
    assert 'rsi14' in data['stats'] and 'trend' in data['stats']
    assert isinstance(data['patterns'], list)
    assert 'DCE.a2701' in data['text']
    # 指标只在图上有时才算：一次就够（不重复取数 ✓）
    assert len(calls) <= 1
    # 回执要够紧凑（长对话不炸上下文 ✓）
    assert len(json.dumps(data, ensure_ascii=False)) < 8000

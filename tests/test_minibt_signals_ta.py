"""信号（signals）+ 技术分析模板（v1.3.7-73，P0/P1）。

用户 2026-11-08 的设计：

* 指标 / 策略声明 `signals = {'rsi': Threshold(0, 1)}`；
* 两种常态信号：`Threshold`（原 Osc，与数值比较）/ `Compare`（原 Trend，与前值比较）；
* 1 多 / 0 中立 / -1 空；技术分析插件按「震荡 / 趋势 / 其他」三类展示；
* 可保存为模板（`ta_template`），也可用函数 / 方法名做自定义信号。
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from minibt import signals as S
from minibt.desk import ta, tools, user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        str(tmp_path / 'prefs.json'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    user_prefs.set_setting('ta_template', [])
    yield


def _frame(rows: int = 200, rising: bool = True):
    close = np.linspace(100, 130, rows) if rising else np.linspace(130, 100, rows)
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=rows, freq='min'),
        'open': close, 'high': close + 1, 'low': close - 1,
        'close': close, 'volume': np.full(rows, 10.0),
    })


# ------------------------------------------------------------ 信号类
def test_threshold_and_compare():
    assert S.Threshold(0, 1).evaluate([5]) == 1
    assert S.Threshold(0, 1).evaluate([0]) == 0
    assert S.Threshold(0, 1).evaluate([-5]) == -1
    # 方向反过来（上方看空 ✓）
    assert S.Threshold(0, -1).evaluate([5]) == -1
    # 与前值比较（-2 = 前一根）
    assert S.Compare(-2, 1).evaluate([1, 2]) == 1
    assert S.Compare(-2, 1).evaluate([2, 2]) == 0
    assert S.Compare(-2, -1).evaluate([1, 2]) == -1
    # 历史不足（Compare(-4) 只有 2 根）→ 中立
    assert S.Compare(-4, 1).evaluate([1, 2]) == 0
    # 旧名别名 ✓
    assert S.Osc is S.Threshold and S.Trend is S.Compare


def test_compare_rejects_future_offset():
    with pytest.raises(ValueError):
        S.Compare(0, 1)


def test_nan_and_custom_signal():
    assert S.Threshold(0, 1).evaluate([float('nan')]) == 0
    assert S.evaluate_values(S.Custom(lambda values: 1 if values[-1] > 0 else -1),
                             [-3]) == -1
    assert S.evaluate_values(S.Custom(lambda values: 'oops'), [1]) == 0


def test_spec_roundtrip():
    spec = S.Threshold(50, -1, label='50 上方看空').to_spec()
    assert spec['kind'] == 'threshold' and spec['level'] == 50
    back = S.signal_from_spec(spec)
    assert back.evaluate([60]) == -1
    compare = S.Compare(-3, 1).to_spec()
    assert compare['offset'] == -3
    assert S.signal_from_spec(compare).evaluate([1, 2, 3]) == 1


def test_summarize_counts_and_score():
    out = S.summarize([
        {'name': 'a', 'signal': 1}, {'name': 'b', 'signal': -1},
        {'name': 'c', 'signal': 0},
    ])
    assert out['counts'] == {'buy': 1, 'neutral': 1, 'sell': 1}
    assert abs(out['score']) < 0.01
    assert S.summarize([{'signal': 1}])['label'] == 'BUY'


# ------------------------------------------------------------ 指标装饰器
def test_tobtind_signals_attach_and_evaluate():
    from minibt.indicators.base import tobtind
    from minibt.indicators.core import KLine

    @tobtind(lines=['rsi'], myself=True, lib=None,
             signals={'rsi': S.Threshold(0, 1)})
    def fake_rsi(source, **kwargs):
        return source.close * 0 + 5

    @tobtind(lines=['sma'], myself=True, lib=None,
             signals={'sma': S.Compare(-2, 1)})
    def fake_sma(source, **kwargs):
        return source.close.rolling(3).mean()

    kline = KLine(_frame(40), duration_seconds=60, data_length=None)
    first = fake_rsi(kline)
    assert first.signal_of('rsi') == 1          # 5 > 0 → 多 ✓
    assert first.signal_map() == {'rsi': 1}
    assert fake_sma(kline).signal_of('sma') == 1   # 递增 → 多 ✓
    # 装饰器参数可被目录反射 ✓
    assert fake_rsi._decorator_args['signals']


# ------------------------------------------------------------ 目录 / 模板
def test_catalog_has_signal_and_options():
    from minibt.desk import indicator_catalog as catalog
    items = catalog.catalog()
    with_signal = [item for item in items if item.get('has_signal')]
    assert with_signal, '内置信号表没有生效'
    assert any(item['key'] == 'pta_rsi' for item in with_signal)
    spec = next(item['signal_spec'] for item in with_signal
                if item['key'] == 'pta_rsi')
    assert spec['rsi']['kind'] == 'threshold'
    data = ta.options()
    assert data['count'] >= 1
    assert data['groups'][0]['key'] == 'oscillator'
    # 全部指标（含没声明信号的）→ 给「建议信号」✓
    everything = ta.options(only_signal=False)
    assert everything['count'] > data['count']


def test_template_save_and_reset():
    rows = [{'key': 'pta_rsi', 'group': 'oscillator',
             'signal': {'kind': 'threshold', 'level': 60, 'direction': 1}}]
    saved = ta.save_template(rows)
    assert saved['count'] == 1
    assert ta.template()[0]['key'] == 'pta_rsi'
    assert user_prefs.settings().get('ta_template')[0]['signal']['level'] == 60
    ta.reset_template()
    assert ta.template() == []


def test_snapshot_default_and_custom():
    # 默认（模板空）→ pylightcharts 内置（RSI / MA 全家）✓
    default = ta.snapshot(_frame())
    assert default['template'] == 'default'
    assert [group['key'] for group in default['groups']] == [
        'oscillator', 'trend', 'other']
    assert default['groups'][0]['rows']
    # 自定义模板 → 只有选中的指标 ✓
    custom = ta.snapshot(_frame(), rows=[
        {'key': 'pta_rsi', 'group': 'oscillator',
         'signal': {'kind': 'threshold', 'level': 70, 'direction': 1}},
        {'key': 'pta_sma', 'group': 'trend',
         'signal': {'kind': 'compare', 'offset': -2, 'direction': 1}},
    ])
    assert custom['template'] == 'custom'
    rows = {row['key']: row for group in custom['groups']
            for row in group['rows']}
    assert rows['pta_rsi']['signal'] == 1        # 上涨末端 RSI > 70 ✓
    assert rows['pta_sma']['signal'] == 1        # 均线上行 ✓
    assert custom['counts']['buy'] == 2


# ------------------------------------------------------------ 工具 / 后端
def test_desk_ta_tool_actions():
    class Desk:
        def _ta_frame(self, symbol):
            return _frame()
    desk = Desk()
    options = json.loads(tools.call('desk_ta', {'action': 'options'}, desk))
    assert options['ok'] is True and options['count'] >= 1
    saved = json.loads(tools.call('desk_ta', {
        'action': 'set',
        'rows': [{'key': 'pta_rsi', 'group': 'oscillator',
                  'signal': {'kind': 'threshold', 'level': 70,
                             'direction': 1}}]}, desk))
    assert saved['count'] == 1
    snap = json.loads(tools.call('desk_ta', {
        'action': 'snapshot', 'symbol': 'SHFE.ag2612'}, desk))
    assert snap['ok'] is True
    assert snap['template'] == 'custom'
    assert snap['groups'][0]['rows'][0]['signal'] == 1
    reset = json.loads(tools.call('desk_ta', {'action': 'reset'}, desk))
    assert reset['reset'] is True


def test_app_registers_ta_commands():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    for name in ('ta_options', 'ta_snapshot', 'ta_template'):
        assert f"'{name}': self._on_{name}" in app
    # 标的页技术分析走自定义模板（没有模板 = 内置默认 ✓）
    block = app.split('def _symbol_widgets(', 1)[1].split(
        '    def _strategy_frame(', 1)[0]
    assert 'ta.snapshot(frame)' in block


# ------------------------------------------------------------ 前端
def test_frontend_ta_groups_and_dialog():
    panel = (JSLIB / '..' / 'panels' / 'technical.ts').read_text(
        encoding='utf-8')
    assert 'groups?: TaGroup[];' in panel
    assert '震荡指标' in panel or 'group.label' in panel
    page = (JSLIB / 'symbol-info.ts').read_text(encoding='utf-8')
    for token in ('_openTaDialog', 'ta_snapshot', 'ta_template',
                  '保存为模板', '恢复默认'):
        assert token in page, token
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ta_snapshot':" in app


# ------------------------------------------------------------ v1.3.7-74（P2）
def test_named_templates_crud():
    from minibt.desk import ta
    ta.save_named('趋势跟踪', [
        {'key': 'pta_sma', 'group': 'trend',
         'signal': {'kind': 'compare', 'offset': -2, 'direction': 1}}])
    ta.save_named('短线', [
        {'key': 'pta_rsi', 'group': 'oscillator',
         'signal': {'kind': 'threshold', 'level': 70, 'direction': 1}}])
    assert sorted(ta.templates()) == ['短线', '趋势跟踪']
    assert ta.active_name() == '短线'
    ta.activate('趋势跟踪')
    assert [row['key'] for row in ta.template()] == ['pta_sma']
    ta.activate('短线')
    assert [row['key'] for row in ta.template()] == ['pta_rsi']
    ta.delete_named('短线')
    assert sorted(ta.templates()) == ['趋势跟踪']
    # 恢复默认 = 不激活（命名模板保留 ✓）
    ta.reset_template()
    assert ta.active_name() == '' and ta.template() == []
    assert sorted(ta.templates()) == ['趋势跟踪']


def test_ta_tool_named_templates():
    class Desk:
        def _ta_frame(self, symbol):
            return _frame()
    desk = Desk()
    saved = json.loads(tools.call('desk_ta', {
        'action': 'save', 'name': '日内',
        'rows': [{'key': 'pta_rsi', 'group': 'oscillator',
                  'signal': {'kind': 'threshold', 'level': 70,
                             'direction': 1}}]}, desk))
    assert saved['name'] == '日内'
    listed = json.loads(tools.call('desk_ta', {'action': 'templates'}, desk))
    assert '日内' in listed['templates']
    used = json.loads(tools.call('desk_ta', {'action': 'use',
                                             'name': '日内'}, desk))
    assert used['name'] == '日内'
    snap = json.loads(tools.call('desk_ta', {'action': 'snapshot'}, desk))
    assert snap['template'] == 'custom'
    deleted = json.loads(tools.call('desk_ta', {'action': 'delete',
                                                'name': '日内'}, desk))
    assert '日内' not in deleted['templates']


def test_signal_alert_creates_and_fires():
    """指标信号预警：kind=signal + key + op → 命中就触发 ✓"""
    from minibt.desk.app import Desk
    desk = Desk(offline=True)
    desk._booted = True
    desk.sent = []
    desk.sender = desk.sent.append
    desk._ta_frame = lambda symbol: _frame()
    desk._alert_last_price = lambda symbol, alert: 129.5
    tools.call('desk_add_alert', {'kind': 'signal', 'symbol': 'SHFE.ag2612',
                                  'key': 'pta_rsi', 'op': 'buy'}, desk)
    assert desk.alerts[-1]['kind'] == 'signal'
    assert desk.alerts[-1]['key'] == 'pta_rsi'
    desk.check_alerts()
    assert desk.alerts[-1]['fired'] is True
    assert any('alert_fired' in str(item) for item in desk.sent)
    # 没有 key 的信号预警 → 明确报错（不静默）
    bad = json.loads(tools.call('desk_add_alert', {
        'kind': 'signal', 'symbol': 'SHFE.ag2612'}, desk))
    assert bad['ok'] is False and 'key' in bad['error']


def test_frontend_signal_badge_and_alert_kind():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (JSLIB / name).read_text(encoding='utf-8')
        assert 'setTaSignal(' in page, name
        assert 'desk-ta-badge' in page or 'taBadge' in page, name
        assert 'requestTaSignal()' in page, name
    app = (JSLIB / 'app.ts').read_text(encoding='utf-8')
    assert "case 'ta_signals':" in app
    dialog = (JSLIB / '..' / 'panels' / 'alert-dialog.ts').read_text(
        encoding='utf-8')
    assert '指标信号' in dialog
    assert "kind: this.kind" in dialog
    page = (JSLIB / 'symbol-info.ts').read_text(encoding='utf-8')
    assert "'ta_template', {" in page or "onCommand('ta_template'" in page

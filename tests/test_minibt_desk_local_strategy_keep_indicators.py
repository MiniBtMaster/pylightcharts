"""本地图表：先加指标、再加策略 → 指标不能丢（2026-11-02 用户实测）

现象：本地图表先「加到图表」几个指标（例如 MA / MACD），再「加到图表」一个策略，
之前加的指标**消失了**。

根因：策略里写了 `self.get_kline(LocalDatas.xxx)` 时，desk 会**自动布局**并把
合约装进各格 —— 走的是 `_on_local_load()`，而这个函数按「加载数据 = 只要 K 线」
的规则把该格指标清空了（`_local_set_items(name, cell, [], page)`）✗
用户手点「加载数据」清空是对的，但**自动布局**不该清，而且格子挪位置时
指标也要跟着搬。
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from minibt.desk import personal as pi

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def make_desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    monkeypatch.setattr(pi, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(pi, 'CONFIG_FILE', str(tmp_path / 'personal.json'))

    def factory():
        desk = appmod.Desk(offline=True)
        desk.sent = []
        desk.sender = desk.sent.append
        desk._booted = True
        desk._strategy_sync = True
        desk.log_to_stdout = False
        desk.log_to_ui = False
        desk._active_local_page = 'local:1'
        return desk
    return factory


def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def _last_items(desk, cell=0):
    payloads = [p for p in _patches(desk)
                if p.get('type') == 'local_indicator' and p.get('cell') == cell]
    return [item.get('key') for item in (payloads[-1].get('items') or [])] \
        if payloads else []


# --------------------------------------------------- `_on_local_load` 的两种语义
def test_local_load_clears_indicators_by_default(make_desk):
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    desk._on_local_add_indicator({'symbol': 'test', 'key': 'MA',
                                  'cell': 0, 'page': 'local:1'})
    assert desk._local_items('test', 0, 'local:1')
    # 用户手点「加载数据」→ 仍然只加载 K 线（指标清空 ✓）
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    assert desk._local_items('test', 0, 'local:1') == []


def test_local_load_can_keep_indicators(make_desk):
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    desk._on_local_add_indicator({'symbol': 'test', 'key': 'MA',
                                  'cell': 0, 'page': 'local:1'})
    # 自动布局走这条路 → 指标要留着 ✓
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1',
                         'keep_indicators': True})
    assert [item['key'] for item in desk._local_items('test', 0, 'local:1')] \
        == ['MA']


# --------------------------------------------- 自动布局：保留 + 跟着格子搬
def test_auto_layout_keeps_indicators_on_same_cell(make_desk):
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1',
                          'cells': ['pp2609_60', 'l2609_60']})
    desk._on_local_load({'name': 'pp2609_60', 'cell': 0, 'page': 'local:1'})
    desk._on_local_add_indicator({'symbol': 'pp2609_60', 'key': 'MA',
                                  'cell': 0, 'page': 'local:1'})
    desk._auto_layout_local(['pp2609_60', 'l2609_60'], current='pp2609_60')
    desk.flush_outbox()
    assert [item['key'] for item in
            desk._local_items('pp2609_60', 0, 'local:1')] == ['MA']
    keys = _last_items(desk, 0)
    assert any(key.startswith('MA') for key in keys), keys


def test_auto_layout_moves_indicators_with_the_cell(make_desk):
    """CSV 被挪到别的格子（1 格 → 2 格）时，指标跟着搬 ✓"""
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1', 'cells': ['l2609_60']})
    desk._on_local_load({'name': 'l2609_60', 'cell': 0, 'page': 'local:1'})
    desk._on_local_add_indicator({'symbol': 'l2609_60', 'key': 'MA',
                                  'cell': 0, 'page': 'local:1'})
    # 策略要 pp + l → l 从格 1 挪到格 2（index 1）
    desk._auto_layout_local(['pp2609_60', 'l2609_60'], current='l2609_60')
    desk.flush_outbox()
    assert desk._local_items('l2609_60', 0, 'local:1') == []      # 老格清掉
    assert [item['key'] for item in
            desk._local_items('l2609_60', 1, 'local:1')] == ['MA']  # 搬过去 ✓


# ------------------------------------------------------------- 端到端（真跑）
_STRATEGY = '''
from minibt import Strategy, LocalDatas


class st_two(Strategy):
    params = dict(length=20)

    def __init__(self):
        self.data = self.get_kline(LocalDatas.pp2609_60)
        self.data2 = self.get_kline(LocalDatas.l2609_60)
        self.ma = self.data.close.sma(self.params.length)

    def next(self):
        pass
'''


def test_adding_strategy_keeps_previous_indicators(make_desk, tmp_path):
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1',
                          'cells': ['pp2609_60', 'l2609_60']})
    desk._on_local_load({'name': 'pp2609_60', 'cell': 0, 'page': 'local:1'})
    assert desk._on_local_add_indicator(
        {'symbol': 'pp2609_60', 'key': 'MA', 'cell': 0,
         'page': 'local:1'}) is True

    folder = tmp_path / 'personal' / 'strategies'
    folder.mkdir(parents=True)
    path = folder / 'st_two.py'
    path.write_text(_STRATEGY, encoding='utf-8')
    desk._on_editor_add_indicator({'path': str(path), 'local': True,
                                  'symbol': 'pp2609_60', 'cell': 0,
                                  'page': 'local:1'})
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if desk._local_strategies.get('local:1'):
            break
        time.sleep(0.1)
    time.sleep(0.5)
    desk.flush_outbox()
    assert desk._local_strategies.get('local:1'), '策略没加载上'

    keys = _last_items(desk, 0)
    assert any(key.startswith('editor:') for key in keys), keys   # 策略线
    assert any(key.startswith('MA') for key in keys), keys        # 指标还在 ✓


# --------------------------------------------------------------- 源码护栏
def test_on_local_load_has_keep_indicators_switch():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('    def _on_local_load(self, payload)', 1)[1]
    block = block.split('    def _on_local_add_indicator(', 1)[0]
    assert "keep_indicators" in block
    assert "if not bool((payload or {}).get('keep_indicators')):" in block
    layout = app.split('    def _auto_layout_local(', 1)[1]
    layout = layout.split('    def _resolve_realtime_contract(', 1)[0]
    assert layout.count("'keep_indicators': True") >= 2      # 两条自动布局路径 ✓


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

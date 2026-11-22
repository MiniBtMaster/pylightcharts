"""布局 / 策略加载：合约清单没下完时**不要误杀**（v1.3.9-10）。

用户实测（已登录天勤）：

1. 应用**左右布局** → 「布局中的合约无法加载：已跳过 DCE.l2701、DCE.pp2701
   —— 天勤合约列表里没有这个合约」；
2. 把 `test_8.py` **加到图表** → 第一次「天勤合约清单尚未加载，请稍后重试」，
   点第二次才好。

真因：校验用的是 `api._data['symbols']`（**懒加载**：用户只浏览过 CFFEX 时
里面只有 CFFEX 的 28 行），DCE 一条都没有 → 被判成"合约不存在" ✗。
现在：**清单为空 → 放行 + 后台重取**；只有清单非空且确实没有才提示。
"""
from __future__ import annotations

import time
import types

import pytest

from minibt.desk.app import Desk


class _Feed:
    """假行情源：本地清单可控"""

    def __init__(self, symbols):
        self._symbols = dict(symbols or {})
        self._symbol_lists = {}
        self.api = types.SimpleNamespace(_data={'symbols': dict(self._symbols)})
        self.reset_calls = []

    def available(self):
        return True

    def contracts_local(self, ins_class='FUT', exchange=''):
        rows = [key for key in self._symbols
                if str(key).upper().startswith(f'{exchange.upper()}.')]
        return rows

    def name_of(self, symbol):
        return '' if symbol not in self._symbols else 'x'

    def reset_symbols(self, ins_class, exchange, force=False):
        self.reset_calls.append((ins_class, exchange, force))
        self._symbol_lists[('FUT', exchange)] = object()


def _desk(feed):
    desk = Desk.__new__(Desk)
    desk.futures = feed
    desk.tabs = {}
    desk._last_rows = {}
    desk.logs = []
    desk.push_log = lambda text, level='info': desk.logs.append((level, text))
    desk.pump = lambda *a, **k: None
    desk._refresh_futures_contracts = lambda f, ex, wait=3.0: set(
        f.contracts_local('FUT', ex))
    desk._queue_contract_refresh = lambda ex, wait=0.0: (
        desk.logs.append(('info', f'{ex}: queued')),
        feed.reset_symbols('FUT', ex, force=True))
    return desk


# ---------------------------------------------------------- 布局（问题 1）
def test_layout_does_not_block_when_exchange_list_is_empty():
    """只加载过 CFFEX 时，DCE 的合约**不该**被判定为不存在 ✓"""
    feed = _Feed({'CFFEX.IF2612': {'price_tick': 0.2}})
    desk = _desk(feed)
    bad = desk._ensure_realtime_contracts(['DCE.l2701', 'DCE.pp2701'])
    assert bad == [], bad
    # 并且排了后台重取（下一拍就有清单）
    assert ('info', 'DCE: queued') in desk.logs


def test_layout_still_blocks_when_list_known_and_missing():
    """清单**非空**但确实没有 → 仍然提示（防订阅不存在的合约把泵搞坏 ✓）"""
    feed = _Feed({'DCE.l2701': {'price_tick': 1},
                  'DCE.pp2701': {'price_tick': 1}})
    desk = _desk(feed)
    bad = desk._ensure_realtime_contracts(['DCE.zz9999'])
    assert [item['symbol'] for item in bad] == ['DCE.zz9999']
    assert '没有这个合约' in bad[0]['reason']


# ---------------------------------------------------------- 策略（问题 2）
def test_strategy_validation_passes_when_list_empty():
    """「策略合约无法加载：清单尚未加载」不再中止（第一次加载就成功 ✓）"""
    feed = _Feed({'CFFEX.IF2612': {'price_tick': 0.2}})
    desk = _desk(feed)
    bad = desk._validate_realtime_contracts(['DCE.l2701', 'DCE.pp2701'])
    assert bad == [], bad


def test_strategy_validation_blocks_unknown_when_list_known():
    feed = _Feed({'DCE.l2701': {'price_tick': 1}})
    desk = _desk(feed)
    bad = desk._validate_realtime_contracts(['DCE.zz9999'])
    assert [item['symbol'] for item in bad] == ['DCE.zz9999']


# ------------------------------------------------- 多布局：策略线不重复
def test_cell0_strategy_group_is_by_own_symbol():
    """格 0 只画**自己合约**那组策略线（配对策略的另一组属于格 1）✓"""
    desk = Desk.__new__(Desk)
    desk.tabs = {}
    info = {
        'strategy': {'name': 'KalmanFilterStrategy', 'path': 'x.py'},
        'strategy_contracts': ['DCE.l2701', 'DCE.pp2701'],
        'strategy_groups': {
            'DCE.l2701': [{'key': 'a', 'label': 'zscores'}],
            'DCE.pp2701': [{'key': 'b', 'label': 'state_mean'}],
        },
        'strategy_items': [{'key': 'b'}],        # 最大的那组 = pp（另一格的）
        'layout': {'cells': [{'symbol': 'DCE.l2701', 'indicators': []},
                             {'symbol': 'DCE.pp2701', 'indicators': []}]},
        'cycle': 60,
        'indicators': [],
    }
    desk.tabs['DCE.l2701'] = info
    group, name, contracts = desk._cell_strategy_group(info, 0, 'DCE.l2701')
    assert [item['label'] for item in group] == ['zscores']
    assert name == 'KalmanFilterStrategy'
    assert contracts == ['DCE.l2701', 'DCE.pp2701']
    # 格 1 拿到的是自己那组
    group1, _n, _c = desk._cell_strategy_group(info, 1, 'DCE.pp2701')
    assert [item['label'] for item in group1] == ['state_mean']

def test_cell0_items_follow_own_contract_not_largest_group():
    """`indicator_payload` 里格 0 的策略线 = 自己合约那组（不再重复）✓"""
    desk = Desk.__new__(Desk)
    info = {
        'strategy': {'name': 'KalmanFilterStrategy', 'path': 'x.py'},
        'strategy_contracts': ['DCE.l2701', 'DCE.pp2701'],
        'strategy_groups': {
            'DCE.l2701': [{'label': 'zscores(l)'}],
            'DCE.pp2701': [{'label': 'zscores(pp)'}, {'label': 'extra'}],
        },
        'strategy_items': [{'label': 'zscores(pp)'}, {'label': 'extra'}],
        'layout': {'cells': [{'symbol': 'DCE.l2701'},
                             {'symbol': 'DCE.pp2701'}]},
    }
    assert [item['label'] for item in
            desk._cell0_strategy_items(info, 'DCE.l2701')] == ['zscores(l)']

    # 单图（没有 layout）→ 保持原行为（用 strategy_items）✓
    single = dict(info)
    single.pop('layout')
    assert desk._cell0_strategy_items(single, 'DCE.pp2701') == info[
        'strategy_items']

    # 多布局但格 0 的合约不属于这套策略 → 不画策略线 ✓
    other = dict(info)
    other['layout'] = {'cells': [{'symbol': 'SHFE.au2612'},
                                 {'symbol': 'DCE.pp2701'}]}
    assert desk._cell0_strategy_items(other, 'SHFE.au2612') == []


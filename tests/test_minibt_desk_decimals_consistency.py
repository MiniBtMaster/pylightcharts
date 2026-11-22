"""小数位（`decimals_of`）链路：**账户面板和报价页必须一致**（v1.3.9-8）。

用户读 `minibt/desk/accounts.py` 时发现：

```python
getter = getattr(self.desk, 'decimals_of', None)
if callable(getter):
    try:
        return int(getter(symbol))
    except Exception:      # ← 全吞了
        pass
return 2                   # ← 期货常常不是 2 位
```

实际场景里有两类 BUG：

1. **持仓 / 委托 / 成交表的小数位和报价页对不上**：Desk 的 `decimals_of()`
   以前只认**报价行**（`_last_rows`，= 自选 / 图表订阅过的合约）。
   实盘持仓里的合约大多**没订阅** → 拿不到 `price_tick` → 一律 2 位 →
   `ag2612` 显示 `13974.00`，而报价页是 `13974`（整数价合约）。
   更糟的是实盘 `_fill_decimals_step()` 会**直接清空补数队列**（怕
   `get_quote` 阻塞），所以永远补不上 ✗。
2. **封装的健壮性**：`int('x')` / `int(None)` 抛错后被 `except Exception: pass`
   静默吞掉 → 悄悄变 2 位，没有任何日志；而且 `default` 没法透传（写死 2）。

修法：
* `Desk.local_price_tick()`：报价行 → **tqsdk 本地合约字典**
  （`api._data['symbols'] / ['quotes']`，`query_symbol_info` 自带
  `price_tick`）—— 零请求、零阻塞，实盘也能拿到正确 tick；
* `AccountView.decimals_of(symbol, default=2)`：`default` 透传、结果必须
  在 0~8 之间、真出错时**每个合约只记一次**运行日志；
* `Trading._decimals()` 同一套口径。
"""
from __future__ import annotations

import types

import pytest

from minibt.desk import accounts
from minibt.desk.app import Desk


# ---------------------------------------------------------------- 工具
class _DeskStub:
    """只实现 decimals_of 相关方法的假 desk"""

    def __init__(self, tick=1.0, *, real=False):
        self._last_rows = {}
        self._real_account = real
        self._decimals_queue = []
        self._decimals_cache = {}
        self.logs = []
        if tick is not None:
            self._last_rows['SHFE.ag2612'] = {'price_tick': tick}
        # tqsdk 本地合约字典（不联网那份）
        self.futures = types.SimpleNamespace(api=types.SimpleNamespace(_data={
            'symbols': {
                'SHFE.ag2612': {'price_tick': 1.0},
                'DCE.rb2610': {'price_tick': 1.0},
                'CZCE.MA609': {'price_tick': 1.0},
                'SHFE.au2612': {'price_tick': 0.02},
            },
        }))

    def push_log(self, text, level='info'):
        self.logs.append((level, text))

    # 直接借用真实的实现，避免"测试里复制一份逻辑"↔"生产代码漂移" ✗
    local_price_tick = Desk.local_price_tick
    decimals_of = Desk.decimals_of


class _View(accounts.AccountView):
    """不跑 `__init__`（它要一个完整 Desk），只测 decimals_of ✓"""

    def __init__(self, desk):                                # noqa: D401
        self.desk = desk


# ---------------------------------------------------------------- 场景 1
def test_accounts_decimals_follow_quote_rows():
    """报价行里有 tick → 小数位和报价页一致（整数价 = 0 位）✓"""
    view = _View(_DeskStub(tick=1.0))
    assert view.decimals_of('SHFE.ag2612') == 0
    # 裸代码（天勤持仓只给 `ag2612`）也要能对上同一条报价行
    assert view.decimals_of('ag2612') == 0


def test_accounts_decimals_use_local_symbol_dict_when_not_quoted():
    """★ 核心 BUG：合约**不在报价行**（实盘持仓常见）也要拿到正确小数位

    以前这里会退回 2 位 → 持仓表 `13974.00`、报价页 `13974`，两边对不上 ✗。
    现在读 tqsdk 本地合约字典（零请求）→ 0 位 ✓
    """
    desk = _DeskStub(tick=None)               # 报价行里什么都没有
    view = _View(desk)
    assert view.decimals_of('SHFE.ag2612') == 0     # price_tick 1.0
    assert view.decimals_of('DCE.rb2610') == 0
    assert view.decimals_of('CZCE.MA609') == 0
    assert view.decimals_of('SHFE.au2612') == 2     # 0.02 → 2 位


def test_real_account_also_gets_correct_decimals():
    """实盘：`_fill_decimals_step` 会清空补数队列，所以必须靠本地字典命中 ✓"""
    desk = _DeskStub(tick=None, real=True)
    view = _View(desk)
    assert view.decimals_of('SHFE.ag2612') == 0
    assert desk._decimals_queue == [], '实盘不该排队等 get_quote（会阻塞）'


def test_unknown_symbol_falls_back_to_default():
    """完全未知的合约 → 队列（小批补）+ 默认 2 位 ✓"""
    desk = _DeskStub(tick=None)
    view = _View(desk)
    assert view.decimals_of('SHFE.zz9999') == 2
    assert 'SHFE.zz9999' in desk._decimals_queue


def test_default_argument_is_passed_through():
    """`default` 要能透传（以前写死 2，调用方没法要 0 位）✓"""
    class _NoDecimals:
        logs = []

        def push_log(self, *a, **k):
            pass

    view = _View(_NoDecimals())
    assert view.decimals_of('SHFE.zz9999') == 2
    assert view.decimals_of('SHFE.zz9999', 0) == 0
    assert view.decimals_of('SHFE.zz9999', default=1) == 1


# ---------------------------------------------------------------- 场景 2
def test_dirty_values_are_rejected():
    """Desk 返回 `None` / 超范围 → 退回 default（以前 int(None) 抛错被吞→2）"""
    class _Dirty:
        logs = []

        def __init__(self, value):
            self.value = value

        def decimals_of(self, symbol, default=2):
            return self.value

        def push_log(self, *a, **k):
            pass

    for value in (None, 'x', -1, 99, 3.7):
        view = _View(_Dirty(value))
        got = view.decimals_of('X', 0)
        assert got == 0 or (value == 3.7 and got == 3), (value, got)


def test_exception_is_logged_once_per_symbol():
    """真异常 → 用 default，并且**同一个合约只记一次**日志（别刷屏）✓"""
    class _Boom:
        def __init__(self):
            self.logs = []

        def decimals_of(self, symbol, default=2):
            raise RuntimeError('boom')

        def push_log(self, text, level='info'):
            self.logs.append((level, text))

    desk = _Boom()
    view = _View(desk)
    assert view.decimals_of('SHFE.ag2612') == 2
    assert view.decimals_of('SHFE.ag2612') == 2
    warnings = [row for row in desk.logs if row[0] == 'warning']
    assert len(warnings) == 1, desk.logs
    assert '小数位取不到' in warnings[0][1]


# ---------------------------------------------------------------- 场景 3
def test_position_table_uses_symbol_decimals():
    """落到真实表格：持仓价 13974 不该出现 `.00` 尾巴 ✓"""
    desk = _DeskStub(tick=None)

    class _PosRow(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as error:
                raise AttributeError(name) from error

    class _Api:
        def get_position_list(self):
            return [_PosRow(instrument_id='ag2612', exchange_id='SHFE',
                            pos_long=2, open_price_long=13974.0,
                            position_price_long=13974.0,
                            float_profit_long=0.0,
                            volume_long=2)]

        def get_position(self, *a, **k):
            return None

        def get_order(self, *a, **k):
            return None

        def get_trade(self, *a, **k):
            return None

    view = accounts.AccountView.__new__(accounts.AccountView)
    view.desk = desk
    view.index = 0
    view.api = lambda symbol='': _Api()
    payload = view.tables(10, '')
    row = payload['positions']['rows'][0]
    assert row[0] == 'SHFE.ag2612'
    # 第 5/6 列分别是开仓价 / 持仓均价
    assert row[4] == '13,974', row
    assert row[5] == '13,974', row

"""图表策略**交易**与两个开关（用户 2026-11-22 报"策略不交易"）

根因：`strategy_run_next` / `strategy_next_on_new_bar` 这两个 desk 设置被旧版本
误写成 **False**（抄了 minibt 回测默认值），图表策略的 `advance()` 里
`if cfg.get('run_next') is False: return True` → `next()` 一次都不跑。

修复：

1. `runtime_config()` 对这两个键**只认 desk 设置 / 单策略 override**，没设置 → True；
2. `user_prefs` 一次性迁移：两个都关着（旧 bug 典型状态）→ 打开一次；
3. 加到图表时如果 `run_next` 仍是 False → **明确提醒**（不再是静默不交易）；
4. 账户：`StrategyRunner(account_provider=…)` 每拍重新解析**当前切换的账户**；
5. 换周期守卫：图表有策略 → 拒绝并提醒先删策略。
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from minibt.desk import strategy_runner as runner_module  # noqa: E402


def _frame(rows: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    return pd.DataFrame({
        'datetime': pd.date_range('2024-01-01', periods=rows, freq='5min'),
        'open': close, 'high': close + 1, 'low': close - 1,
        'close': close, 'volume': 1000.0,
        'symbol': 'DCE.v2601', 'duration': 300,
        'price_tick': 1.0, 'volume_multiple': 5.0,
    })


def _strategy_cls():
    """每根 K 线反手（pos 0/1 交替）——用来判定 next 有没有真跑 ✓"""
    from minibt import Strategy

    class Flip(Strategy):
        params = dict(fast=3, slow=5, size=1)

        def __init__(self):
            close = self.kline.close
            self.fast = close.rolling(3).mean(lines=['sma_fast'])
            self.slow = close.rolling(5).mean(lines=['sma_slow'])
            self.fast.overlap = self.slow.overlap = True

        def next(self):
            if not self.kline.position.pos:
                self.kline.buy()
            else:
                self.kline.sell()

    return Flip


# --------------------------------------------------------------- 开关
def test_runtime_config_defaults_to_running(tmp_path, monkeypatch):
    """没设置过 → 两个开关都 True（加到图表就交易 ✓）"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    runner = runner_module.StrategyRunner(_strategy_cls(), symbol='DCE.v2601',
                                          cycle=300)
    runner.prepare([_frame()], seed_kline=True)
    cfg = runner.runtime_config()
    assert cfg['run_next'] is True
    assert cfg['next_on_new_bar'] is True


def test_runtime_config_honors_explicit_off(tmp_path, monkeypatch):
    """用户显式关掉 → 尊重（但只在设置/override 里关才算 ✓）"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.set_setting('strategy_run_next', False)
    runner = runner_module.StrategyRunner(_strategy_cls(), symbol='DCE.v2601',
                                          cycle=300)
    runner.prepare([_frame()], seed_kline=True)
    assert runner.runtime_config()['run_next'] is False
    runner.override = {'run_next': True}          # 单策略覆盖优先 ✓
    assert runner.runtime_config()['run_next'] is True


def test_strategy_switches_migration(tmp_path, monkeypatch):
    """两个都关着（旧 bug）→ 迁移打开一次，且只迁一次 ✓"""
    from minibt.desk import user_prefs

    prefs = tmp_path / 'p.json'
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(prefs))
    prefs.write_text(json.dumps({'settings': {
        'strategy_next_on_new_bar': False, 'strategy_run_next': False}}),
        encoding='utf-8')
    values = user_prefs.settings()
    assert values['strategy_run_next'] is True
    assert values['strategy_next_on_new_bar'] is True
    assert values['strategy_switches_migrated'] is True
    # 用户之后手动关回来 → 不再被迁移覆盖 ✓
    user_prefs.set_setting('strategy_run_next', False)
    assert user_prefs.settings()['strategy_run_next'] is False


# --------------------------------------------------------------- 交易
def test_chart_advance_actually_trades(tmp_path, monkeypatch):
    """`advance()` 必须真的跑 `next` → 持仓在 0/1 之间交替、有委托 ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    frame = _frame()
    runner = runner_module.StrategyRunner(_strategy_cls(),
                                          symbol='DCE.v2601', cycle=300)
    runner.prepare([frame], seed_kline=True)
    positions = []
    for index in range(4):
        runner.advance([frame.iloc[:200 + index * 10]])
        positions.append(runner.strategy.kline.position.pos)
    assert runner.error == ''
    assert set(positions) == {0, 1}, positions      # 反手 ✓
    assert len(runner.orders) >= 3


def test_run_next_off_means_no_trades(tmp_path, monkeypatch):
    """`run_next=False`（只算指标）→ 不交易、但指标照样有 ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.set_setting('strategy_run_next', False)
    frame = _frame()
    runner = runner_module.StrategyRunner(_strategy_cls(),
                                          symbol='DCE.v2601', cycle=300)
    runner.prepare([frame], seed_kline=True)
    for index in range(3):
        runner.advance([frame.iloc[:200 + index * 10]])
    assert runner.strategy.kline.position.pos == 0
    assert not runner.orders
    assert len(runner.strategy.fast) == 220          # 指标照算（最后一帧 220 根）✓


def test_next_on_new_bar_gates_per_bar(tmp_path, monkeypatch):
    """`next_on_new_bar=True`：同一根 K 线重复推进只跑一次 ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    frame = _frame()
    runner = runner_module.StrategyRunner(_strategy_cls(),
                                          symbol='DCE.v2601', cycle=300)
    runner.prepare([frame], seed_kline=True)
    calls = {'n': 0}
    original = runner.strategy.step

    def counted():
        calls['n'] += 1
        return original()

    runner.strategy.step = counted
    same = frame.iloc[:250]
    runner.advance([same])          # 新 K 线 → 跑一次
    first = calls['n']
    runner.advance([same])          # 同一根 → 不跑
    runner.advance([same])
    assert first >= 1
    assert calls['n'] == first, calls           # 没有重复运行 ✓
    runner.advance([frame.iloc[:260]])          # 又来新 K 线 → 继续跑 ✓
    assert calls['n'] > first


# --------------------------------------------------------------- 账户
def test_account_provider_follows_current_account(tmp_path, monkeypatch):
    """切账户后 `advance()` 要把策略账户换成**当前**那个 ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    frame = _frame()
    accounts = [object(), object()]
    state = {'index': 0}

    def provider():
        return accounts[state['index']]

    runner = runner_module.StrategyRunner(_strategy_cls(),
                                          symbol='DCE.v2601', cycle=300,
                                          account_provider=provider)
    runner.prepare([frame], seed_kline=True)
    runner.live = True                       # 模拟实时图表
    runner._klines[0]._tqobjs = {}           # 没有天勤对象 → 不碰网络 ✓
    runner.advance([frame.iloc[:200]])
    assert runner.account is accounts[0]
    state['index'] = 1                       # 用户切到另一个账户 ✓
    runner.advance([frame.iloc[:210]])
    assert runner.account is accounts[1]
    assert runner.strategy._live_account is accounts[1]


# --------------------------------------------------------------- 换周期
def test_cycle_switch_blocked_when_strategy_attached(tmp_path, monkeypatch):
    """图表有策略 → 换周期被拒绝并提醒；删掉策略后恢复 ✓"""
    from minibt.desk import user_prefs
    from minibt.desk.app import Desk

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = Desk(offline=True)
    pushed: list = []
    desk.push = lambda patch: pushed.append(patch)
    symbol = 'DCE.v2601'
    desk.tabs[symbol] = {'cycle': 300, 'strategy': {'name': 'Flip'}}
    result = desk.set_cycle(symbol, 60)
    assert result['ok'] is False
    assert '先删除策略' in str(result['error'])
    kinds = {item.get('type') for item in pushed if isinstance(item, dict)}
    assert 'toast' in kinds

    desk.tabs[symbol].pop('strategy')       # 删掉策略 → 可以换 ✓
    ok = desk.set_cycle(symbol, 60)
    assert ok['ok'] is True and ok['cycle'] == 60

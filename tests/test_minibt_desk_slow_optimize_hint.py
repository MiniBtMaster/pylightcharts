"""策略参数优化跑太久 → 提醒改用「信号参数优化」（2026-11-02 用户要求）

* `tutorials/basic/optstrategy.py`（策略参数优化）每个 trial 都要**逐根重跑策略**，
  几十组参数就是几分钟；
* `tutorials/basic/signal_optimize.py`（信号参数优化）只算信号，快一两个数量级。

所以：**策略**参数优化超过 1 分钟还没结束 → 冒一条**警告**（运行日志 + toast），
提示改用信号参数优化；提醒走旁路 `threading.Timer`，**不会打断 / 拖慢**当前优化，
并且只提醒一次。**信号参数优化**（`_run_indicator`）不提醒 ✓。
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Desk:
    def __init__(self):
        self.patches = []

    def push(self, patch):
        self.patches.append(patch)


def _lab(**kwargs):
    from minibt.desk.strategy_lab import StrategyLab

    desk = _Desk()
    lab = StrategyLab(desk, 'slow')
    lab.mode = 'optimize'
    for key, value in kwargs.items():
        setattr(lab, key, value)
    return lab, desk


def _hints(desk):
    return [item for item in desk.patches
            if item.get('type') == 'toast'
            and '参数优化' in str(item.get('text') or '')]


def _logs(desk):
    return [item for item in desk.patches
            if item.get('type') == 'strategy_log'
            and '信号参数优化' in str(item.get('line') or '')]


# ------------------------------------------------------------ 常量 / 阈值
def test_default_threshold_is_one_minute():
    from minibt.desk.strategy_lab import SLOW_OPTIMIZE_HINT_SECONDS

    assert SLOW_OPTIMIZE_HINT_SECONDS == 60.0


def test_threshold_can_be_overridden_by_env(monkeypatch):
    lab, _ = _lab()
    monkeypatch.delenv('MINIBT_DESK_SLOW_OPT_HINT', raising=False)
    assert lab._slow_hint_seconds() == 60.0
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.2')
    assert lab._slow_hint_seconds() == pytest.approx(0.2)
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', 'x')
    assert lab._slow_hint_seconds() == 60.0
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0')
    assert lab._slow_hint_seconds() == 0.0


# ------------------------------------------------------- 到点提醒（不打断）
def test_hint_fires_when_still_running(monkeypatch):
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.15')
    lab, desk = _lab()
    lab.status = 'running'
    lab._start_slow_hint()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not _hints(desk):
        time.sleep(0.02)
    lab._cancel_slow_hint()
    hints = _hints(desk)
    assert hints, desk.patches
    assert hints[0]['level'] == 'warning'
    assert '信号参数优化' in str(hints[0].get('detail') or '')
    # 运行日志里也有一条完整说明 ✓
    assert _logs(desk)
    # 优化状态没被改（提醒只是旁观 ✓）
    assert lab.status == 'running' and lab._stop is False


def test_hint_only_once(monkeypatch):
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.1')
    lab, desk = _lab()
    lab.status = 'running'
    lab._start_slow_hint()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not _hints(desk):
        time.sleep(0.02)
    lab._slow_hint_fire()                    # 再手动触发一次也不重复 ✓
    lab._slow_hint_fire()
    lab._cancel_slow_hint()
    assert len(_hints(desk)) == 1


def test_hint_skipped_when_finished_or_cancelled(monkeypatch):
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.1')
    # 已经跑完
    lab, desk = _lab(status='ready')
    lab._slow_hint_fire()
    assert not _hints(desk) and not _logs(desk)
    # 被取消
    lab2, desk2 = _lab(status='running')
    lab2._stop = True
    lab2._slow_hint_fire()
    assert not _hints(desk2)
    # 不是优化模式（回测）
    lab3, desk3 = _lab(status='running')
    lab3.mode = 'backtest'
    lab3._slow_hint_fire()
    assert not _hints(desk3)


def test_timer_is_cancelled_when_optimize_finishes(monkeypatch):
    """跑得快 → 定时器被撤掉，不会在跑完之后冒提醒 ✓"""
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.4')
    lab, desk = _lab()

    class Strategy:
        op_config = {'target': 'sharpe', 'weights': 1.0,
                     'params': {'length': [5, 10]}, 'opconfig': {'n_trials': 1}}

    class Bt:
        strategies = [Strategy]

        def optstrategy(self, target, weights, **kwargs):
            pass

        def run(self, **kwargs):
            pass

    lab.status = 'running'
    lab._run_with_cancel(Bt())               # 立刻结束
    assert lab._slow_hint is None            # finally 里撤掉了 ✓
    # 就算再多等一会儿也不该冒提醒
    time.sleep(0.6)
    assert not _hints(desk)


def test_slow_strategy_optimize_emits_hint(monkeypatch):
    """策略优化真的跑超时 → 提醒（真跑一遍 `_run_with_cancel`）✓"""
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.15')
    lab, desk = _lab()

    class Strategy:
        op_config = {'target': 'sharpe', 'weights': 1.0,
                     'params': {'length': [5, 10]}, 'opconfig': {'n_trials': 1}}

    class Bt:
        strategies = [Strategy]

        def optstrategy(self, target, weights, **kwargs):
            pass

        def run(self, **kwargs):
            time.sleep(0.5)                  # 假装逐根重跑策略很慢

    lab.status = 'running'
    lab._run_with_cancel(Bt())
    assert _hints(desk), '策略优化超时却没有提醒'
    assert lab.status == 'running'            # 优化本身没被打断 ✓


# ------------------------------------------------ 信号参数优化：**不**提醒
def test_no_hint_when_strategy_has_no_op_config(monkeypatch):
    """没有 `op_config` → 回退成普通回测 → **不**该提醒「改用信号参数优化」✓"""
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.1')
    lab, desk = _lab()

    class Strategy:
        op_config = None

    class Bt:
        strategies = [Strategy]

        def run(self, **kwargs):
            time.sleep(0.35)

    lab.status = 'running'
    lab._run_with_cancel(Bt())
    assert not _hints(desk), [item for item in desk.patches
                              if item.get('type') == 'toast']


def test_indicator_path_never_starts_the_timer():
    lab, _ = _lab()
    source = (ROOT / 'minibt' / 'desk' / 'strategy_lab.py').read_text(
        encoding='utf-8')
    indicator = source.split('    def _run_indicator(self) -> bool:', 1)[1]
    indicator = indicator.split('    def _indicator_opt_rows(', 1)[0]
    assert '_start_slow_hint' not in indicator     # 指标 / 信号路径不提醒 ✓
    assert lab.mode == 'optimize'


def test_indicator_optimize_does_not_emit_hint(monkeypatch, tmp_path):
    """真的跑一次信号参数优化（短网格）→ 不该有「改用信号参数优化」提醒 ✓"""
    monkeypatch.setenv('MINIBT_DESK_SLOW_OPT_HINT', '0.05')
    from minibt.desk.strategy_lab import StrategyLab

    folder = tmp_path / 'sig'
    folder.mkdir()
    (folder / 'sig.py').write_text('\n'.join([
        'from minibt import BtIndicator',
        '',
        '',
        'class TinyMA(BtIndicator):',
        "    lines = ['ma', 'long_signal', 'short_signal']",
        '    params = dict(length1=5, length2=10)',
        '',
        '    def next(self):',
        '        ma1 = self.close.sma(self.params.length1)',
        '        ma2 = self.close.sma(self.params.length2)',
        '        return ma1, ma1.cross_up(ma2), ma1.cross_down(ma2)',
        '',
    ]), encoding='utf-8')

    desk = _Desk()
    lab = StrategyLab(desk, 'sig')
    lab.file = str(folder / 'sig.py')
    lab.mode = 'optimize'
    lab.targets = ['sharpe']
    lab.weights = [1.0]
    lab.opt_options = {'method': 'grid', 'n_jobs': 1, 'n_trials': 0,
                       'sampler': '', 'pruner': ''}
    lab.param_space = {'length1': [5, 9, 4]}
    assert lab._run_indicator() is True
    time.sleep(0.2)
    assert not _hints(desk), [item for item in desk.patches
                              if item.get('type') == 'toast']


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

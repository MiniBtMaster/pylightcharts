"""优化目标从 3 个扩到 **9 个**（2026-11-02 用户要求 ✓）

* 后端 `research.normalize_metrics()` 的软上限 3 → `MAX_OPT_TARGETS = 9`；
* `StrategyLab.start()` 收 9 个目标 / 权重，`_push_state()` 原样下发；
* 策略路径（`bt.optstrategy`）与指标路径（`OptimizeConfig`）都要能吃 9 个目标
  （`weights` 元组长度必须跟着走 ✓）。
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_max_opt_targets_is_nine():
    from minibt.desk.research import MAX_OPT_TARGETS

    assert MAX_OPT_TARGETS == 9


def test_normalize_metrics_keeps_up_to_nine():
    from minibt.desk.research import TARGET_METRICS, normalize_metrics

    names = ['sharpe', 'sortino', 'calmar', 'omega', 'cagr', 'win_rate',
             'volatility', 'profit', 'result']
    out = normalize_metrics(names)
    assert out == names                       # 9 个全保留、顺序不变 ✓
    # 超过 9 个 → 截断到 9（不报错）
    more = names + ['profit_ratio', 'max_drawdown']
    assert len(normalize_metrics(more)) == 9
    # 非法 / 重复 / 空 → 照旧
    assert normalize_metrics(['nope', 'sharpe', 'sharpe']) == ['sharpe']
    assert normalize_metrics([]) == ['profit_ratio']
    assert set(normalize_metrics(names)) <= set(TARGET_METRICS)


class _Desk:
    def __init__(self):
        self.patches = []

    def push(self, patch):
        self.patches.append(patch)


def _nine():
    return ['sharpe', 'sortino', 'calmar', 'omega', 'cagr', 'win_rate',
            'volatility', 'profit', 'result']


def test_push_state_carries_nine_targets_and_weights():
    from minibt.desk.strategy_lab import StrategyLab

    desk = _Desk()
    lab = StrategyLab(desk, 'nine')
    lab.mode = 'optimize'
    lab.targets = _nine()
    lab.weights = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0, 1.0]
    lab._push_state()
    patch = desk.patches[-1]
    assert patch['targets'] == _nine()
    assert len(patch['weights']) == 9
    assert patch['weights'][6] == -1.0        # 波动率 = 最小化 ✓
    assert len(patch['target_options']) == 73


def test_strategy_path_forwards_nine_targets():
    """策略路径：`bt.optstrategy(target, weights, …)` 收到 9 个 ✓"""
    captured = {}

    class Strategy:
        op_config = {'target': 'profit_ratio', 'weights': 1.0,
                     'params': {'length': [5, 10]}, 'opconfig': {'n_trials': 1}}

    class Bt:
        strategies = [Strategy]

        def optstrategy(self, target, weights, **kwargs):
            captured['target'] = target
            captured['weights'] = weights

        def run(self, **kwargs):
            pass

    from minibt.desk.strategy_lab import StrategyLab

    lab = StrategyLab(_Desk(), 'nine-strategy')
    lab.mode = 'optimize'
    lab.targets = _nine()
    lab.weights = [1.0] * 9
    lab._run_optimize(Bt())
    assert captured['target'] == _nine()
    assert isinstance(captured['weights'], tuple)
    assert len(captured['weights']) == 9


def test_indicator_config_accepts_nine_targets():
    from minibt import BtIndicator
    from minibt.desk.strategy_lab import StrategyLab

    class _Ind(BtIndicator):
        params = dict(length1=10)

    lab = StrategyLab(_Desk(), 'nine-indicator')
    lab.mode = 'optimize'
    lab.targets = _nine()
    lab.weights = [1.0] * 9
    config = lab._indicator_config(_Ind)
    assert list(config.target) == _nine()
    assert len(config.weights) == 9
    assert config.params == {'length1': (5, 15, 2)}


def test_frontend_renders_nine_target_slots():
    page = (ROOT / 'jslib' / 'src' / 'desk' / 'strategy-lab-page.ts').read_text(
        encoding='utf-8')
    assert 'const OPT_TARGET_SLOTS = 9;' in page
    assert 'data-opt-target="${index}"' in page
    assert '最多 ${OPT_TARGET_SLOTS} 个' in page
    # 重新优化时收集 9 个（不是写死 3 个 ✓）
    restart = page.split('private _restartOptimize(): void {', 1)[1]
    restart = restart.split('private _renderOptimization', 1)[0]
    assert 'OPT_TARGET_SLOTS' in restart and 'slice(0, OPT_TARGET_SLOTS)' in restart


def test_frontend_pareto_axes_support_one_to_three():
    page = (ROOT / 'jslib' / 'src' / 'desk' / 'strategy-lab-page.ts').read_text(
        encoding='utf-8')
    assert 'const PARETO_AXES = 3;' in page
    assert 'data-pareto-axis="0"' in page or 'data-pareto-axis' in page
    assert 'data-pareto-apply' in page
    # 1 个目标 → 权益横轴；2 个 → 二维；3 个 → 三维 ✓
    assert "_equityKey(" in page
    assert "from './chart3d'" in page
    assert '_pareto3DHtml(' in page and 'data-opt-3d' in page
    css = (ROOT / 'jslib' / 'src' / 'desk' / 'desk.css').read_text(
        encoding='utf-8')
    for selector in ('.desk-opt-axisbar', '.desk-opt-3d', '.desk-opt-3d-tip'):
        assert selector in css, selector


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

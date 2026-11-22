"""指标信号参数优化：目标指标不能再恒为 0（2026-10-31 用户实测 ✓）

现象：`tutorials/basic/signal_optimize.py` 参数优化，目标选 `profit` / `result`
后，优化表里 **`values_0` 全是 0**（换成几个目标都一样），`win_rate` 却正常：

    Trial 0 finished with values: [0.0, 0.46774193548387094] ...

根因：`minibt/indicators/core.py` 的 `_calc_qs_metrics()` 只算了 **9 个**指标
（sharpe / sortino / max_drawdown / calmar / win_rate / profit_factor / cagr /
value_at_risk / risk_return_ratio），而 `_objective` 用 `ret.get(t, 0.)` 取目标
→ `profit` / `result` / 其它 60 多个 `OPTTargetType` 全落成 **0.0** ✗。

修法：
* `_calc_qs_metrics()` 补 `result`（最终权益）/ `profit`（盈亏金额）/
  `profit_rate`（盈亏率），与 `minibt.strategy.stats.Stats` 同一套口径；
* 新增 `_target_metric()`：其余目标现场调 `quantstats.stats.<name>(returns)` 补算，
  拿不到标量（如 `monthly_returns` 这类表）→ 0.0 且**提示一次**；
* grid / optuna 两条路径都改走它；
* desk 侧 `_normalize_opt_rows()` 顺手补一列**目标名**（`profit` / `win_rate`），
  并把 `±inf`（失败 trial）转成 `None`（`-Infinity` 不是合法 JSON ✗）。
"""
from __future__ import annotations

import importlib.util
import pathlib

import numpy as np
import pandas as pd
import pytest

from minibt.desk.strategy_lab import (_json_value, _normalize_opt_rows,
                                      StrategyLab)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / 'tutorials' / 'basic' / 'signal_optimize.py'


def _tutorial_module():
    spec = importlib.util.spec_from_file_location('sig_opt_targets', TUTORIAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _indicator():
    from minibt import LocalDatas

    module = _tutorial_module()
    return module.MyMA(LocalDatas.test.kline)


class _Desk:
    def __init__(self):
        self.patches = []

    def push(self, patch):
        self.patches.append(patch)


# ---------------------------------------------------- 引擎：目标不再恒为 0
def test_grid_targets_profit_and_win_rate_are_not_zero():
    from minibt import OptimizeConfig

    ind = _indicator()
    config = OptimizeConfig(
        params={'length1': (5, 15, 5), 'length2': (10, 20, 10)},
        target=['profit', 'win_rate'], weights=(1.0, 1.0),
        method='grid', n_jobs=1)
    result = ind.signal_backtest(size=1, isplot=False, isreport=False,
                                 optimize=config)
    frame = result.to_dataframe()
    assert 'profit' in frame.columns
    profits = [float(value) for value in frame['profit']]
    assert any(abs(value) > 1e-9 for value in profits), profits
    assert len(set(round(value, 6) for value in profits)) > 1, profits
    # `result`（最终权益）也要有值，且与 profit 口径一致（相差初始本金）
    assert all(abs(value) > 1.0 for value in profits)


def test_grid_target_result_is_final_equity():
    from minibt import OptimizeConfig

    ind = _indicator()
    config = OptimizeConfig(
        params={'length1': (5, 10, 5)}, target=['result'],
        method='grid', n_jobs=1)
    result = ind.signal_backtest(size=1, isplot=False, isreport=False,
                                 optimize=config)
    frame = result.to_dataframe()
    values = [float(value) for value in frame['result']]
    assert values and all(value > 1000 for value in values), values
    assert len(set(round(value, 6) for value in values)) > 1, values
    # 与 best_metrics 的 `profit` 自洽：result - profit = 初始本金（1e6）
    best = result.best_metrics
    assert abs((best['result'] - best['profit']) - 1_000_000.) < 1.0


def test_uncomputable_target_degrades_to_zero_with_notice(capsys):
    """`monthly_returns` 这类表格型指标 → 0.0，并且**提示一次** ✓"""
    from minibt import OptimizeConfig

    ind = _indicator()
    config = OptimizeConfig(
        params={'length1': (5, 10, 5)}, target=['monthly_returns'],
        method='grid', n_jobs=1)
    result = ind.signal_backtest(size=1, isplot=False, isreport=False,
                                 optimize=config)
    frame = result.to_dataframe()
    assert list(frame['monthly_returns']) == [0.0] * len(frame)
    out = capsys.readouterr().out
    assert 'monthly_returns' in out and '警告' in out, out


def test_pair_engine_rows_are_extracted():
    """配对引擎（`pair_backtest`）结果放在 `study={'results': [...]}` → 也要出表 ✓"""
    class _Result:
        target = ['profit', 'win_rate']
        best_params = {'window': 30}
        study = {'results': [{
            'params': {'window': 30, 'open_h': 1.5},
            'profit': 1874.0, 'win_rate': 0.28,
            'equity': np.arange(10.0),            # 大数组：必须被丢掉 ✓
            'returns': pd.Series([0.0, 0.1]),
        }]}

    lab = StrategyLab(_Desk(), 'pair-rows')
    rows = lab._indicator_opt_rows(_Result())
    assert rows, '配对优化一行都没取到'
    row = rows[0]
    assert row['values_0'] == 1874.0 and row['values_1'] == 0.28
    assert row['params_window'] == 30 and row['params_open_h'] == 1.5
    assert 'equity' not in row and 'returns' not in row


# ------------------------------------------------------ desk：行 / JSON 安全
def test_json_value_is_json_strict():
    assert _json_value(np.float64('-inf')) is None
    assert _json_value(float('nan')) is None
    assert _json_value(np.float64(1.5)) == 1.5
    assert _json_value(np.int64(3)) == 3
    assert _json_value(True) is True


def test_normalize_rows_adds_target_columns_and_clears_inf():
    rows = [{'number': 0, 'values_0': 1840.0, 'values_1': 0.35,
             'params_length1': 5},
            {'number': 1, 'values_0': '-inf', 'values_1': np.float64('-inf'),
             'params_length1': 10}]
    out = _normalize_opt_rows(rows, ['profit', 'win_rate'], None)
    assert out[0]['profit'] == 1840.0        # 多一列「目标名」，表头好认 ✓
    assert out[0]['win_rate'] == 0.35
    assert out[1]['profit'] is None          # 失败 trial：-inf → 空
    assert out[1]['win_rate'] is None
    assert out[1]['params_length1'] == 10


def test_normalize_rows_drops_heavy_columns():
    rows = [{'profit': 1.0, 'equity': np.arange(100.0),
             'returns': pd.Series([0.0, 0.1]),
             'params': {'a': 1}}]
    out = _normalize_opt_rows(rows, ['profit'], None)
    assert 'equity' not in out[0] and 'returns' not in out[0]
    assert out[0]['params_a'] == 1          # 嵌套 params 已摊平 ✓


def test_desk_indicator_optimize_values_not_all_zero():
    """端到端复现用户那条命令：目标 = profit + win_rate ✓"""
    desk = _Desk()
    lab = StrategyLab(desk, 'opt-target-nonzero')
    lab.file = str(TUTORIAL)
    lab.mode = 'optimize'
    lab.targets = ['profit', 'win_rate']
    lab.weights = [1.0, 1.0]
    lab.opt_options = {'method': 'optuna', 'n_jobs': 1, 'n_trials': 6,
                       'sampler': '', 'pruner': ''}
    lab.param_space = {'length1': [5, 20, 5], 'length2': [10, 30, 10]}
    assert lab._run_indicator() is True
    rows = lab.optimization_rows
    assert rows, '一条 trial 都没有'
    first = [row.get('values_0') for row in rows if row.get('values_0') is not None]
    assert first, 'values_0 全是空/0'
    assert any(abs(float(value)) > 1e-9 for value in first), first
    assert len({round(float(value), 6) for value in first}) > 1, first
    # 目标名那一列也在（前端表格 / 图表更好读 ✓）
    assert 'profit' in rows[0] and 'win_rate' in rows[0]
    # 补丁里不能出现 -Infinity（不是合法 JSON ✗）
    import json
    for patch in desk.patches:
        if patch.get('type') == 'strategy_opt':
            text = json.dumps(patch, ensure_ascii=False, allow_nan=False)
            assert '-Infinity' not in text and 'NaN' not in text


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

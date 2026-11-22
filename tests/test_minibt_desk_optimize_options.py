"""参数优化页的「优化设置」：方法 / 并行 / 试验次数 / 采样器 / 剪枝器 / 权重 / 参数网格

用户需求（2026-10-30）：

1. `tutorials/basic/signal_optimize.py` 参数优化**有结果**，但「优化图表」里的
   帕累托前沿 / 参数排名 / 参数重要性**三张图全空**；
2. 选了三个优化目标，点「按当前目标重新优化」→ 输出还是 `目标=['sharpe']`；
3. 除目标外还要能设置 `OptimizeConfig` 的 method / n_jobs / n_trials / sampler，
   目标权重（weights）与参数（params）也要能改，且都是下拉/可编辑选项。

根因（都已修）：

* 指标信号路径的 `_indicator_config()` **写死** `target='sharpe'`、`method='grid'`、
  `n_jobs=2`，用户选的目标 / 权重根本没传下去；
* grid 引擎的 `OptimizationResult.to_dataframe()` 列名是「目标名 + 裸参数名」
  （`sharpe` / `length1`），而前端图表固定读 `values_*` / `params_*`
  → 三张图都找不到数据。
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from minibt.desk.strategy_lab import (OPT_METHODS, OPT_PRUNERS, OPT_SAMPLERS,
                                      StrategyLab, _normalize_opt_rows,
                                      _sane_options, _sane_param_space)

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding='utf-8')


class _Desk:
    def __init__(self):
        self.patches = []

    def push(self, patch):
        self.patches.append(patch)


def _lab(**kwargs) -> tuple[StrategyLab, _Desk]:
    desk = _Desk()
    lab = StrategyLab(desk, 'opt-options')
    lab.mode = 'optimize'
    for key, value in kwargs.items():
        setattr(lab, key, value)
    return lab, desk


# --------------------------------------------------------------- 参数校验
def test_sane_options_filters_unknown_values():
    options = _sane_options({'method': 'GRID', 'n_jobs': 4, 'n_trials': 30,
                             'sampler': 'TPESampler', 'pruner': 'MedianPruner'})
    assert options['method'] == 'grid'          # 大小写归一
    assert options['n_jobs'] == 4
    assert options['n_trials'] == 30
    assert options['sampler'] == 'TPESampler'
    assert options['pruner'] == 'MedianPruner'
    # 非法值 → 回到「跟随默认」
    # 正整数（或 -1）合法；其它 → 0
    assert _sane_options({'n_jobs': 3})['n_jobs'] == 3
    bad = _sane_options({'method': 'magic', 'n_jobs': -5, 'n_trials': -5,
                         'sampler': 'NoSuchSampler', 'pruner': 'X'})
    assert bad['method'] == '' and bad['n_jobs'] == 0 and bad['n_trials'] == 0
    assert bad['sampler'] == '' and bad['pruner'] == ''
    # -1 = 全部核心（合法）
    assert _sane_options({'n_jobs': -1})['n_jobs'] == -1


def test_sane_param_space_normalises_ranges_and_options():
    space = _sane_param_space({
        'a': [5, 30], 'b': [5, 30, 2], 'c': ['x', 'y'], 'd': 7,
        'e': '  12  ', '': [1, 2], 'f': None, 'g': [],
    })
    assert space == {'a': [5, 30], 'b': [5, 30, 2], 'c': ['x', 'y'],
                     'd': 7, 'e': '12'}


# ------------------------------------------------- grid 引擎行 → 统一列名
def test_normalize_rows_for_grid_engine():
    rows = [{'sharpe': 0.26, 'max_drawdown': -0.12, 'length1': 5,
             'length2': 25, '_weighted_score': 0.14}]
    out = _normalize_opt_rows(rows, ['sharpe', 'max_drawdown'],
                              ['length1', 'length2'])
    assert out[0]['number'] == 1
    assert out[0]['values_0'] == 0.26
    assert out[0]['values_1'] == -0.12
    assert out[0]['params_length1'] == 5
    assert out[0]['params_length2'] == 25


def test_normalize_rows_for_optuna_single_target():
    rows = [{'number': 0, 'value': 0.75, 'params_window': 60}]
    out = _normalize_opt_rows(rows, ['sharpe'], None)
    assert out[0]['values_0'] == 0.75
    assert 'value' not in out[0]
    # ★ `number` 统一成 **1 基**（0 → 1）：图上的 Trial N 和表格一致 ✓
    assert out[0]['number'] == 1


# -------------------------------------- 指标信号：用户设置真的生效（问题 2/3）
class _StubIndicator:
    """只要能被 `_indicator_config` 读 `params` / `op_config` 就行 ✓"""

    params = {'length1': 10, 'length2': 20}


def test_indicator_config_uses_user_targets_and_options():
    lab, _desk = _lab(
        targets=['sharpe', 'max_drawdown', 'profit_ratio'],
        weights=[1.0, -1.0, 2.0],
        opt_options={'method': 'optuna', 'n_jobs': 4, 'n_trials': 50,
                     'sampler': 'TPESampler', 'pruner': 'MedianPruner'},
        param_space={'length1': [5, 30, 5], 'length2': [10, 60, 10]},
    )
    config = lab._indicator_config(_StubIndicator)
    # ★ 以前这里永远是 target='sharpe' / method='grid' / n_jobs=2 ✗
    assert config.target == ('sharpe', 'max_drawdown', 'profit_ratio')
    assert config.weights == (1.0, -1.0, 2.0)
    assert config.method == 'optuna'
    assert config.n_jobs == 4
    assert config.config['n_trials'] == 50
    assert config.config['sampler'] == 'TPESampler'
    assert config.config['pruner'] == 'MedianPruner'
    assert config.params == {'length1': [5, 30, 5], 'length2': [10, 60, 10]}
    # 回写状态：前端要显示真正跑的目标 / 权重
    assert lab.targets == ['sharpe', 'max_drawdown', 'profit_ratio']
    assert lab.weights == [1.0, -1.0, 2.0]


def test_indicator_config_defaults_follow_class_params():
    lab, _desk = _lab(targets=[], weights=[])
    config = lab._indicator_config(_StubIndicator)
    assert config.target == 'sharpe'            # 没有 op_config → 默认单目标
    assert config.method == 'grid'
    assert config.n_jobs == 2                   # 以前写死的默认并行数保留 ✓
    assert set(config.params) == {'length1', 'length2'}
    assert lab.targets == ['sharpe'] and lab.weights == [1.0]


def test_indicator_config_ga_falls_back_to_optuna():
    lab, _desk = _lab(opt_options={'method': 'ga'})
    config = lab._indicator_config(_StubIndicator)
    assert config.method == 'optuna'            # 指标只支持 grid / optuna


# ---------------------------------------- 策略路径：选项进 optstrategy 参数
def test_run_optimize_forwards_options_and_param_space():
    captured = {}

    class Strategy:
        op_config = {'target': 'profit_ratio', 'weights': 1.0,
                     'params': {'length': [5, 10]},
                     'opconfig': {'n_trials': 1},
                     'op_method': 'optuna'}

    class Bt:
        strategies = [Strategy]

        def optstrategy(self, target, weights, **kwargs):
            captured['target'] = target
            captured['weights'] = weights
            captured['kwargs'] = kwargs

        def run(self, **kwargs):
            captured['run'] = kwargs

    lab, _desk = _lab(
        targets=['sharpe', 'max_drawdown'], weights=[1.0, -1.0],
        opt_options={'method': 'optuna', 'n_jobs': 4, 'n_trials': 50,
                     'sampler': 'TPESampler', 'pruner': 'MedianPruner'},
        param_space={'length': [5, 20, 5]},
    )
    lab._run_optimize(Bt())
    kwargs = captured['kwargs']
    assert captured['target'] == ['sharpe', 'max_drawdown']
    assert captured['weights'] == (1.0, -1.0)
    assert kwargs['length'] == [5, 20, 5]        # 用户改过的参数网格 ✓
    assert kwargs['op_method'] == 'optuna'
    optimize_kwargs, study_kwargs = kwargs['opconfig']
    assert optimize_kwargs['n_trials'] == 50
    assert optimize_kwargs['n_jobs'] == 4
    assert study_kwargs['sampler'] == 'TPESampler'
    assert study_kwargs['pruner'] == 'MedianPruner'


def test_run_optimize_ga_keeps_dict_opconfig():
    captured = {}

    class Strategy:
        op_config = {'target': 'sharpe', 'weights': 1.0,
                     'params': {'length': [5, 10]}, 'opconfig': {}}

    class Bt:
        strategies = [Strategy]

        def optstrategy(self, target, weights, **kwargs):
            captured['kwargs'] = kwargs

        def run(self, **kwargs):
            pass

    lab, _desk = _lab(opt_options={'method': 'ga'})
    lab._run_optimize(Bt())
    assert captured['kwargs']['op_method'] == 'ga'
    assert isinstance(captured['kwargs']['opconfig'], dict)   # GA 不能吃元组 ✓


# ------------------------------------------------- 端到端：真的跑一次网格搜索
_TINY_INDICATOR = '''
from minibt import BtIndicator


class TinyMA(BtIndicator):
    lines = ['ma1', 'long_signal', 'short_signal']
    params = dict(length1=5, length2=10)

    def next(self):
        ma1 = self.close.sma(self.params.length1)
        ma2 = self.close.sma(self.params.length2)
        return ma1, ma1.cross_up(ma2), ma1.cross_down(ma2)
'''


def test_indicator_optimize_end_to_end_keeps_targets_and_normalises_rows():
    path = pathlib.Path(tempfile.gettempdir()) / 'minibt_tiny_ma_opt.py'
    path.write_text(_TINY_INDICATOR, encoding='utf-8')
    lab, desk = _lab(
        file=str(path),
        targets=['sharpe', 'profit_ratio'], weights=[1.0, -1.0],
        opt_options={'method': 'grid', 'n_jobs': 1, 'n_trials': 0,
                     'sampler': '', 'pruner': ''},
        param_space={'length1': [5, 9, 2]},       # 3 组，跑得快 ✓
    )
    assert lab._run_indicator() is True
    # ★ 目标不再是写死的 'sharpe'
    assert lab.targets == ['sharpe', 'profit_ratio']
    logs = [patch['line'] for patch in desk.patches
            if patch.get('type') == 'strategy_log']
    assert any('[优化] 目标=' in line and 'profit_ratio' in line
               for line in logs), logs
    rows = lab.optimization_rows
    assert rows, '网格搜索一条结果都没有'
    first = rows[0]
    # 前端图表的统一列名（以前只有 `sharpe` / `length1` → 三张图全空 ✗）
    assert 'values_0' in first and 'values_1' in first
    assert 'params_length1' in first
    assert isinstance(first['number'], int)
    # `strategy_opt` 补丁把行推给了前端 ✓
    assert any(patch.get('type') == 'strategy_opt' for patch in desk.patches)


# ------------------------------------------------------------- 前端接线
def test_frontend_has_weight_and_option_controls():
    page = _read(JSLIB / 'strategy-lab-page.ts')
    for marker in ('data-opt-weight', 'data-opt-opt', 'data-opt-param',
                   'data-opt-param-add', 'data-opt-param-del',
                   '_optOptionsPayload', '_optParamPayload',
                   '_paramRowsFromSpace', 'n_trials', 'sampler', 'pruner',
                   'weight_options', 'param_space', 'param_options',
                   'method_options'):
        assert marker in page, marker
    # 重跑时把权重 / 设置 / 参数网格一起发下去 ✓
    restart = page.split('private _restartOptimize(): void {', 1)[1]
    restart = restart.split('private _renderOptimization', 1)[0]
    for marker in ('metrics, weights', 'options,', 'param_space: paramSpace'):
        assert marker in restart, marker
    css = _read(JSLIB / 'desk.css')
    for selector in ('.desk-strategy-opt-settings', '.desk-opt-param-row',
                     '.desk-opt-param-del', '.desk-opt-dash'):
        assert selector in css, selector


def test_backend_state_exposes_option_lists():
    lab, desk = _lab(targets=['sharpe'])
    lab._push_state()
    patch = desk.patches[-1]
    assert patch['method_options'] == list(OPT_METHODS)
    assert patch['sampler_options'] == list(OPT_SAMPLERS)
    assert patch['pruner_options'] == list(OPT_PRUNERS)
    assert patch['n_jobs_options'] == [1, 2, 4, 8, -1]
    assert patch['weight_options'] == [1.0, 2.0, 0.5, -0.5, -1.0, -2.0]
    assert patch['options']['method'] == ''
    assert isinstance(patch['param_space'], dict)
    assert isinstance(patch['param_options'], list)


def test_effective_param_space_derives_from_class_params():
    lab, _desk = _lab()
    lab._opt_cls = _StubIndicator
    space = lab._effective_param_space()
    assert set(space) == {'length1', 'length2'}
    assert all(isinstance(value, list) and len(value) == 3
               for value in space.values())
    # 用户改过 → 用用户的
    lab.param_space = {'only': [1, 5, 1]}
    assert lab._effective_param_space() == {'only': [1, 5, 1]}


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

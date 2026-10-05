"""btplot 的「指标自带 step」路径：必须把指标登记到策略的 ``_btindicatordataset``。

历史 bug：``_BtplotStep`` 只在 ``next()`` 里调 ``ind.step()``，没有把指标作为**属性
赋值**，于是 ``Strategy.__setattr__`` 不登记 → 图表端拿不到任何指标 →
pylightcharts 模式下**指标与信号一片空白**（当时把 ``step`` 改名成 ``__step``、
让 btplot 走纯图表路径才会显示，但那样就丢了交易逻辑）。
"""
import numpy as np


def test_single_ema_cross_step_is_public():
    """`SingleEMACross` 的交易逻辑必须是**公开的** ``step``。

    写成 ``__step`` 会被名字 mangle 成 ``_SingleEMACross__step``，``btplot`` 的
    ``'step' in ind.__dict__`` 判定不到交易逻辑（回测/实时里 ``ind.step()`` 也调不到）。
    """
    from minibt import LocalDatas
    ind = LocalDatas.test.kline.tradingview.SingleEMACross()
    assert 'step' in ind.__dict__
    assert '_SingleEMACross__step' not in ind.__dict__
    assert callable(ind.step)


def test_make_step_strategy_registers_indicators_for_chart():
    """带 ``step`` 的指标也要出现在 ``_btindicatordataset`` 里（图表才画得出来）。"""
    from minibt import LocalDatas
    from minibt.utils import Config
    import minibt.btplot as btp

    k = LocalDatas.test.kline
    ind = k.tradingview.SingleEMACross()
    strat = btp._make_step_strategy(k, [ind], Config(theme='dark'),
                                    'SingleEMACross')
    strat._start_strategy_run()

    assert 'SingleEMACross' in strat._btindicatordataset, \
        list(strat._btindicatordataset.keys())
    frame = strat._btindicatordataset['SingleEMACross']
    cols = list(frame.pandas_object.columns)
    assert cols[:2] == ['ema_fast', 'ema_slow'], cols
    assert int(np.nansum(np.asarray(frame['long_signal'].values, dtype=float))) > 0
    assert int(np.nansum(np.asarray(frame['short_signal'].values, dtype=float))) > 0
    # 交易逻辑仍然在跑（有回测结果）
    assert strat._results, '带 step 的指标应当跑出回测结果'


def test_btplot_does_not_duplicate_indicator():
    """``_chain`` 去重：同一个指标不能被登记两次（否则图上画两遍）。"""
    from minibt import LocalDatas
    from minibt.utils import Config
    import minibt.btplot as btp

    k = LocalDatas.test.kline
    ind = k.tradingview.SingleEMACross()
    # btplot 内部会把 `indicator` 本身也放进 `indicators`，这里模拟那种输入
    strat = btp._make_step_strategy(k, [ind, ind], Config(theme='dark'), 'Dup')
    strat._start_strategy_run()
    names = list(strat._btindicatordataset.keys())
    assert len([n for n in names if n.startswith('SingleEMACross')]) == 1, names

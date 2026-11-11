"""`config.drawdown_plot`：回测结果页「回撤」副图的显示 / 隐藏（默认隐藏）✓

用户需求（2026-10-30）：

> 为 `minibt.Strategy.config` 添加一个 bool 参数，控制 pylightcharts 在 minibt
> 回测和 minibt desk 策略回测的**回测结果页**（K 线 / 权益 / 回撤 / 盈亏）里
> **回撤副图**的显示与隐藏；True 显示，False 隐藏（感觉这个可有可无），默认 False。

三条链路都要跟着走：

* `Bt().run(...)` 的 pylightcharts 回测窗口（`StrategyWindow._show_backtest`）；
* 回放窗口（`ReplayWindow` → `set_backtest(**data)`）；
* desk 策略回测（`minibt.desk.miniqt_backtest_chart.build_result_html`）。
"""
import pathlib

import numpy as np
import pandas as pd
import pytest

from pylightcharts import Window
from pylightcharts.abstract import AbstractChart

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def _chart():
    """一个能接受所有桥接调用的离屏图表（脚本只被记录，不执行）✓"""
    captured = []
    window = Window(script_func=captured.append)
    window.loaded = True
    chart = AbstractChart(window)
    chart.set(pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=10, freq='D'),
        'open': np.arange(10, dtype=float) + 100,
        'high': np.arange(10, dtype=float) + 101,
        'low': np.arange(10, dtype=float) + 99,
        'close': np.arange(10, dtype=float) + 100.5,
        'volume': np.arange(10, dtype=float),
    }))
    return chart


def _equity(n: int = 10) -> pd.DataFrame:
    return pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=n, freq='D'),
        'value': 1e6 * np.cumprod(1 + np.linspace(0.01, -0.02, n)),
    })


def _pnl(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        'time': pd.date_range('2024-01-02', periods=n, freq='D'),
        'value': [120.0, -80.0, 45.0],
    })


# ------------------------------------------------------------------ Config
def test_config_drawdown_plot_defaults_to_false():
    from minibt.utils import Config

    assert Config().drawdown_plot is False
    # 文档字符串里要能查到（`help(Strategy.config)` / `__doc__`）
    assert 'drawdown_plot' in (Config.__doc__ or '')


def test_resolve_drawdown_plot():
    from minibt.utils import Config, resolve_drawdown_plot

    class _Stub:
        def __init__(self, flag=None):
            self.config = Config()
            if flag is not None:
                self.config.drawdown_plot = flag

    assert resolve_drawdown_plot(None) is False
    assert resolve_drawdown_plot(_Stub()) is False          # 默认
    assert resolve_drawdown_plot(_Stub(True)) is True
    assert resolve_drawdown_plot(_Stub(False)) is False
    # 显式 default 只在策略没设过时生效
    assert resolve_drawdown_plot(None, default=True) is True
    # 没有 config 的对象也不能炸
    assert resolve_drawdown_plot(object()) is False


# ------------------------------------------------------- BacktestPage 本身
def test_backtest_page_hides_drawdown_pane():
    from minibt.strategy.pages import BacktestPage

    page = BacktestPage(_chart(), show_drawdown=False)
    page.update(_equity(), pnl=_pnl())
    assert page.panes.get('equity') is not None
    assert page.panes.get('pnl') is not None
    assert 'drawdown' not in page.panes          # ★ 不建回撤副图
    assert 'drawdown' not in page.series


def test_backtest_page_shows_drawdown_when_enabled():
    from minibt.strategy.pages import BacktestPage

    page = BacktestPage(_chart(), show_drawdown=True)
    page.update(_equity(), pnl=_pnl())
    assert 'drawdown' in page.panes
    assert 'drawdown' not in (page.panes['equity'], page.panes['pnl'])


def test_backtest_page_default_keeps_old_behaviour():
    """不传 show_drawdown 时（老调用）仍然画回撤 —— 避免影响既有用例 ✓"""
    from minibt.strategy.pages import BacktestPage

    page = BacktestPage(_chart())
    assert page.show_drawdown is True
    page.update(_equity())
    assert 'drawdown' in page.panes


def test_backtest_page_remove_clears_hidden_page():
    from minibt.strategy.pages import BacktestPage

    page = BacktestPage(_chart(), show_drawdown=False)
    page.update(_equity(), pnl=_pnl())
    page.remove()
    assert page.panes == {} and page.series == {}


# ------------------------------------------------------- 三条链路的接线
def test_strategy_window_accepts_and_uses_flag():
    source = _read('minibt/strategy/strategy_window.py')
    assert 'show_drawdown: Optional[bool] = None' in source
    assert "'show_drawdown': show_drawdown" in source
    assert 'show_drawdown=show_drawdown' in source
    # 多策略开关不同 → 重建（否则少一个 / 多一个副图）
    assert 'self.backtest.show_drawdown != show_drawdown' in source


def test_backtest_dict_carries_the_flag(monkeypatch):
    """`strategy_backtest_dict()` 把 ``config.drawdown_plot`` 算好放进字典 ✓

    minibt 回测窗口 / 回放窗口 / desk 策略回测都从这里取开关。
    """
    from minibt.strategy import realtime as rt
    from minibt.utils import Config

    class _Stub:
        profits = pd.Series(1e6 * (1 + 0.01 * i) for i in range(6))
        _results = [{'total_profit': list(profits), 'total_fee': 0.0}]

        def __init__(self, flag):
            self.config = Config()
            self.config.drawdown_plot = flag

    monkeypatch.setattr(rt.RealtimeChart, '_trades_from_log',
                        staticmethod(lambda *a, **k: ([], None)))
    monkeypatch.setattr(rt.RealtimeChart, '_extract_all_contract_trades',
                        staticmethod(lambda *a, **k: ([], None)))
    assert rt.strategy_backtest_dict(_Stub(True))['show_drawdown'] is True
    assert rt.strategy_backtest_dict(_Stub(False))['show_drawdown'] is False
    # 没有 profits 的桩对象：直接返回 {}（不炸，也不带这个键 ✓）
    assert rt.strategy_backtest_dict(object()) == {}
    source = _read('minibt/strategy/realtime.py')
    assert "'show_drawdown': resolve_drawdown_plot(strategy)" in source


def test_desk_result_html_passes_the_flag():
    source = _read('minibt/desk/miniqt_backtest_chart.py')
    assert "show_drawdown=bool(data.get('show_drawdown', True))" in source


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

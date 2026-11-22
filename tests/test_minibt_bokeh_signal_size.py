"""bokeh 回测：`SignalStyle` 没写 ``size``（默认 ``None``）时不能崩 ✓

用户 2026-11-2x 实测（``tutorials/plots/01_backtest_bokeh.py``）::

    Bt().run(gui=Gui.Bokeh)
    TypeError: float() argument must be a string or a real number, not 'NoneType'

根因：``SignalStyle.size`` 默认 ``None``（真正取值在 ``resolved_size()`` 里
按渲染引擎算：bokeh 12 / pylightcharts 8），但图表引擎直接
``list(style.values())`` 解包后 ``float(signalsize)`` ✗。而且
``PlotInfo.vars`` 会把 ``signalstyle`` 递归成**普通 dict**，一个
``hasattr(style, 'resolved_size')`` 的判空根本救不到。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'minibt' / 'data' / 'test' / 'test.csv'


def test_signal_style_values_resolve_none_size():
    from minibt.utils import (SignalStyle, resolve_signal_size,
                              signal_style_values)

    style = SignalStyle('low', 'red', 'triangle')
    assert style.size is None
    bokeh_values = signal_style_values(style, 'bokeh')
    assert bokeh_values[5] == 12.0          # key,color,marker,overlap,show,size…
    assert signal_style_values(style, 'pylightcharts')[5] == 8.0
    # PlotInfo.vars 之后拿到的是普通 dict —— 同样要能解析 ✓
    plain = {'key': 'low', 'color': 'red', 'marker': 'triangle',
             'overlap': True, 'show': True, 'size': None, 'label': False}
    assert signal_style_values(plain, 'bokeh')[5] == 12.0
    assert resolve_signal_size({'size': None}, 'pylightcharts') == 8.0
    # 显式 size 永远优先 ✓
    explicit = {'size': 17}
    assert signal_style_values(explicit, 'bokeh')[0] == 17.0
    assert resolve_signal_size(SignalStyle('low', 'red', 'triangle', size=9),
                               'bokeh') == 9.0


CODE = r'''
import sys, pathlib, webbrowser
sys.path.insert(0, {root!r})
webbrowser.open = lambda *a, **k: None
from minibt import (Bt, BtIndicator, Colors, Markers, SignalStyle, Strategy,
                    LocalDatas)


class Cross(BtIndicator):
    lines = ('long_signal', 'short_signal')
    isplot = dict(long_signal=False, short_signal=False)
    signalstyle = dict(
        long_signal=SignalStyle('low', Colors.red, Markers.triangle),
        short_signal=SignalStyle('high', Colors.green,
                                 Markers.inverted_triangle),
    )

    def next(self):
        close = self.close
        return (close.cross_up(close.ema(5)),
                close.cross_down(close.ema(5)))


class Mini(Strategy):
    def __init__(self):
        self.data = self.get_kline(LocalDatas.test)
        self.ind = Cross(self.data)

    def next(self):
        if not self.data.position and self.ind.long_signal.new:
            self.data.buy()


bt = Bt(auto=False)
bt.addstrategy(Mini)
bt.run(isplot=False)
from minibt.strategy.bokeh_plot import plot
tabs = plot(bt.strategies, build_only=True)
assert tabs is not None
print('BOKEH_SIGNAL_SIZE_OK')
'''


@pytest.mark.skipif(not DATA.exists(), reason='缺少 minibt/data/test/test.csv')
def test_bokeh_backtest_with_default_signal_size():
    code = CODE.format(root=str(ROOT))
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join([str(ROOT),
                                           os.environ.get('PYTHONPATH', '')]))
    result = subprocess.run([sys.executable, '-c', code], cwd=str(ROOT),
                            env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=600)
    assert 'BOKEH_SIGNAL_SIZE_OK' in result.stdout, (
        result.stdout + '\n' + result.stderr)

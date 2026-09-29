"""bokeh 回测绘图（`minibt/strategy/bokeh_plot.py::plot`）的回归测试。

覆盖：

* 双合约解包（历史 bug：``ValueError: too many values to unpack (expected 12)``）；
* 主题（``theme`` / ``bokeh_fullscreen``）与 tooltip 深/浅色 CSS 注入。

用子进程跑：bokeh 的全局 output/state 不会污染本进程，失败时也更好定位。
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'minibt' / 'data' / 'test' / 'pp2609_60.csv'

pytestmark = pytest.mark.skipif(
    not DATA.exists(),
    reason='缺少本地测试数据 minibt/data/test/pp2609_60.csv（跳过 bokeh 回归）',
)

# 双合约：合约 0 有信号、合约 1 没有 —— 正好触发“从合约 0 复制信号标记”
# 那个解包循环（历史 bug 所在）。
CODE = r'''
import pathlib, sys, tempfile, webbrowser
sys.path.insert(0, {root!r})
webbrowser.open = lambda *a, **k: None   # 不弹浏览器
import minibt.strategy.bokeh_plot as bp
bp.show = lambda *a, **k: None
from minibt import Bt, Config, LocalDatas, Strategy


class Mini(Strategy):
    config = Config(islog=False, profit_plot=False, theme={theme!r},
                    bokeh_fullscreen={fullscreen!r}, toolbox={toolbar!r})

    def __init__(self):
        self.data = self.get_kline(LocalDatas.pp2609_60)
        self.data1 = self.get_kline(LocalDatas.l2609_60)
        self.cci = self.data.close.cci(14)

    def next(self):
        if not self.data.position:
            if self.cci.cross_up(-100).new:
                self.data.buy()
            elif self.cci.cross_down(100).new:
                self.data.sell()


bt = Bt(auto=False)
bt.addstrategy(Mini)
bt.run(isplot=False)
out = pathlib.Path(tempfile.mkdtemp())
tabs = bt.bokeh_plot(save_plot=True, plot_cwd=str(out))
assert tabs is not None, 'bokeh_plot 返回了 None'
html = next(out.glob('*bokeh_plot.html')).read_text(encoding='utf-8')
assert '--tooltip-color' in html, 'tooltip 主题色 CSS 未注入'
import re
if {toolbar!r}:
    assert re.search(r'"toolbar_location":\s*"right"', html), '开启 toolbox 应出现右侧工具栏'
else:
    assert re.search(r'"toolbar_location":\s*null', html), '默认不应出现工具栏'
{check}
print('BOKEH_PLOT_OK')
'''


def _run(code: str):
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join([str(ROOT),
                                           os.environ.get('PYTHONPATH', '')]))
    return subprocess.run([sys.executable, '-c', code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize('theme, fullscreen, toolbar, check', [
    ('dark', False, False,
     "assert '#454545' in html, '未套用深色主题（DARK_TABS_CSS 未注入）'\n"
     "assert '100vh' not in html, '未开启全屏不应注入 100vh 布局'"),
    ('light', False, False,
     "assert '#454545' not in html, 'light 主题不应注入 DARK_TABS_CSS'"),
    ('dark', True, False,
     "assert '#454545' in html\n"
     "assert '100vh' in html, '开启全屏应注入 100vh 布局'"),
    ('dark', False, True, "assert True"),
])
def test_bokeh_backtest_plot_renders_with_theme(theme, fullscreen, toolbar, check):
    result = _run(CODE.format(root=str(ROOT), theme=theme,
                              fullscreen=fullscreen, toolbar=toolbar,
                              check=check))
    assert result.returncode == 0, result.stderr
    assert 'BOKEH_PLOT_OK' in result.stdout


# 实盘「无限历史」：KLine 只保留最后 `_preload` 根（图表开局先放出的量），
# 而 `get_plot_datas()` 里的指标数组仍是全量 —— 历史 bug：
# `signal_price = price_data[signaldata > 0]` 报
# "boolean index did not match indexed array ... 200 ... 10000"。
CODE_PRELOAD = r'''
import pathlib, sys
sys.path.insert(0, {root!r})
import minibt.strategy.bokeh_plot as bp
bp.show = lambda *a, **k: None
from minibt import Bt, Colors, Config, LocalDatas, Markers, SignalStyle, Strategy
from minibt.indicators.base import IndicatorsBase


class Mini(Strategy):
    config = Config(islog=False)

    def __init__(self):
        self.data = self.get_kline(LocalDatas.pp2609_60)
        self.data1 = self.get_kline(LocalDatas.l2609_60)
        self.cci = self.data.close.cci(14)
        # SignalStyle('low', ...) 默认 overlap=True -> 取价用 K 线的 low 列
        self.cci.signal_style = dict(
            long_signal=SignalStyle(
                'low', Colors.red, Markers.triangle).set_label('B'),
            short_signal=SignalStyle(
                'high', Colors.green, Markers.inverted_triangle).set_label('S'),
        )

    def next(self):
        if not self.data.position:
            if self.cci.cross_up(-100).new:
                self.data.buy()
            elif self.cci.cross_down(100).new:
                self.data.sell()


bt = Bt(auto=False)
bt.addstrategy(Mini)
bt.run(isplot=False)
st = bt.strategies[0]

# 模拟实盘 preload：K 线只剩最后 PRELOAD 根，指标仍是全量
PRELOAD = 200
_orig_get = IndicatorsBase.__dict__['pandas_object'].fget


def _truncated(self):
    obj = _orig_get(self)
    try:
        if len(obj) > PRELOAD:
            return obj.iloc[-PRELOAD:]
    except Exception:
        pass
    return obj


IndicatorsBase.pandas_object = property(_truncated)
st.get_results = lambda: []          # 实盘没有回测结果

assert len(st.data.pandas_object) == PRELOAD
reg = {{}}
bp.plot(bt.strategies, live_sources=reg, build_only=True, with_equity=False,
        volume_mode='overlay')
print('BOKEH_PLOT_PRELOAD_OK')
'''


def test_bokeh_plot_tail_aligns_indicators_to_preload_kline():
    """K 线只给 preload 根时，指标数组要截尾对齐后再画（否则 IndexError）。"""
    result = _run(CODE_PRELOAD.format(root=str(ROOT)))
    assert result.returncode == 0, result.stderr
    assert 'BOKEH_PLOT_PRELOAD_OK' in result.stdout

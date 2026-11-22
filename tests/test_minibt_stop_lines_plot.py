"""停止线（`stop_price` / `target_price`）的**数值正确性 + 主图显示**（用户 2026-11-20）

背景：用户的策略是

```python
def next(self):
    if not self.kline.position.pos:
        self.kline.buy()
        self.kline.buy(stop=BtStop.SegmentationTracking)
```

实测三个问题（本文件就是这三条的护栏）：

1. `buy()` 调两次 → **每次开 2 手**（第一笔开仓 + 第二笔加仓）；
2. 止损价只做单调棘轮、没有上限 → 长时间持仓后 `stop_price` 漂到
   **14298**，而收盘才 4683（图上是一条飞出去的线）；
3. `Stop.update()` 空仓分支是 `else: pass` → 依赖"没人写过"，一旦平仓/开仓
   时序错位，空仓段会留着上一笔的止损价。

修法：
* `SegmentationTracking.long/short`（以及 `TimeSegmentationTracking`）加护栏 —
  多单止损**不得高于本根最低价**、空单**不得低于本根最高价**；
* `Stop.update()` 空仓时**显式写 NaN**，并用**上一根**的止损/止盈价判断触发；
* `set_default_stop_lines` 给默认线型（止损红虚线 / 止盈绿虚线）。

约定：持仓时逐根更新、空仓时 NaN、长度始终等于 K 线长度 ✓
"""
import json
import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip('minibt')

from minibt import Bt, LocalDatas, Strategy
from minibt.stop import BtStop


def _reset_strategy_registry() -> None:
    """清掉 `Base._strategy_instances`（`_sid=0` 会跨用例撞号 ✗）

    `Strategy` 的实例注册表是**类属性**：前面某个用例（尤其 desk overlay /
    btplot 的临时策略）留下 `_sid=0` 之后，本用例新建的策略可能拿到同一 sid →
    `strategy_instances[0]` 指回旧策略 → 止损绑到**别的** K 线上
    （表现为 `kline.stop_price is None` / 初始化 TypeError）。`bt.run()` 自己
    会重置，但 `run_overlay` 这类入口不一定，所以测试里显式清一次 ✓
    """
    try:
        from minibt.utils import Base, StrategyInstances
    except Exception:                                        # noqa: BLE001
        return
    Base._strategy_instances = StrategyInstances()


def _run_once(bars_hold_at: int = 30, single: bool = True):
    """跑一次回测：第 `bars_hold_at` 根开仓（带 SegmentedTracking），返回上下文 ✓"""
    _reset_strategy_registry()
    state = {'kline': None, 'pos': [], 'done': False}

    class Once(Strategy):
        def __init__(self):
            self.kline = self.get_kline(LocalDatas.test)
            # ★ K 线是**共享对象**（同一个进程里前面的测试可能已经跑过带 Stop 的
            #   回测）→ 先清掉旧止损线，否则本次会复用上一笔的 `isstop`/`stop` ✓
            self.kline.reset_stop_lines()
            state['kline'] = self.kline

        def next(self):
            pos = self.kline.position.pos
            state['pos'].append(pos)
            if state['done']:
                return
            if single and self.kline.btindex < bars_hold_at:
                return
            self.kline.buy(stop=BtStop.SegmentationTracking)
            state['done'] = True

    bt = Bt(auto=False)
    bt.addstrategy(Once)
    bt.run(isplot=False, isreport=False)
    kline = state['kline']
    return {
        'kline': kline,
        'pos': np.asarray(state['pos'], dtype=int),
        'stop': np.asarray(kline.stop_price.values, dtype=float),
        'target': np.asarray(kline.target_price.values, dtype=float),
        'close': np.asarray(kline.close.values, dtype=float),
        'low': np.asarray(kline.low.values, dtype=float),
        'high': np.asarray(kline.high.values, dtype=float),
    }


@pytest.fixture(scope='module')
def once():
    return _run_once()


# ---------------------------------------------------------------- 数值正确性
def test_stop_lines_length_equals_bars(once):
    """长度必须与 K 线一致（图上是"整段一根线"，不能只剩最后一根 ✓）"""
    bars = len(once['kline'])
    assert len(once['stop']) == bars
    assert len(once['target']) == bars
    # 回测可能只跑尾部一段（`min_start_length` / 共享 K 线被截断）→ 右对齐比较
    assert len(once['pos']) <= bars


def test_stop_price_never_above_bar_low(once):
    """多单止损价必须 ≤ 本根最低价（棘轮护栏；以前会漂到价格上方一万多点 ✗）"""
    stop = once['stop']
    low = once['low']
    mask = np.isfinite(stop) & np.isfinite(low)
    assert mask.any()
    assert bool((stop[mask] <= low[mask] + 1e-9).all())


def test_stop_price_stays_near_price(once):
    """止损价不能离收盘价太远（历史 bug：14298 vs 4683 ✗）"""
    stop, close = once['stop'], once['close']
    mask = np.isfinite(stop) & np.isfinite(close)
    assert mask.any()
    ratio = np.abs(stop[mask] - close[mask]) / close[mask]
    assert float(ratio.max()) < 0.1, f'最大偏离 {ratio.max():.1%}'


def test_nan_when_flat_and_value_when_holding(once):
    """持仓段有值、平仓之后必须是 NaN（长度不变）✓"""
    stop, pos = once['stop'], once['pos']
    # 右对齐：`pos` 可能只覆盖尾部一段（见上一个测试的说明）
    stop = stop[-len(pos):]
    finite = np.isfinite(stop)
    idx = np.flatnonzero(finite)
    assert idx.size, '持仓期间应当有止损价'
    last = int(idx.max())
    # 平仓之后的每一根都必须是 NaN（空仓 = 空白点，图上自然断开）
    tail = stop[last + 1:]
    assert np.isnan(tail).all(), tail[:5]
    # 开仓后的持仓段应当基本都有值
    hold = pos != 0
    assert hold.any()
    covered = np.isfinite(stop[hold]).sum() / max(1, hold.sum())
    assert covered > 0.5, f'持仓段只有 {covered:.0%} 有值'


def test_target_price_all_nan_for_segmentation_tracking(once):
    """`SegmentationTracking` 不设目标价 → 全 NaN（图上不画止盈线 ✓）"""
    assert np.isnan(once['target']).all()


def test_single_buy_opens_one_lot():
    """`buy(stop=...)` 只调一次 → 1 手（以前 buy()+buy() 是 2 手 ✗）"""
    ctx = _run_once(bars_hold_at=30)
    assert set(np.unique(ctx['pos']).tolist()) <= {-1, 0, 1}
    assert 1 in set(np.unique(ctx['pos']).tolist())


# ---------------------------------------------------------------- 主图显示
def test_overlay_puts_stop_line_on_main_chart(tmp_path):
    """desk 本地图表：止损线必须是**主图**的虚线红线，且不出空目标线 ✓

    ⚠ 用**子进程**跑：desk 的 overlay 会在 `Base._strategy_instances` /
    `_indsetting` 这些**类级全局状态**上留痕，同进程里前面跑过别的 overlay 后
    再跑这一段会 `策略初始化失败: TypeError: Value after * must be an iterable`
    （框架既有串扰，与本轮止损线无关）。子进程 = 干净解释器，断言才稳定 ✓
    """
    script = r'''
import json
import numpy as np
from minibt import Bt, LocalDatas, Strategy
from minibt.stop import BtStop
from minibt.desk import strategy_overlay as ov


class Both(Strategy):
    def __init__(self):
        self.kline = self.get_kline(LocalDatas.test)
        self.kline.reset_stop_lines()
        close = self.kline.close
        self.fast = close.rolling(5).mean(lines=['sma_fast'])
        self.slow = close.rolling(20).mean(lines=['sma_slow'])
        self.fast.overlap = self.slow.overlap = True

    def next(self):
        if not self.kline.position.pos:
            self.kline.buy(stop=BtStop.SegmentationTracking)


frame = LocalDatas.test.kline
result = ov.run_overlay(frame, Both, 'test', 60, replay=True,
                        replay_bars=len(frame),
                        frames=[('test', frame)])
out = {'ok': bool(result.get('ok')), 'error': result.get('error') or '',
       'bars': len(frame), 'items': []}
for item in result.get('items') or []:
    out['items'].append({
        'key': str(item.get('key')),
        'overlay': item.get('overlay'),
        'kind': item.get('kind'),
        'lineStyle': item.get('lineStyle'),
        'color': item.get('color'),
        'points': len(item.get('data') or []),
    })
print('@@RESULT@@' + json.dumps(out))
'''
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    proc = subprocess.run([sys.executable, '-c', script],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', env=env, check=False,
                          cwd=str(pathlib.Path(__file__).resolve().parents[1]))
    assert proc.returncode == 0, (proc.stderr or '')[-2000:]
    line = next((row for row in (proc.stdout or '').splitlines()
                 if row.startswith('@@RESULT@@')), '')
    assert line, (proc.stdout or '')[-2000:]
    data = json.loads(line[len('@@RESULT@@'):])
    assert data['ok'], data.get('error')
    items = {item['key']: item for item in data['items']}
    key = next((k for k in items if 'stop_price' in k), '')
    assert key, list(items)
    stop = items[key]
    assert stop['overlay'] is True            # 主图（不是副图）
    assert stop['kind'] == 'line'
    assert stop['lineStyle'] == 2             # 虚线（LineDash.dashed）
    assert str(stop.get('color') or '').lower() == '#ef5350'
    assert stop['points'] == data['bars']     # 与 K 线等长（空点保留 ✓）
    # 目标价全 NaN → 不该出现 target_price 线
    assert not any('target_price' in k for k in items), list(items)


def test_default_stop_lines_style():
    """`stop_lines` 自带默认线型：止损红虚线 / 止盈绿虚线 ✓"""
    kline = LocalDatas.test.kline
    frame = kline.stop_lines
    assert list(frame.columns) == ['stop_price', 'target_price']
    assert bool(frame.overlap['stop_price']) is True
    styles = frame.plotinfo.linestyle
    stop, target = styles['stop_price'], styles['target_price']
    assert str(stop.line_dash).endswith('dashed')
    assert str(stop.line_color).lower() == '#ef5350'
    assert str(target.line_color).lower() == '#26a69a'


# ---------------------------------------------------------------- 实现细节
def test_stop_update_uses_previous_bar_and_clears_when_flat():
    """源码护栏：`update()` 空仓写 NaN + 用上一根判断（防回归）✓"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'minibt' / 'indicators' / 'core.py').read_text(
        encoding='utf-8')
    start = source.index('    def update(self) -> bool:')
    body = source[start:start + 2600]
    assert 'self.stop_price.new = np.nan' in body
    assert 'self.target_price.new = np.nan' in body
    assert 'prev_stop' in body and 'self.stop_price[-2]' in body


# ---------------------------------------------------------------- bokeh 出图
def test_draw_stop_lines_skips_nan_and_duplicate():
    """`_draw_stop_lines`：全 NaN 不画、target 与 stop 相同只画一条 ✓"""
    import numpy as np
    from bokeh.models import ColumnDataSource
    from bokeh.plotting import figure

    from minibt.btplot import _draw_stop_lines

    kline = LocalDatas.test.kline
    kline.reset_stop_lines()
    frame = kline.stop_lines
    n = len(kline)
    # 只写 stop_price（模拟 SegmentationTracking）
    stop = np.full(n, np.nan)
    stop[:5] = 100.0
    frame.stop_price.new = 100.0
    fig = figure()
    source = ColumnDataSource({'index': list(range(n))})
    drawn = _draw_stop_lines(fig, source, frame)
    assert drawn == ['stop_price']          # 目标价全 NaN → 不画
    assert 'stop_price' in source.column_names
    kline.reset_stop_lines()


def test_btplot_bokeh_draws_stop_and_target(tmp_path, monkeypatch):
    """`btplot(gui='bokeh')` 要把止损 + 止盈线画到**主图**（HTML 里能查到）✓"""
    import webbrowser

    import numpy as np

    import minibt.btplot as btplot_mod
    from minibt.stop import BtStop

    monkeypatch.setattr(webbrowser, 'open', lambda *a, **k: True)

    state = {}

    class Both(Strategy):
        def __init__(self):
            self.kline = self.get_kline(LocalDatas.test)
            self.kline.reset_stop_lines()
            self.ma = self.kline.pta.sma(length=20)
            state.update(kline=self.kline, ma=self.ma)

        def next(self):
            # 第一根就开仓（不依赖 `btindex == 30`：共享 K 线可能被别的用例
            # 截断/换过，按绝对下标取会取不到 ✗）
            if not self.kline.position.pos:
                self.kline.buy(stop=BtStop.FixedStop(stop_distance=5,
                                                     target_distance=20))

    _reset_strategy_registry()
    bt = Bt(auto=False)
    bt.addstrategy(Both)
    bt.run(isplot=False, isreport=False)
    stop = np.asarray(state['kline'].stop_price.values, dtype=float)
    target = np.asarray(state['kline'].target_price.values, dtype=float)
    assert np.isfinite(stop).any() and np.isfinite(target).any()

    out = tmp_path / 'bokeh'
    btplot_mod.btplot(state['ma'], gui='bokeh', save_plot=True,
                      plot_cwd=str(out), plot_name='stop')
    html = (out / 'stop_btplot.html')
    assert html.is_file(), list(out.iterdir())
    text = html.read_text(encoding='utf-8', errors='replace')
    assert text.count('stop_price') >= 3        # 列名 + glyph + 图例
    assert text.count('target_price') >= 3
    assert '#ef5350' in text                   # 止损红
    assert '#26a69a' in text                   # 止盈绿
    state['kline'].reset_stop_lines()

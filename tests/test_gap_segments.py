"""pylightcharts 的「NaN 处断线」分段策略。

* **少量段**（≤ ``Line.MAX_GAP_SEGMENTS``，默认 64）仍逐段拆：每段一个
  legend-less ``Line`` 序列，tooltip / 十字光标最干净；
* **超过 64 段**改用 **单序列 + 透明缺口**：缺口点补成前值并染透明，引擎按
  每段**起点**取色，缺口那一段就不画 —— 效果与逐段拆一样，却只有 1 个序列
  （几百上千个分段序列每个都要一次 `addSeries` + `setData` + 一次重绘，
  加载时会"一条条从左到右画出来"）。
"""
import numpy as np
import pandas as pd


def _set(chart, name, values, **options):
    n = len(values)
    times = pd.date_range('2025-01-01', periods=n, freq='min')
    line = chart.add_series('Line', name=name, **options)
    line.set(pd.DataFrame({'time': list(times), name: values}),
             format_cols=False)
    return line


def _segments(n, length, gap):
    """`n` 段、每段 `length` 根、间隔 `gap` 根的 NaN 数据。"""
    step = length + gap
    vals = np.full(n * step, np.nan)
    for i in range(0, n * step, step):
        vals[i:i + length] = np.arange(length, dtype=float) + i
    return vals


def test_few_segments_are_split():
    """10 段（≤ 64）：仍逐段拆成 10 个分段序列。"""
    from pylightcharts.headless import HeadlessChart
    chart = HeadlessChart()
    line = _set(chart, 'st_up', _segments(10, 30, 5))
    assert len(line.__dict__.get('_gap_series') or []) == 10


def test_many_segments_use_one_transparent_series():
    """110 段、每段 30 根：1 个序列 + 透明缺口，不再建 110 个序列。"""
    from pylightcharts.headless import HeadlessChart
    chart = HeadlessChart()
    line = _set(chart, 'st_up', _segments(110, 30, 30), color='#09D142')
    assert not (line.__dict__.get('_gap_series') or [])
    payload = '\n'.join(chart._scripts)
    assert 'rgba(0, 0, 0, 0)' in payload          # 缺口点染透明
    assert '#09D142' in payload                   # 有效段仍是线色


def test_fragmented_line_uses_transparent():
    """100 段、每段 1 根（逐 bar 交替 NaN）：同样走单序列 + 透明缺口。"""
    from pylightcharts.headless import HeadlessChart
    chart = HeadlessChart()
    line = _set(chart, 'frag', _segments(100, 1, 2), color='#e00000')
    assert not (line.__dict__.get('_gap_series') or [])
    assert 'rgba(0, 0, 0, 0)' in '\n'.join(chart._scripts)


def test_no_nan_stays_single():
    from pylightcharts.headless import HeadlessChart
    chart = HeadlessChart()
    line = _set(chart, 'smooth', np.arange(100.0))
    assert not (line.__dict__.get('_gap_series') or [])

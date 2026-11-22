"""v1.3.8-1：多布局「第 2..N 格」K 线比第 1 格慢（三处根因）。

用户实测（`实时图表左右布局格2.png`）：左格有策略 + 指标时，右格的 K 线
明显"慢半拍"；昨天纯 K 线时正常 → 说明是"增量 / 重算"路径的问题。

根因：
1. 前端 `setCellBars(cell>0)` 增量是**直接 concat**（没有按时间去重）：
   后端每秒推「上一根 + 最后一根」→ 每条时间戳都重复一遍，数组每秒多 2 项，
   `setData` 又要求时间升序 → 第 2 格越跑越慢 / 蜡烛画错 ✗；
2. 前端每次都整表 `setData`（O(n)），第 1 格走的是增量 `update()`；
3. 后端第 2..N 格的"变没变"指纹**只看 close**：影线（high/low）变化不推；
   另外策略后台计算期间 `tick()` 整段跳过 `_refresh_tabs` → 右格停更
   （左格因为策略补丁会整表重推，看起来是"正常"的）。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = (ROOT / 'jslib' / 'src' / 'desk' / 'chart-page.ts').read_text(encoding='utf-8')
APP = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')


# ---------------------------------------------------------------- 前端
def test_cell_bars_dedupe_and_incremental():
    """第 2 格增量：按时间去重（mergeBars）+ 只 update 尾部几根"""
    block = CHART.split('setCellBars(index: number', 1)[1].split('private _applyCellBars', 1)[0]
    assert 'mergeBars(this.cellBars[cell] || [], bars)' in block
    assert '.concat(bars)' not in block            # 老写法必须消失 ✓
    assert 'this._applyCellBars(cell, replace ? null : bars);' in block

    apply_block = CHART.split('private _applyCellBars(index: number', 1)[1].split('\n    }', 1)[0]
    assert 'if (tail && tail.length && tail.length <= 3)' in apply_block
    assert 'series.update({' in apply_block       # 增量不再整表 setData ✓


# ---------------------------------------------------------------- 后端
def test_backend_cell_fingerprint_uses_high_low():
    """第 2..N 格指纹带 high / low（影线变了也要推 ✓）"""
    assert 'key = (count, first_time, last_time, close, high, low)' in APP
    assert "high = round(float(frame['high'].iloc[-1]), 6)" in APP
    assert "low = round(float(frame['low'].iloc[-1]), 6)" in APP


def test_heavy_jobs_pause_is_logged():
    """策略后台计算期间图表会停更 → 至少写日志（含恢复）✓"""
    assert 'self._heavy_since = 0.0' in APP
    assert '期间图表暂停刷新（已自动恢复）' in APP
    block = APP.split('busy = int(getattr(self, \'_heavy_jobs\', 0)) > 0', 1)[1][:800]
    assert 'if busy:' in block and 'elif self._heavy_since:' in block

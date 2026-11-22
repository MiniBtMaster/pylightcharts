"""回放进出时指标图例 / 信号不能累积（v1.3.9-21）。

用户实测 2026-11-17（多布局回放还是有问题.png）：2×1 布局里反复进出回放，
第 2 格左上角出现**三组**同样的 `AdaptiveTrendTrail.*` 标签；而且第 2 格的
交易信号会提前出现在图上、随回放往后挪，走到那根 K 线才落上去。

根因（前端 `jslib/src/desk/indicator.ts`）：

* 图例行 / 信号箭头载体 / markers 图元的 Map 以前按**原始 key** 存
  （`tv:AdaptiveTrendTrail:trend` 与 `AdaptiveTrendTrail.trend` 是两个 key）→
  每换一次来源就新建一行 / 一条载体，旧的没人删 → 一组一组往上叠 ✗
* `handler.createCustomSeries(name, …)`（信号箭头）会**自动**建一行原生图例，
  而删序列走的是 `chart.removeSeries()`（不摘图例行）→ 那行永远留着 ✗

这份测试盯源码闸门（ChartPage / IndicatorLayer 依赖 lightweight-charts，
跑不了真浏览器）。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / 'jslib' / 'src' / 'desk'


def test_indicator_key_is_case_preserving():
    module = (DESK / 'indicator-key.ts').read_text(encoding='utf-8')
    # 内置指标 `MA20` / `MACD_DIF` 的大小写是身份，不能转小写 ✗
    assert '[^A-Za-z0-9' in module
    assert '.toLowerCase()' not in module
    # 去重必须**确定**地选一个 key 口径（否则每拍都重建图例行 ✗）
    assert 'function keyScore(' in module
    assert 'key.includes(\':\') ? 2 : 1' in module


def test_layer_keys_use_family():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    assert "import { normalizeIndicatorKey } from './indicator-key';" in layer
    assert 'private _family(key: string): string {' in layer
    # 图例行 / 箭头载体 / markers 图元都按家族名存 ✓
    assert 'const id = this._family(item.key);' in layer
    assert 'this.legendRows.set(id, {' in layer
    assert 'this.markerSeries.set(id, host);' in layer
    assert 'this.markerPrimitive.set(' in layer
    # 图例清扫按家族名比（以前拿原始 key 比 → 每拍全删重建 ✗）
    assert 'if (!aliveFamilies.has(key)) this._dropLegendRow(key);' in layer
    assert 'const aliveFamilies = new Set(items.map((item) => this._family(item.key)));' \
        in layer


def test_native_legend_is_pruned_with_series():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    assert 'private _pruneNativeLegend(): void {' in layer
    assert 'this._pruneNativeLegend();' in layer
    # 只有 series 还在 handler 的序列清单里才保留那一行 ✓
    assert 'const live = new Set<unknown>(liveList);' in layer


def test_signal_series_are_keyed_by_family():
    """交易信号的自定义序列也要按家族名（`tv:X:line` == `X.line`）✓"""
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    body = layer.split('private _applyShapeRows(', 1)[1]
    body = body.split('private _applyCandleSeries(', 1)[0]
    assert 'const id = this._family(item.key);' in body
    assert 'this.shapeSeries.set(id, entry);' in body
    # ★ 不让 pylightcharts 自动建图例行（自动建的行删不干净 ✗）
    assert "createCustomSeries(" in body
    assert "'', {}, handle, paneIndex)" in body
    assert 'this._syncLegendRow(item, (entry as unknown as {' in body


def test_same_label_rows_are_deduped():
    """同名图例行收敛成一行（历史残留的自动行也能被清掉 ✓）"""
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    assert 'private _dedupeNativeLegend(): void {' in layer
    assert 'this._dedupeNativeLegend();' in layer
    # 保留「归我们管」的那行（有 ⚙），丢残留的自动行 ✓
    assert 'if (owned && !prev.owned) {' in layer


def test_drop_everything_really_removes_signals():
    """换合约 / 进出回放时的 `_dropEverything()` 必须**真删**信号序列 ✓

    以前只清 Map，自定义序列还留在 handler 里继续画箭头 → 图上多一套信号，
    图例眼睛也管不到（用户实测 2026-11-17 ✗）。
    """
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    body = layer.split('private _dropEverything(): void {', 1)[1]
    body = body.split('private ', 1)[0]
    assert 'handler.removeSeries(entry' in body        # 信号自定义序列真删 ✓
    assert 'this.shapeSeries.clear();' in body
    # 图例行也要真删（否则每清一次多一组标签 ✗）
    assert 'this.legendRows.values()' in body
    assert '_lines = lines.filter(' in body


def test_replay_uses_each_cell_symbol():
    """回放时每格用自己的合约（以前全塞页签合约 → 每拍 `_dropEverything` ✗）"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (DESK / name).read_text(encoding='utf-8')
        body = page.split('private _applyReplayIndicators(', 1)[1]
        body = body.split('this.setCellIndicators(index,', 1)[0]
        assert 'const cellSymbol = index === 0' in body
        assert 'symbol: cellSymbol,' in page


def test_future_signals_are_clipped():
    layer = (DESK / 'indicator.ts').read_text(encoding='utf-8')
    assert 'private _clipToBars(rows: unknown[]): unknown[] {' in layer
    # 自定义序列（信号箭头）与原生 markers 都要过闸门 ✓
    assert 'rows = this._clipToBars(rows);' in layer
    assert 'this._clipToBars(item.markers || [])' in layer

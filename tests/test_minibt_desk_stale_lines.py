"""v1.3.7-111：换合约后旧合约的持仓线 / 挂单线 / 预警线没清干净 → 价格轴被拉爆。

用户截图 `持仓线没清理干净.png`：清仓后上一个合约（约 800）的线还在，切到
新合约（约 9000）时价格轴变成 0~12000，K 线被压成一条线 ✗。

根因：三类线（`HorizontalLine` primitive）+ 主图叠加序列（策略停止线）的
"删除"都依赖「补丁能对上页面」这一前提 —— 清仓 / 切合约 / 迟到补丁任何
一环对不上就会漏。所以除了补清理，还加了一道**与补丁无关**的闸门：
价格不属于当前标的的线，无论谁画的都不显示。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / 'jslib' / 'src' / 'desk'
CHART = (DESK / 'chart-page.ts').read_text(encoding='utf-8')
LOCAL = (DESK / 'local-chart-page.ts').read_text(encoding='utf-8')
LAYER = (DESK / 'indicator.ts').read_text(encoding='utf-8')
APP = (DESK / 'app.ts').read_text(encoding='utf-8')


# ---------------------------------------------------------------- 实时图表
def test_chart_has_price_band_gate():
    """实时图表：价格带 + 闸门 + 复查（三类线都过闸）"""
    assert 'private _priceBand(cell = 0): [number, number] | null {' in CHART
    assert 'private _priceFits(price: number, cell = 0, margin = 0.5): boolean' in CHART
    assert 'pruneForeignLines(): void {' in CHART
    # 持仓 / 挂单 / 预警 三处都过滤
    assert CHART.count('.filter((side) => this._priceFits(') >= 1
    assert 'if (!this._priceFits(price, cell)) continue;' in CHART
    assert 'if (!this._priceFits(price, 0)) continue;' in CHART


def test_chart_prunes_on_new_bars():
    """新 K 线到达就复查（换合约 / 清仓漏删都能兜住 ✓）"""
    block = CHART.split('setBars(bars: ChartBar[]', 1)[1].split('setCellBars(', 1)[0]
    assert 'this.pruneForeignLines();' in block


def test_chart_clears_everything_on_symbol_switch():
    """切合约：`clearAllLines()` + 只改 symbol 的路径也要清 ✓"""
    assert 'clearAllLines(): void {' in CHART
    reset = CHART.split('resetForSymbol(): void {', 1)[1].split('\n    }', 1)[0]
    assert 'this.clearAllLines();' in reset
    setter = CHART.split('setSymbol(symbol: string, name = \'\'): void {', 1)[1]
    assert 'this.clearAllLines();' in setter.split('this._setSymbolButton', 1)[0]


def test_chart_ignores_foreign_symbol_patches():
    """别的合约的持仓 / 挂单补丁一律忽略（不能画到当前合约上 ✓）"""
    assert '    }, cell = 0, symbol = \'\'): void {' in CHART
    assert '              symbol = \'\'): void {' in CHART
    assert CHART.count('if (symbol && own && symbol !== own) {') == 2
    # app.ts 要把补丁里的 symbol 传下去
    assert 'page.setPosition(sides,' in APP
    assert 'symbol);' in APP


# ---------------------------------------------------------------- 本地图表
def test_local_chart_has_same_gate():
    assert 'private _priceBand(cell = 0): [number, number] | null {' in LOCAL
    assert 'pruneForeignLines(): void {' in LOCAL
    assert 'clearAllLines(): void {' in LOCAL
    assert 'if (!this._priceFits(price, cell)) continue;' in LOCAL
    assert 'if (!this._priceFits(price, 0)) continue;' in LOCAL
    # 换 CSV = 换标的 → 清线
    assert 'previousName !== name' in LOCAL


# ---------------------------------------------------------------- 指标图层
def test_layer_drops_stale_series_and_prices():
    """图层：合约变了整体清空 + 主图叠加线不在价格带里就丢掉 ✓"""
    assert 'private payloadSymbol = \'\';' in LAYER
    assert 'private _fitsBand(item: IndicatorLine): boolean {' in LAYER
    assert 'private _dropEverything(): void {' in LAYER
    assert 'this._dropEverything();' in LAYER
    assert 'items = items.filter((item) => this._fitsBand(item));' in LAYER
    # 价格带来自 `setBars`
    assert 'this.priceBand = (Number.isFinite(low) && Number.isFinite(high)' in LAYER

"""多布局两个 BUG（用户 2026-11-08 实测）：

1. **工具栏周期不跟当前格**：AI 打开左右布局后，点第 1 / 第 2 格，工具栏
   「周期」按钮还是原来的周期（没有变成当前合约的周期）——因为后端从来没把
   **每格周期**告诉前端（`layout` / `kline` 补丁都不带 `cycle` / `cycles`）。
2. **交易四按钮来回跳**：左右布局里格 1 = 白银空 3 手、格 2 = 黄金空仓；
   点格 2 后，交易面板的四个按钮在「无持仓组」和「空仓组」之间每拍来回切换
   —— 因为 `setPosition()` 里 `index === 0 || symbol === focus`，格 1 的持仓
   补丁**永远**会覆盖交易面板（每秒都推一次 → 两组交替 ✗）。
"""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
from minibt.desk.app import Desk  # noqa: E402


def _read(*parts) -> str:
    return REPO.joinpath(*parts).read_text(encoding='utf-8')


# ------------------------------------------------------------- ① 每格周期
def test_layout_patch_carries_per_cell_cycles():
    desk = Desk(offline=True)
    desk.sent = []
    desk.push = desk.sent.append          # 直接收补丁（sender 收的是脚本 ✓）
    desk._booted = True
    desk.tabs['SHFE.ag2612'] = {
        'cycle': 60,
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': ['SHFE.ag2612', 'SHFE.au2612'],
                   'cells': [{}, {}], 'cycles': [60, 300]},
    }
    desk.last_symbol = 'SHFE.ag2612'
    desk._on_set_layout({'symbol': 'SHFE.ag2612', 'cols': 2, 'rows': 1})
    layout = [p for p in desk.sent if isinstance(p, dict)
              and p.get('type') == 'layout'][-1]
    assert layout['cycles'] == [60, 300]     # ★ 第 2 格 5 分钟要带给前端 ✓
    assert layout['cycle'] == 60
    assert layout['symbols'] == ['SHFE.ag2612', 'SHFE.au2612']


def test_cell_kline_patch_carries_cycle():
    app = _read('minibt', 'desk', 'app.py')
    # `_on_set_cycle`（cell > 0 分支）
    block = app.split('def _on_set_cycle(', 1)[1].split(
        'def account_fingerprint', 1)[0]
    assert 'cycle=cycle))' in block
    # `_push_cell_bars`：每格 K 线也带自己的周期
    cells = app.split('def _push_cell_bars(', 1)[1].split(
        'def _replay_indicator_items', 1)[0]
    assert 'cell=index, cycle=cell_cycle))' in cells


def test_frontend_adopts_cell_cycle():
    page = _read('jslib', 'src', 'desk', 'chart-page.ts')
    assert 'adoptCellCycle(cell: number, cycle: number): void {' in page
    # setCellBars 收 cycle 并采纳
    block = page.split('setCellBars(index: number, bars: ChartBar[],', 1)[1]
    assert 'if (cycle !== undefined) this.adoptCellCycle(cell, Number(cycle));' \
        in block
    # applyLayout 采纳 cycles
    layout = page.split('applyLayout(payload:', 1)[1].split(
        '_refreshDrawings();', 1)[0]
    assert 'count?: number; key?: string; cycle?: number; cycles?: number[];' \
        in page
    assert '(payload.cycles || []).forEach((value, index) => {' in layout
    assert 'this.cellCycles[index] = parsed;' in layout
    # 活动格的工具栏周期立即刷新
    adopt = page.split('adoptCellCycle(cell: number, cycle: number)', 1)[1]
    assert 'this.cycleLabel.textContent = this._cycleText(value);' in adopt
    # app.ts 把 kline 补丁里的 cycle 传下去
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert 'Number(patch.cycle) || undefined);' in app


# ------------------------------------------------------------- ② 交易面板
def test_ticket_position_follows_trade_symbol_only():
    page = _read('jslib', 'src', 'desk', 'chart-page.ts')
    pos = page.split('    setPosition(payload: {', 1)[1].split(
        '/** 真正画某一格的持仓线', 1)[0]
    # ★ 不能再用 `index === 0 || …`（格 1 每拍都会把面板顶回去 ✗）
    assert 'index === 0 || symbol === focus' not in pos
    assert '_isTradeCell' in page
    assert 'private _isTradeCell(index: number): boolean {' in page
    # 切换标的后立刻套用那一格已知持仓（不用等下一拍）
    trade = page.split('setTradeSymbol(symbol: string): void {', 1)[1].split(
        '/** 某个合约的最新价', 1)[0]
    assert 'const known = cell >= 0 ? this.lastPositions.get(cell) : undefined;' \
        in trade
    assert 'this.ticket?.setPosition(' in trade


def test_local_ticket_position_follows_trade_symbol_only():
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    block = page.split('    private _setTicketPosition(', 1)[1].split(
        '/** 导出历史', 1)[0]
    assert 'if (this._isTradeCell(cell)) {' in block
    assert 'this.localTicket?.setPosition(long, short);' in block
    assert 'private _isTradeCell(cell: number): boolean {' in page


def test_trade_cell_detection_semantics():
    """`_isTradeCell`：有标的 → 只认那一格；没标的 → 第 1 格 ✓"""
    page = _read('jslib', 'src', 'desk', 'chart-page.ts')
    block = page.split('private _isTradeCell(index: number): boolean {', 1)[1]
    block = block.split('}', 1)[0]
    assert 'const focus = this.tradeSymbol || this.options.symbol;' in block
    assert "return !!symbol && symbol === focus;" in block

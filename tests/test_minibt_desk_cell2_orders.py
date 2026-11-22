"""v1.3.8-2：多布局「第 2 格」的挂单线在成交 / 撤单后不消失。

用户截图 `格2的挂单线.png`：右格还挂着「挂单卖1手 9117」的虚线，
但「未成委托」列表已经是「暂无数据」→ 空推送被前端丢掉了。

根因：v1.3.7-111 给 `setOrders()` 加了**归属校验**（别的合约的补丁一律忽略），
但后端推的是 `symbol`（= 主 tab 名，用于路由）+ `cell`，而这一格的合约是
`cellSymbols[cell]`。两者在左右布局里**永远不相等** → 空推送被当成"外来补丁"
丢掉 → 成交 / 撤单后挂单线留在图上 ✗。

修法：后端补 `cell_symbol`（这一格真正的合约），前端归属校验优先用它。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = (ROOT / 'jslib' / 'src' / 'desk' / 'chart-page.ts').read_text(encoding='utf-8')
APP_TS = (ROOT / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(encoding='utf-8')
APP_PY = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')


def test_backend_sends_cell_symbol_for_orders():
    """后端：第 2..N 格 & 第 1 格都要带 `cell_symbol` ✓"""
    assert "orders['cell_symbol'] = cell_symbol" in APP_PY
    assert "payload['cell_symbol'] = cell0_symbol" in APP_PY
    assert "position['cell_symbol'] = cell_symbol" in APP_PY


def test_frontend_guard_uses_cell_symbol():
    """前端：归属校验用 `cell_symbol`，缺省才回退 `symbol` ✓"""
    assert ".cell_symbol || symbol" in APP_TS
    # 两处（orders / position）都要用
    assert APP_TS.count('.cell_symbol || symbol') >= 2


def test_guard_still_ignores_foreign_contracts():
    """外来合约的补丁仍然要被挡住（别把保护拆了 ✓）"""
    assert CHART.count('if (symbol && own && symbol !== own) {') == 2
    block = CHART.split('setOrders(items: Array<Record<string, unknown>>', 1)[1]
    assert 'return;' in block.split('this.orderItemsByCell.set', 1)[0]


def test_order_lines_cleared_on_empty_push():
    """空列表 → 这一格的线立刻撤掉（`_clearOrderLines` 在重画前先跑）✓"""
    block = CHART.split('private _renderOrderLines(cell = 0): void {', 1)[1]
    head = block.split('for (const item of items)', 1)[0]
    assert 'this._clearOrderLines(cell);' in head

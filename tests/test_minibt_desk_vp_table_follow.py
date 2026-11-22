"""本地图表：VP 档位区间 + 表格（多格）跟随鼠标 ✓（2026-11-03 用户实测）

两个 bug：
1. `tutorials/basic/vp.py` 的 VPMode1：VP 柱体跑到十字线**下方** ——
   `_vp_item()` 还原档位价格时用了 `price_bars or 120`，而指标默认
   `price_bars=500` → 矩阵按 500 根分档、绘图按 120 根还原 → 分布被压扁；
2. `tutorials/basic/table.py` 的表格不跟随鼠标 —— 十字线只订阅了**格 1**，
   表格在其它格时收不到 `crosshairMove` → 静态。
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK_TS = ROOT / 'jslib' / 'src' / 'desk'


def _read(path) -> str:
    return pathlib.Path(path).read_text(encoding='utf-8')


def _frame(rows: int = 900) -> pd.DataFrame:
    """前 780 根价格 100~140（宽区间），最后 120 根 130~132（窄区间）✓"""
    close = np.concatenate([
        np.linspace(100, 140, rows - 120),
        np.linspace(130, 132, 120),
    ])
    return pd.DataFrame({
        'datetime': pd.date_range('2025-01-01', periods=rows, freq='h'),
        'open': close,
        'high': close + 1,
        'low': close - 1,
        'close': close,
        'volume': np.full(rows, 10.0),
    })


class _Plot:
    category = 'vp'
    vpstyle = {'price_bars': 500}


def test_vp_lo_hi_uses_indicator_price_bars():
    """`vpLo/vpHi` 必须和指标同一套滚动档区（默认 500 根，不是 120）✓"""
    from minibt.desk import indicator_catalog as cat

    frame = _frame(900)
    rows = len(frame)
    matrix = np.zeros((rows, 4), dtype=float)
    matrix[:, 0] = 1.0
    stamps = [int(value) for value in
              frame['datetime'].astype('int64') // 10 ** 9]
    item = cat._vp_item(['vp0', 'vp1', 'vp2', 'vp3'], matrix, stamps, frame,
                        {'name': 'vp'}, _Plot(), 'k', np)
    assert item is not None
    # 最后一根：500 根窗口的 low/high（不是 120 根）✓
    last_lo = float(frame['low'].iloc[-500:].min())
    last_hi = float(frame['high'].iloc[-500:].max())
    assert abs(item['vpLo'][-1] - last_lo) < 1e-6
    assert abs(item['vpHi'][-1] - last_hi) < 1e-6
    # 120 根窗口明显更窄（确认不是旧行为 ✗）
    assert last_hi - last_lo > float(frame['high'].iloc[-120:].max()
                                     - frame['low'].iloc[-120:].min())
    # 每根都有档区（长度 = 矩阵行数），且升序 ✓
    assert len(item['vpLo']) == rows and len(item['vpHi']) == rows
    assert item['vpLo'][-1] < item['vpHi'][-1]


def test_vp_peak_price_matches_volume_window():
    """按 `vpLo/vpHi` 还原的峰值价格要落在最近成交价区间里 ✓"""
    from minibt import LocalDatas
    from minibt.desk import personal, strategy_overlay as so

    path = ROOT / 'tutorials' / 'basic' / 'vp.py'
    if not path.is_file():
        pytest.skip('缺少 tutorials/basic/vp.py')
    module = personal._import_file(str(path))
    classes = [cls for cls in so.classes_of(module)['strategy']
               if cls.__name__ == 'VPMode1']
    if not classes:
        pytest.skip('vp.py 里没有 VPMode1')
    frame = LocalDatas.test.kline.pandas_object.tail(600).reset_index(drop=True)
    result = so.run_overlay(frame, classes[0], 'test', 60, replay=True,
                            frames=[('test', frame)])
    items = result.get('items') or []
    assert items, result.get('error')
    row = items[0]
    values = np.asarray(row['vpMatrix'][-1], dtype=float)
    lo, hi = row['vpLo'][-1], row['vpHi'][-1]
    step = (hi - lo) / len(values)
    peak_price = lo + (int(values.argmax()) + 0.5) * step
    tail = frame['close'].iloc[-100:]
    # 峰值价格落在最近 100 根的成交价区间（留 2 档余量 ✓）
    assert float(tail.min()) - 2 * step <= peak_price <= float(tail.max()) + 2 * step


def test_table_follows_mouse_on_every_cell():
    """十字线按**每格**订阅（表格在格 2 / 格 3 也要跟随 ✓）"""
    page = _read(DESK_TS / 'local-chart-page.ts')
    # ★ 记的是**订阅的 chart 实例**（不是布尔）：切布局 / 换合约会重建格子，
    #   布尔标记会让人一直订阅已经销毁的旧图表 → 十字线永不触发 ✗
    assert 'private readonly crosshairBoundCells: unknown[] = [];' in page
    assert 'private _ensureCrosshair(cell = 0): void {' in page
    assert 'if (this.crosshairBoundCells[cell] === chart) return;' in page
    assert 'this.crosshairBoundCells[cell] = chart;' in page
    assert 'this._syncTableMouse(stamp, cell);' in page
    assert 'this._syncTableMouse(null, cell);' in page
    assert 'private _syncTableMouse(time: number | null, cell = 0): void {' in page
    assert 'private _syncTableIndex(index: number | null, force = false,' in page
    # 每格渲染指标时都要订阅一次 ✓
    assert 'this._ensureCrosshair(cell);      // ★ 表格跟随鼠标依赖它' in page
    assert 'this._ensureCrosshair(cell);\n        overlay.resize();' in page


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))


# ---------------------------------------------------------------- 实时图表
def test_realtime_vp_uses_price_bars_500():
    """实时图表（`minibt.strategy.realtime`）的 VP 档区也要用 500 根窗口 ✓

    用户 2026-11-03 反馈：本地图表修好后要检查实时图表是不是同样的问题 ——
    `_vp_spec()` 以前把 `vpstyle.price_bars=None` 原样传下去 →
    `_vp_price_bands(frame, None, nb)` 退回**整段数据**的 low/high，
    而矩阵按 500 根分档 → 分布被压成一条、位置也不对 ✗
    """
    from minibt.strategy import realtime as rt

    rows = 900
    close = np.concatenate([
        np.linspace(100, 140, rows - 120),
        np.linspace(130, 132, 120),
    ])
    frame = pd.DataFrame({'low': close - 1, 'high': close + 1, 'close': close,
                          'time': np.arange(rows)})
    lo, hi = rt._vp_price_bands(frame, 500, 4)
    assert abs(float(lo[-1]) - float(frame['low'].iloc[-500:].min())) < 1e-9
    assert abs(float(hi[-1]) - float(frame['high'].iloc[-500:].max())) < 1e-9
    # 整段（None）明显更宽 → 旧行为会把分布压扁 ✓
    lo_full, hi_full = rt._vp_price_bands(frame, None, 4)
    assert float(hi_full[-1]) - float(lo_full[-1]) > float(hi[-1]) - float(lo[-1])
    # `_vp_spec` 默认给 500（不是 None）✓
    indicator = pd.DataFrame(np.zeros((rows, 4)),
                             columns=['vp0', 'vp1', 'vp2', 'vp3'])
    spec = rt._vp_spec(None, 'k', indicator, True, {}, {})
    assert spec.vp_price_bars == 500
    # 用户显式写 0 = 整段（保持原语义 ✓）
    spec0 = rt._vp_spec(None, 'k', indicator, True, {}, {'vpstyle': {'price_bars': 0}})
    assert not spec0.vp_price_bars


def test_editor_reveal_file_in_explorer():
    """编辑器切标签时：资源管理器展开上层目录 + 高亮 + 滚到可见区 ✓"""
    panel = _read(DESK_TS / 'editor-panel.ts')
    assert 'revealInExplorer(path: string): void {' in panel
    assert 'private pendingReveal = ' in panel
    # 逐级展开 + 懒加载（等 `explorer_list` 回来再继续）✓
    assert 'this.pendingReveal = path;' in panel
    assert "this.options.onCommand('explorer_list', { path: current });" in panel
    # 切标签时调用 + 节点带 data-path（定位用）✓
    assert 'this.revealInExplorer(path);' in panel
    assert 'row.dataset.path = item.path;' in panel
    assert "row.scrollIntoView({ block: 'nearest' });" in panel
    assert "row.classList.add('reveal');" in panel
    # 目录内容回来后继续定位 ✓
    assert 'this.revealInExplorer(pending);' in panel
    # 定位时短暂高亮的样式 ✓
    assert '.desk-editor-node.reveal {' in panel


# ---------------------------------------------------------------- 实时图表跟随
def test_table_hover_idle_and_latest_bar_rules():
    """表格跟随的三条规则（用户要求 2026-11-03 ✓）

    1. 鼠标在**历史**K 线上 → 显示历史值（**移动**时一直跟随）；
    2. 鼠标**停住不动**（无论十字线在哪）→ 2 秒后回实时；
    3. 鼠标在**最新那根** / 右侧空白 → 一直用**最新**数据。
    """
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (DESK_TS / name).read_text(encoding='utf-8')
        assert 'const TABLE_HOVER_IDLE_MS = 2000;' in page
        assert 'private _markTableHover(cell: number): void {' in page
        idle = page.split('timers[cell] = window.setTimeout(', 1)[1][:400]
        assert 'this._syncTableIndex(null, true, cell);' in idle
        assert 'this.vpOverlays[cell]?.onCrosshair(null);' in idle
        # 最新那根 → 实时 ✓
        assert 'if (index !== null && total > 0 && index >= total - 1) {' in page
        # 右侧空白（`time` 不是数字）→ 实时 ✓
        cross = page.split('if (!Number.isFinite(stamp)) {', 1)[1][:400]
        assert 'this._syncTableIndex(null, true, cell);' in cross
        # VP 也一起回最新（用户要求：实时图表 VP 同表格逻辑 ✓）
        assert 'overlay?.onCrosshair(null);' in cross
        # 最新那根：VP 也回最新 ✓
        latest = page.split('if (index !== null && total > 0', 1)[1][:220]
        assert 'this.vpOverlays[cell]?.onCrosshair(null);' in latest
        # 历史 → 跟随 + 起计时 ✓
        assert 'this._syncTableIndex(target, true, cell);' in page
        assert 'this._markTableHover(cell);' in page
        # ★ 只有 VP（没有表格）也要起计时：十字线回调里单独起一次 ✓
        cross_body = page.split('subscribeCrosshairMove((param) => {', 1)[1]
        cross_body = cross_body[:1600]
        assert 'this._markTableHover(cell);' in cross_body



def test_hover_uses_nearest_row_and_keeps_follow():
    """实时图表：十字线 `param.time` 落在两根之间也要跟随（不能回"最新"）✓

    用户 2026-11-03 实测：实时图表的 VP / 表格只显示最新数据，不跟随鼠标。
    根因两处：
    ① 页面把 `param.time` 为空（两根之间 / 空白）当成"鼠标离开" → 回落最新；
    ② `VpOverlay._search()` 只认**精确命中**，找不到就 null → 回落最新。
    """
    vp = (DESK_TS / 'vp-overlay.ts').read_text(encoding='utf-8')
    body = vp.split('private _search(', 1)[1][:1600]
    assert 'let nearest = 0;' in body
    assert 'const distance = Math.abs(value - time);' in body
    assert 'return nearest;' in body
    assert 'if (time < first || time > last) return null;' in body
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (DESK_TS / name).read_text(encoding='utf-8')
        cross = page.split('subscribeCrosshairMove((param) => {', 1)[1][:900]
        # 只有**没有 point**（离开绘图区）才回落最新 ✓；
        # `time` 不是数字（右侧空白）→ 也用**最新**数据（不是保留旧跟随）✓
        assert 'if (!param || !param.point)' in cross
        assert 'if (!Number.isFinite(stamp)) {' in cross
        # 新 K 线 → 先回"最新"（实时更新优先），鼠标再动才跟随 ✓
        assert 'const previous = this.vpBarTime[cell] || 0;' in page
        assert 'overlay.onCrosshair(null);' in page
        assert 'this._syncTableIndex(null, true, cell);' in page


# ------------------------------------------------------- 表格定位（二级报价）
def test_indicator_table_lives_inside_chart_area():
    """指标表格挂在**图表区**（不含右侧二级报价），报价打开也不会被遮挡 ✓

    用户 2026-11-03 实测：二级报价一出现，右上角的指标表格跑到报价下面
    （甚至跑到图表外面）—— 表格是 `position: absolute`，以前挂在
    `.desk-ind-host` / 页面级容器上，定位基准一路找到整个页面 ✗
    """
    layer = (DESK_TS / 'indicator.ts').read_text(encoding='utf-8')
    # 定位容器：格内 `.desk-cell-main` → 页面级 `.desk-chart-host` ✓
    assert 'private _tableHost(): HTMLElement | null {' in layer
    assert "probe.closest?.('.desk-chart-cell')" in layer
    assert "cell?.querySelector?.('.desk-cell-main')" in layer
    assert "cell?.querySelector?.('.desk-chart-host')" in layer
    assert 'if (node.parentElement !== cell) cell.appendChild(node);' in layer
    # 拖动限制在图表区内（不能拖到报价窗口 / 图表外面）✓
    assert 'const maxX = host ? Math.max(0, host.width - rect.width) : 1e9;' in layer
    assert 'Math.min(maxX,' in layer and 'Math.min(maxY,' in layer
    # CSS：`.desk-cell-main` 是定位容器 ✓
    css = (DESK_TS / 'desk.css').read_text(encoding='utf-8')
    block = css.split('.desk-cell-main {', 1)[1].split('}', 1)[0]
    assert 'position: relative;' in block

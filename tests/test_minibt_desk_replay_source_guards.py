"""回放指标 / 工具条的源码闸门（v1.3.9-20）。

前端这两处无法在 pytest 里跑起来（ChartPage 依赖 lightweight-charts），
所以用源码断言盯住关键实现 ✓
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / 'jslib' / 'src' / 'desk'


def test_set_indicators_routes_by_cell_while_replaying():
    page = (DESK / 'chart-page.ts').read_text(encoding='utf-8')
    body = page.split('setIndicators(payload: IndicatorPayload)', 1)[1]
    body = body.split('setCellIndicators(0, payload);', 1)[0]
    # 回放分支必须按 cell 找目标，不能一律写第 1 格 ✓
    assert 'const cell = Math.max(0, Number(payload.cell ?? 0) || 0);' in body
    assert 'const target = cell === 0 ? null : this.replayCells[cell];' in body
    assert 'target.indicators = payload.items || [];' in body


def test_set_cell_indicators_dedupes_items():
    page = (DESK / 'chart-page.ts').read_text(encoding='utf-8')
    assert "from './indicator-key'" in page
    body = page.split('setCellIndicators(index: number', 1)[1]
    body = body.split('this.cellItems[cell] = items;', 1)[0]
    assert 'items = dedupeIndicatorItems(items);' in body
    # 回放每拍也先去重再铺 ✓
    replay = page.split('private _applyReplayIndicators(', 1)[1]
    replay = replay.split('this.setCellIndicators(index,', 1)[0]
    assert 'dedupeIndicatorItems(' in replay


def test_replay_bar_only_has_time_range():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = (DESK / name).read_text(encoding='utf-8')
        body = page.split('private _ensureReplayBar(', 1)[1]
        body = body.split('// ② ', 1)[0]
        assert "selectLabel.textContent = '选择K线时段';" in body
        assert "label: '选择时间段'" in body
        # 「选择合约」只剩注释里的历史说明，不能出现在菜单里 ✓
        assert "label: '选择合约'" not in body
        assert 'const contracts = ' not in body   # 选合约那段代码已删 ✓


def test_indicator_key_module_exists():
    module = (DESK / 'indicator-key.ts').read_text(encoding='utf-8')
    assert 'export function normalizeIndicatorKey(' in module
    assert 'export function dedupeIndicatorItems<' in module

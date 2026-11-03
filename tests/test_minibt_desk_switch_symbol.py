"""「＋ → 实时图表」用键盘精灵切合约 ✓（2026-11-03 用户实测）

两个问题：
1. 从「＋ → 实时图表」打开的看盘页，切合约后 **交易账户交易页 / 画线键**
   还挂在旧合约上（`_renameChart()` 只调了 `page.setSymbol()`，没换格 1）；
2. 初次切合约**有时只有 2 根 K 线**（`_on_switch_symbol()` 没按
   `data_length()` 取数、也没记 K 线状态 → `_refresh_tabs` 不再补全 ✗）。
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK_TS = ROOT / 'jslib' / 'src' / 'desk'

FRAME = None


def _frame():
    global FRAME
    if FRAME is None:
        from minibt import LocalDatas
        FRAME = LocalDatas.test.kline.pandas_object.copy()
    return FRAME


class _FakeFeed:
    kind = 'futures'
    name = 'fake'
    bars = 240          # 首次返回多少根（模拟天勤占位表可能只有 2 根 ✓）

    def available(self):
        return True

    def klines(self, symbol, cycle, length):
        frame = _frame()
        want = int(length or 0)
        if self.bars:
            want = min(want, self.bars)
        frame = frame.tail(max(2, want)).reset_index(drop=True).copy()
        frame['datetime'] = pd.to_datetime(frame['datetime'])
        return frame

    def name_of(self, symbol):
        return f'{symbol} 名称'

    def quotes(self, *args, **kwargs):
        return []


@pytest.fixture()
def desk(monkeypatch, tmp_path):
    import minibt.desk.local_data as ld

    monkeypatch.setattr(ld, 'STATE_FILE', str(tmp_path / 'local.json'))
    from minibt.desk import app as desk_app
    from minibt.desk.app import Desk

    feed = _FakeFeed()
    monkeypatch.setattr(desk_app, 'pick_feed', lambda feeds, symbol: feed)
    instance = Desk(offline=True)
    instance.sent = []
    instance.sender = instance.sent.append
    instance._booted = True
    instance.log_to_stdout = False
    instance.log_to_ui = False
    instance.feeds = [feed]
    instance.tabs['SHFE.rb2601'] = {'cycle': 60, 'loaded_len': instance.data_length()}
    return instance


def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def test_switch_symbol_fills_data_length_and_state(desk):
    """切合约：长度用 `data_length()`、并记下 K 线状态（`_refresh_tabs` 才会补 ✓）"""
    feed = desk.feeds[0]
    feed.bars = 0                       # 先当作正常返回
    desk._on_switch_symbol({'from': 'SHFE.rb2601', 'to': 'DCE.l2609',
                            'name': '塑料', 'cell': 0, 'multi': False,
                            'cells': ['SHFE.rb2601']})
    info = desk.tabs['DCE.l2609']
    kline = [row for row in _patches(desk) if row.get('type') == 'kline'][-1]
    bars = kline.get('bars') or []
    assert len(bars) == int(info.get('loaded_len') or 0)
    assert len(bars) >= int(desk.data_length() or 0)
    # ★ 状态记好了 → `_refresh_tabs` 能判断"占位表 → 需要全量补" ✓
    assert info['_kline_bars_len'] == len(bars)
    assert info['_kline_time'] == int(bars[-1]['time'])
    assert info['_kline_close'] == float(bars[-1]['close'])
    switch = [row for row in _patches(desk)
              if row.get('type') == 'switch_symbol'][-1]
    assert switch['old'] == 'SHFE.rb2601' and switch['new'] == 'DCE.l2609'


def test_switch_symbol_placeholder_bars_are_noted(desk):
    """天勤刚订阅返回 2 根占位表：也要记状态（否则永远停 2 根 ✗）"""
    feed = desk.feeds[0]
    feed.bars = 2
    desk._on_switch_symbol({'from': 'SHFE.rb2601', 'to': 'CZCE.MA2601',
                            'name': '甲醇', 'cell': 0, 'multi': False,
                            'cells': ['SHFE.rb2601']})
    info = desk.tabs['CZCE.MA2601']
    kline = [row for row in _patches(desk) if row.get('type') == 'kline'][-1]
    assert len(kline.get('bars') or []) == 2
    # 记的是**有数据的根数**（2）→ 下次真数据来了就会全量替换 ✓
    assert info['_kline_bars_len'] == 2
    assert info['_kline_time'] == int(kline['bars'][-1]['time'])


def test_frontend_rename_switches_cell_and_label():
    """前端 `_renameChart()`：格 1（交易标的 / 画线键）+ 标签 baseLabel 一起换 ✓"""
    app = (DESK_TS / 'app.ts').read_text(encoding='utf-8')
    body = app.split('private _renameChart(', 1)[1][:2600]
    assert 'page.setSymbol(newSymbol, name);' in body
    assert 'page.setCellSymbol(0, newSymbol, name);' in body
    assert 'tab.baseLabel = newSymbol;' in body
    # 格子符号（`cells`）也随之更新（`setCellSymbol` 里 ✓）
    page = (DESK_TS / 'chart-page.ts').read_text(encoding='utf-8')
    cell = page.split('setCellSymbol(cell: number', 1)[1][:2200]
    assert 'this.cellSymbols[index] = symbol;' in cell
    assert 'this.setTradeSymbol(symbol);' in cell


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

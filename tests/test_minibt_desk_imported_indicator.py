"""文件里「导入」的指标类也要能加到图表（2026-11-02 用户实测）

`tutorials/basic/btplot.py` 写的是：

    from minibt import *
    from minibt.indicators.tradingview import UT_Bot_Alerts
    LocalDatas.test.kline.tradingview.UT_Bot_Alerts().btplot()

指标是在 `__main__` 里**现算**的，文件里**没有定义**任何指标类 / 函数，
所以 desk 的「加到图表」按文件扫描找不到 → 只提示「没有可用的指标」✗。

现在：扫描不到时再认「**从 `minibt.indicators` 导入**、且指标目录里有的
指标类」（名字 → `tv:<类名>`），直接加到图表；一个都认不到时提示里给出
可操作建议（`btplot(gui="desk")` / 在「指标」面板里选）。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

_BTP_FILE = '''# 和 tutorials/basic/btplot.py 一样的写法
from minibt import *
from minibt.indicators.tradingview import UT_Bot_Alerts  # noqa: F401

if __name__ == "__main__":
    LocalDatas.test.kline.tradingview.UT_Bot_Alerts().btplot()
'''

_PLAIN_FILE = '''from minibt import *

if __name__ == "__main__":
    print("只有一句 print，没有任何指标")
'''


def _import_source(tmp_path, source: str, name: str = 'demo_mod'):
    path = tmp_path / f'{name}.py'
    path.write_text(source, encoding='utf-8')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


class _Desk:
    def __init__(self):
        self.patches = []

    def push(self, patch):
        self.patches.append(patch)


def _patches(desk, kind=None):
    return [item for item in desk.patches
            if kind is None or item.get('type') == kind]


# ------------------------------------------------------- 导入的指标 → 目录 key
def test_imported_indicator_entries_maps_tradingview_classes(tmp_path):
    from minibt.desk.app import imported_indicator_entries

    module, _ = _import_source(tmp_path, _BTP_FILE)
    entries = imported_indicator_entries(module)
    assert entries == [{'name': 'UT_Bot_Alerts', 'key': 'tv:UT_Bot_Alerts'}]


def test_imported_indicator_entries_ignores_non_indicators(tmp_path):
    from minibt.desk.app import imported_indicator_entries

    module, _ = _import_source(tmp_path, _PLAIN_FILE)
    # `from minibt import *` 带来一堆类（Bt / Strategy / KLine…）但都不是指标 ✓
    assert imported_indicator_entries(module) == []
    assert imported_indicator_entries(None) == []


# --------------------------------------------------------- 本地图表：真的加上
def _desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, personal, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE',
                        str(tmp_path / 'personal.json'))
    desk = appmod.Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk._strategy_sync = True
    desk.log_to_stdout = False
    desk.log_to_ui = False
    desk._active_local_page = 'local:1'
    return desk


def _payloads(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def test_local_chart_adds_imported_indicator(tmp_path, monkeypatch):
    """扫描不到定义时，按「导入的指标类」把 `tv:<类名>` 加到图表 ✓

    ⚠ 这里把 `_on_local_add_indicator` 换成记录器：只验证**路由**（key 对不对），
    不去真算 TradingView 指标 —— 真算会拉起整套 KLine / Cython 环境，
    既慢又会在 pytest 里留下全局副作用（实测会让后面的用例莫名失败 ✗）。
    """
    desk = _desk(tmp_path, monkeypatch)
    path = tmp_path / 'btplot_like.py'
    path.write_text(_BTP_FILE, encoding='utf-8')
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})

    calls: list = []
    monkeypatch.setattr(
        desk, '_on_local_add_indicator',
        lambda payload: calls.append(dict(payload)) or True)
    desk._on_editor_add_indicator({'path': str(path), 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1'})
    desk.flush_outbox()
    keys = [item.get('key') for item in calls]
    assert 'tv:UT_Bot_Alerts' in keys, keys
    payload = calls[0]
    assert payload['symbol'] == 'test' and payload['cell'] == 0
    # 成功提示（不是「没有可用的指标」）
    toasts = [item for item in _payloads(desk) if item.get('type') == 'toast']
    assert any('UT_Bot_Alerts' in str(item.get('text') or '')
               for item in toasts), toasts
    assert not any('没有可用的指标' in str(item.get('text') or '')
                   for item in toasts)
    # 目录里确实有这个 key（说明映射是对的 ✓）
    from minibt.desk import indicator_catalog as _cat
    assert any(str(item.get('key')) == 'tv:UT_Bot_Alerts'
               for item in _cat.catalog())


def test_message_hints_when_nothing_can_be_added(tmp_path, monkeypatch):
    desk = _desk(tmp_path, monkeypatch)
    path = tmp_path / 'plain.py'
    path.write_text(_PLAIN_FILE, encoding='utf-8')
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    desk._on_editor_add_indicator({'path': str(path), 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1'})
    desk.flush_outbox()
    toasts = [item for item in _payloads(desk) if item.get('type') == 'toast']
    text = ' '.join(str(item.get('text') or '') for item in toasts)
    assert '没有可用的指标' in text
    assert 'btplot(gui="desk")' in text          # 给出可操作建议 ✓
    assert '指标」面板' in text


# --------------------------------------------------------------- 源码护栏
def test_both_entry_points_use_the_imported_fallback():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'def imported_indicator_entries(' in app
    # 本地图表 / 实时图表两条路径都要兜底 ✓
    assert app.count('imported_indicator_entries(module)') >= 2
    # 只认从 minibt.indicators 导入的类
    assert "origin.startswith('minibt.indicators')" in app


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

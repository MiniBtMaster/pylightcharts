"""一个文件里有多个策略 → 弹窗让用户选（2026-11-02 用户要求）

`tutorials/basic/live_trading_modes.py` 里有 `CCIStrategy` + `CMOStrategy` 两个策略，
以前「加到图表」**默认取第一个**（`_pick_strategy_class` 的兜底）→ 用户没法选 ✗。

现在：文件里有 ≥2 个 Strategy 且用户没指定 → 后端推一条 `strategy_choice`
补丁（带 `path` / `local` / `symbol` / `cell` / `page` / 候选列表），前端弹窗列出
类名 + docstring 首行；用户点一个 → 用同一个 `editor_add_indicator` 命令补上
`strategy: 类名` 重发 → 后端 `_pick_strategy_class()` 按名字取 ✓。
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from minibt.desk import personal as pi

ROOT = pathlib.Path(__file__).resolve().parents[1]

_MULTI = '''
from minibt import BtIndicator, Strategy, LocalDatas


class _Ma(BtIndicator):
    lines = ('ma',)
    params = dict(length=10)
    overlap = True

    def next(self):
        return self.close.sma(self.params.length)


class AlphaStrategy(Strategy):
    """先写一个：Alpha（短均线）"""

    params = dict(length=10)

    def __init__(self):
        self.data = self.get_kline(LocalDatas.test)
        self.ma = self.data.close.sma(self.params.length)

    def next(self):
        pass


class BetaStrategy(Strategy):
    """第二个：Beta（长均线）"""

    params = dict(length=30)

    def __init__(self):
        self.data = self.get_kline(LocalDatas.test)
        self.ma = self.data.close.sma(self.params.length)

    def next(self):
        pass
'''


@pytest.fixture()
def make_desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    monkeypatch.setattr(pi, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(pi, 'CONFIG_FILE', str(tmp_path / 'personal.json'))

    def factory():
        desk = appmod.Desk(offline=True)
        desk.sent = []
        desk.sender = desk.sent.append
        desk._booted = True
        desk._strategy_sync = True
        desk.log_to_stdout = False
        desk.log_to_ui = False
        desk._active_local_page = 'local:1'
        return desk
    return factory


def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


def _wait_strategy(desk, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if desk._local_strategies.get('local:1'):
            break
        time.sleep(0.1)
    time.sleep(0.3)
    desk.flush_outbox()


def _multi_file(tmp_path) -> str:
    folder = tmp_path / 'personal' / 'strategies'
    folder.mkdir(parents=True)
    path = folder / 'multi_strategy.py'
    path.write_text(_MULTI, encoding='utf-8')
    return str(path)


# ------------------------------------------------------------- 候选列表
def test_strategy_choices_reads_names_and_docs():
    from minibt.desk.app import strategy_choices

    class A:
        """第一个策略（doc）"""

    class B:
        pass

    items = strategy_choices([A, B])
    assert items == [{'name': 'A', 'doc': '第一个策略（doc）'},
                     {'name': 'B', 'doc': ''}]
    assert strategy_choices([]) == []


# ------------------------------------------------- 本地图表：先弹窗，不加载
def test_local_chart_asks_before_loading(make_desk, tmp_path):
    desk = make_desk()
    path = _multi_file(tmp_path)
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})

    desk._on_editor_add_indicator({'path': path, 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1'})
    desk.flush_outbox()
    choices = [item for item in _patches(desk)
               if item.get('type') == 'strategy_choice']
    assert choices, '没有弹选择窗'
    choice = choices[-1]
    assert choice['local'] is True and choice['mode'] == 'local'
    assert choice['path'] == path
    assert choice['symbol'] == 'test' and choice['cell'] == 0
    assert choice['page'] == 'local:1'
    assert [item['name'] for item in choice['strategies']] == [
        'AlphaStrategy', 'BetaStrategy']
    assert choice['strategies'][1]['doc'].startswith('第二个')
    # ★ 还没加载任何策略（等用户选 ✓）
    assert desk._local_strategies.get('local:1') is None


def test_local_chart_loads_the_chosen_strategy(make_desk, tmp_path):
    desk = make_desk()
    path = _multi_file(tmp_path)
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    desk._on_editor_add_indicator({'path': path, 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1'})
    desk.flush_outbox()
    # 用户点「BetaStrategy」
    desk._on_editor_add_indicator({'path': path, 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1',
                                   'strategy': 'BetaStrategy'})
    _wait_strategy(desk)
    record = desk._local_strategies.get('local:1') or {}
    assert record.get('name') == 'BetaStrategy', record.get('name')


def test_single_strategy_file_still_loads_directly(make_desk, tmp_path):
    """只有一个策略的文件：不再弹窗，直接加载（行为不变 ✓）"""
    folder = tmp_path / 'personal' / 'strategies'
    folder.mkdir(parents=True)
    path = folder / 'one_strategy.py'
    path.write_text(_MULTI.split('class BetaStrategy')[0], encoding='utf-8')
    desk = make_desk()
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    desk._on_editor_add_indicator({'path': str(path), 'local': True,
                                   'symbol': 'test', 'cell': 0,
                                   'page': 'local:1'})
    _wait_strategy(desk)
    choices = [item for item in _patches(desk)
               if item.get('type') == 'strategy_choice']
    assert not choices
    assert (desk._local_strategies.get('local:1') or {}).get('name') \
        == 'AlphaStrategy'


# ---------------------------------------------------- 实时图表也要先弹窗
def test_realtime_chart_asks_before_loading(make_desk, tmp_path):
    desk = make_desk()
    path = _multi_file(tmp_path)
    desk.tabs['SHFE.demo01'] = {'cycle': 60, 'indicators': []}
    desk._on_editor_add_indicator({'path': path, 'symbol': 'SHFE.demo01'})
    desk.flush_outbox()
    choices = [item for item in _patches(desk)
               if item.get('type') == 'strategy_choice']
    assert choices, '实时图表没有弹选择窗'
    choice = choices[-1]
    assert choice['mode'] == 'realtime' and choice['local'] is False
    assert choice['symbol'] == 'SHFE.demo01'
    assert [item['name'] for item in choice['strategies']] == [
        'AlphaStrategy', 'BetaStrategy']
    # 没有真的去建 tab 策略 ✓
    assert not (desk.tabs['SHFE.demo01'].get('strategy') or {}).get('name')


# --------------------------------------------------------- 前端弹窗接线
def test_frontend_dialog_sends_the_chosen_name():
    app = (ROOT / 'jslib' / 'src' / 'desk' / 'app.ts').read_text(
        encoding='utf-8')
    assert "case 'strategy_choice':" in app
    assert 'showStrategyChoice(' in app
    block = app.split('showStrategyChoice(info: Record<string, any>): void {',
                      1)[1]
    block = block.split('/** 模态提醒弹窗', 1)[0]
    assert "this.send('editor_add_indicator'" in block
    assert 'strategy: name' in block                 # 带上用户选的类名 ✓
    assert 'desk-choice-item' in block
    assert '取消' in block
    css = (ROOT / 'jslib' / 'src' / 'desk' / 'login-dialog.ts').read_text(
        encoding='utf-8')
    for selector in ('.desk-choice-box', '.desk-choice-item',
                     '.desk-choice-tip'):
        assert selector in css, selector


def test_backend_pushes_choice_for_realtime_too():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert "def strategy_choices(" in app
    # 本地 / 实时两个入口都要有「多策略先问」✓
    assert app.count("'type': 'strategy_choice'") >= 2
    assert app.count("'strategies': strategy_choices(strategies)") >= 2


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))

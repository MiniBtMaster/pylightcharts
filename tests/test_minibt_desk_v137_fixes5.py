"""v1.3.7-71：资讯 ↔ 图表联动 / 自选·持仓筛选 / AI 摘要按天缓存 / F10。

用户 2026-11-08：
* 点资讯 → 跳到图表对应时间并高亮那根 K 线；
* 资讯按自选 / 持仓筛选；
* AI 摘要同一天复用（不重复烧 token）；
* **F10** = 当前图表的标的资讯页（A 股软件习惯）。
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from minibt.desk import tools, user_prefs
from minibt.desk.app import Desk
from minibt.desk.info import cache

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, 'DB_FILE', str(tmp_path / 'info.db'))
    monkeypatch.setattr(tools, 'AUDIT_FILE', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        str(tmp_path / 'prefs.json'))
    user_prefs.set_setting(tools.SETTING_ALLOW, True)
    yield


# ------------------------------------------------------------ ① 资讯 → 图表
def test_chart_focus_time_and_highlight():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(name)
        assert 'focusTime(seconds: number, label = \'\'): void {' in page, name
        assert 'setVisibleLogicalRange' in page, name
        assert 'desk-news-pin' in page, name       # 高亮徽标 ✓
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-news-pin' in css


def test_news_click_jumps_to_chart():
    """v1.3.7-72：左键不动作；双击开原文；右键菜单「打开原文 / 打开图表」✓"""
    page = _read('info-page.ts')
    assert '_showNewsMenu(' in page
    assert "node.addEventListener('dblclick'" in page
    assert "onCommand('open_url'" in page
    assert "onCommand('news_focus'" in page
    assert 'private _epochOf(' in page
    assert 'private _symbolOf(' in page
    # 标的资讯页 Top Stories：双击开原文 + 右键菜单
    symbol = _read('symbol-info.ts')
    assert 'onItemDoubleClick:' in symbol
    assert 'onItemContextMenu:' in symbol
    assert "onCommand('news_focus'" in symbol
    # app.ts：带 symbol 时**先打开那一页**再跳时间
    app = _read('app.ts')
    assert "cmd === 'news_focus'" in app
    assert 'const id = this.openChart(symbol);' in app
    assert 'jump(6);' in app


# ------------------------------------------------------------ ② 自选 / 持仓筛选
def test_related_filter_backend_and_frontend():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _on_info_related(', 1)[1].split(
        '    #: AI 摘要缓存文件', 1)[0]
    assert "getattr(self, 'watchlist'" in block
    assert "view.tables(limit=80)" in block       # 持仓里的合约 ✓
    assert "self._name_of(symbol)" in block        # 名称也作为关键词 ✓
    page = _read('info-page.ts')
    assert '只看自选/持仓' in page
    assert 'private _relatedRows(' in page
    assert "onCommand('info_related', {})" in page


# ------------------------------------------------------------ ③ AI 摘要按天缓存
def test_ai_summary_is_cached_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = Desk(offline=True)
    desk._booted = True
    desk.SUMMARY_FILE = str(tmp_path / 'summary.json')
    # 造一条今天的缓存（指向一个存在的会话）
    from minibt.desk import agent
    monkeypatch.setattr(agent, 'SESSIONS_DIR', str(tmp_path / 'sessions'))

    def _ensure() -> str:
        folder = str(tmp_path / 'sessions')
        pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
        return folder
    monkeypatch.setattr(agent, '_ensure_dir', _ensure)
    session = agent.create_session(str(tmp_path), title='资讯摘要 测试')
    agent.save_session({**session, 'messages': [
        {'role': 'user', 'content': '总结一下'},
        {'role': 'assistant', 'content': '今天的要点：…'},
    ]})
    day = desk._summary_day()
    pathlib.Path(desk.SUMMARY_FILE).write_text(json.dumps({
        day: {'session_id': session['id'], 'at': time.time(), 'count': 3},
    }, ensure_ascii=False), encoding='utf-8')

    pushed = []
    desk.push = pushed.append
    desk._on_ai_summary({})
    # 会先 push 一条日志，再 push 摘要补丁 → 找 type=ai_summary 的那条 ✓
    data = [item for item in pushed if item.get('type') == 'ai_summary'][-1]
    assert data['type'] == 'ai_summary'
    assert data['cached'] is True
    assert data['session_id'] == session['id']
    assert '今天的要点' in data['text']
    # 前端：按钮走后端（按天缓存），Shift 点才重新生成
    page = _read('info-page.ts')
    assert "onCommand('ai_summary'" in page
    assert 'regenerate: useCache === false' in page
    app = _read('app.ts')
    assert "case 'ai_summary'" in app
    assert 'openPiSession(sessionId)' in app


# ------------------------------------------------------------ ④ F10
def test_f10_opens_symbol_info():
    app = _read('app.ts')
    block = app.split("if (event.key === 'F10')", 1)[1].split('return;', 1)[0]
    assert 'event.preventDefault();' in block
    assert 'this._openSymbolInfoFromChart();' in block
    # 和 F1（悬浮窗）不冲突
    assert "if (event.key === 'F1')" in app
    menu = _read('chart-context-menu.ts')
    assert "'资讯 / 财务…（F10）'" in menu

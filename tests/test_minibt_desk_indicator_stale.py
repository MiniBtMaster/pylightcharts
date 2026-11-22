"""v1.3.7-109：格 1 残留的重复指标（大写 tqta_MACD）删不掉 / 菜单看不到。"""
from __future__ import annotations

import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs
from minibt.desk.app import _same_indicator_key

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
CHART = (JSLIB / 'chart-page.ts').read_text(encoding='utf-8')
LAYER = (JSLIB / 'indicator.ts').read_text(encoding='utf-8')
APP_PY = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.push = lambda patch: None
    return instance


# ------------------------------------------------------------ 后端匹配
def test_same_indicator_key_rules():
    assert _same_indicator_key('tqta_MACD', 'tqta_macd') is True
    assert _same_indicator_key('tqta_MACD:macd', 'tqta_MACD') is True
    assert _same_indicator_key('pta_macd:macdx', 'pta_MACD') is True
    assert _same_indicator_key('pta_macd', 'pta_ma') is False
    assert _same_indicator_key('', 'pta_macd') is False


def test_remove_matches_case_and_suffix(desk):
    desk.tabs['SHFE.ag2612'] = {
        'symbol': 'SHFE.ag2612',
        'indicators': [{'key': 'pta_ma', 'params': {}},
                       {'key': 'tqta_MACD', 'params': {}},
                       {'key': 'pta_macd:macdx', 'params': {}}],
        'layout': {'cells': []},
    }
    desk._on_remove_indicator({'symbol': 'SHFE.ag2612',
                               'key': 'tqta_macd', 'cell': 0})
    keys = [item['key'] for item in desk.tabs['SHFE.ag2612']['indicators']]
    assert 'tqta_MACD' not in keys
    # 带后缀的那条也能被基础 key 删掉 ✓
    desk._on_remove_indicator({'symbol': 'SHFE.ag2612',
                               'key': 'pta_macd', 'cell': 0})
    keys = [item['key'] for item in desk.tabs['SHFE.ag2612']['indicators']]
    assert keys == ['pta_ma']


def test_remove_other_cell_also_case_insensitive(desk):
    desk.tabs['SHFE.ag2612'] = {
        'symbol': 'SHFE.ag2612', 'indicators': [],
        'layout': {'cells': [
            {'symbol': 'SHFE.ag2612', 'indicators': []},
            {'symbol': 'SHFE.au2612',
             'indicators': [{'key': 'tqta_MACD'}, {'key': 'pta_ma'}]}]},
    }
    desk._on_remove_indicator({'symbol': 'SHFE.ag2612',
                               'key': 'tqta_MACD', 'cell': 1})
    cells = desk.tabs['SHFE.ag2612']['layout']['cells']
    assert [item['key'] for item in cells[1]['indicators']] == ['pta_ma']


# ------------------------------------------------------------ 前端清理
def test_backend_sends_pending_keys(desk):
    assert "'pending_keys'" in APP_PY
    assert 'payload[\'pending_keys\']' in APP_PY


def test_frontend_keeps_only_pending_keys():
    """pending 时只保留 items + pending_keys 的序列（别把已删的留下）✓"""
    assert 'pending_keys' in CHART
    assert 'pendingKeys.has(item.key)' in CHART
    assert 'const aliveKeys = new Set(items.map((item) => item.key));' in LAYER
    assert 'for (const key of pendingKeys) aliveKeys.add(key);' in LAYER
    assert 'keys.every((key) => !aliveKeys.has(key))' in LAYER


def test_remove_source_cleans_registry_even_if_not_in_items():
    assert 'removeSource(source: string): void {' in LAYER
    assert 'for (const [key, series] of [...this.overlaySeries])' in LAYER
    assert 'if (!hit(key)) continue;' in LAYER
    assert 'if (!handle.series.size) {' in LAYER

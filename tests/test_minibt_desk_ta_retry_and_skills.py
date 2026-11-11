"""v1.3.7-104：TA 首帧「数据不足」友好化 + 自动重算；skills.sh 搜索接口修正。"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
CHART = (JSLIB / 'chart-page.ts').read_text(encoding='utf-8')
LOCAL = (JSLIB / 'local-chart-page.ts').read_text(encoding='utf-8')
PI_PY = (ROOT / 'minibt' / 'desk' / 'pi.py').read_text(encoding='utf-8')
TA_PY = (ROOT / 'minibt' / 'desk' / 'ta.py').read_text(encoding='utf-8')
CAT = (ROOT / 'minibt' / 'desk' / 'indicator_catalog.py').read_text(
    encoding='utf-8')


def _frame(bars: int) -> pd.DataFrame:
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=bars, freq='min'),
        'open': np.linspace(100, 103, bars),
        'high': np.linspace(101, 104, bars),
        'low': np.linspace(99, 102, bars),
        'close': np.linspace(100, 103, bars),
        'volume': np.full(bars, 10.0)})


# ------------------------------------------------------------ TA 首帧
def test_short_data_note_is_friendly():
    """K 线不够时 note =「数据不足」，不再把 AssertionError 原文塞进去 ✓"""
    from minibt.desk import ta
    snap = ta.snapshot(_frame(6), rows=[{
        'key': 'pta_adx', 'group': 'trend',
        'signal': {'kind': 'compare', 'offset': -1, 'direction': 1}}])
    row = [r for group in snap['groups'] for r in group['rows']][0]
    assert row['note'] == '数据不足'
    assert 'AssertionError' not in row['note']
    assert row['signal'] == 0
    # 细节留在 error 字段（前端不显示，排查用 ✓）
    assert 'NoneType' in str(row.get('error') or '')
    assert snap['retry'] is True


def test_enough_data_has_no_retry():
    from minibt.desk import ta
    snap = ta.snapshot(_frame(200), rows=[{
        'key': 'pta_adx', 'group': 'trend',
        'signal': {'kind': 'compare', 'offset': -1, 'direction': 1}}])
    row = [r for group in snap['groups'] for r in group['rows']][0]
    assert row['note'] != '数据不足'
    assert snap['retry'] is False


def test_frontend_retries_when_needed():
    for text in (CHART, LOCAL):
        assert 'if (data.retry)' in text
        assert 'this.requestTaSignal(true)' in text
        assert 'requestTaSignal(force = false)' in text
        assert "if (!force && now - this.taAskedAt < 10000) return;" in text


def test_catalog_logs_data_shortage_once():
    assert '_note_once' in CAT
    assert '_NOTE_SEEN' in CAT
    assert '数据不足（K 线还不够）' in CAT


# ------------------------------------------------------------ 技能搜索
def test_skills_api_endpoint_is_search():
    assert "/api/search?" in PI_PY
    assert "/api/skills?" not in PI_PY


def test_skills_search_parses_new_shape(monkeypatch):
    from minibt.desk import pi

    payload = {'skills': [
        {'id': 'samber/dev-event-organizer-skills/event-vip-management',
         'source': 'samber/dev-event-organizer-skills',
         'skillId': 'event-vip-management',
         'name': 'event-vip-management', 'installs': 6588}]}
    monkeypatch.setattr(pi, '_fetch', lambda url, timeout=15.0: payload)
    out = pi.search_skills('minibt', limit=3)
    assert out['ok'] is True and len(out['items']) == 1
    item = out['items'][0]
    assert item['name'] == 'event-vip-management'
    assert item['package'] == 'samber/dev-event-organizer-skills'
    assert item['installs'] == '6588'
    assert item['url'].endswith('/skills/'
                                'samber/dev-event-organizer-skills/'
                                'event-vip-management')


def test_skills_search_http_error_is_reported(monkeypatch):
    import urllib.error
    from minibt.desk import pi

    def boom(url, timeout=15.0):
        raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)

    monkeypatch.setattr(pi, '_fetch', boom)
    out = pi.search_skills('x')
    assert out['ok'] is False and '404' in out['error']

"""图上事件圆点 → 每条事件**可点开来源网站**（v1.3.9-13）。

用户 2026-11-16：圆点事件的内容是从资讯中心引用过来的，希望点一下能打开
对应事件的来源网站。

实现：`info.symbol_events()` 给每条事件带上 `source` + `url`
（东财公告 → 该股票的公告列表页；期货日历 → 财经日历来源页），
前端卡片里带 url 的行变成可点（`open_url`）。
"""
from __future__ import annotations

import pytest

from minibt.desk.info import service


# ---------------------------------------------------------------- 链接拼装
def test_providers_code_from_various_symbols():
    assert service._providers_code('SH.600519') == '600519'
    assert service._providers_code('SZ.000001') == '000001'
    assert service._providers_code('600519') == '600519'
    assert service._providers_code('') == ''


# ------------------------------------------------------------ 股票公告事件
def test_stock_notice_events_carry_url(monkeypatch):
    monkeypatch.setattr(service.providers, 'is_stock', lambda s: True)
    monkeypatch.setattr(service, 'symbol_info', lambda *a, **k: {
        'notices': {'items': [
            {'date': '2026-11-10', 'title': '关于凝血酶时间检测的公告'},
        ]}})
    data = service.symbol_events('SH.600519')
    assert data['ok'] is True
    item = data['items'][0]
    assert item['kind'] == 'notice'
    assert item['source'].startswith('东方财富')
    assert item['url'].endswith('/notices/stock/600519.html'), item['url']


def test_stock_notice_without_code_has_no_url(monkeypatch):
    monkeypatch.setattr(service.providers, 'is_stock', lambda s: True)
    monkeypatch.setattr(service, 'symbol_info', lambda *a, **k: {
        'notices': {'items': [{'date': '2026-11-10', 'title': '公告'}]}})
    data = service.symbol_events('XX.????')      # 拼不出 6 位代码
    assert data['items'][0]['url'] == ''          # 不生造链接 ✓


# ------------------------------------------------------------ 期货日历事件
def test_variety_calendar_events_have_source_page(monkeypatch):
    monkeypatch.setattr(service.providers, 'is_stock', lambda s: False)
    monkeypatch.setattr(service.providers, 'variety_of', lambda s: 'pp')
    monkeypatch.setattr(service, 'symbol_info', lambda *a, **k: {
        'contract': {'items': [{'variety': '聚丙烯'}]}})
    monkeypatch.setattr(service.cache, 'load_calendar',
                        lambda days, limit=400: [{
                            'day': '2026-11-16', 'time': '09:00',
                            'event': '聚丙烯库存数据', 'importance': 2}])
    data = service.symbol_events('DCE.pp2701')
    item = data['items'][0]
    assert item['kind'] == 'variety'
    assert item['source'] == '财经日历（金十）'
    assert item['url'].startswith('https://rili.jin10.com')

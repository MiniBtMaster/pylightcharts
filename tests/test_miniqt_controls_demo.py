"""The '控件演示' page wires three independent controls into a grid.

Only the (Qt-free) mock helpers and class structure are checked; creating the
page builds real webviews, which needs a desktop window.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PyQt6')
demo = pytest.importorskip('miniqt.app.view.controls_demo_interface')


def test_demo_page_class_and_providers():
    assert hasattr(demo, 'ControlsDemoInterface')
    for method in ('_ticker_items', '_heat_items', '_market_groups'):
        assert callable(getattr(demo.ControlsDemoInterface, method, None))


def test_demo_page_uses_the_three_controls():
    from miniqt.app.windows import panel_controls as pc
    # the page module imported the three control classes
    assert demo.TickerControl is pc.TickerControl
    assert demo.HeatmapControl is pc.HeatmapControl
    assert demo.MarketDataControl is pc.MarketDataControl


def test_jitter_keeps_shape_and_changes_values():
    rows = [{'symbol': 'DCE.l2609', 'name': '聚乙烯', 'last': 8000,
             'chg': -2, 'chg_pct': -0.12, 'pre_close': 8002,
             'open_interest': 331984, 'exchange': 'DCE'}]
    out = demo._jitter(rows)
    assert len(out) == 1
    assert out[0]['symbol'] == 'DCE.l2609' and out[0]['last'] > 0
    assert 'chg_pct' in out[0] and 'chg' in out[0]

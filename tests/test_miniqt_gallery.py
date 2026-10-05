"""The miniqt panel gallery page wires every plugin to a builder.

These only check the (Qt-free) wiring and mock data shapes; the page itself needs a
real QtWebEngine window to render.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PyQt6')
gallery = pytest.importorskip('miniqt.app.view.panels_gallery_interface')


def test_specs_cover_the_catalog_in_order():
    titles = [title for title, _method in gallery._SPECS]
    assert len(titles) == 26                     # 27 widgets minus Advanced Chart
    assert titles[0].startswith('2 ')            # Symbol Overview
    assert titles[-1].startswith('27 ')          # Broker Reviews
    # the two not-yet-implemented ones are placeholders, in the right places
    assert any('Technical Analysis' in title for title in titles)
    assert any('Economic Map' in title for title in titles)


def test_every_spec_has_a_builder():
    for _title, method in gallery._SPECS:
        builder = getattr(gallery.PanelsGalleryInterface, method, None)
        assert callable(builder), method


def test_mock_data_shapes():
    rows = gallery._rows(10)
    assert len(rows) == 10
    assert {'symbol', 'name', 'last', 'chg', 'chg_pct', 'spark'} <= set(rows[0])

    items = gallery._items(rows)
    assert items[0]['symbol'] == rows[0]['symbol']
    assert 'spark' not in items[0]

    heat = gallery._heat_items(12, 1)
    assert len(heat) == 12 and 'chg_pct' in heat[0]

    frame = gallery._ohlcv(100, 1)
    assert list(frame.columns)[:5] == ['time', 'open', 'high', 'low', 'close']
    assert len(frame) == 100

    seasonal = gallery.PanelsGalleryInterface._seasonal_frame(2, 1)
    assert 'close' in seasonal.columns and 'time' in seasonal.columns

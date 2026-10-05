"""The panel-control layer: every plugin is a Qt control with a Python API.

Only structure/adapters are checked here; creating a control needs a real
QtWebEngine window (PyQt6's offscreen crashes), so we don't instantiate any.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PyQt6')
controls = pytest.importorskip('miniqt.app.windows.panel_controls')

METHODS = ('set_data', 'set_provider', 'refresh', 'start_realtime',
           'stop_realtime', 'apply_theme', 'control', 'destroy')


def test_registry_covers_the_catalog():
    for name in ('Market Data', 'Market Summary', 'Market Overview',
                 'World Market Summary', 'Watchlist', 'Screener',
                 'Stock Heatmap', 'Crypto Coins Heatmap', 'Forex Table',
                 'ETF Heatmap', 'Seasonal Chart', 'Ticker Tape', 'Ticker Tag',
                 'Single Ticker', 'Tickers', 'Symbol Overview', 'Symbol Info',
                 'Mini Chart', 'Technical Analysis', 'Top Stories', 'News',
                 'Economic Calendar', 'Fundamental Data', 'Company Profile',
                 'Broker Rating', 'Broker Reviews'):
        assert name in controls.CONTROLS, name


def test_every_control_exposes_the_common_api():
    for control_class in set(controls.CONTROLS.values()):
        for method in METHODS:
            assert callable(getattr(control_class, method, None)), (
                control_class.__name__, method)


def test_create_control_rejects_unknown_names():
    with pytest.raises(KeyError):
        controls.create_control('Nope')


def test_providers_are_callables():
    class Fake:
        tq_api = None

    fake = Fake()
    assert callable(controls.market_groups_provider(fake))
    assert callable(controls.quotes_rows_provider(fake, ['DCE.l2609']))
    assert callable(controls.contract_quote_provider(fake, 'DCE.l2609'))
    # a provider with no tq_api returns None (no crash)
    assert controls.contract_quote_provider(fake, 'DCE.l2609')() is None


def test_rows_from_quotes_is_reexported():
    import pandas as pd
    rows = controls.rows_from_quotes(pd.DataFrame([
        {'instrument_id': 'DCE.l2609', 'instrument_name': '聚乙烯',
         'last_price': 8005, 'pre_close': 8000}]))
    assert rows[0]['symbol'] == 'DCE.l2609' and rows[0]['chg'] == 5


def test_new_providers_are_callables_and_safe_without_api():
    class Fake:
        tq_api = None

    fake = Fake()
    assert callable(controls.heatmap_items_provider(fake, ['DCE.l2609']))
    assert callable(controls.ticker_items_provider(fake, ['DCE.l2609']))
    # no tq_api -> None, no crash
    assert controls.heatmap_items_provider(fake, ['DCE.l2609'])() is None
    assert controls.ticker_items_provider(fake, ['DCE.l2609'])() is None


def test_screener_control_exposes_persistence():
    assert callable(getattr(controls.ScreenerControl, 'save_state', None))
    assert callable(getattr(controls.ScreenerControl, 'restore_state', None))


def test_chart_data_manager_stores_panel_state(tmp_path):
    from miniqt.app.common.chart_data import ChartDataManager
    manager = ChartDataManager(str(tmp_path / 'chart_data.json'))
    key = 'SHFE.rb2601|60'
    assert manager.get_panel_state(key) == {}
    manager.set_panel_state(key, {
        'match': 'any',
        'filters': [{'column': 'chg_pct', 'op': '>', 'value': 2}],
        'presets': {'up': [{'column': 'chg_pct', 'op': '>', 'value': 2}]}})
    state = manager.get_panel_state(key)
    assert state['match'] == 'any' and state['presets']['up'][0]['op'] == '>'
    # persisted to disk (a fresh manager reads it back)
    assert ChartDataManager(str(tmp_path / 'chart_data.json')).get_panel_state(key)['match'] == 'any'
    manager.clear_panel_state(key)
    assert manager.get_panel_state(key) == {}


@pytest.fixture(scope='module')
def app():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_calls_before_start_are_deferred_not_crashing(app):
    """Regression: the demo page wired a callback before the control started."""
    control = controls.MarketDataControl(None)
    assert control.control() is None            # not built yet
    # these used to raise AttributeError on `None.on_row_double_click`
    control.set_data({'DCE': [{'symbol': 'DCE.l2609'}]})
    control.on_row_double_click(lambda symbol: None)
    assert len(control._deferred) == 2
    control.destroy()

"""M3 tests: the miniqt market panel adapter and host.

These are split so the *logic* is tested without a browser:

* :func:`market_groups` / :func:`rows_from_quotes` are pure (DataFrame in, rows
  out) and need no Qt;
* :class:`PylightchartsPanelWindow` is built with a fake ``QtPanel`` so the
  tests run without QtWebEngine. (PyQt6's QtWebEngine aborts under the
  ``offscreen`` platform in CI; the real app uses a real window. The panel's
  page/bridge itself is covered by the QtPanel smoke tests elsewhere.)
"""
from __future__ import annotations

import os
import types

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PyQt6')
panel_mod = pytest.importorskip('miniqt.app.windows.pylightcharts_panel')

import pandas as pd                                                        # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget                          # noqa: E402


# --------------------------------------------------------------------- pure
class _FakeQuote:
    def __init__(self, contracts):
        self._contracts = contracts

    def get_main_contracts(self):
        return dict(self._contracts)


def _fake_query_quotes(symbols):
    rows = []
    for index, symbol in enumerate(symbols):
        rows.append({
            'instrument_id': symbol,
            'instrument_name': symbol.split('.')[-1],
            'last_price': 1000 + index * 3,
            'pre_close': 998 + index * 3,
            'open': 999 + index, 'high': 1005 + index, 'low': 997 + index,
            'volume': 1000 + index, 'open_interest': 5000 + index,
        })
    return pd.DataFrame(rows)


class _FakeMain:
    def __init__(self, contracts, with_api=True):
        self.marketQuoteInterface = _FakeQuote(contracts)
        self.tq_api = (types.SimpleNamespace(query_quotes=_fake_query_quotes)
                       if with_api else None)
        self.opened: list = []

    def start_minibt_chart(self, symbol, *_args, **_kwargs):
        self.opened.append(symbol)


def test_rows_from_quotes_computes_change():
    frame = pd.DataFrame([{
        'instrument_id': 'DCE.l2609', 'instrument_name': '聚乙烯',
        'last_price': 8005, 'pre_close': 8000, 'open': 7999, 'high': 8010,
        'low': 7998, 'volume': 1474, 'open_interest': 331984,
    }])
    rows = panel_mod.rows_from_quotes(frame)
    assert rows[0]['symbol'] == 'DCE.l2609'
    assert rows[0]['name'] == '聚乙烯'
    assert rows[0]['chg'] == 5
    assert abs(rows[0]['chg_pct'] - 0.0625) < 1e-9
    assert rows[0]['open_interest'] == 331984


def test_rows_from_quotes_survives_missing_fields():
    frame = pd.DataFrame([{'instrument_id': 'DCE.l2609'}])
    rows = panel_mod.rows_from_quotes(frame)
    assert rows[0]['last'] is None and rows[0]['chg'] is None


def test_market_groups_groups_by_exchange():
    main = _FakeMain({'DCE': ['DCE.l2609', 'DCE.pp2609'],
                      'SHFE': ['SHFE.rb2601']})
    groups = panel_mod.market_groups(main)
    assert set(groups) == {'DCE', 'SHFE'}
    assert [row['symbol'] for row in groups['DCE']] == ['DCE.l2609', 'DCE.pp2609']
    assert groups['DCE'][0]['chg'] == 2


def test_market_groups_without_api_only_lists_symbols():
    main = _FakeMain({'DCE': ['DCE.l2609']}, with_api=False)
    groups = panel_mod.market_groups(main)
    assert groups['DCE'] == [{'symbol': 'DCE.l2609', 'name': 'DCE.l2609'}]


def test_market_groups_empty_without_contracts():
    assert panel_mod.market_groups(None) == {}
    assert panel_mod.market_groups(_FakeMain({})) == {}


# ------------------------------------------------------------- host (faked)
class _FakeWin:
    """Just enough of Window for the panels."""

    def __init__(self):
        self.scripts: list = []
        self.handlers: dict = {}
        self._panels: list = []
        self._theme = None
        self.bulk_run = None
        self.themed: list = []

    def run_script(self, script, run_last=False):
        self.scripts.append(script)

    def theme(self, name='dark', **overrides):
        self.themed.append(name)


class _FakeQtPanel:
    def __init__(self, parent=None):
        self.win = _FakeWin()
        self._widget = QWidget(parent)

    def get_webview(self):
        return self._widget


@pytest.fixture(scope='module')
def app():
    yield QApplication.instance() or QApplication([])


def test_panel_window_builds_and_loads_groups(app, monkeypatch):
    import pylightcharts
    from miniqt.app.windows import chart_engine

    monkeypatch.setattr(chart_engine, 'ensure_qt', lambda: None)
    monkeypatch.setattr(pylightcharts, 'QtPanel', _FakeQtPanel, raising=False)

    main = _FakeMain({'DCE': ['DCE.l2609'], 'SHFE': ['SHFE.rb2601']})
    window = panel_mod.PylightchartsPanelWindow(
        None, main_window=main,
        provider=lambda: panel_mod.market_groups(main))
    window.start()                                   # idempotent + loads data

    assert window.market is not None
    assert window.market.group_keys() == ['DCE', 'SHFE']
    joined = '\n'.join(window.panel_win.scripts)
    # only the active group's rows are emitted; the tab bar carries both keys
    assert 'DCE.l2609' in joined
    assert '"SHFE"' in joined
    # switching the tab emits the other group's rows
    window.market._on_tab('SHFE')
    assert 'SHFE.rb2601' in '\n'.join(window.panel_win.scripts)
    # theme follows miniqt
    assert window.panel_win.themed                         # apply_theme ran


def test_panel_window_row_double_click_opens_chart(app, monkeypatch):
    import pylightcharts
    from miniqt.app.windows import chart_engine

    monkeypatch.setattr(chart_engine, 'ensure_qt', lambda: None)
    monkeypatch.setattr(pylightcharts, 'QtPanel', _FakeQtPanel, raising=False)

    main = _FakeMain({'DCE': ['DCE.l2609']})
    window = panel_mod.PylightchartsPanelWindow(None, main_window=main)
    window.start()
    # the row handler the grid calls
    handler = window.panel_win.handlers[window.market.grid.id]
    handler('DCE.l2609', 'rowdblclick')
    assert main.opened == ['DCE.l2609']


# --------------------------------------------------------------- realtime
def _panel(app, monkeypatch, main, provider):
    import pylightcharts
    from miniqt.app.windows import chart_engine
    monkeypatch.setattr(chart_engine, 'ensure_qt', lambda: None)
    monkeypatch.setattr(pylightcharts, 'QtPanel', _FakeQtPanel, raising=False)
    return panel_mod.PylightchartsPanelWindow(
        None, main_window=main, provider=provider)


def test_refresh_picks_up_new_values(app, monkeypatch):
    main = _FakeMain({'DCE': ['DCE.l2609']})
    calls = {'n': 0}

    def provider():
        calls['n'] += 1
        return {'DCE': [{'symbol': 'DCE.l2609', 'last': 8000 + calls['n']}]}

    window = _panel(app, monkeypatch, main, provider)
    window.start()
    assert calls['n'] == 1
    window.refresh()
    assert calls['n'] == 2
    assert '8002' in '\n'.join(window.panel_win.scripts)


def test_realtime_toggle_controls_timer(app, monkeypatch):
    main = _FakeMain({'DCE': ['DCE.l2609']})
    window = _panel(app, monkeypatch, main,
                    lambda: {'DCE': [{'symbol': 'DCE.l2609', 'last': 1}]})
    window.start()
    assert window.is_realtime()                      # default on
    assert window.realtimeAction.isChecked()

    window.stop_realtime()
    assert not window.is_realtime()
    assert not window.realtimeAction.isChecked()

    window.start_realtime(120)
    assert window.is_realtime()
    assert window.realtimeAction.isChecked()
    window.stop_realtime()


def test_realtime_off_by_flag(app, monkeypatch):
    main = _FakeMain({'DCE': ['DCE.l2609']})
    import pylightcharts
    from miniqt.app.windows import chart_engine
    monkeypatch.setattr(chart_engine, 'ensure_qt', lambda: None)
    monkeypatch.setattr(pylightcharts, 'QtPanel', _FakeQtPanel, raising=False)
    window = panel_mod.PylightchartsPanelWindow(
        None, main_window=main, realtime=False,
        provider=lambda: {'DCE': [{'symbol': 'DCE.l2609', 'last': 1}]})
    window.start()
    assert not window.is_realtime()
    assert not window.realtimeAction.isChecked()

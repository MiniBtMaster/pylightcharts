"""Drawing persistence: drawings must survive a window close and come back for the
same symbol + cycle.

The old code had all the pieces (`ChartDataManager`, `CustomToolBox._save_drawings`)
but never wrote to disk, and keyed everything by symbol only. These tests pin the
new behaviour: `{"symbol|cycle": [...]}` in `chart_data.json`, atomic writes, and
a legacy `{symbol: [...]}` fallback.

    pytest tests/test_miniqt_drawings.py
"""
from __future__ import annotations

import json

from miniqt.app.common.chart_data import ChartDataManager, drawing_key


def frame():
    return [
        {"type": "TrendLine", "points": [
            {"time": 1700000000, "logical": 1, "price": 100},
            {"time": 1700003000, "logical": 2, "price": 110}],
         "options": {"lineColor": "#1E80F0"}},
        {"type": "FibonacciRetracement", "points": [
            {"time": 1700000000, "logical": 1, "price": 100},
            {"time": 1700003000, "logical": 2, "price": 110}],
         "options": {}},
    ]


def test_drawing_key_separates_cycles():
    assert drawing_key("SHFE.rb2610", 60) == "SHFE.rb2610|60"
    assert drawing_key("SHFE.rb2610", 300) == "SHFE.rb2610|300"
    # cycle-less form is the legacy / contract-level key
    assert drawing_key("SHFE.rb2610") == "SHFE.rb2610"
    assert drawing_key("SHFE.rb2610", None) == "SHFE.rb2610"


def test_round_trip_through_disk(tmp_path):
    path = tmp_path / "chart_data.json"
    manager = ChartDataManager(str(path))
    manager.set_drawings("SHFE.rb2610|60", frame())
    manager.set_drawings("SHFE.rb2610|300", [{"type": "HorizontalLine"}])

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "SHFE.rb2610|60" in payload["drawings"]

    # a fresh manager reads it back
    reloaded = ChartDataManager(str(path))
    assert reloaded.get_drawings("SHFE.rb2610|60") == frame()
    assert reloaded.get_drawings("SHFE.rb2610|300") != frame()


def test_legacy_symbol_only_key_still_loads(tmp_path):
    path = tmp_path / "chart_data.json"
    manager = ChartDataManager(str(path))
    manager.set_drawings("SHFE.rb2610", frame())     # old format: symbol only

    assert manager.get_drawings("SHFE.rb2610|60",
                                legacy_key="SHFE.rb2610") == frame()
    # a different cycle does not inherit the legacy data unless asked via legacy_key
    assert manager.get_drawings("SHFE.rb2610|300") == []


def test_clear(tmp_path):
    manager = ChartDataManager(str(tmp_path / "d.json"))
    manager.set_drawings("A|60", frame())
    manager.set_drawings("B|60", frame())

    manager.clear_drawings("A|60")
    assert manager.get_drawings("A|60") == []
    assert manager.get_drawings("B|60") == frame()

    manager.clear_drawings()
    assert manager.drawings == {}


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "d.json"
    manager = ChartDataManager(str(path))
    for index in range(5):
        manager.set_drawings(f"A|{index}", frame())

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    assert json.loads(path.read_text(encoding="utf-8"))["drawings"]


def test_validate_drops_bad_entries(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({
        "drawings": {"good|60": frame(), "bad|60": "not-a-list", "empty|60": []},
        "price_alerts": {"A|60": {"enabled": True}, "bad": 1},
    }), encoding="utf-8")

    manager = ChartDataManager(str(path))
    assert "good|60" in manager.drawings
    assert "bad|60" not in manager.drawings
    assert "empty|60" not in manager.drawings
    assert manager.get_price_alerts("A|60") == {"enabled": True}

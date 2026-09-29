# Changelog

All notable changes to `pylightcharts` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.2] - 2026-09-29

Correctness pass over the series lifecycle, the drawing primitives and the
local browser server — every change here came out of the bridge log
complaining at a real chart (page switches, window rebuilds, Ctrl+C,
sandboxed iframes).

### Added

- **`shapes.stem(price, baseline=0.0, color=None, width=1, style='dashed',
  cap=False, cap_radius=3)`** — a vertical stick from `baseline` to `price`
  (a "lollipop"), for per-bar values that read better as a deviation from a
  common base: per-trade PnL, distance from a moving average, volume at price.
  `style` defaults to `'dashed'`; `cap=True` puts a dot on the tip. Either way
  the item's `value` still drives the autoscale, so the pane range is not
  affected.
- **CORS on the local browser server** (`server.py`): responses carry
  `Access-Control-Allow-Origin` / `-Headers` / `-Methods` and `OPTIONS`
  preflights are answered with `204`, so the JS callbacks and the SSE stream
  keep working when the page is embedded in an opaque-origin / sandboxed
  iframe (Jupyter output frames, Streamlit, `srcdoc`).

### Changed

- Rebuilt `pylightcharts/js/bundle.js`: `removeSeries()` now also drops the
  legend row **by series name** (`e.series === series || e.name === name`),
  because the wrapper handle is not always resolvable at that point (a page
  switch or a window rebuild invalidates it).
- More regression tests: bokeh backtest/replay/realtime subprocess tests, the
  minibt → pylightcharts mapping layer (`tests/test_realtime.py`), theme and
  `Config` resolution, `shapes.stem`, a refreshed API-coverage baseline. Tests
  that need the (unpublished) `minibt` sources skip themselves.
- **The sdist is a full source tree again** (`MANIFEST.in`): it now carries
  `examples/`, `scripts/`, `docs/`, `tests/`, `jslib/` and `requirements.txt`,
  so `pytest tests -q` passes on an unpacked sdist instead of erroring on
  missing example files. `scripts/check_sdist.py` (run by CI) guards the
  manifest; `RELEASING.md` documents the whole release.

### Fixed

- **Deleting a series twice no longer logs "Value is undefined".** Every
  `delete()` path now goes through `Series._do_delete()`, which is idempotent
  (a `_deleted` flag): several managers keep a series in more than one list and
  used to emit `removeSeries({"$ref": ...})` for a handle the JS side had
  already dropped.
- **`Band` / `HorizontalSpan` / `VerticalSpan` are removed with
  `series.detachPrimitive(...)`.** They are v5 series *primitives*, so the old
  `detach()` call raised "`...detach` is not a function"; the detach is also
  skipped when the series they were attached to is already gone.
- **`overlay.add_symbol(...)` passes `price_line_visible` / `last_value_visible`
  / `title` as series creation options** instead of a follow-up
  `applyOptions` pass. That second call logged `Value is null` (LWC
  `ensureNotNull`) when the handle had already been dropped by a page switch or
  a window rebuild, which also aborted the rest of the queued script batch.
- **Ctrl+C on Windows prints `[pylightcharts] window closed`** instead of a
  traceback: `show()` catches the `CancelledError` / `KeyboardInterrupt` that
  `asyncio.run()` re-raises when the pywebview message loop is interrupted.
- The native window is created with `min_size=(width, height)`; a window
  narrower than the requested chart size made the startup `evaluate_js` return
  `null`, and the series' legend rows were lost with it.

## [0.1.1] - 2026-09-23

First release after the `0.1.0` preview: theming, custom-series shapes, panes,
infinite history and browser/live support are now feature-complete enough to
build on.

### Added

- **`shapes.marker(price, marker=..., offset=..., size=..., color=...)`** — a
  pixel-sized marker glyph for declarative custom series. `offset` (vertical
  pixel shift, positive = down) and `size` (pixel half-extent) are **pixels**, so
  glyphs keep their size at every zoom level. Supported `marker` names:
  `triangle` `inverted_triangle` `arrow_up` `arrow_down` `circle`
  `circle_cross` `circle_dot` `circle_x` `circle_y` `square` `dot` `dash`
  `cross` `asterisk` `triangle_dot`.
- **Themes** — `Window.theme(name)` (dark/light) plus `active_background` /
  `crosshair_label` accent colours, per-theme pane-separator colours and
  `layout.font_size`; the whole UI (chart, topbar, legend, tooltips, tables,
  report pages) follows one palette.
- **`chart.create_html_panel()`** (`HtmlPanel`) — a themed, full-bleed HTML
  overlay for report pages (statistics + trade tables).
- **Two price scales per pane** — `overlay.add_symbol(...)`,
  `scale_margins(...)` and independent left/right scales.
- **Infinite history** — `pylightcharts.history` + `events.range_change` driven
  loading, with gap-aware data encoding so the chart never connects across
  missing bars.
- **Browser targets** — `BrowserChart`, `chart.export_html()` and a stdlib
  SSE server for live charts (no Qt, no third-party server).
- **Qt-free chart widgets** and a `Window`-level `on_theme` callback.
- More custom-series helpers: `shapes.range_bar` / `box_plot` / `error_bar`
  presets, legend rows per custom series, and per-series `color_by`.
- Keyboard navigation, swing markers, `size=`, formatter `name=` and drawing
  primitives (trend line, box, horizontal line/span, `fill_between`).

### Changed

- `encode_series_data()` falls back to the JSON path whenever the data contains
  gaps, so `NaN` bars stay whitespace instead of silently connecting.
- `set()` on a single-value series matches a column **named like the series**
  (`{time, value}` style is reserved for OHLC/range series).
- Pane dividers are 1 px and only their **colour** and `enable_resize` are
  configurable.

### Fixed

- A script batch ending without `;` followed by one starting with `(` no longer
  breaks the whole batch (ASI hazard in `run_script`).
- `closeEvent` shadowed its own exception variable, raising `UnboundLocalError`.
- Blank chart on cross-origin `qwebchannel` initialisation (three injection
  modes + an ES2018 build target).
- Legend swatch/eye icons keep their colour (`currentColor`); tooltip bottom
  border is drawn; table borders/centring; page-topbar separator line.

### Notes

- `chart.screenshot()` captures canvases only — use `HeadlessChart.render()` for
  DOM overlays (legend, topbar, HTML panels).
- Real windows host the GUI in a child process, so parent processes should use
  `threading` rather than `QTimer`.

## [0.1.0] - 2026-08-13

- Initial preview release: bridged, near-full TradingView Lightweight Charts v5
  API coverage, declarative custom series, plugins, panes, layouts and
  tooltips.

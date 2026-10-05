# Changelog

All notable changes to `pylightcharts` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.3] - 2026-09-30

### Performance

- **NaN-gap lines draw with far fewer series**: a `Line` that breaks at `nan`
  used to create one internal `addSeries` + `setData` per contiguous segment -
  each is a webview round-trip and another browser repaint, so indicators looked
  like they were drawing "one line at a time, left to right" and loaded slowly.
  Now:
  * up to `Line.MAX_GAP_SEGMENTS` (64) segments keep the per-segment split
    (few series, clean tooltips);
  * above that the line becomes a **single series with transparent gaps**: gap
    points carry the previous value and a transparent `color`, and the engine -
    which colours each segment from its *starting* point - simply skips them.

  MACD-Bollinger `macd_up` / `macd_dn` (369 / 374 segments on the bundled test
  data) went from 743 internal series to 0 (`btplot` ~2.0 s -> ~1.1 s), and the
  all-`nan`-alternating band-boundary lines (`fill_up_low` / `fill_dn_low`,
  264 segments each) from ~1056 series to 4. `fill_between` bands keep breaking
  at those points too - the `LineFill` view treats a transparent point as a gap -
  so SuperTrend-style channels stay correct.

### Added

- **Multi-line labels in `shapes.text(...)`**: a newline inside `text` is now
  rendered as **several lines** (same convention as bokeh's `LabelSet`),
  spaced `line_height` (new keyword, default `1.2`) x `font_size` apart and
  anchored on `baseline` (`'top'` grows downwards, `'bottom'` upwards,
  `'middle'` keeps the whole block centred on `price`). Handy for per-point
  signal annotations such as ``'BUY\nCCI\nRSI'``.
  Covered by `examples/11_api_tour/21_text_multi_line.py`.
- **Full label styling on `shapes.text(...)`**: `offset_x` / `offset_y` (CSS-pixel
  offsets, scaled by the pixel ratio), `font_family` / `font_weight` / `font_style`
  (they build the canvas `font` string), and an optional label box -
  `background_color` (+ `background_alpha`), `border_color` (+ `border_alpha`,
  `border_width`) and `padding` (drawn behind the text, sized to the widest
  line, `
`-aware). All optional: omitted values keep the renderer defaults.
- **Inset floating tables**: `Table.set_position(...)` and
  `chart.create_table(...)` accept `margin_x` / `margin_y` (pixels from the
  nearest horizontal / vertical edge), so a table can be nudged clear of the
  top bar or the legend while staying pinned to its corner on resize. The
  `Table.set_colors(...)` helper keeps working unchanged.

### Fixed

- **A `nan` in either channel line now breaks the band too** (`fill_between` /
  `upper.fill_between(lower)`): the `line-fill` renderer used to build one closed
  path out of every point, so a gap in either line filled straight across it (a
  big ugly triangle at the break - same problem the line series had). It now
  fills one path per run of consecutive *valid* points, so the band stops at the
  gap and picks up again after it. The pane view had to learn about gaps as well:
  `ISeriesApi.data()` does **not** return whitespace items, so a series looks
  contiguous even where it has no values - the view now also compares the
  `timeToIndex()` of consecutive points and inserts a break when the logical
  index jumps. Covered by `jslib/test/line-fill.test.ts` +
  `jslib/test/line-fill-view.test.ts` (single run, gap in the middle,
  leading/trailing gaps, one-sided gap, fewer than two valid points) and by
  `examples/11_api_tour/23_fill_between_gaps.py`.

- **A `nan` in a `Line` series now breaks the line instead of connecting across
  it.** lightweight-charts v5 treats a whitespace item (`{time}` without a
  value) as "a time scale point only" and draws straight through it, so
  `[1, 2, 3, nan, nan, 6, 7, 8]` came out as one continuous line. The main
  series is now hidden (`lineVisible: false`) and every contiguous run is drawn
  by an extra, legend-less `Line` series that copies the main series' style -
  the price line, the last-value label and the legend row stay on the main
  series, and gapless data keeps the single-series behaviour (no extra work).
  Covered by `examples/11_api_tour/22_line_gaps.py` plus two bridge regression
  tests.
- **The native window no longer hangs when the entry script has no
  `if __name__ == '__main__':` guard.** On Windows / macOS the renderer runs in
  a `multiprocessing` child (`spawn`), which **re-executes the entry script**;
  without the guard the child dies before the window is ready, and
  `WebviewHandler.start()` waited on `loaded_event` **forever** (the script just
  looked frozen). It now polls the child's liveness with a timeout and raises
  the new **`pylightcharts.WindowStartError`** (exported from the package) whose
  message says exactly what to do: add the guard, or use a browser target
  (`BrowserChart` / `gui='pylightcharts_web'`).

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

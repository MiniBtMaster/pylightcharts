# Panels — DataGrid and Sparkline

Panels are **DOM components** (not chart engines) that live on the same host
page as a chart. They are driven from Python through the same generic bridge as
everything else, and are the building blocks for the TradingView-style market
widgets: market tables, watchlists, screeners, quote headers and tickers.

`pylightcharts` ships two of them today:

| Panel | What it is |
|---|---|
| [`DataGrid`](#datagrid) | a sortable, filterable, **virtualised** data table |
| [`Sparkline`](#sparkline) | a single-canvas mini line/area chart |
| [`Tabs`](#tabs) | a horizontal group switcher |
| [`MarketData`](#marketdata-and-watchlist) / [`Watchlist`](#marketdata-and-watchlist) | grouped market table / self-selected list |
| [`Ticker`](#ticker-family) family | quote strips (`TickerTape`, `TickerTag`, `SingleTicker`, `Tickers`) |
| [`QuoteHeader`](#quote-headers) family | quote headers (`SymbolInfo`, `SymbolOverview`) and `MiniChart` |
| [`Heatmap`](#heatmap) family | treemap heatmaps (Stock / Crypto / ETF / Forex) |
| [`SeasonalChart`](#seasonal-chart) | seasonality bars (average performance per month) |
| [`Screener`](#screener) | `DataGrid` + column conditions |
| [`FilterBar`](#screener) | removable condition chips, synced with the Screener |
| [`NewsFeed`](#detail-shells) / [`TextBlock`](#detail-shells) | headline list / rich-text block |
| [detail shells](#detail-shells) | `EconomicCalendar`, `FundamentalData`, `CompanyProfile`, `BrokerRating`, `BrokerReviews` |
| [`TechnicalAnalysis`](#technical-analysis) | buy/sell gauge + oscillator / moving-average tables |

All of them are on the package root too (`from pylightcharts import MarketData`).

Both can be hosted on a chart's window, or on a chart-less
[`QtPanel`](#hosting-a-full-page-qtpanel).

## DataGrid

```python
from pylightcharts import Chart
from pylightcharts.panels import Column, DataGrid

chart = Chart()
grid = DataGrid(chart.win, columns=[
    Column('symbol', '代码', width=1.4),
    Column('name', '名称'),
    Column('last', '最新', type='number', color_by='sign'),
    Column('chg', '涨跌', type='change'),
    Column('chg_pct', '涨跌幅', type='percent'),
    Column('volume', '成交量', type='number', compact=True),
    Column('spark', '走势', type='spark'),
])
grid.set_rows(rows)                     # rows: list[dict], keyed by the column keys
```

For symmetry with :meth:`Window.create_table`, the window also has factories:

```python
grid = chart.win.create_data_grid(columns=[...])
spark = chart.win.create_sparkline(width=160, height=40)
```

A row is a plain dict keyed by the column `key` values. Field names are **not**
rewritten, so `open_interest` stays `open_interest`:

```python
rows = [
    {'symbol': 'DCE.l2609', 'name': '聚乙烯2609', 'last': 8005,
     'chg': 12, 'chg_pct': 0.15, 'volume': 1474, 'open_interest': 331984,
     'spark': [8000, 8002, 8001, 8005]},
]
```

### Columns

`Column(key, title=None, *, ...)`:

| Argument | Type | Meaning |
|---|---|---|
| `key` | `str` | field name in each row dict |
| `title` | `str` | header label (defaults to `key`) |
| `width` | `float` | flex grow weight relative to the other columns (default `1`) |
| `align` | `'left'`/`'center'`/`'right'` | default depends on `type` |
| `type` | `'text'`/`'number'`/`'percent'`/`'change'`/`'spark'` | cell renderer |
| `decimals` | `int` | fixed decimal places |
| `color_by` | `'sign'`/`'none'` | colour the value by its sign |
| `compact` | `bool` | render large numbers as 万 / 亿 |
| `prefix` / `suffix` | `str` | literal text around the value |
| `sortable` | `bool` | allow click-to-sort on this column |
| `visible` | `bool` | hide the column |
| `spark` | `dict` | options for the inline `Sparkline` (JS names, e.g. `{'lineWidth': 1.5}`) |

`type='change'` and `type='percent'` are signed (a `+` is added for positive
values) and coloured by sign by default. You can also pass a plain `str` (the
key) or a ready-made option `dict` instead of a `Column`.

### Updating data

| Method | Effect |
|---|---|
| `set_rows(rows)` | replace every row |
| `append_rows(rows)` | add rows |
| `update_row(row)` | replace the row with the same `row_key` |
| `update_rows(rows)` | replace several rows (one rebuild) |
| `set_cell(key, column, value)` | change one cell |
| `delete_row(key)` | remove a row by its key |
| `clear()` | remove every row |

`row_key` (default `'symbol'`) selects the field that identifies a row.

### Sorting and filtering

Click a header to sort; click again to reverse. The same is available from
Python:

```python
grid.sort('chg_pct', direction=-1)      # descending by change %
grid.sort(None)                         # back to insertion order
grid.set_filter('pp')                   # case-insensitive substring filter
```

### Row events

```python
grid.on_row_click(lambda key: print('clicked', key))
grid.on_row_double_click(lambda key: open_chart(key))
```

The callback receives the row's `row_key` value. Async callbacks are awaited
too, matching the rest of the package.

### Theming

`DataGrid` accepts a `theme=` dict and a `color_scheme`:

```python
grid = DataGrid(chart.win, columns=[...], color_scheme='tv')   # green up / red down
```

`color_scheme='cn'` (the default) is red-up / green-down. When you switch the
window theme with `chart.win.theme('light')`, every registered grid is
recoloured automatically.

### Virtual scrolling

Only the rows that are visible in the body are kept in the DOM (plus a small
overscan). A watchlist of several thousand instruments therefore stays smooth;
you can see it in action with `examples/13_panels/01_data_grid.py`.

## Sparkline

```python
from pylightcharts.panels import Sparkline

spark = Sparkline(chart.win, width=160, height=40)
spark.set_data([1, 2, 1.5, 3, 2.5, 4])
```

| Argument | Meaning |
|---|---|
| `baseline` | `'first'` (default) colours by last-vs-first, `'zero'` by last-vs-0, `'none'` keeps `line_color` |
| `line_color` / `fill_color` | explicit colours |
| `up_color` / `down_color` | colours used when `baseline` decides the direction |
| `line_width`, `padding`, `end_dot` | geometry |
| `container` | JS expression of the element to append to (default `window.containerDiv`) |

`set_data(values)` redraws, `re_size(width, height)` resizes, `set_options(...)`
updates colours/geometry (JS option names). A percentage ``width`` (e.g.
``width='100%'``) follows its container and redraws on resize.

## Tabs

```python
from pylightcharts.panels import Tabs

tabs = Tabs(chart.win, [('DCE', '大商所'), ('SHFE', '上期所')],
            on_change=lambda key: print(key))
tabs.set_active('SHFE')
```

A tab is a `str`, a `(key, title)` tuple, or a `{'key', 'title'}` dict.

## MarketData and Watchlist

`MarketData` is a `DataGrid` plus a `Tabs` group switcher:

```python
from pylightcharts.panels import Column, MarketData

market = MarketData(chart.win, groups={
    'DCE': dce_rows, 'SHFE': shfe_rows, 'CZCE': czce_rows,
}, columns=[
    Column('symbol', '代码'),
    Column('last', '最新', type='number', color_by='sign'),
    Column('chg_pct', '涨跌幅', type='percent'),
])
market.set_group_rows('DCE', new_rows)     # refresh the active group
market.on_row_double_click(lambda key: open_chart(key))
```

`Watchlist` is a `DataGrid` preset (代码/名称/最新/涨跌/涨跌幅/成交量/走势) with
in-memory add / update / remove so the host can persist it:

```python
from pylightcharts.panels import Watchlist

watch = Watchlist(chart.win, rows=my_rows)
watch.add({'symbol': 'DCE.l2609', 'last': 8005})
watch.remove('DCE.l2609')
watch.symbols()                            # ['DCE.pp2609', ...]
```

## Ticker family

One class, four names — they differ only in the default `layout`:

| Class | Layout | TradingView widget |
|---|---|---|
| `TickerTape` | `'scroll'` (marquee) | Ticker Tape |
| `TickerTag` | `'wrap'` | Ticker Tag |
| `SingleTicker` | `'wrap'` | Single Ticker |
| `Tickers` | `'wrap'` | Tickers |

```python
from pylightcharts.panels import TickerTape

tape = TickerTape(chart.win, items=[
    {'symbol': 'DCE.l2609', 'name': '聚乙烯2609', 'last': 8005,
     'chg': -2, 'chg_pct': -0.12},
], speed=70, on_item_click=lambda symbol: print(symbol))
tape.set_items(new_items)
tape.update_item({'symbol': 'DCE.l2609', 'last': 8010, 'chg_pct': 0.06})
```

## Quote headers

| Class | What it adds |
|---|---|
| `QuoteHeader` | name / code / last / change + OHLC / volume / OI fields |
| `SymbolInfo` | `QuoteHeader` without a chart |
| `SymbolOverview` | `QuoteHeader` with a larger inline `Sparkline` |
| `MiniChart` | a standalone `Sparkline` (TradingView Mini Chart) |

```python
from pylightcharts.panels import MiniChart, SymbolOverview

overview = SymbolOverview(chart.win, {
    'symbol': 'DCE.l2609', 'name': '聚乙烯2609', 'exchange': 'DCE',
    'last': 8005, 'chg': -2, 'chg_pct': -0.12,
    'open': 8006, 'high': 8008, 'low': 8003, 'pre_close': 8007,
    'volume': 1474, 'open_interest': 331984,
    'spark': [8000, 8003, 8001, 8005],
}, decimals=0)
overview.set_data({'last': 8012, 'chg_pct': 0.09})

MiniChart(chart.win, [1, 2, 1.5, 3], width=220, height=64)
```

## Heatmap

A treemap: tile **size** is one metric (volume / market cap), tile **colour** is
another (percent change).

```python
from pylightcharts import Heatmap

heat = Heatmap(chart.win, [
    {'symbol': '聚乙烯', 'value': 9, 'chg_pct': 1.2},
    {'symbol': '聚丙烯', 'value': 4, 'chg_pct': -0.8},
], color_scheme='cn', max_shock=5,
   on_item_click=lambda symbol: print(symbol))
heat.set_items(new_items)
```

`StockHeatmap`, `CryptoHeatmap`, `EtfHeatmap` and `ForexHeatmap` are the same
component (they only differ in intent). Group the tiles (sectors / exchanges) and
hover any tile for a tooltip:

```python
heat.set_groups([
    {'name': '能源', 'items': [{'symbol': '焦炭', 'value': 5, 'chg_pct': 1.2}]},
    {'name': '化工', 'items': [{'symbol': '聚乙烯', 'value': 7, 'chg_pct': -0.4}]},
])
```

Each group is laid out first (with a label strip), then its tiles inside; a floating
tooltip shows the full symbol / name / weight / change.

The layout is the **squarified treemap** (Bruls et al.), so tiles stay close to
square; a gradient **legend** (`showLegend=True`, default) shows the colour scale
at the bottom-left.

## Seasonal Chart

```python
from pylightcharts import SeasonalChart, seasonal_monthly

chart = SeasonalChart(my_window)
chart.from_frame(df)                 # df with `time` + `close` columns
# ...or feed the numbers yourself:
chart.set_data([1.2, -0.4, 2.1], labels=['1月', '2月', '3月'])

data = seasonal_monthly(df)          # {'labels': [...], 'values': [...]}
```

`seasonal_monthly` averages each month-of-year's return across the years in the
frame (month-end last vs previous month-end last).

## Screener

A `DataGrid` with **multiple column conditions** applied in Python before the
rows are pushed (the grid's search box still filters on top):

```python
from pylightcharts import Screener, Column

screener = Screener(chart.win, rows, columns=[
    Column('symbol', '代码'),
    Column('chg_pct', '涨跌幅', type='percent'),
    Column('volume', '成交量', type='number', compact=True),
])
screener.add_filter('chg_pct', '>', 2)
screener.add_filter('volume', '>=', 10000)
screener.filters()        # [('chg_pct', '>', 2), ('volume', '>=', 10000)]
screener.clear_filters()
```

Operators: `>`, `>=`, `<`, `<=`, `==`, `!=`, `contains`, `in`. Combine it with
[`Tabs`](#tabs) for preset screens (see `examples/13_panels/07_screener.py`).

`screener.set_match('any')` flips the default AND to OR. A `FilterBar` renders the
conditions as removable chips (with an optional inline adder) and stays in sync
both ways:

```python
from pylightcharts import FilterBar

bar = FilterBar(chart.win, columns=['chg_pct', 'volume'], editable=True)
screener.bind_filter_bar(bar)     # user adds/removes a chip -> screener updates
```

### Named presets and persistence

```python
screener.save_preset('up', [('chg_pct', '>', 2)])   # or omit filters = current
screener.apply_preset('up')
screener.presets()                                 # {'up': [('chg_pct', '>', 2)]}

screener.sort('chg_pct', -1).set_filter('pp')
screener.save('screen.json')     # filters + presets + match + sort/search
screener.load('screen.json')     # restore
state = screener.to_dict()       # or dumps() / loads() for strings
```

## Technical Analysis

A buy/sell **gauge** + summary counts + two tables (oscillators / moving
averages). `ta_summary(df)` computes a TradingView-style summary from a price
frame (7 oscillators + 12 moving averages); the widget renders whatever you pass:

```python
from pylightcharts import TechnicalAnalysis
from pylightcharts.panels import ta_summary

ta = TechnicalAnalysis(chart.win, ta_summary(df))   # df with close (high/low optional)

ta.set_data({
    'score': 0.32,                       # -1 .. +1
    'counts': {'buy': 10, 'neutral': 3, 'sell': 2},
    'oscillators': [{'name': 'RSI(14)', 'value': 56.3, 'signal': 'buy'}],
    'moving_averages': [{'name': 'MA10', 'value': 190.2, 'signal': 'buy'}],
})
```

## Detail shells

These are the widgets whose **content needs a data source** the library does not
ship (news / fundamentals / calendar / brokers). The UI and the data contract are
here; the host feeds the rows:

```python
from pylightcharts import (BrokerRating, BrokerReviews, CompanyProfile,
                           EconomicCalendar, FundamentalData, NewsFeed, TextBlock)

EconomicCalendar(window, [
    {'time': '20:30', 'country': 'US', 'event': 'CPI 月率', 'importance': '高',
     'actual': '0.3%', 'forecast': '0.3%', 'previous': '0.4%'},
])
FundamentalData(window, [{'name': '市盈率(TTM)', 'value': 28.4, 'yoy': 0.12,
                          'period': '2024Q4'}])
BrokerRating(window, [{'broker': '高盛', 'rating': '买入', 'target': 210,
                       'upside': 0.10, 'date': '2025-01-12'}])
BrokerReviews(window, [{'broker': '高盛', 'review': '服务稳定', 'score': 4.5,
                        'date': '2025-01-05'}])
NewsFeed(window, [{'title': '...', 'source': 'Reuters', 'time': '10:24',
                   'url': 'https://...', 'summary': '...'}])
TextBlock(window, html='<p>...</p>')

profile = CompanyProfile(window, {'name': '苹果公司', 'symbol': 'AAPL',
                                  'last': 190.2, 'chg_pct': 0.79},
                         html='<p>...</p>')
```

The table shells reuse `DataGrid` (sort / search / virtual scroll for free) and
support `Column(..., colors={'高': '#ef5350', ...})` for value-driven colours
(calendar importance, broker rating).

## Themes

Every panel follows the window theme — dark and light are both fully styled
(tables, tabs, tickers, heatmap neutral + legend, scrollbars, stripes, hover
states). Switch with `win.theme('light')` / `'dark'`:

```python
chart.win.theme('light')      # dark (default) or light
```

Panels created **after** the switch inherit the current theme, and
`Window.theme()` recolours every panel already registered on the window. The
miniqt pages call it on `qconfig.themeChanged`, so they follow the app theme.

## Hosting a full-page QtPanel

`QtPanel` is a chart-less Qt WebEngine page — the counterpart of `QtChart`.
Use it for widgets that fill a screen (a market table, a screener):

```python
from pylightcharts import QtPanel
from pylightcharts.panels import Column, DataGrid

panel = QtPanel(parent)                 # PySide6 / PyQt6 / PyQt5
grid = DataGrid(panel.win, columns=[Column('symbol', '代码')])
grid.set_rows(rows)
layout.addWidget(panel.get_webview())
```

`QtPanel` creates its `Window` (available as `panel.win`), wires the same
QWebChannel bridge, and makes `#container` fill the viewport so the grid can
virtualise. It is **local and offline** — no server, no external resource.

## Reference

```
pylightcharts.panels
├── Panel          base class for DOM panels
├── DataGrid       table panel
│   └── Column     column definition
├── Sparkline      canvas mini chart
├── MiniChart      standalone sparkline
├── Tabs           group switcher
├── MarketData     DataGrid + Tabs
├── Watchlist      DataGrid preset + add/remove
├── Screener       DataGrid + conditions
├── Ticker         quote strip (TickerTape / TickerTag / SingleTicker / Tickers)
├── QuoteHeader    quote header (SymbolInfo / SymbolOverview)
├── Heatmap        treemap heatmap (StockHeatmap / CryptoHeatmap / EtfHeatmap / ForexHeatmap)
├── SeasonalChart  seasonality bars (+ seasonal_monthly)
├── FilterBar      condition chips for the Screener
├── NewsFeed       headline list (TopStories)
├── TextBlock      rich-text / HTML block
├── TechnicalAnalysis  buy/sell gauge + indicator tables (+ ta_summary)
└── EconomicCalendar / FundamentalData / CompanyProfile /
    BrokerRating / BrokerReviews   detail shells
```

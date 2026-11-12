# pylightcharts

[![PyPI](https://img.shields.io/pypi/v/pylightcharts.svg)](https://pypi.org/project/pylightcharts/)
[![Python versions](https://img.shields.io/pypi/pyversions/pylightcharts.svg)](https://pypi.org/project/pylightcharts/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/MiniBtMaster/pylightcharts/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue.svg)](https://github.com/MiniBtMaster/pylightcharts/tree/main/docs)

[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

[TradingView Lightweight Charts™](https://github.com/tradingview/lightweight-charts) の Python バインディングです。
Python らしいインターフェースで、**ほぼ完全な API カバレッジ**を目指しています。

> ステータス：**Lightweight Charts v5.2.1 の API を完全にカバー（インターフェースメソッド 150/150）** —
> 17 種類のインジケーター、13 種類の描画ツール、数値軸、フォーマッター、v5 プラグイン、宣言型の
> プリミティブ、カスタムシリーズ、カスタム水平スケール、JS と Python のテストおよびドキュメントを含む CI。
> メソッドごとの対応表：[`API_IMPLEMENTATION_REPORT.md`](https://github.com/MiniBtMaster/pylightcharts/blob/main/docs/advanced/api-implementation-report.md)。
>
> さらに**金融パネル層**を備えています — TradingView 風のマーケットウィジェット（マーケットテーブル、
> ウォッチリスト、スクリーナー、ヒートマップ、ティッカー、気配値ヘッダー、テクニカル分析、季節性、
> ニュース、カレンダー、銘柄詳細など）を同じホストページ上にレンダリングし、Python から操作できます。
> [金融パネル](#金融パネルtradingview-風ウィジェット)を参照してください。
>
> リリースノート：[`docs/changelog.md`](docs/changelog.md) — 最新は **0.2.1**。

## 仕組み

これはチャートエンジンを Python で再実装したものでは**ありません**。
公式の実績ある JavaScript レンダラーを WebView（pywebview / Qt WebEngine / wx / Jupyter / Streamlit）に
埋め込み、Python から操作します。

```
Python API  ──►  JSON / JS bridge  ──►  Lib.Handler (TypeScript)  ──►  Lightweight Charts v5
```

ピクセル描画とインタラクションは上流のライブラリが生成するため、
見た目の忠実度とパフォーマンスは JS 版と同等です。

## API カバレッジ

pylightcharts は上流のエンジンを直接操作するため、Lightweight Charts v5.2.1 の**すべての公開メソッド**に
アクセスできます。カバレッジは `scripts/check_api_coverage.py` で測定しており、これは上流の
`typings.d.ts` を解析します。

| グループ | カバレッジ |
|---|---|
| `IChartApi` / `ISeriesApi` / `ITimeScaleApi` / `IPriceScaleApi` / `IPaneApi` / `IPriceLine` | 100% |
| v5 プラグイン（シリーズマーカー、上昇/下降マーカー、テキスト・画像ウォーターマーク） | 100% |
| `ISeriesPrimitive` / `IPanePrimitive`（Python からの宣言型） | 100% |
| `ICustomSeriesPaneView` / `ICustomSeriesPaneRenderer` | 100% |
| `IHorzScaleBehavior`（カスタム水平スケール） | 100% |
| オプション / 型エイリアス（約 120） | 100% パススルー |
| 11 個の enum とすべてのトップレベル関数 | エクスポート済み（`Lib.*` + `pylightcharts.constants`） |

```bash
python scripts/check_api_coverage.py          # print the matrix
python scripts/check_api_coverage.py --check  # fail CI if coverage regresses
```

メソッドごとの完全な対応表と、意図的な差異の一覧：
[`API_IMPLEMENTATION_REPORT.md`](https://github.com/MiniBtMaster/pylightcharts/blob/main/docs/advanced/api-implementation-report.md)。

## 金融パネル（TradingView 風ウィジェット）

チャートエンジンの上に、`pylightcharts` は**パネル層**（`pylightcharts.panels`）を提供します。
これは TradingView のウィジェット群を、**同じホストページ上**の DOM コンポーネントとして
再実装したものです。追加のチャートインスタンスは不要なので、数百行のテーブルや
ヒートマップのタイルも軽量なままです。パネルは `Window`（チャートの `win`、
またはチャートを持たない `QtPanel`）上に作成し、Python から操作します。

```python
from pylightcharts import QtPanel
from pylightcharts.panels import Column, DataGrid, Heatmap, MarketData, TickerTape

panel = QtPanel()
MarketData(panel.win, groups, columns=[Column('symbol', '代码'), ...])
Heatmap(panel.win, [{'symbol': '聚乙烯', 'value': 9, 'chg_pct': 1.2}, ...],
        color_scheme='cn')
TickerTape(panel.win, items, speed=70)
panel.get_webview().show()
```

| パネル | TradingView のウィジェット |
|---|---|
| `QuoteBoard` | 気配値ページ：種別/取引所のチップ + グリッド + ティッカー + 読み込み中/空の状態 |
| `SymbolSearch` / `AlertDialog` | 銘柄ピッカー / 価格アラートダイアログ |
| `IndicatorPicker` / `TemplatePicker` | インジケーターブラウザ（★お気に入り付き） / インジケーターテンプレート |
| `DataGrid` / `Column` | マーケットテーブルのプリミティブ |
| `MarketData`, `Watchlist` | Market Data / Market Overview / Market Summary / Watchlist |
| `Screener` + `FilterBar` | Screener（条件、名前付きプリセット、JSON での永続化） |
| `Heatmap` (`StockHeatmap` / `CryptoHeatmap` / `EtfHeatmap` / `ForexHeatmap`) | Stock / Crypto / ETF / Forex Heatmap |
| `Ticker` (`TickerTape` / `TickerTag` / `SingleTicker` / `Tickers`) | Ticker Tape / Tag / Single ticker / Tickers |
| `OrderTicket` | 買い / スプレッド / 売りのチケット |
| `QuoteHeader` / `SymbolInfo` / `SymbolOverview` / `MiniChart` | Symbol Info / Symbol Overview / Mini Chart |
| `TechnicalAnalysis` (+ `ta_summary`) | Technical Analysis（ゲージ + オシレーター / 移動平均のテーブル） |
| `SeasonalChart` (+ `seasonal_monthly`) | Seasonal Chart |
| `EconomicCalendar` / `FundamentalData` / `CompanyProfile` / `BrokerRating` / `BrokerReviews` | 銘柄詳細のシェル |
| `NewsFeed` / `TopStories` / `TextBlock` | Top Stories / ニュース |

- **テーマ**：すべてのパネルはウィンドウのテーマに従います — `chart.win.theme('light')`
  （または既定の `'dark'`）。その後に作成したパネルもテーマを引き継ぎます。両方のスキンがスタイル済みです。
- **データ**：このライブラリは**マーケットデータを同梱しません** — 行 / 項目 /
  気配値はホスト側が供給します（minibt、tqapi、CSV など）。ニュース / ファンダメンタル / カレンダー / ブローカーの
  各パネルは、UI とデータ契約のシェルです。
- **サンプル**：`examples/13_panels/01_data_grid.py` … `15_alert_dialog.py`
  （0.1.6 で追加されたのは `12_quote_board`、`13_symbol_search`、
  `14_indicator_picker`、`15_alert_dialog` です。それぞれ `--check` に対応し、
  一部は `--snapshot` にも対応しています）。
  `10_gallery.py` は、すべてのウィジェットをスクロール可能なギャラリーにしたものです。ガイド：
  [`docs/guide/panels.md`](docs/guide/panels.md)。

## 謝辞 / ライセンス

- Python 層、GUI バックエンド、描画プラグインは
  [lightweight-charts-python](https://github.com/louisnw01/lightweight-charts-python)（MIT）から派生しています。
- チャートエンジンは
  [TradingView Lightweight Charts™](https://github.com/tradingview/lightweight-charts)（Apache-2.0）です。
  `NOTICE` を参照してください。

## lightweight-charts-python からの移行
`pylightcharts` は、元のパッケージのすべてのクラス、メソッド、モジュールレベルの名前を維持しています
（`tests/test_lwc_compat.py` で検証）。そのため、既存のコードは 1 行のシムで動作します。

```python
from pylightcharts.compat import install_alias
install_alias()                     # before any `import lightweight_charts`

import lightweight_charts            # -> pylightcharts
lightweight_charts.widgets.QWebEngineView = MyPyQt6WebEngineView   # patching still works
```

または、インポートを直接変更します。

```diff
- from lightweight_charts.util import Events, JSEmitter
- from lightweight_charts.widgets import QtChart
+ from pylightcharts.util import Events, JSEmitter
+ from pylightcharts.widgets import QtChart
```

## Qt との統合

デスクトップアプリケーションの内部では、`QtChart` がチャートを `QWebEngineView` に埋め込みます。

```python
from PyQt6.QtWidgets import QApplication
from pylightcharts.qt import prepare_qt

prepare_qt('PyQt6')          # pick the binding *before* QApplication
app = QApplication([])

from pylightcharts.widgets import QtChart
chart = QtChart(toolbox=True)
chart.set(df)
chart.get_webview().show()
app.exec()
```

`QtWebEngineWidgets` は `QApplication` が生成される前にインポートする必要があります。
`prepare_qt()` を最初に呼ぶのはそのためです。`$PYLIGHTCHARTS_QT` を使えば、これを呼ばずにバインディングを選べます。
マルチチャートの `sync()`、スクリーンショット、Chromium のネットワークノイズなどの詳細は、
`docs/guide/qt.md` にあります。

## サンプル

### API 全体ツアー（`examples/11_api_tour/`）

**すべての公開 API** を順に試せる、実行可能なビジュアルスクリプトです。各ファイルは
`build(chart)`（テストでヘッドレスに駆動できるようにするため）と、ウィンドウを開く `main()` を公開しています。

| ファイル | 内容 |
|---|---|
| `01_chart_and_data.py` | `set` / `update` / `update_from_tick` / `batch`、レイアウト、グリッド、クロスヘア、凡例、ウォーターマーク、ローソク足と出来高のスタイル、精度、オプション |
| `02_series_types.py` | Line/Area/Bar/Baseline/Histogram/Candlestick、価格ライン、マーカー、データの読み出し、座標変換、順序、ペイン |
| `03_scales_and_queries.py` | 時間軸（スクロール / 範囲 / 変換 / フォーマッター）、価格軸、ペインのクエリ、`chart_options`、`chart_element`、`version` |
| `04_events.py` | click / dblclick / crosshair / range / visible-time / size / data-changed / new-bar / search / hotkeys |
| `05_drawings.py` | 13 種類すべての描画ツールと `vertical_span`、および `update` / `delete` / `options` |
| `06_panes.py` | ペイン、stretch / height / preserve、ペインプリミティブ、ペインレベルのシリーズ |
| `07_indicators.py` | 17 種類すべてのインジケーター、`add_indicator`、`add_computed_series` |
| `08_custom_series.py` | すべての図形 + プリセット + カスタムペインビューの仕様 |
| `09_plugins.py` | マーカー / 上昇・下降 / テキスト・画像ウォーターマークのライフサイクル |
| `10_primitives.py` | 宣言型のシリーズ・ペインプリミティブ、すべての拡張ポイント |
| `11_callbacks.py` | フォーマッター、目盛りマーク、価格フォーマット、オートスケール、定数 |
| `12_numeric_and_scale.py` | YieldCurve / Options チャート、カスタム水平スケール |
| `13_workspace.py` | テーブル、トップバーのウィジェット、ツールボックス、サブチャート、同期、スクリーンショット |
| `14_multi_chart_layout.py` … `23_fill_between_gaps.py` | ページのトップバー、UI 全体のテーマ、ツールチップ、2 銘柄、無限履歴、インジケーターペイン、ステム/散布図、複数行テキスト、NaN ラインと fill-between のギャップ - `examples/11_api_tour/README.md` を参照 |
| `24_layouts_and_legend_settings.py` | 移行向けの拡張：2D の `arrange_tiles(dividers=True)` レイアウト、凡例の歯車（`enable_legend_settings`）、固定表示の凡例行（`pin_legend_row`）、シリーズのスタイルヘルパー（`set_line_*` / `set_price_visible` / `is_visible`）+ `chart.remove()` |
| `25_live_value_table.py` … `27_volume_profile_live.py` | クロスヘアに連動する値テーブルとライブ更新（`25`）、およびボリュームプロファイルのレシピ（`26` は静的、`27` はライブ） - マウスに追従し、表示範囲の右端に固定される出来高分布 - `examples/11_api_tour/README.md` を参照 |

### 金融パネル（`examples/13_panels/`）

パネル層を扱う 10 本のスクリプトです（モックデータ、`--snapshot`、`PYLIGHTCHARTS_QT=`
で切り替え可能）：`01_data_grid`、`02_sparkline`、`03_market_data`、`04_ticker_and_quote`、
`05_heatmap`、`06_seasonal`、`07_screener`、`08_details`、`09_technical`、そして
`10_gallery.py` — 最後のものはすべてのウィジェットをスクロール可能なグリッドに並べ、一度に
見渡せます — さらに `11_sim_account_shell.py`（注文チケット付きの、ページ全体の模擬口座
シェル）があります。[`examples/13_panels/README.md`](examples/13_panels/README.md) を参照してください。

### 個別のサンプル（元の 10 本）

`examples/1_setting_data` … `examples/12_browser` は、それぞれ独自のデータで 1 つのトピックに絞っています。
OHLCV の読み込み、ライブバー、ティック更新、インジケーターライン、スタイル設定、
コールバック、組み込みインジケーター、ヘッドレスでの PNG レンダリング、ブラウザタブ内のチャート
（`examples/12_browser/static.py` と `live.py`。どちらもメインペインに SMA、サブペインに
RSI を表示）、カスタムシリーズ、PyQt6 ウィンドウを扱います。まずは
`examples/1_setting_data/setting_data.py` から始めてください。

## 開発

```bash
# build the JS bridge + vendor the engine into pylightcharts/js/
cd jslib && npm install && npm run build

# install the python package in editable mode
cd .. && pip install -e .

# ...or use the requirement files (pyproject.toml stays the source of truth)
pip install -r requirements.txt        # runtime only
pip install -r requirements-dev.txt    # + tests, e2e, docs, build
```

### テスト

```bash
# unit tests: assert on the JS generated by the python bridge (no browser)
python -m pytest -m "not slow"

# e2e: run the built bundle in headless Chromium and check rendered pixels
python tests/e2e/smoke.py

# headless rendering tests (Playwright or a local Chrome/Edge)
python -m pytest tests/test_headless.py

# full stack: real pywebview window + real chart engine (needs a desktop session)
python tests/e2e/full_stack.py

# performance: JSON vs binary bulk data transfer
python tests/e2e/benchmark.py 100000
```

CI（`.github/workflows/ci.yml`）はバンドルをビルドし、コミットされた成果物が最新であることを確認し、
Linux/Windows/macOS でユニットテストを実行し、ヘッドレス Chromium でレンダリングし、
wheel に JS アセットが含まれていることを検証します。

### 先送りした作業

実現は可能ですが、あえてまだ実装していない機能 — レイアウト区切りのタッチドラッグ、
グリッドレイアウト、チャートの破棄、スパンプリミティブの `zOrder`、… — は、
それぞれの対象ファイルとスケッチとともに
[`docs/advanced/deferred.md`](https://github.com/MiniBtMaster/pylightcharts/blob/main/docs/advanced/deferred.md) にまとめてあります。
ソースに素の `TODO` を残す代わりに、そこへ項目を追加してください。

### パッケージング

```bash
cd jslib && npm run build      # regenerate pylightcharts/js/*
cd .. && python -m build       # sdist + wheel (JS assets are package-data)
twine upload dist/*
```

ビルド済みの `pylightcharts/js/` のファイルは、Node がなくても
`pip install` が動作するよう、意図的にコミットされています。コミットの前には必ず `npm run build` を実行してください。

### ブリッジのルール

- 投げっぱなしの呼び出しは `Window.invoke` を通します（トランスポートが
  `;undefined` を付加するため、pywebview が生きているチャートオブジェクトをシリアライズすることはありません）。
- **オブジェクトを返す**メソッドは、`store_as=...` を使うか、プリミティブなら
  `invoke_get` を使う必要があります。生きているオブジェクトを `invoke_get` で返すと壊れます。
- 往復の呼び出しは直列化され、リクエスト ID で対応付けられます。JS のエラーは `None` を返す代わりに
  `pylightcharts.util.BridgeError` を送出します。
- チャートとシリーズは同じメソッド名（`apply_options`）を共有しますが、
  MRO による隠蔽を避けるため、意図的に分けてあります（`series_options`、`data_points`）。
- lightweight-charts のアップグレード：`npm pack lightweight-charts@X` を実行し、
  破壊的変更に対応して `npm run build` を行い、e2e スイートを実行します。

### 汎用ブリッジ

新機能の追加で TypeScript に手を入れる必要はありません。生きているどのチャートオブジェクトのどのメソッドも、
Python から呼び出せます。

```python
chart._invoke('addSeries', 'Area', 'my area', {'lineWidth': 2}, handle)
chart.win.invoke(f'{series.id}.series', 'applyOptions', {'lineWidth': 3})
```

ハンドルは、`Lib.register(...)` で登録したものか、ドット区切りのウィンドウパス
（`window.abcdefgh.chart`）のいずれかです。`{'$ref': handle}` 引数は生きている
JS オブジェクトに解決されるため、オブジェクトを受け取る API も動作します。

```python
series.attach_primitive('myPrimitive')   # -> attachPrimitive({"$ref": "myPrimitive"})
```

`jslib/src/general/rpc.ts` を参照してください。

### オプションの完全カバレッジ

`apply_options(**kwargs)` は、基盤となる API のあらゆるオプションを受け付け、
`snake_case` のキーを `camelCase` に自動で変換します。

```python
chart.apply_options(auto_size=True, localization={'price_format': {'precision': 4}})
chart.time_scale_options(right_offset=5, bar_spacing=8)   # time scale
series.apply_options(line_width=3, crosshair_marker_visible=False)
get = chart.get_price_scale('left'); get.set_mode('logarithmic')
```

### インジケーター

純粋な pandas による実装で、追加の依存関係はありません。オーバーレイは価格ペインに置かれ、
オシレーターは自動的に専用のペインを持ちます。

```python
chart.add_sma('close', 20)
chart.add_ema('close', 50, color='#2196F3')
chart.add_bollinger('close', 20, 2)      # -> (upper, middle, lower)
chart.add_donchian(20)
chart.add_vwap()

chart.add_rsi(14)                        # own pane + 70/30 guide lines
chart.add_macd()                         # own pane -> (macd, signal, histogram)
chart.add_stochastic()                   # own pane -> (%K, %D)
chart.add_atr(14)
chart.add_adx(14)                        # own pane -> (adx, +DI, -DI)
chart.add_obv()                          # own pane (needs volume)
chart.add_cci(20)
chart.add_williams_r(14)
chart.add_mfi(14)
chart.add_roc(12)
chart.add_keltner(20, 2.0)               # overlay -> (upper, middle, lower)
```

生の値：`from pylightcharts import indicators; indicators.rsi(close, 14)`。
RSI、OBV、CCI、%R、ROC、MFI、ボリンジャーバンドは浮動小数点精度で TA-Lib と一致します。
ATR と ADX はそれぞれ約 1e-4、約 0.1 の範囲内で一致します（Wilder 方式の
累積による丸め）。

#### インジケーターはデータに追従します

すべてのインジケーターは自動的に再計算されます。`chart.set()` では全体を再送し、
`chart.update(bar)` では 1 点だけを更新します（再帰型のインジケーターが
全体を実行した場合と数値的に同一になるよう、ウォームアップ用のウィンドウから再計算します）。
`add_computed_series(compute, name, ...)` で独自のものを追加できます。

#### ティックのバッチ処理

ブリッジの呼び出しは 1 回ごとに WebView との往復が 1 回発生するため、連続する呼び出しは `chart.batch()` で包みます。

```python
with chart.batch():
    for tick in ticks:
        chart.update(tick)      # flushed as a single script
```

#### コンフレーション（非常に大きなデータ）

コンフレーションは通常のシリーズオプションなので、ブリッジからそのまま利用できます。

```python
chart.apply_options(enable_conflation=True, precompute_conflation_on_init=True)
series.apply_options(enable_conflation=True)
```

### カスタムシリーズ（宣言型レンダリング）

カスタムシリーズで難しいのは、毎フレーム同期的に実行される `draw()` です — Python はこれに
関与できません。そこでプロトコルは作業を分割します。
**Python がデータ更新ごとに一度だけ図形を計算し、汎用の JS レンダラーが毎フレーム
それを描画します。**

```python
from pylightcharts import shapes

series = chart.add_custom_series('range bars', pane_index='new')
series.set(df, shapes=lambda row: shapes.range_bar(row['low'], row['high']))
```

図形ビルダー：`rect` `band` `line` `circle` `marker` `text` `polyline`。
プリセットとして `range_bar` `box_plot` `error_bar` `stem` があります。

`shapes.stem(price, baseline=0.0, style='dashed', cap=False)` は `baseline` から `price` までの
縦棒を描きます — 取引ごとの損益、平均からの乖離、価格帯別出来高などを、共通の軸から
垂れ下がる棒として簡単に表示する方法です。

```python
series.set(df, shapes=lambda row: shapes.stem(row['pnl'], color=row['color'],
                                              cap=True))
``` 縦方向のアンカーは価格で、
横方向のオフセットはバー単位です（`-0.4..0.4` で 1 本のバーの幅になります）。ただし
`shapes.marker` は例外で、その `offset`/`size` は**ピクセル**単位です（ズームの影響を受けないグリフ。
`marker=` には minibt の `Markers` の名前を指定します：`triangle` `inverted_triangle`
`arrow_up` `arrow_down` `circle` `circle_cross` `circle_dot` `circle_x`
`circle_y` `square` `dot` `dash` `cross` `asterisk` `triangle_dot`）。

```python
shapes.box_plot(low, q1, median, q3, high)
shapes.polyline([(0.0, 1.0), (0.4, 2.0)], fill_color='rgba(0,0,0,0.2)')
shapes.text(price, 'label\nsecond line',   # multi-line (like bokeh's LabelSet)
            offset_x=6, font_weight='bold',              # pixel offset / bold
            background_color='#222', padding=4)         # label box + padding
```

各データ項目は、`value`、`low`、`high`（オートスケールと最終値用）、
`color`、`shapes` を持てます。

### v5 プラグイン（マーカー / 上昇・下降マーカー / ウォーターマーク）

v5 ではマーカーとウォーターマークが*プリミティブ*に移りました。それぞれに完全な Python ラッパーがあります。

```python
m = series.markers_plugin()          # SeriesMarkersPlugin (ISeriesMarkersPluginApi)
m.markers(); m.apply_options(z_index=1); m.detach(); m.get_series()

up = series.up_down_markers_plugin(positive_color='#26a69a')
up.set_data(df); up.update(point); up.markers(); up.set_markers([...])
up.clear_markers(); up.apply_options(negative_color='#ef5350'); up.detach()

text = chart.text_watermark_plugin('pylightcharts', 48, 'rgba(180,180,220,0.4)')
text.apply_options(horz_align='left'); text.get_pane(); text.detach()

img = chart.image_watermark_plugin('logo.png', max_width=120)
```

### 関数値のオプション（フォーマッターとプロバイダー）

コールバックは描画ループの内部で同期的に実行されるため、小さな JS 本体を登録し、
任意のオプションパスに注入します。

```python
chart.register_js_callback('vol', ['price'], "return (price/1e6).toFixed(1)+'M'")
chart.set_tick_mark_formatter('vol')            # timeScale.tickMarkFormatter

series.set_price_format_formatter('vol')        # merge-safe priceFormat.formatter
series.set_autoscale_info_provider('vol')       # series.autoscaleInfoProvider

chart.set_option_callback(f'{chart.id}.chart', 'applyOptions',
                          'localization.priceFormatter', 'vol')
chart.set_price_formatter_callback('vol'); chart.set_time_formatter_callback('vol')
```

### 宣言型プリミティブ

```python
chart.register_js_callback(
    'draw', ['target', 'pc', 'view', 'prim'],
    "const y = prim.series.priceToCoordinate(100); /* draw with target.useBitmapCoordinateSpace */")
prim = chart.create_series_primitive({
    'paneViews': [{'draw': 'draw', 'zOrder': 'top'}],
    'priceAxisViews': [{'coordinate': 'coord', 'text': 'label'}],
    'hitTest': 'hit', 'autoscaleInfo': 'scale',
})
prim.attach_to(series)

pane_prim = chart.create_pane_primitive({'paneViews': [{'draw': 'draw'}]})
pane_prim.attach_to(chart, 0)
```

### カスタム水平スケール

```python
class MonthChart(Chart):
    _horz_scale_name = 'month'
    _horz_scale = {
        'formatTickmark': (['tickMark', 'loc'], "return 'M' + tickMark"),
        'formatHorzItem': (['item'], "return 'M' + item"),
    }
```

### 定数とエミュレーションのチェック

```python
from pylightcharts.constants import LineStyle, PriceScaleMode, CrosshairMode, verify
chart.apply_options(crosshair={'mode': CrosshairMode.Magnet})
chart.price_scale(mode=PriceScaleMode.Logarithmic)
series.apply_options(line_style=LineStyle.Dashed)
verify(chart)          # [] when the Python constants match the embedded engine
```

### 価格ライン、データの読み出し、イベント

```python
line = series.create_price_line(105.0, color='#00e676', title='entry')
line.apply_options(line_visible=False)
line.remove()

series.price_to_coordinate(105)        # <-> series.coordinate_to_price(y)
series.data_by_index(10)               # individual bar
series.data_points()                   # everything the chart holds
series.pop(2); series.last_value_data(); series.bars_in_logical_range(0, 50)
series.series_type(); series.get_pane_index()
series.move_to_pane(2); series.series_order(); series.set_series_order(3)

chart.scroll_to_real_time(); chart.scroll_to_position(3, animated=False)
chart.reset_time_scale(); chart.set_visible_logical_range(0, 60)
chart.get_visible_range(); chart.get_visible_logical_range()
chart.time_to_coordinate(t); chart.coordinate_to_time(x)
chart.logical_to_coordinate(l); chart.coordinate_to_logical(x)
chart.pane_height(0); chart.set_pane_height(300, 0)
chart.pane_stretch_factor(0); chart.pane_size(); chart.pane_series_count(0)
chart.version(); chart.auto_size_active(); chart.remove()
chart.set_crosshair_position(100.0, some_time); chart.clear_crosshair_position()

chart.get_price_scale('right').get_visible_range()
chart.get_price_scale('right').set_auto_scale(False)
chart.pane_price_scale(0, 'left')

chart.events.crosshair_move += handler      # handler(chart, time, price)
chart.events.dblclick += handler
chart.events.click.unsubscribe()
```

### マルチチャートの同期

```python
price = Chart(); volume = Chart()
price.sync(volume)                       # volume follows price pan/zoom
price.sync(volume, crosshairs_only=True)
```

### ネイティブペイン（lightweight-charts v5）

```python
chart.add_pane()
chart.create_area(name='close', pane_index=1)
chart.add_series('Line', 'ma20', pane_index=1, color='#0ff')
chart.set_pane_stretch(1, 1.5)
chart.pane_count()
```

`pane_index='new'` は新しいペインを作成し、現在のペイン数を超えるインデックスを渡すと、
その間のペインも作成されます。

### 描画ツール

トレンドライン / 水平線 / 垂直線 / レイ / ボックスに加えて、次のものがあります。

```python
chart.fibonacci(t1, p1, t2, p2, levels=(0, 0.382, 0.5, 0.618, 1))
chart.measure(t1, p1, t2, p2)                       # price %, bar count
chart.parallel_channel(t1, p1, t2, p2, offset=5)    # second line 5 price units away
chart.position(t1, entry, t2, target, risk_ratio=1.5)   # profit + stop zones
chart.long_position(t1, entry, t2, target)          # aliases
chart.short_position(t1, entry, t2, target)

chart.andrews_pitchfork(t1, p1, t2, p2, t3, p3)     # 3 points
chart.triangle(t1, p1, t2, p2, t3, p3)              # 3 points
chart.fibonacci_extension(t1, p1, t2, p2, t3, p3)   # impulse + retracement
chart.gann_fan(t1, p1, t2, p2)                      # 1x1 plus steeper/shallower rays
```

`toolbox=True` を指定すると、これらはインタラクティブにも使えます
（Alt+F / M / C / P / A / G / X / N）。

### 数値軸とフォーマッター

```python
from pylightcharts import YieldCurveChart, OptionsChart

curve = YieldCurveChart()                 # x axis = duration in months
series = curve.add_series('Line', 'rate')
series.set(pd.DataFrame({'time': [1, 3, 12], 'rate': [4.2, 4.0, 3.6]}))

surface = OptionsChart()                  # x axis = strike

chart.set_price_formatter(decimals=2, thousands=True, prefix='$')
chart.set_time_formatter('YYYY-MM-DD HH:mm')
chart.register_js_formatter('eur', "value => '\u20ac' + value.toFixed(2)")
chart.set_price_formatter(name='eur')
```

### 大規模データ

2000 行以上の DataFrame は、JavaScript のソースとして送る代わりに、base64 の列優先 Float64
バッファとして転送し、ブラウザ側で再構築します（`Lib.decodeData`）。10 万本のバーでの実測：
**1.56 秒 -> 0.54 秒（約 3 倍）**、
50 万本：**8.9 秒 -> 3.2 秒**。`pylightcharts.util.BINARY_DATA_THRESHOLD` で調整できます。

### ヘッドレス / サーバーサイドレンダリング

```python
from pylightcharts.headless import HeadlessChart

chart = HeadlessChart(width=1200, height=700)
chart.set(df)
chart.add_sma('close', 20)
chart.add_rsi(14)
chart.render('report.png')        # PNG bytes, no window required
chart.to_html()                   # or grab the standalone HTML
```

Playwright がインストールされていればそれを使い、なければローカルの Chrome/Edge をヘッドレスモードで使います
（`PYLIGHTCHARTS_CHROME` でブラウザのパスを上書きできます）。


## pylightcharts の拡張

`pylightcharts` が上流の Lightweight Charts /
lightweight-charts-python の API の上に追加した API です。新しい追加分はここに（簡潔に）記載し、
詳細は `docs/` に記載します。

| API | 内容 |
|---|---|
| すべてのシリーズファクトリとインジケーターの `legend_toggle=` / `legend=` | 凡例の行とその目のアイコンを描画する、またはどちらも描画しない |
| `chart.horizontal_span(low, high, color=, opacity=, filled=, pane_index=)` | 網掛けの価格帯（サポート / レジスタンス）。`pane_index=` でサブペインに配置 |
| `chart.fill_between(upper, lower, color=, opacity=)` / `upper.fill_between(lower)` | 2 本のシリーズラインの間（バンドの本体）を塗りつぶす |
| `horizontal_span` / `fill_between` / `vertical_span` の `opacity=` | あらゆる色形式に対する塗りのアルファ値。輪郭線はくっきりしたまま |
| `chart.pane_separator(color=, hover_color=, enable_resize=)` | ペイン間の 1px の区切り線のスタイル変更 / 非表示 |
| `chart.pane_height()` / `set_pane_height(px, i)`（`IPaneApi` のラッパー） | ペインの絶対的な高さの取得 / 設定 |
| `chart.mark_swings(...)` + `indicators.swing_points` | `length` 本のフラクタルによるスイング高値 / 安値を、その価格をマーカーのテキストとして表示（Lightweight Charts 自体はマーカーを描くだけ） |
| `chart.add_zigzag(threshold=)` + `indicators.zigzag` | 波段線：最小の戻り率を超えた後に交互に現れるピボットを、ラインとして描画し、インジケーターのように同期を保つ（`include_unconfirmed` はまだ確定していない最後の区間を表示し、`inverted=` は反転した価格軸向け） |
| `BrowserChart` + `to_html()` / `save_html()` / `open_in_browser()` | 自己完結した 1 枚の HTML ページ（エンジン + ブリッジ + スタイルをインライン化） - `BrowserChart(...).show()` が書き出して開きます。サーバー、Node、追加の依存関係なしで使えるブラウザ表示 |
| `BrowserChart(live=True)` + `LiveServer` | ブラウザタブでのライブチャート：標準ライブラリの HTTP + Server-Sent-Events ストリーム（ロングポーリングへのフォールバックあり、LAN/スマートフォンでの閲覧用に任意の `token=`）が、すべての `set`/`update`/`apply_options` をページに届け、ウィジェットのコールバックは Python に送り返されます - 依存関係はやはりゼロで、ディスクには何も書き込みません |
| `color_by(...)` / `series.color_by(...)` / `chart.color_by(...)` | ポイントごと / 条件付きの色：あらゆるシリーズ（インジケーターラインを含む）とメインのローソク足で、エンジンの `color` / `wickColor` / `borderColor` キーを埋めます（`docs/guide/charts.md#conditional-colours`） |
| `Chart(..., keyboard=True, keyboard_step=0.1)` + 矢印キー | 組み込みのナビゲーション：矢印キーで表示ウィンドウの移動 / ズーム（最新のバーが画面に入ったら、縮小しても右端を固定）、`Shift` で大きなステップ、`Ctrl`+矢印と `PageUp/Down` で 1 ページ分、`Home`/`End`、`Ctrl+0` で全体表示。ユーザーの `hotkey()` が優先され、文字入力は無視されます |
| `chart.win.page_topbar()` | ウィンドウ全体に広がり、すべてのチャートの上に留まるトップバー（`chart.topbar` は 1 つのチャートの内部にあり、そのチャートとともに縮みます） |
| `chart.win.layout` (`Layout`) | ウィンドウをチャートで敷き詰める：`vertical()` / `horizontal()` / `arrange(kind, count)` / `single()`。既定では独立しており（`sync=True` でパン/ズーム/クロスヘアを連動、`sync='crosshair'` ではクロスヘアのみ）、新しいチャートに内容を供給する `on_create=` と、チャート間のドラッグ可能な区切り（`divider_size=` / `set_divider(...)`）があります |
| `Layout.arrange_tiles(tiles, dividers=True)` + `Lib.clearLayoutTiles` | **2D タイルレイアウト**（TradingView 風の「上に 1 つ / 下に 2 つ」）：`tiles` は `(width, height)` の割合を並べたリストです - `[(1.0, 0.5), (0.5, 0.5), (0.5, 0.5)]`。単一の列/行も、行フロー（2D）のレイアウトも、行と行の間、および行内の列と列の間に**ドラッグ可能な区切り**を持ちます。フロートレイアウト（`arrange()` / `single()`）に戻すと `clearLayoutTiles` を発行し、通常のフロートのジオメトリを復元します（`examples/11_api_tour/24_layouts_and_legend_settings.py`） |
| `series.enable_legend_settings(callback)` | シリーズの凡例行に**設定（歯車）ボタン**を追加します。クリックすると `callback(series, x, y)`（WebView 内のクリック位置。設定カードを凡例の隣にポップアップできます）が呼ばれます。「凡例の上のマウス移動をすべて監視する」代わりに、クリック 1 回分の往復で済みます |
| `series.pin_legend_row(True)` | シリーズの凡例行を**常に表示**したままにします（既定では、クロスヘアがバーの上にあるときだけ行が表示されます）。これにより、インジケーターの名前 + 目 + 歯車が画面に残ります |
| `series.enable_legend_menu(config, callback)` | `enable_legend_settings` の **Qt 不要**版：歯車ボタンに付く自己完結した JS メニュー（`参数` / `线型` / `线宽` / `线颜色` / `其它设置`）。変更のたびに `callback(series, kind, payload)` が呼ばれます |
| `series.remove_legend_row()` | シリーズの凡例行を完全に削除します（冪等） — JS 側はすべてのシリーズに行を作るため、`legend=False` が現在内部で使っているものです |
| `chart.enable_legend_collapse()` | インジケーターの凡例行の下にある、TradingView 風の `∧` / `∨ N` 折りたたみボタン（凡例行がないときは自動的に隠れます） |
| `chart.horizontal_line(..., text=, label_visible=, label_background_color=, label_text_color=, label_font=)` | ラベルを**ペイン内**に描画します（表示範囲の左端に固定）。`axis_label_visible=False` は、隠れたバッジが価格軸を広げることも防ぐようになりました |
| `series.remove_markers(ids)` + `marker(..., size=)` | 多数のマーカーを 1 回の再描画で削除し、v5 のマーカーの `size` を渡す |
| `series.skip_gap_segments()` / `prefer_single_gap()` / `repaint_gaps()` | NaN で途切れるレンダラーの調整：非表示の `fill_between` のキャリアを分割しない、リアルタイムのラインでは単一シリーズの透明ギャップ経路を優先する、色の変更後に再送する |
| `series.set_line_width` / `set_line_color` / `set_line_style` / `set_price_visible` / `is_visible` | インジケーターラインの実行時のスタイル/表示のヘルパー：線幅、色、破線スタイル（`solid` / `dashed` / ...）、価格ライン / 価格ラベルのフラグ（LWC の `priceLineVisible` / `lastValueVisible`）、および Python から最後に設定した表示状態 |
| `chart.remove()` | チャートの破棄で、その `.handler` DOM ラッパーも削除されるようになりました（`Handler.destroy`）。以前はエンジンだけが破棄され、残ったボックスが古いサイズ / 位置のまま、次に作成されるチャートを覆っていました |
| `series.delete()` + `chart.remove_pane(index)` | シリーズを削除し、それがペイン内の最後の 1 本だった場合はペインも削除します。凡例行（ラベル + 目）は消え、後続のペイン（とその `series.pane_index`）は繰り上がります - そのため、インジケーターのサブチャートを実行時に入れ替えられます（`examples/11_api_tour/19_indicator_panes.py`） |
| `chart.win.theme('light'\|'dark')` + `pylightcharts.themes` | 1 回の呼び出しで UI 全体のテーマを設定：ルートの CSS 変数（トップバー、凡例、メニュー）、凡例のテキスト色とその目のアイコン、そしてすべてのチャートの背景 / グリッド / クロスヘア / ローソク足 / 出来高 / 区切り / 軸の色 - 後から作成したチャートも引き継ぎ、既存のテーブルも色が更新され、個別のセッターは引き続きこれを上書きします（`docs/guide/options.md#themes-whole-ui-light-dark`） |
| `chart.infinite_history(loader, page=, threshold=)` + `pylightcharts.history` | 公式の無限履歴デモ：チャート自身の `events.range_change`（`barsInLogicalRange().barsBefore`）が `loader(count[, before])` に古いバーを要求し、ビューポートが動かないように先頭へ追加されます - インジケーター（メインペインとサブペイン）もそれに合わせて延長され、出来高は再送され、描画は保持されます（`docs/guide/infinite-history.md`） |
| `chart.add_symbol(name, data, kind=, scale=, margins=, ...)` + `chart.scale_margins(right=, left=)` | 公式チュートリアルの 2 つの価格軸：メインのローソク足は右の軸に残し、2 つ目の銘柄をローソク足 / バー / ライン / エリア / ベースライン / ヒストグラムとして左の軸にオーバーレイします（またはマージンを使って重ねて積みます）。銘柄名は価格ラインのラベルに表示されます（`docs/guide/two-price-scales.md`） |
| `series.tracking_tooltip(...)` / `series.magnifier_tooltip(...)`（メインシリーズ用は `chart.` 版） | 公式チュートリアルの 2 種類のクロスヘアツールチップを 1 回の呼び出しで：カーソルに追従する（端の近くでは反転する）ボックス、またはペインの上部に固定された半透明の帯。`title=` / `fields='auto'`（OHLC） / `field_labels=` / `decimals=` / `time_format=` / `color_by_candle=` / サイズと色のオプション、`hide()`/`show()`/`set_mode()`/`remove()`。背景/テキストはテーマの CSS 変数に従い、タイトルと枠はシリーズの色を使います（`docs/guide/tooltips.md`） |
| `Table.set_colors(background_color=, border_color=, text_color=, section_color=)` | 構築後にフローティングテーブルのスタイルを変更します（コンストラクターが色を DOM に書き込むため、`Window.theme` が既存のテーブルに使うのがこれです） |
| `Table.set_position(position='top-right', margin_x=, margin_y=)` | フローティングテーブルを 4 つの角のいずれかに固定し、最も近い 2 つの辺から内側にずらします - 同じ 2 つのキーワードが `create_table(...)`/`chart.create_table(...)` でも使えます（`docs/guide/table.md`） |
| `Chart(..., attribution_logo=True)` | ウィンドウごとの TradingView ロゴ（既定ではオフ） |
| `pylightcharts.compat.install_alias()` | `lightweight_charts` のコードをそのまま実行する |
| `chart.register_js_callback` + `create_series_primitive` / `create_pane_primitive` | Python からの宣言型 v5 プリミティブ |
| `chart.set_price_formatter` / `set_time_formatter` | 宣言型の目盛りフォーマッター（`Lib.resolveFormatter`） |
| `add_custom_series(spec={...})` + `view.visibleBars()` / `scope.mediaSize.width` - **ボリュームプロファイルのレシピ** | 宣言型のカスタムシリーズ API で水平の出来高分布を作ります。0 ラインは**表示ペインの右端**に固定され（`scope.mediaSize.width`、出来高バーと面一）、値はクロスヘアに追従し（最も近い `bar.x`）、`series.applyOptions({})` で再描画を強制します - クロスヘアの移動だけでは `rendererDraw` は再実行**されません**。メインペインへのオーバーレイ（価格ビン）としても、専用ペイン（ビンのインデックス、重ね合わせたヒストグラム）としても動作します - `examples/11_api_tour/26_volume_profile.py`（静的）と `27_volume_profile_live.py`（ライブ。*リアルタイム更新がマウス追従に優先する*順序付き） |

ポイントごと / 条件付きの色（任意の条件でバー、ローソク足、ヒストグラムの値に色を付ける）は、
データから駆動する Lightweight Charts の機能です - 
[Charts and data](https://github.com/MiniBtMaster/pylightcharts/blob/main/docs/guide/charts.md#conditional-colours) を参照してください。

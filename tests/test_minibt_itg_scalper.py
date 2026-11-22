"""ITG Scalper（`tradingview.ITGScalper`）—— 逐条对照原 Pine 码的样式与行为。

原码：https://cn.tradingview.com/script/AcrZjl6Q-ITG-Scalper/  （© Complector, v4）

用户 2026-11-13 的要求：
- **均线不按条件变色**（原码 `cc=true` 会绿/红分段）→ 单色 aqua、宽 2；
- **其它样式照原指标复刻** → 买点绿色正三角（bar 下方）、卖点红色倒三角（bar 上方）、
  三角上写成交价（原码 `uselabel` 的 label，最多 50 个）、`plotshape` 分支可切回。
"""
import numpy as np

from minibt import LocalDatas
from minibt.indicators.tradingview import ITGScalper

import pytest


@pytest.fixture(scope='module')
def kline():
    return LocalDatas.test.kline


@pytest.fixture(scope='module')
def ind(kline):
    return kline.tradingview.ITGScalper()


def _texts(indicator):
    raw = getattr(indicator._plotinfo, 'signal_texts', None) or {}
    return {str(key): [v for v in (arr if arr is not None else [])
                       if isinstance(v, str)]
            for key, arr in raw.items()}


def test_lines_and_data_columns(ind):
    """原码的持久变量 buyprice/sellprice 也作为数据列输出 ✓"""
    assert ITGScalper.lines == (
        'out1', 'perc', 'goodlong', 'goodshort',
        'long_signal', 'short_signal', 'buyprice', 'sellprice')
    assert list(ind.columns) == list(ITGScalper.lines)
    # 只有 out1 画线，其它都是数据/信号
    isplot = ITGScalper.isplot
    assert isplot['out1'] is True
    for name in ('perc', 'goodlong', 'goodshort', 'buyprice', 'sellprice'):
        assert isplot[name] is False, name


def test_tema_line_is_single_aqua_two_px():
    """均线**不按条件变色**：一条 aqua 线、宽 2（原码 cc=false 分支）✓"""
    style = ITGScalper.linestyle['out1']
    assert style.line_color.upper() == '#00FFFF'
    assert float(style.line_width) == 2.0
    # 不再有绿/红条件着色相关的参数/样式
    assert 'cc' not in ITGScalper.params
    assert set(ITGScalper.linestyle) == {'out1'}


def test_signal_styles_follow_the_original():
    """买 = 绿色正三角（bar 下方）；卖 = 红色倒三角（bar 上方）；size 用引擎小号 ✓"""
    long_style = ITGScalper.signalstyle['long_signal']
    short_style = ITGScalper.signalstyle['short_signal']
    assert long_style.key == 'low'                 # location=belowbar
    assert long_style.color.upper() == '#00FF00'   # color.lime
    assert long_style.marker == 'triangle'         # shape.triangleup
    assert short_style.key == 'high'               # location=abovebar
    assert short_style.color.upper() == '#FF0000'  # iff(goodshort, red, yellow)
    assert short_style.marker == 'inverted_triangle'
    # 原码 size.small → 不写死像素，交给引擎默认（bokeh 12 / pylightcharts 8）
    assert long_style.size is None and short_style.size is None


def test_signals_alternate_and_prices_are_recorded(ind):
    """多空交替（last_tran 记忆）：买数 ≈ 卖数，buyprice/sellprice 有值 ✓"""
    buys = int(np.nansum(ind.long_signal.values))
    sells = int(np.nansum(ind.short_signal.values))
    assert buys > 0 and abs(buys - sells) <= 1
    assert np.nansum(ind.buyprice.values) > 0
    assert np.nansum(ind.sellprice.values) > 0


def test_every_signal_gets_its_price_text(ind):
    """原码 `uselabel` 的成交价文字：**每个**信号都有（不截断）✓

    曾经按原码注释「max 50」截断成"最近 50 个"，图上就出现"左边一段没标签"✗
    （用户截图 `tradingview/部分有信号标签部分没有.png`）。
    """
    texts = _texts(ind)
    longs, shorts = texts['long_signal'], texts['short_signal']
    buys = int(np.nansum(ind.long_signal.values))
    sells = int(np.nansum(ind.short_signal.values))
    assert len(longs) == buys and buys > 0
    assert len(shorts) == sells and sells > 0
    # 不再有「最多 N 个」的截断常量
    assert not hasattr(ITGScalper, 'MAX_LABEL_SIGNALS')
    # 文字就是成交价（截断到 8 位小数、去掉尾随 0）
    price = ITGScalper._price_text(4891.0)
    assert price == '4891'
    assert ITGScalper._price_text(4680.885999991) == '4680.88599999'
    assert all(float(t) > 0 for t in longs + shorts)


def test_use_label_off_gives_plotshape_only(kline):
    """`use_label=False` = 原码 `plotshape` 分支：只有三角、没有文字 ✓"""
    ind = kline.tradingview.ITGScalper(use_label=False)
    assert ind.params['use_label'] is False
    texts = _texts(ind)
    assert len(texts['long_signal']) == 0 and len(texts['short_signal']) == 0
    # 信号本身还在
    assert int(np.nansum(ind.long_signal.values)) > 0


def test_show_tema_and_show_signals_switches(kline):
    """`shc=false` 线不画（仍算信号）；`showtext=false` 信号与文字都不画 ✓"""
    no_tema = kline.tradingview.ITGScalper(show_tema=False)
    assert bool(np.all(np.isnan(no_tema.out1.values)))
    assert int(np.nansum(no_tema.long_signal.values)) > 0

    no_sig = kline.tradingview.ITGScalper(show_signals=False)
    assert int(np.nansum(no_sig.long_signal.values)) == 0
    assert int(np.nansum(no_sig.short_signal.values)) == 0
    texts = _texts(no_sig)
    assert len(texts['long_signal']) == 0


def test_noise_filter_changes_signal_count(kline):
    """`nfilter=false`（不过滤）信号明显变多 ✓"""
    on = kline.tradingview.ITGScalper()
    off = kline.tradingview.ITGScalper(noise_filter=False)
    assert int(np.nansum(off.long_signal.values)) > \
        int(np.nansum(on.long_signal.values))

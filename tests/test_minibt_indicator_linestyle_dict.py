"""`IndFrame.linestyle = {...}`（按线名的字典）必须真的生效 ✓

用户 2026-10-31 指正：`linestyle` 的底层就是字典
（`PlotInfo.linestyle: Addict[str, LineStyle]`，`LineStyleType` 代理读写的也是它），
而旧 setter 把 dict 赋给 `_plotinfo.line_style` —— 它的 setter **只认单个
`LineStyle`** → 传字典被静默忽略 ✗；用户改写后 MDim 分支里的
`getattr(self, f"_name")` 又是个**字面量** `"_name"` → AttributeError ✗。
"""
import pytest

from minibt.utils import LineDash, LineStyle


@pytest.fixture()
def macd():
    pd = pytest.importorskip('pandas')
    from minibt import LocalDatas
    return LocalDatas.test.kline.close.macd()


def test_linestyle_dict_sets_single_line(macd):
    macd.linestyle = {'macdh': LineStyle(line_dash=LineDash.vbar,
                                         line_color='red')}
    styles = macd._plotinfo.linestyle
    assert styles['macdh'].line_dash == 'vbar'
    assert styles['macdh'].line_color == 'red'
    # 其它线不受影响 ✓
    assert styles['macdx'].line_color is None


def test_linestyle_single_style_applies_to_all(macd):
    macd.linestyle = LineStyle(line_width=3)
    widths = {name: style.line_width
              for name, style in macd._plotinfo.linestyle.items()}
    assert set(widths.values()) == {3}


def test_line_style_accepts_dict_too(macd):
    macd.line_style = {'macds': LineStyle(line_color='green')}
    styles = macd._plotinfo.linestyle
    assert styles['macds'].line_color == 'green'
    assert styles['macdx'].line_color is None


def test_linestyle_ignores_bad_values(macd):
    before = {name: style.line_color
              for name, style in macd._plotinfo.linestyle.items()}
    macd.linestyle = {'macdh': 'not-a-style'}      # 非法值 → 忽略，不报错 ✓
    macd.linestyle = {}
    macd.linestyle = None
    after = {name: style.line_color
             for name, style in macd._plotinfo.linestyle.items()}
    assert after == before


def test_stop_lines_style_still_works():
    from minibt import LocalDatas
    kline = LocalDatas.test.kline
    kline.set_stop_lines_style(stop=LineStyle(line_color='#2962FF'))
    assert (kline.stop_lines._plotinfo.linestyle['stop_price'].line_color
            == '#2962FF')


def test_source_guards():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'minibt' / 'indicators' / 'core.py').read_text(
        encoding='utf-8')
    # 字面量 bug 的那行代码已删（文档里说明原因的那句保留 ✓）
    assert 'line = getattr(self,f"_name")' not in source
    assert 'line = getattr(self, f"_name")' not in source
    assert 'linestyle[name] = style.copy()' in source

"""个人指标**同名不同文件**：不能算错文件（desk 本地图表 overlap 失效）✓

用户 2026-11-2x 实测：在 desk 本地图表里把 ``tutorials/styles/06_overlap.py``
的 ``CompressedCandle`` 加到图上，类里明明写了 ``overlap = True``，却还是
显示在**副图**；用指标设置里「主图叠加」切一下又正常了 ✗。

根因：``tutorials/styles`` 里有三个文件都定义了 ``CompressedCandle``：

* ``03_category.py``   → ``overlap`` 默认（副图）
* ``06_overlap.py``    → ``overlap = True``（主图）
* ``09_candlestyle.py``→ 副图

以前个人指标的 key 只有 ``pi:<分类>/<类名>``（不含文件）→ 三个文件撞成同一个
key；``personal.compute`` 按文件名顺序取**第一个**叫 ``CompressedCandle`` 的类
→ 点 06 实际算的是 03（overlap=False）→ 永远进副图。

现在同名时 key 带文件名：``pi:<分类>/<文件>#<名字>`` ✓
"""
from __future__ import annotations

import json
import os
import textwrap

import pandas as pd
import pytest

CAT_SRC = '''
class CompressedCandle(BtIndicator):
    lines = ('open', 'high', 'low', 'close')
    category = 'candles'

    def next(self):
        n = 3
        return (self.close.shift(n), self.high.rolling(n).max(),
                self.low.rolling(n).min(), self.close)
'''

MAIN_SRC = '''
class CompressedCandle(BtIndicator):
    lines = ('open', 'high', 'low', 'close')
    category = 'candles'
    overlap = True

    def next(self):
        n = 3
        return (self.close.shift(n), self.high.rolling(n).max(),
                self.low.rolling(n).min(), self.close)
'''

OFFSET_SRC = '''
class OffsetCandle(BtIndicator):
    lines = ('open', 'high', 'low', 'close')
    category = 'candles'
    overlap = True

    def next(self):
        n = 3
        return (self.close.shift(n) + 100,
                self.high.rolling(n).max() + 100,
                self.low.rolling(n).min() + 100,
                self.close + 100)
'''

SOLO_SRC = '''
class Solo(BtIndicator):
    lines = ('value',)
    overlap = True

    def next(self):
        return (self.close,)
'''


def _frame():
    n = 40
    close = [100.0 + index for index in range(n)]
    return pd.DataFrame({
        'datetime': pd.Series(pd.date_range(
            '2026-01-01 09:00', periods=n, freq='min')).astype('int64'),
        'open': close,
        'high': [value + 2 for value in close],
        'low': [value - 2 for value in close],
        'close': close,
        'volume': [1.0] * n,
    })


@pytest.fixture()
def personal_dir(tmp_path, monkeypatch):
    from minibt.desk import personal as pi

    folder = tmp_path / 'styles'
    folder.mkdir()
    (folder / '03_category.py').write_text(
        'from minibt import *\n' + textwrap.dedent(CAT_SRC), encoding='utf-8')
    (folder / '06_overlap.py').write_text(
        'from minibt import *\n' + textwrap.dedent(MAIN_SRC), encoding='utf-8')
    (folder / 'solo.py').write_text(
        'from minibt import *\n' + textwrap.dedent(SOLO_SRC), encoding='utf-8')
    (folder / 'offset.py').write_text(
        'from minibt import *\n' + textwrap.dedent(OFFSET_SRC),
        encoding='utf-8')
    config = tmp_path / 'personal.json'
    config.write_text(json.dumps({'directories': [{
        'path': str(folder), 'category': 'styles', 'kind': 'indicator',
    }]}), encoding='utf-8')
    monkeypatch.setattr(pi, 'CONFIG_FILE', str(config))
    monkeypatch.setattr(pi, '_MODULE_CACHE', {})
    monkeypatch.setattr(pi, '_BROKEN_FILES', set())
    return pi


def test_same_name_in_different_files_gets_unique_keys(personal_dir):
    entries = personal_dir.scan('indicator')
    by_file = {os.path.basename(str(entry.get('file') or '')): entry
               for entry in entries if entry.get('name') == 'CompressedCandle'}
    assert set(by_file) == {'03_category.py', '06_overlap.py'}
    cat = by_file['03_category.py']
    main = by_file['06_overlap.py']
    assert cat['key'] == 'pi:styles/03_category#CompressedCandle'
    assert main['key'] == 'pi:styles/06_overlap#CompressedCandle'
    assert cat['key'] != main['key']
    assert '03_category' in cat['label'] and '06_overlap' in main['label']
    # 名字**唯一**的指标保持旧 key（已保存的参数 / 布局不受影响 ✓）
    solo = next(entry for entry in entries if entry.get('name') == 'Solo')
    assert solo['key'] == 'pi:styles/Solo'


def test_compute_uses_the_file_from_the_key(personal_dir):
    """关键回归：06 的 overlap=True 必须真的生效（以前算成 03 的副图 ✗）"""
    frame = _frame()
    main = personal_dir.compute(frame,
                                'pi:styles/06_overlap#CompressedCandle')
    cat = personal_dir.compute(frame,
                               'pi:styles/03_category#CompressedCandle')
    assert main, '06_overlap 没算出来'
    assert cat, '03_category 没算出来'
    assert main[0]['kind'] == 'candles' and cat[0]['kind'] == 'candles'
    assert main[0]['overlay'] is True, main[0]
    assert main[0]['pane'] == '', main[0]
    assert cat[0]['overlay'] is False, cat[0]
    assert cat[0]['pane'], cat[0]
    assert personal_dir.has_class(
        'pi:styles/06_overlap#CompressedCandle') is True


def test_old_key_still_computes(personal_dir):
    """旧的 ``pi:styles/CompressedCandle`` 仍能算（老布局 / 老参数兼容 ✓）"""
    items = personal_dir.compute(_frame(), 'pi:styles/CompressedCandle')
    assert items and items[0]['kind'] == 'candles'


def test_price_offset_is_not_lost(personal_dir):
    """指标里给 OHLC 加的价格偏移必须原样保留（主图叠加 +100 ✓）

    用户 2026-11-2x：改了 ``06_overlap.py`` 让蜡烛整体 +100，图上却看不出 100
    —— 其实当时算的是同名的 ``03_category.py``（没有偏移，见上面的根因）。
    这里直接验算：指标 close = 主图 close + 100 ✓（open/high/low 是压缩后的
    另一组价格，和主图同一字段比本来就不会正好差 100）。
    """
    frame = _frame()
    items = personal_dir.compute(frame, 'pi:styles/OffsetCandle')
    assert items and items[0]['kind'] == 'candles'
    candle = items[0]
    assert candle['overlay'] is True and candle['pane'] == ''
    last = candle['data'][-1][1]
    base_last = frame.iloc[-1]
    assert last[3] == float(base_last['close']) + 100
    # open/high/low 是**压缩后**的价格（close[n] / rolling max / rolling min），
    # 各自 +100；拿它们和当前 bar 的同名字段比本来就不会正好差 100 ✓
    assert last[0] == float(frame['close'].iloc[-4]) + 100
    assert last[1] == float(frame['high'].tail(3).max()) + 100
    assert last[2] == float(frame['low'].tail(3).min()) + 100

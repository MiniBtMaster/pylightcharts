"""通达信本地 K 线（`.day` / `.lc5` / `.lc1`）内置解析（用户 2026-11-22）

不装 `mootdx`，自己用 `struct` 解析 32 字节定长记录 ✓

覆盖：

* `minibt.data.tdx.read_tdx`（日线 / 5 分钟 / 1 分钟，含日期时间解码）
* `scan_root` / `resolve` / `load` / `tdx_id` / `split_tdx_id`
* `desk` 本地图表：`LocalStore.tdx_list`（**分页**）、`frame('tdx:…')`、
  `local_data` 补丁只给数量、`local_tdx_list` 命令、`local_load` 能上图
* `get_kline` / `read_unknown_file` 传 `.day` 路径
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from minibt.data import tdx  # noqa: E402

DAY = struct.Struct('<iiiiifii')
MINUTE = struct.Struct('<HHfffffII')


def _make_root(tmp_path: Path, codes=('600000', '600001')) -> Path:
    """造一个假通达信目录（`vipdoc/<market>/<lday|fzline|min>` ✓）"""
    root = tmp_path / 'new_tdx'
    for sub in ('sh/lday', 'sh/fzline', 'sh/min', 'sz/lday'):
        (root / 'vipdoc' / sub).mkdir(parents=True, exist_ok=True)
    for index, code in enumerate(codes):
        with open(root / 'vipdoc/sh/lday' / f'sh{code}.day', 'wb') as handle:
            for day in range(8):
                handle.write(DAY.pack(20240101 + day, 1000 + day, 1010 + day,
                                      990 + day, 1005 + day, 1234.5,
                                      1000 + day, 0))
        stamp = (2024 - 2004) * 2048 + 1 * 100 + 2 + index
        for name, folder in ((f'sh{code}.lc5', 'fzline'),
                             (f'sh{code}.lc1', 'min')):
            with open(root / 'vipdoc/sh' / folder / name, 'wb') as handle:
                for bar in range(6):
                    handle.write(MINUTE.pack(stamp, 9 * 60 + 30 + 5 * bar,
                                             10.0 + bar, 10.5 + bar,
                                             9.5 + bar, 10.2 + bar,
                                             888.0, 500 + bar, 0))
    with open(root / 'vipdoc/sz/lday/sz000001.day', 'wb') as handle:
        for day in range(4):
            handle.write(DAY.pack(20240201 + day, 2000, 2010, 1990, 2005,
                                  10.0, 100, 0))
    return root


# --------------------------------------------------------------- 解析
def test_read_day_and_minute(tmp_path):
    """`.day`（int×100）与 `.lc5`（float + 编码日期）都要解对 ✓"""
    root = _make_root(tmp_path, codes=('600000',))
    day = tdx.read_tdx(root / 'vipdoc/sh/lday/sh600000.day')
    assert list(day.columns) == ['datetime', 'open', 'high', 'low', 'close',
                                 'volume', 'amount']
    assert len(day) == 8
    assert day['open'].iloc[0] == pytest.approx(10.0)
    assert day['high'].iloc[0] == pytest.approx(10.1)
    assert str(day['datetime'].iloc[0]).startswith('2024-01-01')
    assert day['volume'].iloc[0] == 1000

    five = tdx.read_tdx(root / 'vipdoc/sh/fzline/sh600000.lc5')
    assert len(five) == 6
    assert str(five['datetime'].iloc[0]) == '2024-01-02 09:30:00'
    assert five['close'].iloc[0] == pytest.approx(10.2)
    assert five['datetime'].is_monotonic_increasing

    one = tdx.read_tdx(root / 'vipdoc/sh/min/sh600000.lc1')
    assert len(one) == 6


def test_ids_and_scan(tmp_path):
    """`tdx:` id 的生成 / 解析 + 目录扫描（只列文件名 ✓）"""
    root = _make_root(tmp_path)
    assert tdx.is_tdx_file('a.DAY') is True
    assert tdx.is_tdx_file('a.csv') is False
    assert tdx.tdx_id('sh', '600000', '.day') == 'tdx:sh600000@day'
    assert tdx.split_tdx_id('tdx:sh600000@lc5') == ('sh', '600000', '.lc5')
    assert tdx.split_tdx_id('600000') is None
    assert tdx.split_tdx_id('tdx:xx000001@day') is None

    table = tdx.scan_root(root)
    assert set(table) == {'.day', '.lc5', '.lc1'}
    # 排序规则：先市场（SH < SZ），再代码 ✓
    assert [item['code'] for item in table['.day']] == ['600000', '600001',
                                                        '000001']
    assert table['.day'][0]['id'] == 'tdx:sh600000@day'
    # 传 `vipdoc` 目录也能扫 ✓
    assert len(tdx.scan_root(root / 'vipdoc')['.day']) == 3


def test_resolve_and_load(tmp_path):
    """根目录 + 代码 + 周期 → 路径 / DataFrame（带 symbol、duration ✓）"""
    root = _make_root(tmp_path)
    path = tdx.resolve(root, '600000', '5m')
    assert path and path.endswith('sh600000.lc5')
    assert tdx.resolve(root, '999999', 'day') is None
    frame = tdx.load(root, '600000', 'day')
    assert frame['symbol'].iloc[0] == 'SH.600000'
    assert int(frame['duration'].iloc[0]) == 86400
    assert tdx.load(root, '600000', 300)['duration'].iloc[0] == 300


def test_roots_from(tmp_path):
    """安装根 / vipdoc 目录 / 直接放 .day 的目录都能识别 ✓"""
    root = _make_root(tmp_path, codes=('600000',))
    assert tdx.roots_from([str(root)]) == [str(root)]
    assert tdx.roots_from([str(root / 'vipdoc')]) == [str(root / 'vipdoc')]
    assert tdx.roots_from([str(root / 'vipdoc' / 'sh' / 'lday')]) == [
        str(root / 'vipdoc' / 'sh' / 'lday')]
    assert tdx.roots_from([str(tmp_path / 'nope')]) == []


# --------------------------------------------------------------- desk
def _store(tmp_path, monkeypatch, root: Path):
    from minibt.desk import local_data, user_prefs

    monkeypatch.setattr(local_data, 'FOLDERS_FILE', str(tmp_path / 'f.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 's.json'))
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.set_setting('tdx_root', str(root))
    return local_data.LocalStore()


def test_store_paged_list_and_frame(tmp_path, monkeypatch):
    """`LocalStore`：分页查询 + `frame('tdx:…')` 直接读文件 ✓"""
    root = _make_root(tmp_path)
    store = _store(tmp_path, monkeypatch, root)

    payload = store.tdx_payload()
    assert payload['counts'] == {'day': 3, 'lc5': 2, 'lc1': 2}
    assert payload['roots'] == [str(root)]

    page = store.tdx_list('600', 'day', offset=0, limit=1)
    assert page['total'] == 2 and page['has_more'] is True
    assert len(page['items']) == 1
    assert page['items'][0]['key'].startswith('tdx:sh600')

    page2 = store.tdx_list('600', 'day', offset=1, limit=1)
    assert page2['offset'] == 1 and page2['has_more'] is False

    frame = store.frame('tdx:sh600000@day')
    assert len(frame) == 8
    assert frame['datetime'].dtype == np.int64          # int64 纳秒 ✓
    assert int(frame['duration'].iloc[0]) == 86400
    assert store.info('tdx:sh600000@lc5')['rows'] == 6
    assert store.path_of('tdx:sh600000@day').endswith('sh600000.day')


def test_desk_payload_and_load(tmp_path, monkeypatch):
    """`local_data` 只给数量；`local_tdx_list` 分页；`local_load` 能上图 ✓"""
    root = _make_root(tmp_path)
    from minibt.desk import user_prefs
    from minibt.desk.app import Desk

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.set_setting('tdx_root', str(root))
    desk = Desk(offline=True)
    pushed: list = []
    desk.push = lambda patch: pushed.append(patch)
    store = desk.local_store()
    monkeypatch.setattr(store, 'folders', [])

    desk._on_local_list()
    data = [item for item in pushed
            if isinstance(item, dict) and item.get('type') == 'local_data'][-1]
    assert data['tdx']['counts']['day'] >= 1
    assert 'items' in data and isinstance(data['items'], list)

    desk._on_local_tdx_list({'text': '', 'period': 'day', 'offset': 0,
                             'limit': 2})
    page = [item for item in pushed if isinstance(item, dict)
            and item.get('type') == 'local_tdx'][-1]
    assert page['total'] >= 3 and len(page['items']) == 2
    assert page['has_more'] is True

    desk._on_local_load({'name': 'tdx:sh600000@day'})
    kinds = {item.get('type') for item in pushed if isinstance(item, dict)}
    assert 'local_kline' in kinds
    user_prefs.set_setting('tdx_root', '')


def test_read_unknown_file_and_get_kline(tmp_path):
    """`read_unknown_file` / `get_kline` 吃 `.day` 路径 ✓"""
    from minibt import LocalDatas, options
    from minibt.other import read_unknown_file

    root = _make_root(tmp_path, codes=('600000',))
    path = str(root / 'vipdoc/sh/lday/sh600000.day')
    frame = read_unknown_file(path)
    assert frame is not None and len(frame) == 8
    assert {'datetime', 'open', 'high', 'low', 'close'} <= set(frame.columns)

    options.set_conversion_mode = 'free'
    from minibt.strategy.base import StrategyBase

    strategy = object.__new__(StrategyBase)
    strategy._api = None
    strategy._datas = {}
    kline = StrategyBase.get_kline(strategy, symbol=path,
                                   duration_seconds=86400, data_length=300)
    assert len(kline) == 8


def test_get_kline_docstring_documents_tdx():
    """`get_kline` 的注释里必须有通达信用法（用户 2026-11-22 要求）✓"""
    import inspect

    from minibt.strategy.base import StrategyBase

    doc = inspect.getdoc(StrategyBase.get_kline) or ''
    for needle in ('通达信', 'data_source=\'tdx\'', 'tdx_root', 'tdx_period',
                   '.day', '.lc5', 'vipdoc/', 'minibt/data/tdx.py'):
        assert needle in doc, needle

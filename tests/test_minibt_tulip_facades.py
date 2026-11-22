"""`kline.tulip`（tulipy TuLip）与 `kline.tulip_rs`（TulipRS）必须分开 ✓

历史 bug（v1.3.9 ~ v1.3.10 修复前）：`IndicatorsBase` 里先后定义了**两个**
`tulip` property（先 TuLip、后 TulipRS）—— 后定义的覆盖前者，于是
``kline.tulip`` 实际是 TulipRS（**大写方法名**）；教程
``tutorials/indicators/01_overview.py`` 里的 ``kline.tulip.ema(period=20)``
直接 ``AttributeError: 'TulipRS' object has no attribute 'ema'`` ✗。

现在：``kline.tulip`` = TuLip（小写）；``kline.tulip_rs`` = TulipRS（大写）。
desk 目录前缀仍是 ``tulip_``（`tulip_SMA`），但计算时走 `kline.tulip_rs` ✓。
"""
from __future__ import annotations

import pytest


def _kline():
    from minibt import LocalDatas
    return LocalDatas.test.kline


def test_tulip_and_tulip_rs_are_separate_facades():
    from minibt.indicators.tulip import TuLip
    from minibt.indicators.tulip_rs import TulipRS

    kline = _kline()
    assert isinstance(kline.tulip, TuLip)
    assert isinstance(kline.tulip_rs, TulipRS)
    # 单列上也要正确（`kline.close.tulip` 以前同样被覆盖 ✗）
    assert isinstance(kline.close.tulip, TuLip)
    assert isinstance(kline.close.tulip_rs, TulipRS)
    # 同名指标：小写 / 大写各走各的，数值一致
    a = float(kline.tulip.ema(period=20)[-1])
    b = float(kline.tulip_rs.EMA(period=20)[-1])
    assert abs(a - b) < 1e-6


def test_tutorial_overview_ema_calls_work():
    """教程里 6 个库的 EMA(20) 都能跑（`tulip` 不能再抛 AttributeError）✓"""
    kline = _kline()
    values = {
        'pta': float(kline.close.ema(20)[-1]),
        'talib': float(kline.talib.EMA(timeperiod=20)[-1]),
        'tulip': float(kline.tulip.ema(period=20)[-1]),
        'tulip_rs': float(kline.tulip_rs.EMA(period=20)[-1]),
        'finta': float(kline.finta.EMA(period=20)[-1]),
        'pine': float(kline.pine.ema(length=20)[-1]),
    }
    assert max(values.values()) - min(values.values()) < 1e-6


def test_desk_catalog_tulip_prefix_uses_tulip_rs():
    from minibt.desk import indicator_catalog as catalog

    assert catalog.ACCESSOR_OF['tulip'] == 'tulip_rs'
    errors: dict[str, str] = {}
    items = catalog.compute(_kline(), ['tulip_SMA'], errors=errors)
    assert not errors, errors
    assert items and items[0]['kind'] == 'line'

"""策略图上的 `stop_price` / `target_price` 数值离谱（用户 2026-10-31 实测）✓

`tutorials/basic/indicator_step.py`（`LocalDatas.test`，价格 ≈ 4700）加到本地
图表后，图例里 `stop_price` / `target_price` 都是 **-12116.85**（负的一万多）。

三个根因一起修：

1. **`KLine.set_target_size()`（不带参数 = 平仓）被 desk 的包装层吃掉**：
   `StrategyRunner._wrap_target_size()` 把缺省写成 `size=None` 再
   `original(None)` → 下游 `int(size)` 抛 `TypeError` 被 except 吞掉 →
   `Stop` 触到止损时的**平仓永远不执行** → 持仓永远是第一笔，
   `SegmentationTracking` 的跟踪止损每根都往下棘轮 → 几千根后 -12537 ✗；
2. **时间戳全是 0**：`_stamps()` 用 `int(pd.Timestamp) // 1e9` 会抛
   `TypeError` → 全部落成 0（1970）→ 策略线根本画不到可视区 ✗
   → 新增 `protocol.to_seconds()`（纳秒 int / `Timestamp` / `datetime64` 都认）；
3. **`target_price` 是 `stop_price` 的复制**：`stop_lines.pandas_object` 把没写
   的目标价填成止损价 → 图上多一条完全重合的「止盈线」✗
   → 目标线与止损线完全相同时**不画**目标线。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STEP = ROOT / 'tutorials' / 'basic' / 'indicator_step.py'


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


# ------------------------------------------------------- ① 不带参数的平仓
def test_wrapped_set_target_size_keeps_default_close():
    """`kline.set_target_size()`（无参 = 平仓 0）不能被包装层变成 `None` ✓"""
    from minibt.desk.strategy_runner import StrategyRunner

    calls = []

    class FakeKLine:
        symbol = 'TEST'

        def set_target_size(self, size: int = 0, **kwargs):
            calls.append(size)
            return size

    kline = FakeKLine()
    runner = StrategyRunner.__new__(StrategyRunner)   # 只测包装函数 ✓
    runner.targets = []
    runner._target_serial = 0
    runner._replay_index = 7
    runner._wrap_target_size(kline)

    kline.set_target_size()                # Stop.update() 就是这么调的 ✓
    kline.set_target_size(3)
    kline.set_target_size(size=-2)
    assert calls == [0, 3, -2], calls
    # 本地模拟账户的「目标手数」也要跟着对（无参 = 0 = 平仓 ✓）
    assert [item['target'] for item in runner.targets] == [0.0, 3.0, -2.0]
    assert all(item['symbol'] == 'TEST' for item in runner.targets)


# ------------------------------------------------------------ ② 时间戳
def test_to_seconds_handles_timestamp_and_datetime64():
    pd = pytest.importorskip('pandas')
    np = pytest.importorskip('numpy')
    from minibt.desk.protocol import to_seconds

    stamp = pd.Timestamp('2025-04-02 11:15:00')
    assert to_seconds(stamp) == int(stamp.value) // 1_000_000_000
    assert to_seconds(np.datetime64('2025-04-02T11:15:00')) == int(
        stamp.value) // 1_000_000_000
    assert to_seconds(int(stamp.value)) == int(stamp.value) // 1_000_000_000
    assert to_seconds(stamp.to_pydatetime()) == int(
        stamp.value) // 1_000_000_000
    assert to_seconds(None) == 0 and to_seconds(float('nan')) == 0


def test_stamps_use_timestamp_data():
    """`_stamps()` 对 `datetime64[ns]`（`Timestamp`）不能再返回 0 ✓"""
    pd = pytest.importorskip('pandas')
    from minibt.desk import indicators as ind, strategy_overlay as ov

    frame = pd.DataFrame({
        'datetime': pd.to_datetime(['2025-04-02 11:15', '2025-04-02 11:20']),
        'close': [1.0, 2.0],
    })
    expected = int(pd.Timestamp('2025-04-02 11:15').value) // 1_000_000_000
    assert ov._stamps(frame)[0] == expected
    assert ind._stamps(frame)[0] == expected


# --------------------------------------- ③ 端到端：止损价贴近价格、目标价不重复
def test_indicator_step_stop_lines_are_sane():
    """`indicator_step.py` 的 stop_price 必须在价格附近（不是负的一万多）✓"""
    Strategy = pytest.importorskip('minibt').Strategy
    LocalDatas = pytest.importorskip('minibt').LocalDatas
    from minibt.desk import strategy_overlay as ov

    class StepStrategy(Strategy):
        def __init__(self):
            self.kline = self.get_kline(LocalDatas.test, height=400)
            self.utbot = self.kline.tradingview.UT_Bot_Alerts()

        def next(self):
            self.utbot.step()

    frame = LocalDatas.test.kline
    result = ov.run_overlay(frame, StepStrategy, 'test', 60, replay=True,
                            replay_bars=len(frame), frames=[('test', frame)])
    assert result.get('ok'), result.get('error')

    items = {str(item['key']): item for item in result.get('items') or []}
    keys = list(items)
    assert any('stop_price' in key for key in keys), keys
    stop = items[next(key for key in keys if 'stop_price' in key)]
    last = stop['data'][-1]
    price = float(frame['close'].tolist()[-1])
    assert last[0] > 1_600_000_000, '时间戳必须是真的（以前是 0 ✗）'
    assert abs(float(last[1]) - price) < price * 0.1, (last, price)
    assert float(last[1]) > 0, '止损价不能是负数 ✗'

    # `SegmentationTracking` 不设目标价 → 不能出现一条和止损线重合的 target ✓
    target = [key for key in keys if 'target_price' in key]
    assert not target, target


def test_target_line_skipped_when_identical_to_stop():
    """目标线与止损线完全相同时不画（`stop_lines` 会把目标填成止损 ✓）"""
    source = _read('minibt/desk/strategy_overlay.py')
    assert '目标线与止损线完全相同' in source
    assert 'np.allclose(stop_vals, target_vals, equal_nan=True)' in source
    assert 'specs = [item for item in specs if item is not target_spec]' in source
    assert 'import numpy as np' in source        # 少了这行 → 静默不生效 ✗

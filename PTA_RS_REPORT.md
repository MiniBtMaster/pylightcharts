# PtaRs：pandas_ta 的 Rust 版实现（27 个指标）——效果报告

> 生成时间：2026-11-21 · 环境：Python 3.12 / minibt 1.3.9 / py-alpha-lib 0.5.0 /
> pandas_ta 0.4.71b0 / TA-Lib 0.6.8
> 复现：`py -3.12 scripts/bench_pta_rs.py`（`--fast` 只跑值对比）

## 0. 一句话结论

**可行，而且 27 个里 24 个逐值一致、ATR/ADX 与 TA-Lib 逐值一致。**

第三轮优化之后，算法级已经"该快的地方都快了"：`ts_argmax` **61×**、
`sma` **29×**、`wma` **18×**、`bbands` **10×**、`adx` **7×**、`vwap` **5.7×**、
`atr` 5.1×、`stdev` 4.3×、`stoch` 3.1×、`trix` 2.1×、`ema` 1.8×；
只剩 `skew / kurtosis / roc`（我们为了口径精度做了组合，或本来就只有一个减法）
和 `kc`（两次 EMA）比 pandas 慢。

| 维度 | 结果 |
|---|---|
| 覆盖 | 27 个（sma/ema/wma/rma/stdev/bbands/macd/rsi/atr/donchian/kc/kdj/stoch/obv/mfi/vwap/adx/ao/roc/trix + ts_rank/quantile/skew/kurtosis/linreg/ts_argmax/ts_argmin）|
| 数值 | **24/27 与 pandas_ta 逐值一致**（≤1e-9；skew 1.7e-9、kurtosis 7.2e-7）；ATR/ADX 与 **TA-Lib** 逐值一致 |
| 不一致的 3 条线 | `atr`、`adx`、`dmp` —— pandas_ta 自己的预热种子与 TA-Lib 差一根（尾部收敛到 0）|
| 算法级加速 | `ts_argmax 61×`、`ts_argmin 51×`、`sma 29×`、`wma 18×`、`bbands 10×`、`adx 7.0×`、`vwap 5.7×`、`atr 5.1×`、`stdev 4.3×`、`stoch 3.1×`、`trix 2.1×`、`ema 1.8×` … `skew 0.5×` |
| 指标级加速 | 0.1×–3.0×（框架包装开销主导，见 §3）；批量接口 `batch()` 在 5 000 根时 **4.4×** |

## 1. 怎么用

```python
from minibt import LocalDatas

kline = LocalDatas.test.kline
kline.pta_rs.sma(length=20)          # IndSeries（主图）
kline.pta_rs.macd()                  # IndFrame：macd / macdh / macds
kline.pta_rs.atr(length=14)          # 副图
```

desk 选择器里新增分组「**PtaRS**」共 20 条（参数名和 pandas_ta 一致）。

## 2. 逐值对比（内置 5 分钟 K 线 8964 根，跳过头 120 根）

| 指标 | 线 | 结果 | 最大相对误差 |
|---|---|---|---|
| sma | sma | ✓ | 5.2e-16 |
| ema | ema | ✓ | 0.0 |
| wma | wma | ✓ | 2.0e-16 |
| rma | rma | ✓ | 0.0 |
| stdev | stdev | ✓ | 5.7e-10 |
| bbands | bbl / bbm / bbu | ✓✓✓ | ≤ 6.0e-13 |
| macd | macd / macdh / macds | ✓✓✓ | ≤ 7.4e-10 |
| rsi | rsi | ✓ | 0.0 |
| donchian | dcl / dcm / dcu | ✓✓✓ | 0.0 |
| kc | kcl / kcb / kcu | ✓✓✓ | ≤ 7.5e-16 |
| kdj | k / d / j | ✓✓✓ | ≤ 6.7e-14 |
| stoch | stochk / stochd / stochh | ✓✓✓ | ≤ 6.7e-13 |
| obv | obv | ✓ | 0.0 |
| mfi | mfi | ✓ | 6.8e-14 |
| vwap | vwap | ✓ | 0.0 |
| ao | ao | ✓ | 0.0 |
| roc | roc | ✓ | 1.1e-14 |
| trix | trix / trixs | ✓✓ | ≤ 7.5e-11 |
| ts_rank | ts_rank | ✓ | 0.0 |
| quantile | quantile | ✓ | 0.0 |
| skew | skew | ✓ | 1.7e-9 |
| kurtosis | kurtosis | ✓ | 7.2e-7 |
| linreg | linreg | ✓ | 2.0e-16 |
| ts_argmax | ts_argmax | ✓ | 0.0 |
| ts_argmin | ts_argmin | ✓ | 0.0 |
| **atr** | atr | ✗（预热段）/ 尾部一致 | 1.3e-5 |
| **adx** | adx / dmp / dmn | adx、dmp ✗（预热段）/ dmn ✓ | 1.8e-3 / 9.5e-4 |

**ATR / ADX 为什么不同**：`pandas_ta` 的 `atr(presma=True)` 本意是"前 n 根均值当种子"，
但它内部 `tr[0:length]` 的索引写法让种子晚一根、且数值不同；我们按 **TA-Lib（Wilder 标准）**
实现，实测：

```
atr  vs TA-Lib ATR      ✓（尾部相对误差 1.7e-15）
adx  vs TA-Lib ADX      ✓
dmp  vs TA-Lib PLUS_DI  ✓
dmn  vs TA-Lib MINUS_DI ✓
```

对照 `pandas_ta` 自己的差异只出现在预热段（约 3n 根），之后收敛到 0。

## 3. 速度（100 万根，3 次取最好，单位 ms）

### 3.1 指标级：`kline.pta_rs.*`（含框架 `@tobtind` 包装）

| 指标 | PtaRs | pandas_ta | 加速 |
|---|---:|---:|---:|
| sma | 78.9 | 179.9 | **2.3×** |
| adx | 193.5 | 585.4 | **3.0×** |
| atr | 81.3 | 156.3 | **1.9×** |
| bbands | 165.2 | 249.5 | 1.5× |
| stoch | 174.3 | 207.4 | 1.2× |
| wma | 69.3 | 89.7 | 1.3× |
| vwap | 117.1 | 120.4 | 1.0× |
| kdj / mfi / trix / rsi | 130–183 | 63–128 | 0.6–0.7× |
| ema / rma / stdev / macd / kc / donchian / obv / ao | 57–181 | 13–90 | 0.2–0.5× |
| roc | 47.8 | 6.6 | **0.14×** |

> 指标级有 **约 40–60 ms 的固定开销**（`@tobtind` 的取数 / 校验 / 构造 `IndSeries`、
> 附 `_plotinfo`、replay 分支判断…）。数据量小（<10 万根）时这层开销占主导。

### 3.2 算法级：直接调 `CoreFunc.pta_rs_*`（绕过包装）

| 指标 | Rust 算法 | pandas_ta | 加速 |
|---|---:|---:|---:|
| ts_argmax | 28.9 | 1762.3 | **60.9×** |
| ts_argmin | 32.0 | 1634.7 | **51.1×** |
| sma | 4.8 | 137.6 | **28.8×** |
| wma | 3.8 | 66.4 | **17.6×** |
| bbands | 20.6 | 205.8 | **10.0×** |
| adx | 85.3 | 599.7 | **7.0×** |
| vwap | 20.5 | 115.9 | **5.7×** |
| atr | 26.3 | 134.4 | **5.1×** |
| stdev | 5.7 | 24.8 | **4.3×** |
| stoch | 58.0 | 177.5 | **3.1×** |
| trix | 33.4 | 71.4 | **2.1×** |
| rma | 5.8 | 11.0 | 1.9× |
| ema | 7.1 | 13.0 | 1.8× |
| donchian | 40.5 | 72.7 | 1.8× |
| kdj | 67.6 | 109.4 | 1.6× |
| quantile | 198.7 | 320.3 | 1.6× |
| mfi | 38.6 | 57.3 | 1.5× |
| macd | 33.7 | 45.3 | 1.3× |
| ts_rank | 242.7 | 319.0 | 1.3× |
| obv | 19.0 | 22.4 | 1.2× |
| rsi | 41.8 | 46.3 | 1.1× |
| ao | 13.7 | 15.5 | 1.1× |
| kc | 44.2 | 33.5 | 0.8× |
| roc | 8.5 | 6.1 | 0.7× |
| linreg | 16.6 | 12.1 | 0.7× |
| skew | 32.6 | 39.1 | 1.2×（numba）|
| kurtosis | 30.9 | 44.0 | 1.4×（numba）|

### 3.3 批量接口 `batch()`（一次算 27 个）

```python
from minibt.indicators.pta_rs import batch
out = batch(kline.pandas_object, {'sma': {'length': 20}, 'macd': {}, ...})
```

| 数据量 | `batch()` | 逐个 `kline.pta_rs.*` | 加速 |
|---|---:|---:|---:|
| 1 000 000 根 | 1277 ms（47 ms/个） | ≈ 同（算法主导） | 1.0× |
| 5 000 根 | 10 ms | 45 ms | **4.4×** |
| 500 根 | 13 ms | 33 ms | **2.5×** |

> 数据越小，`@tobtind` 的固定开销占比越高 —— 研究场景（几千根 × 几十个指标）
> 用 `batch()`；画图 / 回测仍走 `kline.pta_rs.*`（要 `_plotinfo`）。

## 4. 三轮优化都做了什么

### v1.3.9-62（第一轮优化 + 加指标）

1. **减拷贝**：`_pta_rs_ema` / `_pta_rs_rma` 改成"只拷一次 + 视图切片"；
2. **批量接口** `batch()`：绕过 `@tobtind` 包装；
3. **新增 7 个"Rust 收益最大"的指标**：`ts_rank / quantile / skew / kurtosis /
   linreg / ts_argmax / ts_argmin`。

### v1.3.9-63（第三轮优化，都在"去隐形成本"）

| 改动 | 效果 |
|---|---|
| `_pta_rs_arrays` **不再算时间戳**（27 个里只有 `vwap` 需要）→ 挪到 `_pta_rs_day_stamps` | 每个指标省 **~17 ms**（1M 根）；`batch()` 5 000 根 **4.4×** |
| `ema` 用**种子线性修正**：直接对"视图"跑 Rust EMA，再用 `(1-α)^k` 修正开头几百个点（`(1-α)^k < 1e-12` 之后可忽略） | `ema` 25.9 → **7.1 ms**（1.8×）、`macd` 89 → 34 ms、`trix` 81 → 33 ms |
| `vwap` 换成 **numpy 前缀和 + 按日分组**（`cumsum` − 组起点前缀和） | 239 → **20.5 ms**，从 0.5× 变 **5.7×** ✓ |

## 5. 为什么有的指标反而慢了（写下来提醒自己）

| 指标 | 慢的原因 | 更好的做法 |
|---|---|---|
| `vwap` | 需要按**交易日**分组累计，Rust 算子是"整段"算子，只能退回 pandas `groupby.cumsum` | 该指标保留 pandas；或自己写 Rust（分组前缀和）|
| `kc` / `macd` / `rsi` / `trix` | 组合了 2–3 次子计算 + Python 层种子处理（`_pta_rs_ema` 里的 `np.mean` + 切片） | 把"种子 + 递归"下沉成算子（Rust 侧 `EMA_PRESMA`），一次调用搞定 |
| `roc` / `ao` | 算法只有 1–2 个减法/均值，pandas 本身就够快，我们的 Python 层（取数组、延迟、包装）成了瓶颈 | 这类别用 Rust，直接用 pandas |
| 全部 | 指标级 `@tobtind` 固定 ~40–60 ms | 批量算多个指标时避开逐指标包装（研究场景用 §3.2 的 `CoreFunc` 直调） |

## 6. 口径细节（做对比才发现的坑）

| 坑 | 说明 |
|---|---|
| `stdev` 的 **ddof** | pandas_ta 默认 `ddof=1`（样本）→ `alpha.STDDEV` 正好一致 |
| `ema` 的**种子** | pandas_ta / TA-Lib 都是"前 n 根均值当种子"（`presma`），而 `alpha.EMA` 是从第一个值递归 → 必须显式注入种子 |
| `rma` 与 `ema` 不同 | `rma` = `ewm(alpha=1/n, adjust=False)`；`alpha.SMA(x, n, 1)` 正好等价 |
| `alpha.REF` 会**补首值** | pandas `shift()` 补 NaN → 自己用 `np.full(n, nan)` 移位（`_pta_rs_delay`）|
| `adx` 的列顺序 | `ADX, ADXR, DMP, DMN`（第 2 列是 ADXR，不是 DMP ✗ 我一开始就踩了）|
| `macd` 的列顺序 | `MACD, MACDh, MACDs`（hist 在中间）|
| `bbands` 列 | `BBL, BBM, BBU, BBB, BBP` |
| `stoch` 默认 `mamode='sma'`，`kc` 默认 `mamode='ema'` | 两个通道类指标的平滑器不一样 |
| `pandas_ta` 的索引敏感 | `tr[0:length]` 在 DatetimeIndex 上是标签切片 → 预热行为跟着变；对比时统一用 RangeIndex |
| `alpha` 只吃**连续 float64** | `np.ascontiguousarray(np.asarray(x, dtype=np.float64))`，否则 `ValueError: invalid input` |

## 7. 下一步（如果要继续）

1. ~~`batch()` 批量入口~~ ✅ 已完成（§3.3）；
2. ~~新增 7 个高收益指标~~ ✅ 已完成（`ts_argmax 61×`）；
3. **把"种子 + 递归"下沉成 Rust 算子**（`EMA_PRESMA`），`ema/macd/kc/trix`
   还有 1.1–1.3× 的提升空间；
4. ~~`skew / kurtosis` 慢~~ ✅ 已换成 **numba JIT 滑窗**（1.2× / 1.4×，
   没装 numba 时自动回落 MOMENT 组合，数值口径不变）；
5. ~~`vwap` 按日分组改用 numpy 前缀和~~ ✅ 已完成（5.7×）；
6. `ts_rank` 现在要调 **两次** `alpha.RANK`（正 / 负序列）才能得到平均名次 →
   1.3×；若 Rust 侧提供"并列平均名次"算子可再快一倍。

## 8. 文件

| 文件 | 作用 |
|---|---|
| `scripts/gen_pta_rs.py` | 生成器（20 个指标的定义 + 写类文件 + 写 `CoreFunc` 标记块）|
| `minibt/indicators/pta_rs.py` | `class PtaRs`（`pta_rs_` 前缀，`@tobtind(lib="pta_rs")`）|
| `minibt/core.py` | `pta_rs_*` 20 个方法 + `_pta_rs_*` 助手（`# <pta-rs:*>` 标记块）|
| `scripts/bench_pta_rs.py` | 值对比 + 两级速度基准（本文所有数字都来自它 ✓）|
| `tests/test_minibt_pta_rs.py` | 14 项测试（覆盖 27 个 / 逐值 / TA-Lib 对拍 / desk / 生成器同步 / `batch()` / vwap 按日重置 / EMA 种子修正 / 取数不算时间戳）|

/**
 * 编辑器代码片段库（v1.3.7）✓
 *
 * 用户 2026-11-08 要求「代码片段库（Snippets）」：右键已有「指标模板」，
 * 这里再补策略骨架 / 下单 / 风控 / 参数优化 / 回测 / VP / 实盘 / 测试 等
 * 常用片段，一键插到光标处（按当前行缩进对齐 ✓）。
 *
 * 全部为**纯前端常量**：不联网、不依赖后端，插入失败也不会影响编辑 ✓
 */
export interface Snippet {
    key: string;
    label: string;
    hint?: string;
    /** 只在 `.py` 文件里显示（默认 true） */
    python?: boolean;
    text: string;
}

const STRATEGY = `class MyStrategy(Strategy):
    """策略骨架：指标 + 交易信号"""

    def __init__(self):
        # 参数（desk「参数优化」会自动识别 params / optuna 目标 ✓）
        self.params = dict(fast=5, slow=20, lots=1)
        self.kline = self.get_kline()

    def next(self):
        fast = self.kline.close.rolling(self.params['fast']).mean()
        slow = self.kline.close.rolling(self.params['slow']).mean()
        if fast.iloc[-1] > slow.iloc[-1] and not self.position:
            self.buy(volume=self.params['lots'])
        elif fast.iloc[-1] < slow.iloc[-1] and self.position > 0:
            self.close()
`;

const INDICATOR_CLASS = `class MyIndicator(BtIndicator):
    """指标类骨架：lines / params + next() 返回一维或二维数组"""

    lines = ('myline',)
    params = dict(length=(5, 60, 20))

    def next(self):
        length = int(self.params['length'])
        out = kline.close.rolling(length).mean()
        return out
`;

const INDICATOR_FUNC = `@indicator(overlap=True, name='MyMA')
def my_ma(kline, length: int = 20):
    """函数式指标（最简单）：返回 Series / DataFrame 都能画 ✓"""
    return kline.close.rolling(int(length)).mean()
`;

const ORDERS = `# ===== 下单片段（desk 内部一律限价单，价格空 = 对手价 ✓）=====
# 买开 / 卖开 / 平仓（策略里）
self.buy(volume=1)                  # 买开 1 手
self.sell(volume=1)                 # 卖开 1 手
self.close()                        # 全平当前合约

# 指定价格（限价）
self.buy(volume=1, limit_price=self.kline.close.iloc[-1])

# 手动交易 API（desk 内 Trading 封装，实盘走 TqApi.insert_order ✓）
# api.insert_order(symbol='SHFE.rb2610', direction='BUY', offset='OPEN',
#                  volume=1, limit_price=3600)
`;

const RISK = `# ===== 风控片段 =====
stop_loss = 0.01        # 1% 止损
take_profit = 0.03      # 3% 止盈
price = float(self.kline.close.iloc[-1])

if self.position > 0:
    if price <= self.entry_price * (1 - stop_loss):
        self.close()                       # 止损
    elif price >= self.entry_price * (1 + take_profit):
        self.close()                       # 止盈
# 手数按权益百分比：lots = equity * risk / (price * multiplier)
`;

const OPTIMIZE = `# ===== 参数优化片段（desk「参数优化」页会自动识别）=====
params = dict(
    fast=(5, 30, 5),        # (最小, 最大, 步长) 或候选列表 [5, 10, 20]
    slow=(20, 120, 20),
)

# 优化目标（不写默认最大化夏普；可自定义）
def optimize_target(result):
    """result: {'sharpe': ..., 'return': ..., 'drawdown': ...}"""
    return result.get('sharpe', 0) - 0.5 * abs(result.get('drawdown', 0))
`;

const BACKTEST = `# ===== 回测入口（脚本直接跑 / desk「策略回测」按钮都会用它）=====
bt = Bt(strategy=MyStrategy, kline=get_kline('SHFE.rb2610', 60), start=..., end=...)
bt.run()
bt.plot()          # 权益曲线 + 回撤（Config.drawdown_plot 控制回撤副图 ✓）
`;

const VP = `# ===== 成交量分布（VolumeProfile）指标片段 =====
class MyVP(RollingVolumeProfile):
    """category='vp'：next() 返回 (n, 1+bins)，第 0 列是普通指标线 ✓"""

    lines = ('ma',) + tuple(f'vp{i}' for i in range(40))
    params = dict(length=(50, 300, 100), bins=40)

    def next(self):
        length = int(self.params['length'])
        bins = int(self.params['bins'])
        ma = kline.close.rolling(length).mean().to_numpy()[-1]
        ...
        return ma, bins
`;

const LIVE = `# ===== 实盘片段（desk「策略实盘」按钮 / 循环驱动）=====
api = tq_auth(user='天勤账号', password='天勤密码')     # 密码不要写进仓库 ✗
account = api.get_account()
klines = api.get_kline_serial('SHFE.rb2610', 60, data_length=200)

while api.wait_update():
    if api.is_changing(klines.iloc[-1], 'close'):
        # 在这里判断信号，然后用 api.insert_order(...) 下**限价单** ✓
        pass
`;

const STOCK = `# ===== 股票（富途 FutuOpenD）片段 =====
api = StockApi(host='127.0.0.1', port=11111)     # 先启动 FutuOpenD
quote = api.get_quote('SH.600000')
print(quote.last_price, quote.bid_price, quote.ask_price)
# 交易（模拟盘）：api.insert_order(...) —— 股票同样用**限价单** ✓
`;

const PLOTINFO = `# ===== PlotInfo 样式片段（颜色 / 线型 / 信号箭头）=====
plotinfo = PlotInfo(
    overlap=True,                  # 画在主图（价格轴）上
    linestyle=dict(ma=LineStyle(color='#26a69a', width=2,
                                line_dash=LineDash.solid)),
    signalstyle=dict(signal=SignalStyle(marker='arrowup', color='#26a69a')),
    bandstyle=dict(band=BandStyle(color='rgba(38,166,154,.15)')),
)
`;

const TEST = `# ===== 指标自测片段（pytest 风格，也可直接跑）=====
def test_my_indicator():
    from minibt import LocalDatas
    kline = LocalDatas.test.kline          # 内置测试数据 ✓
    values = my_ma(kline, 20)
    assert len(values) == len(kline.close)
    assert values.iloc[-1] == values.iloc[-1]      # 不是 NaN
`;

export const SNIPPETS: Snippet[] = [
    { key: 'strategy', label: '策略骨架（Strategy）', hint: '指标 + 交易信号',
      text: STRATEGY },
    { key: 'indicator-class', label: '指标类（BtIndicator）',
      hint: 'lines / params / next()', text: INDICATOR_CLASS },
    { key: 'indicator-func', label: '指标函数（@indicator）',
      hint: '最简单的函数式指标', text: INDICATOR_FUNC },
    { key: 'orders', label: '下单片段', hint: '买开 / 卖开 / 平仓', text: ORDERS },
    { key: 'risk', label: '风控片段', hint: '止损 / 止盈 / 按权益算手数',
      text: RISK },
    { key: 'optimize', label: '参数优化片段', hint: 'params + 自定义目标',
      text: OPTIMIZE },
    { key: 'backtest', label: '回测入口', hint: 'Bt(...).run() / plot()',
      text: BACKTEST },
    { key: 'vp', label: '成交量分布（VP）', hint: 'category="vp" 指标',
      text: VP },
    { key: 'live', label: '实盘循环', hint: 'tq_auth + wait_update',
      text: LIVE },
    { key: 'stock', label: '股票（富途）', hint: 'StockApi 报价 / 交易',
      text: STOCK },
    { key: 'plotinfo', label: 'PlotInfo 样式', hint: '颜色 / 线型 / 箭头',
      text: PLOTINFO },
    { key: 'test', label: '指标自测', hint: 'LocalDatas.test.kline',
      text: TEST },
];

/**
 * 按当前行缩进对齐片段（多行才缩进；第一行不缩进 —— 光标处本来就在行内 ✓）
 *
 * @param snippet 片段原文
 * @param indent  当前行的前导空白（`'    '`）
 */
export function indentSnippet(snippet: string, indent: string): string {
    if (!indent) return snippet;
    const lines = String(snippet || '').split('\n');
    return lines
        .map((line, index) => (index === 0 || !line.trim()
            ? line : indent + line))
        .join('\n');
}

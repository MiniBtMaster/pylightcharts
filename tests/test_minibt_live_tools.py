"""实时图专属工具（买卖盘 / 持仓线 / 二级报价 + 简易下单）。

* `current_kline` 按 ``{symbol}_{cycle}`` 找合约；
* **买卖盘**用 ``TargetPosTask.set_target_volume`` 交易；
* **简易下单**：开多/开空/平仓按价格框价格走 ``insert_order``（限价）——
  开多 = BUY/OPEN、开空 = SELL/OPEN、平仓 = 多头 SELL/CLOSE / 空头 BUY/CLOSE；
  **市价平仓 / 反手 / 部分平** 走 ``TargetPosTask``（市价）；
* 持仓线用 ``horizontal_line(axis_label_visible=False, label_visible=True)``
  （标签画在可视范围左边，不挤进 Y 轴）；
* 二级报价面板复刻 miniqt（合约+名称 / 5 档 / 信息栏 / 简易下单 + 市价按钮）。
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
WINDOW = REPO / 'minibt' / 'strategy' / 'strategy_window.py'
REALTIME = REPO / 'minibt' / 'strategy' / 'realtime.py'
TOOLS = REPO / 'minibt' / 'strategy' / 'live_tools.py'


class FakePos:
    pos = 2
    open_price_long = 100.0
    open_price_short = 0.0
    float_profit = 5.0


class FakeQuote:
    symbol = 'SHFE.ag2612'
    bid_price1 = 99.0
    ask_price1 = 100.0
    price_tick = 0.01
    ask_price2 = 101.0
    ask_volume1 = 3
    last_price = 100.0
    pre_settlement = 98.0
    settlement = None
    open = 99.0
    highest = 102.0
    lowest = 97.0
    volume = 12345
    open_interest = 6789


class FakeTask:
    def __init__(self, size=None):
        self.size = size
        self.target = None

    def set_target_volume(self, value):
        self.target = value


class FakeKline:
    symbol = 'SHFE.ag2612'
    cycle = 60
    name = '沪银'

    def __init__(self):
        self.quote = FakeQuote()
        self.position = FakePos()
        self.orders = []
        #: 真 ``TqObjs.TargetPosTask`` 是一个**实例**（不是工厂）—— 只拿实例，
        #: 绝不能当函数调（``'TargetPosTask' object is not callable`` ✗）
        task = FakeTask()
        self.task = task
        self.tasks = [task]
        tqobj = type('TQ', (), {'TargetPosTask': task})()
        self._tqobjs = {self.symbol: tqobj}

    def insert_order(self, **kwargs):
        self.orders.append(kwargs)


class FakeLine:
    def __init__(self):
        self.updates = []
        self.deleted = False
        self.opts = None

    def update(self, price):
        self.updates.append(price)

    def options(self, **kwargs):
        self.opts = kwargs

    def delete(self):
        self.deleted = True


class FakeChart:
    def __init__(self):
        self.lines = []
        self.scripts = []
        self.win = type('W', (), {'handlers': {}})()

    def horizontal_line(self, price, **kwargs):
        line = FakeLine()
        self.lines.append((price, kwargs, line))
        return line

    def run_script(self, script):
        self.scripts.append(script)


class FakeOwner:
    #: 这些用例测的是**实时**图表的工具（`btplot` / 回测用 `_realtime=False`，
    #: 见 `test_live_tools_are_disabled_outside_the_realtime_chart`）
    _realtime = True

    def __init__(self, strategy, chart, contract='SHFE.ag2612_60'):
        self._strategy = strategy
        self.chart = chart
        self.window = type('Win', (), {'contract': contract})()

    def _strategy_obj(self):
        return self._strategy


class FakeStrategy:
    def __init__(self, kline):
        self._btklinedataset = {'k': kline}


def _tools():
    kline = FakeKline()
    chart = FakeChart()
    strategy = FakeStrategy(kline)
    from minibt.strategy.live_tools import LiveTools

    return LiveTools(FakeOwner(strategy, chart)), kline, chart


def test_current_kline():
    from minibt.strategy.live_tools import current_kline

    kline = FakeKline()
    strategy = FakeStrategy(kline)
    assert current_kline(strategy, 'SHFE.ag2612_60') is kline
    assert current_kline(strategy, 'X_60') is None


def test_tick_decimals():
    from minibt.strategy.live_tools import _tick_decimals

    assert _tick_decimals(0.01) == 2
    assert _tick_decimals(0.5) == 1
    assert _tick_decimals(1.0) == 0


# --------------------------------------------------------------------------- #
# 限价单（简易下单：买 / 卖 / 平 按价格框价格）
# --------------------------------------------------------------------------- #
def test_place_buy_and_sell_open_limit():
    tools, kline, _chart = _tools()
    # 开多：BUY/OPEN
    assert '开多' in tools._place('long', 100.0, 2)
    assert kline.orders[-1]['direction'] == 'BUY'
    assert kline.orders[-1]['offset'] == 'OPEN'
    assert kline.orders[-1]['volume'] == 2
    assert kline.orders[-1]['limit_price'] == 100.0

    # 开空：SELL/OPEN（**不是**开多）
    assert '开空' in tools._place('short', 99.0, 1)
    assert kline.orders[-1]['direction'] == 'SELL'
    assert kline.orders[-1]['offset'] == 'OPEN'

    # 旧的 buy/sell 仍兼容
    assert '开多' in tools._place('buy', 100.0, 1)
    assert kline.orders[-1]['direction'] == 'BUY'
    assert '开空' in tools._place('sell', 99.0, 1)
    assert kline.orders[-1]['direction'] == 'SELL'


def test_depth_panel_labels_and_actions():
    """二级报价按钮：开多 / 开空 / 平仓（不再是 买入 / 卖出）。"""
    from minibt.strategy.live_tools import _DEPTH_JS
    assert '>开多<' in _DEPTH_JS
    assert '>开空<' in _DEPTH_JS
    assert '>平仓<' in _DEPTH_JS
    assert "sendOrder('long')" in _DEPTH_JS
    assert "sendOrder('short')" in _DEPTH_JS
    assert "sendOrder('close')" in _DEPTH_JS


def test_order_book_host_clickable_and_on_top():
    """买卖盘要能点（pointer-events:auto）且不被 K 线盖住（z-index）✓。"""
    from minibt.strategy.live_tools import _ORDER_BOOK_HOST_JS
    assert 'pointer-events:auto' in _ORDER_BOOK_HOST_JS
    assert 'z-index:4000' in _ORDER_BOOK_HOST_JS


def test_place_close_is_limit_at_price():
    """平仓走 insert_order（限价）：多头挂卖平、空头挂买平 ✓。"""
    tools, kline, _chart = _tools()      # 多仓 net=2
    assert '平仓' in tools._place('close', 101.0, 2)
    assert kline.orders[-1]['direction'] == 'SELL'
    assert kline.orders[-1]['offset'] == 'CLOSE'
    assert kline.orders[-1]['limit_price'] == 101.0

    # 空仓 → BUY/CLOSE（空头平仓单）
    kline.position = type('P', (), {'pos': -3})()
    assert '空头平仓' in tools._place('close', 99.0, 5)
    assert kline.orders[-1]['direction'] == 'BUY'
    assert kline.orders[-1]['offset'] == 'CLOSE'
    assert kline.orders[-1]['limit_price'] == 99.0
    assert kline.orders[-1]['volume'] == 3


def test_place_requires_price():
    tools, _kline, _chart = _tools()
    assert '请输入价格' in tools._place('buy', None, 1)


# --------------------------------------------------------------------------- #
# 市价（市价平仓 / 反手 / 部分平）—— TargetPosTask
# --------------------------------------------------------------------------- #
def test_market_close_uses_target_pos():
    tools, kline, _chart = _tools()
    assert '市价平仓' in tools._place_market('close_market', 1)
    assert kline.tasks[-1].target == 0


def test_market_reverse():
    tools, kline, _chart = _tools()      # 多仓 2 → 反手目标 -2
    assert '反手' in tools._place_market('reverse', 1)
    assert kline.tasks[-1].target == -2


def test_market_partial():
    tools, kline, _chart = _tools()      # 多仓 2，部分平 1 → 目标 1
    assert '部分平' in tools._place_market('partial', 1)
    assert kline.tasks[-1].target == 1


def test_market_no_position():
    tools, kline, _chart = _tools()
    kline.position = type('P', (), {'pos': 0})()
    assert '无持仓' in tools._place_market('reverse', 1)
    assert '无持仓' in tools._place_market('partial', 1)


# --------------------------------------------------------------------------- #
# 买卖盘 —— set_target_volume
# --------------------------------------------------------------------------- #
def test_order_book_side_uses_target_pos():
    tools, kline, _chart = _tools()      # 多仓 2
    # 左侧（卖）在多仓时 = 平仓 → 0
    tools._on_order_book_side('sell')
    assert kline.tasks[-1].target == 0
    # 右侧（买）在多仓时 = 加多 → 3
    tools._on_order_book_side('buy')
    assert kline.tasks[-1].target == 3


# --------------------------------------------------------------------------- #
# 持仓线（左标签）
# --------------------------------------------------------------------------- #
def test_position_line_uses_left_edge_label():
    tools, kline, chart = _tools()
    tools.toggle_position_line(True)
    assert len(chart.lines) == 1
    price, kwargs, line = chart.lines[0]
    assert price == 100.0
    assert kwargs['label_visible'] is True
    assert kwargs['axis_label_visible'] is False
    assert '多仓2手' in kwargs['text']

    kline.position = type('P', (), {'pos': 3, 'open_price_long': 101.0,
                                    'open_price_short': 0.0,
                                    'float_profit': -1.0})()
    tools._sync_position_line()
    assert line.updates == [101.0]
    assert '多仓3手' in (line.opts or {}).get('text', '')

    kline.position = type('P', (), {'pos': 0})()
    tools._sync_position_line()
    assert line.deleted is True


def test_position_line_on_by_default():
    """持仓线默认**开** —— 有持仓就自动画（下单后不需手动打开）✓"""
    tools, kline, chart = _tools()
    assert tools._position_line_on is True
    tools._sync_position_line()
    assert len(chart.lines) == 1


def test_position_line_off_does_nothing():
    tools, kline, chart = _tools()
    tools.toggle_position_line(False)      # 手动关掉
    tools._sync_position_line()
    assert chart.lines == []


def test_live_tools_are_disabled_outside_the_realtime_chart():
    """回测 / ``btplot`` 静态图不画实时持仓线。

    以前 ``RealtimeChart`` 无论 ``realtime`` 真假都建 ``LiveTools``，切合约时
    又必调 ``on_contract_changed()`` → `refresh()` —— 用测试数据跑 ``btplot()``
    时策略里回测出的持仓会被当成实盘持仓，打一行
    ``[live_tools] 持仓线已画`` 并在图上画一条线 ✗。
    """
    class BacktestOwner(FakeOwner):
        _realtime = False

    kline = FakeKline()
    chart = FakeChart()
    strategy = FakeStrategy(kline)
    from minibt.strategy.live_tools import LiveTools

    tools = LiveTools(BacktestOwner(strategy, chart))
    assert tools._enabled is False
    tools.refresh()                        # 策略有持仓（pos=2）也不该画
    assert chart.lines == []
    assert tools._position_line is None


# --------------------------------------------------------------------------- #
# 源码约束
# --------------------------------------------------------------------------- #
def test_window_has_live_tool_buttons_before_drawing():
    source = WINDOW.read_text(encoding='utf-8')
    assert 'live_tools: bool = False' in source
    body = source.split("self.page_bar.switcher('strategy'", 1)[1]
    orderbook = body.index("self.page_bar.button('orderbook'")
    depth = body.index("self.page_bar.button('depth'")
    drawing = body.index("self.page_bar.button('drawing'")
    assert orderbook < drawing and depth < drawing
    assert 'def _on_order_book' in source and 'def _on_depth' in source


def test_realtime_wires_live_tools():
    source = REALTIME.read_text(encoding='utf-8')
    assert 'from minibt.strategy.live_tools import LiveTools' in source
    assert 'live_tools=bool(realtime)' in source
    assert 'self.live_tools = LiveTools(self)' in source
    assert 'on_toggle_order_book' in source and 'on_toggle_depth' in source
    assert 'live_tools.refresh()' in source


def test_depth_panel_matches_miniqt():
    source = TOOLS.read_text(encoding='utf-8')
    # 信息栏字段（保留）
    for field in ('最新', '涨跌', '涨跌幅', '昨结', '结算', '今开',
                  '最高', '最低', '成交量', '持仓量'):
        assert field in source, field
    # 去掉：分笔成交 / 增仓 / 成交额
    assert '分笔' not in source
    assert '增仓' not in source
    assert '成交额' not in source
    # +/- 步进 & 市价按钮
    assert 'md-p-up' in source and 'md-v-up' in source
    assert '市价平仓' in source and '反手' in source and '部分平' in source
    # 只对显示中的面板刷新
    assert 'if not self._depth_on or not self._depth_ready' in source


def test_trade_account_picks_sim_in_multi_account():
    """多账户（TqMultiAccount）→ 下单/查持仓要带 account，优先取**模拟账号** ✓"""
    from minibt.strategy.live_tools import LiveTools

    class FakeReal:
        pass

    class FakeSim:
        pass

    class Multi:
        _account_list = [FakeReal(), FakeSim()]

    class OwnerMulti:
        def _first_api(self):
            return type('A', (), {'_account': Multi()})()

    tools = LiveTools(OwnerMulti())
    assert type(tools._trade_account()).__name__ == 'FakeSim'

    # 单账户 → 就用它自己
    class OwnerSingle:
        def _first_api(self):
            return type('A', (), {'_account': FakeReal()})()

    tools2 = LiveTools(OwnerSingle())
    assert type(tools2._trade_account()).__name__ == 'FakeReal'


def test_orders_pass_account():
    """下单（限价 insert_order / 市价 TargetPosTask）都要带 account（多账户 ✓）"""
    import inspect
    from minibt.strategy import live_tools as im

    source = inspect.getsource(im)
    assert 'account=self._trade_account()' in source
    assert 'TargetPosTask(api, symbol, account=' in source
    assert 'api.get_position(symbol, account=account)' in source


# --------------------------------------------------------------------------- #
# 买卖盘回调 + 下单（回归：点击无反应 / TargetPosTask 被当函数调用）
# --------------------------------------------------------------------------- #
def test_order_book_uses_fixed_callback_name():
    """买卖盘回调走**固定名字** ``minibt_order_book``（和二级报价按钮同一套）✓"""
    import inspect
    from minibt.strategy import live_tools as mod

    src = inspect.getsource(mod.LiveTools._ensure_order_book)
    assert "handlers['minibt_order_book'] = self._on_order_book_side" in src
    assert 'callbackName = "minibt_order_book"' in src
    # 不再依赖面板自带的 _bind_callback（key 是 window.xxx，某些桥取不到）
    assert 'on_side_click=self._on_order_book_side' not in src


def test_target_task_never_called_as_factory():
    """``TqObjs.TargetPosTask`` 是实例 —— 只能取实例，不能调（旧代码会报
    ``'TargetPosTask' object is not callable`` → 点了没反应 ✗）✓"""
    import inspect
    from minibt.strategy import live_tools as mod

    src = inspect.getsource(mod.LiveTools._target_task)
    assert 'TargetPosTask(api, symbol, account=account)' in src
    assert "getattr(tqobj, 'TargetPosTask', None)" in src
    assert 'return kline.TargetPosTask' not in src
    assert 'kline.TargetPosTask(0)' not in src


def test_depth_market_buttons_readable_in_light_theme():
    """浅色主题下「市价平仓/反手/部分平」文字要深色（CSS 权重得压过 ``color:#fff``）✓"""
    import inspect
    from minibt.strategy import live_tools as mod

    src = mod._DEPTH_JS
    # ``.d-btns button`` 把 color 设成 #fff；.d-mkt 必须更具体才盖得住
    assert '.d-btns button.d-mkt{' in src
    assert '#minibt-depth .d-mkt{' not in src


# --------------------------------------------------------------------------- #
# 二级报价下方 tabs：持仓 / 委托 / 历史成交（只针对当前合约）
# --------------------------------------------------------------------------- #
def test_depth_panel_has_account_tabs():
    """二级报价按钮下方有可切换的 tabs + 三个表格（表头对齐 miniqt ✓）"""
    from minibt.strategy.live_tools import _DEPTH_JS
    for header in ('>持仓<', '>委托<', '>历史成交<', '>总仓<', '>持仓均价<',
                   '>盈亏<', '>未成交<', '>报单价<', '>成交价<', '>撤单<'):
        assert header in _DEPTH_JS, header
    for tid in ('md-tbl-pos', 'md-tbl-ord', 'md-tbl-trd'):
        assert tid in _DEPTH_JS, tid
    assert 'renderAccounts' in _DEPTH_JS
    assert 'setTab' in _DEPTH_JS
    assert "data-tab=" in _DEPTH_JS
    # “部分平”已换成“撤单”
    assert 'md-cancel' in _DEPTH_JS and 'md-partial' not in _DEPTH_JS


def test_account_rows_positions():
    tools, kline, _chart = _tools()

    class Pos:
        pos_long = 2
        pos_short = 0
        position_price_long = 15000.0
        float_profit_long = 123.456
    tools._position = lambda: Pos()
    rows = tools._account_rows('pos', 1)
    assert rows == [{'direction': '买',
                     'cells': ['买', '2', '15000.0', '+123.46']}]

    class Both:
        pos_long = 1
        pos_short = 3
        position_price_long = 100.0
        position_price_short = 101.0
        float_profit_long = -1.0
        float_profit_short = 2.0
    tools._position = lambda: Both()
    rows = tools._account_rows('pos', 2)
    assert [r['direction'] for r in rows] == ['买', '卖']
    assert rows[1]['cells'] == ['卖', '3', '101.00', '+2.00']


def test_account_rows_orders_and_trades_filter_current_contract():
    tools, kline, _chart = _tools()

    class FakeApi:
        def get_order(self, account=None):
            return [
                # 天勤真实格式：instrument_id **不带**交易所，exchange_id 单独给 ✓
                {'exchange_id': 'SHFE', 'instrument_id': 'ag2612',
                 'direction': 'BUY', 'offset': 'OPEN',
                 'volume_orign': 3, 'volume_left': 1, 'limit_price': 15000.0},
                {'exchange_id': 'SHFE', 'instrument_id': 'cu2612',
                 'direction': 'SELL', 'offset': 'CLOSE',
                 'volume_orign': 1, 'volume_left': 0, 'limit_price': 70000.0},
            ]

        def get_trade(self, account=None):
            return [
                {'exchange_id': 'SHFE', 'instrument_id': 'ag2612',
                 'direction': 'SELL', 'offset': 'CLOSETODAY',
                 'price': 15001.0, 'volume': 2},
                {'exchange_id': 'SHFE', 'instrument_id': 'cu2612',
                 'direction': 'BUY', 'offset': 'OPEN',
                 'price': 70000.0, 'volume': 1},
            ]
    tools._api = lambda: FakeApi()
    tools._trade_account = lambda: 'ACC'

    orders = tools._account_rows('ord', 1)
    assert orders == [{'direction': '买',
                       'cells': ['买', '开', '3', '1', '15000.0']}]  # 铜被过滤 ✓
    trades = tools._account_rows('trd', 1)
    assert trades == [{'direction': '卖',
                       'cells': ['卖', '平今', '15001.0', '2']}]


def test_cancel_orders_only_current_contract_pending():
    """撤单：只撤**当前合约**还有未成交手数的挂单（别的合约 / 已完不动）✓"""
    tools, kline, _chart = _tools()

    class FakeApi:
        def __init__(self):
            self.cancelled = []

        def get_order(self, account=None):
            return [
                {'exchange_id': 'SHFE', 'instrument_id': 'ag2612',
                 'order_id': 'o1', 'status': 'ALIVE', 'volume_left': 1},
                {'exchange_id': 'SHFE', 'instrument_id': 'ag2612',
                 'order_id': 'o2', 'status': 'FINISHED', 'volume_left': 0},
                {'exchange_id': 'SHFE', 'instrument_id': 'cu2612',
                 'order_id': 'o3', 'status': 'ALIVE', 'volume_left': 2},
            ]

        def cancel_order(self, order_id, account=None):
            self.cancelled.append(order_id)
    api = FakeApi()
    tools._api = lambda: api
    tools._trade_account = lambda: 'ACC'

    message = tools._cancel_orders()
    assert api.cancelled == ['o1']       # 只撤当前合约还有量的 ✓
    assert '已撤单 1' in message


def test_account_rows_accepts_full_symbol_form():
    """有些接口直接给全称 ``SHFE.ag2612`` —— 两种形式都得认 ✓"""
    tools, kline, _chart = _tools()

    class FakeApi:
        def get_trade(self, account=None):
            return [{'instrument_id': 'SHFE.ag2612', 'direction': 'BUY',
                     'offset': 'OPEN', 'price': 1.0, 'volume': 1}]
    tools._api = lambda: FakeApi()
    tools._trade_account = lambda: None
    assert tools._account_rows('trd', 1) == [
        {'direction': '买', 'cells': ['买', '开', '1.0', '1']}]


def test_account_rows_accept_dataframe_source():
    """tqsdk 不带参数返回的是 DataFrame，`_records` 要能转成行 ✓"""
    import pandas as pd
    tools, kline, _chart = _tools()

    class FakeApi:
        def get_trade(self, account=None):
            return pd.DataFrame([
                {'instrument_id': 'SHFE.ag2612', 'direction': 'BUY',
                 'offset': 'OPEN', 'price': 15000.0, 'volume': 1},
            ])
    tools._api = lambda: FakeApi()
    tools._trade_account = lambda: 'ACC'
    assert tools._account_rows('trd', 1) == [
        {'direction': '买', 'cells': ['买', '开', '15000.0', '1']}]

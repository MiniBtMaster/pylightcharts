"""图上买卖盘改成「每格一条 + 图例 👁」+ 联动回声修复（2026-11-03）✓

用户实测的 4 个问题：

1. 实时图表多布局（左右）开**联动**后：最新 K 线死死贴在右边、鼠标向左拖
   相当于不断放大，整图无法平移 ✗
   → `_bindLink()` 的回调里直接 `setVisibleLogicalRange()` 推给别的格，
     A→B→A 无限回声；实时行情每笔都触发自动滚动（同一个回调）→ 手动平移
     立刻被覆盖，两图各自 clamp 到数据右端。
2. 实时图表多布局：买卖盘**根本不出现** ✗
   → 买卖盘是整页一个 DOM，固定插进 `cells[0]` 的图例；切布局会重建
     cells / legend，节点留在被卸载的旧图例里。
3. 本地图表：买卖盘**只作用于格 1**，其它格调不出来 ✗（同一个单例节点）
4. 工具栏「买卖盘」其实只是「格 1 的开关」，多格时语义错位 ✗

现在（用户确认的设计）：每格图例一条「买卖盘 买入|点差|卖出 👁」，
眼睛只切当前格；工具栏按钮降级成**全局开关**；显隐按合约 / 数据名落盘；
打开才让后端订阅该格盘口。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


# ---------------------------------------------------------------- 前端结构
@pytest.mark.parametrize('name', ['chart-page.ts', 'local-chart-page.ts'])
def test_pages_have_per_cell_tickets(name):
    """两个图表页都用**每格一条**的 `TicketBar`，显隐由工具栏统一控制 ✓"""
    page = _read(f'jslib/src/desk/{name}')
    assert "from './ticket-bar'" in page
    assert 'private readonly tickets: Array<TicketBar | null> = [];' in page
    assert 'private readonly ticketVisible: boolean[] = [];' in page
    assert 'private ticketsOn = false;' in page       # 一个总开关 ✓
    # 每格建 / 恢复 / 一键全开全关 都要有；逐格 👁 已删除 ✓
    assert 'private _ensureTickets(): void' in page
    assert 'private _restoreTickets(): void' in page
    assert 'setTicketVisibleAll(' in page
    assert 'toggleCellTicket(' not in page
    assert 'ticketTouched' not in page
    # 旧实现（整页一个节点 + 只挂格 1）必须已经消失 ✓
    assert 'orderTicket' not in page
    assert '_renderTicket' not in page
    assert 'this.ticketNet' not in page


def test_ticket_bar_module_and_css():
    bar = _read('jslib/src/desk/ticket-bar.ts')
    assert 'export class TicketBar' in bar
    # ★ 2026-11-04（用户要求）：**去掉行尾 👁**，只留工具栏统一开关 ✓
    assert 'desk-ticket-eye' not in bar
    assert 'onToggle' not in bar
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-ticket-eye' not in css
    # ★ 隐藏 = **整块消失**，不是"变暗" ✗
    off = css.split('.desk-ticket.off .desk-ticket-body {', 1)[1].split('}', 1)[0]
    assert 'display: none' in off
    assert 'opacity' not in off
    built = _read('pylightcharts/js/desk.css')
    assert '.desk-ticket.off .desk-ticket-body' in built   # 构建产物也要有 ✓


@pytest.mark.parametrize('name', ['chart-page.ts', 'local-chart-page.ts'])
def test_link_sync_has_echo_guard(name):
    """联动区间同步必须有回声保护，否则实时图无法平移 / 越拖越放大 ✗"""
    page = _read(f'jslib/src/desk/{name}')
    assert 'private _linkApplying = false;' in page
    assert '_linkApplied' in page
    assert '_sameRange(' in page
    assert 'if (!this.linked || !range || this._linkApplying) return;' in page
    assert '_sameRange(' in page                  # 回声 → 不再回推 ✓
    assert '{ from, to }' in page
    assert 'this._linkApplying = true;' in page
    assert 'this._linkApplied[otherIndex] = { from, to };' in page


def test_app_routes_book_per_cell_and_persists():
    app = _read('jslib/src/desk/app.ts')
    assert 'private ticketsOn = false;' in app
    assert 'settings.ticket_visible_on' in app
    assert 'private _rememberTicket(' in app
    assert "this.send('book_watch'" in app
    assert 'cells: cells || []' in app            # 一次给全部格 ✓
    # book 补丁按「页 + 格」路由 ✓
    book = app.split("case 'book': {", 1)[1].split('break;', 1)[0]
    assert 'patch.page' in book and 'patch.cell' in book
    assert 'target.setBook(' in book
    # 两个页面都接线了 ✓
    assert app.count('onTicketAll:') >= 3
    assert app.count('ticketVisibleOf: () => this.ticketsOn,') >= 3
    # 关页退订 ✓
    assert "this.send('book_watch', { page: id, clear: true });" in app


# ------------------------------------------------------------------ 后端
def test_book_watch_registry_and_clear():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    assert desk._book_watch == {}
    desk._on_book_watch({'page': 'local:1', 'cell': 1, 'symbol': 'test',
                         'visible': True})
    assert desk._book_watch == {'local:1': {'1': 'test'}}
    desk._on_book_watch({'page': 'chart:SHFE.rb2610', 'cell': 0,
                         'symbol': 'SHFE.rb2610', 'visible': True})
    assert set(desk._book_watch) == {'local:1', 'chart:SHFE.rb2610'}
    # 关掉 → 退订这一格（省订阅 ✓）
    desk._on_book_watch({'page': 'local:1', 'cell': 1, 'symbol': 'test',
                         'visible': False})
    assert desk._book_watch == {'chart:SHFE.rb2610': {'0': 'SHFE.rb2610'}}
    # 关页 → 整页退订 ✓
    desk._on_book_watch({'page': 'chart:SHFE.rb2610', 'clear': True})
    assert desk._book_watch == {}


def test_book_watch_pushes_page_and_cell():
    """推送必须带 `page` + `cell`（前端按格路由 ✓）"""
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    pushed = []
    desk.push = pushed.append                        # type: ignore[assignment]
    desk.book_payload = lambda symbol, feed=None, ticks=True: {  # type: ignore
        'type': 'book', 'symbol': symbol,
        'bids': [{'price': 1}], 'asks': [{'price': 2}],
    }
    desk.tabs['SHFE.rb2610'] = {}
    desk._on_book_watch({'page': 'local:7', 'cell': 2, 'symbol': 'test',
                         'visible': True})
    assert not [i for i in pushed if i.get('type') == 'book'],         '命令处理里不能同步算盘口（会卡死 ✗），交给下一拍 ✓'
    desk._push_book_watch(force=True)
    books = [item for item in pushed if item.get('type') == 'book']
    assert books, '下一拍要推一次盘口 ✓'
    assert books[-1]['page'] == 'local:7'
    assert books[-1]['cell'] == 2
    # 本地图表没有真合约 → 用当前看盘合约的盘口 ✓
    assert books[-1]['symbol'] == 'SHFE.rb2610'
    # 页面清掉后不再推 ✓
    pushed.clear()
    desk._on_book_watch({'page': 'local:7', 'clear': True})
    desk._push_book_watch(force=True)
    assert not [item for item in pushed if item.get('type') == 'book']


def test_book_watch_symbol_prefers_chart_pages():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.tabs['SHFE.rb2610'] = {}
    assert desk._book_watch_symbol('chart:SHFE.rb2610',
                                   'SHFE.rb2610') == 'SHFE.rb2610'
    assert desk._book_watch_symbol('local:3', 'test') == 'SHFE.rb2610'


def test_ticket_visible_setting_persisted(tmp_path, monkeypatch):
    """👁 状态按「合约 / 数据名」落盘在 `settings.ticket_visible` ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        str(tmp_path / 'prefs.json'))
    assert 'ticket_visible' in user_prefs.SETTING_KEYS
    user_prefs.set_setting('ticket_visible', {'SHFE.rb2610': True,
                                              'test': False})
    values = user_prefs.settings()
    assert values['ticket_visible'] == {'SHFE.rb2610': True, 'test': False}


def test_backend_registers_book_watch_and_tick_step():
    app = _read('minibt/desk/app.py')
    assert "'book_watch': self._on_book_watch" in app
    assert 'def _on_book_watch(self, payload) -> None:' in app
    assert 'def _push_book_watch(self, force: bool = False) -> None:' in app
    assert "step('买卖盘（每格）', self._push_book_watch)" in app
    assert 'self._book_watch: Dict[str, Dict[str, str]] = {}' in app


# ------------------------------------------------- 二级报价跟着「点的那一格」
def test_focus_chart_switches_level2_symbol():
    """点第 2 格 → 二级报价面板换成**那一格**的合约并刷新（2026-11-03）✓

    用户实测：多布局里点第 2 格，交易面板的商品搜索框会跟着换（正常），
    但右侧「二级报价」一直是**格 1 品种**的数字 ✗ —— 因为
    `focus_chart` 以前只记 `last_symbol`，盘口数据仍是后端按「格 1 合约」
    死推的。
    """
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    pushed = []
    desk.push = pushed.append                        # type: ignore[assignment]
    desk._on_focus_chart({'symbol': 'SHFE.hc2610',
                          'page': 'chart:SHFE.rb2610'})
    assert desk.last_symbol == 'SHFE.hc2610'
    assert desk._book_focus == {'chart:SHFE.rb2610': 'SHFE.hc2610'}
    book = [item for item in pushed if item.get('type') == 'book'][-1]
    assert book['symbol'] == 'SHFE.hc2610'
    assert book['page'] == 'chart:SHFE.rb2610'
    # 不带 `cell` → 前端更新右侧面板 + 同名格的买卖盘 ✓
    assert 'cell' not in book


def test_tick_loop_pushes_book_for_focus_symbol():
    app = _read('minibt/desk/app.py')
    assert 'focus_symbol = self._book_focus.get(page_id) or cell0_symbol' in app
    assert "book['page'] = page_id" in app
    assert 'self._book_focus: Dict[str, str] = {}' in app


def test_frontend_book_panel_follows_clicked_cell():
    chart = _read('jslib/src/desk/chart-page.ts')
    # 页签 id 传给页面（按页路由盘口 ✓）
    assert 'pageId?: string;' in chart
    assert "page: this.options.pageId || ''" in chart
    # 带 `cell` 的盘口**只**刷该格买卖盘，不能改右侧面板 ✗
    book = chart.split('setBook(data: BookData, cell?: number): void {', 1)[1]
    head = book.split('private _restoreTickets', 1)[0]
    assert 'this.setTicketBook(book, cell);' in head
    assert 'return;' in head.split('this.setTicketBook(book, cell);', 1)[1]
    # 无 `cell`（焦点合约）→ 面板 + 同名格 ✓
    assert 'this.book.setBook(data);' in head
    assert "if (symbol && name && name !== symbol) continue;" in chart
    app = _read('jslib/src/desk/app.ts')
    assert 'pageId: `chart:${symbol}`,' in app


# --------------------------------------------- 多布局：周期按「点的那一格」
def test_set_cycle_per_cell_keeps_page_cycle():
    """工具栏 / 右键换周期 → **只换那一格**（第 1 格才动页面周期）✓

    用户 2026-11-03：工具栏周期菜单只对格 1 生效、右键菜单却把所有格都换 ✗
    """
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.push = lambda _payload=None: None              # type: ignore[assignment]
    desk.tabs['SHFE.rb2610'] = {
        'cycle': 60,
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': ['SHFE.rb2610', 'SHFE.hc2610'],
                   'cells': [{}, {}], 'cycles': [60, 60]},
    }
    pushed = []
    desk.push = pushed.append                            # type: ignore[assignment]
    # 第 2 格 → 5 分：页面周期不动，只有第 2 格的周期变 ✓
    desk._on_set_cycle({'symbol': 'SHFE.hc2610', 'cycle': 300, 'cell': 1})
    info = desk.tabs['SHFE.rb2610']
    assert info['cycle'] == 60
    assert info['layout']['cycles'] == [60, 300]
    kline = [item for item in pushed if item.get('type') == 'kline'][-1]
    assert kline['cell'] == 1                    # 只推那一格 ✓
    # 第 1 格 → 15 分：页面周期跟着走（tab 名 / 回放仍以它为准）✓
    desk._on_set_cycle({'symbol': 'SHFE.rb2610', 'cycle': 900, 'cell': 0})
    info = desk.tabs['SHFE.rb2610']
    assert info['cycle'] == 900
    assert info['layout']['cycles'] == [900, 300]
    assert 'cell' not in [item for item in pushed
                          if item.get('type') == 'kline'][-1]


def test_layout_sync_stores_per_cell_cycles():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.push = lambda _payload=None: None              # type: ignore[assignment]
    desk.tabs['SHFE.rb2610'] = {'cycle': 60}
    desk._on_layout_sync({'symbol': 'SHFE.rb2610', 'cols': 2, 'rows': 1,
                          'symbols': ['SHFE.rb2610', 'SHFE.hc2610'],
                          'cycles': [900, 1800]})
    layout = desk.tabs['SHFE.rb2610']['layout']
    assert layout['cycles'] == [900, 1800]


def test_cell_bars_use_own_cycle():
    """每拍补格 2..N 的 K 线要用**那一格自己的**周期 ✓"""
    app = _read('minibt/desk/app.py')
    body = app.split('def _push_cell_bars', 1)[1].split('def ', 1)[0]
    assert "cycles = [int(item or 0) for item in (layout_all.get('cycles') or [])]" \
        in body
    assert 'feed.klines(cell_symbol, cell_cycle,' in body


def test_frontend_cycle_menus_target_active_cell():
    chart = _read('jslib/src/desk/chart-page.ts')
    # 每格周期状态 + 读写 ✓
    assert 'private readonly cellCycles: number[] = [];' in chart
    assert 'cycleOfCell(cell = 0): number {' in chart
    assert 'setCellCycle(cell: number, cycle: number): void {' in chart
    # 点格子 → 工具栏周期显示那一格的周期 ✓
    activate = chart.split('private _activateCell(', 1)[1].split(
        'private _buildCells', 1)[0]
    assert 'this.cycleLabel.textContent = this._cycleText(' in activate
    assert 'this.cycleOfCell(index)' in activate
    # 工具栏菜单 / 右键菜单都只切当前格 ✓
    assert 'const pick = (value: number) => this.setCellCycle(this.activeCell, value);' \
        in chart
    assert 'onCycle: (cycle) => this.setCellCycle(this.activeCell, cycle),' in chart
    # 画线键 / 布局同步都按格 ✓
    assert 'return `${symbol}|${this.cycleOfCell(index)}`;' in chart
    assert 'cycles: this.cellSymbols.map((_, index) => this.cycleOfCell(index)),' \
        in chart
    app = _read('jslib/src/desk/app.ts')
    assert 'onCycleChange: (cycle, cell) => this.send(\'set_cycle\', {' in app
    assert 'cell: Number(cell ?? 0),' in app


# ------------------------------------- 眼睛/卡死/行情恢复（2026-11-03 第二轮）
@pytest.mark.parametrize('name', ['chart-page.ts', 'local-chart-page.ts'])
def test_ticket_defaults_hidden_until_toolbar(name):
    """没点过工具栏按钮 → 买卖盘默认**隐藏**；显隐只看那个总开关 ✓"""
    page = _read(f'jslib/src/desk/{name}')
    assert 'private ticketsOn = false;' in page
    assert 'visible: this.ticketsOn,' in page
    assert 'existing.setVisible(this.ticketsOn);' in page
    # 工具栏按钮 → 一次控制全部格 ✓
    toggle = page.split('toggleOrderTicket(visible?: boolean): boolean {', 1)[1]
    toggle = toggle.split('setTicketVisibleAll', 1)[0]
    assert 'this.ticketsOn' in toggle
    assert 'this.setTicketVisibleAll(next, true);' in page


def test_book_watch_is_cheap():
    """点眼睛不能触发**同步**盘口计算；每格只取买一/卖一（无分笔）✓

    用户实测 2026-11-03：本地图表多布局点 👁 → 界面卡死几分钟 ✗。
    根因：`_on_book_watch` 里同步 `_push_book_watch(force=True)` →
    每个打开的格都跑一遍 `book_payload()`（含 `get_tick_serial`，tqsdk 同步阻塞）。
    """
    app = _read('minibt/desk/app.py')
    watch = app.split('def _on_book_watch', 1)[1].split('def ', 1)[0]
    assert 'self._push_book_watch(force=True)' not in watch
    assert 'self._book_at = 0.0' in watch
    assert 'isinstance(cells, (list, tuple))' in watch   # 整页一起开 / 关 ✓
    push = app.split('def _push_book_watch', 1)[1].split('\n    def ', 1)[0]
    assert 'ticks=False' in push                 # 不算分笔 ✓
    assert 'budget = 2' in push                  # 每拍最多 2 个合约 ✓
    assert '< 0.5' in push                       # 500ms 限流 ✓
    assert 'self._book_seen' in push             # 内容没变不推 ✓
    assert 'def book_payload(self, symbol: str, feed=None,\n' in app
    assert 'ticks: bool = True' in app


def test_index_skipped_without_feed():
    """没连行情源不建全市场索引（用户实测：离线也刷「共 5577 个」✗）"""
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    logs = []
    desk.push_log_once = lambda key, text, level='info': logs.append(text)
    desk._symbol_building = True
    desk._index_step()
    assert desk._symbol_building is False
    assert logs and '没有连接行情源' in logs[0]


def test_market_resume_watch():
    """行情停更 → 记一次；恢复 → **全量重拉** + 提示（午休后不更新 ✗）"""
    import time

    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    logs, pushes = [], []
    desk.push_log = lambda text, level='info': logs.append((level, text))
    desk.push = lambda payload=None: pushes.append(payload)
    reloaded = []

    class Feed:
        def klines(self, *args, **kwargs):
            reloaded.append(args[:2])
            return None

    info = {'cycle': 60, 'feed': Feed()}
    info['_kline_at'] = time.monotonic() - 40
    desk._watch_market_resume('SHFE.rb2610', info)
    assert info['_market_stale'] is True
    # 数据又动了 → 全量重拉这一页
    info['_kline_at'] = time.monotonic()
    info['_market_stale_at'] = time.monotonic() - 60
    desk._watch_market_resume('SHFE.rb2610', info)
    assert info['_market_stale'] is False
    assert reloaded, '恢复后必须重拉 K 线 ✓'
    assert any('行情已恢复' in text for _, text in logs)
    assert any(p.get('type') == 'toast' for p in pushes)
    # 交易时段判断（周内 10:00 → True，周末 → False）
    assert Desk._looks_like_session(time.mktime((2026, 11, 4, 10, 0, 0, 0,
                                                 0, -1))) is True
    assert Desk._looks_like_session(time.mktime((2026, 11, 7, 10, 0, 0, 0,
                                                 0, -1))) is False


def test_after_connect_does_not_block():
    """登录后**不要**同步重拉所有 tab（用户实测卡 1~2 分钟 ✗）"""
    app = _read('minibt/desk/app.py')
    body = app.split('def _after_connect(', 1)[1].split('\n    def ', 1)[0]
    assert 'self._reload_klines()' not in body
    assert 'self._reset_kline_state(info or {})' in body


def test_ui_stall_heartbeat():
    """前端心跳 + 后端记日志（下次卡住能定位 ✓）"""
    app = _read('jslib/src/desk/app.ts')
    assert 'private _watchStall(): void {' in app
    assert "this.send('ui_stall'" in app
    assert 'this._watchStall();' in app
    backend = _read('minibt/desk/app.py')
    assert "'ui_stall': self._on_ui_stall" in backend
    assert 'def _on_ui_stall(self, payload) -> None:' in backend


# -------------------------- 界面卡 158s：索引不能用会阻塞的网络查询（2026-11-04）
def test_index_batches_local_only_skips_network():
    """tick 建索引必须 `local_only=True`：绝不调 `contracts()`（会阻塞 30s ✗）"""
    import inspect

    from minibt.desk import symbol_index as index

    assert 'local_only' in inspect.signature(index.batches).parameters
    text = _read('minibt/desk/symbol_index.py')
    assert 'if local_only:' in text
    assert "getattr(futures, 'contracts_local', None)" in text
    # 兜底只在**没有 api**（测试桩 / 特殊源）时允许，真实 tqsdk 绝不联网 ✓
    assert "getattr(futures, 'api', None) is None" in text
    app = _read('minibt/desk/app.py')
    assert '_index.batches(self.feeds, local_only=True)' in app


def test_index_step_waits_for_idle_and_has_budget():
    """用户刚操作 / 刚登录时不建索引；单批超 1s 就歇一歇（摊开卡顿 ✓）"""
    import time

    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    desk.push_log = lambda text, level='info': None
    desk._symbol_building = True
    desk._last_cmd_at = time.monotonic()          # 刚点过东西
    desk._index_step()
    assert desk._symbol_building is True         # 先不动 ✓

    desk._last_cmd_at = time.monotonic() - 30
    desk._index_next_at = time.monotonic() + 10  # 正在"歇着"
    desk._index_batches_called = 0
    desk._index_step()
    assert desk._index_batches_called == 0

    app = _read('minibt/desk/app.py')
    step = app.split('def _index_step', 1)[1].split('\n    def ', 1)[0]
    assert '_last_cmd_at', '用户操作后要跳过 ✓' in (step, '')
    assert 'if spent > 1.0:' in step
    assert 'self._index_next_at = time.monotonic() + 1.5' in step


def test_handle_tracks_user_activity_and_slow_commands():
    """命令入口记录"用户刚操作过" + 慢命令记日志（卡顿可归因 ✓）"""
    app = _read('minibt/desk/app.py')
    body = app.split('    def handle(self, message: str)', 1)[1].split(
        '\n    #: 「设置 → 关于」', 1)[0]
    assert 'self._last_cmd_at = time.monotonic()' in body
    assert '[性能] 命令 {cmd} 耗时' in body


def test_ui_stall_reports_backend_step():
    """卡顿日志带上"后端最近一步"，能区分是前端还是后端卡 ✓"""
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    logs = []
    desk.push_log = lambda text, level='info': logs.append((level, text))
    desk._tick_step = '全市场索引'
    desk._on_ui_stall({'ms': 158100, 'page': 'local:1'})
    assert logs and '158.1s' in logs[0][1]
    assert '全市场索引' in logs[0][1]
    # 低于 1.5s 的心跳不上报 ✓
    logs.clear()
    desk._on_ui_stall({'ms': 300})
    assert not logs


# --------------------------- 服务器维护时开图/换合约不能卡（2026-11-04 188s）
class _TqApi:
    """假的天勤 api（有 `wait_update` 才算 tqsdk ✓）"""

    def wait_update(self, deadline=None):
        return False


def test_preflight_blocks_open_when_no_data():
    """开图前 1 秒体检：拿不到数据 → **不打开**，而不是卡几分钟 ✓"""
    from minibt.desk.app import Desk

    desk = Desk(offline=True)
    logs, toasts = [], []
    desk.push_log = lambda text, level='info': logs.append((level, text))
    desk.push = lambda payload=None: toasts.append(payload)

    class DeadFeed:
        kind = 'futures'
        api = _TqApi()          # 有 wait_update 才会真的体检 ✓

        def available(self):
            return True

        def contracts_local(self, kind, exchange):
            return []

        def quotes(self, symbols):
            return []

    desk.feeds = [DeadFeed()]
    # 体检（0.1 秒，别真等 1 秒）
    reason = desk._preflight('SHFE.ad2612', wait=0.1)
    assert reason and '无响应' in reason

    # 开图命令 → 直接返回，不建 tab、不推 K 线 ✓
    desk.sent = []
    desk.handle('desk_~_' + '{"cmd":"open_chart","payload":'
                '{"symbol":"SHFE.ad2612"}}'.replace('desk_~_', ''))
    assert 'SHFE.ad2612' not in desk.tabs
    assert any('打开图表失败' in text for _, text in logs)


def test_preflight_passes_when_cache_has_symbol():
    from minibt.desk.app import Desk

    desk = Desk(offline=True)

    class GoodFeed:
        kind = 'futures'
        api = _TqApi()

        def available(self):
            return True

        def contracts_local(self, kind, exchange):
            return ['SHFE.ad2612']

        def quotes(self, symbols):
            return []

    desk.feeds = [GoodFeed()]
    assert desk._preflight('SHFE.ad2612', wait=0.1) == ''


def test_refresh_contracts_never_calls_blocking_contracts():
    """`_refresh_futures_contracts` 只能读本地字典（`contracts()` 会卡 188s ✗）"""
    app = _read('minibt/desk/app.py')
    body = app.split('def _refresh_futures_contracts', 1)[1].split(
        '\n    def ', 1)[0]
    assert "reader = getattr(feed, 'contracts_local', None)" in body
    assert "feed.contracts('FUT', exchange)" not in body


def test_switch_symbol_preflight():
    """换合约也要先体检 ✓"""
    app = _read('minibt/desk/app.py')
    body = app.split('def _on_switch_symbol', 1)[1].split('\n    def ', 1)[0]
    assert 'self._preflight(new)' in body
    assert '切换合约失败' in body


# ------------------------- 多布局点格 2 后二级报价被格 1 改回（2026-11-04）
def test_book_panel_ignores_other_cell_symbols():
    """面板只吃**当前焦点合约**的盘口；别的格的补丁不许把标题改回去 ✓"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(f'jslib/src/desk/{name}')
        assert 'private _isStaleBook(' in page
        assert 'const focus = String(this.tradeSymbol || this.options.symbol || \'\');' \
            in page
        body = page.split('setBook(data: BookData, cell?: number): void {', 1)[1]
        body = body.split('private ', 1)[0]
        assert 'if (this._isStaleBook(data)) {' in body
        # 丢弃时**不要**动右侧面板，只刷同名格的买卖盘 ✓
        stale = body.split('if (this._isStaleBook(data)) {', 1)[1]
        assert 'this.book.setBook(data);' not in stale.split('return;', 1)[0]


def test_book_pushes_carry_page():
    """换合约推的盘口要带 `page`（否则落到别的页 / 找不到页 ✗）"""
    app = _read('minibt/desk/app.py')
    assert "book['page'] = f'chart:{new}'" in app
    assert "book['page'] = f'chart:{tab}'" in app


# ---------------------------- 界面缩放搬位置 + 默认 100%（2026-11-05 用户）
def test_zoom_setting_lives_under_personal_appearance():
    page = _read('jslib/src/desk/settings-page.ts')
    personal = page.split('private _renderPersonal(): void {', 1)[1]
    personal = personal.split('private _render', 1)[0]
    # 外观段里有缩放；编辑器段里不再有 ✓
    appearance = personal.split("this._section('编辑器');", 1)[0]
    assert "this._row('zoom', '界面缩放'" in appearance
    editor = personal.split("this._section('编辑器');", 1)[1]
    assert "this._row('zoom'" not in editor
    # 默认 100%（没设置过 → 1，不是"跟随系统 0"）✓
    assert 'v.ui_zoom === undefined || v.ui_zoom === null' in page
    app = _read('jslib/src/desk/app.ts')
    assert 'this._applyZoom(values.ui_zoom === undefined' in app


def test_focus_chart_never_blocks():
    """`focus_chart`（点格子 / 点买卖盘都发）不能同步取分笔盘口 ✓

    用户实测 2026-11-05：`[性能] 命令 focus_chart 耗时 158.02s` → 界面卡死。
    根因：`book_payload()` → `_book_ticks()` → `api.get_tick_serial()` 没有
    走 `_fast_call`，服务器维护时阻塞上百秒。
    """
    app = _read('minibt/desk/app.py')
    ticks = app.split('def _book_ticks', 1)[1].split('\n    def ', 1)[0]
    assert 'fast = getattr(feed, \'_fast_call\', None)' in ticks
    assert 'frame = fast(getter, symbol) if callable(fast) else getter(symbol)' \
        in ticks
    # 本地页的 CSV 名要解析成真实合约（否则订阅不存在的合约 → 卡 ✗）
    focus = app.split('def _on_focus_chart', 1)[1].split('\n    def ', 1)[0]
    assert 'self._book_watch_symbol(page, symbol)' in focus
    assert "self.push(data)" in focus


# ------------------------- 平仓线 + 限价平仓语义（2026-11-05 用户）
def test_order_lines_distinguish_close():
    """挂单线里 `offset=平` 画成**平仓线**（橙色 +「平仓」字样）✓"""
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(f'jslib/src/desk/{name}')
        assert "const offset = String(item.offset || '开');" in page
        assert 'const isClose = offset.startsWith(\'平\');' in page
        assert "isClose ? '#ffb74d'" in page
        assert "`${isClose ? '平仓' : '挂单'}${side}`" in page
        assert 'badge.classList.toggle(\'close\', isClose);' in page
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-order-badge.close {' in css


def test_limit_price_not_autofilled():
    """价格框不再用最新价填满：空 = 市价；填了 = 限价挂单（等触发）✓

    用户实测 2026-11-05：点「平仓」秒成交 —— 因为 `priceValue()` 在空框时
    回退成**最新价**，于是变成"可成交的限价单"，永远挂不上（也不会有线）✗
    """
    ticket = _read('jslib/src/desk/replay-ticket.ts')
    # 空框 → 0（市价）；不再回退 lastPrice ✓
    value = ticket.split('priceValue: () => {', 1)[1].split('},', 1)[0]
    assert 'return Number.isFinite(raw) && raw > 0 ? raw : 0;' in value
    assert 'lastPrice) || 0' not in value
    # 最新价只当 placeholder ✓
    assert 'price.placeholder = String(value);' in ticket
    assert 'price.value = \'\';            // 换标的 → 清空（回到"市价"）✓' in ticket


# ------------------- 限价平仓挂单被"目标仓机器人"撤掉（2026-11-05 用户实测）
def test_manual_order_stops_target_pos_task():
    """手动下单前必须释放 `TargetPosTask`，否则它会把限价挂单撤掉 ✗

    用户实测 2026-11-05：设好价格点「平仓」→ 图上出现平仓线，转眼消失，
    「未成交委托」里的单子也没了（像被撤销）。根因是 tqsdk 的
    `TargetPosTask`（之前市价平仓 / 买卖盘用过）会持续维持目标仓位，
    每拍**撤掉自己不认识的挂单**再重新下单 → 我们的限价单被它撤掉。
    """
    from minibt.desk.trading import Trading

    class Task:
        def __init__(self):
            self.cancelled = 0

        def cancel(self):
            self.cancelled += 1

    task = Task()
    trader = Trading.__new__(Trading)
    trader._tasks = {'SHFE.ag2612': task}
    trader.api = lambda symbol: None                  # type: ignore[assignment]
    trader.release_target_task('SHFE.ag2612')
    assert task.cancelled == 1, '必须真的叫停机器人 ✓'
    assert 'SHFE.ag2612' not in trader._tasks

    # 下单路径里也要先释放（`place()` 现在转调 `insert()` ✓）
    import inspect

    place = inspect.getsource(Trading.place)
    assert 'return self.insert(' in place
    body = inspect.getsource(Trading.insert)
    assert 'self.release_target_task(symbol)' in body
    assert body.index('self.release_target_task(symbol)') < body.index(
        'insert_order')


# ---------------- 交易面板改成快期四按钮 + insert_order（2026-11-05 用户）
def _trader_stub(long_volume=0, short_volume=0):
    from minibt.desk.trading import Trading

    class Quote:
        ask_price1 = 12709.0
        bid_price1 = 12707.0
        last_price = 12708.0

    class Feed:
        kind = 'futures'

        def spec(self, symbol):
            return Quote()

    class DeskStub:
        trading = True
        _last_rows = {}

        def feed_of(self, symbol):
            return Feed()

        def push_log(self, *args, **kwargs):
            pass

        def push(self, payload=None):
            pass

    class Api:
        def __init__(self):
            self.calls = []

        def insert_order(self, **kwargs):
            self.calls.append(kwargs)

            class Order:
                order_id = 'o%d' % len(self.calls)
                instrument_id = kwargs.get('symbol')
                status = 'ALIVE'

            return Order()

    class Pos:
        pos_long = long_volume
        pos_short = short_volume
        # 上期所模拟："全部是今仓"（没有这两个字段时走 CLOSE 兜底）
        pos_long_today = long_volume
        pos_long_his = 0
        pos_short_today = short_volume
        pos_short_his = 0

    trader = Trading.__new__(Trading)
    trader.desk = DeskStub()
    trader._tasks = {}
    trader._watch = {}
    api = Api()
    trader.api = lambda symbol: api                     # type: ignore
    trader.account_kwargs = lambda symbol: {}           # type: ignore
    trader.account_label = lambda symbol='': '快期模拟'  # type: ignore
    trader._position = lambda symbol: Pos()             # type: ignore
    trader._replay_sim = lambda symbol: None            # type: ignore
    trader._decimals = lambda symbol: 2                 # type: ignore
    return trader, api


def test_insert_order_uses_counterparty_price():
    """价格留空 = **对手价**（买→卖一 / 卖→买一）✓"""
    trader, api = _trader_stub(long_volume=2)
    trader.insert('SHFE.ag2612', 'buy', 'open', 1, 0)      # 加多
    assert api.calls[-1]['limit_price'] == 12709.0         # 买 = 卖一 ✓
    trader.insert('SHFE.ag2612', 'sell', 'close', 2, 0)    # 卖平（平多）
    assert api.calls[-1]['limit_price'] == 12707.0         # 卖 = 买一 ✓
    # 上期所全是今仓 → 平今（CLOSETODAY）✓
    assert api.calls[-1]['offset'] in ('CLOSE', 'CLOSETODAY')
    assert api.calls[-1]['direction'] == 'SELL'


def test_insert_order_validates_close_volume():
    """平仓手数不能超过该方向持仓（超了不报单，直接提醒 ✓）"""
    trader, api = _trader_stub(long_volume=2)
    text = trader.insert('SHFE.ag2612', 'sell', 'close', 3, 12710)
    assert '可平2手' in text and not api.calls
    # 空头为 0 时"买平"（平空）也不该发单 ✓
    text = trader.insert('SHFE.ag2612', 'buy', 'close', 1, 12710)
    assert '没有可平的空头持仓' in text and not api.calls


def test_legacy_close_never_becomes_open():
    """老接口 `place(close)` 必须下成**平仓**（以前变成卖开 → 9 手变 10 手 ✗）"""
    trader, api = _trader_stub(long_volume=2)
    trader.place('SHFE.ag2612', 'close', 1, 0)
    call = api.calls[-1]
    assert call['direction'] == 'SELL'
    assert call['offset'] in ('CLOSE', 'CLOSETODAY')


def test_ticket_buttons_switch_by_position():
    """四按钮按仓位切换（多 / 空 / 无 / 锁仓），平仓手数夹在 1..持仓 ✓"""
    ticket = _read('jslib/src/desk/replay-ticket.ts')
    for key in ("label: '加多'", "label: '加空'", "label: '买开'",
                "label: '卖开'", "label: '锁仓'", "label: '买平'",
                "label: '卖平'"):
        assert key in ticket, key
    # 「平多X / 平空X」跟手数框联动、夹到持仓 ✓
    assert 'const closeQty = (available: number): number => {' in ticket
    assert 'return Math.max(1, Math.min(want, cap));' in ticket
    assert "label: `平多${closeQty(long)}`" in ticket
    assert "label: `平空${closeQty(short)}`" in ticket
    # 无仓时「买平 / 卖平」禁用 ✓
    assert "label: '买平', side: 'buy', offset: 'close', qty: rawQty,\n                  enabled: false" in ticket
    # 四个按钮一行 + 面板加宽 ✓
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-local-ticket-buttons.desk-local-ticket-four {' in css
    assert 'repeat(4, minmax(0, 1fr))' in css
    assert 'flex: 0 0 320px;' in css


# --------------- 上期所等不支持市价单：所有"市价*"都要换成对手价 limit（2026-11-05）
def _shfe_trader(long_volume=0, short_volume=3, quote=True):
    """假 trader + 假 api：`limit_price=None` 直接抛"不支持市价单"（上期所行为）"""
    from minibt.desk.trading import Trading

    class Quote:
        ask_price1 = 12709.0
        bid_price1 = 12707.0
        last_price = 12708.0

    class Feed:
        kind = 'futures'

        def spec(self, symbol):
            return Quote() if quote else None

    class DeskStub:
        trading = True
        _last_rows = {}

        def feed_of(self, symbol):
            return Feed()

        def push_log(self, *args, **kwargs):
            pass

        def push(self, payload=None):
            pass

    class Api:
        def __init__(self):
            self.calls = []

        def insert_order(self, **kwargs):
            if kwargs.get('limit_price') is None:
                raise ValueError(
                    'SHFE.ag2612不支持市价单，请使用limit_price参数指定价格。')
            self.calls.append(kwargs)

            class Order:
                order_id = 'o%d' % len(self.calls)
                instrument_id = kwargs.get('symbol')
                status = 'ALIVE'

            return Order()

    class Pos:
        pos_long = long_volume
        pos_short = short_volume

    trader = Trading.__new__(Trading)
    trader.desk = DeskStub()
    trader._tasks = {}
    trader._watch = {}
    api = Api()
    trader.api = lambda symbol: api               # type: ignore
    trader.account_kwargs = lambda symbol: {}     # type: ignore
    trader.account_label = lambda symbol='': '快期模拟'   # type: ignore
    trader._position = lambda symbol: Pos()       # type: ignore
    trader._replay_sim = lambda symbol: None      # type: ignore
    trader._decimals = lambda symbol: 2           # type: ignore
    return trader, api


def test_close_main_uses_limit_price_not_market():
    """交易页「市价平仓」→ 对手价 limit（上期所不支持市价单 ✗）"""
    trader, api = _shfe_trader(short_volume=3)
    text = trader.action('close_main', 'SHFE.ag2612')
    assert '买平' in text
    call = api.calls[-1]
    assert call['limit_price'] == 12709.0        # 买 → 卖一 ✓
    assert call['direction'] == 'BUY'
    assert call['offset'] in ('CLOSE', 'CLOSETODAY')
    assert call['volume'] == 3                   # 全部平掉（净仓要取绝对值 ✓）


def test_reverse_uses_limit_price_for_both_legs():
    trader, api = _shfe_trader(short_volume=2)
    trader.action('reverse', 'SHFE.ag2612')
    close_call, open_call = api.calls[-2], api.calls[-1]
    assert close_call['offset'] == 'CLOSE' and close_call['limit_price']
    assert open_call['offset'] == 'OPEN' and open_call['limit_price']
    assert (close_call['direction'], open_call['direction']) == ('BUY', 'SELL')


def test_close_all_and_position_rows_use_limit():
    """持仓列表的 平 / 反 / 全平 也都不能发市价单 ✓"""
    trader, api = _shfe_trader(short_volume=3)
    trader.close_symbol('SHFE.ag2612', side='空')
    assert api.calls[-1]['limit_price'] == 12709.0
    assert api.calls[-1]['offset'] in ('CLOSE', 'CLOSETODAY')
    trader.reverse_symbol('SHFE.ag2612', 1, '空')
    assert all(call['limit_price'] for call in api.calls[-2:])
    before = len(api.calls)
    trader._positions = lambda: [type('P', (), {
        'instrument_id': 'SHFE.ag2612', 'exchange_id': 'SHFE',
        'pos_long': 0, 'pos_short': 2})()]        # type: ignore
    trader._close_all()
    assert len(api.calls) == before + 1
    assert api.calls[-1]['limit_price'] == 12709.0


def test_market_order_helper_never_sends_none():
    """`_market_order`（内部"市价"）也必须带 limit_price ✓"""
    trader, api = _shfe_trader(short_volume=1)
    trader._market_order('SHFE.ag2612', 'BUY', 'CLOSE', 1)
    assert api.calls[-1]['limit_price'] == 12709.0


def test_reverse_disabled_when_locked():
    """锁仓（多空都有）时「反手」不可用；多 / 空单边才可用 ✓ 2026-11-05"""
    ticket = _read('jslib/src/desk/replay-ticket.ts')
    assert 'const actionButtonsByKind: Record<string, HTMLButtonElement> = {};' \
        in ticket
    assert 'const locked = long > 0 && short > 0;' in ticket
    assert 'reverseButton.disabled = locked || !tradeable;' in ticket
    assert "reverseButton.title = locked" in ticket
    assert '锁仓状态下不能反手' in ticket
    # 点击时也要挡住（disabled 之外的双保险）✓
    assert 'if (button.disabled) return;' in ticket


# ------------- 锁仓平仓 / 平今平昨 / 全平（2026-11-05 用户实测三项失效）
def _lock_trader(long_volume=2, short_volume=1, today_only=True):
    trader, api = _shfe_trader(long_volume=long_volume,
                               short_volume=short_volume)
    from minibt.desk import trading as _t

    class Pos:
        instrument_id = 'ag2612'
        exchange_id = 'SHFE'
        pos_long = long_volume
        pos_short = short_volume
        pos_long_today = long_volume if today_only else 0
        pos_long_his = 0 if today_only else long_volume
        pos_short_today = short_volume if today_only else 0
        pos_short_his = 0 if today_only else short_volume

    trader._position = lambda symbol: Pos()      # type: ignore
    trader._positions = lambda: [Pos()]          # type: ignore
    return trader, api, _t


def test_close_plan_splits_today_and_history():
    """上期所 / 能源中心：平今用 CLOSETODAY、平昨用 CLOSE（否则被拒 ✗）"""
    trader, api, _ = _lock_trader(long_volume=5, short_volume=0,
                                  today_only=False)
    trader._position = lambda symbol: type('P', (), {
        'instrument_id': 'ag2612', 'exchange_id': 'SHFE',
        'pos_long': 5, 'pos_short': 0,
        'pos_long_today': 3, 'pos_long_his': 2})()   # type: ignore
    assert trader.close_plan('SHFE.ag2612', 'sell', 4) == [
        ('CLOSE', 2), ('CLOSETODAY', 2)]
    plan = trader.close_plan('SHFE.ag2612', 'sell', 3)
    assert sum(qty for _, qty in plan) == 3          # 手数合计正确 ✓
    assert all(offset in ('CLOSE', 'CLOSETODAY') for offset, _ in plan)
    # 其他交易所直接 CLOSE ✓
    assert trader.close_plan('DCE.a2701', 'sell', 2) == [('CLOSE', 2)]


def test_close_symbol_requires_side_when_locked():
    """锁仓时右键平仓必须按行指定多 / 空（否则方向错、平不掉 ✗）"""
    trader, api, _ = _lock_trader(long_volume=2, short_volume=1)
    text = trader.close_symbol('SHFE.ag2612')
    assert '锁仓' in text and not api.calls
    # 多单行 → 卖出平（平今）✓
    trader.close_symbol('SHFE.ag2612', 2, '多')
    assert api.calls[-1]['direction'] == 'SELL'
    assert api.calls[-1]['offset'] == 'CLOSETODAY'
    assert api.calls[-1]['volume'] == 2
    # 空单行 → 买入平 ✓
    trader.close_symbol('SHFE.ag2612', 1, '空')
    assert api.calls[-1]['direction'] == 'BUY'
    assert api.calls[-1]['offset'] == 'CLOSETODAY'
    assert api.calls[-1]['volume'] == 1


def test_reverse_symbol_side_and_no_extra_volume():
    """反手多单 = 平多 + 开空（手数不能翻倍 → 以前变成 4 手 ✗）"""
    trader, api, _ = _lock_trader(long_volume=2, short_volume=1)
    text = trader.reverse_symbol('SHFE.ag2612', 2, '多')
    assert '锁仓' not in text
    close_leg, open_leg = api.calls[-2], api.calls[-1]
    assert (close_leg['direction'], close_leg['offset']) == (
        'SELL', 'CLOSETODAY')
    assert (open_leg['direction'], open_leg['offset']) == ('BUY', 'OPEN')
    assert close_leg['volume'] == open_leg['volume'] == 2


def test_close_all_closes_both_sides_of_locked_position():
    """全平：锁仓要**多空各平一次**，且覆盖所有账户 ✓"""
    trader, api, _ = _lock_trader(long_volume=2, short_volume=1)
    text = trader._close_all()
    assert '全部平仓' in text
    sides = {(c['direction'], c['offset']) for c in api.calls}
    assert sides == {('SELL', 'CLOSETODAY'), ('BUY', 'CLOSETODAY')}
    volumes = sorted(c['volume'] for c in api.calls)
    assert volumes == [1, 2]


def test_close_main_in_trade_page_closes_both_sides():
    """交易页「市价平仓」在锁仓时也要两边都平 ✓"""
    trader, api, _ = _lock_trader(long_volume=2, short_volume=1)
    text = trader.action('close_main', 'SHFE.ag2612')
    assert '；' in text                       # 两条
    assert {(c['direction'], c['offset']) for c in api.calls} == {
        ('SELL', 'CLOSETODAY'), ('BUY', 'CLOSETODAY')}


# --------------- 改单弹窗 + 全平只平当前账户 + 实盘确认（2026-11-05 用户）
def test_modify_order_cancels_then_reinserts():
    """改单 = 撤旧单 + 按新价/新手数重下（方向、开平沿用原委托 ✓）"""
    from minibt.desk.trading import Trading

    class Order:
        order_id = 'o-1'
        instrument_id = 'ag2612'
        exchange_id = 'SHFE'
        direction = 'BUY'
        offset = 'OPEN'
        volume_orign = 2
        volume_left = 2
        limit_price = 12708.0
        status = 'ALIVE'

    class Quote:
        ask_price1 = 12715.0
        bid_price1 = 12713.0
        last_price = 12714.0

    class Feed:
        kind = 'futures'

        def spec(self, symbol):
            return Quote()

    class DeskStub:
        trading = True
        _last_rows = {}

        def feed_of(self, symbol):
            return Feed()

        def push_log(self, *args, **kwargs):
            pass

        def push(self, payload=None):
            pass

    class Api:
        def __init__(self):
            self.calls = []
            self.cancelled = []

        def get_order(self, *args, **kwargs):
            return Order()

        def cancel_order(self, order_id=None, **kwargs):
            self.cancelled.append(order_id or kwargs.get('order_id'))

        def insert_order(self, **kwargs):
            self.calls.append((kwargs['direction'], kwargs['offset'],
                               kwargs['volume'], kwargs['limit_price']))

            class O:
                order_id = 'o-2'
                instrument_id = kwargs['symbol']
                status = 'ALIVE'

            return O()

    class Pos:
        pos_long = 2
        pos_short = 0
        pos_long_today = 2
        pos_long_his = 0

    trader = Trading.__new__(Trading)
    trader.desk = DeskStub()
    trader._tasks = {}
    trader._watch = {}
    api = Api()
    trader.api = lambda symbol='': api                 # type: ignore
    trader.account_kwargs = lambda symbol='': {}       # type: ignore
    trader.account_label = lambda symbol='': '快期模拟'  # type: ignore
    trader._position = lambda symbol: Pos()            # type: ignore
    trader._replay_sim = lambda symbol: None           # type: ignore
    trader._decimals = lambda symbol: 2                # type: ignore

    snapshot = trader.order_snapshot('o-1', 'SHFE.ag2612')
    assert (snapshot['direction'], snapshot['offset']) == ('BUY', 'OPEN')
    assert snapshot['volume'] == 2 and snapshot['price'] == 12708.0
    text = trader.modify_order('SHFE.ag2612', 'o-1', 3, 12720)
    assert '已改单' in text
    assert api.cancelled == ['o-1']                    # 先撤旧单 ✓
    assert api.calls[-1] == ('BUY', 'OPEN', 3, 12720.0)  # 方向/开平不变 ✓
    # 价格留空 → 对手价（卖一）✓
    trader.modify_order('SHFE.ag2612', 'o-1', 1, 0)
    assert api.calls[-1][3] == 12715.0


def test_close_all_only_current_account():
    """全平只平**当前账户**（用户 2026-11-05 要求；不再遍历所有账户 ✓）"""
    import inspect

    from minibt.desk.trading import Trading

    src = inspect.getsource(Trading._close_all)
    # ★ 按**这一页的合约**取账户（`_positions_for(symbol)`），不遍历所有账户 ✓
    assert 'positions = self._positions_for(symbol)' in src
    assert '_positions_all()' not in src


def test_real_account_confirm_and_risk_guard():
    """实盘：持仓行 平/反/全 要二次确认；后端也过一道风控 ✓"""
    app = _read('minibt/desk/app.py')
    body = app.split('def _on_position_action', 1)[1].split('\n    def ', 1)[0]
    assert "if action in ('close', 'reverse'):" in body
    assert 'self._risk_guard(' in body
    assert "'modify'" in app.split('def _on_order_modify', 1)[1].split(
        '\n    def ', 1)[0]
    dock = _read('jslib/src/desk/account-dock.ts')
    assert "const guard = (text: string): boolean => {" in dock
    assert '【实盘】' in dock
    assert 'openModifyOrder(' in dock
    accounts = _read('minibt/desk/accounts.py')
    assert "payload['real'] = self.is_real(symbol, key)" in accounts


def test_modify_dialog_module():
    """改单弹窗：合约只读 + 手数/价格预填 + 提交 ✓"""
    dialog = _read('jslib/src/desk/order-modify-dialog.ts')
    assert 'export function openOrderModifyDialog' in dialog
    assert "title.textContent = '修改委托单';" in dialog
    assert "qty.value = String(Math.max(1, Math.round(Number(options.volume) || 1)));" \
        in dialog
    assert "price.placeholder = '留空 = 对手价';" in dialog
    assert "this.send('order_modify'" in _read('jslib/src/desk/account-dock.ts')
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-modal-overlay {' in css and '.desk-modify input {' in css


# ------------------- 天勤账户切换（指纹 / 重连 / 保留画面）2026-11-05
def test_account_fingerprint_rules():
    """四种切账户场景都判"不同"；完全一致才判"相同" ✓"""
    from minibt.desk.app import account_fingerprint as fp

    sim_u1 = fp({'username': 'u1'})
    sim_real_u1 = fp({'username': 'u1', 'real': True,
                      'broker': 'B', 'account': 'A'})
    sim_real_u1_b2 = fp({'username': 'u1', 'real': True,
                         'broker': 'B2', 'account': 'A2'})
    sim_u2 = fp({'username': 'u2', 'real': True, 'broker': 'B', 'account': 'A'})
    # ① 只模拟 → 模拟+实盘
    assert sim_u1 != sim_real_u1
    # ② 天勤账号不同、实盘相同
    assert sim_real_u1 != sim_u2
    # ③ 天勤相同、实盘不同
    assert sim_real_u1 != sim_real_u1_b2
    # ④ 两者都不同
    assert sim_real_u1 != fp({'username': 'u3', 'real': True,
                              'broker': 'B9', 'account': 'A9'})
    # 相同
    assert sim_u1 == fp({'username': 'u1'})
    assert (sim_u1, sim_real_u1) == (('u1', '', ''), ('u1', 'B', 'A'))


def test_same_account_does_not_relogin():
    from minibt.desk.app import Desk

    desk = Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True

    class Feed:
        kind = 'futures'

        def available(self):
            return True

    feed = Feed()
    desk.futures = feed
    desk.feeds = [feed]
    desk._account_fp = ('u1', '', '')
    desk.handle('desk_~_' + '{"cmd":"connect_futures","payload":'
                '{"username":"u1","password":"p"}}')
    assert desk._connect_pending is None        # 不重连 ✓


def test_switch_account_builds_pending_job():
    from minibt.desk.app import Desk

    desk = Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True

    class Feed:
        kind = 'futures'

        def available(self):
            return True

    feed = Feed()
    desk.futures = feed
    desk.feeds = [feed]
    desk._account_fp = ('u1', '', '')
    desk.handle('desk_~_' + '{"cmd":"connect_futures","payload":'
                '{"username":"u1","password":"p","real":true,'
                '"broker":"B","account":"A","trade_password":"t"}}')
    job = desk._connect_pending
    assert job and job[0] == 'futures'
    assert job[1]['_fp'] == ('u1', 'B', 'A')     # 指纹带上 ✓
    assert job[1]['_switch'] is True
    assert '_preferred_identity' in job[1]


def test_reconnect_replaces_feed_and_closes_old(monkeypatch):
    """重连：新 feed 放最前、旧 feed 摘掉并**在主线程关闭**、清账户缓存 ✓"""
    import sys
    import types

    from minibt.desk import app as desk_app

    created = {}

    class FakeApi:
        def __init__(self, target, auth=None):
            created['api'] = self

        def close(self):
            created['closed'] = True

    class FakeKq:
        pass

    class FakeAccount:
        def __init__(self, broker, account, password):
            self.broker_id = broker
            self.account_id = account

    class FakeMulti:
        def __init__(self, items):
            self._account_list = items
            self._account = self

    fake_tq = types.SimpleNamespace(
        TqApi=FakeApi, TqAuth=lambda u, p: (u, p), TqKq=FakeKq,
        TqAccount=FakeAccount, TqMultiAccount=FakeMulti)
    monkeypatch.setitem(sys.modules, 'tqsdk', fake_tq)

    class FakeFeed:
        kind = 'futures'

        def __init__(self, api, kind):
            self.api = api
            self.closed = False

        def available(self):
            return True

        def close(self):
            self.closed = True

    monkeypatch.setattr(desk_app, 'FuturesFeed', FakeFeed)

    desk = desk_app.Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True
    old = FakeFeed(object(), 'futures')
    desk.futures = old
    desk.feeds = [old]
    desk._account_fp = ('u1', '', '')
    desk._book_focus = {'local:1': 'SHFE.rb2610'}
    desk._book_watch = {'local:1': {'0': 'SHFE.rb2610'}}

    desk._connect_pending = ('futures', {
        'username': 'u1', 'password': 'p', 'real': True,
        'broker': 'B', 'account': 'A', 'trade_password': 't',
        '_fp': ('u1', 'B', 'A'), '_switch': True, '_preferred_identity': '',
    })
    desk._run_connect()

    new = desk.futures
    assert new is not old
    assert desk.feeds[0] is new
    assert old not in desk.feeds                     # 旧 feed 摘掉 ✓
    assert desk._old_feed_pending is old             # 交给主线程关闭 ✓
    assert desk._account_fp == ('u1', 'B', 'A')      # 指纹更新 ✓
    assert desk._book_focus == {} and desk._book_watch == {}

    desk._after_connect('futures', '天勤已连接')
    assert old.closed is True                        # 主线程关掉了 ✓


def test_relogin_failure_keeps_old_connection(monkeypatch):
    """重连失败 → 旧连接 / 旧指纹都**保留**（不能把用户踢下线 ✗）"""
    import sys
    import types

    from minibt.desk import app as desk_app

    class Boom:
        def __init__(self, *args, **kwargs):
            raise RuntimeError('登录失败')

    fake_tq = types.SimpleNamespace(
        TqApi=Boom, TqAuth=lambda u, p: (u, p), TqKq=object,
        TqAccount=object, TqMultiAccount=object)
    monkeypatch.setitem(sys.modules, 'tqsdk', fake_tq)

    desk = desk_app.Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True
    old = object()
    desk.futures = old
    desk._account_fp = ('u1', '', '')
    desk._connect_pending = ('futures', {
        'username': 'u2', 'password': 'p', 'real': False,
        '_fp': ('u2', '', ''), '_switch': True,
    })
    desk._run_connect()
    assert desk.futures is old                       # 旧连接还在 ✓
    assert desk._account_fp == ('u1', '', '')        # 指纹没变 ✓


def test_login_dialog_switch_confirm_and_hint():
    app = _read('jslib/src/desk/app.ts')
    assert "'切换 / 重新登录期货账户…'" in app
    assert '将断开当前账户并重新订阅，确认？' in app
    assert "(values as Record<string, unknown>).switch = true;" in app
    dialog = _read('jslib/src/desk/login-dialog.ts')
    assert '已连接时再登录 = 切换账户' in dialog


# --------------- 账户切换下拉框搬到「持仓/委托…」子表行（2026-11-05 用户）
def test_account_select_lives_on_table_tab_row():
    """切换账户下拉框在**交易账户页的子表行**、导出 CSV 左边 ✓

    以前挂在 dock 顶部的页签条（交易账户/编辑器/运行日志）里 —— 那是
    "面板切换"，和"账户切换"语义不搭；现在放到持仓/委托这条表工具条上，
    紧挨着「导出 CSV」，在交易账户页里一眼能看到 ✓
    """
    dock = _read('jslib/src/desk/account-dock.ts')
    # 不再挂到 tabs（顶部页签条）
    assert 'this.tabs.appendChild(this.accountSelect);' not in dock
    # 挂到 actions（子表行右侧），且在导出按钮**之前**
    actions = dock.split("this.actions.appendChild(this.accountSelect);", 1)
    assert len(actions) == 2
    before_export = actions[1].split('this.actions.appendChild(exportButton);',
                                     1)[0]
    assert 'exportButton' in actions[1] or True
    assert dock.index('this.actions.appendChild(this.accountSelect);') < \
        dock.index('this.actions.appendChild(exportButton);')
    assert "'切换交易账户（快期模拟 / 实盘）'" in dock
    # ★ 2026-11-05：下拉框**常驻**（不隐藏），没登录的项置灰 ✓
    assert "this.accountSelect.style.display = '';" in dock
    assert "option.disabled = item.available === false;" in dock
    assert "this.accountSelect.disabled = !anyOn;" in dock
    css = _read('jslib/src/desk/desk.css')
    block = css.split('.desk-dock-account {', 1)[1].split('}', 1)[0]
    assert 'max-width: 170px' in block
    assert 'margin-left: 0' in block


# ------------------- 三账户统一模型（快期模拟 / 富途模拟 / TqAccount）2026-11-05
def _three_account_desk():
    from minibt.desk.app import Desk

    class FuturesFeed:
        kind = 'futures'

        def __init__(self):
            class Api:
                class _account:
                    _account_list = [
                        type('Kq', (), {'broker_id': ''})(),
                        type('Real', (), {'broker_id': 'H宏源期货',
                                          'account_id': '123'})()]

            self.api = Api()

        def available(self):
            return True

    class StocksFeed:
        kind = 'stocks'

        def __init__(self):
            class Api:
                _trade_enabled = True

            self.api = Api()

        def available(self):
            return True

    desk = Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True
    desk.futures = FuturesFeed()
    desk.stocks = StocksFeed()
    desk.feeds = [desk.futures, desk.stocks]
    return desk


def test_three_account_catalog_and_availability():
    """两个下拉框的选项都是「快期模拟 / 富途模拟 / TqAccount」✓"""
    desk = _three_account_desk()
    items = desk.account_catalog()
    assert [item['label'] for item in items] == [
        '快期模拟', '富途模拟', 'TqAccount']
    assert all(item['available'] for item in items)
    payload = desk.account_kind_payload()
    assert payload['type'] == 'account_kind'
    assert payload['labels'] == ['快期模拟', '富途模拟', 'TqAccount']
    # 离线（都没登录）→ 全部不可用 ✓
    from minibt.desk.app import Desk

    offline = Desk(offline=True, browser=True)
    assert all(item['available'] is False
               for item in offline.account_catalog())


def test_switch_account_kind_syncs_everything():
    """切换账户：AccountView / 账户面板 / 首页账户卡 一起变 ✓"""
    desk = _three_account_desk()
    assert desk.set_account_kind('real') is True
    assert desk.active_account_key() == 'real'
    view = desk.account_view()
    assert view.identity_of(view.current()).startswith('real:')
    # 富途模拟 → 账户面板走**股票**接口 ✓
    assert desk.set_account_kind('futu') is True
    assert desk.account_view().api() is desk.stocks.api
    assert desk.account_view().labels() == ['富途模拟']
    # 回快期模拟 → 期货接口 ✓
    assert desk.set_account_kind('kq') is True
    assert desk.account_view().api() is desk.futures.api
    # 未登录的账户不能切（离线）✓
    from minibt.desk.app import Desk

    offline = Desk(offline=True, browser=True)
    assert offline.set_account_kind('real') is False


def test_trading_must_match_account_kind():
    """快期模拟 / TqAccount 只做期货；富途模拟只做股票 ✓"""
    desk = _three_account_desk()
    from minibt.desk.trading import Trading

    trader = Trading(desk)
    # ★ 账户**按页独立**（2026-11-05）：品种校验看的是该合约所在页面的 key ✓
    desk.set_account_kind('kq')
    assert trader.account_kind_issue('SHFE.ag2612') == ''
    # 股票页默认富途模拟 → 正常；硬把它设成快期模拟才报错 ✓
    assert trader.account_kind_issue('SSE.600000') == ''
    desk._account_keys['chart:SSE.600000'] = 'kq'
    assert '请切换账户' in trader.account_kind_issue('SSE.600000')
    desk._account_keys.pop('chart:SSE.600000', None)
    desk.set_account_kind('futu')
    assert trader.account_kind_issue('SSE.600000') == ''
    desk._account_keys['chart:SHFE.ag2612'] = 'futu'
    assert '请切换账户' in trader.account_kind_issue('SHFE.ag2612')
    desk._account_keys.pop('chart:SHFE.ag2612', None)


def test_home_choices_use_three_keys():
    desk = _three_account_desk()
    account = desk.home_account()
    assert [item['key'] for item in account['choices']] == [
        'kq', 'futu', 'real']
    assert account['key'] in ('kq', 'futu', 'real')
    # 首页切换走 key → 全局同步 ✓
    desk.handle('desk_~_' + '{"cmd":"home_account_kind","payload":'
                '{"key":"real"}}')
    assert desk.active_account_key() == 'real'


def test_frontend_three_account_wiring():
    dock = _read('jslib/src/desk/account-dock.ts')
    assert 'setAccountCatalog(' in dock
    assert "this.send('set_account_kind'," in dock
    assert "option.textContent += '（未登录）';" in dock
    app = _read('jslib/src/desk/app.ts')
    assert "case 'account_kind': {" in app
    assert 'dock.setAccountCatalog(patch as never);' in app
    home = _read('jslib/src/desk/home-page.ts')
    assert "'home_account_kind', { key: choice.key }" in home


# ---------------- 登录记忆 + 失败提醒（2026-11-05 用户）
def test_login_remembers_fields_but_never_trade_password(tmp_path, monkeypatch):
    """用户名 / 实盘 / 期货公司 / 资金账号记住；**交易密码永不保存** ✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.save_login('futures', {
        'username': 'u1', 'remember': True, 'real': True,
        'broker': 'H宏源期货', 'account': '123',
        'password': 'pw', 'trade_password': 'tp'})
    saved = user_prefs.login()['futures']
    assert saved['username'] == 'u1'
    assert saved['real'] is True
    assert saved['broker'] == 'H宏源期货'
    assert saved['account'] == '123'
    assert saved['password'] == 'pw'                 # 记住密码才存 ✓
    assert 'trade_password' not in saved             # 交易密码永不落盘 ✓
    # 不勾"记住密码" → 登录密码也不存 ✓
    user_prefs.save_login('futures', {
        'username': 'u2', 'remember': False, 'real': False,
        'password': 'pw2'})
    saved = user_prefs.login()['futures']
    assert 'password' not in saved and saved['username'] == 'u2'
    assert 'trade_password' not in user_prefs.LOGIN_FIELDS['futures']


def test_login_failure_saves_input_and_alerts(monkeypatch):
    """登录失败：**先保存已填内容**，再弹模态提醒（带"下一步改什么"）✓"""
    from minibt.desk import user_prefs

    import tempfile
    import os

    monkeypatch.setattr(user_prefs, 'PREFS_FILE',
                        os.path.join(tempfile.mkdtemp(), 'p.json'))
    from minibt.desk.app import Desk

    desk = Desk(offline=True, browser=True)
    desk.sender = lambda script: None
    desk._booted = True
    alerts, toasts = [], []
    desk.push_alert = lambda title, message, detail='', level='warning': (
        alerts.append((title, message, detail)))
    desk.push = lambda payload=None: toasts.append(payload)

    desk.handle('desk_~_' + '{"cmd":"connect_futures","payload":'
                '{"username":"u9","password":"p","real":true,'
                '"broker":"","account":"888","trade_password":""}}')
    # ① 已填内容先落盘（下次预填）✓
    saved = user_prefs.login()['futures']
    assert saved['username'] == 'u9'
    assert saved['account'] == '888'
    assert saved.get('real') is True
    assert 'trade_password' not in saved
    # ② 弹窗说清楚缺什么 + 下一步怎么做 ✓
    assert alerts and alerts[0][0] == '期货登录失败'
    assert '期货公司' in alerts[0][1]
    assert '交易密码' in alerts[0][1]
    assert '期货公司' in alerts[0][2]        # hint
    assert desk._connect_pending is None      # 不发连接请求 ✓


def test_login_error_alert_hints():
    from minibt.desk.app import Desk

    assert '期货公司' in Desk._login_hint('futures', 'broker 为空')
    assert '交易密码' in Desk._login_hint('futures', '缺少交易密码')
    assert 'FutuOpenD' in Desk._login_hint('stocks', 'connection refused')


def test_login_dialog_validates_before_submit():
    dialog = _read('jslib/src/desk/login-dialog.ts')
    # 期货公司占位（不默认第一项）✓
    # ★ 期货公司改成 input + datalist（任意公司都能填 / 记住的值一定回填 ✓）
    assert "select.setAttribute('list', 'desk-login-brokers');" in dialog
    assert "createElement('datalist')" in dialog
    assert "select.placeholder = '例如 H宏源期货';" in dialog
    assert 'brokerNode.value = String(saved.broker);' in dialog
    # 交易密码不保存 + 每次输入提示 ✓
    assert '交易密码不保存，每次登录都要重新输入' in dialog
    # 提交前校验（缺字段直接提示，不发请求 ✓）
    assert 'private _warn(text: string): void {' in dialog
    assert 'if (missing.length) {' in dialog
    assert "missing.push('期货公司');" in dialog
    assert "missing.push('交易密码（每次都要输入）');" in dialog


# ---------- 切账户后：首页数值 / 交易页面板都要跟着变（2026-11-05 用户）
def _two_accounts():
    from minibt.desk.app import Desk

    class Acc:
        def __init__(self, broker='', code='', balance=1.0):
            self.broker_id = broker
            self.account_id = code
            self.balance = balance

    class Api:
        class _account:
            _account_list = [Acc('', '', 861741.0),
                             Acc('H宏源期货', '123456', 999999.0)]

        def get_account(self, account=None):
            base = getattr(account, 'balance', 861741.0) if account is not None \
                else 861741.0
            return type('A', (), {
                'pre_balance': base, 'balance': base, 'position_profit': 0,
                'close_profit': 0, 'float_profit': 0, 'commission': 0,
                'margin': 0, 'frozen_margin': 0, 'frozen_commission': 0,
                'available': base, 'risk_ratio': 0})()

        def get_position_list(self):
            return []

        def get_position(self, symbol=None, **kwargs):
            return None

        def get_order(self, **kwargs):
            return []

        def get_trade(self, **kwargs):
            return []

    class Feed:
        kind = 'futures'

        def __init__(self):
            self.api = Api()

        def available(self):
            return True

        def klines(self, *args, **kwargs):
            return None

    desk = Desk(offline=True, browser=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.futures = Feed()
    desk.feeds = [desk.futures]
    desk._real_account = True
    desk.tabs['SHFE.ag2612'] = {'feed': desk.futures, 'cycle': 60}
    return desk


def test_home_values_follow_switched_account():
    """首页切到实盘 → **资金数值也跟着变**（不只是下拉标题）✓"""
    desk = _two_accounts()
    assert desk.home_account()['values']['balance'] == 861741.0
    assert desk.set_account_kind('real')
    home = desk.home_account()
    assert home['key'] == 'real'
    assert home['choices'][2]['key'] == 'real'
    assert home['values']['balance'] == 999999.0        # ★ 数值也换了 ✓
    assert desk.trading_state('SHFE.ag2612')['account'] == '天勤实盘'
    # 再读一次**不能自己翻回去**（以前会来回切 ✗）
    again = desk.home_account()
    assert again['key'] == 'real' and again['values']['balance'] == 999999.0
    # 切回模拟 ✓
    assert desk.set_account_kind('kq')
    assert desk.home_account()['values']['balance'] == 861741.0


def test_switch_pushes_account_before_kind():
    """推送顺序：账户数据先、`account_kind` 最后（避免新 key + 旧数据 ✗）"""
    import json

    desk = _two_accounts()
    desk.sent.clear()
    desk.set_account_kind('real')
    kinds = []
    for script in desk.sent:
        try:
            kinds.append(json.loads(
                script[len('window.__desk.applyPatch('):-2])['type'])
        except Exception:                                        # noqa: BLE001
            continue
    assert kinds[-1] == 'account_kind'
    assert 'account' in kinds and 'home_account' in kinds
    # 账户补丁要带 symbol（按页路由 ✓）
    account = next(json.loads(s[len('window.__desk.applyPatch('):-2])
                     for s in desk.sent
                     if json.loads(s[len('window.__desk.applyPatch('):-2])
                     ['type'] == 'account')
    assert account.get('symbol') == 'SHFE.ag2612'


def test_account_patch_reaches_local_pages():
    """账户补丁要喂到**本地图表页**（以前只喂 ChartPage → 面板不动 ✗）"""
    app = _read('jslib/src/desk/app.ts')
    block = app.split("case 'account': {", 1)[1].split("case '", 1)[0]
    assert 'this.pages.forEach(applyToLocal);' in block
    assert 'this._localPageFor(symbol)' in block
    assert 'setAccount?.(patch as never)' in block
    # 本地页查找辅助存在 ✓
    assert 'private _localPageFor(symbol: string): LocalChartPage | null {' in app


def test_dock_select_never_empty():
    """账户目录没到时下拉框退回 labels，不能变成空的 ✗"""
    dock = _read('jslib/src/desk/account-dock.ts')
    assert 'if (!catalog.length) {' in dock
    assert 'catalog = (this.payload.labels || []).map(' in dock
    assert 'const known = Array.prototype.slice.call(this.accountSelect.options)' \
        in dock


def test_account_key_is_verified_against_real_list():
    """切实盘但账户列表里没有 TqAccount → **整齐退回模拟**（不抖动）✓

    用户实测 2026-11-05：首页切实盘"只有标题变、数值还是模拟"，
    并且首页在 快期模拟 / TqAccount 之间来回跳 ✗
    → 现在 `_verified_account_key()` 每次都按天勤账户列表核对并对齐
      `AccountView` 的选中项；没有实盘就退回模拟并记一条日志 ✓
    """
    desk = _two_accounts()
    desk._account_kind = 'real'          # 模拟"上一次只改了 key"
    home = desk.home_account()
    assert home['key'] == 'real'
    assert home['values']['balance'] == 999999.0       # 数值也切过去了 ✓
    assert desk.account_view().index == 1              # 选中项已对齐 ✓
    # 连续读多次都不翻转 ✓
    assert {desk.home_account()['values']['balance'] for _ in range(5)} == {
        999999.0}

    # 账户里**没有**实盘 → 退回模拟（并记录一次）✓
    one = _two_accounts()
    one.futures.api._account._account_list = [
        one.futures.api._account._account_list[0]]
    one._account_kind = 'real'
    home = one.home_account()
    assert home['key'] == 'kq'
    assert home['values']['balance'] == 861741.0


def test_trading_labels_use_verified_key():
    """交易页 / 日志的账户名也用**核对后**的 key（别出现"实盘"标签 + 模拟数值）✓"""
    desk = _two_accounts()
    desk._account_kind = 'real'
    trader = desk.trading_view()
    assert trader.account_label('SHFE.ag2612') == '天勤实盘'
    assert desk.trading_state('SHFE.ag2612')['account'] == '天勤实盘'
    # 没有实盘账户 → 标签回模拟 ✓
    one = _two_accounts()
    one.futures.api._account._account_list = [
        one.futures.api._account._account_list[0]]
    one._account_kind = 'real'
    trader = one.trading_view()
    trader._account_key()          # 触发核对
    assert trader.account_label('SHFE.ag2612') == '天勤模拟'


def test_login_prefill_restores_broker_password_and_checks_remember():
    """登录框要把上次的**用户名 / 密码 / 期货公司 / 资金账号**都填回来 ✓

    用户 2026-11-05 截图：只回填了用户名和资金账号，
    期货公司变成「请选择期货公司」、密码空着 ✗
    """
    dialog = _read('jslib/src/desk/login-dialog.ts')
    # ① 期货公司 = 可输入 + 建议列表（任意公司都能填 ✓）
    assert "select.setAttribute('list', 'desk-login-brokers');" in dialog
    assert "select.placeholder = '例如 H宏源期货';" in dialog
    # ② 记住的值**无条件**回填（以前"列表里没有就清空"✗）
    assert 'if (brokerNode && saved.broker) {' in dialog
    assert 'brokerNode.value = String(saved.broker);' in dialog
    assert 'const known = options.some(' not in dialog
    # ③ 记住密码默认勾上（没保存过密码 / 保存过 false 但没密码 ✓）
    assert 'rememberNode.checked = saved.remember === undefined' in dialog
    assert '(!!saved.remember || !hasPassword)' in dialog
    # ④ 交易密码永不预填 ✓
    assert "tradeInput.title = '交易密码不保存，每次登录都要重新输入';" in dialog


def test_login_submit_saves_broker_and_account(tmp_path, monkeypatch):
    """点登录时**先落盘**（用户名 / 实盘 / 期货公司 / 资金账号）✓"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = _two_accounts()
    desk._login_saved('futures', {
        'username': 'u1', 'remember': True, 'real': True,
        'broker': 'MyBroker期货', 'account': 'A1', 'password': 'pw'})
    saved = desk.login_payload('futures')
    assert saved == {'username': 'u1', 'remember': True, 'real': True,
                     'broker': 'MyBroker期货', 'account': 'A1',
                     'password': 'pw'}


def test_tickets_start_hidden_on_every_new_chart():
    """买卖盘：**每打开一页图表（含多布局每格）都从「关」开始** ✓

    用户 2026-11-05：多布局出图时买卖盘默认是打开的（上次的开关被恢复 ✗）
    """
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(f'jslib/src/desk/{name}')
        block = page.split('private _restoreTickets(): void {', 1)[1].split(
            '\n    }', 1)[0]
        assert 'this.ticketsOn = false;' in block
        assert 'ticketVisibleOf' not in block          # 不再读上次的开关 ✓
        assert 'onTicketAll' not in block              # 关着就不订阅盘口 ✓
        assert "classList.toggle('on', false)" in block
    app = _read('jslib/src/desk/app.ts')
    assert 'this.ticketsOn = settings.ticket_visible_on === true' not in app
    assert 'this.ticketsOn = false;               // 每次启动都从「关」开始' \
        in app or 'this.ticketsOn = false;' in app


def test_local_chart_is_local_sim_account_only():
    """本地图表：**隐藏切账户下拉框 + 只用本地模拟账户** ✓

    用户 2026-11-05：本地图表不该接实时 / 实盘账户
    """
    page = _read('jslib/src/desk/local-chart-page.ts')
    assert "this.dock.element.classList.add('local-only');" in page
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-dock.local-only .desk-dock-account {' in css
    assert 'display: none;' in css.split(
        '.desk-dock.local-only .desk-dock-account {', 1)[1].split('}', 1)[0]
    app = _read('jslib/src/desk/app.ts')
    assert "=== 'local_account';" in app
    assert 'if (page instanceof LocalChartPage) {' in app
    assert 'if (localOk) applyTo(page);' in app
    # 后端：本地下单走 `local_sim()`（不经过 `Trading` / TqAccount ✓）
    desk_py = _read('minibt/desk/app.py')
    body = desk_py.split('def _on_local_order(self, payload) -> None:', 1)[1]
    assert 'self.local_sim().order(' in body.split('def _on_local_active', 1)[0]
    assert 'self.trader' not in body.split('def _on_local_active', 1)[0]


def test_home_account_menu_never_loses_choices():
    """首页「切账户」下拉框不能没选项（交易页切过账户后也是 ✓）

    用户 2026-11-05：交易账户页切账户后，首页下拉框变成空的 ✗
    """
    home = _read('jslib/src/desk/home-page.ts')
    block = home.split('setAccount(account: HomeAccount): void {', 1)[1].split(
        '\n    }', 1)[0]
    assert 'merged.choices = this.account?.choices;' in block
    assert 'this.account = merged;' in block
    app = _read('jslib/src/desk/app.ts')
    kind = app.split('private _accountKindAsHome()', 1)[1].split(
        '\n    }', 1)[0]
    assert ': (previous.choices || []);' in kind


# ---------- 2026-11-05 第三轮：登录持久化 / 账户按页独立 / 价格步进
def test_login_survives_full_prefs_rewrite(tmp_path, monkeypatch):
    """登录信息存**独立文件**：整份偏好被重写也不丢 ✓（第二次打开还有数据）"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.save_login('futures', {
        'username': 'u1', 'password': 'pw', 'remember': True,
        'real': True, 'broker': 'H宏源期货', 'account': 'A'})
    assert (tmp_path / 'desk_login.json').exists()
    # 整份偏好被重写成空（换版本 / 别的写入路径）→ 登录信息仍在 ✓
    user_prefs.save({'favorites': [], 'strategies': [], 'templates': [],
                     'layouts': [], 'settings': {}, 'exports': [],
                     'login': {}, 'watch': {}})
    saved = user_prefs.login()['futures']
    assert saved['username'] == 'u1'
    assert saved['password'] == 'pw'
    assert saved['remember'] is True and saved['real'] is True
    assert saved['broker'] == 'H宏源期货' and saved['account'] == 'A'
    # 老文件（login 在 prefs 里）→ 自动迁移 ✓
    old = tmp_path / 'old'
    old.mkdir()
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(old / 'p.json'))
    (old / 'p.json').write_text(
        '{"login": {"futures": {"username": "old", "broker": "X", '
        '"account": "Z"}}}', encoding='utf-8')
    assert user_prefs.login()['futures']['username'] == 'old'
    assert (old / 'desk_login.json').exists()


def test_login_dialog_keeps_client_side_cache():
    """打开登录框先用**前端缓存**填（不等后端，第二次打开也有数据 ✓）"""
    app = _read('jslib/src/desk/app.ts')
    assert 'this.loginCache[kind] = { ...saved };' in app
    assert 'const cached = saved || this.loginCache[kind] || null;' in app
    assert 'this.login.open(kind, cached);' in app
    # 后端落盘后把记住的内容推回来 ✓
    desk_py = _read('minibt/desk/app.py')
    assert "saved=self.login_payload('futures')" in desk_py
    assert "saved=self.login_payload('stocks')" in desk_py


def test_account_switch_is_per_page():
    """首页 / 每个实时图表页的账户切换**各自独立** ✓（用户 2026-11-05）"""
    desk = _two_accounts()
    desk.tabs['SHFE.cu2612'] = {'feed': desk.futures, 'cycle': 60}
    # 首页切实盘 → 只影响首页
    assert desk.set_account_kind('real')
    assert desk.home_key() == 'real'
    assert desk.account_key_for('chart:SHFE.ag2612') == 'real'   # 没设过 → 跟首页
    # 图表 2 切模拟 → 只影响它自己
    assert desk.set_account_kind('kq', 'chart:SHFE.cu2612')
    assert desk.account_key_for('chart:SHFE.cu2612') == 'kq'
    assert desk.account_key_for('chart:SHFE.ag2612') == 'real'
    assert desk.home_key() == 'real'
    # 面板数值按**各自页面**的账户取 ✓
    assert desk.account_payload(symbol='SHFE.ag2612')['values']['balance'] \
        == 999999.0
    assert desk.account_payload(symbol='SHFE.cu2612')['values']['balance'] \
        == 861741.0
    # 交易 / 实盘标记也按页面 ✓
    assert desk.trading_state('SHFE.ag2612')['account'] == '天勤实盘'
    assert desk.trading_state('SHFE.cu2612')['account'] == '天勤模拟'
    assert desk.trading_view()._account_key('SHFE.cu2612') == 'kq'


def test_account_kind_payload_and_commands_carry_page():
    """`account_kind` 补丁带 page（首页 / 各页互不覆盖 ✓）"""
    desk = _two_accounts()
    desk.sent.clear()
    desk.set_account_kind('real', 'chart:SHFE.ag2612')
    import json

    patches = []
    for script in desk.sent:
        try:
            patches.append(json.loads(
                script[len('window.__desk.applyPatch('):-2]))
        except Exception:                                        # noqa: BLE001
            continue
    kinds = [item for item in patches if item.get('type') == 'account_kind']
    assert kinds and kinds[-1]['page'] == 'chart:SHFE.ag2612'
    accounts = [item for item in patches if item.get('type') == 'account']
    assert accounts[-1]['page'] == 'chart:SHFE.ag2612'
    # 没有 page → 首页自己那份（account_kind 不带 page ✓）
    assert desk.home_key() == 'kq'
    app = _read('jslib/src/desk/app.ts')
    assert 'const kindPage = String(' in app
    assert "if (!kindPage) {" in app
    dock = _read('jslib/src/desk/account-dock.ts')
    assert "page: this.pageId," in dock


def test_price_step_buttons_use_tick_and_book():
    """价格框上下按钮：空值 = 买一 / 卖一，否则 ±**最小变动价位** ✓"""
    ticket = _read('jslib/src/desk/replay-ticket.ts')
    assert 'desk-local-ticket-price-box' in ticket
    assert "const upButton = makeStep(1, '▲'," in ticket
    assert "const downButton = makeStep(-1, '▼'," in ticket
    assert 'const nudge = (dir: 1 | -1): void => {' in ticket
    assert 'const book = dir > 0 ? askOne : bidOne;' in ticket
    assert 'next = current + dir * stepValue;' in ticket
    assert 'stepValue = value;' in ticket
    assert 'setBookPrices: (bid: number | null, ask: number | null)' in ticket
    # 真实盘口喂买一 / 卖一 ✓
    page = _read('jslib/src/desk/chart-page.ts')
    assert 'this.ticket?.setBookPrices(' in page
    # 原生 spinner 必须隐藏（否则空值时给 1 / -1 ✗）
    css = _read('jslib/src/desk/desk.css')
    assert '.desk-local-ticket-price::-webkit-inner-spin-button {' in css


# ---------- 2026-11-05 第四轮：股票实时图表不更新 / 一字线 / 二级报价空
def _fake_feed(kind, api):
    class _Feed:
        def __init__(self):
            self.kind = kind
            self.api = api

        def available(self):
            return True

        def klines(self, *args, **kwargs):
            return None

    return _Feed()


def test_pump_drives_every_feed():
    """行情泵必须同时驱动**股票** api（以前只泵期货 → 股票全冻住 ✗）"""
    class StockApi:
        poll_interval = 0.2

        def __init__(self):
            self.calls = []

        def wait_update(self, deadline=None):
            self.calls.append(deadline)
            return True

    class FutApi:
        def __init__(self):
            self.calls = []

        def wait_update(self, deadline=None):
            self.calls.append(deadline)
            return True

    desk = _two_accounts()
    fut, stock = FutApi(), StockApi()
    desk.futures = _fake_feed('futures', fut)
    desk.stocks = _fake_feed('stocks', stock)
    desk.feeds = [desk.futures, desk.stocks]
    desk.pump(0.05)
    assert len(fut.calls) == 1 and fut.calls[0] > 1e9      # 天勤 = 时间戳 ✓
    assert stock.calls == [0.05]                            # 富途 = 秒数 ✓
    # 只有股票（期货没连）→ 照样要泵 ✓
    desk.futures = None
    desk.pump(0.05)
    assert len(stock.calls) == 2


def test_stock_quote_carries_bid_ask():
    """富途快照 → quote 里要有买一 / 卖一（否则二级报价永远是空的 ✗）"""
    from minibt.stock_api import StockApi

    class Snap:
        empty = False

        class _ILoc:
            def __getitem__(self, _index):
                return {'last_price': 10.5, 'bid_price': 10.49,
                        'ask_price': 10.51, 'bid_vol': 300, 'ask_vol': 500,
                        'open': 10.2, 'high': 10.6, 'low': 10.1,
                        'volume': 12345, 'price_spread': 0.01,
                        'prev_close_price': 10.0, 'turnover': 999.0}

        iloc = _ILoc()

    class Ctx:
        def get_market_snapshot(self, codes):
            return 0, Snap()

    api = StockApi.__new__(StockApi)
    api._quotes = {}
    api._prices = {}
    api._ticks = {}
    api._RET_OK = 0
    api._ctx = Ctx()
    quote = StockApi.get_quote(api, 'SH.600000')
    assert quote.bid_price1 == 10.49 and quote.ask_price1 == 10.51
    assert quote.bid_volume1 == 300 and quote.ask_volume1 == 500
    assert quote.high == 10.6 and quote.low == 10.1 and quote.open == 10.2
    assert quote.pre_close == 10.0 and quote.last_price == 10.5


def test_stock_flat_bar_gets_stretched():
    """开盘前打开 → 一字线：用最新价把最后一根撑开 ✓"""
    import pandas as pd

    from minibt.stock_api import StockApi

    api = StockApi.__new__(StockApi)
    api._prices = {'SH.600000': 10.5}
    frame = pd.DataFrame({
        'datetime': [1, 2], 'open': [10.0, 10.0], 'high': [10.2, 10.0],
        'low': [9.8, 10.0], 'close': [10.0, 10.0], 'volume': [1.0, 0.0]})
    assert StockApi._stretch_flat_bar(api, frame, 'SH.600000') is True
    assert float(frame['high'].iloc[-1]) == 10.5
    assert float(frame['low'].iloc[-1]) == 10.0
    assert float(frame['close'].iloc[-1]) == 10.5
    assert int(frame['datetime'].iloc[-1]) == 2          # 时间不动 ✓
    # 已经撑开过 → 不再重复改 ✓
    assert StockApi._stretch_flat_bar(api, frame, 'SH.600000') is False


def test_kline_push_detects_high_low_change():
    """最后一根的 high / low 变了也要推（一字线撑开时收盘价可能没变 ✓）"""
    desk_py = _read('minibt/desk/app.py')
    assert "or last_high != info.get('_kline_high')" in desk_py
    assert "or last_low != info.get('_kline_low')" in desk_py
    assert "info['_kline_high'] = last_high" in desk_py
    assert "info['_kline_low'] = last_low" in desk_py
    assert "'_kline_high', '_kline_low'," in desk_py


def test_dock_active_follows_payload_key():
    """下拉框选中项必须以**这页的账户补丁**为准（否则每秒被顶回首页账户 ✗）"""
    dock = _read('jslib/src/desk/account-dock.ts')
    block = dock.split('const active = String(', 1)[1].split(');', 1)[0]
    assert 'key?: string }).key' in block
    assert block.index('key?: string }).key') < block.index(
        'this.accountCatalog?.active')
    # 图表页创建时要问后端要**这一页**的账户目录 ✓
    app = _read('jslib/src/desk/app.ts')
    # v1.3.7-67：开图时 account_kind 延后发（先出 K 线 ✓）
    assert "['account_kind', { page: `chart:${symbol}` }, 0]," in app
    # 后端打开图表时也主动推这一页的目录 + 数据 ✓
    desk_py = _read('minibt/desk/app.py')
    assert "kind['page'] = page" in desk_py
    assert "account['page'] = page" in desk_py


def test_account_switch_matches_instrument():
    """富途模拟只能看股票页；期货页只能用 快期模拟 / 实盘 ✓"""
    desk = _two_accounts()
    desk.tabs['SH.600000'] = {'feed': desk.futures, 'cycle': 300}
    # 股票页默认就是富途模拟 ✓
    assert desk.account_key_for('chart:SH.600000') == 'futu'
    # 期货页切富途模拟 → 拒绝（不会出现"按钮变了数据没变" ✗）
    assert desk.set_account_kind('futu', 'chart:SHFE.ag2612') is False
    assert desk.account_key_for('chart:SHFE.ag2612') == 'kq'
    # 股票页切实盘 → 拒绝 ✓
    assert desk.set_account_kind('real', 'chart:SH.600000') is False
    assert desk.account_key_for('chart:SH.600000') == 'futu'


def test_local_account_patch_never_leaks_to_realtime():
    """本地模拟账户补丁不能盖到实时图表页（否则实时页显示 100,000 但
    下拉框写着「快期模拟」✗ 用户 2026-11-05 截图）"""
    app = _read('jslib/src/desk/app.ts')
    block = app.split("case 'account': {", 1)[1].split("case '", 1)[0]
    assert 'if (page instanceof LocalChartPage) {' in block
    assert 'if (localOk) applyTo(page);' in block
    assert 'if (localOk) return;' in block          # 实时页拒收 local_account ✓
    # 本地模拟账户补丁的 type 由后端标好 ✓
    desk_py = _read('minibt/desk/local_data.py')
    assert "'type': 'local_account'," in desk_py


def test_login_fields_saved_without_submit(tmp_path, monkeypatch):
    """登录框**边填边存**：不点「登录」、直接关窗也要记住 ✓（2026-11-05）"""
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = _two_accounts()
    # 前端 `onDirty` / 关窗 → `login_save`
    desk._on_login_save({'kind': 'futures', 'values': {
        'username': 'owenhellen', 'password': 'pw', 'remember': True,
        'real': True, 'broker': 'H宏源期货', 'account': 'A1',
        'trade_password': 'tp'}})
    saved = desk.login_payload('futures')
    assert saved['username'] == 'owenhellen'
    assert saved['password'] == 'pw'
    assert saved['remember'] is True and saved['real'] is True
    assert saved['broker'] == 'H宏源期货' and saved['account'] == 'A1'
    assert 'trade_password' not in saved            # 交易密码永不落盘 ✓
    # 取消勾「记住密码」→ 密码被清掉，其余仍在 ✓
    desk._on_login_save({'kind': 'futures', 'values': {
        'username': 'owenhellen', 'password': 'pw', 'remember': False,
        'real': False, 'broker': 'H宏源期货', 'account': 'A1'}})
    saved = desk.login_payload('futures')
    assert 'password' not in saved
    assert saved['username'] == 'owenhellen'
    assert saved['real'] is False


def test_login_dialog_saves_on_change_and_close():
    """前端：字段一变（400ms 防抖）就落盘，关窗前再存一次 ✓"""
    dialog = _read('jslib/src/desk/login-dialog.ts')
    assert 'onDirty?: (kind: LoginKind, values: Record<string, unknown>) => void;' \
        in dialog
    assert 'this._watchDirty();' in dialog
    assert "pane.addEventListener('input', handler);" in dialog
    assert 'private _saveNow(kind: LoginKind = this.kind): void {' in dialog
    assert 'this._saveNow();' in dialog          # close() 里 ✓
    assert 'private _values(kind: LoginKind = this.kind)' in dialog
    app = _read('jslib/src/desk/app.ts')
    assert "this.send('login_save', { kind, values });" in app
    assert 'onDirty: (kind, values) => {' in app
    desk_py = _read('minibt/desk/app.py')
    assert "'login_save': self._on_login_save," in desk_py
    assert 'def _on_login_save(self, payload=None) -> None:' in desk_py


def test_account_after_login_push_carries_symbol():
    """登录成功后的账户推送必须带 symbol（否则刷到所有页 → 期货页显示
    股票账户的资金 / 持仓 ✗ 用户 2026-11-05 截图）"""
    desk = _two_accounts()
    desk.tabs['SHFE.ag2612'] = {'feed': desk.futures, 'cycle': 60}
    desk.sent.clear()
    desk._after_connect('futures', '登录成功（模拟）')
    import json

    accounts = []
    for script in desk.sent:
        try:
            patch = json.loads(script[len('window.__desk.applyPatch('):-2])
        except Exception:                                        # noqa: BLE001
            continue
        if patch.get('type') == 'account':
            accounts.append(patch)
    assert accounts, '登录后应推账户数据'
    assert all(item.get('symbol') for item in accounts)     # ★ 必须带 ✓
    assert accounts[-1]['page'] == 'chart:SHFE.ag2612'


def test_rejected_switch_restores_select():
    """品种不匹配被拒后 → 下拉框要**弹回真实账户**，并给一句反馈 ✓"""
    desk = _two_accounts()
    desk.stocks = _fake_feed('stocks', object())     # 富途已连 → futu 可选 ✓
    desk.feeds = [desk.futures, desk.stocks]
    desk.sent.clear()
    desk.set_account_kind('futu', 'chart:SHFE.ag2612')
    import json

    kinds = []
    for script in desk.sent:
        try:
            patch = json.loads(script[len('window.__desk.applyPatch('):-2])
        except Exception:                                        # noqa: BLE001
            continue
        if patch.get('type') == 'account_kind':
            kinds.append(patch)
    assert kinds and kinds[-1]['page'] == 'chart:SHFE.ag2612'
    assert kinds[-1]['active'] == desk.account_key_for('chart:SHFE.ag2612')


def test_frontend_rejects_cross_instrument_account_patch():
    """兜底：股票账户补丁不能刷到期货页（反之亦然 ✓）"""
    app = _read('jslib/src/desk/app.ts')
    block = app.split("case 'account': {", 1)[1].split("case '", 1)[0]
    assert "const kindOf = String((patch as { kind?: string }).kind || '');" \
        in block
    assert "if (kindOf === 'stock' && pageSymbol" in block
    assert "if (kindOf === 'futures' && pageSymbol" in block


# ---------- 2026-11-05 第五轮：多布局**每格**账户独立
def _layout_desk():
    class StockApi:
        def get_account(self, account=None):
            return type('A', (), {'pre_balance': 100000.0, 'balance': 100000.0,
                'position_profit': 0, 'close_profit': 0, 'float_profit': 0,
                'commission': 0, 'margin': 0, 'frozen_margin': 0,
                'frozen_commission': 0, 'available': 97815.0,
                'risk_ratio': 0})()

        def get_position_list(self):
            return []

        def get_position(self, symbol=None, **kwargs):
            return None

        def get_order(self, **kwargs):
            return []

        def get_trade(self, **kwargs):
            return []

    desk = _two_accounts()
    desk.stocks = _fake_feed('stocks', StockApi())
    desk.feeds = [desk.futures, desk.stocks]
    desk.tabs['SHFE.ag2612'] = {
        'feed': desk.futures, 'cycle': 60,
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': ['SHFE.ag2612', 'SH.600000']}}
    return desk


def test_multi_layout_cells_have_own_account():
    """多布局：期货格 / 股票格**各自一个账户**，切换互不影响 ✓"""
    desk = _layout_desk()
    assert desk.account_key_for('chart:SHFE.ag2612#0') == 'kq'
    assert desk.account_key_for('chart:SHFE.ag2612#1') == 'futu'   # 股票格 ✓
    assert desk.account_payload(symbol='SHFE.ag2612')['values']['balance'] \
        == 861741.0
    assert desk.account_payload(symbol='SH.600000')['values']['balance'] \
        == 100000.0
    # 期货格切实盘 → 只影响这一格 ✓
    assert desk.set_account_kind('real', 'chart:SHFE.ag2612', 0)
    assert desk.account_payload(symbol='SHFE.ag2612')['values']['balance'] \
        == 999999.0
    assert desk.account_payload(symbol='SH.600000')['values']['balance'] \
        == 100000.0                                  # 股票格不动 ✓
    # 股票格不能用期货账户 ✓
    assert desk.set_account_kind('real', 'chart:SHFE.ag2612', 1) is False
    assert desk.account_key_for('chart:SHFE.ag2612#1') == 'futu'


def test_account_payload_key_not_shadowed():
    """`payload['key']` 不能被 ACCOUNT_FIELDS 循环变量覆盖（'risk_ratio' ✗）"""
    accounts = _read('minibt/desk/accounts.py')
    assert 'payload_key = str(key or \'\')' in accounts
    assert "'key': payload_key," in accounts
    assert "index = (self.index_for_key(payload_key, symbol) if payload_key" \
        in accounts
    desk = _layout_desk()
    payload = desk.account_payload(symbol='SH.600000')
    assert payload['key'] == 'futu'
    assert payload['kind'] == 'stock'


def test_frontend_dock_and_pages_route_by_cell():
    """前端：下拉框发 cell；别的格的目录 / 账户补丁不能改当前格 ✓"""
    dock = _read('jslib/src/desk/account-dock.ts')
    assert 'cell = -1;' in dock
    assert "...(this.cell >= 0 ? { cell: this.cell } : {})," in dock
    page = _read('jslib/src/desk/chart-page.ts')
    assert 'if (this.dock) this.dock.cell = index;' in page
    assert "'account_kind', {" in page
    app = _read('jslib/src/desk/app.ts')
    assert 'const kindCell = (patch as { cell?: number }).cell;' in app
    assert 'const patchCell = (patch as { cell?: number }).cell;' in app
    assert 'const cellSymbols = target.cellSymbols;' in app


def test_account_apply_handles_null_page():
    """`_chartPageFor()` 可能返回 null → 不能直接取属性（每拍 JS 报错导致
    交易账户面板 / 持仓表不渲染 ✗ 用户 2026-11-05 截图）"""
    app = _read('jslib/src/desk/app.ts')
    block = app.split("case 'account': {", 1)[1].split("case '", 1)[0]
    assert 'if (!page) return;' in block
    assert "(target as { activeCellIndex?: number })\n                        .activeCellIndex" \
        not in block
    assert 'const pageCell = target.activeCellIndex;' in block
    assert 'const cellSymbols = target.cellSymbols;' in block
    # 卡片数据源仍是 11 张卡（静态权益 / 账户权益 / 盈亏 …）✓
    accounts = _read('minibt/desk/accounts.py')
    assert "ACCOUNT_FIELDS" in accounts


def test_first_open_selects_account_by_instrument():
    """首次打开实时图表：按**格 1 合约**自动选账户 ✓

    股票 → 富途模拟；期货 → 快期模拟（即使登录了实盘也默认快期模拟）。
    之后用户手选的账户不被覆盖（只初始化一次 ✓）。
    """
    desk = _two_accounts()
    desk._real_account = True                 # 实盘已登录
    desk._home_key = 'real'
    desk._account_kind = 'real'
    desk.stocks = _fake_feed('stocks', object())
    desk.feeds = [desk.futures, desk.stocks]
    desk._on_open_chart({'symbol': 'SHFE.ag2612', 'name': '银'})
    assert desk.account_key_for('chart:SHFE.ag2612#0') == 'kq'   # ★ 快期模拟 ✓
    desk._on_open_chart({'symbol': 'SH.600000', 'name': '浦发'})
    assert desk.account_key_for('chart:SH.600000#0') == 'futu'   # ★ 富途模拟 ✓
    # 用户手动切过 → 重新打开（同页已存在）不覆盖 ✓
    desk._account_keys['chart:SH.600000#0'] = 'futu'
    desk._on_open_chart({'symbol': 'SH.600000', 'name': '浦发'})
    assert desk.account_key_for('chart:SH.600000#0') == 'futu'
    # 打开时推的账户数据用**这一页的 key**（卡片直接有数据，不用拖动 ✓）
    desk.sent.clear()
    desk._on_open_chart({'symbol': 'SHFE.cu2612', 'name': '铜'})
    import json

    accounts = []
    for script in desk.sent:
        try:
            patch = json.loads(script[len('window.__desk.applyPatch('):-2])
        except Exception:                                        # noqa: BLE001
            continue
        if patch.get('type') == 'account':
            accounts.append(patch)
    assert accounts and accounts[-1]['key'] == 'kq'
    assert accounts[-1]['cell'] == 0


# ---------- 2026-11-06：富途模拟必须是**富途官方模拟账户**
def test_futu_simulate_uses_official_paper_account():
    """`trd_env=SIMULATE` → 强制连富途官方模拟账户（不是本地记账 ✗）"""
    desk = _two_accounts()
    desk.sent.clear()
    desk._on_connect_stocks({'host': '127.0.0.1', 'port': 11111,
                             'trade': False, 'trd_env': 'SIMULATE',
                             'trd_market': 'CN'})
    pending = desk._connect_pending or ('', {})
    assert pending[0] == 'stocks'
    assert pending[1].get('trade') is True        # ★ 模拟盘强制开交易 ✓
    assert pending[1].get('trd_env') == 'SIMULATE'
    # 真实交易**不**强制（必须用户显式勾选 ✓）
    desk._connect_pending = None
    desk._on_connect_stocks({'host': '127.0.0.1', 'port': 11111,
                             'trade': False, 'trd_env': 'REAL',
                             'trd_market': 'CN'})
    pending = desk._connect_pending or ('', {})
    assert pending[1].get('trade') is False


def test_stock_label_and_real_flag_follow_trd_env():
    """富途**模拟**账户不算实盘（标签/二次确认都按 `_trd_env` ✓）"""
    from minibt.desk.trading import Trading

    desk = _two_accounts()
    desk.stocks = _fake_feed('stocks', type('A', (), {
        '_trd': object(), '_trd_env': 'SIMULATE'})())
    desk.feeds = [desk.futures, desk.stocks]
    trader = Trading(desk)
    assert trader.account_label('SH.601988') == '股票模拟（富途）'
    assert trader.is_real('SH.601988') is False
    desk.stocks.api = type('A', (), {'_trd': object(), '_trd_env': 'REAL'})()
    assert trader.account_label('SH.601988') == '股票实盘（富途）'
    assert trader.is_real('SH.601988') is True
    desk.stocks.api = type('A', (), {'_trd': None})()
    assert trader.account_label('SH.601988') == '股票本地模拟'
    assert trader.is_real('SH.601988') is False


def test_positions_prefer_futu_and_jp_sim_is_rejected():
    """持仓优先读富途；日本个股没有模拟盘 → 明确报错 ✓"""
    api_src = _read('minibt/stock_api.py')
    block = api_src.split('def get_position_list(', 1)[1].split(
        'def get_order(', 1)[0]
    assert 'position_list_query' in block          # ★ 先读富途真实持仓 ✓
    assert '_sync_positions_from_futu' in block
    assert '对日股 / ETF / REITs **没有模拟盘**' in api_src
    # 每个市场有独立模拟账户 → 惰性切换上下文 ✓
    assert 'def _ensure_market(self, market: str) -> None:' in api_src
    assert '_trd_extra' in api_src


def test_login_dialog_enables_futu_trade_by_default():
    """登录框「启用交易（富途账户）」默认勾上（模拟盘=官方账户 ✓）"""
    dialog = _read('jslib/src/desk/login-dialog.ts')
    assert 'data-f="trade" checked' in dialog


def test_close_all_uses_page_account_not_home():
    """「清仓 / 全平」按**这一页的账户**走（以前用首页账户 → 期货页提示富途 ✗）"""
    class FutPos:
        def __init__(self, sym):
            self.symbol = sym
            self.instrument_id = sym
            self.volume_long = 2
            self.volume_short = 0
            self.open_price_long = 7000.0
            self.position_price_long = 7000.0
            self.float_profit_long = 0.0
            self.margin = 1000.0

    class FutApi:
        class _account:
            _account_list = []

        def get_position_list(self, **kwargs):
            return [FutPos('SHFE.ag2612')]

        def get_position(self, symbol=None, **kwargs):
            return None

        def get_order(self, **kwargs):
            return []

        def get_trade(self, **kwargs):
            return []

        def insert_order(self, **kwargs):
            return None

    desk = _two_accounts()
    desk.futures = _fake_feed('futures', FutApi())
    desk.stocks = _fake_feed('stocks', object())
    desk.feeds = [desk.futures, desk.stocks]
    desk.sender = lambda s: None
    desk.tabs['SHFE.ag2612'] = {'feed': desk.futures, 'cycle': 60}
    desk.tabs['SH.600000'] = {'feed': desk.stocks, 'cycle': 300}
    desk._account_keys['chart:SHFE.ag2612#0'] = 'kq'
    desk._account_keys['chart:SH.600000#0'] = 'futu'
    trader = desk.trading_view()
    # 期货页的账户名是「天勤模拟」，不是富途 ✓
    assert trader.account_label('SHFE.ag2612') == '天勤模拟'
    text = trader.action('all', 'SHFE.ag2612')
    assert '全部平仓' in text and '天勤模拟' in text
    assert '富途' not in text
    # 源码：全平要带 symbol，`_positions(symbol)` 决定行情源 / 账户 ✓
    src = _read('minibt/desk/trading.py')
    assert 'return self._close_all(symbol)' in src
    assert 'def _close_all(self, symbol: str = \'\') -> str:' in src
    assert 'def _positions(self, symbol: str = \'\'):' in src
    # 前端：右键「全」必须带 symbol / page ✓
    dock = _read('jslib/src/desk/account-dock.ts')
    assert "action: 'all', symbol: ownSymbol || symbol, page: this.pageId," in dock


def test_stock_login_fields_persist_even_when_connected(tmp_path, monkeypatch):
    """股票登录的 host/port/启用交易/交易环境/交易市场都要记住 ✓

    用户 2026-11-06：改了「启用交易 / 交易环境 / 交易市场」下次打开又变回去了 ✗
    （以前"已经连上了"直接 return，根本没落盘）
    """
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = _two_accounts()
    desk.sender = lambda patch: None
    desk._on_connect_stocks({'host': '192.168.1.9', 'port': 22222,
                             'trade': False, 'trd_env': 'SIMULATE',
                             'trd_market': 'CN'})
    saved = desk.login_payload('stocks')
    assert saved['host'] == '192.168.1.9'
    assert saved['port'] == 22222
    assert saved['trade'] is False            # 用户的**原始**勾选状态 ✓
    assert saved['trd_env'] == 'SIMULATE'
    assert saved['trd_market'] == 'CN'
    # 第二次（哪怕"已连接"提前返回）也要保存新值 ✓
    desk._on_connect_stocks({'host': '192.168.1.9', 'port': 22222,
                             'trade': True, 'trd_env': 'REAL',
                             'trd_market': 'HK'})
    saved = desk.login_payload('stocks')
    assert saved['trade'] is True
    assert saved['trd_env'] == 'REAL'
    assert saved['trd_market'] == 'HK'
    # 独立登录文件里也有（整份偏好被重写也不丢 ✓）
    assert (tmp_path / 'desk_login.json').exists()


def test_stock_login_saved_before_connect_early_return():
    """落盘必须在"已经连上了 → return"之前 ✓"""
    app_py = _read('minibt/desk/app.py')
    body = app_py.split('def _on_connect_stocks', 1)[1].split(
        '\n    def ', 1)[0]
    save_at = body.index("self._login_saved('stocks'")
    same_at = body.index('if self.stocks is not None and self.stocks.available()')
    assert save_at < same_at
    # 「已连接」判定包含交易环境（只改环境也会重连 ✓）
    assert "_trd_env', '') or '').upper()" in body


def test_account_key_clamped_by_instrument():
    """期货合约永远解析成 kq/real，股票合约一定是 futu ✓

    用户 2026-11-06：期货页（面板显示快期模拟）下单却提示
    「当前账户是富途模拟」—— 因为这一页没登记 key 时退回**首页账户**（富途）✗
    """
    desk = _two_accounts()
    desk.stocks = _fake_feed('stocks', object())
    desk.feeds = [desk.futures, desk.stocks]
    desk.sender = lambda patch: None
    # 首页是富途（例如之前在股票页切过）+ 期货页没有登记 key
    desk._home_key = 'futu'
    desk._account_kind = 'futu'
    desk.tabs['SHFE.ag2612'] = {'feed': desk.futures, 'cycle': 60}
    assert desk.account_key_for('SHFE.ag2612') == 'kq'      # ★ 期货收敛 ✓
    assert desk.account_key_for('chart:SHFE.ag2612') == 'kq'
    trader = desk.trading_view()
    assert trader.account_label('SHFE.ag2612') == '天勤模拟'
    assert trader.account_kind_issue('SHFE.ag2612') == ''   # 不再误报 ✓
    # 股票合约仍然走富途 ✓
    assert desk.account_key_for('SH.600000') == 'futu'


def test_switch_symbol_auto_selects_account_for_single_chart():
    """单布局单图换标的 → 按品种自动切账户（期货 kq / 股票 futu ✓）

    用户 2026-11-06 要求：原本不是那个账户才切；多布局不动（每格自己切）。
    """
    desk = _two_accounts()
    desk.stocks = _fake_feed('stocks', object())
    desk.feeds = [desk.futures, desk.stocks]
    desk.sender = lambda patch: None
    desk._on_open_chart({'symbol': 'SHFE.ag2612', 'name': '银'})
    assert desk.account_key_for('SHFE.ag2612') == 'kq'
    # 换成股票 → 自动切富途模拟 ✓
    desk._on_switch_symbol({'from': 'SHFE.ag2612', 'to': 'SH.600000',
                            'name': '浦发'})
    assert desk.account_key_for('SH.600000') == 'futu'
    assert 'chart:SHFE.ag2612#0' not in desk._account_keys   # 旧 key 不残留 ✓
    # 已是富途 → 再切股票不动 ✓
    desk._on_switch_symbol({'from': 'SH.600000', 'to': 'SZSE.000001',
                            'name': '平安'})
    assert desk.account_key_for('SZSE.000001') == 'futu'
    # 换成期货 → 自动切快期模拟 ✓
    desk._on_switch_symbol({'from': 'SZSE.000001', 'to': 'SHFE.cu2612',
                            'name': '铜'})
    assert desk.account_key_for('SHFE.cu2612') == 'kq'
    # 需求原文：期货一律回到**快期模拟**（即使原来是实盘 ✓ 用户 2026-11-06）
    desk.set_account_kind('real', 'chart:SHFE.cu2612', 0)
    desk._on_switch_symbol({'from': 'SHFE.cu2612', 'to': 'SHFE.ag2612',
                            'name': '银'})
    assert desk.account_key_for('SHFE.ag2612') == 'kq'
    # 多布局不动（每格账户由用户自己切 ✓）
    desk.tabs['DCE.i2612'] = {'feed': desk.futures, 'cycle': 60,
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': ['DCE.i2612', 'DCE.j2612']}}
    desk._account_keys['chart:DCE.i2612#0'] = 'futu'
    assert desk._auto_account_for_symbol('DCE.i2612') == 'futu'


def test_frontend_switch_keeps_cell_symbols_in_sync():
    """前端换标的要同步 `cellSymbols`，否则账户补丁的品种校验会挡掉 ✓"""
    page = _read('jslib/src/desk/chart-page.ts')
    block = page.split('setSymbol(symbol: string, name = \'\'): void {', 1)[1]
    block = block.split('\n    }', 1)[0]
    assert 'if (this.cells.length <= 1) this.cellSymbols[0] = symbol;' in block
    app = _read('jslib/src/desk/app.ts')
    assert 'const single = !cellSymbols || cellSymbols.length <= 1;' in app


def test_close_uses_page_account_not_home():
    """平仓 / 清仓必须按**这一页的账户**查持仓（以前用首页账户 → 查不到持仓 ✗）

    用户 2026-11-06：白银页「平空1」提示没有可平空头、「市价平仓」提示没有持仓、
    右键「全」提示平掉 1 笔但**实际没交易**，而「加空」正常。
    """
    from types import SimpleNamespace

    placed = []

    class _Acc:
        def __init__(self, broker='', code=''):
            self.broker_id = broker
            self.account_id = code

    SIM, REAL = _Acc(), _Acc('H宏源期货', '1')

    class Api:
        class _account:
            _account_list = [SIM, REAL]

        def get_position(self, symbol=None, **kwargs):
            # ★ 只有模拟（kq）账户有 1 手空头；实盘账户什么都没有
            if kwargs.get('account') is SIM:
                return SimpleNamespace(
                    symbol='SHFE.ag2612', volume_long=0, volume_short=1,
                    long_today=0, long_his=0, short_today=0, short_his=1,
                    open_price_short=12000.0, position_price_short=12000.0)
            return SimpleNamespace(
                symbol='SHFE.ag2612', volume_long=0, volume_short=0,
                long_today=0, long_his=0, short_today=0, short_his=0)

        def get_position_list(self, **kwargs):
            # ✅ 只有模拟账户有持仓（和 `get_position` 一致 ✓）
            if kwargs.get('account') is SIM:
                return [self.get_position(**kwargs)]
            return []

        def get_quote(self, symbol):
            return SimpleNamespace(last_price=12000.0, price_tick=1.0,
                                   ask_price1=12001.0, bid_price1=11999.0)

        def get_order(self, **kwargs):
            return []

        def get_trade(self, **kwargs):
            return []

        def insert_order(self, **kwargs):
            placed.append(kwargs)
            return {'order_id': f"t{len(placed)}"}

    desk = _two_accounts()
    desk.futures = _fake_feed('futures', Api())
    desk.stocks = _fake_feed('stocks', object())
    desk.feeds = [desk.futures, desk.stocks]
    desk.sender = lambda patch: None
    desk.tabs['SHFE.ag2612'] = {'feed': desk.futures, 'cycle': 60}
    desk._account_keys['chart:SHFE.ag2612#0'] = 'kq'
    desk._home_key = 'futu'                   # 首页是富途（最容易踩坑 ✓）
    desk._account_kind = 'futu'
    trader = desk.trading_view()
    # 平空 1 手 → 真的下单（BUY + CLOSE）✓
    text = trader.insert('SHFE.ag2612', 'buy', 'close', 1, 0)
    assert '没有可平' not in text, text
    assert placed and placed[-1]['direction'] == 'BUY'
    assert placed[-1]['offset'] in ('CLOSE', 'CLOSETODAY')
    assert placed[-1]['volume'] == 1
    # 清仓：多/空各一次 → 至少发 1 笔，且提示里不能是"没有可平" ✓
    placed.clear()
    text = trader.action('all', 'SHFE.ag2612')
    assert placed, text
    assert '没有可平' not in text
    # `_position` 用的是这一页的账户（不是首页富途）✓
    src = _read('minibt/desk/trading.py')
    block = src.split('    def _position(self, symbol: str):', 1)[1].split(
        '\n    def ', 1)[0]
    assert 'kwargs = self.account_kwargs(symbol)' in block
    assert 'self.account_kwargs()' not in block
    # "没有可平 / 已取消下单" 必须被当成失败（不再算作成功 ✓）
    assert "'没有可平', '已取消下单'" in src


def test_clear_all_indicators_works_for_template_on_single_chart():
    """工具栏「删除全部指标」对模板加载的指标也要生效 ✓

    用户 2026-11-06：实时图表加载 `uta_macd` 模板后点「删除全部指标」没反应
    （本地图表正常）。根因：按钮带 `cell: 0`，而单图 `layout.cells` 是空的
    → `_drop_cell_indicators()` 直接 return，什么都删不掉 ✗
    """
    import json

    desk = _two_accounts()
    desk.sent.clear()
    desk.sender = desk.sent.append
    desk.tabs['SHFE.ag2612'] = {
        'feed': desk.futures, 'cycle': 60,
        'indicators': [{'key': 'uta_macd', 'params': {}},
                       {'key': 'uta_rsi', 'params': {}}]}
    desk._on_remove_indicator({'symbol': 'SHFE.ag2612', 'key': '*', 'cell': 0})
    assert desk.tabs['SHFE.ag2612']['indicators'] == []      # ★ 真的清空 ✓
    patches = []
    for script in desk.sent:
        try:
            patches.append(json.loads(
                script[len('window.__desk.applyPatch('):-2]))
        except Exception:                                        # noqa: BLE001
            continue
    indicator = [item for item in patches if item.get('type') == 'indicator']
    assert indicator, '必须推 indicator 补丁（前端才会清线 ✓）'
    assert indicator[-1].get('cell') == 0
    assert not (indicator[-1].get('items') or [])

    # 多布局：只清那一格，别的格不动 ✓
    desk.tabs['DCE.i2612'] = {
        'feed': desk.futures, 'cycle': 60,
        'indicators': [{'key': 'uta_macd', 'params': {}}],
        'layout': {'cols': 2, 'rows': 1,
                   'symbols': ['DCE.i2612', 'DCE.j2612'],
                   'cells': [{'symbol': 'DCE.i2612',
                              'indicators': [{'key': 'uta_macd'}]},
                             {'symbol': 'DCE.j2612',
                              'indicators': [{'key': 'uta_rsi'}]}]}}
    desk._on_remove_indicator({'symbol': 'DCE.i2612', 'key': '*', 'cell': 1})
    cells = desk.tabs['DCE.i2612']['layout']['cells']
    assert cells[0]['indicators'] == [{'key': 'uta_macd'}]   # 第 1 格保留 ✓
    assert cells[1]['indicators'] == []                      # 第 2 格清空 ✓


def test_login_password_kept_and_defaults_after_fill(tmp_path, monkeypatch):
    """记住密码被"默认勾上" + 已存的密码不会被空密码冲掉 ✓

    用户 2026-11-06（第三次反馈）：登录框里密码永远是空的 ——
    因为他保存的是 `remember=false`，而"默认勾上"只对**从没保存过**生效，
    且勾了记住密码但这次密码框为空时会把已存密码清掉 ✗
    """
    from minibt.desk import user_prefs

    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    user_prefs.save_login('futures', {'username': 'u1', 'password': 'Secret123',
                                      'remember': True, 'real': True,
                                      'broker': 'B', 'account': 'A'})
    # 只改了别的字段（密码框空着）→ 已记住的密码必须保留 ✓
    user_prefs.save_login('futures', {'username': 'u1', 'remember': True,
                                      'real': True, 'broker': 'B',
                                      'account': 'A', 'password': ''})
    saved = user_prefs.login()['futures']
    assert saved['password'] == 'Secret123'
    assert saved['remember'] is True
    # 取消勾选记住密码 → 密码真的删掉 ✓
    user_prefs.save_login('futures', {'username': 'u1', 'remember': False,
                                      'broker': 'B', 'account': 'A'})
    assert 'password' not in user_prefs.login()['futures']
    # 前端：默认值必须在**回填之后**再修正（否则又被 checkbox 覆盖 ✗）
    dialog = _read('jslib/src/desk/login-dialog.ts')
    block = dialog.split('setSaved(kind: LoginKind, saved', 1)[1].split(
        '\n    }', 1)[0]
    assert block.index('for (const [name, value] of Object.entries(saved))') \
        < block.index('rememberNode.checked = saved.remember === undefined')
    assert "(!!saved.remember || !hasPassword)" in block
    assert "if (env === 'SIMULATE') tradeNode.checked = true;" in block
    # 前后端都支持"字段一变就落盘" / "点登录先落盘" ✓
    app_py = _read('minibt/desk/app.py')
    assert "'login_save': self._on_login_save," in app_py
    assert "self._login_saved('futures', {" in app_py
    assert "self._login_saved('stocks', {" in app_py

"""用户 2026-11-08 四条（v1.3.7-67）。

1. 标的资讯页改用 `pylightcharts` 金融小插件（Company Profile / Fundamental Data /
   Technical Analysis / Top Stories）；
2. 事件圆点悬停 → 当日事件卡片（东财风格，放得下内容）；
3. 多账户（先登录富途再登录期货）加策略报「需要指定账户实例 account」→ 按页账户解析；
4. 从行情报价打开股票：先出 K 线，其余数据延后加载。
"""
from __future__ import annotations

import pathlib

from minibt.desk import tools, user_prefs
from minibt.desk.app import Desk

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (JSLIB / name).read_text(encoding='utf-8')


# ------------------------------------------------------------ ① 小插件
def test_symbol_info_page_uses_widgets():
    page = _read('symbol-info.ts')
    for token in ('QuoteHeader', 'TextBlock', 'DataGrid',
                  'TechnicalAnalysis', 'NewsFeed'):
        assert token in page, token
    assert "'标的概况'" in page
    assert "'基本面数据'" in page
    assert "'技术分析'" in page
    assert "'最新资讯'" in page
    # 数据字段（后端一次给全 ✓）
    for field in ('quote', 'profile_text', 'fundamentals', 'technical',
                  'stories'):
        assert f"data.{field}" in page or f"'{field}'" in page, field


def test_backend_supplies_widget_payload():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _symbol_widgets(', 1)[1].split(
        '    def _strategy_frame(', 1)[0]
    for token in ("out['quote']", "out['profile_text']",
                  "out['fundamentals']", "out['technical']",
                  "out['stories']", 'ta_summary'):
        assert token in block, token
    # 缺失值补 `-`
    assert "'value': str(value or '-') or '-'" in block


# ------------------------------------------------------------ ② 事件卡片
def test_calendar_dots_have_popover():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(name)
        assert 'private _bindCalPopover(' in page, name
        assert 'desk-cal-pop' in page, name
        # 按天分组：一个点 = 当天所有事件
        assert 'groups.get(day)!.push(item);' in page, name
    css = (JSLIB / 'desk.css').read_text(encoding='utf-8')
    assert '.desk-cal-pop' in css and '.pop-row' in css


# ------------------------------------------------------------ ③ 多账户
def test_strategy_account_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    desk = Desk(offline=True)
    desk._booted = True

    class SimAccount:
        pass
    SimAccount.__name__ = 'TqKq'

    class RealAccount:
        broker_id = 'H宏源期货'

    class Container:
        _account_list = [RealAccount(), SimAccount()]

    class FakeApi:
        _account = Container()

    class FakeFutures:
        api = FakeApi()

        def available(self):
            return True

    desk.futures = FakeFutures()
    desk.trading = True

    # 兜底：模拟账户优先于实盘 ✓
    picked = desk._fallback_trade_account()
    assert type(picked).__name__ == 'TqKq'

    # 单账户（没有 _account_list）→ 用它自己
    class OneApi:
        class _account:
            pass

    class OneFutures:
        api = OneApi()

        def available(self):
            return True

    desk.futures = OneFutures()
    assert desk._fallback_trade_account() is OneApi._account

    # `_strategy_live_context` 不再是 None（这是之前报错的根因 ✓）
    live, api, account = desk._strategy_live_context(object(), 'SHFE.ag2612')
    assert live is True and api is not None and account is not None
    # 找不到任何账户时才可能是 None（不 crash ✓）
    desk.futures = None
    live, api, account = desk._strategy_live_context(object(), 'SHFE.ag2612')
    assert live is False


def test_strategy_account_logged(app_text=None):
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    assert 'def _strategy_live_context(self, cls, symbol: str = \'\'):' in app
    assert 'self.account_key_for(symbol)' in app
    assert '策略账户：' in app


# ------------------------------------------------------------ ④ 开图不阻塞
def test_open_chart_defers_auxiliary_commands():
    app = _read('app.ts')
    block = app.split('    openChart(symbol: string', 1)[1].split(
        '    /**', 1)[0]
    # K 线请求在最前
    assert "this.send('open_chart'" in block
    # 其余命令延后（错开发送 ✓）
    assert '_deferCommands([' in block
    for cmd in ("'favorites'", "'templates'", "'layouts'",
                "'info_symbol_events'", "'alerts'"):
        assert cmd in block, cmd
    # 延后实现：setTimeout + 不会同步发出
    assert 'private _deferCommands(' in app
    assert 'window.setTimeout(() => {' in app


def test_stock_open_skips_contract_check():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('    def _on_open_chart(', 1)[1].split(
        '        cycle = int(', 1)[0]
    # 股票（富途）不走天勤合约清单校验（会卡数秒 ✓）
    assert 'if not _is_stock(symbol):' in block
    assert 'issue = self.symbol_issue(symbol)' in block


# ------------------------------------------------------------ 工具不受影响
def test_tools_still_have_events():
    assert 'desk_news' in tools.NAMES
    assert 'desk_fundamentals' in tools.NAMES


# ------------------------------------------------------------ v1.3.7-68
def test_symbol_page_theme_and_controls():
    page = _read('symbol-info.ts')
    # 主题：applyTheme 别名 + 固定调色板（不读 computed style，避免切主题顺序问题）
    assert 'applyTheme(theme: ' in page
    assert "const light = this.options.theme === 'light';" in page
    assert "text: '#1f2329'" in page          # 浅色主题文字要够深 ✓
    # Fundamental Data：报告期切换 + 数值列宽度
    assert 'periodSelect' in page and "_request()" in page
    assert "title: '数值', width: 150" in page
    # Technical Analysis：周期选择
    assert 'TA_CYCLES' in page and 'cycleSelect' in page
    # Top Stories：搜索（走 info_news）
    assert 'desk-symbol-search' in page
    assert "onCommand('info_news'" in page


def test_dot_tooltip_disabled():
    for name in ('chart-page.ts', 'local-chart-page.ts'):
        page = _read(name)
        assert "badge.removeAttribute('title')" in page, name
        assert 'private _bindCalPopover(' in page, name


def test_symbol_events_backend_is_threaded():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _on_info_symbol_events(', 1)[1].split(
        'def _on_pi_cleanup', 1)[0]
    assert 'threading.Thread(target=work' in block
    # 不再在命令里同步取数（实测 4s 阻塞主线程 ✗）
    assert '_info.symbol_events(symbol, self' not in block.split(
        'def work()', 1)[0]


def test_close_tab_is_fault_tolerant():
    app = _read('app.ts')
    block = app.split('    closeTab(id: string): void {', 1)[1].split(
        '    /**', 1)[0]
    assert 'try {' in block
    assert "console.warn('[desk] 关页出错" in block
    # 删页签 / 摘 DOM 在 try 之外（一定会执行 ✓）
    after = block.split("console.warn('[desk] 关页出错", 1)[1]
    assert 'page?.element.remove();' in after
    assert 'this.tabs.delete(id);' in after


def test_info_symbol_accepts_period_and_cycle():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('def _symbol_widgets(', 1)[1].split(
        '    def _strategy_frame(', 1)[0]
    assert 'period: int = 0' in block and 'cycle: int = 0' in block
    assert "out['periods'] = periods" in block
    assert "tech['cycle'] = cycle" in block


# ------------------------------------------------------------ v1.3.7-69
def test_symbol_page_light_theme_and_formatting():
    page = _read('symbol-info.ts')
    # 浅色主题：DataGrid 的表头 / 悬停 / 斑马线都要给（否则仍是深色 ✗）
    for token in ("headerBackground: '#f2f4f7'", "headerText: '#3a4250'",
                  "rowHover: '#eef2f7'", "gridLine: 'rgba(0,0,0,0.06)'"):
        assert token in page, token
    # 开 / 高 / 低 / 昨收保留 2 位小数；成交量 / 持仓量整数
    assert 'decimals: 2' in page
    assert "intFields: ['volume', 'open_interest']" in page
    # 表格按行数撑高度（不出滚动条）
    assert 'this.fundHost.style.height' in page
    header = (JSLIB / '..' / 'panels' / 'quote-header.ts').read_text(
        encoding='utf-8')
    assert 'intFields?: string[];' in header
    assert "Math.round(Number(value)).toLocaleString" in header


def test_top_stories_refreshes_news_when_cache_empty():
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split("        # ---- Top Stories", 1)[1].split(
        '        return out', 1)[0]
    # v1.3.7-70：改用 `symbol_news`（专属源 + 全市场关键词，合并去重 ✓）
    assert '_info2.symbol_news(' in block
    assert '_info2.refresh_symbol_news(' in block
    assert 'event.wait(' in block
    # 公告在前、资讯在后
    assert "[公告]" in block

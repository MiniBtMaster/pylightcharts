"""pylightcharts 看盘窗口（``windows/pylightcharts_window.py``）的守卫测试。

只做源码级/纯逻辑断言（不建 GUI）：把这几轮踩出来的规矩钉住，避免以后改回去：

* **三条铁律**：用 ``ci.get_chart_class()`` 建图、``get_webview()`` 嵌布局、
  数据 ``time`` 走 ``to_chart_time``（datetime64）、送数据要有排队/延后；
* **布局**：``arrange`` 要给已存在的 anchor 也回调 ``on_create``
  （pylightcharts 只对新图调 —— 不补首张就没数据，实测 ``bars: 0``）；
* **主题跟随 miniqt**（不自己做开关）、**实时增量**走 ``update_from_tick``；
* 工具栏：周期组 7 个 + "自"、布局按钮、截图。

    pytest tests/test_pylightcharts_window.py
"""
from __future__ import annotations

import pathlib

WINDOW = (pathlib.Path(__file__).resolve().parents[1] / 'miniqt' / 'app'
          / 'windows' / 'pylightcharts_window.py')


def _source() -> str:
    return WINDOW.read_text(encoding='utf-8')


def test_window_lives_next_to_the_other_chart_files():
    assert WINDOW.exists()
    folder = WINDOW.parent
    assert (folder / 'chart_interface.py').exists()      # 旧的（未动）
    assert (folder / 'pylightcharts_page.py').exists()   # P0 的冒烟页


def test_three_rules_are_kept():
    source = _source()
    assert 'get_chart_class()' in source            # 用 miniqt 补丁版 QtChart
    assert 'get_webview()' in source                # 视图就是它
    assert '_pending' in source                     # 未就绪先排队
    assert 'QTimer.singleShot' in source            # 建图后延后发数据


def test_arrange_also_feeds_the_anchor():
    """`on_create` 必须连 anchor 一起回调（否则首张图没数据）。"""
    source = _source()
    body = source.split('def arrange(', 1)[1]
    body = body.split(chr(10) + '    @property', 1)[0]
    assert 'on_create' in body
    assert 'on_create(self.chart)' in body          # anchor


def test_toolbar_layout_menu_and_close_layout():
    """工具栏：「布局」（2/3 个窗口的子菜单）+「关闭布局」（关最后点击过的图 ✓）。"""
    source = _source()
    assert "Action(FluentIcon.LAYOUT, '布局'" in source
    assert 'LAYOUT_MENUS' in source
    assert "'2 个窗口布局'" in source and "'3 个窗口布局'" in source
    assert "'上1下左1下右1'" in source and "'上左1上右1下1'" in source
    assert 'DEFAULT_FOR_COUNT' in source          # 删除后回落（2 -> 左右 ✓）
    assert 'def close_layout' in source
    assert 'last_panel' in source                 # 跟踪最后点击过的图
    assert 'events.click' in source               # 用 click 事件跟踪 ✓
    assert 'arrange_tiles' in source              # 2D 布局


def test_toolbar_has_periods_layout_and_screenshot():
    source = _source()
    assert 'PERIODS' in source
    for label in ('30秒', '1分', '5分', '15分', '30分', '1时', '1日', '自'):
        assert f"'{label}'" in source, label
    assert 'cycleChanged' in source                 # 周期变化的信号
    assert 'close_layout' in source                 # 关闭布局 ✓
    assert 'takeScreenshot' in source               # 截图走页面 canvas


def test_theme_follows_miniqt_only():
    """主题由 miniqt 决定：跟随 qconfig.themeChanged，不提供独立开关。"""
    source = _source()
    assert 'qconfig.themeChanged' in source
    assert 'isDarkTheme' in source
    assert 'def apply_theme' in source
    # 不该有"主题"按钮（水印/价格线同理：留给右键菜单/指标属性）
    assert "TransparentPushButton(\n            '主题'" not in source
    assert "'水印'" not in source


def test_realtime_uses_update_from_tick():
    source = _source()
    assert "self._call('update_from_tick'" in source
    assert 'def push_tick' in source
    assert 'cumulative_volume' in source


def test_watermark_stays_out_until_the_context_menu():
    """水印按约定不做在工具栏（留给右键菜单）；价格线已归到指标参数窗口 ✓。"""
    source = _source()
    assert "self._button('水印'" not in source
    # 价格线/价格标签是指标参数（不是工具栏按钮），见 add_indicator ✓
    assert "self._button('价格线'" not in source
    assert 'price_line=price_line' in source


def test_multi_contract_provider_and_panel_realtime():
    """多合约取数：`set_contracts` + `_contract_frame` + `start_panel_realtime`。"""
    source = _source()
    for name in ('def set_contracts', 'def _contract_frame',
                 'def feed_contract_panel', 'def start_panel_realtime',
                 'def stop_panel_realtime', 'def _panel_realtime_step'):
        assert name in source, name
    assert 'self.contracts' in source
    assert 'self.data_provider' in source
    # contracts[index % len] 循环取合约 ✓
    assert 'index % len(self.contracts)' in source


def test_new_watch_window_replaces_the_old_one():
    """新看盘窗口（替代旧 MarketWatchWindow）就在旁边，且主窗口已接上。"""
    watch = WINDOW.parent / 'pylightcharts_market_watch.py'
    assert watch.exists()
    src = watch.read_text(encoding='utf-8')
    for name in ('class PylightchartsMarketWatchWindow', 'def _frame',
                 'def _feed_panel', 'def _bootstrap',
                 'set_contracts', 'start_panel_realtime',
                 'set_last_clicked_widget'):
        assert name in src, name
    # 旧接口对齐（main_window.start_minibt_chart 直接替换）
    for attr in ('self.symbol', 'self.cycle', 'self.length',
                 'self.is_stock', 'self.main_window'):
        assert attr in src, attr

    main = WINDOW.parents[1] / 'view' / 'main_window.py'
    main_src = main.read_text(encoding='utf-8')
    assert 'pylightcharts_market_watch' in main_src      # 新窗口
    assert 'chart_engine' in main_src and 'LEGACY' in main_src  # 可回退
    assert 'market_watch_window import MarketWatchWindow' in main_src


def test_toolbar_has_drawing_and_panel_buttons():
    """画线 / 清除画线 / 添加板块（对齐旧看盘工具栏 ✓）。"""
    source = _source()
    for label in ('画线', '清除画线', '添加板块'):
        assert f"'{label}'" in source, label
    for name in ('def toggle_toolbox', 'def clear_drawings', 'def add_panel',
                 'def remove_panel'):
        assert name in source, name
    assert 'from pylightcharts.toolbox import ToolBox' in source


def test_watch_window_keyelf_and_symbol_switch():
    """新看盘窗口要支持键盘精灵（空格）与切合约 ✓。"""
    watch = WINDOW.parent / 'pylightcharts_market_watch.py'
    src = watch.read_text(encoding='utf-8')
    for name in ('active_chart_widget', 'show_key_elf', 'switch_chart_symbol',
                 '_init_symbol_search_data', '_restore_key_elf',
                 'keyPressEvent', '_KeyElfGlobalFilter', 'symbol_search_data'):
        assert name in src, name
    assert 'KeyElfWindow' in src
    assert 'add_market_watch_window' in src


def test_indicator_and_drawing_persistence_hooks():
    """指标/画线持久化：`save_indicators`/`load_indicators` + 工具箱保存回调 ✓。"""
    source = _source()
    for name in ('def save_indicators', 'def load_indicators',
                 'def _indicator_key', 'def _panel_symbol',
                 'def _init_drawings_persistence', 'def _drawing_tag'):
        assert name in source, name
    assert 'chart_data_manager' in source
    assert 'set_indicators' in source and 'get_indicators' in source
    assert 'save_drawings' in source and 'set_drawings' in source
    assert 'loadDrawings' in source


def test_add_panel_contract_picker_hook():
    """空调用「添加板块」时交给 `contract_picker`（看盘窗口弹合约菜单 ✓）。"""
    source = _source()
    assert 'contract_picker' in source
    assert 'addPanelAction' in source
    watch = WINDOW.parent / 'pylightcharts_market_watch.py'
    watch_src = watch.read_text(encoding='utf-8')
    assert 'contract_picker' in watch_src
    assert '_show_add_contract_menu' in watch_src


def test_price_alert_hooks_and_dialog():
    """价格预警：设置/清除/触发锁定 + 移植的对话框 ✓。"""
    source = _source()
    for name in ('def load_price_alert', 'def show_price_alert_menu',
                 'def show_price_alert_dialog', 'def apply_price_alert',
                 'def reset_price_alert', 'def check_price_alert'):
        assert name in source, name
    assert '_alert_fired' in source          # 触发锁定
    assert 'set_price_alerts' in source and 'get_price_alerts' in source

    dialog = WINDOW.parent / 'price_alert_dialog.py'
    assert dialog.exists()
    src = dialog.read_text(encoding='utf-8')
    for name in ('class PriceAlertDialog', 'alertSettingsChanged',
                 'def settings', 'def _validate_input'):
        assert name in src, name
    assert "'both'" in src and "'up'" in src and "'down'" in src


def test_context_menu_and_price_alert_button():
    source = _source()
    for name in ('def show_context_menu', 'def show_price_alert_menu',
                 'def _menu_action'):
        assert name in source, name
    assert 'CustomContextMenu' in source        # webview 右键
    assert "Action(FluentIcon.MESSAGE, '预警'" in source
    assert "'指标'" in source and "'移除指标'" in source


def test_period_switch_reloads_panels():
    """周期切换后要重新拉各格数据（`reload_panels` ✓）。"""
    source = _source()
    assert 'def reload_panels' in source
    assert '_on_period' in source
    assert 'self.reload_panels(seconds)' in source
    watch = WINDOW.parent / 'pylightcharts_market_watch.py'
    assert 'reload_panels' in watch.read_text(encoding='utf-8')


def test_watch_window_cycle_normalization_and_insert_position():
    """股票周期归一化 + 插入位置（S5 ✓）。"""
    import sys
    sys.path.insert(0, str(WINDOW.parents[2]))       # 仓库根
    from miniqt.app.windows.pylightcharts_market_watch import (
        normalize_cycle, STOCK_PERIODS)
    assert normalize_cycle(False, 3) == 3            # 期货任意秒
    assert normalize_cycle(False, 123) == 123
    assert normalize_cycle(True, 60) == 60
    assert normalize_cycle(True, 120) == 60          # 最近受支持周期
    assert normalize_cycle(True, 400) == 300
    assert normalize_cycle(True, 1000) == 900
    assert normalize_cycle(True, 99999999) == max(STOCK_PERIODS)

    source = _source()
    assert 'insert_position' in source
    assert "'插入位置'" in source        # 右键菜单
    watch = (WINDOW.parent / 'pylightcharts_market_watch.py').read_text(
        encoding='utf-8')
    assert 'def _insert_index' in watch and 'def set_insert_position' in watch


def test_drawings_reload_on_cycle_and_symbol_change():
    """切周期/换合约后画线要按新键重载（`_reload_drawings` ✓）。"""
    source = _source()
    assert 'def _reload_drawings' in source
    assert 'self._reload_drawings(_chart)' in source    # reload_panels 里逐格
    assert 'self._drawing_tag(chart)' in source         # 保存时按格动态取键
    watch = (WINDOW.parent / 'pylightcharts_market_watch.py').read_text(
        encoding='utf-8')
    assert '_reload_drawings' in watch                  # switch_chart_symbol 里


def test_toolbar_is_commandbar_with_overflow():
    """工具栏用 `CommandBar`（窗口变窄时放不下的按钮收进“…”）✓，不再是 QHBoxLayout ✗。"""
    source = _source()
    assert 'CommandBar' in source
    assert 'self.toolbar.addAction(' in source
    assert 'self.toolbar.addSeparator()' in source
    assert 'toolbarLayout' not in source


def test_indicator_worker_guards_deleted_object():
    """后台 worker 被 deleteLater 后，`refresh_indicators` 不能再碰它 ✗。"""
    source = _source()
    assert 'def _on_indicator_worker_finished' in source
    assert 'except RuntimeError' in source
    assert 'worker.deleteLater()' in source
    assert 'self._indicator_worker = None' in source


def test_no_toolbar_button_uses_a_checked_background():
    """周期按钮和画线按钮都不勾选高亮（用户要求）✓。"""
    source = _source()
    assert 'setCheckable' not in source
    assert 'setChecked' not in source
    assert 'def toggle_toolbox' in source
    # 画线针对“最后点击那格”，显隐状态按格记录 ✓
    assert 'def _active_chart' in source
    assert 'chart._toolbox_visible' in source


def test_reload_panels_uses_single_argument_feed():
    """`reload_panels` 必须只给 feed 一个参数（否则 set 不发 → 旧数据 + update 报错 ✗）。"""
    source = _source()
    body = source.split('def reload_panels', 1)[1].split('\n    def ', 1)[0]
    assert 'feed(chart)' in body
    assert 'feed(chart, index)' not in body


def test_screenshot_shows_a_notification():
    source = _source()
    assert "InfoBar.success('截图已保存'" in source
    assert "InfoBar.warning('截图失败'" in source
    assert 'def _save_shot(self' in source          # 变成实例方法（要有 parent 弹 InfoBar）
    assert '@staticmethod' not in source.split('def _save_shot', 1)[0][-40:]


def test_reload_guards_realtime_updates():
    """切周期重载期间不跑实时 update（避免 set 未到就先 update 旧序列 ✗）。"""
    source = _source()
    assert 'self._reloading = False' in source
    assert "getattr(self, '_reloading', False)" in source
    assert 'def _panel_realtime_step' in source


def test_period_label_and_two_line_legend():
    """图例第一行 = 合约名+周期；第二行 = 四价+成交量+百分比（一行）✓。"""
    import sys
    sys.path.insert(0, str(WINDOW.parents[2]))
    from miniqt.app.windows.pylightcharts_window import (
        PylightchartsChartWindow as W)
    assert W.period_label(60) == '1分'
    assert W.period_label(300) == '5分'
    assert W.period_label(86400) == '1日'
    assert W.period_label(180) == '3分'          # 不在预设里也拼得出
    assert W.period_label(90) == '90秒'

    source = _source()
    assert 'def _panel_legend_title' in source
    assert "f'{symbol}  {period}'" in source     # 第一行：合约名 + 周期
    assert 'def _style_panel' in source          # 每一格都上图例
    assert 'def _apply_custom_legend' in source
    assert 'addCrosshairListener' in source
    assert "text += ' | V '" in source           # 成交量与四价同一行
    assert 'pct.toFixed(2)' in source            # 百分比


def test_panels_all_get_the_legend():
    """多布局时每一格都要上图例（`apply_theme` 不再只给 anchor ✗）。"""
    source = _source()
    body = source.split('def apply_theme', 1)[1].split(
        'def _watch_theme', 1)[0]
    assert 'for chart in panels' in body
    assert 'self._style_panel(chart, colors)' in body
    feed = source.split('def feed_contract_panel', 1)[1].split(
        '\n    def ', 1)[0]
    assert 'self._style_panel(chart)' in feed


def test_custom_legend_js_is_generated_and_idempotent():
    """`_apply_custom_legend` 生成的 JS 要包住 legendHandler 并只包一次 ✓。"""
    import sys
    sys.path.insert(0, str(WINDOW.parents[2]))
    from miniqt.app.windows.pylightcharts_window import (
        PylightchartsChartWindow as W)

    window = W.__new__(W)

    class Fake:
        id = 'window.fake'

        def __init__(self):
            self.scripts = []
            self._miniqt_legend_styled = False

        def run_script(self, script):
            self.scripts.append(script)

    fake = Fake()
    window._apply_custom_legend(fake)
    js = fake.scripts[0]
    assert 'legendHandler' in js and 'addCrosshairListener' in js
    assert 'removeCrosshairListener' in js
    assert "| V " in js and 'pct.toFixed(2)' in js
    window._apply_custom_legend(fake)          # 幂等：不再包一层
    assert len(fake.scripts) == 1


def test_panel_symbol_and_indicator_key_are_panel_aware():
    """多面板：合约名按 `index % len(contracts)`；子格指标键带 `|p<index>` ✓。"""
    import sys
    sys.path.insert(0, str(WINDOW.parents[2]))
    from miniqt.app.windows.pylightcharts_window import (
        PylightchartsChartWindow as W)

    class Fake:
        pass

    window = W.__new__(W)
    window.cycle = 60
    anchor, second = Fake(), Fake()
    window.chart = anchor
    window.contracts = ['SHFE.ni2611']
    window.panels = lambda: [anchor, second]
    # 单合约时每一格都显示这个合约（否则子格图例第一行缺合约名 ✗）
    assert window._panel_symbol(anchor) == 'SHFE.ni2611'
    assert window._panel_symbol(second) == 'SHFE.ni2611'

    window.contracts = ['A', 'B', 'C']
    assert window._panel_symbol(anchor) == 'A'
    assert window._panel_symbol(second) == 'B'
    # anchor 用 合约|周期；子格再加 |p<index>，避免共用键导致重复恢复 ✗
    assert window._indicator_key(anchor) == 'A|60'
    assert window._indicator_key(second) == 'B|60|p1'


def test_load_indicators_skips_a_chart_that_already_has_them():
    source = _source()
    body = source.split('def load_indicators', 1)[1].split('\n    def ', 1)[0]
    assert "any(entry.get('chart') is chart" in body

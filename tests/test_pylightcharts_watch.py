"""新看盘窗口（`pylightcharts_market_watch`）的数据层集成测试（mock 天勤）。

国庆期间没有实时行情，用假 `tq_api` 把「取数 → 合约/周期 → 面板」这条链路钉住：
不建 webview（不 `start()`），所以这些断言在 CI/离线也稳定 ✓。

    pytest tests/test_pylightcharts_watch.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[1]


def _run(script: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, '-c', textwrap.dedent(script)], cwd=str(REPO),
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=300)
    if result.returncode != 0:
        import pytest
        pytest.fail(f'子进程失败（{result.returncode}）:\n'
                    f'{result.stdout}\n{result.stderr}')
    return result


def test_data_layer_with_mock_tq_api():
    """`_frame` 走 `tq_api.get_kline_serial`，时间列是 datetime64 ✓。"""
    result = _run("""
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        import sys
        sys.path.insert(0, '.')
        from pylightcharts.compat import install_alias
        install_alias()
        os.chdir('miniqt')
        import miniqt.app.common.config      # noqa: F401
        os.chdir('..')
        import numpy as np
        import pandas as pd
        from PyQt6.QtWidgets import QApplication, QWidget
        app = QApplication([])

        class MockTqApi:
            def __init__(self):
                self.calls = []
            def get_kline_serial(self, symbol, cycle, length):
                self.calls.append((symbol, cycle, length))
                n = min(int(length or 100), 200)
                return pd.DataFrame({
                    'datetime': pd.date_range('2024-01-01', periods=n,
                                              freq='min'),
                    'open': 1.0, 'high': 2.0, 'low': 0.5, 'close': 1.5,
                    'volume': 10})

        main = QWidget()
        main.tq_api = MockTqApi()
        main.login_status = {'futures': True}

        from miniqt.app.windows.pylightcharts_market_watch import (
            PylightchartsMarketWatchWindow, normalize_cycle)
        window = PylightchartsMarketWatchWindow(
            main, symbol='SHFE.rb2610', cycle=60, length=150)
        frame = window._frame('SHFE.rb2610', 60, 150)
        print('CALLS', main.tq_api.calls)
        print('COLS', list(frame.columns))
        print('DTYPE', str(frame['time'].dtype))
        print('ROWS', len(frame))
        print('CONTRACTS', window.contracts)

        # 股票周期归一化 / 类型识别（键盘精灵切合约用 ✓）
        window.switch_chart_symbol('000001', 'STOCK')
        print('STOCK', window.is_stock, window.cycle)
        window.switch_chart_symbol('SHFE.rb2610', 'FUTURES')
        print('FUTURES', window.is_stock, window.cycle)
        print('NORM', normalize_cycle(True, 400), normalize_cycle(False, 400))
    """)
    out = result.stdout
    assert "('SHFE.rb2610', 60, 150)" in out, out        # 透传到 tq_api
    assert "datetime64" in out, out                      # time 必须 datetime64
    assert 'ROWS 150' in out, out
    assert 'DTYPE datetime64' in out, out
    assert "CONTRACTS ['SHFE.rb2610']" in out, out
    assert 'STOCK True 60' in out, out                   # 股票 120 -> 60
    assert 'FUTURES False 60' in out, out
    assert 'NORM 300 400' in out, out


def test_watch_window_api_surface():
    """对外接口与旧 `MarketWatchWindow` 对齐（`start_minibt_chart` 直接替换 ✓）。"""
    watch = (REPO / 'miniqt' / 'app' / 'windows'
             / 'pylightcharts_market_watch.py').read_text(encoding='utf-8')
    for name in ('symbol', 'cycle', 'length', 'is_stock', 'main_window',
                 'set_last_clicked_widget', 'get_last_clicked_widget',
                 'active_chart_widget', 'switch_chart_symbol',
                 'show_key_elf', 'add_market_watch_window',
                 'on_period_button_clicked', 'closeEvent'):
        assert name in watch, name

    main = (REPO / 'miniqt' / 'app' / 'view' / 'main_window.py').read_text(
        encoding='utf-8')
    assert 'pylightcharts_market_watch' in main
    assert 'MINIQT_CHART_ENGINE' in main or 'engine_name' in main

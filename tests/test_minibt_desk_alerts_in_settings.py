"""v1.3.7-91：告警通道搬到「设置 → 系统设置 → 告警通道」。"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
SETTINGS = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
SUITE = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
APP = (JSLIB / 'app.ts').read_text(encoding='utf-8')
CSS = (JSLIB / 'desk.css').read_text(encoding='utf-8')


def test_nav_has_alerts_after_info_sources():
    line = "{ key: 'alerts', label: '告警通道' },"
    assert line in SETTINGS
    before = SETTINGS.index("{ key: 'info-sources', label: '资讯数据源' },")
    after = SETTINGS.index(line)
    assert after > before
    # 中间只隔一个换行（同一组、紧挨着 ✓）
    assert SETTINGS[before:after].count('\n') == 1


def test_settings_renders_alert_channels():
    for token in ('_renderAlerts', 'ops_notify_config', 'ops_notify_test',
                  '微信公众号', '企业微信', '自定义 Webhook',
                  'xtuis', 'wx.xtuis.cn'):
        assert token in SETTINGS, token
    assert 'setNotify(' in SETTINGS
    assert 'bell:' in SETTINGS          # 导航图标


def test_ops_page_dropped_the_alert_card():
    start = SUITE.index('export class OpsPage {')
    ops = SUITE[start:]
    # 只剩下「已搬到设置页」的注释，没有表单 / 渲染函数 ✓
    assert '<h3>告警通道' not in ops
    for token in ('data-op-notify-save', 'data-op-notify-test',
                  'xtuisToken', 'xtuisEnabled', 'renderNotify',
                  'renderNotify('):
        assert token not in ops, token
    # 说明里指向设置页
    assert '告警通道在「设置 → 系统设置 → 告警通道」' in ops


def test_app_routes_notify_to_settings():
    assert 'this.settingsPage?.setNotify(' in APP
    assert "case 'ops_notify':" in APP
    assert 'onToast: (level, text) => this.toast(level, text),' in APP


def test_settings_options_allow_toast():
    assert 'onToast?: (level: string, text: string) => void;' in SETTINGS

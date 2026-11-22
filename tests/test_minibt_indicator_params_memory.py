"""指标**参数持久化**（v1.3.9-49，用户 2026-11-19）。

需求：
1. 指标设置卡片点「应用」→ 参数落盘；
2. 以后**加载指标**默认就用上次保存的参数；
3. 卡片打开的也是持久化后的参数（没保存过才用目录默认）。

实现：`settings.indicator_params = {指标key: {参数: 值}}`（白名单新键），
加指标时 `saved` 当默认 + 记住这次传的；`_attach_indicator_params` 也补 saved
（图例 ⚙ 卡片据此显示上次的值）。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
PREFS = (ROOT / 'minibt' / 'desk' / 'user_prefs.py').read_text(encoding='utf-8')
CHART = (ROOT / 'jslib' / 'src' / 'desk' / 'chart-page.ts').read_text(
    encoding='utf-8')
LOCAL = (ROOT / 'jslib' / 'src' / 'desk' / 'local-chart-page.ts').read_text(
    encoding='utf-8')


def test_setting_key_whitelisted():
    assert "'indicator_params'," in PREFS


def test_backend_helpers_exist():
    assert 'def saved_indicator_params(' in APP
    assert 'def remember_indicator_params(' in APP
    assert 'def _with_saved_params(' in APP
    # 三处 `_attach_indicator_params` 都补 saved（卡片才能显示上次的值）✓
    assert APP.count('_attach_indicator_params(payload, '
                     'self._with_saved_params(') == 3


def test_add_indicator_merges_and_remembers():
    body = APP.split('def _on_add_indicator(', 1)[1]
    body = body.split('errors: dict[str, str] = {}', 1)[0]
    assert 'self.saved_indicator_params(key)' in body
    assert 'self.remember_indicator_params(key, passed)' in body
    # 本地图表同样
    local = APP.split('def _on_local_add_indicator(', 1)[1]
    local = local.split('self._local_set_items(', 1)[0]
    assert 'self.saved_indicator_params(key)' in local
    assert 'self.remember_indicator_params(key, passed)' in local


def test_frontend_remembers_and_restores():
    for source in (CHART, LOCAL):
        assert 'private savedParams:' in source
        assert 'settings?.indicator_params' in source
        assert 'this._rememberParams(baseKey, state.params);' in source
        assert "key: 'indicator_params'," in source
        # 卡片打开：上次保存的参数优先 ✓
        assert "params: { ...(item.params || {}), ...remembered }," in source


def test_params_keep_zero_values(tmp_path):
    """0 也是合法参数（`up_thresh=0` 不能被当成"没设置" ✗）"""
    sys.path.insert(0, str(ROOT))
    from minibt.desk import user_prefs

    prefs_file = tmp_path / 'p.json'
    original = user_prefs.PREFS_FILE
    try:
        user_prefs.PREFS_FILE = str(prefs_file)
        user_prefs.set_setting('indicator_params',
                               {'btind_zigzag_support_resistance':
                                {'up_thresh': 0.0, 'down_thresh': 0.0}})
        saved = (user_prefs.settings() or {}).get('indicator_params') or {}
        entry = saved.get('btind_zigzag_support_resistance') or {}
        assert entry.get('up_thresh') == 0.0
        assert entry.get('down_thresh') == 0.0
    finally:
        user_prefs.PREFS_FILE = original

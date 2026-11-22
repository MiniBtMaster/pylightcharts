"""切换实盘账户（TqAccount）要真的生效（v1.3.9-29）。

用户实测 2026-11-18：交易账户页 / 首页账户概览切到「TqAccount」都失败 ——
日志出现 `「SHFE.ad2612」交易账户 → TqAccount`，但面板一直显示快期模拟的数据；
再点一次只回「当前已是 TqAccount」。

根因（key 记账口径不一致）：

* `set_account_kind()` 单布局只写 `chart:X`（不带 `#cell`）
* 每秒的 `_account_patch()` 读的是 `chart:X#0`
→ 读到旧 key（或首页 key）→ 前端下拉框每秒被顶回「快期模拟」，
看起来就是切不过去 ✗

现在写主 key 之后**把另一处也补上**（`setdefault`，不覆盖别格已单独设过的账户）。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
DOCK = (ROOT / 'jslib' / 'src' / 'desk' / 'account-dock.ts').read_text(
    encoding='utf-8')
HOME = (ROOT / 'jslib' / 'src' / 'desk' / 'home-page.ts').read_text(
    encoding='utf-8')


def test_key_written_to_both_shapes():
    body = APP.split('def set_account_kind(self', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    # 现在所有写入都走唯一入口 `_set_account_key()`（带 reason 日志 ✓）
    assert "self._set_account_key(store, key, '用户切换')" in body
    # 另一种口径也要补上（否则读取端永远拿到旧 key ✗）
    assert 'mirror = (page if has_cell' in body
    assert "self._set_account_key(mirror, key, '镜像同页')" in body


def test_switch_reports_effective_account():
    """切完回一句「账户已生效：…｜权益 …」（看出是 key 还是数据源的问题 ✓）"""
    body = APP.split('def set_account_kind(self', 1)[1]
    body = body.split('def _focus_symbols', 1)[0]
    assert "text = f'账户已生效：{label}'" in body
    assert '权益' in body


def test_frontend_pins_user_choice():
    """前端在补丁回来前**钉住**用户的选择（不被每秒刷新顶回 ✓）"""
    assert 'private pendingKey = ' in DOCK
    assert 'this.pendingKey = key;' in DOCK
    assert 'Date.now() - this.pendingAt > 5000' in DOCK
    # 首页账户卡同样处理
    assert 'private _activeKey(): string {' in HOME
    assert "this.pendingKey = String(choice.key || '');" in HOME
    assert "this.options.onCommand('home_account_kind'," in HOME

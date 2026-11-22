"""指标 / 策略页：工具栏「源码」按钮 + 编辑器**临时文件**（不落盘）✓

用户需求（2026-11-22）：

1. 「指标和策略」页工具栏，**收藏按钮左侧**加一个「源码」图标按钮：
   效果 = 顶栏页签右键「查看原始码（只读）」；要有 tooltip；
   **本地图表 / 实时图表不显示**这个按钮；
2. 打开指标 / 策略时**不再**在个人目录里生成 .py（否则文件越攒越多）→
   只生成**临时文件**；点「保存 / 另存」才真的写盘：
   * 临时文件时按钮显示「另存」，点击弹路径；
   * 另存后变成普通文件 → 按钮回到「保存」，之后是覆盖保存 ✓
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


# ------------------------------------------------------------- 源码按钮
def test_source_button_left_of_star_only_on_tv_pages():
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    assert 'desk-tool-source' in page
    toolbar = page[page.index('toolbar.append(symbol,'):]
    toolbar = toolbar[:toolbar.index(');')]
    assert 'sourceButton' in toolbar and 'starButton' in toolbar
    # 源码在收藏**左边** ✓
    assert toolbar.index('sourceButton') < toolbar.index('starButton')
    # 只有 tvKey 页才加进来 ✓
    assert "options.tvKey ? [sourceButton, starButton] : []" in page


def test_source_button_sends_tv_source_and_has_tip():
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    at = page.index('private _openSourceCode()')
    body = page[at:at + 400]
    assert "'tv_source'" in body
    assert 'page: this.options.pageId' in body
    assert '查看原始码（只读）' in page        # tooltip ✓


def test_source_button_icon_exists():
    icons = _read('jslib', 'src', 'desk', 'icons.ts')
    assert 'export const ICON_CODE' in icons


# ------------------------------------------------------------- 临时文件
def test_tv_script_does_not_write_personal_dir():
    """打开指标 / 策略 → 只写**临时**文件，个人目录里不新增 .py ✓"""
    from minibt.desk import tv_page  # noqa: PLC0415

    data = tv_page.script_payload({'key': 'tv:ADX_and_DI'})
    assert data.get('ok'), data
    assert data.get('temp') is True
    assert 'personal' not in data['path'].lower()
    assert data.get('suggested', '').lower().endswith('.py')
    assert 'personal' in data['suggested'].lower()


def test_tv_source_dry_does_not_write():
    """「查看原始码」不产生任何文件 ✓"""
    from minibt.desk import tv_page  # noqa: PLC0415

    data = tv_page.script_payload({'key': 'tv:ADX_and_DI', 'dry': True})
    assert data['ok'] and data['path'] == ''
    assert data['temp'] is False
    assert data['text']


def test_editor_file_patch_carries_temp_flag():
    backend = _read('minibt', 'desk', 'app.py')
    at = backend.index("def _on_tv_script")
    body = backend[at:at + 1600]
    assert "bool(data.get('temp'))" in body
    assert "'suggested'" in body


# ------------------------------------------------------------- 保存 / 另存
def test_editor_save_button_label_and_save_as():
    panel = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    # 临时 → 「另存」；普通 → 「保存」 ✓
    assert "const label = tab.temp ? '另存' : '保存';" in panel
    # 保存：临时文件走另存（弹路径）✓
    at = panel.index('private _save(): void')
    body = panel[at:at + 500]
    assert 'tab.temp' in body and '_saveAs(tab)' in body
    # 另存请求带 `from`（后端据此回传）✓
    at2 = panel.index('private _saveAs(tab: OpenTab)')
    body2 = panel[at2:at2 + 1600]
    # ★ 2026-11-22：改成**微信式另存对话框**（选文件夹 + 改名字）→ 不再 prompt
    assert 'from, saveAs: true' in body2
    assert '_ensureSaveDialog' in body2
    assert 'window.prompt' not in body2
    # 另存成功后换页签 → 之后就是普通覆盖保存 ✓
    assert 'adoptPath(from: string, to: string' in panel


def test_saved_patch_moves_temp_tab_to_real_path():
    app = _read('jslib', 'src', 'desk', 'app.ts')
    at = app.index("patch.type === 'editor_saved'")
    block = app[at:at + 700]
    assert 'adoptPath' in block and 'from' in block
    assert 'adoptPath?:' in app
    backend = _read('minibt', 'desk', 'app.py')
    at2 = backend.index("def _on_editor_save")
    body = backend[at2:at2 + 2200]
    assert "'from': str(payload.get('from') or '')" in body


def test_temp_scripts_dir_is_system_temp():
    from minibt.desk import tv_page  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    assert tv_page.TEMP_SCRIPT_DIR.startswith(tempfile.gettempdir())


def test_wechat_topbar_is_icon_button():
    """顶栏「微信」按钮改成**微信图标**（tooltip / 悬停二维码不变 ✓）"""
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert 'ICON_WECHAT' in app
    assert "wechat.textContent = '微信'" not in app
    assert 'wechat.title' in app            # tooltip 保留 ✓
    icons = _read('jslib', 'src', 'desk', 'icons.ts')
    assert 'export const ICON_WECHAT' in icons
    css = _read('jslib', 'src', 'desk', 'desk.css')
    assert '.desk-wechat-btn svg' in css


def test_save_as_dialog_uses_folder_browser():
    """「另存」= 微信式对话框：可选文件夹 + 改文件名（不再用 prompt ✓）"""
    panel = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    at = panel.index('private _saveAs(tab: OpenTab)')
    body = panel[at:at + 1600]
    assert 'SaveAsDialog' in body or '_ensureSaveDialog' in body
    assert 'window.prompt' not in body
    dialog = _read('jslib', 'src', 'desk', 'save-dialog.ts')
    assert 'export class SaveAsDialog' in dialog
    assert "onCommand('fs_list'" in dialog
    assert '文件名' in dialog and '保存' in dialog
    assert 'applyListing' in dialog
    # 后端：任意目录浏览 ✓
    explorer = _read('minibt', 'desk', 'explorer.py')
    assert 'def browse(' in explorer
    backend = _read('minibt', 'desk', 'app.py')
    assert "'fs_list': self._on_fs_list" in backend


def test_fs_list_routing_and_css():
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert "case 'fs_list':" in app
    assert 'setSaveList' in app
    css = _read('jslib', 'src', 'desk', 'desk.css')
    for token in ('.desk-save-list', '.desk-save-row', '.desk-save-name'):
        assert token in css, token


def test_local_search_defaults_to_csv_tab():
    """★ 本地图表商品搜索：**打开时只显示本地 CSV**（不显示通达信代码 ✓）

    以前：沿用上次的通达信分页 + 后端推的 `local_tdx_list` 无条件覆盖列表
    → 一打开就是 `tdx:bj...` 通达信数据，来回切一次才恢复（用户 2026-11-22 ✗）
    """
    page = _read('jslib', 'src', 'desk', 'local-chart-page.ts')
    at = page.index('openLocalDataSearch(): void')
    body = page[at:at + 5200]
    # 打开时把通达信分页清掉 + 显式选回「本地 CSV」✓
    assert "this.localTdxPeriod = '';" in body
    assert "this.symbolSearch.setMarket('');" in body
    # 通达信结果只在通达信分页时才进列表 ✓
    at2 = page.index('setTdxList(payload')
    block = page[at2:at2 + 700]
    assert 'if (!this._tdxMode() || !this.symbolSearch) return;' in block


def test_editor_file_case_not_swallowed_by_fs_list():
    """★ `editor_file` / `editor_files` 不能被 `fs_list` 吞掉 ✓

    2026-11-22 事故：`case 'editor_files': case 'editor_file': case 'fs_list':`
    连在一起 → 打开文件的补丁全进了"另存为对话框"分支就 `break` → 资源管理器
    点文件没反应、指标/策略页也不再出现临时文件 ✗
    """
    app = _read('jslib', 'src', 'desk', 'app.ts')
    at = app.index("case 'fs_list':")
    block = app[at - 120:at + 60]
    assert "case 'editor_file':\n            case 'fs_list':" not in block
    # 打开文件的分支必须还在（和 editor_saved / editor_check 同一组 ✓）
    group = app[app.index("case 'editor_files':"):][:400]
    assert "case 'editor_file':" in group
    assert "case 'editor_saved':" in group


def test_info_package_exports_home_calendar():
    """★ `minibt.desk.info` 包要导出 `home_calendar`（否则命令 500 ✗）"""
    from minibt.desk import info  # noqa: PLC0415

    assert hasattr(info, 'home_calendar')
    assert 'home_calendar' in info.__all__
    data = info.home_calendar()
    assert data['ok'] and isinstance(data['items'], list)


def test_tv_page_passes_lsp_to_editor():
    """★ 指标 / 策略页也要把 LSP 传给编辑器（否则永远「LSP 未启用」✗）"""
    app = _read('jslib', 'src', 'desk', 'app.ts')
    at = app.index('openTvIndicator(key: string')
    block = app[at:at + 1400]
    assert 'lsp: () => this.lspInfo || undefined,' in block
    # 本地图表 / 实时图表也要有（回归：不能被删）
    assert app.count('lsp: () => this.lspInfo || undefined,') >= 2

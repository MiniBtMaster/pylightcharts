"""PI 页 / 对话页跟随窗口缩放（用户 2026-11-08 第二批反馈）。

现象（截图 `tradingview/PI助手对话页面.png`）：窗口缩小后

1. 编辑器工具栏**右边右对齐的按钮**（预览 / 分屏 / 片段 …）看不到；
2. 对话页**右侧节点导航**看不到；
3. 输入框右边的**发送按钮**看不到；
4. 底部**状态栏**被截掉一截。

根因：flex 链路里有几层是默认的 `min-width: auto` —— 内容不肯收缩，
整页被顶到 1179px（窗口只有 1028px），右侧全部被挤出可视区。
修法：每一层 `min-width: 0` + 工具栏窄窗口换行 + 状态栏文字单独省略 +
LSP 徽标只显示短标签（长说明进 tooltip）。
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts) -> str:
    return REPO.joinpath(*parts).read_text(encoding='utf-8')


def _block(text: str, selector: str) -> str:
    """取某条 CSS 规则的内容（`selector {` … `}`）✓"""
    head = f'{selector} {{'
    assert head in text, f'缺 CSS 规则：{selector}'
    return text.split(head, 1)[1].split('}', 1)[0]


# ------------------------------------------------- ① 每层都允许收缩
def test_editor_chain_can_shrink():
    code = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    editor = _block(code, '.desk-editor')
    assert 'min-width: 0' in editor
    assert 'width: 100%' in editor
    side = _block(code, '.desk-editor-side')
    assert 'min-width: 0' in side and 'overflow: hidden' in side
    main = _block(code, '.desk-editor-main')
    assert 'min-width: 0' in main


def test_pi_page_and_chat_can_shrink():
    css = _read('jslib', 'src', 'desk', 'desk.css')
    for selector in ('.desk-pi-page', '.desk-pi-chat', '.desk-pi-body',
                     '.desk-pi-log', '.desk-pi-composer',
                     '.desk-pi-composer-row', '.desk-pi-chips'):
        assert 'min-width: 0' in _block(css, selector), selector
    # 发送按钮不被 chips 挤掉
    assert 'flex: 0 0 auto' in _block(css, '.desk-pi-send')
    # 右侧节点导航要压在日志之上（不会被长文本盖住）
    assert 'z-index: 2' in _block(css, '.desk-pi-nav')
    # 左右留白：右边给导航让出位置
    assert 'padding: 14px 30px 14px 18px' in _block(css, '.desk-pi-log')


# ------------------------------------------------- ② 工具栏换行
def test_toolbar_wraps_instead_of_clipping():
    code = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    toolbar = _block(code, '.desk-editor-toolbar')
    assert 'flex-wrap: wrap' in toolbar      # 右对齐按钮换行，不再被切掉 ✓
    assert 'min-width: 0' in toolbar
    tabs = _block(code, '.desk-editor-tabs')
    assert 'min-width: 0' in tabs


# ------------------------------------------------- ③ 状态栏不截断
def test_status_bar_text_ellipsizes():
    code = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    status = _block(code, '.desk-editor-status')
    assert 'overflow: hidden' in status
    text = _block(code, '.desk-editor-status-text')
    assert 'text-overflow: ellipsis' in text
    assert 'flex: 0 1 auto' in text
    # 写状态栏时用 span 包起来（裸文本节点不能省略号，会把右侧顶出去 ✗）
    block = code.split('private _writeStatus(text: string): void {', 1)[1]
    block = block.split('private _ensureLspBadge', 1)[0]
    assert 'desk-editor-status-text' in block
    assert 'statusText' in block


def test_lsp_badge_uses_short_label():
    code = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    block = code.split('private _setLspStatus(', 1)[1].split(
        'private _toastTop', 1)[0]
    # 长句（`LSP 已连接（jedi：补全 / 悬停 / 跳转 / 语法检查）` 236px）压成短标签
    assert 'badge.textContent = short;' in block
    assert 'badge.title' in block            # 完整说明留在 tooltip ✓
    css = _read('jslib', 'src', 'desk', 'desk.css')
    lsp = _block(css, '.desk-editor-lsp')
    assert 'max-width: 220px' in lsp
    assert 'text-overflow: ellipsis' in lsp


# ------------------------------------------------- ④ 初始化页与宿互斥
def test_welcome_and_host_never_coexist():
    code = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    block = code.split('private _syncWelcome(): void {', 1)[1].split(
        'private _sendFromWelcome', 1)[0]
    # 两个 flex 项并排会把对话区挤成 0 宽 → panes 一起藏 ✓
    assert 'panes.style.display = show' in block
    assert "style.setProperty('display', show ? 'none' : '')" in block
    # 打开会话 / 打开文件后都要重新同步，否则欢迎页盖住对话区
    activate_pi = code.split('private _activatePi(', 1)[1].split(
        'closePiSession', 1)[0]
    assert 'this._syncWelcome();' in activate_pi
    activate = code.split('private _activate(path: string', 1)[1].split(
        'private _closeTab', 1)[0]
    assert 'this._syncWelcome();' in activate

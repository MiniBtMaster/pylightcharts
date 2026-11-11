"""PI 悬浮球交互 + 附件上传（用户 2026-11-08 两条需求）。

1. 悬浮窗使用方式：
   1.1 激活 = **PI 小球**（不是对话窗口）；
   1.2 **双击小球** → 小球隐藏、对话窗口出现；
   1.3 对话窗口的 **✕** → 窗口消失、小球出现；
   1.4 小球可在**界面任意位置**拖动（不再吸附边界）。
2. PI 助手支持**上传附件 / 图片**（📎 / 粘贴 / 拖入；后端转 OpenAI 视觉格式）。
"""
import base64
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
from minibt.desk import agent as A  # noqa: E402


def _read(*parts) -> str:
    return REPO.joinpath(*parts).read_text(encoding='utf-8')


# ------------------------------------------------------------- ① 悬浮球
def test_activation_shows_ball_not_card():
    code = _read('jslib', 'src', 'desk', 'pi-float.ts')
    show = code.split('    show(): void {', 1)[1].split('    hide()', 1)[0]
    assert 'this.showBall();' in show
    assert 'showBall(): void {' in code
    assert 'openCard(): void {' in code
    app = _read('jslib', 'src', 'desk', 'app.ts')
    # 快捷入口：出现小球（不是直接弹对话窗口）
    assert 'if (!this.piFloat.visible) this.piFloat.show();' in app
    assert 'else this.piFloat.showBall();' in app


def test_double_click_ball_opens_card_and_close_returns_ball():
    code = _read('jslib', 'src', 'desk', 'pi-float.ts')
    assert "this.icon.addEventListener('dblclick'" in code
    assert 'this.openCard();' in code
    # ✕ → 回到小球
    assert "this._iconButton('关闭（回到 PI 小球）', '✕',\n" in code
    assert '() => this.showBall());' in code
    # 单击不动作（避免和拖拽冲突）
    assert "this.icon.addEventListener('click'" in code


def test_ball_drags_anywhere_without_edge_snapping():
    code = _read('jslib', 'src', 'desk', 'pi-float.ts')
    # 自由位置（left / top），不再有找"最近的边"
    assert 'private iconPos: { left: number; top: number } | null = null;' \
        in code
    assert 'const distances: Array<[string, number]> = [' not in code
    assert "'left', centerX" not in code
    # 松手就停在任意位置
    end = code.split('private _endIconDrag(', 1)[1].split('expand(', 1)[0]
    assert 'this._placeIcon();' in end          # 停在松手的位置 ✓
    assert 'this.iconPos = {' in end
    # 位置持久化 + 刷新后还原
    assert "window.localStorage.setItem(\n                ICON_KEY" in code \
        or 'ICON_KEY, JSON.stringify(this.iconPos' in code
    assert 'this.iconPos = { left: data.left, top: data.top };' in code
    # 拖完 300ms 内不触发双击
    assert 'this.iconMoved = false; }, 300);' in code


def test_ball_context_menu_opens_and_quits():
    """小球右键菜单：打开 PI 悬浮窗 / 关闭悬浮窗（彻底退出）✓"""
    code = _read('jslib', 'src', 'desk', 'pi-float.ts')
    assert "import { showMenu } from './menu';" in code
    assert "this.icon.addEventListener('contextmenu'" in code
    menu = code.split('private _ballMenu(', 1)[1].split(
        'quit(): void {', 1)[0]
    assert "label: '打开 PI 悬浮窗', run: () => this.openCard()" in menu
    assert "label: '关闭悬浮窗'," in menu
    assert 'run: () => this.quit(),' in menu
    # 右键不触发拖拽（拖拽只认左键）
    start = code.split('private _startIconDrag(', 1)[1].split(
        'const move', 1)[0]
    assert 'if (event.button !== 0) return;' in start
    # quit = 彻底退出：两个 DOM 都隐藏 + 通知宿主
    quit_block = code.split('quit(): void {', 1)[1].split('destroy()', 1)[0]
    assert "this.element.style.display = 'none';" in quit_block
    assert "this.icon.style.display = 'none';" in quit_block
    assert 'this.options.onQuit?.();' in quit_block
    assert 'this.options.onClose?.();' in quit_block
    # destroy：摘掉 DOM（下次重新 new ✓）
    destroy = code.split('destroy(): void {', 1)[1].split(chr(10) + '    }')[0]
    assert 'this.element.remove();' in destroy
    assert 'this.icon.remove();' in destroy
    # 宿主：销毁实例 + 关掉独立小窗
    app = _read('jslib', 'src', 'desk', 'app.ts')
    assert 'onQuit: () => {' in app
    assert 'this.piFloat?.destroy();' in app
    assert 'this.piFloat = null;' in app
    assert "this.send('pi_float_close', {});" in app
    # 后端命令：关掉独立浮窗
    desk = _read('minibt', 'desk', 'app.py')
    assert "'pi_float_close': self._on_pi_float_close," in desk
    assert 'def _on_pi_float_close(' in desk
    assert 'float_window.close_float(self)' in desk


def test_detached_window_opens_card():
    index = _read('jslib', 'src', 'desk', 'index.ts')
    assert 'float.openCard();' in index


# ------------------------------------------------------------- ② 附件
def test_sanitize_attachments_rules():
    png = base64.b64encode(b'\x89PNG' + b'0' * 40).decode()
    items = A.sanitize_attachments([
        {'name': 'a.png', 'mime': 'image/png', 'data': f'data:image/png;base64,{png}'},
        {'name': 'b.py', 'mime': 'text/x-python', 'text': 'print(1)'},
        {'name': 'c.zip', 'mime': 'application/zip', 'text': 'binary'},
    ])
    kinds = [(item['name'], item['kind']) for item in items]
    assert kinds == [('a.png', 'image'), ('b.py', 'text')]   # zip 被跳过 ✓
    assert items[1]['text'] == 'print(1)'
    # 上限：最多 4 个
    many = A.sanitize_attachments([{'name': f'{i}.txt', 'mime': 'text/plain',
                                    'text': 'x'} for i in range(9)])
    assert len(many) == A.MAX_ATTACHMENTS


def test_api_messages_uses_vision_content_parts():
    png = base64.b64encode(b'\x89PNG0').decode()
    items = A.sanitize_attachments([
        {'name': 'a.png', 'mime': 'image/png', 'data': png},
        {'name': 'a.py', 'mime': 'text/x-python', 'text': 'print(1)'},
    ])
    rows = A.api_messages([{'role': 'user', 'content': '看看这个',
                            'attachments': items, 'thinking': 'x'}])
    content = rows[0]['content']
    assert isinstance(content, list)
    text_part = [part for part in content if part['type'] == 'text'][0]
    assert '看看这个' in text_part['text']
    assert '--- a.py ---' in text_part['text']
    image_part = [part for part in content
                  if part['type'] == 'image_url'][0]
    assert image_part['image_url']['url'].startswith('data:image/png;base64,')
    # `attachments` 不能残留在 API payload 里（模型不认 ✓）
    assert 'attachments' not in rows[0]
    # 没附件的老消息还是字符串 content（行为不变 ✓）
    plain = A.api_messages([{'role': 'user', 'content': 'hi'}])
    assert plain[0]['content'] == 'hi'


def test_agent_run_carries_attachments():
    code = _read('minibt', 'desk', 'agent.py')
    assert 'attachments: Optional[List[Dict[str, Any]]] = None,' in code
    assert 'self.attachments = sanitize_attachments(attachments or [])' in code
    run = code.split('    def _run(self) -> None:', 1)[1]
    assert "user_message['attachments'] = self.attachments" in run
    assert "describe_attachments(self.attachments)" in run
    # `user` 事件也给前端（重开 / 悬浮窗都显示缩略图 ✓）
    assert "'attachments': [" in run


def test_pi_send_accepts_attachment_only():
    app = _read('minibt', 'desk', 'app.py')
    send = app.split('    def _on_pi_send(', 1)[1].split(
        '    def flush_pi_queue', 1)[0]
    assert 'attachments = _agent.sanitize_attachments(' in send
    assert 'if not text and not attachments:' in send
    assert "text = '（请看附件）'" in send
    assert 'attachments=attachments,' in send
    # 带附件不能"追加到本轮"（append 只支持纯文本）→ 走排队 ✓
    assert 'if (not attachments and callable(append) and append(text)):' in send


def test_frontend_attachment_ui():
    chat = _read('jslib', 'src', 'desk', 'pi-chat.ts')
    for token in ('export interface PiAttachment',
                  'private attachments: PiAttachment[] = [];',
                  'pickAttachments(): void {',
                  'addFiles(files: File[]): void {',
                  "this.input.addEventListener('paste'",
                  "composer.addEventListener('drop'",
                  'private renderAttachBar(): void {',
                  'attachments: attachments.map((item) => ({'):
        assert token in chat, token
    # 用户气泡里显示缩略图
    assert 'desk-pi-attach-list' in chat
    assert "row.appendChild(box);" in chat
    # 悬浮窗也能传
    flo = _read('jslib', 'src', 'desk', 'pi-float.ts')
    for token in ('addFiles(files: File[]): void {',
                  "attachButton.textContent = '📎';",
                  'attachments,'):
        assert token in flo, token
    css = _read('jslib', 'src', 'desk', 'desk.css')
    for token in ('.desk-pi-attach-bar', '.desk-pi-attach-item',
                  '.desk-pi-float-attach', '.desk-pi-attach-list'):
        assert token in css, token


def test_float_attach_sits_beside_model_button():
    """📎 挪到**底部模型按钮左边**、同高；输入行只留输入框 + 发送（用户 2026-11-08）"""
    code = _read('jslib', 'src', 'desk', 'pi-float.ts')
    # 附件按钮：在 foot 里，且在模型按钮左边
    assert 'this.attachButton = attachButton;' in code
    assert 'foot.append(this.attachButton, this.modelButton, version);' in code
    # 输入行不再塞 📎（也修过「漏 append → 按钮根本不在 DOM」）
    assert 'composerRow.append(this.input, this.sendButton);' in code
    css = _read('jslib', 'src', 'desk', 'desk.css')
    attach = css.split('.desk-pi-float-attach {', 1)[1].split('}', 1)[0]
    assert 'height: 22px' in attach          # 和模型按钮同高 ✓
    assert 'width: 22px' in attach and 'min-width: 22px' in attach
    assert 'border-radius: 999px' in attach
    model = css.split('.desk-pi-float-model {', 1)[1].split('}', 1)[0]
    assert 'height: 22px' in model           # 两个都 22px（对齐）
    # 输入框仍然占满整行
    row = css.split('.desk-pi-float-composer-row {', 1)[1].split('}', 1)[0]
    assert 'flex: 1 1 auto' in row and 'width: 100%' in row
    assert 'min-width: 0' in row
    assert '.desk-pi-float-composer-row .desk-pi-float-input { width: 100%;'         in css


def test_session_payload_keeps_attachments():
    app = _read('minibt', 'desk', 'app.py')
    block = app.split('    def _ai_session_payload(', 1)[1].split(
        '    def _pi_session_payload', 1)[0]
    assert "attachments = message.get('attachments') or []" in block
    assert "row['attachments'] = [" in block


def test_theme_switch_reaches_every_page_including_pi():
    """切主题要覆盖**所有**页面（PI 独立界面的代码页以前被漏掉 ✗）

    用户截图 `tradingview/pi助手中代码页面在切换主题时没有跟随切换.png`：
    整体变浅色了，PI 页的 CodeMirror 还是黑的（本地 / 实时图表编辑器正常）。
    """
    app = _read('jslib', 'src', 'desk', 'app.ts')
    block = app.split('    applyTheme(theme', 1)[1].split(
        'this.root.classList.toggle', 1)[0]
    # 不再用「页面类白名单」（漏一个页面就永远不跟随 ✗）
    assert 'page instanceof ChartPage || page instanceof LocalChartPage' \
        not in block
    assert "applyTheme?: (value: 'light' | 'dark') => void;" in block
    assert "if (typeof apply !== 'function') continue;" in block
    assert 'apply.call(page, theme);' in block
    # PI 页要真的把主题转给编辑器
    pi = _read('jslib', 'src', 'desk', 'pi-page.ts')
    assert 'applyTheme(theme: \'light\' | \'dark\'): void {' in pi
    assert 'this.editorPanel.setTheme(theme);' in pi
    editor = _read('jslib', 'src', 'desk', 'editor-panel.ts')
    set_theme = editor.split('setTheme(theme:', 1)[1].split(
        '\n    }', 1)[0]
    assert 'for (const tab of this.open.values()) tab.editor.setTheme(theme);' \
        in set_theme

/**
 * PiFloat —— **AI 悬浮对话窗**（v1.3.7-40）
 *
 * 要点（用户 2026-11-08 的设计要求）：
 *
 *  ┌ PI 悬浮窗 ──────────────────────────────── ✕ ┐
 *  │  · 紧凑对话（最近几条 + 流式输出）            │
 *  │  ┌────────────────────────────────────────┐ │
 *  │  │ 输入消息…                        → 发送 │ │
 *  │  └────────────────────────────────────────┘ │
 *  │  ◉ deepseek-flash      在页面打开  新话题    │
 *  │  ▬▬▬▬▬▬▬▬▬▬▬▬▬  ← 执行中才显示的不定进度条   │
 *  └────────────────────────────────────────────┘
 *
 *  · **发到会话里**（不是一次性问答）：多轮工具 / 上下文 / 可追溯，
 *    点「在页面打开」就跳到完整会话页；
 *  · 拖到窗口四边（< 28px）→ 自动收起成小圆标，点图标恢复；
 *  · 只有「pi 已安装 + 模型已配置」才激活输入框。
 */
import { esc } from './pi-util';
import { markdownToHtml } from './pi-chat';
import { showMenu } from './menu';

export interface PiFloatOptions {
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
    /** 「在页面打开」→ 打开 PI 独立界面并定位到该会话 */
    onOpenSession?: (id: string) => void;
    /** 点模型 chip → 打开模型对话框 */
    onModels?: () => void;
    /** 关窗 */
    onClose?: () => void;
    /** 悬浮球背景色（`''` = 默认配色；用户可在设置里改 ✓） */
    ballColor?: string;
    /**
     * 右键「关闭悬浮窗」= **彻底退出悬浮功能**（小球 + 对话窗口都没了）✓
     *
     * 宿主（`app.ts`）收到后销毁实例；下次从菜单 / 快捷键再打开会重新建一个。
     */
    onQuit?: () => void;
}

interface FloatAttachment {
    name: string;
    mime?: string;
    kind?: string;
    data?: string;
    size?: number;
}

interface FloatMessage {
    role: string;
    content: string;
    thinking?: string;
    attachments?: FloatAttachment[];
}

const EDGE = 28;          // （旧）距窗口边缘多少 px 触发自动收起
const POS_KEY = 'desk.pi.float.pos';
const COLLAPSE_KEY = 'desk.pi.float.collapsed';
/** 小球位置（**界面任意位置**，不再吸附边界 ✓ 用户 2026-11-08） */
const ICON_KEY = 'desk.pi.float.icon';
const PINNED_KEY = 'desk.pi.float.pinned';

export class PiFloat {
    readonly element: HTMLDivElement;
    readonly icon: HTMLButtonElement;
    private readonly options: PiFloatOptions;
    private readonly log: HTMLDivElement;
    private readonly input: HTMLTextAreaElement;
    private readonly sendButton: HTMLButtonElement;
    private readonly modelButton: HTMLButtonElement;
    /** 📎 附件：★ 用户 2026-11-08 要求放在**底部模型按钮左边**（和模型同高）✓ */
    private readonly attachButton: HTMLButtonElement;
    private readonly progress: HTMLDivElement;
    private readonly progressFill: HTMLElement;
    private readonly progressText: HTMLSpanElement;
    private readonly hint: HTMLDivElement;
    private sessionId = '';
    private messages: FloatMessage[] = [];
    private live: FloatMessage | null = null;
    private streaming = false;
    private installed: boolean | null = null;
    private model = '';
    private pendingSend = '';
    private collapsed = false;
    private drag: { x: number; y: number; left: number; top: number } | null
        = null;
    /** 悬浮球背景色（空 = 用主题默认 ✓） */
    private ballColor = '';
    /** 最近会话（标题栏「会话 ▾」下拉 ✓） */
    private sessions: Array<{ id: string; title: string;
                              pinned?: boolean }> = [];
    private readonly sessionButton: HTMLButtonElement;
    private readonly files: HTMLDivElement;
    private fileTimer: number | undefined;
    /** 小圆标（小球）在界面上的**自由位置**（用户可拖到任意位置 ✓） */
    private iconPos: { left: number; top: number } | null = null;
    /** 拖动小圆标（松手吸附到最近的边，不触发展开 ✓） */
    private iconDrag: { x: number; y: number; moved: boolean } | null = null;
    /** 刚拖过（用来吞掉紧接着的 click，避免"拖完就展开" ✓） */
    private iconMoved = false;
    /** 待发送附件（图片 / 文本 = 4 张上限，和后端一致 ✓） */
    private attachments: Array<{ name: string; mime: string;
                                 kind: 'image' | 'text'; data?: string;
                                 text?: string; size?: number }> = [];
    private attachBar: HTMLDivElement | null = null;
    private fileInput: HTMLInputElement | null = null;
    /** 输入历史（↑ 上一条 / ↓ 下一条 ✓） */
    private readonly history: string[] = [];
    private historyAt = -1;
    /** 钉住（关掉贴边自动隐藏 ✓） */
    private pinned = false;
    private hideTimer: number | undefined;
    private readonly pinButton: HTMLButtonElement;

    constructor(options: PiFloatOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = `desk-pi-float theme-${options.theme}`;

        // ---- 头（拖拽手柄）----
        const head: HTMLDivElement = document.createElement('div');
        head.className = 'desk-pi-float-head';
        const title = document.createElement('span');
        title.className = 'desk-pi-float-title';
        title.textContent = 'PI';
        this.sessionButton = document.createElement('button');
        this.sessionButton.className = 'desk-pi-float-session';
        this.sessionButton.textContent = '会话 ▾';
        this.sessionButton.title = '切换会话（最近 12 个）';
        this.sessionButton.addEventListener('click', (event) => {
            event.stopPropagation();
            this._sessionMenu();
        });
        const actions = document.createElement('div');
        actions.className = 'desk-pi-float-actions';
        const open = this._iconButton('打开会话', '⤢', () => {
            if (!this.sessionId) {
                this.options.onToast?.('info', '还没有会话：先发一句话');
                return;
            }
            this.options.onOpenSession?.(this.sessionId);
        });
        const fresh = this._iconButton('新话题', '＋', () => this.newTopic());
        const detach = this._iconButton('浮到窗口外（独立置顶小窗）', '⧉',
                                        () => this.detach());
        // ★ 用户 2026-11-08：关掉对话窗口 → **小球出现**（不是全没了）
        const close = this._iconButton('关闭（回到 PI 小球）', '✕',
                                       () => this.showBall());
        this.pinButton = this._iconButton('钉住（贴边不自动收起）', '📍',
                                          () => this._togglePin());
        actions.append(detach, open, fresh, this.pinButton, close);
        head.append(title, this.sessionButton, actions);
        head.addEventListener('mousedown', (event) => this._startDrag(event));

        // ---- 对话区 ----
        this.log = document.createElement('div');
        this.log.className = 'desk-pi-float-log';

        // ---- @文件 联想（复用后端 `ai_files` ✓）----
        this.files = document.createElement('div');
        this.files.className = 'desk-pi-float-files';
        this.files.style.display = 'none';

        // ---- 输入区 ----
        const composer = document.createElement('div');
        composer.className = 'desk-pi-float-composer';
        this.input = document.createElement('textarea');
        this.input.className = 'desk-pi-float-input';
        this.input.rows = 2;
        this.input.placeholder = '输入消息…（Enter 发送 / Shift+Enter 换行）';
        this.sendButton = document.createElement('button');
        this.sendButton.className = 'desk-pi-float-send';
        this.sendButton.textContent = '→';
        this.sendButton.title = '发送';
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.send();
                return;
            }
            // ★ ↑ / ↓ 翻历史输入（和 PI 对话页一致；用户 2026-11-08 要求 ✓）
            if (event.key === 'ArrowUp') {
                if (!this.history.length) return;
                event.preventDefault();
                this.historyAt = Math.min(this.history.length - 1,
                                          this.historyAt + 1);
                this._applyHistory(this.history[this.history.length - 1
                    - this.historyAt] || '');
                return;
            }
            if (event.key === 'ArrowDown') {
                if (this.historyAt < 0) return;
                event.preventDefault();
                this.historyAt = Math.max(-1, this.historyAt - 1);
                this._applyHistory(this.historyAt < 0 ? ''
                    : (this.history[this.history.length - 1
                        - this.historyAt] || ''));
            }
        });
        this.sendButton.addEventListener('click', () => this.send());
        this.input.addEventListener('input', () => this._onInput());
        // ★ 附件条（图片缩略图 / 文件名 + ✕）✓
        this.attachBar = document.createElement('div');
        this.attachBar.className = 'desk-pi-attach-bar desk-pi-float-attach-bar';
        this.attachBar.style.display = 'none';
        // 📎 上传（图片 / 代码 / 文本）
        const attachButton = document.createElement('button');
        attachButton.className = 'desk-pi-float-attach';
        attachButton.textContent = '📎';
        attachButton.title = '上传图片 / 代码 / 文本（也可粘贴 / 拖进来）';
        attachButton.addEventListener('click', () => this.fileInput?.click());
        this.fileInput = document.createElement('input');
        this.fileInput.type = 'file';
        this.fileInput.multiple = true;
        this.fileInput.accept = 'image/*,.py,.md,.txt,.json,.csv,.log,.yml,'
            + '.yaml,.ts,.js,.html,.css,.sql,.sh';
        this.fileInput.style.display = 'none';
        this.fileInput.addEventListener('change', () => {
            this.addFiles(Array.from(this.fileInput?.files || []));
            if (this.fileInput) this.fileInput.value = '';
        });
        // 粘贴图片（Ctrl+V）
        this.input.addEventListener('paste', (event) => {
            const files = Array.from(event.clipboardData?.items || [])
                .filter((item) => item.kind === 'file')
                .map((item) => item.getAsFile())
                .filter((file): file is File => !!file);
            if (files.length) {
                event.preventDefault();
                this.addFiles(files);
            }
        });
        // 拖文件进来
        composer.addEventListener('dragover', (event) => {
            event.preventDefault();
            composer.classList.add('drag');
        });
        composer.addEventListener('dragleave', () => {
            composer.classList.remove('drag');
        });
        composer.addEventListener('drop', (event) => {
            event.preventDefault();
            composer.classList.remove('drag');
            const files = Array.from(event.dataTransfer?.files || []);
            if (files.length) this.addFiles(files);
        });
        const composerRow = document.createElement('div');
        composerRow.className = 'desk-pi-float-composer-row';
        // ★ 输入行只放「输入框 + 发送」（📎 已挪到底部模型按钮左边 ✓）
        composerRow.append(this.input, this.sendButton);
        composer.append(this.attachBar, composerRow, this.fileInput);

        // ---- 底部：模型 + 状态 ----
        const foot = document.createElement('div');
        foot.className = 'desk-pi-float-foot';
        this.modelButton = document.createElement('button');
        this.modelButton.className = 'desk-pi-float-model';
        this.modelButton.textContent = '◉ 未选择模型';
        this.modelButton.title = '切换模型 / 供应商';
        this.modelButton.addEventListener('click', () => this.options.onModels?.());
        const version = document.createElement('span');
        version.className = 'desk-pi-float-version';
        version.textContent = 'pi 悬浮窗';
        // ★ 📎 放在模型按钮**左边**，高度和模型按钮一致（22px ✓）
        this.attachButton = attachButton;
        foot.append(this.attachButton, this.modelButton, version);

        // ---- 提示行（未安装 / 未配置模型）----
        this.hint = document.createElement('div');
        this.hint.className = 'desk-pi-float-hint';
        this.hint.style.display = 'none';

        // ---- 执行进度条（默认隐藏，跑完才收 ✓）----
        this.progress = document.createElement('div');
        this.progress.className = 'desk-pi-float-progress';
        this.progress.style.display = 'none';
        this.progressFill = document.createElement('i');
        this.progressText = document.createElement('span');
        this.progressText.className = 'desk-pi-float-progress-text';
        this.progress.append(this.progressFill, this.progressText);

        this.element.append(head, this.log, this.hint, this.files,
                            composer, foot, this.progress);

        // ---- 收起后的小圆标（贴边）----
        this.icon = document.createElement('button');
        this.icon.className = 'desk-pi-float-icon';
        this.icon.title = 'PI 助手（双击打开对话窗口 / 可拖动到任意位置）';
        // ★ 用户 2026-11-08：小球用「π」并放大（一眼看出是 PI ✓）
        this.icon.textContent = 'π';
        this.icon.style.display = 'none';
        // ★ 用户 2026-11-08 的新交互：
        //   * 激活时**先出现小球**（不是对话窗口）；
        //   * **双击小球** → 小球隐藏、对话窗口出现；
        //   * 小球可以在**界面任意位置**拖动（不再吸附边界 ✓）。
        this.setBallColor(String(options.ballColor || ''));
        this.icon.addEventListener('mousedown', (event) => {
            this._startIconDrag(event);
        });
        this.icon.addEventListener('dblclick', (event) => {
            event.preventDefault();
            if (this.iconMoved) return;
            this.openCard();
        });
        this.icon.addEventListener('click', (event) => {
            // 单击不动作（双击才开窗）；标题提示里写清楚 ✓
            event.preventDefault();
        });
        // ★ 右键菜单（用户 2026-11-08）：
        //   「打开 PI 悬浮窗」/「关闭悬浮窗（彻底退出悬浮功能）」
        this.icon.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._ballMenu(event.clientX, event.clientY);
        });

        try {
            this.pinned = window.localStorage.getItem(PINNED_KEY) === '1';
        } catch {
            this.pinned = false;
        }
        this._restore();
        this.render();
        this.refresh();
        // ★ 窗口缩放：小圆标 / 卡片都要留在可视区（用户会拖到边角 ✓）
        window.addEventListener('resize', () => {
            if (this.collapsed) {
                this._placeIcon();
            } else if (!this.drag) {
                const box = this.element.getBoundingClientRect();
                const left = Math.max(0, Math.min(
                    window.innerWidth - Math.max(120, box.width), box.left));
                const top = Math.max(0, Math.min(
                    window.innerHeight - Math.max(80, box.height), box.top));
                this.element.style.left = `${left}px`;
                this.element.style.top = `${top}px`;
            }
            if (this.icon.style.display !== 'none') {
                this._placeIcon();
            }
        });
        // ★ 主窗口 ↔ 独立浮窗：主题 / 位置 / 钉住 实时同步（storage 事件 ✓）
        window.addEventListener('storage', (event) => {
            const key = String(event.key || '');
            if (key === 'minibt.desk.theme') {
                this.setTheme(event.newValue === 'light' ? 'light' : 'dark');
                return;
            }
            if (key === PINNED_KEY) {
                this.pinned = event.newValue === '1';
                this._syncPinButton();
                return;
            }
            if (key === POS_KEY && !this.collapsed) {
                try {
                    const data = JSON.parse(event.newValue || '{}') as {
                        left?: number; top?: number };
                    if (typeof data.left === 'number') {
                        this.element.style.left = `${data.left}px`;
                    }
                    if (typeof data.top === 'number') {
                        this.element.style.top = `${data.top}px`;
                    }
                } catch {
                    /* 忽略坏数据 */
                }
            }
        });
    }

    // ------------------------------------------------------------- 显示
    /**
     * 激活浮窗 = **只显示小球**（不是对话窗口 ✓ 用户 2026-11-08）
     *
     * 想要对话窗口：双击小球（或 `openCard()`）。
     */
    show(): void {
        this.showBall();
    }

    /** 彻底隐藏（小球 + 对话窗口都收起来） */
    hide(): void {
        this.element.style.display = 'none';
        this.icon.style.display = 'none';
        this.collapsed = false;
        this.options.onClose?.();
    }

    /**
     * 快捷键 / 按钮的智能切换 ✓
     *
     * * 对话窗口开着 → 收成小球（不是全关，随手能再点开）；
     * * 只有小球 → 打开对话窗口；
     * * 都没有 → 出现小球。
     */
    toggle(): void {
        if (!this.collapsed
            && this.element.style.display !== 'none') {
            this.showBall();
            return;
        }
        if (this.icon.style.display !== 'none') {
            this.openCard();
            return;
        }
        this.showBall();
    }

    get visible(): boolean {
        return this.element.style.display !== 'none' && !this.collapsed;
    }

    /** 正在跑（进度条 / 外部判断用 ✓） */
    get busy(): boolean {
        return this.streaming;
    }

    /** 第一次打开时拉一次后端状态（装没装 / 模型 / 会话）✓ */
    refresh(): void {
        this.options.onCommand('pi_status', {});
        this.options.onCommand('pi_models', {});
        if (!this.sessionId) {
            this.options.onCommand('pi_sessions', {});
            return;
        }
        // ★ 独立浮窗关着的时候**不发脚本**（避免 Qt discard 警告）→
        //   重新打开时补拉一次当前会话，界面不会停在旧内容 ✓
        this.options.onCommand('pi_history', { id: this.sessionId });
    }

    /** 悬浮球背景色（`''` = 恢复默认；持久化由设置页负责 ✓） */
    setBallColor(color: string): void {
        const value = String(color || '').trim();
        this.ballColor = /^#[0-9a-fA-F]{3,8}$/.test(value) ? value : '';
        if (!this.icon) return;
        if (this.ballColor) {
            this.icon.style.background = this.ballColor;
            this.icon.style.borderColor = this.ballColor;
            this.icon.dataset.custom = '1';
        } else {
            this.icon.style.background = '';
            this.icon.style.borderColor = '';
            delete this.icon.dataset.custom;
        }
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.element.className = `desk-pi-float theme-${theme}`;
    }

    // ------------------------------------------------------------- 补丁
    piOnPatch(patch: Record<string, unknown>): void {
        const kind = String(patch.type || '');
        if (kind === 'pi_status') {
            this.installed = patch.installed !== false;
            this._syncReady();
            return;
        }
        if (kind === 'pi_models') {
            const active = (patch.active || {}) as Record<string, unknown>;
            this.model = String(active.model || '');
            this.modelButton.textContent = `◉ ${this.model || '未选择模型'}`;
            this._syncReady();
            return;
        }
        if (kind === 'pi_sessions') {
            const items = (patch.items || []) as Array<Record<string, unknown>>;
            this.sessions = items.map((row) => ({
                id: String(row.id || ''),
                title: String(row.title || row.name || row.id || ''),
                pinned: row.pinned === true,
            })).filter((row) => row.id);
            if (!this.sessionId && items.length) {
                // 默认接**最近一个会话**（置顶的优先，后端已排序 ✓）
                this.sessionId = String(items[0].id || '');
                this.options.onCommand('pi_history', { id: this.sessionId });
            }
            return;
        }
        if (kind === 'pi_session' || kind === 'pi_history') {
            const session = (patch.session || {}) as Record<string, unknown>;
            const id = String(session.id || '');
            if (!id) return;
            this.sessionId = id;
            this.messages = ((session.messages || []) as Array<
                Record<string, unknown>>)
                .filter((row) => row.role === 'user'
                    || (row.role === 'assistant'
                        && String(row.content || '').trim()))
                .map((row) => ({ role: String(row.role || ''),
                                 content: String(row.content || ''),
                                 thinking: String(row.thinking || ''),
                                 attachments: Array.isArray(
                                     row.attachments)
                                     ? (row.attachments as FloatAttachment[])
                                     : undefined }));
            this.live = null;
            this.render();
            if (this.pendingSend) {
                const text = this.pendingSend;
                this.pendingSend = '';
                this._post(text);
            }
            return;
        }
        if (kind === 'ai_files') {
            // @文件 联想结果 ✓
            this.setFiles((patch.items || []) as Array<Record<string, unknown>>);
            return;
        }
        if (kind === 'pi_event') {
            if (String(patch.id || '') !== this.sessionId) return;
            this._event(patch);
        }
    }

    // ------------------------------------------------------------- 动作
    private send(): void {
        const text = this.input.value.trim();
        // ★ 只有附件、没有文字也能发（后端会用「（请看附件）」占位 ✓）
        if (!text && !this.attachments.length) return;
        if (text) this._remember(text);
        if (!this.ready) {
            this.options.onToast?.('warning', this.readyHint || '先配置模型');
            return;
        }
        this.input.value = '';
        if (!this.sessionId) {
            // 没有会话 → 用首句建一个（和独立界面一致 ✓）
            this.pendingSend = text || '（请看附件）';
            this.options.onCommand('pi_new_session', {
                cwd: '', title: (text || '（附件）').slice(0, 40),
            });
            this.streaming = true;
            this._showProgress('正在新建会话…');
            return;
        }
        this._post(text);
    }

    // ------------------------------------------------------------- 附件
    /** 读文件 → 附件（图片 dataURL / 文本内容；单个 ≤4MB，最多 4 个 ✓） */
    addFiles(files: File[]): void {
        for (const file of files) {
            if (this.attachments.length >= 4) {
                this.options.onToast?.('warning', '最多 4 个附件');
                break;
            }
            if (file.size > 4 * 1024 * 1024) {
                this.options.onToast?.('warning',
                                       `${file.name} 超过 4MB，已跳过`);
                continue;
            }
            const isImage = /^image\//.test(file.type || '')
                || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
            const reader = new FileReader();
            reader.onload = () => {
                const value = String(reader.result || '');
                this.attachments.push({
                    name: file.name || (isImage ? 'image.png' : 'file.txt'),
                    mime: file.type || (isImage ? 'image/png' : 'text/plain'),
                    kind: isImage ? 'image' : 'text',
                    data: isImage ? value : undefined,
                    text: isImage ? undefined : value,
                    size: file.size,
                });
                this._renderAttachBar();
            };
            reader.onerror = () => this.options.onToast?.(
                'warning', `读取 ${file.name} 失败`);
            if (isImage) reader.readAsDataURL(file);
            else reader.readAsText(file);
        }
    }

    private _renderAttachBar(): void {
        if (!this.attachBar) return;
        this.attachBar.textContent = '';
        this.attachBar.style.display = this.attachments.length ? '' : 'none';
        this.attachments.forEach((item, index) => {
            const box = document.createElement('div');
            box.className = `desk-pi-attach ${item.kind}`;
            if (item.kind === 'image' && item.data) {
                const img = document.createElement('img');
                img.src = item.data;
                img.alt = item.name;
                box.appendChild(img);
            }
            const label = document.createElement('span');
            label.className = 'desk-pi-attach-name';
            label.textContent = item.name;
            box.appendChild(label);
            const remove = document.createElement('button');
            remove.className = 'desk-pi-attach-x';
            remove.textContent = '✕';
            remove.addEventListener('click', () => {
                this.attachments.splice(index, 1);
                this._renderAttachBar();
            });
            box.appendChild(remove);
            this.attachBar?.appendChild(box);
        });
    }

    /** 记一条输入历史（最多 100 条；重复的只留最新 ✓） */
    private _remember(text: string): void {
        const value = String(text || '').trim();
        if (!value) return;
        const at = this.history.lastIndexOf(value);
        if (at >= 0) this.history.splice(at, 1);
        this.history.push(value);
        if (this.history.length > 100) this.history.shift();
        this.historyAt = -1;
    }

    private _applyHistory(text: string): void {
        this.input.value = text;
        this.input.selectionStart = text.length;
        this.input.selectionEnd = text.length;
        this.onInputChanged();
    }

    private onInputChanged(): void {
        try {
            this._onInput();
        } catch {
            /* @文件 联想失败不影响输入 */
        }
    }

    private _post(text: string): void {
        this.streaming = true;
        const attachments = this.attachments.map((item) => ({ ...item }));
        this.attachments = [];
        this._renderAttachBar();
        this.messages.push({
            role: 'user', content: text || '（请看附件）',
            attachments: attachments.length
                ? (attachments as FloatAttachment[]) : undefined,
        });
        this.live = { role: 'assistant', content: '' };
        this.render();
        this._showProgress('思考中…');
        this.options.onCommand('pi_send', {
            id: this.sessionId, text: text || '（请看附件）', refs: [],
            model: this.model, effort: 'medium', permission: 'full',
            compress: false, attachments,
        });
    }

    private newTopic(): void {
        this.sessionId = '';
        this.messages = [];
        this.live = null;
        this.streaming = false;
        this.pendingSend = '';
        this.progress.style.display = 'none';
        this.render();
        this.options.onToast?.('info', '新话题：发第一句话时创建会话');
        this.input.focus();
    }

    /** 会话下拉：最近 12 个（置顶的排前面 ✓） */
    private _sessionMenu(): void {
        const list = this.sessions.slice(0, 12);
        if (!list.length) {
            this.options.onToast?.('info', '还没有会话：发一句话会自动新建');
            return;
        }
        const box = this.files;
        box.textContent = '';
        box.className = 'desk-pi-float-files desk-pi-float-sessions';
        // ★ 会话搜索：输入即过滤（用户「会话搜索」需求 ✓）
        const search = document.createElement('input');
        search.className = 'desk-pi-float-search';
        search.placeholder = '搜索会话…';
        box.appendChild(search);
        const rowsBox = document.createElement('div');
        box.appendChild(rowsBox);
        const renderRows = (keyword: string) => {
            rowsBox.textContent = '';
            const needle = keyword.trim().toLowerCase();
            const filtered = list.filter((row) => !needle
                || row.title.toLowerCase().includes(needle));
            if (!filtered.length) {
                const empty = document.createElement('div');
                empty.className = 'desk-pi-float-empty';
                empty.textContent = '（没有匹配的会话）';
                rowsBox.appendChild(empty);
                return;
            }
            for (const row of filtered) {
                const button = document.createElement('button');
                button.className = 'desk-pi-float-file';
                button.textContent = (row.pinned ? '📌 ' : '')
                    + (row.title || row.id);
                button.title = row.id;
                button.addEventListener('mousedown', (event) => {
                    event.preventDefault();
                    this.sessionId = row.id;
                    this.messages = [];
                    this.live = null;
                    box.style.display = 'none';
                    this.options.onCommand('pi_history', { id: row.id });
                });
                rowsBox.appendChild(button);
            }
        };
        search.addEventListener('input', () => renderRows(search.value));
        search.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') box.style.display = 'none';
        });
        renderRows('');
        box.style.display = '';
    }

    /** 浮到窗口外（独立置顶小窗；由后端开 Qt 窗口 ✓） */
    detach(): void {
        this.options.onCommand('pi_detach_float', {});
        this.options.onToast?.('info', '正在打开独立浮窗（置顶小窗）…');
    }

    /** `@文件` 联想（后端 `ai_files` 回包 → `setFiles` ✓） */
    private _onInput(): void {
        const value = this.input.value;
        const caret = this.input.selectionStart ?? value.length;
        const head = value.slice(0, caret);
        const matched = /(^|\s)@([\w./-]*)$/.exec(head);
        if (!matched) {
            this.files.style.display = 'none';
            return;
        }
        if (this.fileTimer !== undefined) window.clearTimeout(this.fileTimer);
        this.fileTimer = window.setTimeout(() => {
            this.options.onCommand('ai_files', { query: matched[2] || '' });
        }, 180);
    }

    /** 后端 `ai_files` 结果 → 下拉（点一下插入 `@路径` ✓） */
    setFiles(items: Array<Record<string, unknown>>): void {
        this.files.textContent = '';
        this.files.className = 'desk-pi-float-files';
        if (!items.length) {
            this.files.style.display = 'none';
            return;
        }
        for (const item of items.slice(0, 20)) {
            const path = String(item.path || '');
            const button = document.createElement('button');
            button.className = 'desk-pi-float-file';
            button.textContent = path;
            button.addEventListener('mousedown', (event) => {
                event.preventDefault();
                const value = this.input.value;
                const caret = this.input.selectionStart ?? value.length;
                const head = value.slice(0, caret).replace(
                    /(^|\s)@[\w./-]*$/, `$1@${path} `);
                this.input.value = head + value.slice(caret);
                this.files.style.display = 'none';
                this.input.focus();
            });
            this.files.appendChild(button);
        }
        this.files.style.display = '';
    }

    private _togglePin(): void {
        this.pinned = !this.pinned;
        this._syncPinButton();
        try {
            window.localStorage.setItem(PINNED_KEY,
                                        this.pinned ? '1' : '0');
        } catch {
            /* 隐私模式忽略 */
        }
        if (this.pinned) this._cancelAutoHide();
    }

    private _syncPinButton(): void {
        this.pinButton.textContent = this.pinned ? '📌' : '📍';
        this.pinButton.title = this.pinned ? '已钉住（贴边不自动收起）'
            : '钉住（贴边不自动收起）';
        if (this.element.classList.contains('desk-pi-float-max')) {
            // 独立浮窗不参与贴边收起 → 显示为钉住态 ✓
            this.pinButton.style.display = 'none';
        }
    }

    private _cancelAutoHide(): void {
        if (this.hideTimer !== undefined) {
            window.clearTimeout(this.hideTimer);
            this.hideTimer = undefined;
        }
    }

    // ------------------------------------------------------------- 事件
    private _event(patch: Record<string, unknown>): void {
        const kind = String(patch.event || '');
        const text = String(patch.text || '');
        if (kind === 'start') {
            this.streaming = true;
            this._showProgress('思考中…');
            return;
        }
        if (kind === 'thinking') {
            this._showProgress('思考中…');
            return;
        }
        if (kind === 'delta') {
            const live = this.live || (this.live = { role: 'assistant',
                                                     content: '' });
            live.content += text;
            this.render();
            return;
        }
        if (kind === 'assistant') {
            const live = this.live;
            if (live) live.content = text || live.content;
            this.render();
            return;
        }
        if (kind === 'tool') {
            this._showProgress(`执行工具：${String(patch.name || '')}…`);
            return;
        }
        if (kind === 'tool_result') {
            this._showProgress('继续思考…');
            return;
        }
        if (kind === 'error') {
            this.streaming = false;
            this._hideProgress();
            this.messages.push({ role: 'assistant',
                                 content: `⚠ ${String(patch.error || '')}` });
            this.render();
            return;
        }
        if (kind === 'done' || kind === 'stopped') {
            this.streaming = false;
            this._hideProgress();
            const live = this.live;
            if (live && live.content.trim()) {
                this.messages.push(live);
            }
            this.live = null;
            this.render();
            return;
        }
        if (kind === 'queued' || kind === 'appended') {
            this._showProgress(String(patch.text || '已排队…'));
        }
    }

    // ------------------------------------------------------------- 渲染
    private render(): void {
        this.log.textContent = '';
        const rows = [...this.messages];
        if (this.live) rows.push(this.live);
        const recent = rows.slice(-8);
        if (!recent.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-pi-float-empty';
            empty.textContent = this.ready
                ? '问点什么吧 —— 会发到会话里（多轮 / 可追溯）'
                : (this.readyHint || '正在检查 PI 状态…');
            this.log.appendChild(empty);
            this._scroll();
            return;
        }
        for (const row of recent) {
            const item = document.createElement('div');
            item.className = `desk-pi-float-msg ${row.role}`;
            const body = document.createElement('div');
            body.className = 'desk-pi-float-bubble';
            const text = String(row.content || '').trim();
            // ★ v1.3.7-105：assistant 的输出走 Markdown（**表格 / 列表 / 粗体**）；
            //   以前一律 textContent，表格只显示一堆 `|` ✗
            const markup = (row.role === 'assistant' && text)
                ? markdownToHtml(text.length > 4000
                    ? text.slice(0, 4000) + '…' : text)
                : '';
            if (markup) {
                body.innerHTML = markup;
                body.classList.add('md');
            } else {
                body.textContent = text.length > 1200
                    ? text.slice(0, 1200) + '…' : text;
            }
            if (!text && row === this.live) body.textContent = '▍';
            item.appendChild(body);
            const attached = row.attachments || [];
            if (attached.length) {
                const list = document.createElement('div');
                list.className = 'desk-pi-float-attach-list';
                for (const file of attached.slice(0, 4)) {
                    if (file.kind === 'image' && file.data) {
                        const img = document.createElement('img');
                        img.src = file.data;
                        img.alt = String(file.name || 'image');
                        img.title = String(file.name || '');
                        list.appendChild(img);
                    } else {
                        const tag = document.createElement('span');
                        tag.className = 'desk-pi-float-attach-name';
                        tag.textContent = `📄 ${String(file.name || '')}`;
                        list.appendChild(tag);
                    }
                }
                item.appendChild(list);
            }
            this.log.appendChild(item);
        }
        this._scroll();
    }

    private _scroll(): void {
        this.log.scrollTop = this.log.scrollHeight;
    }

    private _showProgress(text: string): void {
        this.streaming = true;
        this.progress.style.display = 'flex';
        this.progressText.textContent = text;
        this.progress.classList.add('on');
    }

    private _hideProgress(): void {
        this.streaming = false;
        this.progress.classList.remove('on');
        this.progress.style.display = 'none';
        this.progressText.textContent = '';
    }

    // ------------------------------------------------------------- 激活条件
    private ready = false;
    private readyHint = '';

    /** pi 装了 **且** 模型配置好 → 才允许输入 ✓ */
    private _syncReady(): void {
        const installed = this.installed !== false;
        const hasModel = !!this.model;
        this.ready = installed && hasModel;
        this.readyHint = installed
            ? (hasModel ? '' : '还没选择模型：点下面的模型按钮配置')
            : '没有检测到 pi：点「模型」旁的提示安装后再用';
        this.input.disabled = !this.ready;
        this.sendButton.disabled = !this.ready;
        this.modelButton.disabled = false;
        this.hint.style.display = this.ready ? 'none' : '';
        this.hint.innerHTML = this.ready ? '' : `<span>${esc(
            this.readyHint)}</span>`;
        if (!this.ready && installed) {
            const fix = document.createElement('button');
            fix.className = 'desk-pi-float-fix';
            fix.textContent = '打开模型设置';
            fix.addEventListener('click', () => this.options.onModels?.());
            this.hint.appendChild(fix);
        }
        this.input.placeholder = this.ready
            ? '输入消息…（Enter 发送 / Shift+Enter 换行）'
            : (this.readyHint || '暂不可用');
        this.render();
    }

    // ------------------------------------------------------------- 拖拽 / 收起
    private _startDrag(event: MouseEvent): void {
        if ((event.target as HTMLElement).closest('button')) return;
        const box = this.element.getBoundingClientRect();
        this.drag = { x: event.clientX, y: event.clientY,
                      left: box.left, top: box.top };
        const move = (moveEvent: MouseEvent) => this._onDrag(moveEvent);
        const up = () => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            this._endDrag();
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        event.preventDefault();
    }

    private _onDrag(event: MouseEvent): void {
        const drag = this.drag;
        if (!drag) return;
        const box = this.element.getBoundingClientRect();
        const left = Math.max(0, Math.min(window.innerWidth - box.width,
                                          drag.left + event.clientX - drag.x));
        const top = Math.max(0, Math.min(window.innerHeight - box.height,
                                         drag.top + event.clientY - drag.y));
        this.element.style.left = `${left}px`;
        this.element.style.top = `${top}px`;
        this.element.style.right = 'auto';
        this.element.style.bottom = 'auto';
    }

    /** 松手：贴到四边（<28px）→ 自动收起成小圆标 ✓ */
    private _endDrag(): void {
        this.drag = null;
        const box = this.element.getBoundingClientRect();
        const nearLeft = box.left <= EDGE;
        const nearRight = window.innerWidth - box.right <= EDGE;
        const nearTop = box.top <= EDGE;
        const nearBottom = window.innerHeight - box.bottom <= EDGE;
        this._savePosition(box.left, box.top);
        if (!(nearLeft || nearRight || nearTop || nearBottom)) return;
        this.collapse(nearLeft ? 'left' : (nearRight ? 'right'
            : (nearTop ? 'top' : 'bottom')));
    }

    /**
     * （兼容旧调用）收起成小球 ✓
     *
     * 新交互里小球就是**常态**（激活即小球），`edge` / `offset` 只用来
     * 兼容老调用（贴在某个角上）；日常一律走 `showBall()`。
     */
    collapse(edge = 'right', offset?: number): void {
        this.showBall();
        if (!Number.isFinite(Number(offset))) return;
        // 老调用给了偏移 → 按边换算成自由坐标（仅兼容用 ✓）
        const size = 44;
        const value = Number(offset);
        this.iconPos = (edge === 'left' || edge === 'right')
            ? { left: edge === 'left' ? 4 : window.innerWidth - size - 4,
                top: value }
            : { left: value,
                top: edge === 'top' ? 4 : window.innerHeight - size - 4 };
        this._placeIcon();
    }

    /** 小球右键菜单：打开悬浮窗 / 彻底关闭悬浮功能 ✓ */
    private _ballMenu(x: number, y: number): void {
        showMenu(x, y, [
            { label: '打开 PI 悬浮窗', run: () => this.openCard() },
            {
                label: '关闭悬浮窗',
                run: () => this.quit(),
            },
        ]);
    }

    /**
     * **彻底退出**悬浮 AI 对话功能（用户 2026-11-08 的"关闭悬浮窗"）✓
     *
     * 小球 + 对话窗口一起消失，并通知宿主销毁实例；独立小窗也一起关掉。
     * 想再用：菜单「AI 悬浮窗」/ `F1` → 会重新创建一个（先出现小球）。
     */
    quit(): void {
        this._cancelAutoHide();
        this.element.style.display = 'none';
        this.icon.style.display = 'none';
        this.collapsed = false;
        this.options.onQuit?.();
        this.options.onClose?.();
    }

    /** 宿主销毁用：把两个 DOM 节点摘掉（之后再 `new` 一个 ✓） */
    destroy(): void {
        this._cancelAutoHide();
        try {
            this.element.remove();
        } catch {
            /* ignore */
        }
        try {
            this.icon.remove();
        } catch {
            /* ignore */
        }
        this.collapsed = false;
    }

    /** 显示小球（隐藏对话窗口）—— 激活 / 关窗都走这里 ✓ */
    showBall(): void {
        this.collapsed = true;
        this.element.style.display = 'none';
        this.icon.style.display = '';
        this._placeIcon();
        this._saveIconPos();
    }

    /**
     * 打开对话窗口（小球隐藏）—— 双击小球 / 快捷键用 ✓
     */
    openCard(): void {
        this.collapsed = false;
        this.icon.style.display = 'none';
        this.element.style.display = 'flex';
        // 窗口出现在小球附近（但保证完整可见 ✓）
        if (this.iconPos) {
            const box = { width: 400, height: 460 };
            const left = Math.max(0, Math.min(
                window.innerWidth - box.width, this.iconPos.left - 40));
            const top = Math.max(0, Math.min(
                window.innerHeight - box.height, this.iconPos.top - 40));
            this.element.style.left = `${left}px`;
            this.element.style.top = `${top}px`;
            this.element.style.right = 'auto';
            this.element.style.bottom = 'auto';
        }
        try {
            window.localStorage.removeItem(COLLAPSE_KEY);
        } catch {
            /* ignore */
        }
        this.refresh();
        this.input.focus();
        this._cancelAutoHide();
    }

    /** 把小球摆在**记住的自由位置**（钳制进可视区 ✓） */
    private _placeIcon(): void {
        const size = 44;
        const pos = this.iconPos || { left: window.innerWidth - size - 16,
                                      top: window.innerHeight * 0.35 };
        const left = Math.max(0, Math.min(window.innerWidth - size,
                                          Number(pos.left) || 0));
        const top = Math.max(0, Math.min(window.innerHeight - size,
                                         Number(pos.top) || 0));
        this.iconPos = { left, top };
        this.icon.style.left = `${left}px`;
        this.icon.style.top = `${top}px`;
        this._saveIconPos();
    }

    private _saveIconPos(): void {
        try {
            window.localStorage.setItem(
                ICON_KEY, JSON.stringify(this.iconPos || {}));
            window.localStorage.setItem(COLLAPSE_KEY, 'ball');
        } catch {
            /* 隐私模式忽略 */
        }
    }

    /** 按下圆标：记录起点；拖动时跟着鼠标，松手吸附最近的边 ✓ */
    private _startIconDrag(event: MouseEvent): void {
        // 右键留给菜单（不要顺手开始拖拽 ✓）
        if (event.button !== 0) return;
        this.iconDrag = { x: event.clientX, y: event.clientY, moved: false };
        const move = (moveEvent: MouseEvent) => this._onIconDrag(moveEvent);
        const up = (upEvent: MouseEvent) => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            this._endIconDrag(upEvent);
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        event.preventDefault();
        event.stopPropagation();
    }

    private _onIconDrag(event: MouseEvent): void {
        const drag = this.iconDrag;
        if (!drag) return;
        if (Math.abs(event.clientX - drag.x) > 3
            || Math.abs(event.clientY - drag.y) > 3) {
            drag.moved = true;
        }
        if (!drag.moved) return;
        const size = 44;
        const left = Math.max(0, Math.min(window.innerWidth - size,
                                          event.clientX - size / 2));
        const top = Math.max(0, Math.min(window.innerHeight - size,
                                         event.clientY - size / 2));
        this.icon.style.left = `${left}px`;
        this.icon.style.top = `${top}px`;
    }

    private _endIconDrag(event: MouseEvent): void {
        const drag = this.iconDrag;
        this.iconDrag = null;
        if (!drag || !drag.moved) return;
        this.iconMoved = true;
        // ★ 松手就停在**任意位置**（不再吸附到四边 ✓ 用户 2026-11-08）
        const size = 44;
        this.iconPos = {
            left: Math.max(0, Math.min(window.innerWidth - size,
                                       event.clientX - size / 2)),
            top: Math.max(0, Math.min(window.innerHeight - size,
                                      event.clientY - size / 2)),
        };
        this._placeIcon();
        // 拖完的 300ms 内双击不生效（避免"拖完就开窗"）
        window.setTimeout(() => { this.iconMoved = false; }, 300);
    }

    /** 老 API：展开对话窗口（等价 `openCard()` ✓） */
    expand(): void {
        this.openCard();
    }

    private _savePosition(left: number, top: number): void {
        try {
            window.localStorage.setItem(POS_KEY,
                                        JSON.stringify({ left, top }));
        } catch {
            /* ignore */
        }
    }

    private _restore(): void {
        let left = window.innerWidth - 400;
        let top = Math.max(60, window.innerHeight - 420);
        try {
            const raw = window.localStorage.getItem(POS_KEY);
            if (raw) {
                const data = JSON.parse(raw) as { left?: number;
                                                  top?: number };
                left = Number(data.left ?? left);
                top = Number(data.top ?? top);
            }
        } catch {
            /* ignore */
        }
        this.element.style.left = `${Math.max(0, left)}px`;
        this.element.style.top = `${Math.max(0, top)}px`;
        this.element.style.right = 'auto';
        this.element.style.bottom = 'auto';
        this.element.style.display = 'none';
        // ★ 上次是「小球」状态 → 刷新 / 重启后还原小球的位置 ✓
        let collapsed = '';
        try {
            collapsed = String(
                window.localStorage.getItem(COLLAPSE_KEY) || '');
        } catch {
            collapsed = '';
        }
        try {
            const raw = window.localStorage.getItem(ICON_KEY);
            if (raw) {
                const data = JSON.parse(raw) as { left?: number;
                                                  top?: number };
                if (typeof data.left === 'number'
                    && typeof data.top === 'number') {
                    this.iconPos = { left: data.left, top: data.top };
                }
            }
        } catch {
            /* 坏数据 → 用默认位置 */
        }
        if (!collapsed && !this.iconPos) return;
        this.collapsed = true;
        this.icon.style.display = '';
        this._placeIcon();
    }

    private _iconButton(title: string, label: string,
                        run: () => void): HTMLButtonElement {
        const button = document.createElement('button');
        button.className = 'desk-pi-float-btn';
        button.textContent = label;
        button.title = title;
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            run();
        });
        return button;
    }
}

/**
 * PiChat —— PI 会话的对话页（v1.3.7-20），对齐 `Pi-Agent-Web-main` 的
 * `ChatWindow` / `MessageView` / `ChatMinimap` / `ChatInput`（**纯 TS，零 npm**）：
 *
 *   ┌────────────────────────────── ↑2k ↓58 <$0.01  3% / 1.0M ┐ 顶栏只用右侧
 *   │ 我：看看这个指标…                                    │
 *   │ deepseek-flash  ↓412 · 12.3 t/s                      │      ┌ 节点导航
 *   │ ▸ 思考                                            3s │      │ ● 用户
 *   │ ▾ bash  sed -n 1455,1500p …                       3s │      │ ○ 回答
 *   │     参数 / 输出（收起可点开）                          │      │ ● …
 *   │ 已修复。根因是…（markdown，代码块带「复制」）            │      │
 *   │ 输入 41,068 · 输出 457 · 缓存 2,560 · $0.0129 ⧉ 复制   │      └
 *   ├──────────────────────────────────────────────────────┤
 *   │ [输入消息…]（右键 = 粘贴剪贴板）              → 发送   │
 *   │ @文件  模型 ▾  强度 ▾  权限 ▾  压缩  🎤(置灰)          │
 *   └──────────────────────────────────────────────────────┘
 */
import { showMenuBelow, type MenuItem } from './menu';
import { esc } from './pi-util';

export interface PiChatOptions {
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
    /** 编辑器当前文件（`@文件` 按钮 / 引用用 ✓） */
    context?: () => { path?: string; code?: string };
}

export interface PiModelsState {
    active?: { provider?: string; model?: string };
    providers?: Array<Record<string, unknown>>;
    models?: Record<string, unknown>;
}

/** 单次调用的用量（服务端回的 usage，缺了就本地粗估 ✓） */
interface PiUsage {
    prompt?: number;
    completion?: number;
    cached?: number;
    cost?: number;
    total?: number;
}

/** 一次工具调用（参数 / 结果 / 耗时 ✓） */
interface PiTool {
    name: string;
    args?: string;
    content?: string;
    elapsed?: number;
}

/** 一条附件（图片带 dataURL / 文本带内容 ✓） */
export interface PiAttachment {
    name: string;
    mime: string;
    kind: 'image' | 'text';
    /** 图片：dataURL；文本：不填（用 `text`） */
    data?: string;
    /** 文本附件内容（后端直接拼进 prompt） */
    text?: string;
    size?: number;
}

/** 附件上限（和后端 `MAX_ATTACHMENTS` 对齐 ✓） */
export const MAX_ATTACHMENTS = 4;
export const MAX_ATTACH_BYTES = 4 * 1024 * 1024;

interface PiMessage {
    role: string;
    content: string;
    /** 用户消息带的附件（图片缩略图 / 文件名 ✓） */
    attachments?: PiAttachment[];
    index?: number;
    /** 思考过程（模型原始输出，默认收起 ✓） */
    thinking?: string;
    /** 这一轮的用量（输入 / 输出 / 缓存 / 金额 ✓） */
    usage?: PiUsage;
    model?: string;
    /** 这一轮生成用了多少秒（思考块右侧显示 ✓） */
    seconds?: number;
    tools?: PiTool[];
    /** 历史里的工具行（后端单独存一条 `role: 'tool'` ✓） */
    name?: string;
    args?: string;
    elapsed?: number;
}

const EFFORTS = [
    { value: 'low', label: 'low' },
    { value: 'medium', label: 'medium' },
    { value: 'high', label: 'high' },
];
const PERMISSIONS = [
    // 和 pi-agent-studio 的 `permission.mode = FullAccess` 一致：
    // 完全访问 = 所有工具都放行（含操控 desk）、**从不询问** ✓
    { value: 'full', label: '完全访问（不询问）' },
    // ★ v1.3.7-24：能改界面（切合约 / 加指标 / 布局），但不动钱 ✓
    { value: 'desk', label: '操控 desk（会点按钮）' },
    { value: 'default', label: '默认（只改代码）' },
    { value: 'readonly', label: '只读' },
];

/** 复制到剪贴板：优先**后端**系统剪贴板（QtWebEngine 里浏览器 API 常失败 ✗） */
function copyText(text: string, send?: (cmd: string,
                                        payload?: unknown) => void): Promise<void> {
    if (send) {
        // 后端 `clipboard_set` 用 QApplication.clipboard() / tkinter → 稳 ✓
        send('clipboard_set', { text });
        return Promise.resolve();
    }
    const clipboard = navigator.clipboard;
    if (clipboard && typeof clipboard.writeText === 'function') {
        return clipboard.writeText(text).catch(() => fallbackCopy(text));
    }
    return Promise.resolve(fallbackCopy(text));
}

function fallbackCopy(text: string): void {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
    document.body.appendChild(area);
    area.select();
    try {
        document.execCommand('copy');
    } catch {
        /* 复制不了就算了（不弹窗打扰 ✓） */
    } finally {
        area.remove();
    }
}

function fmtNum(value: number): string {
    const number = Math.round(Number(value) || 0);
    return number.toLocaleString('en-US');
}

function fmtCost(value: number): string {
    const cost = Number(value) || 0;
    if (!cost) return '$0';
    return `$${cost.toFixed(cost < 0.1 ? 4 : 3)}`;
}

function fmtSeconds(value: number): string {
    const seconds = Number(value) || 0;
    if (!seconds) return '';
    return seconds >= 60 ? `${(seconds / 60).toFixed(1)}m`
        : `${Math.round(seconds * 10) / 10}s`;
}

/** `输入 1,234 · 输出 56 · 缓存 78 · $0.0012`（对齐 pi 的 `formatUsage` ✓） */
function usageText(usage: PiUsage | undefined): string {
    const parts: string[] = [];
    const data = usage || {};
    if (data.prompt) parts.push(`输入 ${fmtNum(data.prompt)}`);
    if (data.completion) parts.push(`输出 ${fmtNum(data.completion)}`);
    if (data.cached) parts.push(`缓存 ${fmtNum(data.cached)}`);
    if (data.cost) parts.push(fmtCost(data.cost));
    return parts.join(' · ');
}

/** 工具卡标题里的预览：命令 / 路径 / 正则（对齐 pi 的 `getToolPreview` ✓） */
function toolPreview(tool: PiTool): string {
    const raw = String(tool.args || '');
    let args: Record<string, unknown> = {};
    try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
            args = parsed as Record<string, unknown>;
        }
    } catch {
        return raw.replace(/\s+/g, ' ').slice(0, 120);
    }
    for (const key of ['command', 'path', 'file_path', 'pattern', 'query']) {
        if (key in args) return String(args[key] ?? '').slice(0, 160);
    }
    const first = Object.values(args)[0];
    return first === undefined ? '' : String(first).slice(0, 120);
}

/** 表格分隔行：`|---|:--:|` */
export function isTableDivider(line: string | undefined): boolean {
    const text = String(line || '').trim();
    if (!text || !text.includes('-')) return false;
    const cells = splitTableRow(text);
    return cells.length > 0
        && cells.every((cell) => /^:?-{2,}:?$/.test(cell));
}

/** 把 `| a | b |` 拆成单元格（去掉首尾竖线；`\|` 当普通字符） */
export function splitTableRow(line: string): string[] {
    let text = String(line || '').trim();
    if (!text.includes('|')) return [];
    text = text.replace(/^\|/, '').replace(/\|$/, '');
    return text.split('|').map((cell) => cell.trim());
}

/** 分隔行 → 每列对齐（`:--` 左、`--:` 右、`:-:`` 居中） */
export function tableAligns(line: string | undefined): string[] {
    return splitTableRow(line || '').map((cell) => {
        const left = cell.startsWith(':');
        const right = cell.endsWith(':');
        if (left && right) return 'center';
        if (right) return 'right';
        return left ? 'left' : '';
    });
}

/** 画表格（列多时外层横向滚动；单元格支持行内格式 ✓） */
export function renderPiTable(header: string[], rows: string[][],
                              aligns: string[] = [],
                              raw = false): string {
    const cols = Math.max(header.length, ...rows.map((row) => row.length), 1);
    const cell = (tag: string, text: string, index: number) => {
        const align = aligns[index] || '';
        const style = align ? ` style="text-align:${align}"` : '';
        // `raw=true`：调用方已经做过行内格式化 + 转义（`markdownInline`）✓
        return `<${tag}${style}>${raw ? String(text ?? '')
            : esc(text ?? '')}</${tag}>`;
    };
    const head = header.length
        ? '<thead><tr>'
          + Array.from({ length: cols }, (_, index) =>
              cell('th', header[index] ?? '', index)).join('')
          + '</tr></thead>'
        : '';
    const body = rows.length
        ? '<tbody>' + rows.map((row) => '<tr>'
            + Array.from({ length: cols }, (_, index) =>
                cell('td', row[index] ?? '', index)).join('')
            + '</tr>').join('') + '</tbody>'
        : '';
    return `<div class="desk-pi-table-wrap"><table class="desk-pi-table">${
        head}${body}</table></div>`;
}

/** 行内格式：`**粗**` / 反引号代码（先转义 ✓） */
export function piInline(text: string): string {
    return esc(text)
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
}

/** 按行画：标题 / 列表 / 表格 / 段落 ✓ */
export function piMarkdownText(chunk: string): string {
    const lines = String(chunk || '').replace(/\r\n?/g, '\n').split('\n');
    const out: string[] = [];
    let paragraph: string[] = [];
    let items: string[] = [];
    const flushParagraph = () => {
        if (!paragraph.length) return;
        out.push(`<p>${paragraph.join('<br>')}</p>`);
        paragraph = [];
    };
    const flushList = () => {
        if (!items.length) return;
        out.push(`<ul>${items.map((item) => `<li>${item}</li>`).join('')}`
            + '</ul>');
        items = [];
    };
    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index].trim();
        if (!line) {
            flushParagraph();
            flushList();
            continue;
        }
        // ★ 表格（GFM）：`| a | b |` + `|---|---|` → `<table>` ✓
        if (/^\|.*\|$/.test(line) && isTableDivider(lines[index + 1])) {
            const header = splitTableRow(line);
            const aligns = tableAligns(lines[index + 1]);
            const rows: string[][] = [];
            let cursor = index + 2;
            while (cursor < lines.length
                    && /^\|.*\|$/.test(lines[cursor].trim())) {
                const cells = splitTableRow(lines[cursor]);
                if (cells.length) rows.push(cells);
                cursor += 1;
            }
            flushParagraph();
            flushList();
            // `piInline` 已经转义 + 加了 `<b>/<code>` → raw=true（别二次转义 ✓）
            out.push(renderPiTable(header.map((text) => piInline(text)),
                                   rows.map((row) => row.map(
                                       (text) => piInline(text))),
                                   aligns, true));
            index = cursor - 1;
            continue;
        }
        const bullet = /^[-*+]\s+(.*)$/.exec(line);
        if (bullet) {
            flushParagraph();
            items.push(piInline(bullet[1]));
            continue;
        }
        const ordered = /^\d+[.)]\s+(.*)$/.exec(line);
        if (ordered) {
            flushParagraph();
            items.push(piInline(ordered[1]));
            continue;
        }
        const heading = /^(#{1,4})\s+(.*)$/.exec(line);
        if (heading) {
            flushParagraph();
            flushList();
            const level = Math.min(5, heading[1].length + 2);
            out.push(`<h${level}>${piInline(heading[2])}</h${level}>`);
            continue;
        }
        flushList();
        paragraph.push(piInline(line));
    }
    flushParagraph();
    flushList();
    return out.join('');
}

/** 完整 Markdown → HTML（代码块带「复制」按钮 / 表格 / 列表 ✓） */
export function markdownToHtml(source: string): string {
    const blocks = String(source || '').split('```');
    const out: string[] = [];
    blocks.forEach((chunk, index) => {
        if (index % 2 === 1) {
            const lines = chunk.split('\n');
            let lang = (lines[0] || '').trim();
            if (/^[A-Za-z0-9+#._-]*$/.test(lang)) lines.shift();
            else lang = '';
            const code = lines.join('\n').replace(/\n$/, '');
            out.push('<div class="desk-pi-code-wrap">'
                + `<div class="desk-pi-code-head"><span>${
                    esc(lang || 'code')}</span>`
                + '<button class="desk-pi-link" data-pi-copy="1">复制</button>'
                + '</div>'
                + `<pre class="desk-pi-code"><code>${esc(code)}</code></pre>`
                + '</div>');
            return;
        }
        out.push(piMarkdownText(chunk));
    });
    return out.join('');
}

export class PiChat {
    readonly element: HTMLDivElement;
    readonly sessionId: string;
    private readonly options: PiChatOptions;
    private readonly meter: HTMLDivElement;
    private readonly log: HTMLDivElement;
    private readonly nav: HTMLDivElement;
    private readonly jump: HTMLButtonElement;
    private readonly input: HTMLTextAreaElement;
    private readonly status: HTMLDivElement;
    private readonly chips: HTMLDivElement;
    private readonly titleEl: HTMLSpanElement;
    private messages: PiMessage[] = [];
    private title = '新会话';
    private model = '';
    private effort = 'medium';
    private permission = 'full';
    private compress = false;
    private streaming = false;
    private usage: Record<string, unknown> = {};
    private contextTokens = 0;
    private windowTokens = 0;
    private providers: Array<Record<string, unknown>> = [];
    private modelsData: Record<string, unknown> = {};
    private refs = new Set<string>();
    /** 待发送的附件（图片 / 文本；发出去就清空 ✓） */
    private attachments: PiAttachment[] = [];
    /** 附件条（输入框上方）✓ */
    private attachBar: HTMLDivElement | null = null;
    private fileInput: HTMLInputElement | null = null;
    private readonly files: HTMLDivElement;
    private fileTimer: number | undefined;
    /** 流式中的这一轮（对齐 pi 的 assistant 消息 ✓） */
    private live: PiMessage | null = null;
    /** 流式中那一轮的 DOM（新开一轮时清空 → 不会画错元素 ✓） */
    private liveEl: HTMLElement | null = null;
    /** 这一轮的工具已经跑完 → 下一次 delta 要新开一轮 ✓ */
    private roundClosed = true;
    private liveTool: PiTool | null = null;
    private startedAt = 0;
    /** 用户在往上翻 → 不自动滚到底部 ✓ */
    private follow = true;
    /** 右键粘贴时的光标位置（等后端剪贴板回来 ✓） */
    private pasteAt: { start: number; end: number } | null = null;
    /** 发过的消息（↑↓ 翻历史；对齐终端 / REPL ✓） */
    private readonly history: string[] = [];
    private historyAt = -1;
    private navTimer: number | undefined;

    constructor(sessionId: string, options: PiChatOptions) {
        this.sessionId = String(sessionId);
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-pi-chat';

        // 顶栏：**只保留右侧**的上行/下行/花费/上下文（按用户要求 ✓）
        const head = document.createElement('div');
        head.className = 'desk-pi-chat-head';
        this.titleEl = document.createElement('span');
        this.titleEl.className = 'desk-pi-chat-title';
        this.titleEl.textContent = '新会话';
        this.meter = document.createElement('div');
        this.meter.className = 'desk-pi-meter';
        head.append(this.titleEl, this.meter);

        const body = document.createElement('div');
        body.className = 'desk-pi-body';
        this.log = document.createElement('div');
        this.log.className = 'desk-pi-log';
        this.nav = document.createElement('div');
        this.nav.className = 'desk-pi-nav';
        // ★ v1.3.7-106：原生 title 关掉 —— 悬停时本来就会浮出
        //   `.desk-pi-nav-label`，两个提示叠在一起 ✗（用户实测）
        this.nav.setAttribute('aria-label', '对话节点导航（点一下跳过去）');
        body.append(this.log, this.nav);

        this.jump = document.createElement('button');
        this.jump.className = 'desk-pi-jump';
        this.jump.textContent = '↓ 回到底部';
        this.jump.style.display = 'none';
        this.jump.addEventListener('click', () => {
            this.follow = true;
            this.scrollToEnd();
        });
        body.appendChild(this.jump);

        this.files = document.createElement('div');
        this.files.className = 'desk-pi-files';
        this.files.style.display = 'none';

        const composer = document.createElement('div');
        composer.className = 'desk-pi-composer';
        this.input = document.createElement('textarea');
        this.input.className = 'desk-pi-input';
        this.input.placeholder = '输入消息…（Enter 发送 / Shift+Enter 换行'
            + ' / 右键粘贴 ✓）';
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.send();
            } else if (event.key === 'ArrowUp') {
                // ★ 单行时 ↑ 翻上一条（用户 2026-11-08 要求 ✓）
                if (this.history.length) {
                    event.preventDefault();
                    this.historyAt = Math.min(this.history.length - 1,
                        this.historyAt + 1);
                    this.input.value = this.history[
                        this.history.length - 1 - this.historyAt] || '';
                    this.input.selectionStart = this.input.value.length;
                }
            } else if (event.key === 'ArrowDown') {
                if (this.historyAt >= 0) {
                    event.preventDefault();
                    this.historyAt = Math.max(-1, this.historyAt - 1);
                    this.input.value = this.historyAt < 0 ? ''
                        : (this.history[this.history.length - 1
                            - this.historyAt] || '');
                    this.input.selectionStart = this.input.value.length;
                }
            } else if (event.key === 'Escape') {
                this.files.style.display = 'none';
            }
        });
        this.input.addEventListener('input', () => this.onInput());
        // ★ 右键 = 把剪贴板内容粘进输入框（用户 2026-11-08 要求 ✓）
        //   QtWebEngine 里 `navigator.clipboard.readText()` 读不到 →
        //   让后端用系统剪贴板读（`pi_paste` 命令 ✓）
        this.input.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            this.requestPaste();
        });

        // ★ 附件条（图片缩略图 / 文件名 + ✕）：只在有附件时显示 ✓
        this.attachBar = document.createElement('div');
        this.attachBar.className = 'desk-pi-attach-bar';
        this.attachBar.style.display = 'none';

        const row = document.createElement('div');
        row.className = 'desk-pi-composer-row';
        this.chips = document.createElement('div');
        this.chips.className = 'desk-pi-chips';
        // 📎 上传附件（图片 / 代码 / 文本）—— file input 在 QtWebEngine 里可用 ✓
        const attachButton = document.createElement('button');
        attachButton.className = 'desk-pi-chip desk-pi-attach-btn';
        attachButton.textContent = '📎 附件';
        attachButton.title = '上传图片 / 代码 / 文本（也可直接粘贴或拖进来）';
        attachButton.addEventListener('click', () => this.pickAttachments());
        this.fileInput = document.createElement('input');
        this.fileInput.type = 'file';
        this.fileInput.multiple = true;
        this.fileInput.accept = 'image/*,.py,.md,.txt,.json,.csv,.log,.yml,'
            + '.yaml,.ts,.js,.html,.css,.sql,.sh';
        this.fileInput.style.display = 'none';
        this.fileInput.addEventListener('change', () => {
            const files = Array.from(this.fileInput?.files || []);
            this.addFiles(files);
            if (this.fileInput) this.fileInput.value = '';
        });
        const sendButton = document.createElement('button');
        sendButton.className = 'desk-pi-send';
        sendButton.textContent = '→ 发送';
        sendButton.addEventListener('click', () => this.send());
        row.append(attachButton, this.chips, sendButton);

        this.status = document.createElement('div');
        this.status.className = 'desk-pi-status';

        // 粘贴图片（Ctrl+V）/ 拖文件进来 ✓
        this.input.addEventListener('paste', (event) => {
            const items = Array.from(event.clipboardData?.items || []);
            const files = items
                .filter((item) => item.kind === 'file')
                .map((item) => item.getAsFile())
                .filter((file): file is File => !!file);
            if (files.length) {
                event.preventDefault();
                this.addFiles(files);
            }
        });
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

        composer.append(this.attachBar, this.input, row, this.status,
                        this.fileInput);
        this.element.append(head, body, this.files, composer);

        // 滚动：跟到底部 / 用户上翻就停（对齐 pi 的行为 ✓）
        this.log.addEventListener('scroll', () => {
            const distance = this.log.scrollHeight - this.log.scrollTop
                - this.log.clientHeight;
            this.follow = distance < 60;
            this.jump.style.display = this.follow ? 'none' : '';
            this.syncActiveNode();
        });

        // 代码块「复制」/ 工具卡开合都用事件委托（重渲染也不丢 ✓）
        this.log.addEventListener('click', (event) => {
            const target = event.target as HTMLElement | null;
            if (!target) return;
            const copy = target.closest('[data-pi-copy]') as HTMLElement | null;
            if (copy) {
                const holder = copy.closest('.desk-pi-code-wrap')
                    || copy.closest('.desk-pi-tool');
                const source = holder?.querySelector('pre');
                const text = source?.textContent || '';
                copyText(text, this._send).then(() => {
                    copy.textContent = '已复制';
                    window.setTimeout(() => {
                        copy.textContent = '复制';
                    }, 1500);
                });
                return;
            }
            const toggle = target.closest('.desk-pi-fold-head') as
                HTMLElement | null;
            if (toggle) {
                const box = toggle.parentElement;
                box?.classList.toggle('open');
            }
        });

        this.buildChips();
        this.renderMeter();
        this.render();
    }

    // ------------------------------------------------------------- 数据
    bind(session: Record<string, unknown>): void {
        this.title = String(session.title || session.name || '新会话');
        this.titleEl.textContent = this.title;
        const options = (session.options || {}) as Record<string, unknown>;
        this.effort = String(options.effort || 'medium');
        this.permission = String(options.permission || 'full');
        this.compress = options.compress === true;
        this.model = String(options.model || this.model || '');
        this.messages = ((session.messages || []) as PiMessage[])
            .filter((item) => item && item.role !== 'system');
        this.usage = (session.usage || {}) as Record<string, unknown>;
        this.contextTokens = Number(session.context || 0);
        this.windowTokens = Number(session.window || 0);
        this.live = null;
        this.liveEl = null;
        this.liveTool = null;
        this.roundClosed = true;
        this.streaming = false;
        this.buildChips();
        this.render();
        this.follow = true;
        this.scrollToEnd();
    }

    setModels(state: PiModelsState): void {
        this.providers = (state.providers || []) as Array<Record<string, unknown>>;
        this.modelsData = (state.models || {}) as Record<string, unknown>;
        const active = (state.active || {}) as Record<string, unknown>;
        if (!this.model) this.model = String(active.model || '');
        this.buildChips();
    }

    event(patch: Record<string, unknown>): void {
        if (String(patch.id || '') !== this.sessionId) return;
        const kind = String(patch.event || '');
        const text = String(patch.text || '');
        if (kind === 'start') {
            this.streaming = true;
            this.follow = true;
            this.live = null;
            this.liveEl = null;
            this.liveTool = null;
            this.roundClosed = true;
            this.startedAt = Date.now();
            if (patch.model) this.model = String(patch.model);
            const options = (patch.options || {}) as Record<string, unknown>;
            if (options.effort) this.effort = String(options.effort);
            if (options.permission) this.permission = String(options.permission);
            this.buildChips();
            this.render();
            return;
        }
        if (kind === 'user') {
            const attached = Array.isArray(patch.attachments)
                ? (patch.attachments as PiAttachment[]) : undefined;
            this.messages.push({ role: 'user', content: text,
                                 attachments: attached });
            this.live = null;
            this.roundClosed = true;
            this.render();
            this.scrollToEnd();
            return;
        }
        if (kind === 'thinking') {
            const round = this.ensureRound();
            round.thinking = (round.thinking || '') + text;
            this.refreshLive();
            return;
        }
        if (kind === 'delta') {
            const round = this.ensureRound();
            round.content += text;
            this.refreshLive();
            return;
        }
        if (kind === 'assistant') {
            if (this.live && !this.roundClosed) {
                this.live.content = text || this.live.content;
                this.refreshLive();
            } else {
                this.messages.push({ role: 'assistant', content: text,
                                     model: this.model, tools: [] });
                this.render();
                this.scrollToEnd();
            }
            return;
        }
        if (kind === 'tool') {
            const round = this.ensureRound();
            const tool: PiTool = { name: String(patch.name || ''),
                                   args: JSON.stringify(patch.args || {}) };
            round.tools = [...(round.tools || []), tool];
            this.liveTool = tool;
            this.refreshLive();
            return;
        }
        if (kind === 'tool_result') {
            const tool = this.liveTool || this.lastPendingTool();
            if (tool) {
                tool.content = text;
                tool.elapsed = Number(patch.elapsed || 0);
            }
            this.liveTool = null;
            this.roundClosed = true;          // 下一次 delta 就是新一轮 ✓
            this.refreshLive();
            return;
        }
        if (kind === 'usage') {
            this.usage = (patch.usage || {}) as Record<string, unknown>;
            this.contextTokens = Number(patch.context || this.contextTokens);
            this.windowTokens = Number(patch.window || this.windowTokens);
            const round = this.lastRound();
            const roundUsage = patch.round as PiUsage | undefined;
            if (round && roundUsage && typeof roundUsage === 'object') {
                round.usage = roundUsage;
            }
            this.renderMeter();
            this.refreshLive();
            return;
        }
        if (kind === 'appended') {
            // 执行中追加成功：本轮下一步就会带上（不用等结束 ✓）
            this.status.textContent = String(patch.text
                || '已追加：模型下一步就会看到这句');
            return;
        }
        if (kind === 'queued') {
            // 上一轮还没跑完 → 后端排队了；提示一下，别让用户以为丢了 ✓
            this.status.textContent = String(patch.text
                || '正在执行：已排队，本轮结束后自动发送');
            return;
        }
        if (kind === 'context_warn' || kind === 'trimmed'
            || kind === 'compressed') {
            this.status.textContent = kind === 'context_warn'
                ? `上下文已用 ${Number(patch.percent || 0).toFixed(0)}%`
                : (kind === 'trimmed'
                    ? `已裁剪 ${Number(patch.dropped || 0)} 条更早消息`
                    : '已压缩更早的对话');
            return;
        }
        if (kind === 'error') {
            this.streaming = false;
            this.live = null;
            this.liveEl = null;
            this.roundClosed = true;
            this.messages.push({ role: 'assistant',
                                 content: `⚠ ${String(patch.error || '出错了')}`,
                                 model: this.model, tools: [] });
            this.render();
            this.scrollToEnd();
            return;
        }
        if (kind === 'done' || kind === 'stopped') {
            this.streaming = false;
            this.live = null;
            this.liveEl = null;
            this.liveTool = null;
            this.roundClosed = true;
            const note = String(patch.note || '');
            if (note) {
                const last = this.messages[this.messages.length - 1];
                if (!(last && last.role === 'assistant'
                    && String(last.content || '').includes(note))) {
                    this.messages.push({ role: 'assistant', content: note,
                                         model: this.model, tools: [] });
                }
            }
            this.status.textContent = '';
            this.render();
            this.scrollToEnd();
            return;
        }
        this.render();
    }

    focus(): void {
        this.input.focus();
    }

    /** 「发给 AI」：把代码 / 文件地址插进输入框（不自动发送 ✓） */
    appendToInput(text: string): void {
        const block = String(text || '').trim();
        if (!block) return;
        const value = this.input.value.replace(/\s+$/, '');
        this.input.value = value ? value + '\n' + '\n' + block : block;
        const end = this.input.value.length;
        this.input.selectionStart = end;
        this.input.selectionEnd = end;
        this.input.focus();
        this.onInput();
        this.status.textContent = '已插入代码，按 Enter 发送';
    }

    /** 后端 `ai_files` 结果 → 下拉（点一下插入 `@路径` ✓） */
    setFiles(items: Array<Record<string, unknown>>): void {
        this.files.textContent = '';
        if (!items.length) {
            this.files.style.display = 'none';
            return;
        }
        for (const item of items.slice(0, 30)) {
            const path = String(item.path || '');
            const button = document.createElement('button');
            button.className = 'desk-pi-file';
            button.textContent = path;
            button.addEventListener('mousedown', (event) => {
                event.preventDefault();
                const value = this.input.value;
                const caret = this.input.selectionStart ?? value.length;
                const head = value.slice(0, caret).replace(
                    /(^|\s)@[\w./-]*$/, `$1@${path} `);
                this.input.value = head + value.slice(caret);
                this.refs.add(path);
                this.files.style.display = 'none';
                this.input.focus();
            });
            this.files.appendChild(button);
        }
        this.files.style.display = '';
    }

    // ------------------------------------------------------- 流式轮次管理
    /** 拿到「当前这一轮」；上一轮已经收尾就新开一轮 ✓ */
    private ensureRound(): PiMessage {
        if (this.live && !this.roundClosed) return this.live;
        const round: PiMessage = { role: 'assistant', content: '',
                                   thinking: '', model: this.model,
                                   tools: [] };
        this.messages.push(round);
        this.live = round;
        this.liveEl = null;
        this.roundClosed = false;
        this.render();          // 新开一轮 → 重画（拿到新的 live 元素 ✓）
        return round;
    }

    private lastRound(): PiMessage | null {
        for (let index = this.messages.length - 1; index >= 0; index -= 1) {
            if (this.messages[index].role === 'assistant') {
                return this.messages[index];
            }
        }
        return null;
    }

    private lastPendingTool(): PiTool | null {
        const round = this.lastRound();
        const tools = round?.tools || [];
        for (let index = tools.length - 1; index >= 0; index -= 1) {
            if (tools[index].content === undefined) return tools[index];
        }
        return null;
    }

    // ------------------------------------------------------------- 渲染
    private buildChips(): void {
        if (!this.chips) return;
        this.chips.textContent = '';
        const chip = (label: string, title: string, run: () => void,
                      disabled = false) => {
            const button = document.createElement('button');
            button.className = 'desk-pi-chip';
            button.textContent = label;
            button.title = title;
            button.disabled = disabled;
            button.addEventListener('click', run);
            this.chips.appendChild(button);
            return button;
        };
        chip('@', '引用当前文件（@文件）', () => this.attachFile());
        chip(`模型：${this.model || '未选择'}`, '选择模型 / 供应商', () =>
            this.pickModel());
        chip(`强度：${this.effort}`, '推理强度', () => {
            showMenuBelow(this._anchor(), EFFORTS.map((item) => ({
                label: item.label,
                run: () => {
                    this.effort = item.value;
                    this.buildChips();
                },
            })));
        });
        chip(`权限：${PERMISSIONS.find((item) => item.value === this.permission)
            ?.label || '完全访问（不询问）'}`,
            '工具权限：完全访问 = 不询问（等同 pi 的 FullAccess）', () => {
            showMenuBelow(this._anchor(), PERMISSIONS.map((item) => ({
                label: item.label,
                run: () => {
                    this.permission = item.value;
                    this.buildChips();
                },
            })));
        });
        chip(`压缩${this.compress ? '：开' : '：关'}`,
            '上下文接近上限时自动压缩旧对话', () => {
                this.compress = !this.compress;
                this.buildChips();
            });
        // 麦克风：浏览器语音需要额外服务 → 置灰（用户要求 ✓）
        chip('🎤', '语音输入（本机未启用）', () => undefined, true);
    }

    private pickModel(): void {
        const items: MenuItem[] = [];
        const providers = this.providers || [];
        const saved = (this.modelsData.providers || {}) as Record<
            string, Record<string, unknown>>;
        for (const provider of providers) {
            const id = String(provider.id || '');
            const label = String(provider.label || id);
            const record = saved[id] || {};
            const models = (record.models as string[] | undefined)
                || (provider.models as string[] | undefined) || [];
            const configured = !!record.apiKey
                || provider.kind === 'local' || provider.configured === true;
            items.push({
                label: `${label}${configured ? '' : '（未配置 Key）'}`,
                disabled: !models.length,
                run: () => {
                    if (!models.length) {
                        this.options.onCommand('pi_models', {});
                        this.options.onToast?.('info',
                            '这个供应商还没有模型：点左下「模型」添加');
                        return;
                    }
                    showMenuBelow(this._anchor(), models.slice(0, 40).map(
                        (model) => ({
                            label: model,
                            run: () => {
                                this.model = model;
                                this.buildChips();
                                this.options.onCommand('pi_model_select', {
                                    provider: id, model,
                                });
                            },
                        })));
                },
            });
        }
        items.push({ label: '', separator: true });
        items.push({ label: '管理供应商 / API Key…', run: () =>
            this.options.onCommand('pi_models', {}) });
        showMenuBelow(this._anchor(), items);
    }

    /** 整体重画（打开会话 / 新增用户消息 / 结束时 ✓） */
    private render(): void {
        this.log.textContent = '';
        if (!this.messages.length) {
            // ★ 新会话先显示「初始化界面」（同一套欢迎样式，标题 + 建议 ✓）
            const empty = document.createElement('div');
            empty.className = 'desk-pi-empty desk-pi-welcome-inline';
            const title = document.createElement('div');
            title.className = 'desk-pi-welcome-title';
            title.innerHTML = 'PI 助手'
                + '<span class="desk-pi-welcome-sub">用简单的话讲清楚。'
                + '</span>';
            const hint = document.createElement('div');
            hint.className = 'desk-pi-welcome-hint';
            hint.textContent = '直接说需求：读代码 / 改文件 / 跑命令 / 查指标；'
                + 'Enter 发送，Shift+Enter 换行。';
            const chips = document.createElement('div');
            chips.className = 'desk-pi-welcome-suggestions';
            for (const text of ['读一下这个文件，指出问题',
                                '帮我改一个指标',
                                '跑一下测试']) {
                const chip = document.createElement('button');
                chip.className = 'desk-pi-welcome-chip';
                chip.textContent = text;
                chip.addEventListener('click', () => {
                    this.input.value = text;
                    this.input.focus();
                });
                chips.appendChild(chip);
            }
            empty.append(title, hint, chips);
            this.log.appendChild(empty);
        }
        let blocks: HTMLElement | null = null;
        for (const message of this.messages) {
            if (message.role === 'user') {
                this.log.appendChild(this.userRow(message));
                blocks = null;
                continue;
            }
            if (message.role === 'tool') {
                // 历史里的工具结果（后端单独一行）→ 填进上一轮那张卡 ✓
                const filled = this.fillToolCard(blocks, {
                    name: message.name || 'tool',
                    args: String(message.args || ''),
                    content: message.content,
                    elapsed: Number(message.elapsed || 0),
                });
                if (!filled) {
                    const card = this.toolCard({
                        name: message.name || 'tool',
                        args: String(message.args || ''),
                        content: message.content,
                        elapsed: Number(message.elapsed || 0),
                    });
                    if (blocks) blocks.appendChild(card);
                    else this.log.appendChild(card);
                }
                continue;
            }
            const row = this.assistantRow(message);
            if (message === this.live) this.liveEl = row;
            blocks = row.querySelector('.desk-pi-blocks') as HTMLElement | null;
            this.log.appendChild(row);
        }
        if (this.streaming && !this.live) {
            const cursor = document.createElement('span');
            cursor.className = 'desk-pi-cursor';
            cursor.textContent = '▍';
            this.log.appendChild(cursor);
        }
        this.renderMeter();
        this.scheduleNav();
    }

    /** 流式更新：只重画「当前这一轮」+ 导航（不整屏闪 ✓） */
    private refreshLive(): void {
        const round = this.live;
        const el = this.liveEl;
        if (!round || !el || !el.isConnected) {
            this.render();
            this.scrollToEnd();
            return;
        }
        this.paintRound(el, round);
        this.scheduleNav();
        this.scrollToEnd();
    }

    private userRow(message: PiMessage): HTMLElement {
        const row = document.createElement('div');
        row.className = 'desk-pi-msg user';
        row.dataset.role = 'user';
        const bubble = document.createElement('div');
        bubble.className = 'desk-pi-bubble';
        bubble.textContent = message.content;
        row.appendChild(bubble);
        // ★ 附件：图片缩略图（点一下新窗口看大图）/ 文本文件名 ✓
        if (message.attachments && message.attachments.length) {
            const box = document.createElement('div');
            box.className = 'desk-pi-attach-list';
            for (const item of message.attachments) {
                const node = document.createElement('div');
                node.className = `desk-pi-attach-item ${item.kind}`;
                if (item.kind === 'image' && item.data) {
                    const img = document.createElement('img');
                    img.src = item.data;
                    img.alt = item.name;
                    img.title = item.name;
                    img.addEventListener('click', () => {
                        window.open(item.data || '', '_blank');
                    });
                    node.appendChild(img);
                }
                const name = document.createElement('span');
                name.textContent = item.name;
                node.appendChild(name);
                box.appendChild(node);
            }
            row.appendChild(box);
        }
        // 悬浮「复制」（对齐 pi ✓）
        const tools = document.createElement('div');
        tools.className = 'desk-pi-row-actions';
        const copy = document.createElement('button');
        copy.className = 'desk-pi-link';
        copy.textContent = '复制';
        copy.addEventListener('click', () => {
            copyText(message.content, this._send).then(() => {
                copy.textContent = '已复制';
                window.setTimeout(() => {
                    copy.textContent = '复制';
                }, 1500);
            });
        });
        tools.appendChild(copy);
        row.appendChild(tools);
        return row;
    }

    private assistantRow(message: PiMessage): HTMLElement {
        const row = document.createElement('div');
        row.className = 'desk-pi-round'
            + (message === this.live ? ' live' : '');
        row.dataset.role = 'assistant';
        this.paintRound(row, message);
        return row;
    }

    /** 画一轮：模型标签 → 思考卡 → 工具卡 → 正文 → 用量 + 复制 ✓ */
    private paintRound(row: HTMLElement, message: PiMessage): void {
        row.textContent = '';

        const meta = document.createElement('div');
        meta.className = 'desk-pi-msg-meta';
        const label = document.createElement('span');
        label.textContent = String(message.model || this.model || 'PI');
        meta.appendChild(label);
        if (message === this.live && this.streaming) {
            const chars = (message.content || '').length
                + (message.thinking || '').length;
            const est = Math.round(chars / 4);
            const seconds = (Date.now() - this.startedAt) / 1000;
            const tps = seconds >= 1 ? (chars / 4) / seconds : 0;
            const stats = document.createElement('span');
            stats.className = 'desk-pi-stream-stats';
            stats.textContent = est > 0 ? `↓${est}` : '';
            if (tps > 0) {
                const badge = document.createElement('i');
                badge.className = 'desk-pi-tps';
                badge.textContent = `${tps.toFixed(1)} t/s`;
                badge.dataset.tier = tps >= 50 ? 'fast'
                    : (tps >= 30 ? 'ok' : (tps >= 15 ? 'meh' : 'slow'));
                stats.appendChild(badge);
            }
            meta.appendChild(stats);
        }
        row.appendChild(meta);

        const blocks = document.createElement('div');
        blocks.className = 'desk-pi-blocks';
        row.appendChild(blocks);

        if (message.thinking) {
            blocks.appendChild(this.fold({
                title: '思考',
                seconds: message.seconds,
                text: message.thinking,
                kind: 'think',
                open: false,
            }));
        }
        if (message.content) {
            const body = document.createElement('div');
            body.className = 'desk-pi-msg-body';
            body.innerHTML = this.markdown(message.content);
            blocks.appendChild(body);
        }
        for (const tool of message.tools || []) {
            blocks.appendChild(this.toolCard(tool));
        }

        const usage = usageText(message.usage);
        if (usage || message.content) {
            const foot = document.createElement('div');
            foot.className = 'desk-pi-usage';
            if (usage) {
                const text = document.createElement('span');
                text.textContent = usage;
                foot.appendChild(text);
            }
            // ★ 结论下方**始终**有「复制」（用户 2026-11-08 要求 ✓）
            if (message.content) {
                const copy = document.createElement('button');
                copy.className = 'desk-pi-link desk-pi-copy-answer';
                copy.textContent = '复制';
                copy.title = '复制这条回答';
                copy.addEventListener('click', () => {
                    copyText(message.content, this._send).then(() => {
                        copy.textContent = '已复制';
                        window.setTimeout(() => {
                            copy.textContent = '复制';
                        }, 1500);
                    });
                });
                foot.appendChild(copy);
            }
            row.appendChild(foot);
        }
    }

    /** 思考 / 工具 共用的折叠块（默认收起，点标题展开 ✓） */
    private fold(options: { title: string; seconds?: number; text: string;
                            kind: string; open: boolean;
                            preview?: string; error?: boolean;
                            empty?: boolean }): HTMLElement {
        const box = document.createElement('div');
        box.className = `desk-pi-fold ${options.kind}`
            + (options.open ? ' open' : '')
            + (options.error ? ' error' : '');
        const head = document.createElement('button');
        head.className = 'desk-pi-fold-head';
        const name = document.createElement('span');
        name.className = 'desk-pi-fold-name';
        name.textContent = options.title;
        head.appendChild(name);
        if (options.preview) {
            const preview = document.createElement('span');
            preview.className = 'desk-pi-fold-preview';
            preview.textContent = options.preview;
            head.appendChild(preview);
        }
        if (options.seconds) {
            const seconds = document.createElement('span');
            seconds.className = 'desk-pi-fold-seconds';
            seconds.textContent = fmtSeconds(options.seconds);
            head.appendChild(seconds);
        }
        const arrow = document.createElement('span');
        arrow.className = 'desk-pi-fold-arrow';
        arrow.textContent = '▸';
        head.appendChild(arrow);
        const body = document.createElement('pre');
        body.className = 'desk-pi-fold-body';
        body.textContent = options.empty ? '（无输出）'
            : (options.text || '（执行中…）').slice(0, 20000);
        box.append(head, body);
        return box;
    }

    /** 把工具结果填进上一轮里同名、还没结果的卡片（历史上两者分开存 ✓） */
    private fillToolCard(blocks: HTMLElement | null,
                         tool: PiTool): boolean {
        if (!blocks) return false;
        const cards = Array.from(blocks.querySelectorAll('.desk-pi-fold.tool'));
        for (const card of cards) {
            if (card.getAttribute('data-pending') !== '1') continue;
            const name = card.getAttribute('data-tool') || '';
            if (name && tool.name && name !== tool.name) continue;
            card.replaceWith(this.toolCard(tool));
            return true;
        }
        return false;
    }

    private toolCard(tool: PiTool): HTMLElement {
        const running = tool.content === undefined;
        const text = String(tool.content || '');
        // 后端工具出错时返回「错误：…」/ traceback → 红卡 ✓
        const failed = !running && (/^错误[：:]/.test(text.trim())
            || text.includes('Traceback (most recent call last)'));
        const box = this.fold({
            title: String(tool.name || 'tool'),
            preview: toolPreview(tool),
            seconds: tool.elapsed,
            text: running ? '（执行中…）' : String(tool.content || ''),
            kind: 'tool',
            open: false,
            empty: !running && !text.trim(),
            error: failed,
        });
        box.classList.toggle('running', running);
        box.dataset.tool = String(tool.name || '');
        box.dataset.pending = running ? '1' : '0';
        // 参数也给它看一眼（开了「参数」→ 结果下面 ✓）
        if (tool.args) {
            const body = box.querySelector('.desk-pi-fold-body');
            if (body) {
                const args = document.createElement('div');
                args.className = 'desk-pi-tool-args';
                args.textContent = `参数：${tool.args}`;
                body.insertBefore(args, body.firstChild);
            }
        }
        const copy = document.createElement('button');
        copy.className = 'desk-pi-link desk-pi-tool-copy';
        copy.dataset.piCopy = '1';
        copy.textContent = '复制';
        box.querySelector('.desk-pi-fold-head')?.appendChild(copy);
        return box;
    }

    /** `↑2k ↓58 <$0.01  3% / 1.0M`（按用户要求：只保留这一段 ✓） */
    private renderMeter(): void {
        const fmt = (value: number) => (value >= 1000
            ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`
            : String(Math.round(value)));
        const prompt = Number(this.usage.prompt || 0);
        const completion = Number(this.usage.completion || 0);
        const cost = Number(this.usage.cost || 0);
        const percent = this.windowTokens
            ? (100 * this.contextTokens) / this.windowTokens : 0;
        const parts = [
            `↑${fmt(prompt)}`,
            `↓${fmt(completion)}`,
            fmtCost(cost),
            `${percent.toFixed(0)}%`,
        ];
        this.meter.textContent = parts.join('  ') + (this.windowTokens
            ? ` / ${fmt(this.windowTokens)}` : '');
        const bar = document.createElement('div');
        bar.className = 'desk-pi-meter-bar';
        const fill = document.createElement('i');
        fill.style.width = `${Math.min(100, Math.max(0, percent))}%`;
        bar.appendChild(fill);
        this.meter.appendChild(bar);
    }

    // ------------------------------------------------------- 节点导航（右侧）
    /** 节点 = 用户提问 + 有内容的回答（对齐 pi 的 `ChatMinimap` ✓） */
    private scheduleNav(): void {
        if (this.navTimer !== undefined) window.clearTimeout(this.navTimer);
        this.navTimer = window.setTimeout(() => this.buildNav(), 60);
    }

    private buildNav(): void {
        this.nav.textContent = '';
        if (this.log.scrollHeight <= this.log.clientHeight + 24) return;
        const total = Math.max(1, this.log.scrollHeight);
        const rows = Array.from(this.log.children) as HTMLElement[];
        // ★ v1.3.7-107：导航提示要能看清"问了什么 / 答了什么" ——
        //   以前只截 36 个字，悬停根本看不出内容 ✗
        const QUESTION_CHARS = 90;
        const ANSWER_CHARS = 140;
        let question = '';
        for (const row of rows) {
            const role = row.dataset.role;
            if (role !== 'user' && role !== 'assistant') continue;
            let text = '';
            if (role === 'user') {
                text = (row.querySelector('.desk-pi-bubble')?.textContent || '');
            } else {
                text = row.querySelector('.desk-pi-msg-body')?.textContent || '';
            }
            const clean = text.replace(/\s+/g, ' ').trim();
            if (!clean) continue;
            if (role === 'user') question = clean;
            const node = document.createElement('button');
            node.className = `desk-pi-nav-node ${role}`;
            node.style.top = `${(row.offsetTop / total) * 100}%`;
            node.dataset.target = String(rows.indexOf(row));
            // 原生 title 会跟浮出的 label 重复 → 只在 aria-label 里留全文本 ✓
            node.removeAttribute('title');
            const preview = role === 'user'
                ? `问：${clean.slice(0, QUESTION_CHARS)}`
                : `问：${question.slice(0, QUESTION_CHARS)}` + ' ' +
                  `答：${clean.slice(0, ANSWER_CHARS)}`;
            node.setAttribute('aria-label', preview.slice(0, 260));
            const dot = document.createElement('i');
            const label = document.createElement('span');
            label.className = 'desk-pi-nav-label';
            if (role === 'user') {
                label.textContent = preview;
            } else {
                // 答的节点：上行"问"、下行"答"（两行更好读 ✓）
                const ask = document.createElement('span');
                ask.className = 'q';
                ask.textContent = `问：${question.slice(0, QUESTION_CHARS)}`;
                const answer = document.createElement('span');
                answer.className = 'a';
                answer.textContent = `答：${clean.slice(0, ANSWER_CHARS)}`;
                label.append(ask, answer);
            }
            node.append(dot, label);
            node.addEventListener('click', () => {
                this.follow = false;
                row.scrollIntoView({ block: 'start', behavior: 'smooth' });
            });
            this.nav.appendChild(node);
        }
        this.syncActiveNode();
    }

    /** 滚动时高亮「当前读到的节点」✓ */
    private syncActiveNode(): void {
        const nodes = Array.from(this.nav.children) as HTMLElement[];
        if (!nodes.length) return;
        const rows = Array.from(this.log.children) as HTMLElement[];
        const probe = this.log.scrollTop + this.log.clientHeight * 0.3;
        let active = -1;
        for (const node of nodes) {
            const row = rows[Number(node.dataset.target || 0)];
            if (row && row.offsetTop <= probe) active = Number(node.dataset.target);
        }
        for (const node of nodes) {
            node.classList.toggle('on',
                Number(node.dataset.target || 0) === active);
        }
    }

    // ------------------------------------------------------------- 滚动
    private scrollToEnd(): void {
        if (!this.follow) return;
        this.log.scrollTop = this.log.scrollHeight;
        this.syncActiveNode();
    }

    // ------------------------------------------------------------- markdown
    /** Markdown → HTML（**含表格**；悬浮窗 / 对话页共用同一套 ✓ v1.3.7-105） */
    private markdown(source: string): string {
        return markdownToHtml(source);
    }

    // ------------------------------------------------------------- 附件
    /** 打开系统选文件框（QtWebEngine 支持原生 file dialog ✓） */
    pickAttachments(): void {
        this.fileInput?.click();
    }

    /** 读文件 → 附件列表（图片 dataURL / 文本内容；超限直接提示 ✓） */
    addFiles(files: File[]): void {
        for (const file of files) {
            if (this.attachments.length >= MAX_ATTACHMENTS) {
                this.options.onToast?.('warning',
                    `最多 ${MAX_ATTACHMENTS} 个附件`);
                break;
            }
            if (file.size > MAX_ATTACH_BYTES) {
                this.options.onToast?.(
                    'warning', `${file.name} 超过 4MB，已跳过`);
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
                this.renderAttachBar();
            };
            reader.onerror = () => this.options.onToast?.(
                'warning', `读取 ${file.name} 失败`);
            if (isImage) reader.readAsDataURL(file);
            else reader.readAsText(file);
        }
    }

    /** 附件条：缩略图 / 文件名 + ✕ ✓ */
    private renderAttachBar(): void {
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
            label.title = `${item.name} · ${Math.max(1, Math.round(
                Number(item.size || 0) / 1024))}KB`;
            box.appendChild(label);
            const remove = document.createElement('button');
            remove.className = 'desk-pi-attach-x';
            remove.textContent = '✕';
            remove.title = '移除这个附件';
            remove.addEventListener('click', () => {
                this.attachments.splice(index, 1);
                this.renderAttachBar();
            });
            box.appendChild(remove);
            this.attachBar?.appendChild(box);
        });
    }

    /** 发出去之后清空附件（图在消息气泡里继续显示 ✓） */
    private clearAttachments(): void {
        this.attachments = [];
        this.renderAttachBar();
    }

    // ------------------------------------------------------------- 动作
    private send(): void {
        const text = this.input.value.trim();
        const attachments = this.attachments.map((item) => ({ ...item }));
        // ★ 只有附件、没有文字也能发（后端会用「（请看附件）」占位 ✓）
        if (!text && !attachments.length) return;
        this.history.push(text || '（请看附件）');
        if (this.history.length > 100) this.history.shift();
        this.historyAt = -1;
        const refs = [...this.refs].filter((ref) => text.includes(`@${ref}`));
        this.input.value = '';
        this.refs.clear();
        this.clearAttachments();
        this.streaming = true;
        this.follow = true;
        this.options.onCommand('pi_send', {
            id: this.sessionId, text, refs,
            model: this.model, effort: this.effort,
            permission: this.permission, compress: this.compress,
            attachments: attachments.map((item) => ({
                name: item.name, mime: item.mime, kind: item.kind,
                data: item.data, text: item.text, size: item.size,
            })),
        });
    }

    /** 统一的命令通道（复制 / 粘贴都走它 ✓） */
    private readonly _send = (cmd: string, payload?: unknown): void => {
        this.options.onCommand(cmd, payload);
    };

    /** 切到这个会话页时调用：滚到最新一条（用户 2026-11-08 要求 ✓） */
    scrollToBottom(): void {
        this.follow = true;
        this.jump.style.display = 'none';
        this.log.scrollTop = this.log.scrollHeight;
        this.syncActiveNode();
    }

    /** 程序化发一句话（初始化页 / 外部调用；不走输入框 ✓） */
    sendText(text: string): void {
        const value = String(text || '').trim();
        if (!value) return;
        this.input.value = value;
        this.send();
    }

    /** 右键粘贴第一步：记住光标位置 + 让后端把剪贴板读回来 ✓ */
    private requestPaste(): void {
        this.pasteAt = {
            start: this.input.selectionStart ?? this.input.value.length,
            end: this.input.selectionEnd ?? this.input.value.length,
        };
        this.status.textContent = '正在读取剪贴板…';
        this.options.onCommand('pi_paste', { id: this.sessionId });
        window.setTimeout(() => {
            if (this.pasteAt) this.status.textContent = '';
        }, 1500);
    }

    /** 右键粘贴第二步：后端回了剪贴板内容 → 插到刚才的光标处 ✓ */
    applyPaste(text: string, ok = true): void {
        this.pasteAt = null;
        this.status.textContent = '';
        if (!ok || !text) {
            // 后端也读不到（浏览器壳 / 剪贴板空）→ 再试浏览器 API
            const clipboard = navigator.clipboard;
            if (ok === false && clipboard
                && typeof clipboard.readText === 'function') {
                clipboard.readText().then((value) => {
                    if (value) this.insertText(value);
                    else this.options.onToast?.('warning',
                        '剪贴板是空的');
                }).catch(() => this.options.onToast?.('warning',
                    '读不到剪贴板：请用 Ctrl+V 粘贴'));
                return;
            }
            this.options.onToast?.('warning', '读不到剪贴板：请用 Ctrl+V 粘贴');
            return;
        }
        this.insertText(text);
    }

    /** 插到光标处（保留选区替换语义 ✓） */
    private insertText(text: string): void {
        const caret = this.pasteAt || {
            start: this.input.selectionStart ?? this.input.value.length,
            end: this.input.selectionEnd ?? this.input.value.length,
        };
        const value = this.input.value;
        this.input.value = value.slice(0, caret.start) + text
            + value.slice(caret.end);
        const next = caret.start + text.length;
        this.input.selectionStart = next;
        this.input.selectionEnd = next;
        this.input.focus();
        this.onInput();
    }

    private attachFile(): void {
        const context = this.options.context?.() || {};
        if (!context.path) {
            this.options.onToast?.('info', '编辑器里还没有打开的文件');
            return;
        }
        const name = String(context.path).split(/[\\/]/).pop() || 'file.py';
        this.refs.add(name);
        this.input.value += (this.input.value ? ' ' : '') + `@${name}`;
        this.options.onCommand('pi_attach', { path: context.path });
        this.input.focus();
    }

    private onInput(): void {
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

    private _anchor(): HTMLElement {
        const anchor = document.createElement('span');
        const box = this.element.getBoundingClientRect();
        anchor.style.cssText = `position:fixed;left:${box.left + 120}px;`
            + `top:${box.bottom - 120}px;width:0;height:0;`;
        document.body.appendChild(anchor);
        window.setTimeout(() => anchor.remove(), 0);
        return anchor;
    }
}

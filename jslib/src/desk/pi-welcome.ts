/**
 * PiWelcome —— PI 独立界面的**初始化页**（v1.3.7-38）
 *
 * 对齐 `Pi-Agent-Web-main` 的初始对话界面（`pi-web初始对话界面.png`）：
 *
 *   ┌──────────────────────────────────────────────────────────┐
 *   │                                                          │
 *   │  PI 助手   用简单的话讲清楚。  ▍          desk v1.3.7     │
 *   │                                          pi 1.3.7        │
 *   │  ┌────────────────────────────────────────────────────┐  │
 *   │  │ 输入消息…                                → 发送     │  │
 *   │  └────────────────────────────────────────────────────┘  │
 *   │  ▣ model ▾                ⚙ 自动   ⚖ 默认   ⇲ 压缩       │
 *   └──────────────────────────────────────────────────────────┘
 *
 * 它**不是一个页签**：独立界面没有任何会话时显示它；
 * 一发送就等于「新建一个会话」→ 初始化页消失、出现会话页签 ✓
 */
import { esc } from './pi-util';

export interface PiWelcomeOptions {
    theme: 'light' | 'dark';
    /** 版本信息（右侧小字）：desk = minibt 版本 */
    version?: string;
    /** pi（命令行）的版本 —— 以前误用了 minibt 的版本号 ✗ */
    piVersion?: string;
    /** 当前模型（左下角显示） */
    model?: string;
    /** 发送：调用方负责「新建会话 + 发送」 */
    onSend: (text: string) => void;
    /** 点左下角模型 → 打开模型对话框 */
    onModels?: () => void;
    /** 快捷建议（点一下填进输入框） */
    suggestions?: string[];
    /** 最近会话（点一下直接打开 ✓） */
    onOpenSession?: (id: string) => void;
    /** 落到输入框里的文件提示（浏览器拿不到真实路径时用 ✓） */
    onToast?: (level: string, text: string) => void;
}

export class PiWelcome {
    readonly element: HTMLDivElement;
    private readonly options: PiWelcomeOptions;
    private readonly input: HTMLTextAreaElement;
    private readonly modelChip: HTMLButtonElement;
    private readonly suggestions: HTMLDivElement;
    private readonly recent: HTMLDivElement;
    private readonly versions: HTMLDivElement;
    private deskVersion = '';
    private piVersion = '';

    constructor(options: PiWelcomeOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = `desk-pi-welcome theme-${options.theme}`;

        const head = document.createElement('div');
        head.className = 'desk-pi-welcome-head';
        const title = document.createElement('div');
        title.className = 'desk-pi-welcome-title';
        title.innerHTML = 'PI 助手'
            + '<span class="desk-pi-welcome-sub">用简单的话讲清楚。</span>'
            + '<i class="desk-pi-welcome-cursor">▍</i>';
        const versions = document.createElement('div');
        versions.className = 'desk-pi-welcome-versions';
        this.versions = versions;
        this.deskVersion = String(options.version || '');
        this.piVersion = String(options.piVersion || '');
        this._renderVersions();
        head.append(title, versions);

        const composer = document.createElement('div');
        composer.className = 'desk-pi-welcome-composer';
        this.input = document.createElement('textarea');
        this.input.className = 'desk-pi-welcome-input';
        this.input.rows = 2;
        this.input.placeholder = '输入消息…（Enter 发送 / Shift+Enter 换行）';
        const send = document.createElement('button');
        send.className = 'desk-pi-welcome-send';
        send.textContent = '→ 发送';
        send.addEventListener('click', () => this._send());
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this._send();
            }
        });
        composer.append(this.input, send);

        const foot = document.createElement('div');
        foot.className = 'desk-pi-welcome-foot';
        this.modelChip = document.createElement('button');
        this.modelChip.className = 'desk-pi-welcome-model';
        this.modelChip.textContent = `◉ ${options.model || '未选择模型'}`;
        this.modelChip.title = '选择模型 / 供应商';
        this.modelChip.addEventListener('click', () => options.onModels?.());
        this.modelChip.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            options.onModels?.();
        });
        const hints = document.createElement('div');
        hints.className = 'desk-pi-welcome-hints';
        hints.innerHTML = '<span>⚙ 自动</span><span>⚖ 默认</span>'
            + '<span>⇲ 压缩</span>';
        foot.append(this.modelChip, hints);

        this.suggestions = document.createElement('div');
        this.suggestions.className = 'desk-pi-welcome-suggestions';
        for (const text of (options.suggestions || [])) {
            const chip = document.createElement('button');
            chip.className = 'desk-pi-welcome-chip';
            chip.textContent = text;
            chip.addEventListener('click', () => {
                this.input.value = text;
                this.input.focus();
            });
            this.suggestions.appendChild(chip);
        }
        if (!this.suggestions.childElementCount) {
            this.suggestions.style.display = 'none';
        }

        this.recent = document.createElement('div');
        this.recent.className = 'desk-pi-welcome-recent';
        this.recent.style.display = 'none';

        // ★ 拖文件进来 / 粘贴图片：QtWebEngine 拿不到真实路径 → 明确提示 ✓
        this.element.addEventListener('dragover', (event) => {
            event.preventDefault();
            this.element.classList.add('drag');
        });
        this.element.addEventListener('dragleave', () => {
            this.element.classList.remove('drag');
        });
        this.element.addEventListener('drop', (event) => {
            event.preventDefault();
            this.element.classList.remove('drag');
            const text = event.dataTransfer?.getData('text/plain') || '';
            if (text) {
                this.input.value += text;
                this.input.focus();
                return;
            }
            options.onToast?.('info',
                '浏览器里拿不到拖入文件的路径：请用左下角「＠」或'
                + '资源管理器右键「发给 AI」✓');
        });
        this.element.addEventListener('paste', (event) => {
            const items = Array.from(event.clipboardData?.items || []);
            for (const item of items) {
                if (item.kind === 'file') {
                    event.preventDefault();
                    options.onToast?.('info',
                        '暂不支持直接粘贴图片：先存成文件，再用「＠」引用 ✓');
                    return;
                }
            }
        });

        this.element.append(head, composer, foot, this.suggestions,
                            this.recent);
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.element.className = `desk-pi-welcome theme-${theme}`;
    }

    setModel(model: string): void {
        this.modelChip.textContent = `◉ ${model || '未选择模型'}`;
    }

    /** 版本号：`desk v<minibt>` / `pi v<pi CLI>`（用户 2026-11-08 ✓） */
    setVersions(deskVersion?: string, piVersion?: string): void {
        if (deskVersion !== undefined && deskVersion !== '') {
            this.deskVersion = String(deskVersion);
        }
        if (piVersion !== undefined && piVersion !== '') {
            this.piVersion = String(piVersion);
        }
        this._renderVersions();
    }

    private _renderVersions(): void {
        if (!this.versions) return;
        const desk = this.deskVersion ? `desk v${esc(this.deskVersion)}` : '';
        const pi = this.piVersion ? `pi v${esc(this.piVersion)}` : '';
        this.versions.innerHTML = [desk, pi].filter(Boolean).join('<br>');
        this.versions.style.display = (desk || pi) ? '' : 'none';
    }

    focus(): void {
        this.input.focus();
    }

    /**
     * 最近会话（初始化页下方）：**只列 3 个**，点一下**打开那个会话** ✓
     *
     * 用户 2026-11-08：以前 6 个入口、点进去像新建会话 → 现在只要近期 3 个，
     * 新建会话统一走左栏「＋」。
     */
    setRecent(rows: Array<Record<string, unknown>>): void {
        this.recent.textContent = '';
        const list = (rows || []).slice(0, 3);
        if (!list.length) {
            this.recent.style.display = 'none';
            return;
        }
        const label = document.createElement('div');
        label.className = 'desk-pi-welcome-recent-label';
        label.textContent = '最近会话';
        this.recent.appendChild(label);
        for (const row of list) {
            const id = String(row.id || '');
            if (!id) continue;
            const button = document.createElement('button');
            button.className = 'desk-pi-welcome-recent-item';
            const pin = row.pinned ? '📌 ' : '';
            button.textContent = pin + String(row.title || row.name || id);
            button.title = String(row.preview || row.title || id);
            button.addEventListener('click', () => {
                this.options.onOpenSession?.(id);
            });
            this.recent.appendChild(button);
        }
        this.recent.style.display = '';
    }

    /** 程序化填字（外部想预填时用 ✓） */
    setText(text: string): void {
        this.input.value = String(text || '');
    }

    private _send(): void {
        const text = this.input.value.trim();
        if (!text) {
            this.input.focus();
            return;
        }
        this.input.value = '';
        this.options.onSend(text);
    }
}

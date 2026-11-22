/**
 * 「另存为」对话框（用户 2026-11-22：要像微信保存文件那样 ✓）
 *
 * 现在的流程：临时源码（打开指标 / 策略时自动生成，未写盘）→ 点「另存」
 * → 弹出这个窗口：
 *
 * ```
 * ┌ 另存为 ──────────────────────────────── ✕ ┐
 * │ ↑上级  ⌂主目录  个人指标  个人策略   [路径]│
 * │ ┌ 文件夹 / 文件列表（双击进文件夹）──────┐ │
 * │ └───────────────────────────────────────┘ │
 * │ 文件名 [____________________] .py         │
 * │                         [取消] [保存]     │
 * └───────────────────────────────────────────┘
 * ```
 *
 * 列表数据来自后端 `fs_list`（`explorer.browse()`，可以进任意目录 ✓）。
 */
import { ensureLayoutStyle } from './layout-dialogs';

export interface SaveListPayload {
    ok?: boolean;
    path?: string;
    parent?: string;
    home?: string;
    personal?: { indicators?: string; strategies?: string };
    items?: Array<{ name: string; path: string; dir: boolean; py?: boolean }>;
    error?: string;
}

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

const SEP = (path: string): string =>
    path.includes('\\') ? '\\' : '/';

export class SaveAsDialog {
    public readonly element: HTMLDivElement;
    private readonly onCommand: (cmd: string, payload?: unknown) => void;
    private readonly pathLabel: HTMLSpanElement;
    private readonly list: HTMLDivElement;
    private readonly nameInput: HTMLInputElement;
    private readonly hint: HTMLDivElement;
    private dir = '';
    private payload: SaveListPayload = {};
    private onSave: ((path: string) => void) | null = null;
    /** 当前选中的文件名（点列表里的文件时用 ✓） */
    private selected = '';

    /** 当前选中的条目（没用到也保留：以后支持"选中文件夹再保存" ✓） */
    get selection(): string {
        return this.selected;
    }

    constructor(onCommand: (cmd: string, payload?: unknown) => void) {
        ensureLayoutStyle();
        this.onCommand = onCommand;
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask desk-save-mask';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg desk-save';

        // ---- 标题栏
        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        const title = document.createElement('span');
        title.textContent = '另存为…';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '取消';
        close.addEventListener('click', () => this.close());
        head.append(title, close);

        // ---- 工具栏：上级 / 主目录 / 个人指标 / 个人策略 / 路径
        const bar = document.createElement('div');
        bar.className = 'desk-save-bar';
        const up = document.createElement('button');
        up.className = 'desk-save-nav';
        up.textContent = '↑ 上级';
        up.title = '上一层文件夹';
        up.addEventListener('click', () => this._go(this.payload.parent || ''));
        const home = document.createElement('button');
        home.className = 'desk-save-nav';
        home.textContent = '⌂ 主目录';
        home.title = '回到用户主目录';
        home.addEventListener('click', () => this._go(this.payload.home || ''));
        const ind = document.createElement('button');
        ind.className = 'desk-save-nav';
        ind.textContent = '个人指标';
        ind.title = '个人指标目录（保存后立刻能在「指标 → 个人」里用）';
        ind.addEventListener('click', () => this._go(
            this.payload.personal?.indicators || ''));
        const strat = document.createElement('button');
        strat.className = 'desk-save-nav';
        strat.textContent = '个人策略';
        strat.title = '个人策略目录';
        strat.addEventListener('click', () => this._go(
            this.payload.personal?.strategies || ''));
        this.pathLabel = document.createElement('span');
        this.pathLabel.className = 'desk-save-path';
        bar.append(up, home, ind, strat, this.pathLabel);

        // ---- 目录 / 文件列表
        this.list = document.createElement('div');
        this.list.className = 'desk-save-list';
        this.list.addEventListener('dblclick', (event) => {
            const row = (event.target as HTMLElement).closest<HTMLElement>(
                '[data-dir]');
            if (row) this._go(row.dataset.dir || '');
        });
        this.list.addEventListener('click', (event) => {
            const row = (event.target as HTMLElement).closest<HTMLElement>(
                '[data-item]');
            if (!row) return;
            this.selected = row.dataset.item || '';
            for (const node of Array.from(
                this.list.querySelectorAll<HTMLElement>('[data-item]'))) {
                node.classList.toggle('on', node === row);
            }
            // 点文件 → 顺手填进文件名框（和系统另存为一致 ✓）
            if (row.dataset.file === '1') {
                this.nameInput.value = row.dataset.item || '';
            }
        });

        // ---- 文件名 + 按钮
        const foot = document.createElement('div');
        foot.className = 'desk-save-foot';
        const label = document.createElement('span');
        label.className = 'desk-save-label';
        label.textContent = '文件名';
        this.nameInput = document.createElement('input');
        this.nameInput.className = 'desk-lg-input desk-save-name';
        this.nameInput.placeholder = '文件名（例：MyIndicator.py）';
        this.nameInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') this._commit();
        });
        this.hint = document.createElement('div');
        this.hint.className = 'desk-save-hint';
        const spacer = document.createElement('span');
        spacer.style.flex = '1';
        const cancel = document.createElement('button');
        cancel.className = 'desk-lg-btn desk-save-btn';
        cancel.textContent = '取消';
        cancel.addEventListener('click', () => this.close());
        const save = document.createElement('button');
        save.className = 'desk-lg-btn primary desk-save-btn';
        save.textContent = '保存';
        save.addEventListener('click', () => this._commit());
        foot.append(label, this.nameInput, spacer, cancel, save);

        box.append(head, bar, this.list, this.hint, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.element.dataset.deskTheme = theme === 'light' ? 'light' : 'dark';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    /**
     * 打开对话框
     *
     * `dir` = 建议目录（个人指标 / 策略 ✓）；`name` = 建议文件名
     */
    open(dir: string, name: string, onSave: (path: string) => void): void {
        this.onSave = onSave;
        this.selected = '';
        this.nameInput.value = name || '';
        this.element.style.display = '';
        this._go(dir);
        window.setTimeout(() => {
            this.nameInput.focus();
            // 只选中主文件名，保留扩展名（和系统另存为一致 ✓）
            const dot = this.nameInput.value.lastIndexOf('.');
            this.nameInput.setSelectionRange(
                0, dot > 0 ? dot : this.nameInput.value.length);
        }, 30);
    }

    close(): void {
        this.element.style.display = 'none';
        this.onSave = null;
    }

    /** 后端 `{type:'fs_list'}` 回来了 → 填列表 ✓ */
    applyListing(payload: SaveListPayload): void {
        if (!payload) return;
        this.payload = payload;
        if (payload.ok === false) {
            this.hint.textContent = String(payload.error || '读取目录失败');
            return;
        }
        if (payload.path) this.dir = payload.path;
        this.pathLabel.textContent = this.dir;
        this.pathLabel.title = this.dir;
        this.hint.textContent = '';
        this.list.textContent = '';
        const items = payload.items || [];
        const dirs = items.filter((item) => item.dir);
        const files = items.filter((item) => !item.dir && item.py);
        if (!dirs.length && !files.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-lg-empty';
            empty.textContent = '（这个文件夹是空的）';
            this.list.appendChild(empty);
            return;
        }
        for (const item of dirs) this.list.appendChild(this._row(item, true));
        for (const item of files) this.list.appendChild(this._row(item, false));
    }

    private _row(item: { name: string; path: string },
                 dir: boolean): HTMLDivElement {
        const row = document.createElement('div');
        row.className = `desk-save-row${dir ? ' dir' : ''}`;
        row.dataset.item = item.name;
        row.dataset.file = dir ? '0' : '1';
        if (dir) row.dataset.dir = item.path;
        row.innerHTML = `<span class="icon">${dir ? '📁' : '🐍'}</span>`
            + `<span class="name">${esc(item.name)}</span>`;
        return row;
    }

    private _go(path: string): void {
        const target = String(path || '').trim();
        this.selected = '';
        this.onCommand('fs_list', { path: target });
    }

    private _commit(): void {
        const name = this.nameInput.value.trim();
        if (!name) {
            this.hint.textContent = '请填写文件名';
            return;
        }
        const sep = SEP(this.dir);
        const full = this.dir ? `${this.dir}${sep}${name}` : name;
        const callback = this.onSave;
        this.close();
        callback?.(full);
    }
}

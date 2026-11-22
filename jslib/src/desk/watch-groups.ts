/**
 * 自选分组管理（首页左侧「自选分组」→ ⚙ 图标 ✓）
 *
 * 需求（用户 2026-11-21）：
 * 1. 列出**所有**分组；系统分组（最近打开 / 收藏 / 自选 …）**不可重命名 /
 *    不可删除**；
 * 2. 用户自建分组：鼠标悬停出现「重命名 / 删除」两个图标按钮，功能可用；
 * 3. 这里的改动要**同步首页侧栏**（删了「自选1」两处都没了 ✓）；
 * 4. 页面里的「＋」和首页「＋」是同一套（新建分组 ✓）；
 * 5. 显示分组信息（标的数量 ✓）。
 *
 * 界面复用「布局管理」的样式（`desk-lg-*`，见 `layout-dialogs.ts`），
 * 这样深浅主题 / 遮罩 / 按钮风格完全一致 ✓
 */
import { ensureLayoutStyle } from './layout-dialogs';

export interface WatchGroupRow {
    id: string;
    label: string;
    /** `recent` / `favorites` / `all` / `filter` / `custom` */
    kind: string;
    /** 分组里的标的数量 ✓ */
    count: number;
    /** 系统分组 → 不能重命名 / 删除 ✓ */
    system: boolean;
    /** 规则说明（系统分组用：`按代码前缀自动归类` 等 ✓） */
    hint?: string;
}

export interface WatchGroupManagerOptions {
    /** 当前所有分组（每次渲染都重新取 → 与首页同步 ✓） */
    rows: () => WatchGroupRow[];
    /** 重命名（返回 false → 提示失败） */
    onRename: (id: string, label: string) => boolean;
    /** 删除 */
    onDelete: (id: string) => void;
    /** 新建（和首页「＋」同一个动作 ✓） */
    onCreate: () => void;
    /** 点分组名 → 首页切到这个分组 ✓ */
    onOpen?: (id: string) => void;
    /** 自建分组：编辑里面的标的（逗号分隔 ✓） */
    onEdit?: (id: string) => void;
    /** 提示（复用首页 toast ✓） */
    onToast?: (level: string, text: string) => void;
}

const RENAME_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="1.8" stroke-linecap="round"><path d="M4 20h4L20 8l-4-4L4 16Z"/>'
    + '</svg>';
const EDIT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h10M4 18h7"/>'
    + '<path d="M17 14l4 4-4 4"/></svg>';
const DELETE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16"/>'
    + '<path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>'
    + '</svg>';

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

export class WatchGroupManager {
    public readonly element: HTMLDivElement;
    private readonly list: HTMLDivElement;
    private readonly countLabel: HTMLSpanElement;
    private readonly options: WatchGroupManagerOptions;
    /** 正在重命名 / 新建的行（内联输入框 ✓） */
    private renaming = '';

    constructor(options: WatchGroupManagerOptions) {
        ensureLayoutStyle();
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask desk-wg-mask';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg desk-wg';

        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        const title = document.createElement('span');
        title.textContent = '自选分组管理';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.append(title, close);

        const body = document.createElement('div');
        body.className = 'desk-lg-body';
        body.style.paddingTop = '0';
        const meta = document.createElement('div');
        meta.className = 'desk-lg-row';
        meta.innerHTML = '<span class="k" style="flex:0 0 auto">分组名称</span>';
        this.countLabel = document.createElement('span');
        this.countLabel.className = 'desk-lg-count';
        this.countLabel.style.marginLeft = 'auto';
        meta.appendChild(this.countLabel);
        body.appendChild(meta);

        this.list = document.createElement('div');
        this.list.className = 'desk-lg-list desk-wg-list';

        const foot = document.createElement('div');
        foot.className = 'desk-lg-foot';
        const add = document.createElement('button');
        add.className = 'desk-lg-btn primary';
        add.textContent = '＋ 新建分组';
        add.title = '新建分组（和首页「＋」同一个动作）';
        add.addEventListener('click', () => {
            this.options.onCreate();
            this.render();                    // 新建后立刻出现（首页同步 ✓）
        });
        const hint = document.createElement('span');
        hint.className = 'desk-wg-hint';
        hint.textContent = '系统分组（最近打开 / 收藏 / 自选）不可重命名 / 删除';
        const spacer = document.createElement('span');
        spacer.style.flex = '1';
        const done = document.createElement('button');
        done.className = 'desk-lg-btn';
        done.textContent = '关闭';
        done.addEventListener('click', () => this.close());
        foot.append(add, hint, spacer, done);

        box.append(head, body, this.list, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
        this.setTheme('dark');
    }

    /** 主题：和「布局管理」一样靠 `data-desk-theme` 让 CSS 变量接管 ✓ */
    setTheme(theme: 'light' | 'dark'): void {
        this.element.dataset.deskTheme = theme === 'light' ? 'light' : 'dark';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    open(): void {
        this.renaming = '';
        this.element.style.display = '';
        this.render();
    }

    close(): void {
        this.renaming = '';
        this.element.style.display = 'none';
    }

    toggle(): void {
        if (this.visible) this.close();
        else this.open();
    }

    /** 外部（首页 / 行情报价）改了分组 → 如果开着就重画 ✓ */
    refresh(): void {
        if (this.visible) this.render();
    }

    render(): void {
        const rows = this.options.rows() || [];
        this.countLabel.textContent = `${rows.length} 个分组`;
        this.list.textContent = '';
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-lg-empty';
            empty.textContent = '（还没有分组：点下面「＋ 新建分组」）';
            this.list.appendChild(empty);
            return;
        }
        for (const row of rows) {
            this.list.appendChild(
                this.renaming === row.id ? this._renderRename(row)
                    : this._renderRow(row));
        }
    }

    private _renderRow(row: WatchGroupRow): HTMLDivElement {
        const item = document.createElement('div');
        item.className = 'desk-lg-item desk-wg-item';
        item.dataset.groupId = row.id;
        const text = document.createElement('div');
        text.className = 'desk-wg-text';
        text.innerHTML = `<div class="desk-lg-name">${esc(row.label)}</div>`
            + `<div class="desk-lg-desc">${row.count} 个标的`
            + `${row.hint ? ` · ${esc(row.hint)}` : ''}</div>`;
        text.style.cursor = 'pointer';
        text.addEventListener('click', () => {
            this.options.onOpen?.(row.id);
            this.close();
        });
        const tag = document.createElement('span');
        tag.className = `desk-wg-tag${row.system ? ' system' : ''}`;
        tag.textContent = row.system ? '系统' : '自建';
        item.append(text, tag);
        if (!row.system) {
            const edit = document.createElement('button');
            edit.className = 'desk-lg-icon desk-wg-icon';
            edit.innerHTML = EDIT_ICON;
            edit.title = '编辑这个分组里的标的';
            edit.addEventListener('click', (event) => {
                event.stopPropagation();
                this.options.onEdit?.(row.id);
                this.render();
            });
            item.append(edit);
            const rename = document.createElement('button');
            rename.className = 'desk-lg-icon desk-wg-icon';
            rename.innerHTML = RENAME_ICON;
            rename.title = '重命名这个分组';
            rename.addEventListener('click', (event) => {
                event.stopPropagation();
                this.renaming = row.id;
                this.render();
            });
            const drop = document.createElement('button');
            drop.className = 'desk-lg-icon desk-wg-icon';
            drop.innerHTML = DELETE_ICON;
            drop.title = '删除这个分组';
            drop.addEventListener('click', (event) => {
                event.stopPropagation();
                const ok = window.confirm(
                    `删除分组「${row.label}」？\n（分组里的标的会一起从该分组移除，`
                    + '「自选 / 收藏」不受影响）');
                if (!ok) return;
                this.options.onDelete(row.id);
                this.render();                // 首页同步由回调负责 ✓
            });
            item.append(rename, drop);
        }
        return item;
    }

    private _renderRename(row: WatchGroupRow): HTMLDivElement {
        const item = document.createElement('div');
        item.className = 'desk-lg-item desk-wg-item renaming';
        const input = document.createElement('input');
        input.className = 'desk-lg-input desk-wg-input';
        input.value = row.label;
        input.placeholder = '分组名称';
        const commit = (save: boolean): void => {
            const label = input.value.trim();
            this.renaming = '';
            if (!save || !label || label === row.label) {
                this.render();
                return;
            }
            if (!this.options.onRename(row.id, label)) {
                this.options.onToast?.('warning', '重命名失败（分组不存在？）');
            }
            this.render();
        };
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') commit(true);
            else if (event.key === 'Escape') commit(false);
        });
        input.addEventListener('blur', () => commit(true));
        const ok = document.createElement('button');
        ok.className = 'desk-lg-btn primary desk-wg-ok';
        ok.textContent = '确定';
        ok.addEventListener('mousedown', (event) => {
            event.preventDefault();           // 别让 blur 抢先 ✓
            commit(true);
        });
        item.append(input, ok);
        window.setTimeout(() => {
            input.focus();
            input.select();
        }, 0);
        return item;
    }
}

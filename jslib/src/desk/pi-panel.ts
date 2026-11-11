/**
 * PiPanel —— 编辑器左栏的「PI 会话」列表（v1.3.7-9）
 *
 * 对齐 `Pi-Agent-Web-main` 的 `SessionSidebar`（去掉「文件」区 —— 文件用
 * desk 自己的资源管理器 ✓）：
 *
 *   ┌ 项目路径  ＋ ⟳（导入 pi 会话）┐
 *   │ 搜索…                        │
 *   │ 会话标题                      │
 *   │ 时间 · N 条 · 首行预览         │
 *   │ …                            │
 *   └ [模型] [技能]                 ┘
 */
import { showMenuBelow, type MenuItem } from './menu';
import { ICON_MERGE, ICON_PENCIL, ICON_REFRESH, ICON_TRASH } from './icons';
import { shortPath, whenText } from './pi-util';

export interface PiSessionRow {
    id: string;
    title?: string;
    name?: string;
    cwd?: string;
    created?: number;
    updated?: number;
    count?: number;
    preview?: string;
    source?: string;
    piPath?: string;
    /** 置顶（写在后端 `pi_pins` ✓） */
    pinned?: boolean;
}

export interface PiPanelOptions {
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
    onOpen: (id: string) => void;
    onModels: () => void;
    onSkills: () => void;
    onNew: () => void;
    /** 切换目录（和资源管理器**双向同步** ✓） */
    onDir?: (path: string) => void;
    /** 选择文件夹（系统对话框） */
    onPickDir?: () => void;
    /** 置顶 / 取消置顶（写 `pi_pins` ✓） */
    onPin?: (id: string, on: boolean) => void;
}

export class PiPanel {
    readonly element: HTMLDivElement;
    private readonly options: PiPanelOptions;
    private readonly head: HTMLDivElement;
    private readonly project: HTMLButtonElement;
    private readonly search: HTMLInputElement;
    private readonly list: HTMLDivElement;
    private readonly footer: HTMLDivElement;
    private rows: PiSessionRow[] = [];
    private active = '';
    /** 当前目录（= 资源管理器根目录 ✓） */
    private dir = '';
    /** 默认目录（个人指标 / 策略的根）与「最近打开过」的目录 */
    private defaultDir = '';
    private recent: string[] = [];

    constructor(options: PiPanelOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-pi-side';

        this.head = document.createElement('div');
        this.head.className = 'desk-pi-side-head';
        this.project = document.createElement('button');
        this.project.className = 'desk-pi-project';
        this.project.title = '切换目录（与资源管理器同步）';
        this.project.addEventListener('click', () => this._dirMenu());
        const add = document.createElement('button');
        add.className = 'desk-editor-btn';
        add.textContent = '＋';
        add.title = '新建会话';
        add.addEventListener('click', () => options.onNew());
        const refresh = document.createElement('button');
        refresh.className = 'desk-editor-btn';
        refresh.innerHTML = ICON_REFRESH;
        refresh.title = '刷新 / 导入 pi 会话';
        refresh.addEventListener('click', () => {
            showMenuBelow(refresh, [
                { label: '刷新会话列表', run: () =>
                    this.options.onCommand('pi_sessions', {}) },
                { label: '导入 pi 的会话（~/.pi/agent/sessions）', run: () =>
                    this.options.onCommand('pi_import', {}) },
            ]);
        });
        this.head.append(this.project, add, refresh);

        this.search = document.createElement('input');
        this.search.className = 'desk-pi-search';
        this.search.placeholder = '搜索会话…';
        this.search.addEventListener('input', () => this.render());

        this.list = document.createElement('div');
        this.list.className = 'desk-pi-list';

        this.footer = document.createElement('div');
        this.footer.className = 'desk-pi-footer';
        const models = document.createElement('button');
        models.className = 'desk-pi-footer-btn';
        models.textContent = '模型';
        models.title = '供应商 / API Key / 模型';
        models.addEventListener('click', () => options.onModels());
        const skills = document.createElement('button');
        skills.className = 'desk-pi-footer-btn';
        skills.textContent = '技能';
        skills.title = '技能（SKILL.md）安装与启用';
        skills.addEventListener('click', () => options.onSkills());
        this.footer.append(models, skills);

        this.element.append(this.head, this.search, this.list, this.footer);
    }

    /** 项目路径（= 资源管理器根目录 ✓）；目录变了要重新过滤会话 */
    setProject(path: string): void {
        const value = String(path || '');
        if (value && this.dir
            && value.toLowerCase() !== this.dir.toLowerCase()) {
            this.dir = value;
            this.render();
        } else if (value) {
            this.dir = value;
        }
        this.project.textContent = (value
            ? shortPath(value, 2, 26) : '（未打开目录）') + ' ▾';
        this.project.title = value || '（未打开目录）';
    }

    /** 默认目录（「使用默认目录」菜单项 ✓） */
    setDefaultDir(path: string): void {
        this.defaultDir = String(path || '');
    }

    /** 最近打开过的目录（菜单里列出来 ✓） */
    setRecent(rows: string[]): void {
        this.recent = (rows || []).filter(Boolean);
    }

    /** 目录下拉菜单：使用默认目录 / 最近 / 选择文件夹 ✓ */
    private _dirMenu(): void {
        const items: MenuItem[] = [];
        const short = (path: string) => shortPath(path, 2, 30);
        if (this.defaultDir) {
            items.push({
                label: `使用默认目录（${short(this.defaultDir)}）`,
                run: () => this.options.onDir?.(this.defaultDir),
            });
        }
        const others = this.recent.filter(
            (path) => path.toLowerCase() !== this.dir.toLowerCase());
        if (others.length) {
            items.push({ label: '最近打开过', disabled: true });
            for (const path of others.slice(0, 8)) {
                items.push({ label: `　${short(path)}`,
                             run: () => this.options.onDir?.(path) });
            }
        }
        items.push({ label: '', separator: true });
        items.push({
            label: '选择文件夹…',
            run: () => this.options.onPickDir?.(),
        });
        const box = this.project.getBoundingClientRect();
        showMenuBelow(this._anchor(box.left, box.bottom + 2), items);
    }

    setActive(id: string): void {
        this.active = String(id || '');
        this.render();
    }

    setSessions(rows: PiSessionRow[]): void {
        this.rows = Array.isArray(rows) ? rows.slice() : [];
        this.render();
    }

    private render(): void {
        const needle = this.search.value.trim().toLowerCase();
        this.list.textContent = '';
        const current = String(this.dir || '').toLowerCase();
        const rows = this.rows.filter((row) => {
            // ★ 只显示**当前目录**下的会话（用户 2026-11-08 要求 ✓）
            if (current) {
                const cwd = String(row.cwd || '').toLowerCase();
                if (cwd && cwd !== current) return false;
            }
            if (!needle) return true;
            const name = String(row.title || row.name || '');
            return name.toLowerCase().includes(needle)
                || String(row.preview || '').toLowerCase().includes(needle);
        });
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-pi-empty';
            empty.textContent = needle
                ? '（没有匹配的会话）'
                : '（这个目录下还没有会话：点「＋」新建，'
                    + '或点目录名切换 / ⟳ 导入 pi 会话）';
            this.list.appendChild(empty);
            return;
        }
        for (const row of rows) {
            const current = String(row.id) === this.active;
            const item = document.createElement('div');
            item.className = 'desk-pi-item' + (current ? ' on' : '');
            // 标题行：标题 + 悬浮按钮（和 pi-agent-web 一样靠右排列 ✓）
            const top = document.createElement('div');
            top.className = 'desk-pi-item-top';
            const title = document.createElement('div');
            title.className = 'desk-pi-item-title';
            // ★ 置顶的会话前面加 📌，并且排在最前面（后端已排序 ✓）
            const pinned = row.pinned === true;
            title.textContent = (pinned ? '📌 ' : '')
                + String(row.title || row.name || '新会话');
            if (pinned) item.classList.add('pinned');
            const actions = document.createElement('div');
            actions.className = 'desk-pi-item-actions';
            const iconButton = (icon: string, tip: string,
                                run: () => void) => {
                const button = document.createElement('button');
                button.className = 'desk-pi-item-btn';
                button.innerHTML = icon;
                button.title = tip;
                button.addEventListener('click', (event) => {
                    event.stopPropagation();
                    run();
                });
                actions.appendChild(button);
                return button;
            };
            // 当前会话：重命名 / 删除；其它会话：合并摘要 / 重命名 / 删除 ✓
            if (!current && this.active) {
                iconButton(ICON_MERGE, '把它的摘要合并到当前会话', () =>
                    this.mergeIntoCurrent(row));
            }
            iconButton(pinned ? '★' : '☆',
                       pinned ? '取消置顶' : '置顶（排最前）',
                       () => this.options.onPin?.(String(row.id), !pinned));
            iconButton(ICON_PENCIL, '重命名', () => this.rename(row));
            iconButton(ICON_TRASH, '删除', () => this.drop(row));
            top.append(title, actions);
            const info = document.createElement('div');
            info.className = 'desk-pi-item-info';
            const when = this._when(row.updated || row.created);
            const count = Number(row.count || 0);
            info.textContent = `${when} · ${count} 条 messages`
                + (row.source === 'pi' ? ' · 来自 pi' : '');
            const preview = document.createElement('div');
            preview.className = 'desk-pi-item-preview';
            preview.textContent = String(row.preview || '');
            item.append(top, info, preview);
            item.addEventListener('click', () => {
                this.active = String(row.id);
                this.render();
                this.options.onOpen(String(row.id));
            });
            item.addEventListener('contextmenu', (event) => {
                event.preventDefault();
                const items: MenuItem[] = [
                    { label: '在标签页打开', run: () =>
                        this.options.onOpen(String(row.id)) },
                ];
                if (String(row.id) !== this.active && this.active) {
                    items.push({ label: '合并摘要到当前会话',
                                 run: () => this.mergeIntoCurrent(row) });
                }
                items.push({
                    label: pinned ? '取消置顶' : '置顶',
                    run: () => this.options.onPin?.(String(row.id), !pinned),
                });
                items.push(
                    { label: '重命名…', run: () => this.rename(row) },
                    { label: '', separator: true },
                    { label: '删除会话', run: () => this.drop(row) },
                );
                showMenuBelow(this._anchor(event.clientX, event.clientY), items);
            });
            this.list.appendChild(item);
        }
    }

    /** 把「另一个会话」的摘要合并进**当前打开的**会话 ✓ */
    private mergeIntoCurrent(row: PiSessionRow): void {
        if (!this.active) {
            this.options.onToast?.('info', '先在标签页打开一个会话，再合并');
            return;
        }
        this.options.onCommand('pi_merge', {
            id: String(row.id), into: this.active,
        });
    }

    private rename(row: PiSessionRow): void {
        const current = String(row.title || row.name || '新会话');
        const name = window.prompt('会话名称', current);
        if (name === null) return;
        this.options.onCommand('pi_rename', { id: row.id, title: name });
    }

    private drop(row: PiSessionRow): void {
        const name = String(row.title || row.name || '');
        if (!window.confirm(`删除会话「${name}」？（不会删磁盘上的其他东西）`)) {
            return;
        }
        this.options.onCommand('pi_delete', { id: row.id });
    }

    private _when(value?: number): string {
        return whenText(value);
    }

    private _anchor(x: number, y: number): HTMLElement {
        const anchor = document.createElement('span');
        anchor.style.cssText = `position:fixed;left:${x}px;top:${y}px;`
            + 'width:0;height:0;';
        document.body.appendChild(anchor);
        window.setTimeout(() => anchor.remove(), 0);
        return anchor;
    }
}

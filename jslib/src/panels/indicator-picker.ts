/**
 * IndicatorPicker — 「指标、衡量标准和策略」选择器（复刻 miniqt 的指标面板）。
 *
 *   ┌ 指标、衡量标准和策略                                ✕ ┐
 *   │ [搜索 …]                                          🔍 │
 *   │ 个人      │ ☆ AndeanOsc                       BtInd │
 *   │  收藏     │   安第斯振荡器指标 (Andean Oscillator)     │
 *   │  我的脚本 │ ☆ Coral_Trend_Candles …                  │
 *   │  我的策略 │ …                                        │
 *   │ 内置指标  │                                          │
 *   │  BtInd    │                                          │
 *   └──────────────────────────────────────────────────────┘
 *
 * 事件（``;;;`` 分隔）：``pick;;;<key>`` / ``favorite;;;<key>;;;<0|1>``。
 */
import { emitCallback, ensureStyle } from './emit';

export interface PickerSection {
    key: string;
    label: string;
}

export interface PickerGroup {
    key: string;
    label: string;
    sections: PickerSection[];
}

export interface PickerItem {
    key: string;
    label: string;
    desc?: string;
    provider?: string;
    section?: string;
    /** 主图叠加（true）/ 副图（false）；`undefined` = 未知（个人脚本）✓ */
    overlay?: boolean;
    favorite?: boolean;
    strategy?: boolean;
    params?: Array<Record<string, unknown>>;
}

export interface IndicatorPickerOptions {
    title?: string;
    groups?: PickerGroup[];
    items?: PickerItem[];
    /** 默认选中的 section（`favorites` → 收藏 ✓） */
    section?: string;
    theme?: 'light' | 'dark';
    callbackName?: string | null;
}

const STYLE_ID = 'pylightcharts-indicatorpicker-style';

const CSS = `
.pylc-ip-mask{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:11800;
  display:flex;align-items:center;justify-content:center}
.pylc-ip{width:840px;height:620px;max-height:88vh;display:flex;flex-direction:column;
  border-radius:10px;overflow:hidden;background:var(--ip-bg);color:var(--ip-text);
  border:1px solid var(--ip-border);box-shadow:0 20px 60px rgba(0,0,0,.45)}
.pylc-ip-head{display:flex;align-items:center;justify-content:space-between;
  padding:12px 16px;font-size:15px;font-weight:600}
.pylc-ip-close{border:none;background:transparent;color:var(--ip-text);
  cursor:pointer;font-size:17px}
.pylc-ip-search-wrap{padding:0 16px 10px}
.pylc-ip-search{width:100%;height:30px;padding:0 10px;border-radius:6px;outline:none;
  border:1px solid var(--ip-border);background:var(--ip-input);color:var(--ip-text);
  font-size:12.5px}
.pylc-ip-search:focus{border-color:var(--ip-accent)}
.pylc-ip-body{flex:1;min-height:0;display:flex;border-top:1px solid var(--ip-border)}
.pylc-ip-tree{flex:0 0 190px;overflow:auto;padding:8px 0;
  border-right:1px solid var(--ip-border)}
/* 分组标题（可点击收起 / 展开 ✓） */
.pylc-ip-group{display:flex;align-items:center;gap:4px;padding:6px 14px 2px;
  color:var(--ip-accent);font-size:12px;cursor:pointer;user-select:none;
  border-radius:0 6px 6px 0}
.pylc-ip-group:hover{background:var(--ip-hover)}
.pylc-ip-group .pylc-ip-chev{display:inline-block;width:10px;font-size:10px;
  line-height:1;transition:transform .12s ease;opacity:.9}
.pylc-ip-group.collapsed .pylc-ip-chev{transform:rotate(-90deg)}
.pylc-ip-group .pylc-ip-group-count{margin-left:auto;color:var(--ip-muted);
  font-size:10.5px}
.pylc-ip-section{padding:4px 14px 4px 22px;cursor:pointer;font-size:12.5px;
  border-radius:0 6px 6px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pylc-ip-section.hidden{display:none}
.pylc-ip-section:hover{background:var(--ip-hover)}
.pylc-ip-section.on{background:var(--ip-active);font-weight:600}
.pylc-ip-list{flex:1;min-width:0;overflow:auto}
.pylc-ip-row{display:grid;grid-template-columns:22px 1fr auto;gap:6px;
  align-items:start;padding:8px 14px;cursor:pointer;border-bottom:1px solid var(--ip-border)}
.pylc-ip-row:hover{background:var(--ip-hover)}
/* 上次停留的指标：打开时闪一下（1.6s 后自动消失 ✓） */
.pylc-ip-row-focus{background:var(--ip-active, rgba(41,98,255,.18));
  box-shadow:inset 0 0 0 1px var(--ip-accent, #2962ff)}
.pylc-ip-star{color:var(--ip-muted);font-size:13px;line-height:1.25;
  cursor:pointer;user-select:none}
.pylc-ip-star.on{color:#f6c343}
.pylc-ip-name{font-size:13px}
.pylc-ip-desc{color:var(--ip-muted);font-size:11.5px;line-height:1.45}
.pylc-ip-provider{color:var(--ip-muted);font-size:11.5px;white-space:nowrap}
.pylc-ip-empty{padding:20px 16px;color:var(--ip-muted);font-size:12.5px}
.pylc-ip-filters{display:flex;align-items:center;gap:6px;padding:0 16px 8px;
  font-size:12px;color:var(--ip-muted)}
.pylc-ip-filter{padding:2px 9px;border-radius:999px;cursor:pointer;
  border:1px solid var(--ip-border);background:transparent;color:var(--ip-muted);
  font-size:12px;line-height:1.5}
.pylc-ip-filter:hover{background:var(--ip-hover)}
.pylc-ip-filter.on{background:var(--ip-active);color:var(--ip-text);
  border-color:var(--ip-accent);font-weight:600}
.pylc-ip-filter-count{margin-left:auto;color:var(--ip-muted);font-size:11.5px}
.pylc-ip-filter-hint{color:var(--ip-accent);font-size:11.5px;line-height:1.5}
.pylc-ip-filters{flex-wrap:wrap;row-gap:4px}
.pylc-ip-filter-count{white-space:nowrap}
`;

const PALS = {
    dark: {
        bg: '#161a20', text: '#d8d9db', muted: '#8b93a1', border: '#262c36',
        input: '#0f1115', hover: '#1e242d', active: '#263041', accent: '#4c8dff',
    },
    light: {
        bg: '#ffffff', text: '#1f2329', muted: '#6b7280', border: '#e3e6ea',
        input: '#f6f7f9', hover: '#eef1f5', active: '#e6efff', accent: '#1a73e8',
    },
};

export class IndicatorPicker {
    public readonly element: HTMLDivElement;
    public callbackName: string | null = null;
    public onPickCallback: ((item: PickerItem) => void) | null = null;
    public onFavoriteCallback:
        ((item: PickerItem, on: boolean) => void) | null = null;
    /** 选中的 section 变了 / 滚动位置变了（宿主可以记住，下次打开接着用 ✓） */
    public onSectionCallback: ((section: string) => void) | null = null;
    public onScrollCallback: ((top: number) => void) | null = null;
    /** 二级筛选变了（宿主可以记住，下次打开接着用 ✓） */
    public onFilterCallback:
        ((kind: 'all' | 'main' | 'sub') => void) | null = null;
    /** 左侧分组收起 / 展开变了（宿主可以记住 ✓） */
    public onGroupsCallback: ((collapsed: string[]) => void) | null = null;
    /** 关闭（宿主用来落盘最终的滚动位置 ✓） */
    public onCloseCallback: ((state: {
        section: string; scroll: number; treeScroll: number;
    }) => void) | null = null;
    /** 「重新加载」按钮（目录为空时自救 ✓） */
    public onReloadCallback: (() => void) | null = null;

    private groups: PickerGroup[];
    private items: PickerItem[];
    private section = 'favorites';
    private filterBar: HTMLDivElement | null = null;
    /** 载体统计 / 错误提示（`共 774 个指标` / 目录失败原因 ✓） */
    private infoBar: HTMLDivElement | null = null;
    private total = 0;
    /** 光标停留 / 定位用（上次看到哪个指标 ✓） */
    private focusTimer = 0;
    private focusedKey = '';
    private error = '';
    /** 二级筛选：全部 / 主图叠加 / 副图 ✓ */
    private overlayFilter: 'all' | 'main' | 'sub' = 'all';
    /** 左侧**收起**的分组 key（默认全部展开 ✓） */
    private collapsed = new Set<string>();
    private readonly tree: HTMLDivElement;
    private readonly list: HTMLDivElement;
    private readonly search: HTMLInputElement;
    private readonly titleEl: HTMLSpanElement;

    constructor(options: IndicatorPickerOptions = {}) {
        ensureStyle(STYLE_ID, CSS);
        this.callbackName = options.callbackName || null;
        this.groups = options.groups || [];
        this.items = options.items || [];
        this.section = options.section || 'favorites';

        this.element = document.createElement('div');
        this.element.className = 'pylc-ip-mask';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'pylc-ip';

        const head = document.createElement('div');
        head.className = 'pylc-ip-head';
        this.titleEl = document.createElement('span');
        this.titleEl.textContent = options.title || '指标、衡量标准和策略';
        const close = document.createElement('button');
        close.className = 'pylc-ip-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.append(this.titleEl, close);

        const searchWrap = document.createElement('div');
        searchWrap.className = 'pylc-ip-search-wrap';
        this.search = document.createElement('input');
        this.search.className = 'pylc-ip-search';
        this.search.placeholder = '搜索';
        this.search.title = '按名称 / 代码搜索指标';
        this.search.addEventListener('input', () => this._render());
        searchWrap.appendChild(this.search);

        this.filterBar = document.createElement('div');
        this.filterBar.className = 'pylc-ip-filters';
        this.infoBar = document.createElement('div');
        this.infoBar.className = 'pylc-ip-info';
        this.tree = document.createElement('div');
        this.tree.className = 'pylc-ip-tree';
        this.list = document.createElement('div');
        this.list.className = 'pylc-ip-list';
        // ★ 滚动位置变化 → 通知宿主（下次打开回到刚才的位置 ✓）
        let scrollTimer = 0;
        this.list.addEventListener('scroll', () => {
            window.clearTimeout(scrollTimer);
            scrollTimer = window.setTimeout(() => {
                this.onScrollCallback?.(this.scrollTop);
            }, 400);
        });

        const body = document.createElement('div');
        body.className = 'pylc-ip-body';
        body.append(this.tree, this.list);

        box.append(head, searchWrap, this.filterBar, this.infoBar, body);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);

        this.setTheme(options.theme === 'light' ? 'light' : 'dark');
        this.setGroups(this.groups);
        this._render();
    }

    // ------------------------------------------------------------- 数据
    setGroups(groups: PickerGroup[]): void {
        this.groups = groups || [];
        this._renderTree();
    }

    /** 载体统计 / 错误（后端 `indicator_picker` 补丁里的 `total` / `error` ✓） */
    setInfo(total: number, error = ''): void {
        this.total = Number(total) || 0;
        this.error = String(error || '');
        this._renderInfo();
        this._render();
    }

    private _renderInfo(): void {
        const bar = this.infoBar;
        if (!bar) return;
        bar.textContent = '';
        bar.classList.toggle('error', !!this.error);
        if (this.error) {
            bar.append(`⚠ ${this.error}`);
            const reload = document.createElement('button');
            reload.className = 'pylc-ip-reload';
            reload.textContent = '重新加载';
            reload.addEventListener('mousedown', (event) => {
                event.preventDefault();
                this.onReloadCallback?.();
            });
            bar.appendChild(reload);
            return;
        }
        bar.textContent = this.total ? `共 ${this.total} 个指标` : '';
    }

    setItems(items: PickerItem[]): void {
        this.items = items || [];
        this._render();
    }

    setFavorites(keys: string[]): void {
        const set = new Set(keys || []);
        for (const item of this.items) item.favorite = set.has(item.key);
        this._render();
    }

    /** 二级筛选（`all` / `main` 主图叠加 / `sub` 副图 ✓） */
    setOverlayFilter(kind: 'all' | 'main' | 'sub', notify = false): void {
        this.overlayFilter = kind === 'main' || kind === 'sub' ? kind : 'all';
        this._render();
        if (notify) this.onFilterCallback?.(this.overlayFilter);
    }

    /** 顶部筛选（全部 / 主图叠加 / 副图）—— 宿主持久化用 ✓ */
    get filterKey(): 'all' | 'main' | 'sub' {
        return this.overlayFilter;
    }

    get filter(): 'all' | 'main' | 'sub' {
        return this.overlayFilter;
    }

    setSection(section: string): void {
        const next = section || 'favorites';
        const changed = next !== this.section;
        this.section = next;
        this._renderTree();
        this._render();
        if (changed) this.onSectionCallback?.(next);
    }

    /** 当前 section（宿主持久化用 ✓） */
    get sectionKey(): string {
        return this.section;
    }

    /** 被收起的分组 key（宿主持久化用 ✓） */
    get collapsedGroups(): string[] {
        return [...this.collapsed];
    }

    /** 左侧导航滚动位置（宿主持久化用 ✓） */
    get treeScrollTop(): number {
        return Number(this.tree.scrollTop) || 0;
    }

    /** 恢复收起状态（不触发回调 ✓） */
    setCollapsed(keys: string[]): void {
        this.collapsed = new Set((keys || []).map((key) => String(key)));
        this._renderTree();
    }

    /** 切换某个分组的收起 / 展开 ✓ */
    toggleGroup(key: string): void {
        const name = String(key || '');
        if (!name) return;
        if (this.collapsed.has(name)) this.collapsed.delete(name);
        else this.collapsed.add(name);
        this._renderTree();
        this.onGroupsCallback?.(this.collapsedGroups);
    }

    /** 光标最后停留（或点过）的指标 key（宿主持久化用 ✓） */
    get focusKey(): string {
        return this.focusedKey;
    }

    /** 光标停留变了（宿主可以记住 ✓） */
    onFocusCallback: ((key: string) => void) | null = null;

    /**
     * 定位到某个指标：滚到它 + 高亮闪一下 ✓
     *
     * 返回 false → 当前列表里没有它（目录变了 / 换了分组），宿主改用滚动位置 ✓
     */
    revealKey(key: string): boolean {
        const target = String(key || '');
        if (!target) return false;
        const rows = Array.from(
            this.list.querySelectorAll<HTMLElement>('[data-item-key]'));
        const row = rows.find((item) => item.dataset.itemKey === target);
        if (!row) return false;
        try {
            row.scrollIntoView?.({ block: 'center' });
        } catch {
            const top = row.offsetTop - this.list.clientHeight / 2;
            this.list.scrollTop = Math.max(0, top);
        }
        row.classList.add('pylc-ip-row-focus');
        window.setTimeout(() => row.classList.remove('pylc-ip-row-focus'),
                          1600);
        return true;
    }

    /** 记录光标停留（节流 300ms 上报，避免划过一排就刷一堆 ✓） */
    private _noteFocus(key: string): void {
        if (!key || key === this.focusedKey) return;
        this.focusedKey = key;
        window.clearTimeout(this.focusTimer);
        this.focusTimer = window.setTimeout(() => {
            this.onFocusCallback?.(this.focusedKey);
        }, 300);
    }

    /** 列表滚动位置（宿主持久化用 ✓） */
    get scrollTop(): number {
        return Number(this.list.scrollTop) || 0;
    }

    /**
     * 恢复「上次的状态」：**先** section + 顶部筛选，**再**定位 / 滚动 ✓
     *
     * 用户 2026-11-19：只恢复 section 不够 —— 顶部筛选（全部 / 主图叠加 /
     * 副图）不同，行数就不同，滚动位置 / 定位的指标都会错位 ✗
     * 顺序必须是：section → 筛选 →（revealKey 或 restoreScroll）。
     */
    restoreState(state: {
        section?: string;
        filter?: 'all' | 'main' | 'sub';
        key?: string;
        scroll?: number;
        collapsed?: string[];
        treeScroll?: number;
    }): void {
        const section = String(state.section || '');
        if (section) this.section = section;
        const filter = state.filter;
        this.overlayFilter = filter === 'main' || filter === 'sub'
            ? filter : 'all';
        // ★ 左侧导航的收起状态先定下来，再渲染（否则 _renderTree 会重置 ✓）
        if (state.collapsed) {
            this.collapsed = new Set(state.collapsed.map((key) => String(key)));
            // 上次停的 section 如果被收起了 → 把它所在分组展开（否则左侧空了 ✗）
            for (const group of this.groups) {
                const owns = (group.sections || []).some(
                    (item) => item.key === this.section);
                if (owns) this.collapsed.delete(String(group.key));
            }
        }
        this._renderTree();
        this._render();
        const key = String(state.key || '');
        if (key && this.revealKey(key)) { /* 定了指标 → 不用滚动 ✓ */ }
        else if (state.scroll) this.restoreScroll(state.scroll);
        if (state.treeScroll) this.restoreTreeScroll(state.treeScroll);
    }

    /** 恢复左侧导航滚动位置（等渲染完再设 ✓） */
    restoreTreeScroll(top: number): void {
        const value = Math.max(0, Number(top) || 0);
        const apply = () => {
            try {
                this.tree.scrollTop = value;
            } catch { /* ignore */ }
        };
        apply();
        window.requestAnimationFrame?.(apply);
        window.setTimeout(apply, 60);
        window.setTimeout(apply, 200);
    }

    /** 恢复滚动位置：等渲染完再设（列表内容是异步来的 ✓） */
    restoreScroll(top: number): void {
        const value = Math.max(0, Number(top) || 0);
        const apply = () => {
            try {
                this.list.scrollTop = value;
            } catch { /* ignore */ }
        };
        apply();
        // 一帧后再来一次（图片 / 卡片渲染会改变高度）
        window.requestAnimationFrame?.(apply);
        window.setTimeout(apply, 60);
        window.setTimeout(apply, 200);
    }

    open(section = ''): void {
        this.element.style.display = '';
        this.search.value = '';
        if (section) this.setSection(section);
        else { this._renderTree(); this._render(); }
        this.search.focus();
    }

    close(): void {
        this.element.style.display = 'none';
        // ★ 关闭时把「最终的」位置交给宿主持久化（滚动位置只有关掉才定型 ✓）
        this.onCloseCallback?.({
            section: this.section,
            scroll: this.scrollTop,
            treeScroll: this.treeScrollTop,
        });
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    setTheme(theme: 'light' | 'dark'): void {
        const pal = PALS[theme === 'light' ? 'light' : 'dark'];
        for (const [key, value] of Object.entries(pal)) {
            this.element.style.setProperty(`--ip-${key}`, value);
        }
    }

    // ------------------------------------------------------------- 渲染
    private _renderTree(): void {
        this.tree.textContent = '';
        for (const group of this.groups) {
            const key = String(group.key || group.label || '');
            const collapsed = this.collapsed.has(key);
            const title = document.createElement('div');
            title.className = 'pylc-ip-group' + (collapsed ? ' collapsed' : '');
            title.dataset.groupKey = key;
            title.title = collapsed
                ? `展开「${group.label}」` : `收起「${group.label}」`;
            const chev = document.createElement('span');
            chev.className = 'pylc-ip-chev';
            chev.textContent = '▾';
            const label = document.createElement('span');
            label.textContent = group.label;
            const count = document.createElement('span');
            count.className = 'pylc-ip-group-count';
            count.textContent = String((group.sections || []).length);
            title.append(chev, label, count);
            title.addEventListener('click', () => this.toggleGroup(key));
            this.tree.appendChild(title);
            for (const section of group.sections) {
                const row = document.createElement('div');
                row.className = 'pylc-ip-section'
                    + (section.key === this.section ? ' on' : '')
                    + (collapsed ? ' hidden' : '');
                row.dataset.sectionKey = String(section.key || '');
                row.dataset.groupKey = key;
                row.textContent = section.label;
                row.addEventListener('click', () => this.setSection(section.key));
                this.tree.appendChild(row);
            }
        }
        // ★ 当前选中的 section 滚到**可见位置**（左侧导航很长时也能看出
        //   "上次打开的是哪一项"✓ 用户 2026-11-19）
        const active = this.tree.querySelector<HTMLElement>(
            '.pylc-ip-section.on');
        if (active) {
            try {
                active.scrollIntoView?.({ block: 'nearest' });
            } catch { /* 老内核 → 忽略 ✓ */ }
        }
    }

    /** 当前 section（+ 搜索 + 二级筛选）下的条目 ✓ */
    private _visibleRows(): PickerItem[] {
        const rows = this._sectionRows();
        // 二级筛选：主图叠加 / 副图（未知 overlay 的一律当副图看，别藏起来 ✗）
        if (this.overlayFilter === 'main') {
            return rows.filter((item) => item.overlay === true);
        }
        if (this.overlayFilter === 'sub') {
            return rows.filter((item) => item.overlay !== true);
        }
        return rows;
    }

    /** 筛选按钮（全部 / 主图叠加 / 副图 + 计数 ✓） */
    private _renderFilters(): void {
        if (!this.filterBar) return;
        const rows = this._visibleRows();
        this.filterBar.textContent = '';
        const label = document.createElement('span');
        label.textContent = '显示：';
        this.filterBar.appendChild(label);
        // ★ 三个按钮都带**计数**（用户 2026-11-08：只看「副图」时以为指标缺了 ✓）
        const base = this._sectionRows();
        const counts: Record<string, number> = {
            all: base.length,
            main: base.filter((item) => item.overlay === true).length,
            sub: base.filter((item) => item.overlay !== true).length,
        };
        for (const [key, text] of [['all', '全部'],
                                   ['main', '主图叠加'],
                                   ['sub', '副图']] as const) {
            const chip = document.createElement('button');
            chip.className = 'pylc-ip-filter'
                + (this.overlayFilter === key ? ' on' : '');
            chip.textContent = `${text} ${counts[key]}`;
            chip.title = `${text}：本分区 ${counts[key]} 个指标`;
            chip.addEventListener('click',
                                  () => this.setOverlayFilter(key, true));
            this.filterBar.appendChild(chip);
        }
        const count = document.createElement('span');
        count.className = 'pylc-ip-filter-count';
        count.textContent = rows.length === base.length
            ? `共 ${rows.length} 个`
            : `${rows.length} / ${base.length} 个`;
        this.filterBar.appendChild(count);
        // ★ 被筛掉多少 → 明说，并给一个「显示全部」的按钮 ✓
        const hidden = base.length - rows.length;
        if (this.overlayFilter !== 'all' && hidden > 0) {
            const hint = document.createElement('span');
            hint.className = 'pylc-ip-filter-hint';
            hint.textContent = `（已按「${this.overlayFilter === 'main'
                ? '主图叠加' : '副图'}」筛选，隐藏 ${hidden} 个`
                + ` — 看不到想要的指标就点「全部 ${base.length}」）`;
            const showAll = document.createElement('button');
            showAll.className = 'pylc-ip-filter';
            showAll.textContent = '显示全部';
            showAll.addEventListener('click',
                                     () => this.setOverlayFilter('all', true));
            this.filterBar.append(hint, showAll);
        }
    }

    /** 当前分组（还没过二级筛选）的条目 ✓ */
    private _sectionRows(): PickerItem[] {
        const needle = this.search.value.trim().toLowerCase();
        const favorite = this.section === 'favorites';
        return this.items.filter((item) => {
            if (needle) {
                return item.key.toLowerCase().includes(needle)
                    || (item.label || '').toLowerCase().includes(needle);
            }
            if (favorite) return !!item.favorite;
            if (this.section === 'all') return true;
            if (this.section === 'my_strategies') return !!item.strategy;
            if (this.section === 'my_scripts') return item.section === 'my_scripts';
            return item.section === this.section;
        });
    }

    private _render(): void {
        this._renderFilters();
        const rows = this._visibleRows();
        const favorite = this.section === 'favorites';
        this.list.textContent = '';
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'pylc-ip-empty';
            empty.textContent = this.error
                ? `（加载失败：${this.error}）`
                : favorite
                ? '（还没有收藏指标：点条目左侧的 ☆ 收藏）'
                : (this.overlayFilter === 'main'
                    ? '（这个分组里没有主图叠加的指标 —— 点上面的「显示全部」）'
                    : (this.overlayFilter === 'sub'
                        ? '（这个分组里没有副图指标 —— 点上面的「显示全部」）'
                        : '（没有匹配的指标）'));
            this.list.appendChild(empty);
            return;
        }
        for (const item of rows) {
            const row = document.createElement('div');
            row.className = 'pylc-ip-row';
            // ★ 记住「光标停在哪个指标上」→ 下次打开定位到它（用户 2026-11-18）
            row.dataset.itemKey = String(item.key || '');
            row.addEventListener('mouseenter', () => {
                this._noteFocus(String(item.key || ''));
            });
            const star = document.createElement('span');
            star.className = 'pylc-ip-star' + (item.favorite ? ' on' : '');
            star.textContent = item.favorite ? '★' : '☆';
            star.title = item.favorite ? '取消收藏' : '收藏（工具栏下拉可用）';
            star.addEventListener('click', (event) => {
                event.stopPropagation();
                item.favorite = !item.favorite;
                star.textContent = item.favorite ? '★' : '☆';
                star.classList.toggle('on', !!item.favorite);
                emitCallback(this.callbackName,
                    `favorite;;;${item.key};;;${item.favorite ? 1 : 0}`);
                this.onFavoriteCallback?.(item, !!item.favorite);
            });
            const text = document.createElement('div');
            text.innerHTML = `<div class="pylc-ip-name">${item.label}</div>`
                + (item.desc ? `<div class="pylc-ip-desc">${item.desc}</div>` : '');
            const provider = document.createElement('div');
            provider.className = 'pylc-ip-provider';
            provider.textContent = item.provider || '';
            row.append(star, text, provider);
            row.addEventListener('click', () => {
                this._noteFocus(String(item.key || ''));
                emitCallback(this.callbackName, `pick;;;${item.key}`);
                this.onPickCallback?.(item);
                this.close();
            });
            this.list.appendChild(row);
        }
    }
}

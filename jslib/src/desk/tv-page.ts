/**
 * 「指标和策略」列表页（仿 TradingView 的 Indicators & Strategies ✓）
 *
 * 只针对 **minibt 自带的 TradingView 指标**（后端 `tv_list` 给的 `tv:` 组）：
 *
 *  - 大标题 + 胶囊标签（热门 / 收藏）+ 分组筛选 + 搜索 + 卡片网格 + 分页；
 *  - 卡片：缩略图（本地没有就**自动截图**）+ 名称 + 简介 + 参数数 + 收藏 ⭐；
 *  - 卡片可 **「＋ 在图表上使用」**（加到当前图表）；
 *  - **点卡片 → 新开一个页签**（指标图表页，多开互不影响 ✓），
 *    不在本页里嵌详情（用户 2026-11-02 要求 ✓）。
 */
import { showMenu, showMenuBelow } from './menu';

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

export interface TvPageOptions {
    id: string;
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: Record<string, unknown>) => void;
    onToast?: (level: string, text: string) => void;
    /** 「在图表上使用」→ 让主界面弹出图表列表（在鼠标位置 ✓） */
    onApply?: (key: string, position?: { x: number; y: number }) => void;
    /** 点卡片 → 新开一个指标图表页（多开 ✓） */
    onOpen?: (key: string, name: string, kind?: string) => void;
    /** 当前打开的**本地图表 / 实时图表**（卡片右键「在图表上使用」子菜单 ✓） */
    charts?: () => Array<{ id: string; label: string }>;
    /** 右键「在图表上使用」→ 加到指定图表 ✓ */
    onApplyToChart?: (key: string, targetId: string) => void;
}

interface TvCard {
    key: string; name: string; group: string; desc: string;
    params: number; overlap: boolean; star: boolean; comments: number;
    card: string;
    /** 用户自己的指标 / 策略（`file:<路径>` ✓） */
    user?: boolean;
    kind?: string;
    rel?: string;
}

interface TvGroup { key: string; label: string; user: boolean; count: number }

interface TvState {
    items: TvCard[]; total: number; page: number; pages: number;
    groups: TvGroup[]; group: string; star: boolean;
}

/** 下拉框里的两个「动作」项（不是分组 ✓） */
const GROUP_ADD = '__add__';
const GROUP_REMOVE = '__remove__';

/** 一页 24 个（最大化 3 行 × 8 ✓ 用户要求 8） */
const PAGE_SIZE = 24;

export class TvPage {
    public readonly element: HTMLDivElement;
    public readonly id: string;
    private readonly options: TvPageOptions;
    private state: TvState = {
        items: [], total: 0, page: 1, pages: 1,
        groups: [{ key: '', label: 'TradingView', user: false, count: 0 }],
        group: '', star: false,
    };
    private query = '';
    private group = '';
    private starOnly = false;
    private page = 1;
    /** 缩略图缓存：key → data URI ✓ */
    private readonly cards = new Map<string, string>();
    private readonly pendingCards = new Set<string>();
    /** 「回到顶部」按钮（页面能滚动、且滚过筛选行才出现 ✓） */
    private readonly topButton: HTMLButtonElement;

    constructor(options: TvPageOptions) {
        this.options = options;
        this.id = options.id;
        this.element = document.createElement('div');
        this.element.className = 'desk-tv';
        this.topButton = document.createElement('button');
        this.topButton.type = 'button';
        this.topButton.className = 'desk-tv-top';
        this.topButton.textContent = '↑';
        this.topButton.title = '回到顶部';
        this.topButton.setAttribute('aria-label', '回到顶部');
        this.topButton.addEventListener('click', () => {
            this.element.scrollTo?.({ top: 0, behavior: 'smooth' });
            this.element.scrollTop = 0;      // 老内核不支持 scrollTo 选项时兜底 ✓
        });
        this.element.addEventListener('scroll', () => this._syncTopButton());
        try {
            window.addEventListener('resize', () => this._syncTopButton());
        } catch {
            /* 测试 stub / 老内核没有 window.addEventListener ✓ */
        }
        this._bind();
        this._render();
    }

    /**
     * 「回到顶部」按钮的显隐 + 位置 ✓
     *
     * * 只有**页面真能滚动**（卡片超过一屏）时才可能出现；
     * * 滚到「全部分组」那一行**以下**才出现（在上面时它在视口外，没意义）；
     * * 固定在页面右下角（`position: fixed`，坐标按页面矩形算）。
     */
    private _syncTopButton(): void {
        const button = this.topButton;
        if (!button.isConnected) {
            this.element.appendChild(button);
        }
        const scrollable = this.element.scrollHeight
            - this.element.clientHeight > 8;
        const filter = this.element.querySelector<HTMLElement>(
            '.desk-tv-filter');
        const rect = this.element.getBoundingClientRect();
        const passedHeader = !filter || filter.getBoundingClientRect().bottom
            < rect.top + 4;
        const show = scrollable && passedHeader && this.element.scrollTop > 0;
        button.classList.toggle('on', show);
        if (!show) return;
        button.style.left = `${Math.round(rect.right - 52)}px`;
        button.style.top = `${Math.round(rect.bottom - 52)}px`;
    }

    // ------------------------------------------------------------ 生命周期
    show(): void { this.element.style.display = 'flex'; }

    hide(): void { this.element.style.display = 'none'; }

    applyTheme(theme: 'light' | 'dark'): void {
        if (theme === this.options.theme) return;
        this.options.theme = theme;
        this.cards.clear();
        this.pendingCards.clear();       // 旧主题的请求作废 ✓
        this._reload();
    }

    setList(patch: Record<string, any>): void {
        this.state = {
            items: (patch.items || []) as TvCard[],
            total: Number(patch.total) || 0,
            page: Number(patch.page) || 1,
            pages: Number(patch.pages) || 1,
            groups: (patch.groups || []) as TvGroup[],
            group: String(patch.group || ''),
            star: !!patch.star,
        };
        this.group = this.state.group;
        this.page = this.state.page;
        this.starOnly = this.state.star;
        this._render();
        // 卡片缩略图：缺 data URI 就按需请求（**用户自己的也自动生成** ✓）
        for (const item of this.state.items) this._ensureCard(item.key);
    }

    setSnapshot(patch: Record<string, any>): void {
        const key = String(patch.key || '');
        const url = String(patch.dataUrl || '');
        this.pendingCards.delete(key);
        if (!key || !url) return;
        // ★ 主题对不上的图**不要**（深色截图不能覆盖浅色卡片 ✓）
        const theme = String(patch.theme || '');
        if (theme && theme !== this.options.theme) return;
        this.cards.set(key, url);
        const img = this.element.querySelector<HTMLImageElement>(
            `img[data-tv-card="${CSS.escape(key)}"]`);
        if (img) img.src = url;
        const empty = this.element.querySelector<HTMLElement>(
            `[data-tv-thumb="${CSS.escape(key)}"]`);
        if (empty) {
            const image = document.createElement('img');
            image.className = 'desk-tv-card-img';
            image.dataset.tvCard = key;
            image.alt = key;
            image.src = url;
            empty.replaceWith(image);
        }
    }

    /** 收藏变化 → 刷新列表（保持 ⭐ 同步 ✓） */
    refresh(): void { this._reload(); }

    // ---------------------------------------------------------------- 渲染
    private _render(): void {
        this.element.innerHTML = this._listHtml();
        this.element.appendChild(this.topButton);   // 重新挂上（innerHTML 清过 ✓）
        this.element.querySelectorAll<HTMLImageElement>('img[data-tv-card]')
            .forEach((img) => {
                const url = this.cards.get(img.dataset.tvCard || '');
                if (url) img.src = url;
            });
        this._syncTopButton();
    }

    private _cardHtml(item: TvCard): string {
        const img = this.cards.get(item.key);
        const kind = item.kind === 'strategy' ? '策略' : '指标';
        // ★ 用户自己的指标 / 策略也**自动生成缩略图**（和 TradingView 一样 ✓）
        const thumb = (img || item.card)
            ? `<img class="desk-tv-card-img" data-tv-card="${esc(item.key)}"
                   src="${esc(img || '')}" alt="${esc(item.name)}">`
            : `<div class="desk-tv-card-img is-empty${item.user ? ' is-file' : ''}"
                   data-tv-thumb="${esc(item.key)}">
                   ${item.user
        ? `<span class="desk-tv-file-badge">我的${kind}</span>
                       <span class="desk-tv-file-path">${esc(item.rel || item.name)}</span>
                       <span class="desk-tv-file-note">缩略图生成中…</span>`
        : '<span>截图生成中…</span>'}
               </div>`;
        // ★ 右上角「指标 / 策略」标记用 **HTML** 画（不再烘焙进 SVG）：
        //   手动截图会把封面换成 PNG（没有这个标记），HTML 标记始终在 ✓
        //   （用户实测 2026-11-03：截图后卡片标记不见了 ✗）
        const tag = item.user
            ? `我的${kind}`
            : kind;
        return `<article class="desk-tv-card" data-tv-open="${esc(item.key)}"
                    data-tv-name="${esc(item.name)}"
                    data-tv-kind="${esc(item.kind || 'indicator')}">
            ${thumb}
            <span class="desk-tv-card-tag">${esc(tag)}</span>
            <button class="desk-tv-card-use" data-tv-use="${esc(item.key)}"
                title="把「${esc(item.name)}」加到当前图表">＋ 在图表上使用</button>
            <div class="desk-tv-card-body">
                <div class="desk-tv-card-title">${esc(item.name)}</div>
                <div class="desk-tv-card-desc">${esc(item.desc || '（暂无简介）')}</div>
                <div class="desk-tv-card-foot">
                    <span class="desk-tv-card-author">minibt · ${esc(item.group)}</span>
                    <span class="desk-tv-card-stats">
                        <span title="参数个数">⚙ ${item.params}</span>
                        <span class="${item.star ? 'on' : ''}"
                              title="${item.star ? '取消收藏' : '收藏'}"
                              data-tv-star="${esc(item.key)}">${item.star ? '★' : '☆'}</span>
                    </span>
                </div>
            </div>
        </article>`;
    }

    private _listHtml(): string {
        const groups = this.state.groups.length ? this.state.groups
            : [{ key: '', label: 'TradingView', user: false, count: 0 }];
        const options = [`<option value="">全部分组（${
            groups.reduce((sum, group) => sum + Number(group.count || 0), 0)
            || this.state.total}）</option>`]
            .concat(groups.map((group) =>
                `<option value="${esc(group.key)}"${
                    group.key === this.group ? ' selected' : ''
                }>${esc(group.label)}${group.user ? '' : ' · 默认'}${
                    group.count !== undefined ? `（${group.count}）` : ''
                }</option>`))
            .concat([
                `<option value="${GROUP_ADD}">＋ 添加指标和策略</option>`,
                `<option value="${GROUP_REMOVE}">－ 删除指标和策略</option>`,
            ]);
        const cards = this.state.items.length
            ? this.state.items.map((item) => this._cardHtml(item)).join('')
            : '<div class="desk-tv-empty">没有匹配的指标（换个关键词试试）</div>';
        return `<div class="desk-tv-head">
            <div class="desk-tv-title-row">
                <h1>指标和策略</h1>
                <div class="desk-tv-tabs">
                    <button class="desk-tv-pill${this.starOnly ? '' : ' on'}"
                        data-tv-tab="hot">热门</button>
                    <button class="desk-tv-pill${this.starOnly ? ' on' : ''}"
                        data-tv-tab="star">收藏</button>
                </div>
            </div>
            <div class="desk-tv-filter">
                <select data-tv-group>${options.join('')}</select>
                <input class="desk-tv-search" data-tv-search
                    placeholder="搜索指标（名称 / 分组 / 简介）…"
                    value="${esc(this.query)}">
                <button class="desk-tv-btn" data-tv-refresh
                    title="重新拉取列表">刷新</button>
                <button class="desk-tv-btn" data-tv-reload
                    title="重新计算指标 / 策略并重新生成卡片截图">重载图表</button>
                <span class="desk-tv-count">${this.state.total} 个指标</span>
            </div>
        </div>
        <div class="desk-tv-grid">${cards}</div>
        ${this._pagerHtml()}`;
    }

    private _pagerHtml(): string {
        if (this.state.pages <= 1) return '';
        const buttons: string[] = [];
        for (let index = 1; index <= this.state.pages; index += 1) {
            buttons.push(`<button class="desk-tv-page${index === this.page
                ? ' on' : ''}" data-tv-page="${index}">${index}</button>`);
        }
        return `<div class="desk-tv-pager">${buttons.join('')}</div>`;
    }

    // ---------------------------------------------------------------- 事件
    private _bind(): void {
        this.element.addEventListener('click', (event) => {
            const target = event.target as HTMLElement;
            const use = target.closest<HTMLElement>('[data-tv-use]');
            if (use) {
                event.stopPropagation();
                const key = use.dataset.tvUse || '';
                if (key && this.options.onApply) {
                    // ★ 菜单要弹在**鼠标点的位置**（以前跑到左下角 ✗）
                    this.options.onApply(key, {
                        x: event.clientX, y: event.clientY,
                    });
                }
                return;
            }
            const star = target.closest<HTMLElement>('[data-tv-star]');
            if (star) {
                event.stopPropagation();
                const key = star.dataset.tvStar || '';
                this.options.onCommand('tv_star', {
                    id: this.id, key, on: !star.classList.contains('on'),
                });
                return;
            }
            const card = target.closest<HTMLElement>('[data-tv-open]');
            if (card) {
                const key = card.dataset.tvOpen || '';
                const name = card.dataset.tvName || '';
                const kind = card.dataset.tvKind || 'indicator';
                if (key && this.options.onOpen) {
                    this.options.onOpen(key, name, kind);
                }
                return;
            }
            const tab = target.closest<HTMLElement>('[data-tv-tab]');
            if (tab) {
                this.starOnly = tab.dataset.tvTab === 'star';
                this.page = 1;
                this._reload();
                return;
            }
            const page = target.closest<HTMLElement>('[data-tv-page]');
            if (page) {
                this.page = Number(page.dataset.tvPage) || 1;
                this._reload();
                return;
            }
            if (target.closest('[data-tv-refresh]')) this._reload();
            if (target.closest('[data-tv-reload]')) {
                // ★ 重载：重算当前页卡片的指标 / 策略 + 重新截图 ✓
                this.options.onCommand('tv_reload', {
                    id: this.id, theme: this.options.theme,
                    group: this.group, query: this.query,
                    star: this.starOnly, page: this.page, size: PAGE_SIZE,
                });
                this.options.onToast?.('info', '正在重新计算并生成卡片截图…');
                return;
            }
        });
        // ★ 卡片右键菜单：「在图表上使用」（二级菜单）+「重载图表」（单张 ✓）
        //   页面其它地方的原生右键菜单一律禁用（需求 3 ✓）
        this.element.addEventListener('contextmenu', (event) => {
            const target = event.target as HTMLElement;
            const card = target.closest<HTMLElement>('[data-tv-open]');
            event.preventDefault();
            if (!card) return;
            const key = card.dataset.tvOpen || '';
            if (!key) return;
            const cardName = card.dataset.tvName || '';
            const cardKind = card.dataset.tvKind || 'indicator';
            const charts = this.options.charts?.() || [];
            const submenu = charts.length
                ? charts.map((chart) => ({
                    label: chart.label,
                    run: () => this.options.onApplyToChart?.(key, chart.id),
                }))
                : [{ label: '（没有打开的本地 / 实时图表）', disabled: true }];
            showMenu(event.clientX, event.clientY, [
                {
                    // ★ 和左键点卡片一样（已打开就直接跳过去 ✓）
                    label: cardKind === 'strategy' ? '打开策略' : '打开指标',
                    run: () => this.options.onOpen?.(
                        key, cardName, cardKind),
                },
                { label: '在图表上使用', submenu, separator: true },
                {
                    label: '重载图表', separator: true,
                    run: () => this.options.onCommand('tv_card_reload', {
                        id: this.id, key, theme: this.options.theme,
                    }),
                },
            ] as never);
        });

        this.element.addEventListener('change', (event) => {
            const select = (event.target as HTMLElement)
                .closest<HTMLSelectElement>('[data-tv-group]');
            if (!select) return;
            const value = select.value;
            if (value === GROUP_ADD) {
                select.value = this.group;      // 选完恢复（不是真的分组 ✓）
                this.options.onCommand('tv_group_add', { id: this.id });
                return;
            }
            if (value === GROUP_REMOVE) {
                select.value = this.group;
                this._removeGroupMenu(select);
                return;
            }
            this.group = value;
            this.page = 1;
            this._reload();
        });
        this.element.addEventListener('input', (event) => {
            const input = (event.target as HTMLElement)
                .closest<HTMLInputElement>('[data-tv-search]');
            if (!input) return;
            this.query = input.value;
        });
        this.element.addEventListener('keydown', (event) => {
            const input = (event.target as HTMLElement)
                .closest<HTMLInputElement>('[data-tv-search]');
            if (input && event.key === 'Enter') {
                this.page = 1;
                this._reload();
            }
        });
    }

    /** 「删除指标和策略」：弹菜单列出已添加的分组 ✓ */
    private _removeGroupMenu(anchor: HTMLElement): void {
        const users = this.state.groups.filter((group) => group.user);
        if (!users.length) {
            this.options.onToast?.('info', '还没有添加过指标 / 策略分组');
            return;
        }
        showMenuBelow(anchor, users.map((group) => ({
            label: `${group.label}（${group.count}）`,
            run: () => this.options.onCommand('tv_group_remove', {
                id: this.id, path: group.key,
            }),
        })));
    }

    /** 分组增删的结果：刷新下拉框 + 列表 ✓ */
    setGroups(patch: Record<string, any>): void {
        if (Array.isArray(patch.groups)) {
            this.state.groups = patch.groups as TvGroup[];
        }
        const paths = new Set((patch.groups || [])
            .map((group: TvGroup) => group.key));
        const added = String(patch.path || '');
        if (patch.ok && added && paths.has(added)) {
            // ★ 刚「添加指标和策略」的文件夹 → **立刻切过去**（用户要求 ✓）：
            //   以前只是把分组加进下拉框、列表还停在原来的分组，
            //   用户选完文件夹看不到任何变化 ✗
            this.group = added;
            this.page = 1;
            this.query = '';            // 清掉旧搜索词，否则新分组可能被过滤空
            this.starOnly = false;      // 回到「热门」，不然收藏页可能是空列表
        } else if (this.group && !paths.has(this.group)) {
            this.group = '';
        }
        this._reload();
    }

    private _reload(): void {
        this.options.onCommand('tv_list', {
            id: this.id, query: this.query, group: this.group,
            star: this.starOnly, page: this.page, size: PAGE_SIZE,
            theme: this.options.theme,
        });
    }

    /** 缺缩略图 → 让后端现场截图（串行，避免一次性算 20 个 ✓） */
    private _ensureCard(key: string): void {
        if (!key || this.cards.has(key) || this.pendingCards.has(key)) return;
        this.pendingCards.add(key);
        this.options.onCommand('tv_snapshot', {
            id: this.id, key, theme: this.options.theme,
        });
    }
}

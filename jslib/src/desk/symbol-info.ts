/**
 * SymbolInfoPage —— **标的资讯 / 资料页**（v1.3.7-68）
 *
 * 顶部 = 标的 pill 导航；下面 4 个金融小插件（`pylightcharts/panels`）：
 *
 *   1. **Company Profile**：`QuoteHeader`（名称 / 最新 / 涨跌幅 / 迷你图）+ `TextBlock`
 *   2. **Fundamental Data**：`DataGrid`（缺失 `-`）+ **报告期切换**（股票）
 *   3. **Technical Analysis**：`TechnicalAnalysis` + **周期选择**
 *   4. **Top Stories**：`NewsFeed` + **搜索**（接 `desk_news{action:"search"}` 缓存）
 *
 * 主题：面板颜色全部从主程序的 CSS 变量取（切主题时重建 → 立即跟随 ✓）。
 */
import { showMenu } from './menu';
import { esc } from './pi-util';
import { DataGrid } from '../panels/data-grid';
import { NewsFeed } from '../panels/news';
import { QuoteHeader } from '../panels/quote-header';
import { TechnicalAnalysis } from '../panels/technical';
import { TextBlock } from '../panels/text-block';

export interface SymbolInfoOptions {
    theme: 'light' | 'dark';
    symbols: string[];
    active?: string;
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
}

const PAGE_ID = 'symbol-info:app';

/** 技术面周期候选（秒 → 文案） */
const TA_CYCLES: Array<[number, string]> = [
    [300, '5分'], [900, '15分'], [1800, '30分'], [3600, '1时'],
    [86400, '日线'], [604800, '周线'],
];

export class SymbolInfoPage {
    readonly element: HTMLDivElement;
    private options: SymbolInfoOptions;
    private symbols: string[] = [];
    private symbol = '';
    private data: Record<string, unknown> = {};
    private notice = '';
    private periodIndex = 0;
    private taCycle = 0;
    private query = '';
    private searchRows: Array<Record<string, unknown>> = [];
    private readonly nav: HTMLDivElement;
    private readonly status: HTMLSpanElement;
    private readonly body: HTMLDivElement;
    private profile: QuoteHeader | null = null;
    private about: TextBlock | null = null;
    private grid: DataGrid | null = null;
    private technical: TechnicalAnalysis | null = null;
    private stories: NewsFeed | null = null;
    private periodSelect: HTMLSelectElement | null = null;
    /** 技术分析：可选指标 / 当前模板（`info_symbol.ta_options` ✓） */
    private taOptions: Array<Record<string, unknown>> = [];
    private taTemplate: Array<Record<string, unknown>> = [];
    private taTemplates: string[] = [];
    private taActive = '';
    private taMask: HTMLDivElement | null = null;
    /** Fundamental Data 的宿主（按行数撑高度，避免滚动条 ✓） */
    private fundHost: HTMLDivElement | null = null;
    private cycleSelect: HTMLSelectElement | null = null;
    private searchInput: HTMLInputElement | null = null;

    constructor(options: SymbolInfoOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = `desk-symbol-info theme-${options.theme}`;
        const head = document.createElement('div');
        head.className = 'desk-symbol-head';
        this.nav = document.createElement('div');
        this.nav.className = 'desk-symbol-nav';
        this.status = document.createElement('span');
        this.status.className = 'desk-symbol-status';
        head.append(this.nav, this.status);
        this.body = document.createElement('div');
        this.body.className = 'desk-symbol-body';
        this.element.append(head, this.body);
        this._buildWidgets();
        this.setSymbols(options.symbols || [], options.active || '');
    }

    /** 兼容 app.ts 的统一入口（`page.applyTheme?.(theme)` ✓） */
    applyTheme(theme: 'light' | 'dark'): void {
        this.setTheme(theme);
    }

    /** 切主题：重建插件（面板颜色来自 CSS 变量 ✓） */
    setTheme(theme: 'light' | 'dark'): void {
        this.options.theme = theme;
        this.element.className = `desk-symbol-info theme-${theme}`;
        this._buildWidgets();
        this._render();
    }

    setSymbols(symbols: string[], active = ''): void {
        this.symbols = (symbols || []).filter(Boolean);
        if (active) this.symbol = active;
        if (!this.symbol || !this.symbols.includes(this.symbol)) {
            this.symbol = this.symbols[0] || this.symbol;
        }
        this._renderNav();
    }

    show(): void {
        this.element.style.display = 'flex';
        // 主题可能在别处切过 → 用当前 body 上的 class 对齐一次（无副作用 ✓）
        const light = document.body.classList.contains('theme-light');
        if ((light ? 'light' : 'dark') !== this.options.theme) {
            this.setTheme(light ? 'light' : 'dark');
        }
        this._request();
    }

    hide(): void { this.element.style.display = 'none'; }

    destroy(): void {
        this.profile?.element.remove();
        this.about?.element.remove();
        this.grid?.element.remove();
        this.technical?.element.remove();
        this.stories?.destroy();
        this.element.remove();
    }

    apply(patch: Record<string, unknown>): void {
        const type = String(patch.type || '');
        if (type === 'info_news') {
            // Top Stories 搜索回执（带 query / page ✓）
            if (String(patch.page || '') !== PAGE_ID) return;
            if (!String(patch.query || '')) return;
            this.searchRows = (patch.items || []) as Array<
                Record<string, unknown>>;
            this._renderStories();
            return;
        }
        if (type !== 'info_symbol') return;
        if (String(patch.page || '') !== PAGE_ID) return;
        if (String(patch.symbol || '') !== this.symbol) return;
        this.data = patch;
        this.notice = String(patch.error || '');
        this.periodIndex = Number(patch.period_index || 0);
        this._render();
    }

    // ------------------------------------------------------------ 请求
    private _request(): void {
        if (!this.symbol) {
            this.body.innerHTML = '<div class="desk-info-empty">还没有标的：'
                + '先在图表里打开一个合约 / 本地数据集，再从右键'
                + '「资讯 / 财务…」进来 ✓</div>';
            return;
        }
        this.status.textContent = '加载中…';
        const payload: Record<string, unknown> = {
            symbol: this.symbol, page: PAGE_ID, refresh: true,
        };
        if (this.periodIndex > 0) payload.period = this.periodIndex;
        if (this.taCycle) payload.cycle = this.taCycle;
        this.options.onCommand('info_symbol', payload);
    }

    /**
     * 面板主题：**按当前主题给固定调色板**（和 desk 的 CSS 变量一致 ✓）
     *
     * 不用 `getComputedStyle(--desk-*)`：切主题时 app 可能先调 `applyTheme`
     * 再切 body class → 那时读到的还是旧值（浅色主题下文字发灰 ✗ 用户实测）。
     */
    private _panelTheme(): Record<string, string> {
        const light = this.options.theme === 'light';
        return (light
            ? {
                background: '#ffffff', panel: '#ffffff',
                text: '#1f2329', muted: '#5b6472',
                border: '#dfe3e8', accent: '#2962ff',
                positive: '#d03050', negative: '#089981',
                // ★ DataGrid 的表头 / 悬停 / 斑马线（以前没给 → 浅色主题下
                //   仍是深色样式 ✗ 用户 2026-11-08）
                headerBackground: '#f2f4f7', headerText: '#3a4250',
                rowHover: '#eef2f7', striped: 'rgba(0,0,0,0.02)',
                gridLine: 'rgba(0,0,0,0.06)', scrollbar: '#c3c9d2',
            }
            : {
                background: '#161a20', panel: '#171a21',
                text: '#dfe6f0', muted: '#8b93a1',
                border: '#262b33', accent: '#2962ff',
                positive: '#ef5350', negative: '#26a69a',
                headerBackground: '#1e222d', headerText: '#9aa0aa',
                rowHover: '#1e222d', striped: 'rgba(255,255,255,0.02)',
                gridLine: 'rgba(255,255,255,0.04)', scrollbar: '#3a3f4b',
            }) as never;
    }

    private _buildWidgets(): void {
        this.profile?.element.remove();
        this.about?.element.remove();
        this.grid?.element.remove();
        this.technical?.element.remove();
        this.stories?.destroy();
        this.body.innerHTML = '';
        const theme = this._panelTheme();

        const section = (title: string, cls: string,
                         controls: HTMLElement[] = []): HTMLDivElement => {
            const box = document.createElement('div');
            box.className = `desk-symbol-block ${cls}`;
            const head = document.createElement('div');
            head.className = 'block-title';
            const label = document.createElement('span');
            label.textContent = title;
            head.appendChild(label);
            for (const control of controls) head.appendChild(control);
            const host = document.createElement('div');
            host.className = 'desk-symbol-widget';
            box.append(head, host);
            this.body.appendChild(box);
            return host;
        };

        // ① Company Profile
        const profileHost = section('标的概况', 'profile');
        this.profile = new QuoteHeader({
            compact: false, showSpark: true, theme,
            // ★ 用户 2026-11-08：开 / 高 / 低 / 昨收要保留 2 位小数
            decimals: 2,
            // 成交量 / 持仓量按整数（别显示 12,345.00 ✗）
            intFields: ['volume', 'open_interest'],
        }, profileHost);
        this.about = new TextBlock({ text: '', theme }, profileHost);

        // ② Fundamental Data + 报告期切换
        this.periodSelect = document.createElement('select');
        this.periodSelect.className = 'desk-symbol-select';
        this.periodSelect.title = '切换报告期';
        this.periodSelect.addEventListener('change', () => {
            this.periodIndex = Number(this.periodSelect?.value || 0);
            this._request();
        });
        const fundHost = section('基本面数据', 'fundamental',
                                 [this.periodSelect]);
        this.fundHost = fundHost;
        this.grid = new DataGrid({
            columns: [
                { key: 'name', title: '指标', width: 180 },
                // ★ 数值列给足宽度（以前太窄，长数字被截 ✗ 用户 2026-11-08）
                { key: 'value', title: '数值', width: 150, align: 'right' },
            ],
            rowKey: 'name',
            rowHeight: 24,
            fontSize: 12,
            searchable: false,
            theme: { ...theme, background: 'transparent' },
        }, fundHost);

        // ③ Technical Analysis + 周期选择
        this.cycleSelect = document.createElement('select');
        this.cycleSelect.className = 'desk-symbol-select';
        this.cycleSelect.title = '技术面周期';
        const current = document.createElement('option');
        current.value = '0';
        current.textContent = '页面周期';
        this.cycleSelect.appendChild(current);
        for (const [value, label] of TA_CYCLES) {
            const option = document.createElement('option');
            option.value = String(value);
            option.textContent = label;
            this.cycleSelect.appendChild(option);
        }
        this.cycleSelect.value = String(this.taCycle);
        this.cycleSelect.addEventListener('change', () => {
            this.taCycle = Number(this.cycleSelect?.value || 0);
            this._request();
        });
        const taButton = document.createElement('button');
        taButton.className = 'desk-symbol-btn';
        taButton.textContent = '⚙ 设置';
        taButton.title = '选择参与技术分析的指标（可保存为模板）';
        taButton.addEventListener('click', () => this._openTaDialog());
        const taHost = section('技术分析', 'technical',
                               [this.cycleSelect, taButton]);
        this.technical = new TechnicalAnalysis({ theme }, taHost);

        // ④ Top Stories + 搜索
        this.searchInput = document.createElement('input');
        this.searchInput.className = 'desk-symbol-search';
        this.searchInput.placeholder = '搜资讯…';
        this.searchInput.value = this.query;
        let timer = 0;
        this.searchInput.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            this._search();
        });
        this.searchInput.addEventListener('input', () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => this._search(), 350);
        });
        const newsHost = section('最新资讯', 'stories', [this.searchInput]);
        this.stories = new NewsFeed({
            items: [], theme,
            // ★ v1.3.7-72：左键不动作；**双击开原文**；右键菜单（原文 / 图表）
            onItemDoubleClick: (index: number) => {
                const row = this._storyAt(index);
                if (row.url) {
                    this.options.onCommand('open_url', { url: row.url });
                }
            },
            onItemContextMenu: (index: number, event: MouseEvent) => {
                const row = this._storyAt(index);
                showMenu(event.clientX, event.clientY, [
                    {
                        label: '打开原文',
                        disabled: !row.url,
                        run: () => this.options.onCommand(
                            'open_url', { url: row.url }),
                    },
                    {
                        label: '打开图表',
                        // 标的资讯页本身就知道是哪个标的 → 一定能跳 ✓
                        run: () => this._openChart(row),
                    },
                ]);
            },
        }, newsHost);
        this.stories.element.style.height = 'auto';
        this.stories.element.style.maxHeight = '360px';
    }

    /** Top Stories 搜索：搜本地资讯缓存（`info_news{query}` ✓） */
    private _search(): void {
        this.query = String(this.searchInput?.value || '').trim();
        if (!this.query) {
            this.searchRows = [];
            this._renderStories();
            return;
        }
        this.options.onCommand('info_news', {
            kind: 'flash', query: this.query, limit: 30, page: PAGE_ID,
        });
    }

    private _renderNav(): void {
        this.nav.innerHTML = '';
        for (const symbol of this.symbols) {
            const button = document.createElement('button');
            button.className = 'desk-symbol-pill'
                + (symbol === this.symbol ? ' on' : '');
            button.textContent = symbol;
            button.title = symbol;
            button.addEventListener('click', () => {
                if (symbol === this.symbol) return;
                this.symbol = symbol;
                this.data = {};
                this.periodIndex = 0;
                this.searchRows = [];
                if (this.searchInput) this.searchInput.value = '';
                this._renderNav();
                this._request();
            });
            this.nav.appendChild(button);
        }
        if (!this.symbols.length) {
            this.nav.innerHTML = '<span class="desk-symbol-empty">'
                + '（没有标的）</span>';
        }
    }

    private _render(): void {
        const data = this.data || {};
        const name = String(
            (data.quote as Record<string, unknown> | undefined)?.name
            || data.name || '');
        const source = data.futu ? '富途' : 'AkShare';
        this.status.textContent = this.notice
            ? '数据源异常'
            : [name, source].filter(Boolean).join(' · ');
        this.status.title = this.notice;

        // ① Company Profile
        const quote = (data.quote || {}) as Record<string, unknown>;
        this.profile?.setData({
            symbol: this.symbol,
            name: String(quote.name || name || ''),
            last: Number(quote.last) || undefined,
            chg_pct: Number(quote.chg_pct ?? NaN),
            high: Number(quote.high) || undefined,
            low: Number(quote.low) || undefined,
            open: Number(quote.open) || undefined,
            pre_close: Number(quote.pre_close) || undefined,
            volume: Number(quote.volume) || undefined,
            open_interest: Number(quote.open_interest) || undefined,
            spark: (quote.spark || []) as number[],
        });
        this.about?.setText(String(data.profile_text || ''));

        // ② Fundamental Data（报告期下拉 ✓）
        const rows = (data.fundamentals || []) as Array<Record<string, unknown>>;
        this.grid?.setRows(rows.map((row) => ({
            name: String(row.name || ''),
            value: String(row.value ?? '-') || '-',
        })));
        // ★ 按行数撑开高度（行高 24 + 表头 28 + 边框）→ 没有滚动条 ✓
        if (this.fundHost) {
            this.fundHost.style.height =
                `${Math.max(1, rows.length) * 24 + 34}px`;
        }
        const periods = (data.periods || []) as string[];
        if (this.periodSelect) {
            if (periods.length) {
                this.periodSelect.style.display = '';
                this.periodSelect.innerHTML = periods.map((item, index) =>
                    `<option value="${index}">${item}</option>`).join('');
                this.periodSelect.value = String(this.periodIndex);
            } else {
                this.periodSelect.style.display = 'none';
            }
        }

        // ③ Technical Analysis（周期下拉 ✓）
        this.technical?.setData(
            (data.technical || {}) as never);
        const taOptions = (data.ta_options || {}) as Record<string, unknown>;
        this.taOptions = (taOptions.items || []) as Array<
            Record<string, unknown>>;
        this.taTemplate = (taOptions.template || []) as Array<
            Record<string, unknown>>;
        this.taTemplates = (taOptions.templates || []) as string[];
        this.taActive = String(taOptions.active || '');
        if (this.cycleSelect) {
            const used = Number((data.technical as Record<string, unknown>
                | undefined)?.cycle || 0);
            if (used > 0 && !this.taCycle) {
                const match = TA_CYCLES.find(([value]) => value === used);
                if (match) {
                    const option = document.createElement('option');
                    option.value = String(used);
                    option.textContent = match[1];
                    this.cycleSelect.appendChild(option);
                    this.cycleSelect.value = String(used);
                }
            }
        }

        // ④ Top Stories
        this._renderStories();

        if (!rows.length && !this.query && !this.notice) {
            this.status.textContent = '正在获取 ' + this.symbol + ' 的资料…';
        }
    }

    /** 当前 Top Stories 的第 N 条（搜索时用搜索结果 ✓） */
    private _storyAt(index: number): Record<string, unknown> {
        const rows = (this.searchRows.length && this.query
            ? this.searchRows : (this.data.stories || [])) as Array<
            Record<string, unknown>>;
        return (rows[index] || {}) as Record<string, unknown>;
    }

    /** 「打开图表」：本页标的已知 → 直接跳（时间有效才跳 ✓） */
    private _openChart(row: Record<string, unknown>): void {
        const seconds = this._epochOf(String(row.time || ''));
        this.options.onCommand('news_focus', {
            symbol: this.symbol,
            time: seconds,
            label: String(row.title || '').slice(0, 20),
        });
    }

    /** `2026-11-10 09:00` → unix 秒（本地时区；解析不了返回 0 ✓） */
    private _epochOf(text: string): number {
        const raw = String(text || '').trim();
        if (!raw) return 0;
        const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/
            .exec(raw);
        if (!match) return 0;
        const stamp = new Date(Number(match[1]), Number(match[2]) - 1,
                               Number(match[3]), Number(match[4] || 0),
                               Number(match[5] || 0), 0);
        const seconds = Math.floor(stamp.getTime() / 1000);
        return Number.isFinite(seconds) ? seconds : 0;
    }

    /**
     * 「技术分析 ⚙ 设置」：选指标 + 配信号（阈值 / 比较）+ 保存模板 ✓
     */
    private _openTaDialog(): void {
        this.taMask?.remove();
        const mask = document.createElement('div');
        mask.className = 'desk-symbol-mask';
        mask.addEventListener('click', (event) => {
            if (event.target === mask) this._closeTaDialog();
        });
        const box = document.createElement('div');
        box.className = 'desk-symbol-dialog';
        const head = document.createElement('div');
        head.className = 'dialog-head';
        const title = document.createElement('b');
        title.textContent = '技术分析指标';
        const close = document.createElement('button');
        close.className = 'desk-symbol-btn';
        close.textContent = '×';
        close.addEventListener('click', () => this._closeTaDialog());
        head.append(title, close);

        const search = document.createElement('input');
        search.className = 'desk-symbol-search dialog-search';
        search.placeholder = '搜索指标（如 rsi / macd / ma）';

        const list = document.createElement('div');
        list.className = 'dialog-list';
        const chosen = new Map<string, Record<string, unknown>>();
        for (const row of this.taTemplate) {
            chosen.set(String(row.key || ''), {
                key: String(row.key || ''),
                group: String(row.group || 'other'),
                signal: { ...(row.signal as Record<string, unknown> || {}) },
            });
        }
        const render = (): void => {
            const needle = search.value.trim().toLowerCase();
            list.textContent = '';
            const groups: Record<string, string> = {
                oscillator: '震荡指标', trend: '趋势指标', other: '其他指标',
            };
            let count = 0;
            for (const key of ['oscillator', 'trend', 'other']) {
                const rows = this.taOptions.filter((row) => {
                    if (String(row.group || 'other') !== key) return false;
                    if (!needle) return true;
                    return `${row.label || ''} ${row.key || ''}`
                        .toLowerCase().includes(needle);
                });
                if (!rows.length) continue;
                const groupHead = document.createElement('div');
                groupHead.className = 'dialog-group';
                groupHead.textContent = groups[key];
                list.appendChild(groupHead);
                for (const row of rows) {
                    const id = String(row.key || '');
                    const line = String(row.line || '');
                    const item = document.createElement('label');
                    item.className = 'dialog-row';
                    const check = document.createElement('input');
                    check.type = 'checkbox';
                    check.checked = chosen.has(id);
                    const name = document.createElement('span');
                    name.className = 'name';
                    name.textContent = String(row.label || id);
                    const spec = (row.signal || {}) as Record<string, unknown>;
                    const kind = document.createElement('select');
                    kind.className = 'mini';
                    kind.innerHTML = '<option value="threshold">阈值</option>'
                        + '<option value="compare">与前值比较</option>';
                    kind.value = String(spec.kind || 'threshold');
                    const direction = document.createElement('select');
                    direction.className = 'mini';
                    direction.innerHTML = '<option value="1">上方看多</option>'
                        + '<option value="-1">上方看空</option>';
                    direction.value = String(spec.direction || 1);
                    const level = document.createElement('input');
                    level.className = 'mini num';
                    level.type = 'number';
                    level.step = 'any';
                    level.value = String(spec.level ?? 0);
                    const offset = document.createElement('select');
                    offset.className = 'mini';
                    offset.innerHTML = '<option value="-2">前 1 根</option>'
                        + '<option value="-3">前 2 根</option>'
                        + '<option value="-4">前 3 根</option>';
                    offset.value = String(spec.offset || -2);
                    const sync = (): void => {
                        const compare = kind.value === 'compare';
                        offset.style.display = compare ? '' : 'none';
                        level.style.display = compare ? 'none' : '';
                    };
                    sync();
                    const save = (): void => {
                        if (!check.checked) {
                            chosen.delete(id);
                            return;
                        }
                        chosen.set(id, {
                            key: id, group: key, line,
                            signal: {
                                kind: kind.value,
                                direction: Number(direction.value),
                                level: Number(level.value) || 0,
                                offset: Number(offset.value) || -2,
                                group: key,
                            },
                        });
                    };
                    check.addEventListener('change', () => {
                        if (check.checked) item.classList.add('on');
                        else item.classList.remove('on');
                        save();
                    });
                    for (const control of [kind, direction, level, offset]) {
                        control.addEventListener('change', () => {
                            save();
                            sync();
                        });
                    }
                    item.classList.toggle('on', check.checked);
                    item.append(check, name, kind, direction, level, offset);
                    list.appendChild(item);
                    count += 1;
                }
            }
            if (!count) {
                const empty = document.createElement('div');
                empty.className = 'dialog-empty';
                empty.textContent = this.taOptions.length
                    ? '没有匹配的指标' : '（这个标的没有可选指标；先打开图表再试）';
                list.appendChild(empty);
            }
        };
        search.addEventListener('input', render);
        render();

        // ★ v1.3.7-74：模板下拉（多套）+ 另存为 ✓
        const bar = document.createElement('div');
        bar.className = 'dialog-bar';
        const pick = document.createElement('select');
        pick.className = 'mini';
        pick.innerHTML = '<option value="">默认模板</option>'
            + this.taTemplates.map((name) => `<option value="${esc(name)}"`
                + (name === this.taActive ? ' selected' : '') + `>`
                + `${esc(name)}</option>`).join('');
        pick.addEventListener('change', () => {
            this.options.onCommand('ta_template', {
                action: 'activate', name: pick.value,
            });
            this.options.onCommand('ta_snapshot', {
                symbol: this.symbol, page: PAGE_ID,
            });
        });
        const nameInput = document.createElement('input');
        nameInput.className = 'mini name';
        nameInput.placeholder = '模板名（另存为）';
        bar.append(pick, nameInput);

        // ★ v1.3.7-99：图表右上角的「技术分析标签」开关（用户自己选 ✓）
        const badgeRow = document.createElement('div');
        badgeRow.className = 'dialog-bar';
        const badgeLabel = document.createElement('label');
        badgeLabel.className = 'inline badge-toggle';
        const badgeInput = document.createElement('input');
        badgeInput.type = 'checkbox';
        badgeInput.dataset.taBadge = '1';
        const values = (window as unknown as {
            __desk?: { settingsValues?: Record<string, unknown> };
        }).__desk?.settingsValues || {};
        badgeInput.checked = values.ta_badge !== false;
        const badgeText = document.createElement('span');
        badgeText.textContent = '在图表右上角显示技术分析标签'
            + '（TA 多/空/中立，悬停看明细）';
        badgeLabel.append(badgeInput, badgeText);
        badgeInput.addEventListener('change', () => {
            this.options.onCommand('set_setting', {
                key: 'ta_badge', value: badgeInput.checked,
            });
        });
        badgeRow.append(badgeLabel);

        const foot = document.createElement('div');
        foot.className = 'dialog-foot';
        const apply = document.createElement('button');
        apply.className = 'desk-symbol-btn primary';
        apply.textContent = '应用';
        apply.addEventListener('click', () => {
            this._closeTaDialog();
            this.options.onCommand('ta_snapshot', {
                symbol: this.symbol, page: PAGE_ID,
                rows: [...chosen.values()],
            });
        });
        const saveBtn = document.createElement('button');
        saveBtn.className = 'desk-symbol-btn';
        saveBtn.textContent = '保存为模板';
        saveBtn.addEventListener('click', () => {
            const name = nameInput.value.trim();
            this.options.onCommand('ta_template', name
                ? { action: 'save', name, items: [...chosen.values()] }
                : { items: [...chosen.values()] });
        });
        const reset = document.createElement('button');
        reset.className = 'desk-symbol-btn';
        reset.textContent = '恢复默认';
        reset.addEventListener('click', () => {
            this.options.onCommand('ta_template', { reset: true });
            this.options.onCommand('ta_snapshot', {
                symbol: this.symbol, page: PAGE_ID, rows: [],
            });
        });
        const cancel = document.createElement('button');
        cancel.className = 'desk-symbol-btn';
        cancel.textContent = '取消';
        cancel.addEventListener('click', () => this._closeTaDialog());
        foot.append(apply, saveBtn, reset, cancel);

        box.append(head, search, list, bar, badgeRow, foot);
        mask.appendChild(box);
        document.body.appendChild(mask);
        this.taMask = mask;
    }

    private _closeTaDialog(): void {
        this.taMask?.remove();
        this.taMask = null;
    }

    private _renderStories(): void {
        if (this.searchRows.length && this.query) {
            this.stories?.setItems(this.searchRows.map((row) => ({
                title: String(row.title || ''),
                source: String(row.source || ''),
                time: String(row.published || ''),
                url: String(row.url || ''),
            })) as never);
            return;
        }
        const stories = (this.data.stories || []) as Array<
            Record<string, unknown>>;
        this.stories?.setItems(stories.map((row) => ({
            title: String(row.title || ''),
            source: String(row.source || ''),
            time: String(row.time || ''),
            url: String(row.url || ''),
        })) as never);
    }
}

export { PAGE_ID as SYMBOL_INFO_PAGE_ID };

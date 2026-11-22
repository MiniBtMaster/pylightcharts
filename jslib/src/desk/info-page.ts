/**
 * InfoPage —— **资讯中心**（v1.3.7-62，P0）
 *
 * 三个分区（左栏，和「指标和策略」页同一套风格）：
 *
 * | 分区 | 数据源（AkShare） | 刷新 |
 * | --- | --- | --- |
 * | 快讯 | `stock_info_global_sina`（备：`stock_info_global_em`） | 60s 自动 |
 * | 要闻 | `stock_news_main_cx`（财新精选） | 手动 / 10min |
 * | 日历 | `news_economic_baidu`（按天传日期） | 手动 / 6h |
 *
 * 行为约定：
 * * 打开页面就发一次命令 → 后端**先回缓存**（立刻有内容），再后台刷新推送；
 * * 后端没装 AkShare → 显示一条安装命令（不影响其它页面）；
 * * 条目右键：复制标题 / 打开原文 / 让 AI 分析（走 PI 会话，`pi_send`）；
 * * 条目里的链接 / 股票代码不做自动跳转（P1 再做联动）。
 */
import { MenuItem, showMenu } from './menu';
import { esc } from './pi-util';

export interface InfoPageOptions {
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
}

type InfoKind = 'flash' | 'market' | 'calendar' | 'macro' | 'futures';

interface NewsItem {
    id?: string;
    title?: string;
    summary?: string;
    source?: string;
    url?: string;
    published?: string;
    kind?: string;
    symbol?: string;
}

interface CalendarItem {
    id?: string;
    day?: string;
    time?: string;
    region?: string;
    event?: string;
    actual?: string;
    forecast?: string;
    previous?: string;
    importance?: number;
}

const KIND_LABEL: Record<InfoKind, string> = {
    flash: '快讯',
    market: '要闻',
    calendar: '日历',
    macro: '宏观',
    futures: '期货',
};

/** 自动刷新间隔（只有快讯开 ✓） */
const AUTO_MS = 60000;

export class InfoPage {
    readonly element: HTMLDivElement;
    private readonly options: InfoPageOptions;
    private kind: InfoKind = 'flash';
    private news: NewsItem[] = [];
    private calendar: CalendarItem[] = [];
    private macro: Array<Record<string, unknown>> = [];
    /** 期货 tab：当前标的（默认取图表里第一个合约 ✓） */
    private futuresSymbol = '';
    private futuresData: Record<string, unknown> = {};
    /** 图表里的合约（多布局会一起带上） */
    private charts: string[] = [];
    private query = '';
    private status: Record<string, unknown> = {};
    /** 自选 / 持仓关键词（`info_related` 补丁 ✓） */
    private relatedSymbols: string[] = [];
    private relatedNames: string[] = [];
    private relatedOnly = false;
    /** AI 摘要：上次缓存 / 运行状态 */
    private summary: Record<string, unknown> = {};
    private summaryAt = 0;
    private notice = '';
    private readonly list: HTMLDivElement;
    private readonly tabs = new Map<InfoKind, HTMLButtonElement>();
    private readonly search: HTMLInputElement;
    private readonly statusChip: HTMLSpanElement;
    private relatedButton: HTMLButtonElement | null = null;
    private timer: number | null = null;

    constructor(options: InfoPageOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = `desk-info theme-${options.theme}`;

        const head = document.createElement('div');
        head.className = 'desk-info-head';
        const nav = document.createElement('div');
        nav.className = 'desk-info-nav';
        for (const kind of ['flash', 'market', 'calendar', 'macro',
                            'futures'] as InfoKind[]) {
            const button = document.createElement('button');
            button.className = 'desk-info-tab';
            button.textContent = KIND_LABEL[kind];
            button.addEventListener('click', () => this.open(kind));
            nav.appendChild(button);
            this.tabs.set(kind, button);
        }
        this.search = document.createElement('input');
        this.search.className = 'desk-info-search';
        this.search.placeholder = '搜索已缓存的资讯（回车）';
        this.search.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            this.query = this.search.value.trim();
            this._request();
        });
        this.statusChip = document.createElement('span');
        this.statusChip.className = 'desk-info-status';
        this.statusChip.textContent = '…';
        const refresh = document.createElement('button');
        refresh.className = 'desk-info-btn';
        refresh.textContent = '刷新';
        refresh.addEventListener('click', () => this._request(true));
        // ★ AI 摘要：把这批资讯丢给 PI 会话（复用 pi_send ✓）
        const relate = document.createElement('button');
        relate.className = 'desk-info-btn';
        relate.textContent = '只看自选/持仓';
        relate.title = '按自选、持仓、已打开图表的合约过滤资讯';
        relate.addEventListener('click', () => {
            this.relatedOnly = !this.relatedOnly;
            relate.classList.toggle('on', this.relatedOnly);
            this.options.onCommand('info_related', {});
            this._render();
        });
        this.relatedButton = relate;
        const summarize = document.createElement('button');
        summarize.className = 'desk-info-btn';
        summarize.textContent = 'AI 摘要';
        summarize.title = '让 PI 总结当前资讯（同一天复用上次结果；按住 Shift 点重新生成）';
        summarize.addEventListener('click', (event) => {
            this._summarize(!event.shiftKey);
        });
        head.append(nav, this.search, this.statusChip, relate, summarize,
                    refresh);

        this.list = document.createElement('div');
        this.list.className = 'desk-info-list';
        this.element.append(head, this.list);
        this._renderTabs();
        this._render();
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.element.className = `desk-info theme-${theme}`;
    }

    show(): void {
        this.element.style.display = 'flex';
        this._request();
        this._syncTimer();
        // 顺带问一次数据源状态（右上角徽标 ✓）
        this.options.onCommand('info_status', {});
        // 自选 / 持仓关键词（资讯右键「打开图表」要认标的 ✓）
        this.options.onCommand('info_related', {});
    }

    hide(): void {
        this.element.style.display = 'none';
        this._syncTimer();
    }

    destroy(): void {
        if (this.timer) window.clearInterval(this.timer);
        this.element.remove();
    }

    /** 图表里的合约（期货 tab 的标的下拉；多布局会一起带上 ✓） */
    setCharts(symbols: string[], active = ''): void {
        this.charts = (symbols || []).filter(Boolean);
        if (active && !this.futuresSymbol) this.futuresSymbol = active;
        if (!this.futuresSymbol && this.charts.length) {
            this.futuresSymbol = this.charts[0];
        }
        if (this.kind === 'futures') this._render();
    }

    /** 切分区（也供外部：`desk_info_open{kind}` 用 ✓） */
    open(kind: InfoKind): void {
        this.kind = KIND_LABEL[kind] ? kind : 'flash';
        this.query = '';
        this.search.value = '';
        this._renderTabs();
        this._request();
        this._syncTimer();
    }

    /** 后端补丁（`info_news` / `info_calendar` / `info_status` ✓） */
    apply(patch: Record<string, unknown>): void {
        const type = String(patch.type || '');
        if (type === 'info_status') {
            this.status = patch;
            this._renderStatus();
            return;
        }
        if (type === 'info_news') {
            const kind = String(patch.kind || 'flash');
            // 只认当前分区（别的分区的迟到补丁不覆盖列表 ✗）
            if (kind !== 'flash' && kind !== 'market' && kind !== 'calendar') {
                return;
            }
            if (kind !== this.kind) return;
            this.news = (patch.items || []) as NewsItem[];
            this.notice = String(patch.error || '');
            this._renderStatus();
            this._render();
            return;
        }
        if (type === 'info_related') {
            this.relatedSymbols = (patch.symbols || []) as string[];
            this.relatedNames = (patch.names || []) as string[];
            this.relatedButton?.classList.toggle('on', this.relatedOnly);
            if (this.relatedOnly) this._render();
            return;
        }
        if (type === 'ai_summary') {
            this.summary = patch;
            const error = String(patch.error || '');
            if (error) {
                this.options.onToast?.('warning', error);
                return;
            }
            const cached = patch.cached === true;
            this.summaryAt = Number(patch.at || Date.now() / 1000);
            this.options.onToast?.('info', cached
                ? '今天的摘要已在缓存（按住 Shift 点可重新生成）'
                : '正在生成摘要，稍等…');
            return;
        }
        if (type === 'info_macro') {
            // ★ v1.3.7-70：逐步推送 / 缓存补丁 → 按 key 合并（别把已有序列清空 ✗）
            const incoming = (patch.items || []) as Array<
                Record<string, unknown>>;
            const merged = new Map<string, Record<string, unknown>>();
            for (const item of this.macro) {
                merged.set(String(item.key || ''), item);
            }
            for (const item of incoming) {
                merged.set(String(item.key || ''), item);
            }
            this.macro = [...merged.values()];
            this.notice = String(patch.error || '');
            this._renderStatus();
            if (this.kind === 'macro') this._render();
            return;
        }
        if (type === 'info_symbol') {
            // 资讯中心的「期货」tab 只认自己的请求（标的资料页有自己的页面 ✓）
            if (String(patch.page || '') === 'symbol-info:app') return;
            this.futuresData = patch;
            this.notice = String(patch.error || '');
            if (this.kind === 'futures') this._render();
            return;
        }
        if (type === 'info_calendar') {
            // 首页也会收到这个补丁（events），带 items 才算资讯中心的 ✓
            if (!Array.isArray(patch.items)) return;
            this.calendar = patch.items as CalendarItem[];
            if (this.kind === 'calendar') {
                this.notice = '';
                this._renderStatus();
                this._render();
            }
            return;
        }
    }

    // ------------------------------------------------------------ 内部
    private _request(refresh = false): void {
        if (this.kind === 'calendar') {
            this.options.onCommand('info_calendar',
                                   { days: 3, refresh });
            return;
        }
        if (this.kind === 'macro') {
            this.options.onCommand('info_macro', { limit: 12, refresh });
            return;
        }
        if (this.kind === 'futures') {
            if (!this.futuresSymbol && this.charts.length) {
                this.futuresSymbol = this.charts[0];
            }
            if (!this.futuresSymbol) return;
            this.options.onCommand('info_symbol', {
                symbol: this.futuresSymbol, page: 'info:app',
            });
            return;
        }
        this.options.onCommand('info_news', {
            kind: this.kind,
            limit: 60,
            refresh,
            query: this.query,
        });
    }

    /**
     * 「AI 摘要」：**后端按天缓存**（同一天复用上次会话，不重复烧 token ✓）
     *
     * 按住 Shift 点 = 重新生成（`regenerate: true`）。
     */
    private _summarize(useCache = true): void {
        this.options.onCommand('ai_summary',
                               { regenerate: useCache === false });
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

    private _syncTimer(): void {
        const want = this.kind === 'flash'
            && this.element.style.display !== 'none';
        if (want && !this.timer) {
            this.timer = window.setInterval(() => this._request(), AUTO_MS);
        } else if (!want && this.timer) {
            window.clearInterval(this.timer);
            this.timer = null;
        }
    }

    private _renderTabs(): void {
        for (const [kind, button] of this.tabs) {
            button.classList.toggle('on', kind === this.kind);
        }
        const newsKind = this.kind === 'flash' || this.kind === 'market';
        this.search.style.display = newsKind ? '' : 'none';
    }

    private _renderStatus(): void {
        const installed = this.status.installed !== false;
        if (!installed) {
            this.statusChip.textContent = '未安装 AkShare';
            this.statusChip.classList.add('warn');
            this.statusChip.title = String(this.status.hint
                || 'pip install "minibt[news]"');
            return;
        }
        this.statusChip.classList.remove('warn');
        const cache = (this.status.cache || {}) as Record<string, unknown>;
        this.statusChip.textContent = this.notice
            ? '刷新失败'
            : `AkShare ${String(this.status.version || '')}`.trim();
        const summaryAt = Number(this.summaryAt || 0);
        const hasSummary = !!String(this.summary.text || '');
        this.statusChip.title = this.notice
            || `缓存：资讯 ${String(cache.news || 0)} 条 · `
            + `日历 ${String(cache.calendar || 0)} 条`
            + (summaryAt
                ? ` · 今天摘要：${hasSummary ? '已缓存' : '生成中'}`
                    + `（${new Date(summaryAt * 1000)
                        .toLocaleTimeString('zh-CN', { hour12: false })}）`
                : '');
    }

    private _render(): void {
        if (this.kind === 'calendar') {
            this._renderCalendar();
        } else if (this.kind === 'macro') {
            this._renderMacro();
        } else if (this.kind === 'futures') {
            this._renderFutures();
        } else {
            this._renderNews();
        }
    }

    /** 宏观：每个指标一张小卡（最新值 + 最近 6 期）✓ */
    private _renderMacro(): void {
        if (!this.macro.length) {
            this.list.innerHTML = this._empty();
            return;
        }
        this.list.innerHTML = this.macro.map((item) => {
            const points = (item.points || []) as Array<[string, number]>;
            const latest = (item.latest || []) as [string, number];
            const spark = points.slice(-6).map((point) => '<span class="mv">'
                + '<i>' + esc(point[0]) + '</i><b>' + point[1] + '</b></span>')
                .join('');
            return '<div class="desk-info-macro">'
                + '<div class="macro-head"><b>' + esc(item.name || item.key)
                + '</b><span class="macro-latest">' + (latest[1] ?? '')
                + ' <em>' + esc(item.unit || '') + '</em></span></div>'
                + '<div class="macro-meta">最新：' + esc(latest[0] || '')
                + '</div><div class="macro-points">' + spark + '</div></div>';
        }).join('');
    }

    /** 期货：合约规则 + 库存 + 基差（标的可切换 ✓） */
    private _renderFutures(): void {
        const data = this.futuresData || {};
        const choices = (this.charts.length ? this.charts
            : [this.futuresSymbol]).filter(Boolean);
        const options = choices.map((symbol) => '<option value="'
            + esc(symbol) + '"' + (symbol === this.futuresSymbol
                ? ' selected' : '') + '>' + esc(symbol) + '</option>').join('');
        const select = '<div class="desk-info-pick"><span>标的</span>'
            + '<select class="desk-info-select">' + options + '</select>'
            + '<button class="desk-info-btn" data-refresh>刷新</button></div>';
        if (!this.futuresSymbol) {
            this.list.innerHTML = select + '<div class="desk-info-empty">'
                + '先在图表里打开一个合约（期货 / 本地数据都可以）</div>';
            this._bindFuturesControls();
            return;
        }
        if (!data || Object.keys(data).length === 0) {
            this.list.innerHTML = select + this._empty();
            this._bindFuturesControls();
            return;
        }
        const contract = (((data.contract || {}) as Record<string, unknown>)
            .items || []) as Array<Record<string, unknown>>;
        const inv = (data.inventory || {}) as Record<string, unknown>;
        const basis = (data.basis || {}) as Record<string, unknown>;
        const profile = (data.profile || {}) as Record<string, unknown>;
        const rows: string[] = [select];
        const profileRows = (profile.items || []) as Array<
            Record<string, unknown>>;
        if (profileRows.length) {
            rows.push('<div class="desk-info-block"><div class="block-title">'
                + '概览</div>' + profileRows.map((row) => '<div class="kv"><i>'
                    + esc(row.label) + '</i><b>' + esc(row.value) + '</b></div>')
                    .join('') + '</div>');
        }
        if (contract.length) {
            const row = contract[0];
            rows.push('<div class="desk-info-block"><div class="block-title">'
                + '合约规则</div>'
                + '<div class="kv"><i>品种</i><b>' + esc(row.variety)
                + '</b></div><div class="kv"><i>交易所</i><b>'
                + esc(row.exchange) + '</b></div>'
                + '<div class="kv"><i>保证金</i><b>' + esc(row.margin)
                + '%</b></div><div class="kv"><i>涨跌停</i><b>'
                + esc(row.limit) + '%</b></div>'
                + '<div class="kv"><i>合约乘数</i><b>' + esc(row.multiple)
                + '</b></div><div class="kv"><i>最小变动</i><b>'
                + esc(row.tick) + '</b></div></div>');
        }
        const latest = (inv.latest || null) as Record<string, unknown> | null;
        if (latest) {
            rows.push('<div class="desk-info-block"><div class="block-title">'
                + '库存</div><div class="kv"><i>日期</i><b>' + esc(latest.date)
                + '</b></div><div class="kv"><i>库存</i><b>'
                + esc(latest.inventory) + '</b></div>'
                + '<div class="kv"><i>增减</i><b>' + esc(latest.change)
                + '</b></div></div>');
        }
        if (basis && !basis.empty) {
            rows.push('<div class="desk-info-block"><div class="block-title">'
                + '基差</div><div class="kv"><i>日期</i><b>' + esc(basis.date)
                + '</b></div><div class="kv"><i>现货</i><b>'
                + esc(basis.spot_price) + '</b></div>'
                + '<div class="kv"><i>主力</i><b>'
                + esc(basis.dominant_contract) + ' '
                + esc(basis.dominant_price) + '</b></div>'
                + '<div class="kv"><i>主力基差</i><b>'
                + esc(basis.dominant_basis) + '</b></div></div>');
        }
        // ★ 相关资讯（后端 `info_symbol.stories`：专属源 + 全市场关键词 ✓）
        const stories = (data.stories || []) as Array<Record<string, unknown>>;
        if (stories.length) {
            rows.push('<div class="desk-info-block"><div class="block-title">'
                + '相关资讯</div><div class="desk-info-news">'
                + stories.slice(0, 12).map((row) => {
                    const url = String(row.url || '');
                    return `<div class="news-row"${url
                        ? ` data-url="${esc(url)}"` : ''}>`
                        + `<div class="title">${esc(row.title || '')}</div>`
                        + `<div class="meta">${esc(row.source || '')} `
                        + `${esc(String(row.time || '').slice(5))}</div></div>`;
                }).join('') + '</div></div>');
        }
        if (rows.length === 1) rows.push(this._empty());
        this.list.innerHTML = rows.join('');
        this._bindFuturesControls();
        for (const node of Array.from(
                this.list.querySelectorAll<HTMLElement>('.desk-info-news .news-row'))) {
            const url = node.dataset.url || '';
            if (!url) continue;
            node.addEventListener('click', () => {
                this.options.onCommand('open_url', { url });
            });
        }
    }

    private _bindFuturesControls(): void {
        const select = this.list.querySelector(
            '.desk-info-select') as HTMLSelectElement | null;
        select?.addEventListener('change', () => {
            this.futuresSymbol = select.value;
            this._request(true);
        });
        const refresh = this.list.querySelector(
            '[data-refresh]') as HTMLButtonElement | null;
        refresh?.addEventListener('click', () => this._request(true));
    }

    /** 资讯右键菜单：打开原文 / 打开图表（找不到标的时禁用并提示 ✓） */
    private _showNewsMenu(item: NewsItem, x: number, y: number): void {
        const symbol = this._symbolOf(item, this.relatedSymbols,
                                      this.relatedNames);
        const menu: MenuItem[] = [
            {
                label: '打开原文',
                disabled: !item.url,
                run: () => this.options.onCommand('open_url',
                                                  { url: item.url }),
            },
            {
                label: symbol ? `打开图表（${symbol}）` : '打开图表（找不到标的）',
                run: () => {
                    if (!symbol) {
                        this.options.onToast?.('warning',
                            '这条资讯没有对应标的（综合 / 宏观类），'
                            + '没法打开图表');
                        return;
                    }
                    const seconds = this._epochOf(item.published || '');
                    this.options.onCommand('news_focus', {
                        symbol, time: seconds,
                        label: String(item.title || '').slice(0, 20),
                    });
                },
            },
            {
                label: '复制标题',
                run: () => {
                    this.options.onCommand('clipboard_set', {
                        text: String(item.title || ''),
                    });
                    this.options.onToast?.('success', '标题已复制');
                },
            },
            {
                label: '让 AI 分析这条',
                run: () => {
                    const text = `请结合行情分析这条资讯的影响：`
                        + `
【${item.source || ''}】`
                        + `${item.title || ''}
${item.summary || ''}`
                        + (item.url ? `
${item.url}` : '');
                    this.options.onCommand('pi_send', {
                        id: '', text,
                        title: String(item.title || '').slice(0, 40),
                    });
                    this.options.onToast?.('info',
                        '已发给 PI 会话（新建会话里查看）');
                },
            },
        ];
        showMenu(x, y, menu);
    }

    /**
     * 从资讯里认出**标的代码**（找不到返回 '' ✓）
     *
     * 规则：① 条目自带 `symbol`；② 标题 / 摘要里出现自选·持仓的名称或代码
     * （长词优先，避免「铜」匹配到「铜陵有色」✗）。都没有 → 综合类资讯。
     */
    private _symbolOf(item: NewsItem, symbols: string[],
                      names: string[]): string {
        const own = String((item as { symbol?: string }).symbol || '');
        if (own) return own;
        const text = `${item.title || ''} ${item.summary || ''}`;
        // 名称 → 代码（长度倒序，长词更精确 ✓）
        const pairs = names
            .map((name, index) => ({ name, symbol: symbols[index] || '' }))
            .filter((row) => row.name && row.symbol)
            .sort((a, b) => b.name.length - a.name.length);
        for (const row of pairs) {
            if (text.includes(row.name)) return row.symbol;
        }
        // 代码直接出现（`SHFE.ag2612` / `ag2612`）
        for (const symbol of symbols) {
            if (symbol && text.includes(symbol)) return symbol;
            const tail = symbol.includes('.') ? symbol.split('.', 1)[1] : '';
            if (tail && tail.length >= 4 && text.includes(tail)) return symbol;
        }
        // ★ 文本里直接写期货 / 股票代码也能认（资讯里常带「（600009）」✓）
        const futures = /([A-Z]{2,6}\.[a-zA-Z]{1,3}\d{3,4})/.exec(text);
        if (futures) return futures[1];
        const stock = /(6\d{5}|0\d{5}|3\d{5})/.exec(text);
        if (stock) {
            return (stock[1].startsWith('6') ? 'SSE.' : 'SZSE.') + stock[1];
        }
        return '';
    }

    /** 只看自选/持仓：标题或摘要里出现这些关键词 ✓ */
    private _relatedRows(rows: NewsItem[]): NewsItem[] {
        if (!this.relatedOnly) return rows;
        const words = [...this.relatedNames, ...this.relatedSymbols]
            .filter(Boolean);
        if (!words.length) return rows;
        return rows.filter((item) => {
            const text = `${item.title || ''} ${item.summary || ''}`;
            return words.some((word) => word && text.includes(word));
        });
    }

    private _renderNews(): void {
        const rows = this._relatedRows(this.news);
        if (!rows.length) {
            this.list.innerHTML = this._empty();
            return;
        }
        this.list.innerHTML = rows.map((item) => {
            const title = esc(item.title || '');
            const summary = esc(item.summary || '');
            const same = summary && summary.startsWith(title.slice(0, 10));
            return `<div class="desk-info-row" data-id="${esc(item.id || '')}">
                <div class="row-main">
                    <div class="row-title">${title}</div>
                    ${same ? '' : `<div class="row-summary">${summary}</div>`}
                </div>
                <div class="row-meta">
                    <span class="src">${esc(item.source || '')}</span>
                    <span class="time">${esc((item.published || '').slice(5))}</span>
                </div>
            </div>`;
        }).join('');
        this._bindRows();
    }

    private _renderCalendar(): void {
        if (!this.calendar.length) {
            this.list.innerHTML = this._empty();
            return;
        }
        const groups = new Map<string, CalendarItem[]>();
        for (const item of this.calendar) {
            const day = String(item.day || '');
            if (!groups.has(day)) groups.set(day, []);
            groups.get(day)!.push(item);
        }
        const rows: string[] = [];
        for (const [day, items] of groups) {
            rows.push(`<div class="desk-info-day">${esc(day)}</div>`);
            for (const item of items.slice(0, 120)) {
                const level = Number(item.importance || 0);
                rows.push(`<div class="desk-info-row cal l${level}">
                    <span class="cal-time">${esc(item.time || '')}</span>
                    <span class="cal-region">${esc(item.region || '')}</span>
                    <span class="cal-event">${esc(item.event || '')}</span>
                    <span class="cal-values">${esc(item.actual || '')}
                        ${item.forecast ? `（预期 ${esc(item.forecast)}）` : ''}
                        ${item.previous ? `（前值 ${esc(item.previous)}）` : ''}
                    </span>
                </div>`);
            }
        }
        this.list.innerHTML = rows.join('');
    }

    private _empty(): string {
        if (this.status.installed === false) {
            return '<div class="desk-info-empty">还没安装 AkShare：'
                + '<code>pip install "minibt[news]"</code>'
                + '<br>装好后点右上角「刷新」。</div>';
        }
        if (this.notice) {
            return `<div class="desk-info-empty">刷新失败：${esc(this.notice)}
                <br>可以先用已缓存的内容，或稍后再点「刷新」。</div>`;
        }
        if (this.kind === 'futures') {
            return '<div class="desk-info-empty">还没有这个标的的资料：'
                + '点「刷新」抓一次（约 1 秒）</div>';
        }
        return '<div class="desk-info-empty">还没有数据：点右上角「刷新」'
            + '（首次抓取约 1 秒）</div>';
    }

    private _bindRows(): void {
        const nodes = Array.from(
            this.list.querySelectorAll<HTMLElement>('.desk-info-row'));
        for (const node of nodes) {
            const id = node.dataset.id || '';
            const item = this.news.find((row) => row.id === id);
            if (!item) continue;
            // ★ v1.3.7-72：**左键不动作**；双击打开原文；右键菜单 ✓
            node.addEventListener('dblclick', () => {
                if (item.url) {
                    this.options.onCommand('open_url', { url: item.url });
                } else {
                    this.options.onToast?.('info', '这条资讯没有原文链接');
                }
            });
            node.addEventListener('contextmenu', (event) => {
                event.preventDefault();
                this._showNewsMenu(item, event.clientX, event.clientY);
            });
            node.addEventListener('contextmenu', (event: MouseEvent) => {
                // 旧的右键菜单已并进 `_showNewsMenu`（打开原文 / 打开图表 ✓）
                event.preventDefault();
                event.stopPropagation();
            });
        }
    }
}

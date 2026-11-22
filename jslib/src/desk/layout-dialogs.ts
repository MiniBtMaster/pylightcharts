/**
 * LayoutDialogs — 「保存当前布局」+「布局」管理（复刻 miniqt 的两个弹窗）。
 *
 *  保存当前布局                     布局                    ✕
 *  ┌ 名称 [布局 2026-10-18 16:46 ▾] ┐  ┌ [搜索]              ┐
 *  │ 即将保存                       │  │ 布局名称        3 个 │
 *  │ 布局：单图  周期：1分           │  │ ★ ag2612_macd  ✎ 🗑 │
 *  │ SHFE.ag2612                    │  │   单图 · 1分 · …     │
 *  └ [保存]            [取消]        ┘  └─────────────────────┘
 */
import { ensureStyle } from '../panels/emit';

export interface LayoutRow {
    key: string;
    name: string;
    favorite?: boolean;
    cols?: number;
    rows?: number;
    count?: number;
    shape?: string;
    cycle?: number;
    desc?: string;
    cells?: Array<Record<string, unknown>>;
}

const STYLE_ID = 'desk-layout-dialogs-style';

const CSS = `
.desk-lg-mask{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:12200;
  display:flex;align-items:center;justify-content:center;
  /* ★ 主题：直接用 desk 的变量（body.theme-light 会覆盖 :root ✓）——
     以前只认 pylightcharts Handler 注入的 --lg-*（建好后不再更新）→
     切换主题后布局管理窗口仍是旧配色（用户实测 2026-11-16 ✗）*/
  --lg-bg: var(--desk-panel, #1b2027);
  --lg-panel: var(--desk-panel, #1b2027);
  --lg-text: var(--desk-text, #d8d9db);
  --lg-muted: var(--desk-muted, #8b93a1);
  --lg-border: var(--desk-border, #262c36);
  --lg-hover: var(--desk-hover, #1e242d);
  --lg-input: var(--desk-bg, #0f1115);
  --lg-accent: var(--desk-accent, #0d9488)}
.desk-lg{width:560px;max-height:80vh;display:flex;flex-direction:column;
  border-radius:10px;overflow:hidden;
  /* 兜底：--lg-* 由 pylightcharts Handler 注入，策略管理挂在 desk 根上
     时可能还没定义 → 退到 desk 主题变量（否则背景透明 ✗） */
  background:var(--lg-bg, var(--desk-panel, #1b2027));
  color:var(--lg-text, var(--desk-text, #d8d9db));
  border:1px solid var(--lg-border, var(--desk-border, #2a3038));
  box-shadow:0 20px 60px rgba(0,0,0,.45)}
.desk-lg-head{display:flex;align-items:center;justify-content:space-between;
  padding:14px 18px;font-size:16px;font-weight:600}
.desk-lg-close{border:none;background:transparent;color:var(--lg-text);
  cursor:pointer;font-size:17px}
.desk-lg-body{padding:0 18px 14px;display:flex;flex-direction:column;gap:10px;
  overflow:auto}
.desk-lg-row{display:flex;align-items:center;gap:10px;font-size:13px}
.desk-lg-row > .k{flex:0 0 66px;color:var(--lg-text)}
.desk-lg-input{flex:1;height:30px;padding:0 10px;border-radius:6px;outline:none;
  border:1px solid var(--lg-border);background:var(--lg-input);color:var(--lg-text);
  font-size:13px}
.desk-lg-input:focus{border-color:var(--lg-accent)}
/* 布局管理的搜索框：高度是普通输入框的 2 倍（30 → 60，用户要求 2026-11-17 ✓） */
.desk-lg-search{height:60px;border-radius:8px;padding:0 14px;font-size:14px}
.desk-lg-hint{color:var(--lg-muted);font-size:12.5px;line-height:1.6}
.desk-lg-hint b{color:var(--lg-text);font-weight:600}
.desk-lg-foot{display:flex;gap:12px;padding:14px 18px;border-top:1px solid var(--lg-border)}
.desk-lg-btn{flex:1;height:34px;border-radius:6px;cursor:pointer;font-size:13.5px;
  border:1px solid var(--lg-border);background:transparent;color:var(--lg-text)}
.desk-lg-btn.primary{background:var(--lg-accent);border-color:var(--lg-accent);
  color:#fff}
.desk-lg-list{flex:1;min-height:0;overflow:auto}
.desk-lg-item{display:grid;grid-template-columns:24px 1fr auto auto;gap:10px;
  align-items:center;padding:10px 18px;border-bottom:1px solid var(--lg-border);
  cursor:default;font-size:13px}
.desk-lg-item:hover{background:var(--lg-hover)}
/* 布局行悬停卡片（同 PI 圆点卡片：不透明面板 + 阴影 ✓） */
.desk-lg-tip{position:fixed;z-index:12400;width:max-content;
  max-width:min(360px,60vw);padding:7px 10px;border-radius:8px;
  /* 卡片挂在 <body> 上（不在 .desk-lg 里）→ 变量必须带兜底，否则透明 ✗ */
  background:var(--lg-panel, var(--desk-panel, #1b2027));
  border:1px solid var(--lg-border, var(--desk-border, #2a3038));
  color:var(--lg-text, var(--desk-text, #d8d9db));
  font-size:11.5px;line-height:1.55;
  box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:auto}
.desk-lg-tip-head{font-weight:600;margin-bottom:4px;
  color:var(--lg-text, var(--desk-text, #d8d9db));
  white-space:normal;word-break:break-word}
.desk-lg-tip-row{color:var(--lg-muted, var(--desk-muted, #9aa4b2));
  white-space:normal;word-break:break-word}
.desk-lg-tip-row.cell{color:var(--lg-text, var(--desk-text, #d8d9db));
  font-weight:600;margin-top:4px}
/* 分组标题（「指标」/「策略」）—— 下方每项独立成段 ✓ */
.desk-lg-tip-row.group{margin-top:6px;color:var(--lg-muted, var(--desk-muted,
  #9aa4b2));font-size:11px;letter-spacing:.04em}
/* 一个指标 = 一段（等宽字体，参数对齐好认 ✓） */
.desk-lg-tip-row.item{padding-left:9px;
  color:var(--lg-text, var(--desk-text, #d8d9db));
  font-family:ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size:11.5px;line-height:1.5;white-space:pre}
/* 策略管理：没有收藏星 → 3 个图标按钮 + 文本 ✓ */
.desk-lg-item.is-strategy{grid-template-columns:1fr auto auto auto}
.desk-lg-star{cursor:pointer;color:var(--lg-muted);font-size:14px}
.desk-lg-star.on{color:#f6c343}
.desk-lg-name{font-weight:600}
.desk-lg-desc{color:var(--lg-muted);font-size:11.5px;line-height:1.5;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.desk-lg-icon{border:none;background:transparent;color:var(--lg-muted);
  cursor:pointer;font-size:14px}
.desk-lg-icon:hover{color:var(--lg-text)}
/* 策略管理：两个开关做成**圆形**按钮（正方形 + 50% 圆角 = 正圆 ✓） */
.desk-lg-icon.desk-lg-round{width:26px;height:26px;min-width:26px;padding:0;
  border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font-size:13px;line-height:1;
  border:1px solid var(--lg-border, var(--desk-border, #2a3038))}
.desk-lg-icon.desk-lg-round:hover{background:var(--lg-hover)}
.desk-lg-icon.desk-lg-round.on{color:#fff;background:var(--lg-accent,
  var(--desk-accent, #2962ff));border-color:transparent}
.desk-lg-count{color:var(--lg-muted);font-size:12px}
.desk-lg-empty{padding:18px;color:var(--lg-muted);font-size:12.5px}
`;

/** 配色**不再写死在 JS 里**：全部用 CSS 的 `var(--desk-*)`（`body.theme-light`
 *  会覆盖 `:root`）→ 切换主题时对话框**立刻**跟着变 ✓
 *
 *  以前这里是 `PALS.dark/light` + `element.style.setProperty('--lg-*')`，
 *  而 `setTheme()` 只在**第一次建对话框**时被调用一次 → 之后不管怎么切主题，
 *  布局管理窗口都还是旧的配色（用户实测 2026-11-17 ✗）。
 */
const PALETTE_KEYS = ['bg', 'panel', 'text', 'muted', 'border', 'input',
                      'hover', 'accent'] as const;

function applyPalette(element: HTMLElement, theme: 'light' | 'dark'): void {
    // 清掉历史内联值（老版本 / 外部注入留下的），让 CSS 变量接管
    for (const key of PALETTE_KEYS) {
        element.style.removeProperty(`--lg-${key}`);
    }
    element.dataset.deskTheme = theme === 'light' ? 'light' : 'dark';
}

function esc(value: unknown): string {
    return String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --------------------------------------------------------------- 保存布局
export class SaveLayoutDialog {
    public readonly element: HTMLDivElement;
    public onSaveCallback: ((name: string) => void) | null = null;

    private readonly input: HTMLInputElement;
    private readonly hint: HTMLDivElement;
    private readonly saveButton: HTMLButtonElement;
    private theme: 'light' | 'dark' = 'dark';
    /** 当前作用域已有的布局名称（保存时做同名确认 ✓） */
    private existing: string[] = [];
    private pendingName = '';

    constructor() {
        ensureStyle(STYLE_ID, CSS);
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask';
        this.element.dataset.kind = 'save';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg';
        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        head.innerHTML = '<span>保存当前布局</span>';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.appendChild(close);

        const body = document.createElement('div');
        body.className = 'desk-lg-body';
        const nameRow = document.createElement('div');
        nameRow.className = 'desk-lg-row';
        nameRow.innerHTML = '<span class="k">名称</span>';
        this.input = document.createElement('input');
        this.input.className = 'desk-lg-input';
        this.input.title = '布局名称（同名布局会提示替换）';
        this.input.addEventListener('input', () => this._resetConfirm());
        nameRow.appendChild(this.input);

        this.hint = document.createElement('div');
        this.hint.className = 'desk-lg-hint';
        body.append(nameRow, this.hint);

        const foot = document.createElement('div');
        foot.className = 'desk-lg-foot';
        const cancel = document.createElement('button');
        cancel.className = 'desk-lg-btn';
        cancel.textContent = '取消';
        cancel.title = '不保存';
        cancel.addEventListener('click', () => this.close());
        const save = document.createElement('button');
        save.className = 'desk-lg-btn primary';
        save.textContent = '保存';
        save.title = '保存当前布局';
        this.saveButton = save;
        save.addEventListener('click', () => {
            const name = this.input.value.trim() || this._defaultName();
            if (this._exists(name) && this.pendingName !== name) {
                this.pendingName = name;
                this.saveButton.textContent = '确认替换';
                this.hint.innerHTML =
                    `<div style="color:#f0a020;margin-bottom:4px">`
                    + `已有同名布局「${esc(name)}」</div>`
                    + '<div>再次点击「确认替换」将覆盖该布局。</div>';
                return;
            }
            this.onSaveCallback?.(name);
            this.close();
        });
        foot.append(save, cancel);

        box.append(head, body, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
        this.setTheme('dark');
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.theme = theme === 'light' ? 'light' : 'dark';
        applyPalette(this.element, this.theme);
    }

    /** 打开并显示「即将保存」的信息（布局 / 周期 / 合约 ✓） */
    open(info: { shape: string; cycle: string; symbols: string[];
                 existing?: string[] }): void {
        this.element.style.display = '';
        this.existing = (info.existing || []).map((name) => String(name || ''));
        if (!this.input.value) this.input.value = this._defaultName();
        this._resetConfirm();
        const rows = [
            `<div>布局：<b>${esc(info.shape)}</b>　周期：<b>${esc(info.cycle)}</b></div>`,
            ...info.symbols.map((symbol) => `<div>${esc(symbol)}</div>`),
        ];
        this.hint.innerHTML = '<div style="margin-bottom:4px">即将保存</div>'
            + rows.join('');
        this.input.focus();
        this.input.select();
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    private _exists(name: string): boolean {
        return this.existing.some((item) => item.trim() === name.trim());
    }

    private _resetConfirm(): void {
        this.pendingName = '';
        this.saveButton.textContent = '保存';
        if (this.hint.dataset.keep !== '1') {
            // 重新打开/改名的普通提示由 open() 重写；这里只清掉替换警告
            if (this.hint.textContent?.includes('已有同名布局')) {
                this.hint.textContent = '';
            }
        }
    }

    private _defaultName(): string {
        const now = new Date();
        const pad = (value: number) => String(value).padStart(2, '0');
        return `布局 ${now.getFullYear()}-${pad(now.getMonth() + 1)}-`
            + `${pad(now.getDate())} ${pad(now.getHours())}:`
            + `${pad(now.getMinutes())}`;
    }
}

// --------------------------------------------------------------- 布局管理
/** 布局管理的样式（策略管理弹窗也复用这一套 ✓） */
export function ensureLayoutStyle(): void {
    ensureStyle(STYLE_ID, CSS);
}

export class LayoutManager {
    public readonly element: HTMLDivElement;
    public onApplyCallback: ((key: string) => void) | null = null;
    public onDeleteCallback: ((key: string) => void) | null = null;
    public onFavoriteCallback: ((key: string, on: boolean) => void) | null = null;
    /** ✎ 编辑指标参数 ✓ */
    public onEditCallback: ((row: LayoutRow) => void) | null = null;
    /** 导出 / 导入布局（JSON 文本 ✓） */
    public onExportCallback: (() => void) | null = null;
    public onImportCallback: ((text: string) => void) | null = null;

    private readonly list: HTMLDivElement;
    private readonly search: HTMLInputElement;
    private readonly count: HTMLSpanElement;
    private readonly foot: HTMLDivElement;
    private exportText = '';
    private rows: LayoutRow[] = [];

    constructor() {
        ensureStyle(STYLE_ID, CSS);
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask';
        this.element.dataset.kind = 'manage';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg';
        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        head.innerHTML = '<span>布局</span>';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.appendChild(close);

        const searchWrap = document.createElement('div');
        searchWrap.className = 'desk-lg-body';
        searchWrap.style.paddingTop = '0';
        this.search = document.createElement('input');
        this.search.className = 'desk-lg-input desk-lg-search';
        this.search.placeholder = '搜索';
        this.search.title = '按布局名称搜索';
        this.search.addEventListener('input', () => this._render());
        searchWrap.appendChild(this.search);

        const meta = document.createElement('div');
        meta.className = 'desk-lg-row';
        meta.innerHTML = '<span class="k" style="flex:0 0 auto">布局名称</span>';
        this.count = document.createElement('span');
        this.count.className = 'desk-lg-count';
        this.count.style.marginLeft = 'auto';
        meta.appendChild(this.count);
        searchWrap.appendChild(meta);

        this.list = document.createElement('div');
        this.list.className = 'desk-lg-list';

        this.foot = document.createElement('div');
        this.foot.className = 'desk-lg-foot';
        const importButton = document.createElement('button');
        importButton.className = 'desk-lg-btn';
        importButton.textContent = '导入…';
        importButton.title = '从 JSON 文件导入布局';
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.json,application/json';
        fileInput.style.display = 'none';
        fileInput.addEventListener('change', () => {
            const file = fileInput.files && fileInput.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                this.onImportCallback?.(String(reader.result || ''));
                fileInput.value = '';
            };
            reader.readAsText(file, 'utf-8');
        });
        importButton.addEventListener('click', () => fileInput.click());
        const exportButton = document.createElement('button');
        exportButton.className = 'desk-lg-btn';
        exportButton.textContent = '导出…';
        exportButton.title = '把全部布局导出成 JSON 文件';
        exportButton.addEventListener('click', () => {
            const text = this.exportText || '{"layouts": []}';
            const blob = new Blob([text], { type: 'application/json' });
            const link = document.createElement('a');
            const stamp = new Date().toISOString().slice(0, 19)
                .replace(/[:T]/g, '-');
            link.download = `desk_layouts_${stamp}.json`;
            link.href = URL.createObjectURL(blob);
            link.click();
            window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
            this.onExportCallback?.();
        });
        const spacer = document.createElement('span');
        spacer.style.flex = '1';
        const closeButton = document.createElement('button');
        closeButton.className = 'desk-lg-btn primary';
        closeButton.textContent = '关闭';
        closeButton.addEventListener('click', () => this.close());
        this.foot.append(importButton, exportButton, fileInput, spacer,
                         closeButton);

        box.append(head, searchWrap, this.list, this.foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
        this.setTheme('dark');
    }

    setTheme(theme: 'light' | 'dark'): void {
        applyPalette(this.element, theme === 'light' ? 'light' : 'dark');
    }

    /** 后端给的导出文本（Qt 里也能「导出」✓） */
    setExportText(text: string): void {
        this.exportText = String(text || '');
    }

    setRows(rows: LayoutRow[]): void {
        this.rows = rows || [];
        this._render();
    }

    open(): void {
        this.element.style.display = '';
        this.search.value = '';
        this._render();
        this.search.focus();
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    private _render(): void {
        const needle = this.search.value.trim().toLowerCase();
        const rows = this.rows.filter((row) => !needle
            || row.name.toLowerCase().includes(needle));
        this.count.textContent = `${this.rows.length} 个`;
        this.list.textContent = '';
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-lg-empty';
            empty.textContent = '（还没有保存的布局：点「保存布局」）';
            this.list.appendChild(empty);
            return;
        }
        for (const row of rows) {
            const item = document.createElement('div');
            item.className = 'desk-lg-item';
            const star = document.createElement('span');
            star.className = 'desk-lg-star' + (row.favorite ? ' on' : '');
            star.textContent = row.favorite ? '★' : '☆';
            star.title = row.favorite ? '取消收藏' : '收藏布局';
            star.addEventListener('click', () => {
                this.onFavoriteCallback?.(row.key, !row.favorite);
                star.classList.toggle('on', !row.favorite);
                star.textContent = !row.favorite ? '★' : '☆';
            });
            const text = document.createElement('div');
            // ★ 用户 2026-11-16：原生 `title` 只显示合约、看不到指标 / 策略 →
            //   **禁用原生 tooltip**，改用下面自绘的悬停卡片（同 K 线事件圆点 ✓）
            text.innerHTML = `<div class="desk-lg-name">${esc(row.name)}</div>`
                + `<div class="desk-lg-desc">${esc(row.desc || '')}</div>`;
            text.querySelector('.desk-lg-desc')?.removeAttribute('title');
            text.style.cursor = 'pointer';
            text.addEventListener('click', () => {
                this.onApplyCallback?.(row.key);
                this.close();
            });
            const edit = document.createElement('button');
            edit.className = 'desk-lg-icon';
            edit.textContent = '✎';
            edit.title = '编辑这个布局里每个指标的参数';
            edit.addEventListener('click', () => {
                this.onEditCallback?.(row);
            });
            const drop = document.createElement('button');
            drop.className = 'desk-lg-icon';
            drop.textContent = '🗑';
            drop.title = '删除这个布局';
            drop.addEventListener('click', () => {
                this.onDeleteCallback?.(row.key);
                this.rows = this.rows.filter((it) => it.key !== row.key);
                this._render();
            });
            item.append(star, text, edit, drop);
            // ★ 悬停卡片：形状 / 合约 / **每格的指标（带参数）/ 策略** ✓
            bindLayoutTip(item, row);
            this.list.appendChild(item);
        }
    }
}


// --------------------------------------------------------- 指标参数编辑器
export interface LayoutCellLike {
    symbol?: string;
    indicators?: Array<{ key?: string; params?: Record<string, unknown> }>;
}

/** 「编辑指标参数」：列出每格每个指标，参数用数字输入框 ✓ */
export class LayoutParamsDialog {
    public readonly element: HTMLDivElement;
    public onSaveCallback:
        ((cells: LayoutCellLike[]) => void) | null = null;

    private readonly body: HTMLDivElement;
    private readonly titleEl: HTMLSpanElement;
    private cells: LayoutCellLike[] = [];
    private inputs: Array<{ cell: number; index: number; name: string;
                           input: HTMLInputElement; kind: string }> = [];

    constructor() {
        ensureStyle(STYLE_ID, CSS);
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask';
        this.element.dataset.kind = 'params';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg';
        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        this.titleEl = document.createElement('span');
        this.titleEl.textContent = '编辑指标参数';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.append(this.titleEl, close);

        this.body = document.createElement('div');
        this.body.className = 'desk-lg-body';

        const foot = document.createElement('div');
        foot.className = 'desk-lg-foot';
        const cancel = document.createElement('button');
        cancel.className = 'desk-lg-btn';
        cancel.textContent = '取消';
        cancel.addEventListener('click', () => this.close());
        const save = document.createElement('button');
        save.className = 'desk-lg-btn primary';
        save.textContent = '保存';
        save.title = '保存这些参数（下次应用布局时生效）';
        save.addEventListener('click', () => this._save());
        foot.append(save, cancel);

        box.append(head, this.body, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
        this.setTheme('dark');
    }

    setTheme(theme: 'light' | 'dark'): void {
        applyPalette(this.element, theme === 'light' ? 'light' : 'dark');
    }

    open(name: string, cells: LayoutCellLike[]): void {
        this.element.style.display = '';
        this.titleEl.textContent = `编辑指标参数 · ${name}`;
        this.cells = JSON.parse(JSON.stringify(cells || [])) as
            LayoutCellLike[];
        this.inputs = [];
        this.body.textContent = '';
        this.cells.forEach((cell, cellIndex) => {
            const header = document.createElement('div');
            header.className = 'desk-lg-row';
            header.innerHTML = `<span class="k" style="flex:0 0 auto">`
                + `第 ${cellIndex + 1} 格</span><b>`
                + `${esc(cell.symbol || '')}</b>`;
            this.body.appendChild(header);
            const indicators = cell.indicators || [];
            if (!indicators.length) {
                const empty = document.createElement('div');
                empty.className = 'desk-lg-hint';
                empty.textContent = '（这格没有指标）';
                this.body.appendChild(empty);
                return;
            }
            for (const [index, item] of indicators.entries()) {
                const params = item.params || {};
                const names = Object.keys(params);
                const row = document.createElement('div');
                row.className = 'desk-lg-row';
                row.innerHTML = `<span class="k">${esc(item.key || '')}</span>`;
                if (!names.length) {
                    const hint = document.createElement('span');
                    hint.className = 'desk-lg-hint';
                    hint.textContent = '（无参数）';
                    row.appendChild(hint);
                }
                for (const paramName of names) {
                    const value = params[paramName];
                    const label = document.createElement('span');
                    label.className = 'desk-lg-hint';
                    label.textContent = paramName;
                    const input = document.createElement('input');
                    input.className = 'desk-lg-input';
                    input.style.maxWidth = '90px';
                    input.value = String(value ?? '');
                    input.title = `${item.key}.${paramName}`;
                    const kind = typeof value === 'number' ? 'number'
                        : (typeof value === 'boolean' ? 'bool' : 'str');
                    input.dataset.kind = kind;
                    this.inputs.push({ cell: cellIndex, index,
                                       name: paramName, input, kind });
                    row.append(label, input);
                }
                this.body.appendChild(row);
            }
        });
        if (!this.cells.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-lg-hint';
            empty.textContent = '（这个布局没有记录任何合约 / 指标）';
            this.body.appendChild(empty);
        }
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    private _save(): void {
        for (const entry of this.inputs) {
            const cell = this.cells[entry.cell];
            const item = (cell?.indicators || [])[entry.index];
            if (!item) continue;
            const raw = entry.input.value.trim();
            if (entry.kind === 'number') {
                const number = Number(raw);
                if (!Number.isFinite(number)) {
                    entry.input.focus();
                    return;
                }
                item.params = { ...(item.params || {}), [entry.name]: number };
            } else if (entry.kind === 'bool') {
                item.params = { ...(item.params || {}),
                                [entry.name]: raw === 'true' || raw === '1' };
            } else {
                item.params = { ...(item.params || {}), [entry.name]: raw };
            }
        }
        this.onSaveCallback?.(this.cells);
        this.close();
    }
}

// --------------------------------------------------------- 策略管理（复用布局管理界面）
export interface StrategyRow {
    symbol: string;
    /** 本地图表策略的稳定键（页签 id / CSV 名；删除时回传 ✓） */
    key?: string;
    cell?: number;
    name: string;
    path?: string;
    lines?: number;
    next_on_new_bar?: boolean;
    run_next?: boolean;
    local?: boolean;
    /** ★ 策略实盘（`Bt(live=True)` 常驻子进程）的那一行 ✓ */
    live?: boolean;
    running?: boolean;
    pid?: number;
    file?: string;
}

/**
 * **策略管理** —— 界面**完全复用「布局管理」**（同一套 `desk-lg-*` 样式）：
 * 标题栏 / 列表（悬停变浅）/ 图标按钮 / 底部「关闭」。
 *
 * 每行：`名称 + 说明`、`🕯 新K线next`、`▶ 运行next`、`🗑 删除`
 * （两个开关和删除同款图标按钮，开启时主题色 ✓）
 */
export class StrategyManager {
    public readonly element: HTMLDivElement;
    public onToggleCallback:
        ((row: StrategyRow, key: string, value: boolean) => void) | null = null;
    public onDeleteCallback: ((row: StrategyRow) => void) | null = null;

    private readonly list: HTMLDivElement;
    private readonly count: HTMLSpanElement;
    private rows: StrategyRow[] = [];

    constructor() {
        ensureStyle(STYLE_ID, CSS);
        this.element = document.createElement('div');
        this.element.className = 'desk-lg-mask';
        this.element.dataset.kind = 'manage';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-lg';
        const head = document.createElement('div');
        head.className = 'desk-lg-head';
        head.innerHTML = '<span>策略</span>';
        const close = document.createElement('button');
        close.className = 'desk-lg-close';
        close.textContent = '✕';
        close.title = '关闭';
        close.addEventListener('click', () => this.close());
        head.appendChild(close);

        const body = document.createElement('div');
        body.className = 'desk-lg-body';
        body.style.paddingTop = '0';
        const meta = document.createElement('div');
        meta.className = 'desk-lg-row';
        meta.innerHTML = '<span class="k" style="flex:0 0 auto">策略名称</span>';
        this.count = document.createElement('span');
        this.count.className = 'desk-lg-count';
        this.count.style.marginLeft = 'auto';
        meta.appendChild(this.count);
        body.appendChild(meta);

        this.list = document.createElement('div');
        this.list.className = 'desk-lg-list';
        body.appendChild(this.list);

        const foot = document.createElement('div');
        foot.className = 'desk-lg-foot';
        const spacer = document.createElement('span');
        spacer.style.flex = '1';
        const done = document.createElement('button');
        done.className = 'desk-lg-btn primary';
        done.textContent = '关闭';
        done.addEventListener('click', () => this.close());
        foot.append(spacer, done);

        box.append(head, body, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
    }

    open(rows: StrategyRow[]): void {
        this.rows = Array.isArray(rows) ? rows : [];
        this.element.style.display = '';
        this._render();
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    /** 一个开关按钮（图标 + tooltip，和删除同款 ✓） */
    private _toggle(row: StrategyRow, key: 'next_on_new_bar' | 'run_next',
                    glyph: string, label: string,
                    tip: string): HTMLButtonElement {
        const on = row[key] !== false;
        const button = document.createElement('button');
        button.className = 'desk-lg-icon desk-lg-round'
            + (on ? ' on' : '');
        button.textContent = glyph;
        button.title = `${label}：${on ? '开启' : '关闭'}
${tip}`;
        button.addEventListener('click', () => {
            const next = !(row[key] !== false);
            row[key] = next;
            button.classList.toggle('on', next);
            button.title = `${label}：${next ? '开启' : '关闭'}
${tip}`;
            this.onToggleCallback?.(row, key, next);
        });
        return button;
    }

    private _render(): void {
        this.count.textContent = `${this.rows.length} 个`;
        this.list.textContent = '';
        if (!this.rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-lg-empty';
            empty.textContent = '（当前没有图表 / 实盘在跑策略）';
            this.list.appendChild(empty);
            return;
        }
        for (const row of this.rows) {
            const item = document.createElement('div');
            item.className = 'desk-lg-item is-strategy';
            const text = document.createElement('div');
            const cell = Number(row.cell) || 0;
            const title = document.createElement('div');
            title.className = 'desk-lg-name';
            const live = !!row.live;
            const overlay = (row as unknown as { overlay?: boolean }).overlay;
            title.textContent = live
                ? `${row.running ? '● ' : '○ '}实盘 · ${row.name || '策略'}`
                : `${cell && !overlay ? `格 ${cell + 1} · ` : ''}`
                    + `${row.name || '策略'}`;
            if (live) {
                title.style.color = row.running ? '#26a69a' : '';
                title.title = row.running
                    ? `策略实盘运行中（PID ${Number(row.pid) || '?'}）`
                    : '策略实盘未运行（后台子进程已结束）';
            }
            const desc = document.createElement('div');
            desc.className = 'desk-lg-desc';
            desc.textContent = live
                ? `${String(row.file || row.path || '')}　·　`
                    + (row.running ? `PID ${Number(row.pid) || '?'}` : '未运行')
                : `${String(row.symbol || '')}　`
                    + `${Number(row.lines) || 0} 条线`
                    + (row.local ? '　·　本地图表' : '');
            text.append(title, desc);
            const newBar = this._toggle(
                row, 'next_on_new_bar', '🕯', '新K线next',
                '开启：只在**新 K 线**运行一次 next；'
                + '关闭：每次指标计算完成就运行 next');
            const runNext = this._toggle(
                row, 'run_next', '▶', '运行next',
                '开启：运行策略交易逻辑（next）；'
                + '关闭：只计算指标、不跑交易逻辑');
            const drop = document.createElement('button');
            drop.className = 'desk-lg-icon';
            drop.textContent = '🗑';
            drop.title = live
                ? '停止并移除这个策略实盘（子进程结束，不平仓）'
                : (overlay
                    ? '删除这个只读叠加（不含交易、不影响策略 / 指标）'
                    : '从这个图表删除该策略（指标保留）');
            drop.addEventListener('click', () => {
                this.onDeleteCallback?.(row);
                this.rows = this.rows.filter((it) => it !== row);
                this._render();
            });
            if (overlay) {
                // ★ 只读叠加不跑 next → 两个开关**禁用**（灰掉而不是隐藏：
                //   让用户知道为什么点了没反应 ✓）
                for (const button of [newBar, runNext]) {
                    button.disabled = true;
                    button.classList.remove('on');
                    button.classList.add('disabled');
                    button.style.opacity = '0.35';
                    button.style.cursor = 'not-allowed';
                    button.title = '只读叠加：不运行 next（只算指标线）';
                }
                item.append(text, newBar, runNext, drop);
            } else {
                item.append(text, newBar, runNext, drop);
            }
            this.list.appendChild(item);
        }
    }
}

// ------------------------------------------------------------ 布局悬停卡片
/** `PandasTa.sma` → `sma`（卡片里只写人话 ✓） */
function shortKey(key: string): string {
    const text = String(key || '');
    const parts = text.split('.');
    return parts[parts.length - 1] || text;
}

/** 指标参数摘要：`{length: 120}` → `(120)`（太长就省略 ✓） */
function paramsText(params: unknown): string {
    if (!params || typeof params !== 'object') return '';
    const values = Object.values(params as Record<string, unknown>)
        .filter((value) => value !== null && value !== undefined
            && typeof value !== 'object')
        .map((value) => String(value));
    if (!values.length) return '';
    return `(${values.join(', ')})`;
}

/** 一行提示（`title` / `text`；`kind` 决定卡片里的排版 ✓） */
interface TipRow {
    title?: string;
    text: string;
    kind?: 'cell' | 'group' | 'item' | 'line';
}

/**
 * 布局卡片的内容 — **一个指标一段**（用户要求 2026-11-17 ✓）
 *
 * 指标清单优先用后端算好的 `tipIndicators`：那里已经做过简化 ——
 * 框式指标（IndFrame，例 `pta_adx` 的 adxx/adxr/dmp/dmn 四条线）合并成
 * 一条 `pta_adx(14, 14, 100, rma, 1, 0)`；单线指标（IndSeries）保持
 * `pta_sma:sma(10, true, 0)`。后端没给（旧数据）就退回按线条列。
 */
export function layoutTipRows(row: LayoutRow): TipRow[] {
    const rows: TipRow[] = [];
    const cells = (row.cells || []) as Array<Record<string, unknown>>;
    cells.forEach((cell, index) => {
        const symbol = String(cell.symbol || '');
        if (!symbol) return;
        rows.push({ title: `#${index + 1} ${symbol}`, text: '', kind: 'cell' });
        const tips = (cell.tipIndicators || []) as unknown;
        if (Array.isArray(tips) && tips.length) {
            rows.push({ title: '指标', text: '', kind: 'group' });
            for (const text of tips) {
                const value = String(text || '').trim();
                if (value) rows.push({ text: value, kind: 'item' });
            }
        } else {
            const indicators = (cell.indicators || []) as Array<
                Record<string, unknown>>;
            if (indicators.length) {
                rows.push({ title: '指标', text: '', kind: 'group' });
                for (const item of indicators) {
                    rows.push({
                        text: shortKey(String(item.key || ''))
                            + paramsText(item.params),
                        kind: 'item',
                    });
                }
            }
        }
        const strategy = (cell.strategy || {}) as Record<string, unknown>;
        if (strategy && (strategy.name || strategy.path)) {
            const name = String(strategy.name || '').trim()
                || String(strategy.path || '').split(/[\/]/).pop()
                || '';
            if (name) {
                rows.push({ title: '策略', text: '', kind: 'group' });
                rows.push({ text: name, kind: 'item' });
            }
        }
    });
    return rows;
}

/** 悬停布局行 → 浮出卡片（复用 PI 圆点那种卡片样式 ✓） */
function bindLayoutTip(item: HTMLElement, row: LayoutRow): void {
    let tip: HTMLDivElement | null = null;
    let hideTimer = 0;
    const hide = () => {
        hideTimer = window.setTimeout(() => {
            tip?.remove();
            tip = null;
        }, 140);
    };
    const show = () => {
        if (tip) { window.clearTimeout(hideTimer); return; }
        const lines = layoutTipRows(row);
        if (!lines.length) return;
        tip = document.createElement('div');
        tip.className = 'desk-lg-tip';
        const head = document.createElement('div');
        head.className = 'desk-lg-tip-head';
        head.textContent = `${row.name} · ${row.desc || ''}`;
        tip.appendChild(head);
        for (const line of lines) {
            const div = document.createElement('div');
            div.className = 'desk-lg-tip-row';
            if (line.kind === 'cell' || (line.title && !line.text
                                         && line.kind !== 'group')) {
                div.classList.add('cell');
                div.textContent = line.title || '';   // `#1 SHFE.ag2612`
            } else if (line.kind === 'group') {
                div.classList.add('group');
                div.textContent = line.title || '';   // `指标` / `策略`
            } else {
                div.classList.add('item');
                div.textContent = line.text;          // 一条指标 / 一个策略名
            }
            tip.appendChild(div);
        }
        const rect = item.getBoundingClientRect();
        tip.style.left = `${Math.max(8, rect.right + 8)}px`;
        tip.style.top = `${Math.max(8, rect.top)}px`;
        tip.addEventListener('mouseenter',
                             () => window.clearTimeout(hideTimer));
        tip.addEventListener('mouseleave', hide);
        document.body.appendChild(tip);
        // 右侧放不下 → 贴到左边 ✓
        const box = tip.getBoundingClientRect();
        if (box.right > window.innerWidth - 8) {
            tip.style.left = `${Math.max(8, rect.left - box.width - 8)}px`;
        }
    };
    item.addEventListener('mouseenter', show);
    item.addEventListener('mouseleave', hide);
}

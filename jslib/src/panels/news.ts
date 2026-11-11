/**
 * NewsFeed — a scrollable headline list (TradingView Top Stories).
 *
 * Python supplies the items (there is no news source in the library); clicking an
 * item reports its index (and opens `url` in a new tab when given).
 */

import { emitCallback, ensureStyle } from './emit';

export interface NewsItem {
    title: string;
    source?: string;
    time?: string;
    url?: string;
    summary?: string;
}

export interface NewsTheme {
    background?: string;
    text?: string;
    muted?: string;
    border?: string;
    accent?: string;
}

export interface NewsFeedOptions {
    items?: NewsItem[];
    openLinks?: boolean;
    theme?: NewsTheme;
    onItemClick?: (index: number) => void;
    /** 右键某条（index + 原生事件）→ 宿主弹自己的菜单 ✓ */
    onItemContextMenu?: (index: number, event: MouseEvent) => void;
    /** 双击某条（默认 = 打开原文；宿主可覆盖 ✓） */
    onItemDoubleClick?: (index: number) => void;
}

interface ResolvedTheme {
    background: string;
    text: string;
    muted: string;
    border: string;
    accent: string;
}

const STYLE_ID = 'pylightcharts-news-style';
const CSS = `
.pylc-news{width:100%;height:100%;overflow:auto;box-sizing:border-box;padding:6px 12px;
  background:var(--nw-bg);color:var(--nw-text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Roboto,Arial,sans-serif}
.pylc-news-item{padding:9px 0;border-bottom:1px solid var(--nw-border);cursor:pointer}
.pylc-news-item:last-child{border-bottom:0}
.pylc-news-title{font-size:13.5px;font-weight:600;color:var(--nw-text);line-height:1.4}
.pylc-news-item:hover .pylc-news-title{color:var(--nw-accent)}
.pylc-news-meta{font-size:11px;color:var(--nw-muted);margin-top:3px}
.pylc-news-summary{font-size:12px;color:var(--nw-muted);margin-top:5px;line-height:1.55}
.pylc-news-empty{color:var(--nw-muted);padding:16px;text-align:center}
.pylc-stack>.pylc-news{height:auto;flex:1 1 auto;min-height:0}
`;

function defaultContainer(): HTMLElement {
    const host = window as unknown as { containerDiv?: HTMLElement };
    return host.containerDiv ?? document.body;
}

export class NewsFeed {
    public callbackName: string | null = null;
    public readonly element: HTMLDivElement;

    private _items: NewsItem[] = [];
    private _openLinks: boolean;
    private _theme: ResolvedTheme;
    private _onItemClick?: (index: number) => void;
    private _onItemContextMenu?: (index: number, event: MouseEvent) => void;
    private _onItemDoubleClick?: (index: number) => void;

    constructor(options: NewsFeedOptions = {}, parent?: HTMLElement | null) {
        ensureStyle(STYLE_ID, CSS);
        this._openLinks = options.openLinks ?? true;
        this._theme = this._resolveTheme(options.theme ?? {});
        this._onItemClick = options.onItemClick;
        this._onItemContextMenu = options.onItemContextMenu;
        this._onItemDoubleClick = options.onItemDoubleClick;
        this.element = document.createElement('div');
        this.element.className = 'pylc-news';
        this._applyThemeVars();
        (parent ?? defaultContainer()).appendChild(this.element);
        this.setItems(options.items ?? []);
    }

    setItems(items: NewsItem[]): void {
        this._items = items ?? [];
        this._render();
    }

    setOptions(options: Partial<NewsFeedOptions>): void {
        if (options.openLinks !== undefined) this._openLinks = options.openLinks;
        if (options.theme) {
            this._theme = this._resolveTheme(options.theme);
            this._applyThemeVars();
        }
        this._render();
    }

    destroy(): void {
        this.element.remove();
    }

    private _resolveTheme(theme: NewsTheme): ResolvedTheme {
        return {
            background: theme.background ?? '#131722',
            text: theme.text ?? '#d1d4dc',
            muted: theme.muted ?? '#787b86',
            border: theme.border ?? '#2a2e39',
            accent: theme.accent ?? '#2962ff',
        };
    }

    private _applyThemeVars(): void {
        const style = this.element.style;
        style.setProperty('--nw-bg', this._theme.background);
        style.setProperty('--nw-text', this._theme.text);
        style.setProperty('--nw-muted', this._theme.muted);
        style.setProperty('--nw-border', this._theme.border);
        style.setProperty('--nw-accent', this._theme.accent);
    }

    private _render(): void {
        this.element.textContent = '';
        if (this._items.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'pylc-news-empty';
            empty.textContent = '暂无新闻';
            this.element.appendChild(empty);
            return;
        }
        this._items.forEach((item, index) => {
            const node = document.createElement('div');
            node.className = 'pylc-news-item';

            const title = document.createElement('div');
            title.className = 'pylc-news-title';
            title.textContent = item.title;
            node.appendChild(title);

            const metaText = [item.source, item.time].filter(Boolean).join(' · ');
            if (metaText) {
                const meta = document.createElement('div');
                meta.className = 'pylc-news-meta';
                meta.textContent = metaText;
                node.appendChild(meta);
            }
            if (item.summary) {
                const summary = document.createElement('div');
                summary.className = 'pylc-news-summary';
                summary.textContent = item.summary;
                node.appendChild(summary);
            }
            // ★ 默认行为在 v1.3.7-72 改了：**左键不再直接跳 / 开**（宿主决定）
            node.addEventListener('dblclick', () => {
                if (this._onItemDoubleClick) {
                    this._onItemDoubleClick(index);
                    return;
                }
                if (this._openLinks && item.url) {
                    window.open(item.url, '_blank', 'noopener');
                }
            });
            // 左键：宿主需要时可接（默认不做事 ✓ v1.3.7-72）
            node.addEventListener('click', () => {
                if (this._onItemClick) this._onItemClick(index);
                else if (this.callbackName) {
                    emitCallback(this.callbackName, String(index));
                }
            });
            node.addEventListener('contextmenu', (event) => {
                if (this._onItemContextMenu) {
                    event.preventDefault();
                    this._onItemContextMenu(index, event);
                }
            });
            this.element.appendChild(node);
        });
    }

}

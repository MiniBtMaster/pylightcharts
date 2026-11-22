/**
 * 多布局画线：**共用一个画线工具** + 按「合约|周期」持久化 ✓
 *
 * 用户 2026-10-29 需求：
 *  1. 多图表布局里所有图共用一个画线工具，统一由工具栏「画线」按钮显隐；
 *  2. 画线本地持久化，键 = `合约|周期`（同一个品种不同周期各画各的，
 *     **不**把一个品种所有周期的画线混到一起 —— 之前验证过会乱 ✗）。
 *
 * 实现要点：
 *  * pylightcharts 的 `ToolBox.saveDrawings()` 会调用
 *    `window.callbackFunction('save_drawings<handlerId>_~_<json>')` →
 *    这里 hook 住这条消息，按 handlerId 找到「哪一格」，再把画线交给 desk
 *    后端存盘（Qt / 浏览器两种壳都走同一条 `callbackFunction` ✓）；
 *  * 每格的工具箱**都建出来但默认隐藏**（不建的话 `loadDrawings()` 无处可载），
 *    工具栏按钮只显示**当前格**那一个 → 视觉上就是“共用一个工具”；
 *  * 同键的多格（比如左右两图都是 ag2612|1分）拿到同一份画线 ✓。
 */

interface CellInfo {
    /** handler id（`Handler` 构造时给的那个，save_drawings 回调里带 ✓） */
    id: string;
    /** 持久化键：`<合约>|<周期秒>` ✓ */
    key: string;
    /** pylightcharts `Handler`（要 `.toolBox` / `.createToolBox()`） */
    handler: unknown;
}

interface BoxLike {
    div?: HTMLElement;
    loadDrawings?: (items: unknown[]) => void;
    clearDrawings?: () => void;
}

export interface DrawingsSyncOptions {
    /** 当前每格（每次调用都现算：换合约 / 换周期 / 换布局后 ✓） */
    cells: () => CellInfo[];
    /** 存一份画线（空数组 = 删除该键） */
    save: (key: string, items: unknown[]) => void;
    /** 请求某个键的画线（后端随后推 `{type:'drawings', key, items}` ✓） */
    request?: (key: string) => void;
    /**
     * **兜底格**：回调里的 handlerId 对不上任何已知格时用它（当前活跃格）✓
     *
     * 用户实测（2026-11-16，左右布局）：**格 1** 的右键「Delete Drawing」
     * 删不掉画线，只有「删除所有画线」有效；格 2 正常。
     * 根因是回调里的 id 与 `cellHandlerIds[0]` 不一致（重建格子 / 单格→多格
     * 时旧 id 残留）→ `SAVERS.get(id)` 落空，删除结果被丢弃 ✗。
     */
    fallback?: () => { id: string; key: string } | null;
}

/** handlerId → 保存回调（`save_drawings<id>_~_<json>` 用 ✓） */
const SAVERS = new Map<string, (json: string) => void>();
/** key → 保存回调（id 兜底时按 key 找 ✓） */
const KEY_SAVERS = new Map<string, (json: string) => void>();
/** 最后注册的兜底（一页一个 ChartPage，够用 ✓） */
let FALLBACK: (() => { id: string; key: string } | null) | null = null;
let hooked = false;

function installHook(): void {
    if (hooked) return;
    hooked = true;
    const host = window as unknown as { callbackFunction?: Function };
    const wrap = (): void => {
        const original = host.callbackFunction;
        if (typeof original !== 'function') return;
        if ((original as unknown as { __deskDrawings?: boolean }).__deskDrawings) {
            return;
        }
        const hookedFn = function (this: unknown, message: string) {
            const text = String(message ?? '');
            if (text.startsWith('save_drawings')) {
                const rest = text.slice('save_drawings'.length);
                const cut = rest.indexOf('_~_');
                if (cut > 0) {
                    const id = rest.slice(0, cut);
                    let saver = SAVERS.get(id);
                    if (!saver && FALLBACK) {
                        // ★ id 对不上（重建格子后旧 id 残留）→ 用活跃格兜底，
                        //   否则格 1 的"删除画线"会被静默丢弃 ✗
                        const cell = FALLBACK();
                        if (cell?.key) {
                            saver = (json: string) => {
                                const target = FALLBACK?.() || cell;
                                const byKey = KEY_SAVERS.get(target.key);
                                if (byKey) byKey(json);
                            };
                            SAVERS.set(id, saver);   // 记住，下次直接命中 ✓
                        }
                    }
                    if (saver) {
                        try {
                            saver(rest.slice(cut + 3));
                        } catch {
                            /* 解析失败不打断画线 ✓ */
                        }
                        return;
                    }
                }
            }
            return original.apply(this, arguments as never);
        };
        (hookedFn as unknown as { __deskDrawings?: boolean })
            .__deskDrawings = true;
        host.callbackFunction = hookedFn as unknown as Function;
    };
    wrap();
    // Qt 壳 / pylightcharts 可能在页面加载后才绑定 callbackFunction → 补装 ✓
    window.setTimeout(wrap, 800);
    window.setTimeout(wrap, 3000);
}

export class DrawingsSync {
    /** `key -> 画线列表`（后端推来 / 本地保存后都缓一份，换格不用再问 ✓） */
    private readonly cache = new Map<string, unknown[]>();
    private readonly ids = new Set<string>();

    constructor(private readonly options: DrawingsSyncOptions) {}

    /** 重建格子 / 换合约 / 换周期 / 换布局后调用 ✓ */
    refresh(): void {
        installHook();
        FALLBACK = this.options.fallback || null;
        const cells = this.options.cells();
        const alive = new Set(cells.map((cell) => cell.id));
        for (const id of [...this.ids]) {
            if (!alive.has(id)) {
                SAVERS.delete(id);
                this.ids.delete(id);
            }
        }
        for (const cell of cells) {
            if (!cell.id) continue;
            this.ids.add(cell.id);
            const save = (json: string) => this._onSave(cell.key, json);
            SAVERS.set(cell.id, save);
            KEY_SAVERS.set(cell.key, save);
            // ★ 有些版本里 handler 的 id 与记录的不同（重建格子后旧 id 残留）
            //   → 把**当前** handler 的 id 也注册一遍，双保险 ✓
            const liveId = String((cell.handler as unknown as { id?: string })
                ?.id || '');
            if (liveId && liveId !== cell.id) SAVERS.set(liveId, save);
            this._applyTo(cell);
        }
    }

    /** 后端 `{type:'drawings', key, items}` ✓ */
    apply(payload: { key?: string; items?: unknown[] }): void {
        const key = String(payload.key || '');
        if (!key) return;
        const items = Array.isArray(payload.items) ? payload.items : [];
        this.cache.set(key, items);
        for (const cell of this.options.cells()) {
            if (cell.key === key) this._applyTo(cell);
        }
    }

    /** 清掉某个键（所有同键的格一起清，后端也删掉 ✓） */
    clear(key: string): void {
        if (!key) return;
        this.cache.set(key, []);
        for (const cell of this.options.cells()) {
            if (cell.key !== key) continue;
            this._box(cell)?.clearDrawings?.();
        }
        KEY_SAVERS.set(key, (json) => this._onSave(key, json));
        this.options.save(key, []);
    }

    /** 工具箱显隐：**只显示当前格**（多布局共用一个 ✓） */
    showToolBox(visible: boolean, activeId: string): void {
        for (const cell of this.options.cells()) {
            const box = this._box(cell);
            if (!box?.div) continue;
            box.div.style.display = visible && cell.id === activeId
                ? 'flex' : 'none';
        }
    }

    private _onSave(key: string, json: string): void {
        let items: unknown[] = [];
        try {
            const parsed = JSON.parse(json) as unknown;
            items = Array.isArray(parsed) ? parsed : [];
        } catch {
            return;                       // 坏数据不落盘 ✓
        }
        this.cache.set(key, items);
        this.options.save(key, items);
    }

    private _box(cell: CellInfo): BoxLike | null {
        const handler = cell.handler as unknown as {
            toolBox?: BoxLike;
            createToolBox?: () => void;
        } | null;
        if (!handler) return null;
        // 不建工具箱的话 `loadDrawings()` 无处可载（隐藏着也要建 ✓）
        if (!handler.toolBox) handler.createToolBox?.();
        return handler.toolBox || null;
    }

    private _applyTo(cell: CellInfo): void {
        const box = this._box(cell);
        if (!box) return;
        const items = this.cache.get(cell.key);
        box.clearDrawings?.();
        if (items === undefined) {
            this.options.request?.(cell.key);   // 没缓存过 → 问后端 ✓
            return;
        }
        if (items.length) box.loadDrawings?.(items);
    }
}

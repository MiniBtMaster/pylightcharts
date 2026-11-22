// 画线同步：**格 1 右键「Delete Drawing」删不掉**（v1.3.9-10 修复）
//
// 现象（用户实测，左右布局）：格 1 的画线只能靠工具栏「删除所有画线」清掉，
// 右键删除不生效；格 2 正常。
// 根因：回调 `save_drawings<handlerId>_~_<json>` 里的 id 在**重建格子**后
// 可能对不上 `cellHandlerIds` 里的旧值 → `SAVERS.get(id)` 落空 → 删除被丢弃 ✗。
// 修法：按 key 注册一份 + id 兜底（当前活跃格）。
import { beforeAll, describe, expect, it, vi } from 'vitest';

class Box {
    div = { style: { display: '' } };
    items: unknown[] = [];
    cleared = 0;
    loadDrawings(items: unknown[]) { this.items = items; }
    clearDrawings() { this.items = []; this.cleared += 1; }
}

function handler(id: string) {
    const box = new Box();
    return { id, toolBox: box, createToolBox() { /* noop */ } };
}

type Sync = import('../src/desk/drawings-sync').DrawingsSync;
let MakeSync: typeof import('../src/desk/drawings-sync').DrawingsSync;

beforeAll(async () => {
    // drawings-sync 里用到了 `window`（Qt / 浏览器壳都有）→ 测试里造一个 ✓
    (globalThis as unknown as { window: unknown }).window = {
        setTimeout: () => 0,
        callbackFunction: (_message: string) => undefined,
    };
    const mod = await import('../src/desk/drawings-sync');
    MakeSync = mod.DrawingsSync;
});

function callback() {
    return (window as unknown as { callbackFunction: (m: string) => void })
        .callbackFunction;
}

describe('drawings-sync：右键删除画线必须能存下来', () => {
    it('已知 id → 存到该格的键', () => {
        const save = vi.fn();
        const sync: Sync = new MakeSync({
            cells: () => [{ id: 'cell-0', key: 'DCE.l2701|60',
                            handler: handler('cell-0') }],
            save,
            fallback: () => ({ id: 'cell-0', key: 'DCE.l2701|60' }),
        });
        sync.refresh();
        callback()('save_drawingscell-0_~_[]');
        expect(save).toHaveBeenCalledWith('DCE.l2701|60', []);
    });

    it('★ id 残留（回调 id 不在表里）→ 用活跃格兜底，删除不再丢', () => {
        const save = vi.fn();
        const sync: Sync = new MakeSync({
            cells: () => [{ id: 'cell-0', key: 'DCE.l2701|60',
                            handler: handler('cell-0') }],
            save,
            fallback: () => ({ id: 'cell-0', key: 'DCE.l2701|60' }),
        });
        sync.refresh();
        callback()('save_drawingsstale-id_~_[]');   // 旧 id（重建格子后）
        expect(save).toHaveBeenCalledWith('DCE.l2701|60', []);
    });

    it('不同格各自存自己的键（不串）', () => {
        const save = vi.fn();
        const sync: Sync = new MakeSync({
            cells: () => [
                { id: 'c0', key: 'DCE.l2701|60', handler: handler('c0') },
                { id: 'c1', key: 'DCE.pp2701|60', handler: handler('c1') },
            ],
            save,
            fallback: () => ({ id: 'c1', key: 'DCE.pp2701|60' }),
        });
        sync.refresh();
        callback()('save_drawingsc1_~_[]');
        expect(save).toHaveBeenCalledWith('DCE.pp2701|60', []);
    });
});

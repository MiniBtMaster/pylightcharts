// 「＋ → 实时图表」每次都要**新开一页**（v1.3.9-26）
//
// 用户实测 2026-11-18：已经开着一个实时图表时，再点「＋ → 实时图表」
// 什么都不发生 —— `openChart()` 按 `chart:<合约>` 去重、直接 activate 了旧页 ✗
//
// 这里用源码闸门（App 依赖整页 DOM，跑不起来）：
//  * `openChart(..., {forceNew})` → `_uniqueChartId('chart:X')` → `chart:X~2` ✓
//  * 「＋」菜单 / `default_realtime` 都传 `forceNew` ✓
//  * 补丁路由：**按 symbol 广播给同合约的每一页**（用户 2026-11-20）
//    —— 以前只喂激活页，另一页永远空白 / 只有 2 根 K 线 ✗；带 `page` 的补丁
//    （策略 / 布局）只给那一页 ✓
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const app = readFileSync('src/desk/app.ts', 'utf8');

describe('实时图表多开', () => {
    it('openChart 支持 forceNew + 唯一 id', () => {
        expect(app).toContain('forceNew?: boolean } = {}): string {');
        expect(app).toContain('? this._uniqueChartId(`chart:${symbol}`)');
        expect(app).toContain('private _uniqueChartId(base: string): string {');
        expect(app).toContain('const id = `${base}~${seq}`;');
    });

    it('「＋ → 实时图表」总是新开一页（含未连行情时的空白页）', () => {
        expect(app).toContain('openBlankChart(forceNew = true): string {');
        expect(app).toContain('this.pendingRealtimeNew = forceNew;');
        expect(app).toContain('this._openBlankChartFallback(this.pendingRealtimeNew);');
        expect(app).toContain('blank: true, label: \'实时图表\', forceNew,');
        expect(app).toContain('forceNew: this.pendingRealtimeNew,');
    });

    it('重复页的标签带序号，关掉一页不退订后端', () => {
        expect(app).toContain('const seqText = /~(');
        expect(app).toContain('.exec(id);');
        expect(app).toContain('const stillUsed = [...this.pages.entries()].some(');
        expect(app).toContain('if (!stillUsed) {');
    });

    it('补丁按 symbol 广播到每一页，带 page 的只给那一页', () => {
        expect(app).toContain('private _chartPagesFor(symbol: string): ChartPage[] {');
        expect(app).toContain('private _pagesForPatch(patch: Record<string, unknown>,');
        // 带 `page` → 精确到那一页；否则广播 ✓
        expect(app).toContain("const pageId = String(patch.page || '');");
        expect(app).toContain('return this._chartPagesFor(symbol);');
        // 「每 5 秒重开一次」的临时手段已删除（会反复推短帧 → K 线闪 ✗）
        expect(app).not.toContain('_refreshDuplicateChart');
    });
});

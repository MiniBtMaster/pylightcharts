// 副图里的蜡烛型指标（CumulativeDeltaVolume）：眼睛隐藏后再显示要能画回来
// （v1.3.9-40，用户实测 2026-11-18：副图还在，蜡烛不见了）
//
// 根因：只有一根蜡烛的副图被"隐藏"时会整块删掉（`_syncPaneVisibility`），
// 蜡烛序列随 pane 一起被删；但 `candleSeries` 缓存还留着**死序列** →
// 再次显示走"已存在"分支，往死序列 setData 静默失败 → 图上空白 ✗
import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import { IndicatorLayer } from '../src/desk/indicator';
import { StubElement, installDom } from './dom';

let dom: any;

beforeEach(() => {
    dom = installDom();
    (globalThis as any).window.LightweightCharts = {
        LineSeries: { kind: 'line' },
        HistogramSeries: { kind: 'hist' },
        CandlestickSeries: { kind: 'candles' },
    };
});

class FakeSeries {
    options: Record<string, unknown>;
    data: unknown[] = [];
    dead = false;
    kind: string;
    constructor(kind: string, options: Record<string, unknown>) {
        this.kind = kind;
        this.options = { ...options };
    }
    applyOptions(patch: Record<string, unknown>): void {
        if (this.dead) throw new Error('series removed');
        Object.assign(this.options, patch);
    }
    setData(rows: unknown[]): void {
        if (this.dead) throw new Error('series removed');
        this.data = rows;
    }
    update(): void { /* noop */ }
    priceScale() { return { applyOptions: () => undefined, width: () => 0 }; }
    createPriceLine() { return {}; }
    removePriceLine(): void { /* noop */ }
}

function makeEnv() {
    const created: FakeSeries[] = [];
    const panes: Array<{ index: number }> = [{ index: 0 }];
    const chart: any = {
        addSeries: (def: { kind: string }, options: Record<string, unknown>,
                    pane?: number) => {
            const item = new FakeSeries(def?.kind || 'line', options);
            created.push(item);
            void pane;
            return item;
        },
        removeSeries: (target: FakeSeries) => { target.dead = true; },
        panes: () => panes,
        removePane: (index: number) => { panes.splice(index, 1); },
        priceScale: () => ({ width: () => 0, applyOptions: () => undefined }),
        timeScale: () => ({}),
    };
    const layer = new IndicatorLayer(
        new StubElement('div') as never,
        () => chart,
        () => ({ background: '#000', text: '#fff',
                 up: '#26a69a', down: '#ef5350' }),
        () => null,
        () => null,
    );
    layer.setBars([{ time: 1 }, { time: 2 }] as never);
    return { layer, created, panes };
}

const candleItem = (visible: boolean) => ({
    key: 'tv:CumulativeDeltaVolume:cdv', label: 'CumulativeDeltaVolume',
    kind: 'candles', overlay: false, pane: 'CumulativeDeltaVolume',
    color: '#26a69a', visible,
    data: [[1, [1, 2, 0.5, 1.5]], [2, [1.5, 3, 1, 2.5]]],
});

describe('副图蜡烛型指标的显隐', () => {
    it('首次显示 → 建一根蜡烛并写数据', () => {
        const { layer, created } = makeEnv();
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [candleItem(true)] } as never);
        const candles = created.filter((item) => item.kind === 'candles');
        expect(candles.length).toBe(1);
        expect(candles[0].data.length).toBe(2);
    });

    it('序列被删掉（副图清空 / 眼睛关过）→ 再次显示自动重建，不是空白', () => {
        const { layer, created } = makeEnv();
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [candleItem(true)] } as never);
        const first = created.filter((item) => item.kind === 'candles')[0];
        // 模拟"序列被 chart 删掉、缓存还留着"（正是隐藏再显示时的真实情况）
        first.dead = true;
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [candleItem(true)] } as never);
        const alive = created.filter((item) => item.kind === 'candles'
            && !item.dead);
        expect(alive.length).toBe(1);
        expect(alive[0].data.length).toBe(2);
    });

    it('删副图时会清掉蜡烛缓存（下次 apply 重新创建 ✓）', () => {
        const source = readFileSync('src/desk/indicator.ts', 'utf8');
        const at = source.indexOf('private _removePane(');
        expect(at).toBeGreaterThan(0);
        const body = source.slice(at, at + 2400);
        expect(body).toContain('for (const [key, entry] of [...this.candleSeries])');
        expect(body).toContain('if (entry.pane === index)');
        // ★ 只清序列缓存，**不能删图例行**（否则眼睛没了、指标再也打不开 ✗）
        expect(body).toContain('this.candleSeries.delete(key);');
        const inner = body.indexOf('[...this.candleSeries]');
        expect(at).toBeGreaterThan(0);
        expect(inner).toBeGreaterThan(0);
        const block = body.slice(inner, inner + 400);
        expect(block).not.toContain('_dropLegendRow');
    });
});

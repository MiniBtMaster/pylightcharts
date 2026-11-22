// 换合约 / 进出回放后 `PlotInfo` 样式不能丢（v1.3.9-25）
//
// 用户实测 2026-11-17：pp_l_2609_60 布局里 `AdaptiveTrendTrail` 有 `bandstyle`
// 色带，**进回放 / 退回收放后就没了**。
//
// 根因：`_dropEverything()`（交换约 / 进出回放时调用）只删了序列，没清
// `bands` / `spans` / `tables` / `watermarks` 这些「挂在序列上的样式」缓存 →
// 重建序列后 `bands.has(key)` 为真 → 直接 continue，色带永远不再画 ✗
import { beforeEach, describe, expect, it } from 'vitest';

import { IndicatorLayer } from '../src/desk/indicator';
import { StubElement, installDom } from './dom';

let dom: any;

beforeEach(() => {
    dom = installDom();
    (globalThis as any).window.LightweightCharts = {
        LineSeries: { kind: 'line' }, HistogramSeries: { kind: 'hist' },
    };
});

class FakeSeries {
    options: Record<string, unknown>;
    data: unknown[] = [];
    primitives: unknown[] = [];
    constructor(options: Record<string, unknown>) { this.options = { ...options }; }
    applyOptions(patch: Record<string, unknown>): void {
        Object.assign(this.options, patch);
    }
    setData(rows: unknown[]): void { this.data = rows; }
    update(): void { /* noop */ }
    attachPrimitive(p: unknown): void { this.primitives.push(p); }
    detachPrimitive(p: unknown): void {
        const at = this.primitives.indexOf(p);
        if (at >= 0) this.primitives.splice(at, 1);
    }
    priceToCoordinate(price: number): number { return price; }
    coordinateToPrice(coordinate: number): number { return coordinate; }
    priceScale(): Record<string, unknown> {
        return { applyOptions: () => undefined, width: () => 0 };
    }
    createPriceLine(): Record<string, unknown> { return {}; }
    removePriceLine(): void { /* noop */ }
}

function makeEnv() {
    const series: FakeSeries[] = [];
    const chart: any = {
        addSeries: (_def: unknown, options: Record<string, unknown>) => {
            const item = new FakeSeries(options);
            series.push(item);
            return item;
        },
        removeSeries: (target: FakeSeries) => {
            const at = series.indexOf(target);
            if (at >= 0) series.splice(at, 1);
        },
        panes: () => [{ setHeight: () => undefined }],
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
    return { layer, series };
}

const line = (key: string) => ({
    key, label: key, kind: 'line', overlay: true, color: '#f6c343',
    data: [[1, 10], [2, 11]],
});

const band = {
    key: 'tv:X:band:basis:depth_trail', label: 'X 色带', kind: 'band',
    overlay: true, color: 'steelblue',
    lowerKey: 'tv:X:basis', upperKey: 'tv:X:depth_trail',
};

describe('bandstyle 换合约后不丢', () => {
    it('第一次画上色带', () => {
        const { layer, series } = makeEnv();
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [line('tv:X:basis'), line('tv:X:depth_trail'),
                              band] } as never);
        const upper = series.find((item) => item.options.color === '#f6c343'
            && item.primitives.length);
        expect(upper).toBeTruthy();
        expect(upper!.primitives.length).toBe(1);
    });

    it('换合约（_dropEverything）后色带要**重画**，不是消失', () => {
        const { layer } = makeEnv();
        const payload = [line('tv:X:basis'), line('tv:X:depth_trail'), band];
        layer.apply({ type: 'indicator', symbol: 'X', items: payload } as never);
        // 换合约 → 图层 `_dropEverything()` 再重建
        layer.apply({ type: 'indicator', symbol: 'Y', items: payload } as never);
        // ★ 拿当前还活着的序列看有没有挂上填充
        const withFill = (layer as unknown as {
            overlaySeries: Map<string, FakeSeries>;
        }).overlaySeries.get('tv:X:depth_trail');
        expect(withFill).toBeTruthy();
        expect(withFill!.primitives.length).toBe(1);
    });

    it('同一合约连续推送 → 不重复叠加填充', () => {
        const { layer } = makeEnv();
        const payload = [line('tv:X:basis'), line('tv:X:depth_trail'), band];
        layer.apply({ type: 'indicator', symbol: 'X', items: payload } as never);
        layer.apply({ type: 'indicator', symbol: 'X', items: payload } as never);
        const upper = (layer as unknown as {
            overlaySeries: Map<string, FakeSeries>;
        }).overlaySeries.get('tv:X:depth_trail');
        expect(upper!.primitives.length).toBe(1);
    });
});

// 交易信号（`kind:'marker'` + `shapeRows`）的图例行 / 自定义序列不能累积
// （v1.3.9-22，用户实测 2026-11-17：进回放 2 组信号标签、退出后 3 组）
//
// 根因：
//  * `handler.createCustomSeries(item.label, …)` 会**自动**建一行原生图例，
//    那行不归 `legendRows` 管 → 删序列时容易漏 ✗
//  * `shapeSeries` 按**原始 key** 存，`tv:X:line` 与 `X.line` 各建一条序列
//    → 图例一行行往上叠、箭头画两套 ✗
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
    constructor(o: Record<string, unknown>) { this.options = { ...o }; }
    applyOptions(p: Record<string, unknown>) { Object.assign(this.options, p); }
    setData(rows: unknown[]) { this.data = rows; }
    update() { /* noop */ }
    priceScale() { return { applyOptions: () => undefined, width: () => 0 }; }
    createPriceLine() { return {}; }
    removePriceLine() { /* noop */ }
}

function makeEnv() {
    const legendRows: Array<{ row: any; series: unknown; name?: string }> = [];
    const legend = {
        _lines: legendRows,
        makeSeriesRow(name: string, series: unknown) {
            const row = new StubElement('div');
            // ⚠ 必须写到**当前的** `_lines`（清扫会换成新数组 ✗）
            legend._lines.push({ row, series, name } as never);
        },
        setSeriesVisible: () => true,
    };
    const candle = new FakeSeries({});
    const handler: any = {
        _seriesList: [candle],
        createCustomSeries(name: string) {
            const series = new FakeSeries({});
            handler._seriesList.push(series);
            if (name) legend.makeSeriesRow(name, series);
            return { name, series, priceScale: () => ({}) };
        },
        removeSeries(wrapper: any) {
            const series = wrapper?.series;
            const at = handler._seriesList.indexOf(series);
            if (at >= 0) handler._seriesList.splice(at, 1);
            const name = wrapper?.name;
            const line = legendRows.find((r) => r.series === series
                || (!!name && r.name === name));
            if (line) {
                legendRows.splice(legendRows.indexOf(line), 1);
                line.row.remove?.();
            }
        },
    };
    const chart: any = {
        addSeries: (_d: unknown, o: Record<string, unknown>) => new FakeSeries(o),
        removeSeries: () => undefined,
        panes: () => [{ setHeight: () => undefined }],
        priceScale: () => ({ width: () => 0, applyOptions: () => undefined }),
        timeScale: () => ({}),
    };
    const layer = new IndicatorLayer(
        new StubElement('div') as never,
        () => chart,
        () => ({ background: '#000', text: '#fff', up: '#26a69a', down: '#ff0000' }),
        () => legend as never,
        () => handler,
    );
    layer.setBars([{ time: 1 }, { time: 2 }, { time: 3 }] as never);
    return { legend, handler, layer, rows: legendRows };
}

const signalItem = (line: string, marker: string) => ({
    key: `tv:AdaptiveTrendTrail:${line}`, label: `AdaptiveTrendTrail.${line}`,
    kind: 'marker', overlay: false, pane: 'AdaptiveTrendTrail', color: '#26a69a',
    data: [] as unknown[],
    shapeRows: [{ time: 1, shape: marker }, { time: 2, shape: marker }],
});

const lineItem = (line: string) => ({
    key: `tv:AdaptiveTrendTrail:${line}`,
    label: `AdaptiveTrendTrail.${line}`,
    kind: 'line', overlay: true, color: '#f6c343',
    data: [[1, 10], [2, 11]],
});

describe('signal legend rows', () => {
    it('两次 apply（同一批）→ 信号图例行不重复', () => {
        const { layer, legend } = makeEnv();
        const rows = () => legend._lines;
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [lineItem('trend'), signalItem('long_signal', 'arrowUp')] } as never);
        const first = rows().map((r) => r.name);

        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [lineItem('trend'), signalItem('long_signal', 'arrowUp')] } as never);
        const second = rows().map((r) => r.name);

        expect(second.length).toBe(first.length);
    });

    it('key 口径在两种写法间来回切 → 行数不变', () => {
        const { layer, legend } = makeEnv();
        const rows = () => legend._lines;
        const a = signalItem('long_signal', 'arrowUp');
        const b = { ...a, key: 'AdaptiveTrendTrail.long_signal' };
        layer.apply({ type: 'indicator', symbol: 'X', items: [a] } as never);
        const n1 = rows().length;

        layer.apply({ type: 'indicator', symbol: 'X', items: [b] } as never);

        layer.apply({ type: 'indicator', symbol: 'X', items: [a] } as never);

        console.log('rows', n1, rows().length, rows().map((r) => r.name));
        expect(rows().length).toBe(n1);
    });

    it('历史残留的同名图例行（自动建的）→ 一次 apply 就收敛成一行', () => {
        const { layer, legend, handler } = makeEnv();
        // 模拟旧版本留下的两行 `long_signal`（没有 ⚙、也不归我们管）
        const stale1 = new StubElement('div');
        const stale2 = new StubElement('div');
        const series1 = new FakeSeries({});
        legend._lines.push({ row: stale1, name: 'AdaptiveTrendTrail.long_signal',
                             series: series1 });
        legend._lines.push({ row: stale2, name: 'AdaptiveTrendTrail.long_signal',
                             series: series1 });
        expect(legend._lines.length).toBe(2);
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [signalItem('long_signal', 'arrowUp')] } as never);
        const names = legend._lines.map((r: any) => r.name);

        expect(names.filter((name: string) => name.includes('long_signal')).length)
            .toBe(1);
        void handler;
    });

    it('换合约（`_dropEverything`）→ 图例行和信号序列都真删，不残留', () => {
        const { layer, legend, handler } = makeEnv();
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [lineItem('trend'), signalItem('long_signal', 'arrowUp')] } as never);
        const first = legend._lines.length;
        const seriesBefore = handler._seriesList.length;
        expect(first).toBe(2);
        // 换合约：图层会 `_dropEverything()` 再重建
        layer.apply({ type: 'indicator', symbol: 'Y',
                      items: [lineItem('trend'), signalItem('long_signal', 'arrowUp')] } as never);
        expect(legend._lines.length).toBe(first);
        // 旧的信号自定义序列必须从 handler 里移除（否则图上多一套箭头 ✗）
        expect(handler._seriesList.length).toBe(seriesBefore);
    });

    it('隐藏信号（眼睛 / 设置）→ 箭头系列也要跟着隐藏', () => {
        const { layer, legend } = makeEnv();
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [signalItem('long_signal', 'arrowUp')] } as never);
        const row = legend._lines.find((r: any) =>
            String(r.name).includes('long_signal')) as any;
        expect(row).toBeTruthy();
        const series = row.series as FakeSeries;
        expect(series.options.visible).toBe(true);
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [{ ...signalItem('long_signal', 'arrowUp'),
                                visible: false }] } as never);
        expect(series.options.visible).toBe(false);
    });

    it('信号从 payload 里消失 → 图例行跟着删', () => {
        const { layer, legend } = makeEnv();
        const rows = () => legend._lines;
        layer.apply({ type: 'indicator', symbol: 'X',
                      items: [lineItem('trend'), signalItem('long_signal', 'arrowUp')] } as never);
        expect(rows().length).toBe(2);
        layer.apply({ type: 'indicator', symbol: 'X', items: [lineItem('trend')] } as never);
        expect(rows().map((r) => r.name)).toEqual(['AdaptiveTrendTrail.trend']);
    });
});

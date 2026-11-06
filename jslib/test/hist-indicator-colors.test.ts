/**
 * 柱状指标（`kind: 'hist'`，如 MACD 的 macdh）的涨 / 跌色 ✓
 *
 * 用户 2026-10-31 实测：desk 看盘窗口的 macdh 柱体是**指标线的颜色**（橙色），
 * 既不是 `upColor/downColor`，也不是「跟 K 线涨跌色」。
 *
 * 根因：`ChartPage` / `LocalChartPage` 里**第一个** `IndicatorLayer`（格 1 用的
 * 那个）的主题回调只返回 `{background, text}`，没有 `up` / `down` →
 * `item.upColor || this.theme().up || item.color` 一路退到 `item.color` ✗。
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { IndicatorLayer } from '../src/desk/indicator';
import { chartPalette } from '../src/desk/theme';
import { DomStub, StubElement, installDom } from './dom';

let dom: DomStub;

beforeEach(() => {
    dom = installDom();
    (globalThis as any).window.LightweightCharts = {
        LineSeries: { kind: 'line' },
        HistogramSeries: { kind: 'hist' },
        CandlestickSeries: { kind: 'candles' },
    };
});

interface Row { time?: number; value?: number; color?: string }
interface FakeSeries {
    type: string;
    options: Record<string, unknown>;
    data: Row[];
    applyOptions(patch: Record<string, unknown>): void;
    setData(rows: Row[]): void;
    update(row: Row): void;
    priceScale(): Record<string, unknown>;
    createPriceLine(): Record<string, unknown>;
    removePriceLine(): void;
}

function makeChart() {
    const created: FakeSeries[] = [];
    const panes: Array<Record<string, never>> = [{}];
    const chart = {
        panes: () => panes,
        addPane: () => { panes.push({}); },
        removePane: (index: number) => { panes.splice(index, 1); },
        addSeries: (_def: unknown, options: Record<string, unknown>) => {
            const series: FakeSeries = {
                type: String((_def as { kind?: string })?.kind || 'line'),
                options: { ...options },
                data: [],
                applyOptions(patch) { Object.assign(this.options, patch); },
                setData(rows) { this.data = rows; },
                update(row) { this.data = [...this.data, row]; },
                priceScale: () => ({ applyOptions: () => undefined,
                                     width: () => 0 }),
                createPriceLine: () => ({}),
                removePriceLine: () => undefined,
            };
            created.push(series);
            return series;
        },
        removeSeries: (series: FakeSeries) => {
            const index = created.indexOf(series);
            if (index >= 0) created.splice(index, 1);
        },
        priceScale: () => ({ width: () => 0, applyOptions: () => undefined }),
        timeScale: () => ({}),
    };
    return { chart, created, panes };
}

const LEGEND = {
    makeSeriesRow: () => undefined,
    setSeriesVisible: () => true,
    _lines: [] as unknown[],
};

function makeLayer(chart: unknown, up: string, down: string): IndicatorLayer {
    return new IndicatorLayer(
        new StubElement('div') as never,
        () => chart as never,
        () => ({ background: '#0f1115', text: '#d8d9db', up, down }),
        () => LEGEND as never,
        () => null,
    );
}

const ITEM = {
    key: 'pta_macd:macdh', label: 'macdh', overlay: false, kind: 'hist',
    pane: 'macd', color: '#f6c343', lineWidth: 2, lineStyle: 0,
    base: 0,
    data: [[1_700_000_000, 1.5], [1_700_000_060, -2.5],
           [1_700_000_120, 3.0], [1_700_000_180, -0.5]],
};

describe('histogram indicator colors', () => {
    it('uses the theme up/down colours when the item has none', () => {
        const { chart, created } = makeChart();
        const layer = makeLayer(chart, '#ef5350', '#26a69a');
        layer.apply({ type: 'indicator', symbol: 'X', items: [ITEM] } as never);
        const series = created.find((item) => item.type === 'hist');
        expect(series, 'histogram series created').toBeTruthy();
        expect(series!.data.map((row) => row.color)).toEqual([
            '#ef5350', '#26a69a', '#ef5350', '#26a69a',
        ]);
        // 序列自身的颜色仍然是 item.color（图例小方块用它 ✓）
        expect(series!.options.color).toBe('#f6c343');
    });

    it('prefers the indicator\'s own upColor / downColor', () => {
        const { chart, created } = makeChart();
        const layer = makeLayer(chart, '#ef5350', '#26a69a');
        layer.apply({
            type: 'indicator', symbol: 'X',
            items: [{ ...ITEM, upColor: 'rgba(39, 157, 130, 0.392)',
                      downColor: 'rgba(200, 97, 100, 0.392)' }],
        } as never);
        const series = created.find((item) => item.type === 'hist')!;
        expect(series.data.map((row) => row.color)).toEqual([
            'rgba(39, 157, 130, 0.392)', 'rgba(200, 97, 100, 0.392)',
            'rgba(39, 157, 130, 0.392)', 'rgba(200, 97, 100, 0.392)',
        ]);
    });

    it('matches the candle palette when the backend sends null', () => {
        // 后端（`indicator_catalog` / `strategy_overlay`）默认**不下发**
        // `upColor/downColor`（JSON 里是 null）→ 柱子必须跟主图 K 线涨跌色
        // 一模一样（用户 2026-11-03：默认柱体太暗、像成交量 ✗）
        const { chart, created } = makeChart();
        const dark = chartPalette('dark');
        const layer = makeLayer(chart, dark.up, dark.down);
        layer.apply({
            type: 'indicator', symbol: 'X',
            items: [{ ...ITEM, upColor: null, downColor: null }],
        } as never);
        const series = created.find((item) => item.type === 'hist')!;
        expect(series.data.map((row) => row.color)).toEqual([
            dark.up, dark.down, dark.up, dark.down,
        ]);
    });

    it('keeps the transparent colour on gap points', () => {
        const { chart, created } = makeChart();
        const layer = makeLayer(chart, '#ef5350', '#26a69a');
        layer.apply({
            type: 'indicator', symbol: 'X',
            items: [{ ...ITEM, base: 0,
                      data: [[1_700_000_000, 1.0], [1_700_000_060, null],
                             [1_700_000_120, -1.0]] }],
        } as never);
        const series = created.find((item) => item.type === 'hist')!;
        expect(series.data.map((row) => row.color)).toEqual([
            '#ef5350', 'rgba(0,0,0,0)', '#26a69a',
        ]);
    });
});

describe('histogram baseline (vbar_base)', () => {
    it('passes `base` to the Histogram series', () => {
        const { chart, created } = makeChart();
        const layer = makeLayer(chart, '#ef5350', '#26a69a');
        layer.apply({
            type: 'indicator', symbol: 'X',
            items: [{ ...ITEM, base: 50,
                      data: [[1_700_000_000, 60], [1_700_000_060, 40]] }],
        } as never);
        const series = created.find((item) => item.type === 'hist')!;
        expect(series.options.base).toBe(50);
        // 分色依旧按「值 vs base」：60 > 50 → 涨色，40 → 跌色 ✓
        expect(series.data.map((row) => row.color)).toEqual([
            '#ef5350', '#26a69a',
        ]);
    });

    it('updates `base` on later pushes', () => {
        const { chart, created } = makeChart();
        const layer = makeLayer(chart, '#ef5350', '#26a69a');
        layer.apply({ type: 'indicator', symbol: 'X', items: [ITEM] } as never);
        layer.apply({
            type: 'indicator', symbol: 'X',
            items: [{ ...ITEM, base: 50,
                      data: [[1_700_000_000, 60], [1_700_000_060, 40]] }],
        } as never);
        const series = created.find((item) => item.type === 'hist')!;
        expect(series.options.base).toBe(50);
    });
});

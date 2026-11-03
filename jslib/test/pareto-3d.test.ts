/**
 * 参数优化「帕累托前沿」：轴选择 + 三维图（2026-11-02 用户要求 ✓）
 *
 * - 目标从 3 个扩到 **9 个**；
 * - 帕累托前沿可选 **1~3 个轴**：1 个 → 权益 × 目标；2 个 → 二维；3 个 → 三维；
 * - 三维图用 `chart3d.ts`（纯数学 + canvas，不引 3D 库 ✓）。
 */
import { describe, expect, it } from 'vitest';
import {
    axisRange, axisTicks, depthOrder, drawScene, drawTooltip, hitTestPoint,
    layoutPoints, normalizeValue, projectPoint, rad, rotatePoint,
    shortNumber,
} from '../src/desk/chart3d';
import { StrategyLabPage } from '../src/desk/strategy-lab-page';

type Any = Record<string, any>;

/** 只记录调用的 canvas 上下文（drawScene 只需要这几个方法 ✓） */
function fakeCtx() {
    const calls: Array<{ op: string; args: any[] }> = [];
    const ctx: Any = {
        fillStyle: '', strokeStyle: '', lineWidth: 1, globalAlpha: 1,
        font: '', textAlign: '', textBaseline: '',
        clearRect: (...args: any[]) => calls.push({ op: 'clearRect', args }),
        beginPath: () => calls.push({ op: 'beginPath', args: [] }),
        moveTo: (...args: any[]) => calls.push({ op: 'moveTo', args }),
        lineTo: (...args: any[]) => calls.push({ op: 'lineTo', args }),
        stroke: () => calls.push({ op: 'stroke', args: [] }),
        fill: () => calls.push({ op: 'fill', args: [] }),
        arc: (...args: any[]) => calls.push({ op: 'arc', args }),
        fillText: (...args: any[]) => calls.push({ op: 'fillText', args }),
        fillRect: (...args: any[]) => calls.push({ op: 'fillRect', args }),
        save: () => calls.push({ op: 'save', args: [] }),
        restore: () => calls.push({ op: 'restore', args: [] }),
    };
    return { ctx, calls };
}

function fakePage(overrides: Any = {}): Any {
    const proto = StrategyLabPage.prototype as unknown as Any;
    const page: Any = Object.create(proto);
    Object.assign(page, {
        optTargets: [],
        optWeights: [],
        optParetoAxes: [],
        optWeightOptions: [1, 2, 0.5, -0.5, -1, -2],
        optMethodOptions: ['grid', 'optuna'],
        optSamplerOptions: ['TPESampler'],
        optPrunerOptions: ['MedianPruner'],
        optNJobsOptions: [1, 2, 4],
        optParamSpace: [],
        optParamOptions: [],
        targetOptions: ['sharpe', 'win_rate'],
        optOptions: { method: '', n_jobs: 0, n_trials: 0, sampler: '', pruner: '' },
        panels: { optimize: { clientWidth: 1200 } },
        _weightFor(index: number) {
            const value = Number(this.optWeights[index]);
            return Number.isFinite(value) && value !== 0 ? value : 1;
        },
    }, overrides);
    return page;
}

const ROWS = [
    { number: 0, result: 1_010_000, profit: 10000, win_rate: 0.55, sharpe: 1.2,
      max_drawdown: -0.12, params_length: 5 },
    { number: 1, result: 990_000, profit: -10000, win_rate: 0.42, sharpe: 0.3,
      max_drawdown: -0.3, params_length: 10 },
    { number: 2, result: 1_030_000, profit: 30000, win_rate: 0.61, sharpe: 1.8,
      max_drawdown: -0.2, params_length: 15 },
];

// --------------------------------------------------------------- 纯数学
describe('chart3d', () => {
    it('normalizeValue / axisRange / axisTicks', () => {
        expect(normalizeValue(5, 0, 10)).toBeCloseTo(0, 6);
        expect(normalizeValue(0, 0, 10)).toBeCloseTo(-1, 6);
        expect(normalizeValue(10, 0, 10)).toBeCloseTo(1, 6);
        expect(normalizeValue(NaN, 0, 10)).toBe(0);
        expect(normalizeValue(3, 3, 3)).toBe(0);          // 全相等不炸 ✓
        const [lo, hi] = axisRange([1, 2, 3]);
        expect(lo).toBeLessThan(1);
        expect(hi).toBeGreaterThan(3);
        expect(axisRange([])).toEqual([0, 1]);
        expect(axisTicks([0, 4], 4)).toEqual([0, 1, 2, 3, 4]);
        expect(shortNumber(1234567)).toContain('万');
        expect(shortNumber(0.5)).toBe('0.5000');
    });

    it('rotatePoint / projectPoint / depthOrder', () => {
        const same = rotatePoint({ x: 1, y: 0, z: 0 }, { yaw: 0, pitch: 0 });
        expect(same.x).toBeCloseTo(1, 6);
        const turned = rotatePoint({ x: 1, y: 0, z: 0 }, { yaw: rad(90), pitch: 0 });
        expect(turned.z).toBeCloseTo(1, 6);               // 绕 Y 转 90° ✓
        const center = projectPoint({ x: 0, y: 0, z: 0 }, { yaw: 0, pitch: 0 },
            100, 200, 150);
        expect(center.sx).toBeCloseTo(200, 6);
        expect(center.sy).toBeCloseTo(150, 6);
        // 近的点更大（透视 ✓）
        const near = projectPoint({ x: 0, y: 0, z: 1 }, { yaw: 0, pitch: 0 },
            100, 200, 150);
        const far = projectPoint({ x: 0, y: 0, z: -1 }, { yaw: 0, pitch: 0 },
            100, 200, 150);
        expect(near.k).toBeGreaterThan(far.k);
        expect(depthOrder([near, far]).map((item) => item.z))
            .toEqual([-1, 1]);
    });

    it('drawScene 画出所有点 + 轴标签', () => {
        const { ctx, calls } = fakeCtx();
        const points = ROWS.map((row, index) => ({
            point: { x: index - 1, y: index * 0.5 - 0.5, z: -index + 1 },
            index,
        }));
        drawScene(ctx, {
            width: 600, height: 400, points,
            axes: [{ min: 0, max: 1, label: 'A' },
                   { min: 0, max: 1, label: 'B' },
                   { min: -1, max: 1, label: 'C' }],
            camera: { yaw: rad(-35), pitch: rad(22) },
            highlight: 1,
        });
        const arcs = calls.filter((call) => call.op === 'arc');
        expect(arcs.length).toBe(points.length);          // 每个点一个圆 ✓
        const texts = calls.filter((call) => call.op === 'fillText')
            .map((call) => String(call.args[0]));
        expect(texts).toContain('A');
        expect(texts).toContain('B');
        expect(texts).toContain('C');
    });
});

// ------------------------------------------------- 页面：轴选择 / 三维
describe('参数优化页的帕累托轴', () => {
    it('候选指标：目标优先，排除 values_*/params_*/number', () => {
        const page = fakePage({ optTargets: ['sharpe', 'win_rate'] });
        const choices = page._paretoMetricChoices(ROWS);
        expect(choices.slice(0, 2)).toEqual(['sharpe', 'win_rate']);
        expect(choices).toContain('profit');
        expect(choices).toContain('max_drawdown');
        expect(choices).not.toContain('number');
        expect(choices.some((key: string) => key.startsWith('params_'))).toBe(false);
    });

    it('默认轴 = 本次优化的目标（单目标 → 只 1 个轴 ✓）', () => {
        // 单目标优化：行里还有 profit / result / win_rate… 都不能顶替
        const one = fakePage({ optTargets: ['profit'] });
        const choices = one._paretoMetricChoices(ROWS);
        expect(choices.length).toBeGreaterThan(2);      // 行内有很多数值列
        expect(one._paretoAxes(ROWS, choices)).toEqual(['profit']);
        // 两个目标 → 两个轴（二维）
        const two = fakePage({ optTargets: ['sharpe', 'win_rate'] });
        expect(two._paretoAxes(ROWS, choices)).toEqual(['sharpe', 'win_rate']);
    });

    it('默认取前 3 个目标；用户选过就用用户的', () => {
        const page = fakePage({ optTargets: ['sharpe', 'win_rate', 'profit'] });
        const choices = page._paretoMetricChoices(ROWS);
        expect(page._paretoAxes(ROWS, choices)).toEqual(
            ['sharpe', 'win_rate', 'profit']);
        page.optParetoAxes = ['profit'];
        expect(page._paretoAxes(ROWS, choices)).toEqual(['profit']);
        // 选过的轴已经不在候选里 → 退回默认 ✓
        page.optParetoAxes = ['not-a-metric'];
        expect(page._paretoAxes(ROWS, choices).length).toBe(3);
        // 完全没有数值目标 → 退回 trial 序号，不能空白 ✓
        expect(page._paretoAxes([{ number: 0 }], [])).toEqual(['number']);
    });

    it('1 个目标时横轴用账户权益（没有就退回 trial 序号）', () => {
        const page = fakePage();
        expect(page._equityKey(ROWS)).toBe('result');
        expect(page._equityKey([{ number: 0, sharpe: 1 }])).toBe('number');
    });

    it('轴选择条：3 个下拉 + 显示按钮；三维时提示拖动', () => {
        const page = fakePage({ optTargets: ['sharpe', 'win_rate', 'profit'] });
        const choices = page._paretoMetricChoices(ROWS);
        const html2 = page._paretoAxesHtml(choices, ['sharpe', 'win_rate']);
        expect(html2).toContain('data-pareto-axis="0"');
        expect(html2).toContain('data-pareto-axis="2"');
        expect(html2).toContain('data-pareto-apply');
        expect(html2).toContain('二维帕累托前沿');
        const html3 = page._paretoAxesHtml(choices,
            ['sharpe', 'win_rate', 'profit']);
        expect(html3).toContain('三维图');
    });

    it('3 个轴 → canvas 三维；2 个轴 → SVG 二维', () => {
        const page = fakePage({ optTargets: ['sharpe', 'win_rate', 'profit'] });
        const html3 = page._pareto3DHtml(ROWS, ['sharpe', 'win_rate', 'profit']);
        expect(html3).toContain('<canvas');
        expect(html3).toContain('data-opt-3d="1"');
        const svg2 = page._paretoSvg(ROWS, ['sharpe', 'win_rate']);
        expect(svg2).toContain('<svg');
        expect(svg2).toContain('sharpe');
        // 1 个目标：X = 账户权益，Y = 目标 ✓
        const svg1 = page._paretoSvg(ROWS, ['sharpe']);
        expect(svg1).toContain('账户权益（X）');
        expect(svg1).toContain('sharpe（Y）');
        // 目标本身就是权益 → X 退回 trial 序号（不能两轴一样 ✗）
        const svgSame = page._paretoSvg(ROWS, ['result']);
        expect(svgSame).toContain('trial 序号（X）');
        expect(svgSame).toContain('result（Y）');
    });

    it('三维图悬停：命中最近的 trial（命中半径内）', () => {
        const projected = layoutPoints({
            width: 600, height: 400,
            points: [{ point: { x: 0, y: 0, z: 0 }, index: 7 }],
            camera: { yaw: 0, pitch: 0 },
        });
        const first = projected[0];
        const hit = hitTestPoint(projected, first.sx + 3, first.sy - 2, 12);
        expect(hit?.index).toBe(7);
        expect(hitTestPoint(projected, first.sx + 60, first.sy, 12))
            .toBeUndefined();
    });

    it('三维图悬停浮层：画出 trial + 各轴数值 + 参数', () => {
        const { ctx, calls } = fakeCtx();
        drawTooltip(ctx, {
            x: 100, y: 100, width: 600, height: 400,
            lines: ['Trial 3', 'profit: 1.2万', 'win_rate: 0.55',
                    'length1=15  length2=36'],
        });
        const texts = calls.filter((call) => call.op === 'fillText')
            .map((call) => String(call.args[0]));
        expect(texts).toEqual(['Trial 3', 'profit: 1.2万', 'win_rate: 0.55',
                               'length1=15  length2=36']);
        expect(calls.some((call) => call.op === 'fillRect')).toBe(true);
        // 浮层不能画出画布外 ✓
        const { ctx: ctx2, calls: calls2 } = fakeCtx();
        drawTooltip(ctx2, {
            x: 590, y: 5, width: 600, height: 400, lines: ['Trial 9'],
        });
        const rect = calls2.find((call) => call.op === 'fillRect');
        expect(rect).toBeTruthy();
        expect(Number(rect!.args[0])).toBeLessThanOrEqual(600);
        expect(Number(rect!.args[1])).toBeGreaterThanOrEqual(0);
    });

    it('单目标没有权益 → X 用真 trial 序号（整数刻度、和表格一致）', () => {
        // 后端已把 `trial` 归一成 1 基 → 这里给 1/4/8 ✓
        const rows = [{ trial: 1, sharpe: 0.5 }, { trial: 4, sharpe: 0.2 },
                      { trial: 8, sharpe: -0.1 }];
        const page = fakePage();
        const html = page._paretoSvg(rows, ['sharpe']);
        // 轴名 + 整数刻度（不再出现 -2.36 / 6.32 这种插值 ✗）
        expect(html).toContain('trial 序号（X）');
        expect(html).not.toMatch(/#\d+\.\d/);
        // tooltip 用**真 trial 序号**（+1），不是列表行号 ✓
        expect(html).toContain('Trial 1');
        expect(html).toContain('Trial 4');
        expect(html).toContain('Trial 8');
    });

    it('单目标有权益 → X = 账户权益（tooltip 仍是真 trial 序号）', () => {
        const page = fakePage({ optTargets: ['sharpe'] });
        const html = page._paretoSvg(ROWS, ['sharpe']);
        expect(html).toContain('账户权益（X）');
        // ROWS 的 trial 列为缺省 → 退回 number（1 基）✓
        expect(html).toContain('Trial 1');
    });

    it('三维图的「综合最优」按权重方向算', () => {
        const page = fakePage({ optTargets: ['sharpe', 'win_rate', 'profit'],
                                optWeights: [1, 1, 1] });
        expect(page._bestParetoIndex(ROWS,
            ['sharpe', 'win_rate', 'profit'])).toBe(2);   // 第 3 条全面最好 ✓
        // 权重方向：正 = 越大越好、负 = 越小越好（单轴最直观 ✓）
        const two = [{ p: 10 }, { p: 0 }];
        page.optTargets = ['p'];                        // 权重按目标名的下标取 ✓
        page.optWeights = [1];
        expect(page._bestParetoIndex(two, ['p'])).toBe(0);    // 最大化 → 10 ✓
        page.optWeights = [-1];
        expect(page._bestParetoIndex(two, ['p'])).toBe(1);    // 最小化 → 0 ✓
    });

    it('优化目标有 9 个位置', () => {
        const page = fakePage({ targetOptions: ['sharpe', 'win_rate'],
                                optTargets: [], running: false });
        const html = page._optSettingsHtml();
        for (let index = 0; index < 9; index += 1) {
            expect(html).toContain(`data-opt-target="${index}"`);
            expect(html).toContain(`data-opt-weight="${index}"`);
        }
        expect(html).toContain('最多 9 个');
    });
});

/**
 * 参数优化页的「优化设置」UI（用户要求 2026-10-30 ✓）
 *
 * 除了 1~3 个目标外，还要能设置 `OptimizeConfig` 的 method / n_jobs / n_trials /
 * sampler / pruner、每个目标的权重（weights）以及待优化参数（params），
 * 而且这些**都是选项**（参数名也是下拉）✓
 *
 * 这里直接对 `StrategyLabPage` 的原型方法做单元测试（不需要真 DOM）：
 * 拼出来的 HTML / 发回后端的 payload 才是这次改动的风险点。
 */
import { describe, expect, it } from 'vitest';
import { StrategyLabPage } from '../src/desk/strategy-lab-page';

type Any = Record<string, any>;

function makeFake(overrides: Any = {}): Any {
    const proto = StrategyLabPage.prototype as unknown as Any;
    const fake: Any = Object.create(proto);
    Object.assign(fake, {
        running: false,
        optTargets: ['sharpe', 'max_drawdown'],
        optWeights: [1, -1],
        targetOptions: ['sharpe', 'max_drawdown', 'profit_ratio', 'volatility'],
        optOptions: {
            method: 'optuna', n_jobs: 4, n_trials: 50,
            sampler: 'TPESampler', pruner: 'MedianPruner',
        },
        optParamSpace: [
            { name: 'length1', kind: 'range', low: '5', high: '30', step: '5',
              list: '', value: '' },
            { name: 'mode', kind: 'list', low: '', high: '', step: '',
              list: 'a,b', value: '' },
        ],
        optParamOptions: ['length1', 'length2', 'mode'],
        optMethodOptions: ['grid', 'optuna', 'ga'],
        optSamplerOptions: ['TPESampler', 'RandomSampler'],
        optPrunerOptions: ['MedianPruner', 'NopPruner'],
        optNJobsOptions: [1, 2, 4, 8, -1],
        optWeightOptions: [1, 2, 0.5, -0.5, -1, -2],
        options: { onToast: () => undefined, onCommand: () => undefined },
    }, overrides);
    return fake;
}

/** 假的 optimize 面板：`[data-opt-target=i]` / `[data-opt-weight=i]` / 设置项 */
function makeFakePanel(config: {
    targets?: string[];
    weights?: string[];
    options?: Record<string, string>;
} = {}): Any {
    const targets = config.targets || [];
    const weights = config.weights || [];
    const options = config.options || {};
    const nodes = Object.entries(options).map(([key, value]) => ({
        dataset: { optOpt: key },
        value,
    }));
    return {
        querySelector: (selector: string) => {
            const target = /\[data-opt-target="(\d+)"\]/.exec(selector);
            if (target) return { value: targets[Number(target[1])] ?? '' };
            const weight = /\[data-opt-weight="(\d+)"\]/.exec(selector);
            if (weight) return { value: weights[Number(weight[1])] ?? '' };
            return null;
        },
        querySelectorAll: (selector: string) =>
            (selector === '[data-opt-opt]' ? nodes : []),
    };
}

describe('参数优化页的优化设置', () => {
    it('目标 / 权重 / 设置 / 参数网格都渲染出来', () => {
        const fake = makeFake();
        const html: string = fake._optSettingsHtml();

        // ① 目标 + 权重下拉（3 个目标位，每个都带权重下拉 ✓）
        expect(html).toContain('data-opt-target="0"');
        expect(html).toContain('data-opt-weight="0"');
        expect(html).toContain('data-opt-weight="2"');
        expect(html).toContain('（最大化）');
        expect(html).toContain('（最小化）');

        // ② 优化设置：方法 / 并行 / 试验次数 / 采样器 / 剪枝器
        for (const key of ['method', 'n_jobs', 'n_trials', 'sampler', 'pruner']) {
            expect(html).toContain(`data-opt-opt="${key}"`);
        }
        // 后端下发的选项 + 当前值
        expect(html).toContain('value="optuna" selected');
        expect(html).toContain('value="4" selected');
        expect(html).toContain('value="50"');
        expect(html).toContain('value="TPESampler" selected');
        expect(html).toContain('value="MedianPruner" selected');

        // ③ 参数网格：一行一个参数（参数名也是下拉 ✓）
        expect(html).toContain('desk-strategy-opt-params');
        expect(html).toContain('desk-opt-param-row');
        expect(html).toContain('data-opt-param="0" data-field="name"');
        expect(html).toContain('data-opt-param="0" data-field="low"');
        expect(html).toContain('data-opt-param="1" data-field="list"');
        expect(html).toContain('data-opt-param-del="0"');
        expect(html).toContain('data-opt-param-add');
        expect(html).toContain('>length1<');
        expect(html).toContain('数值范围');
        expect(html).toContain('固定选项');
        expect(html).toContain('固定值');
    });

    it('参数网格 → param_space 字典（范围 / 选项 / 固定值）', () => {
        const fake = makeFake({
            optParamSpace: [
                { name: 'length1', kind: 'range', low: '5', high: '30',
                  step: '5', list: '', value: '' },
                { name: 'length2', kind: 'range', low: '10', high: '60',
                  step: '', list: '', value: '' },
                { name: 'mode', kind: 'list', low: '', high: '', step: '',
                  list: 'a, b，c', value: '' },
                { name: 'fixed', kind: 'fixed', low: '', high: '', step: '',
                  list: '', value: '7' },
                { name: '', kind: 'range', low: '1', high: '2', step: '',
                  list: '', value: '' },
                { name: 'broken', kind: 'range', low: '', high: '', step: '',
                  list: '', value: '' },
            ],
        });
        expect(fake._optParamPayload()).toEqual({
            length1: [5, 30, 5],
            length2: [10, 60],
            mode: ['a', 'b', 'c'],
            fixed: 7,
        });
    });

    it('后端 -> 前端：param_space 字典还原成可编辑的行', () => {
        const fake = makeFake();
        const rows = fake._paramRowsFromSpace({
            length1: [5, 30, 5], mode: ['a', 'b'], fixed: 7,
        });
        expect(rows).toEqual([
            { name: 'length1', kind: 'range', low: '5', high: '30',
              step: '5', list: '', value: '' },
            { name: 'mode', kind: 'list', low: '', high: '', step: '',
              list: 'a,b', value: '' },
            { name: 'fixed', kind: 'fixed', low: '', high: '', step: '',
              list: '', value: '7' },
        ]);
    });

    it('「按当前目标重新优化」把权重 / 设置 / 参数一起发下去', () => {
        const sent: Array<{ cmd: string; payload: Any }> = [];
        // 面板里的下拉（目标 / 权重 / 优化设置）——用假节点模拟用户的选择 ✓
        const panel = makeFakePanel({
            targets: ['sharpe', 'max_drawdown', 'profit_ratio'],
            weights: ['1', '-1', '2'],
            options: { method: 'optuna', n_jobs: '4', n_trials: '50',
                       sampler: 'TPESampler', pruner: 'MedianPruner' },
        });
        const fake = makeFake({
            running: false, optRows: [], optTargets: [], optWeights: [],
            panels: { optimize: panel },
            _renderOptimization: () => undefined,
            options: {
                onToast: () => undefined,
                onCommand: (cmd: string, payload: Any) => sent.push({ cmd, payload }),
            },
        });
        fake._restartOptimize();
        const start = sent.find((item) => item.cmd === 'strategy_start');
        expect(start).toBeTruthy();
        const payload = start!.payload;
        expect(payload.mode).toBe('optimize');
        expect(payload.metrics).toEqual(['sharpe', 'max_drawdown', 'profit_ratio']);
        expect(payload.weights).toEqual([1, -1, 2]);
        expect(payload.options.method).toBe('optuna');
        expect(payload.options.n_trials).toBe(50);
        expect(payload.param_space).toEqual({ length1: [5, 30, 5], mode: ['a', 'b'] });
    });

    it('一个目标都没选时不发命令（提示至少 1 个）', () => {
        const sent: Any[] = [];
        const toasts: string[] = [];
        const fake = makeFake({
            optTargets: [],
            panels: { optimize: makeFakePanel({ targets: ['', '', ''] }) },
            options: {
                onToast: (level: string, text: string) => toasts.push(`${level}:${text}`),
                onCommand: (cmd: string) => sent.push(cmd),
            },
        });
        fake._restartOptimize();
        expect(sent).toEqual([]);
        expect(toasts.length).toBe(1);
    });
});

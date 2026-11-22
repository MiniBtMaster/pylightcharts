// 指标参数持久化（v1.3.9-49）
//
// 用户 2026-11-19：`zigzag_support_resistance` 把 up_thresh/down_thresh 改成 0，
// 重新加载指标后点⚙，卡片里还是**默认参数**。
// 现在：应用参数 → 落盘 `indicator_params`；卡片打开用上次保存的值；
// 后端加指标时也用 saved 当默认。
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const chart = readFileSync('src/desk/chart-page.ts', 'utf8');
const local = readFileSync('src/desk/local-chart-page.ts', 'utf8');
const backend = readFileSync('../minibt/desk/app.py', 'utf8');

describe('指标参数持久化', () => {
    it('两个页面都记住参数并落盘', () => {
        for (const source of [chart, local]) {
            expect(source).toContain('private savedParams:');
            expect(source).toContain("key: 'indicator_params',");
            expect(source).toContain('this._rememberParams(baseKey, state.params);');
        }
    });

    it('卡片打开用上次保存的参数（覆盖默认）', () => {
        for (const source of [chart, local]) {
            expect(source).toContain('...remembered');
            expect(source).toContain('params: { ...(item.params || {}), ...remembered },');
        }
    });

    it('后端：加指标用 saved 当默认 + 记住这次传的参数', () => {
        expect(backend).toContain('def saved_indicator_params(');
        expect(backend).toContain('def remember_indicator_params(');
        expect(backend).toContain('merged_params = {**self.saved_indicator_params(key), **passed}');
    });

    it('后端：图例卡片参数补 saved（3 处 _attach_indicator_params）', () => {
        expect(backend.match(/_with_saved_params\(/g)?.length || 0)
            .toBeGreaterThanOrEqual(4);
    });
});

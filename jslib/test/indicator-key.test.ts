// 回放反复切换时图例重复（v1.3.9-20）
//
// 同一指标有两种 key 口径：回放/布局用 `tv:X:line`，实时推送用 `X.line`。
// 两套都进 items → 图例出现两行同名指标（用户实测 2026-11-17 ✗）。
import { describe, expect, it } from 'vitest';

import { dedupeIndicatorItems, normalizeIndicatorKey }
    from '../src/desk/indicator-key';

describe('指标 key 归一化', () => {
    it('不同口径归一成同一家族', () => {
        expect(normalizeIndicatorKey('tv:AdaptiveTrendTrail:trend'))
            .toBe('AdaptiveTrendTrailtrend');
        expect(normalizeIndicatorKey('AdaptiveTrendTrail.trend'))
            .toBe('AdaptiveTrendTrailtrend');
        expect(normalizeIndicatorKey('pi:我的指标/StyleZoo_VP:vp'))
            .toBe('我的指标StyleZooVPvp');
        // 内置指标大小写是身份的一部分，不能抹平 ✓
        expect(normalizeIndicatorKey('MA20')).toBe('MA20');
        expect(normalizeIndicatorKey('MACD_DIF')).toBe('MACDDIF');
    });

    it('框式指标的多条线/多线指标不能归一（各留一行 ✓）', () => {
        const keys = ['pta_adx:adxx', 'pta_adx:adxr', 'pta_adx:dmp',
                      'pta_adx:dmn'];
        const families = new Set(keys.map(normalizeIndicatorKey));
        expect(families.size).toBe(4);
    });
});

describe('同家族去重', () => {
    it('两种口径都传进来 → 只留最后一份（数据最新 ✓）', () => {
        const items = dedupeIndicatorItems([
            { key: 'tv:AdaptiveTrendTrail:trend', label: 'AdaptiveTrendTrail.trend',
              data: [[1, 10]] },
            { key: 'tv:AdaptiveTrendTrail:basis', label: 'AdaptiveTrendTrail.basis',
              data: [[1, 20]] },
            { key: 'AdaptiveTrendTrail.trend', label: 'AdaptiveTrendTrail.trend',
              data: [[1, 11]] },
        ]);
        // key 统一成「带来源冒号」那个口径（确定的 ✓），数据用最新的
        expect(items.map((item) => item.key))
            .toEqual(['tv:AdaptiveTrendTrail:trend', 'tv:AdaptiveTrendTrail:basis']);
        expect((items[0] as { data: number[][] }).data).toEqual([[1, 11]]);
    });

    it('两种口径交替出现 → 每一拍都选同一个 key（否则图例反复重建 ✗）', () => {
        const only = dedupeIndicatorItems([{ key: 'tv:X:trend', data: [[1, 2]] }]);
        const both = dedupeIndicatorItems([
            { key: 'tv:X:trend', data: [[1, 2]] },
            { key: 'X.trend', data: [[1, 2]] },
        ]);
        const flipped = dedupeIndicatorItems([
            { key: 'X.trend', data: [[1, 2]] },
            { key: 'tv:X:trend', data: [[1, 2]] },
        ]);
        expect(only[0].key).toBe('tv:X:trend');
        expect(both[0].key).toBe('tv:X:trend');
        expect(flipped[0].key).toBe('tv:X:trend');   // 顺序变了也一样 ✓
    });

    it('反复切换回放（同一批推 3 次）→ 行数不变 ✓', () => {
        const payload = [
            { key: 'tv:X:trend' }, { key: 'tv:X:basis' },
            { key: 'X.trend' }, { key: 'X.basis' },
        ];
        for (let round = 0; round < 5; round += 1) {
            expect(dedupeIndicatorItems(payload).length).toBe(2);
        }
    });

    it('顺序按首次出现（图例不跳 ✓）', () => {
        const items = dedupeIndicatorItems([
            { key: 'pta_adx:adxx' }, { key: 'pta_sma:sma' },
            { key: 'pta_adx:adxr' }, { key: 'pta_adx:adxx' },
        ]);
        expect(items.map((item) => item.key))
            .toEqual(['pta_adx:adxx', 'pta_sma:sma', 'pta_adx:adxr']);
    });

    it('空 / 没有 key 的项直接丢掉（不会画出空行 ✓）', () => {
        expect(dedupeIndicatorItems([])).toEqual([]);
        expect(dedupeIndicatorItems(null)).toEqual([]);
        expect(dedupeIndicatorItems([{ key: '' }, { key: 'A' }]))
            .toHaveLength(1);
    });
});

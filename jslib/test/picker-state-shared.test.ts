// 位置记忆必须**两种图表都覆盖**（实时图表 + 本地图表，v1.3.9-47）
//
// 用户 2026-11-19：实时图表改了，但测试用的是**本地图表** → 完全没生效 ✗
// 现在两页共用 `picker-state.ts`（localStorage + 后端设置双保险）。
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
const chart = readFileSync('src/desk/chart-page.ts', 'utf8');
const local = readFileSync('src/desk/local-chart-page.ts', 'utf8');

describe('picker 位置记忆（两页共用）', () => {
    it('共享模块：读写 + 双保险 + 恢复顺序', () => {
        expect(shared).toContain('export function readPickerState()');
        expect(shared).toContain('export function savePickerState(');
        expect(shared).toContain("const STORAGE_KEY = 'desk.indicatorPicker';");
        expect(shared).toContain("const SETTING_KEY = 'indicator_picker_state';");
        expect(shared).toContain('export function restorePickerState(');
        // 顺序：筛选 → open(section) → restoreState
        const at = shared.indexOf('export function restorePickerState(');
        const body = shared.slice(at, at + 1400);
        expect(body.indexOf('picker.setOverlayFilter(filter);'))
            .toBeLessThan(body.indexOf('picker.open(section);'));
        expect(body.indexOf('picker.open(section);'))
            .toBeLessThan(body.indexOf('picker.restoreState({'));
    });

    it('实时图表页接上共享模块', () => {
        expect(chart).toContain("from './picker-state'");
        expect(chart).toContain('bindPickerState(this.indicatorPicker);');
        expect(chart).toContain('restorePickerState(this.indicatorPicker,');
        expect(chart).toContain('setPickerRemote(settings?.indicator_picker_state);');
    });

    it('本地图表页也接上（这次的关键 ✓）', () => {
        expect(local).toContain("from './picker-state'");
        expect(local).toContain('bindPickerState(this.indicatorPicker);');
        expect(local).toContain('restorePickerState(this.indicatorPicker,');
        expect(local).toContain('setPickerRemote(');
        // 不能再出现"写死回收藏"的旧逻辑
        expect(local).not.toContain(
            "this.indicatorPicker.open(favorites.length ? 'favorites' : 'all');");
    });
});

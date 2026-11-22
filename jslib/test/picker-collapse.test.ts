// 「指标、衡量标准和策略」选择器：**左侧导航收起 / 展开 + 状态持久化**
// （用户 2026-11-20）
//
// 三件事：
//  1. 左栏顺序固定为 个人 → 内置指标 → 交易系统（后端 `_picker_groups`）
//  2. 分组标题可点击收起 / 展开（`toggleGroup`）
//  3. 收起状态 + 左导航滚动 + 指标列表滚动都持久化，下次打开恢复
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const picker = readFileSync('src/panels/indicator-picker.ts', 'utf8');
const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
const page = readFileSync('src/desk/chart-page.ts', 'utf8');
const local = readFileSync('src/desk/local-chart-page.ts', 'utf8');

describe('选择器左侧导航：收起 / 展开', () => {
    it('分组标题可点击 → toggleGroup（带 ▾ 图标 + 收起样式）', () => {
        expect(picker).toContain('toggleGroup(key: string): void {');
        expect(picker).toContain('title.addEventListener(\'click\', () => this.toggleGroup(key));');
        expect(picker).toContain("chev.textContent = '▾';");
        expect(picker).toContain("'pylc-ip-group' + (collapsed ? ' collapsed' : '')");
        // 收起时 section 行加 `hidden`（CSS display:none，不重建 DOM 更稳）
        expect(picker).toContain("+ (collapsed ? ' hidden' : '');");
        expect(picker).toContain('.pylc-ip-section.hidden{display:none}');
    });

    it('收起状态对外可读可写，并通知宿主', () => {
        expect(picker).toContain('get collapsedGroups(): string[] {');
        expect(picker).toContain('setCollapsed(keys: string[]): void {');
        expect(picker).toContain('this.onGroupsCallback?.(this.collapsedGroups);');
        expect(picker).toContain('public onGroupsCallback: ((collapsed: string[]) => void) | null = null;');
    });

    it('恢复时：上次停的 section 若被收起 → 自动展开它所在分组', () => {
        const at = picker.indexOf('if (state.collapsed) {');
        expect(at).toBeGreaterThan(0);
        const body = picker.slice(at, at + 600);
        expect(body).toContain('this.collapsed = new Set(');
        expect(body).toContain('if (owns) this.collapsed.delete(String(group.key));');
    });

    it('左导航滚动位置可读 + 可恢复', () => {
        expect(picker).toContain('get treeScrollTop(): number {');
        expect(picker).toContain('restoreTreeScroll(top: number): void {');
        expect(picker).toContain('this.tree.scrollTop = value;');
    });
});

describe('选择器状态持久化（收起 + 两处滚动）', () => {
    it('状态结构里带 collapsed / treeScroll', () => {
        expect(shared).toContain('collapsed: string[];');
        expect(shared).toContain('treeScroll: number;');
        expect(shared).toContain('collapsed: _strings(data.collapsed),');
        expect(shared).toContain('treeScroll: Number(data.treeScroll) || 0,');
    });

    it('关闭时把最终滚动位置落盘（force 推后端，不只写 localStorage）', () => {
        expect(picker).toContain('this.onCloseCallback?.({');
        expect(picker).toContain('treeScroll: this.treeScrollTop,');
        expect(shared).toContain('picker.onCloseCallback = (state) => {');
        expect(shared).toContain('}, true);');
        expect(shared).toContain('export function savePickerState(patch: Partial<PickerState>,');
        expect(shared).toContain('if (!force && !structural) return;');
    });

    it('收起状态 / 左导航滚动也进恢复参数', () => {
        expect(shared).toContain('collapsed: saved.collapsed, treeScroll: saved.treeScroll,');
        expect(shared).toContain('picker.onGroupsCallback = (collapsed) => savePickerState({ collapsed });');
    });

    it('图表页在 onFilterCallback **之后**才 bindPickerState（否则筛选记不住）', () => {
        const filterAt = page.indexOf('this.indicatorPicker.onFilterCallback = (kind) => {');
        const bindAt = page.indexOf('bindPickerState(this.indicatorPicker);');
        expect(filterAt).toBeGreaterThan(0);
        expect(bindAt).toBeGreaterThan(filterAt);
        // 本地图表页同样顺序
        const localFilter = local.indexOf('this.indicatorPicker.onFilterCallback = (kind) => {');
        const localBind = local.indexOf('bindPickerState(this.indicatorPicker);');
        expect(localBind).toBeGreaterThan(localFilter);
    });
});

describe('左栏分组顺序：个人 → 内置指标 → 交易系统', () => {
    it('后端 `_picker_groups` 按这个顺序返回', () => {
        const app = readFileSync('../minibt/desk/app.py', 'utf8');
        const at = app.indexOf('def _picker_groups');
        expect(at).toBeGreaterThan(0);
        const body = app.slice(at, app.indexOf('def picker_items', at));
        const personal = body.indexOf("{'key': 'personal'");
        const builtin = body.indexOf("{'key': 'builtin'");
        const trading = body.indexOf("{'key': 'tradingsystem'");
        expect(personal).toBeGreaterThan(0);
        expect(builtin).toBeGreaterThan(personal);
        expect(trading).toBeGreaterThan(builtin);
    });
});

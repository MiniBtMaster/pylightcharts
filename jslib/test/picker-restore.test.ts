// 「指标、衡量标准和策略」选择器：记住上次打开的位置（v1.3.9-43）
//
// 用户 2026-11-18 要求：下次打开停在**上次的指标位置**（选中的分组 + 滚动位置），
// 而不是每次都回到「收藏 / 全部指标」顶部。
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const picker = readFileSync('src/panels/indicator-picker.ts', 'utf8');
const page = readFileSync('src/desk/chart-page.ts', 'utf8');
const tv = readFileSync('src/desk/tv-page.ts', 'utf8');

describe('指标选择器位置记忆', () => {
    it('picker 暴露 section / scroll 并上报变化', () => {
        expect(picker).toContain('onSectionCallback');
        expect(picker).toContain('onScrollCallback');
        expect(picker).toContain('get sectionKey(): string {');
        expect(picker).toContain('get scrollTop(): number {');
        expect(picker).toContain('restoreScroll(top: number): void {');
        // 滚动 → 节流 400ms 上报
        expect(picker).toContain('this.list.addEventListener(\'scroll\'');
        expect(picker).toContain('}, 400);');
    });

    it('open() 不传 section 时**保持当前**（不是每次回收藏）', () => {
        const at = picker.indexOf('    open(section = ');
        expect(at).toBeGreaterThan(0);
        const body = picker.slice(at, at + 400);
        expect(body).toContain("open(section = ''): void {");
        expect(body).toContain('if (section) this.setSection(section);');
    });

    it('恢复顺序：左侧 section → 顶部筛选 → 定位 / 滚动', () => {
        // picker：restoreState 一次性摆好（先 section + 筛选，再定位）
        expect(picker).toContain('restoreState(state: {');
        const at = picker.indexOf('restoreState(state: {');
        const body = picker.slice(at, at + 2000);
        expect(body).toContain('this.section = section;');
        expect(body).toContain('this.overlayFilter = filter ===');
        expect(body).toContain('this._renderTree();');
        expect(body).toContain('this._render();');
        expect(body.indexOf('this._render();')).toBeLessThan(
            body.indexOf('this.revealKey(key)'));
        // 左侧导航：当前 section 自动滚到可见（长列表也看得出打开了哪个 ✓）
        expect(picker).toContain('.pylc-ip-section.on');

        // 图表页：先把筛选对齐再去定位
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain('const filter = (saved.filter ||');
        expect(page).toContain('restorePickerState(this.indicatorPicker,');
    });

    it('顶部筛选（全部 / 主图叠加 / 副图）也跟着持久化', () => {
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain('savePickerState({ filter: kind });');
        expect(picker).toContain("get filterKey(): 'all' | 'main' | 'sub' {");
    });

    it('光标停留的指标优先（定位 + 高亮），没停留才用滚动位置', () => {
        expect(picker).toContain('row.dataset.itemKey');
        expect(picker).toContain('revealKey(key: string): boolean {');
        expect(picker).toContain("row.classList.add('pylc-ip-row-focus');");
        expect(picker).toContain('onFocusCallback: ((key: string) => void) | null = null;');
        // 图表页：交给 restoreState（内部：key 优先，没有才 restoreScroll ✓）
        expect(page).toContain('restorePickerState(this.indicatorPicker,');
        expect(picker).toContain('if (key && this.revealKey(key)) {');
        expect(picker).toContain('else if (state.scroll) this.restoreScroll(state.scroll);');
        expect(page).toContain("from './picker-state'");
        // 卡片页同样
        expect(tv).toContain('revealKey(key: string): boolean {');
        expect(tv).toContain("if (this.pendingFocus && this.revealKey(this.pendingFocus)) {");
    });

    it('「指标和策略」页：按分组记住滚动位置（下次打开回到原处 ✓）', () => {
        expect(tv).toContain('private readonly scrollMemory = new Map<string, number>();');
        expect(tv).toContain('private _scrollKey(): string {');
        expect(tv).toContain('this.scrollMemory.set(this._scrollKey(),');
        expect(tv).toContain('const remembered = this.scrollMemory.get(this._scrollKey());');
    });

    it('图表页：localStorage 持久化 + 打开时恢复', () => {
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain("window.localStorage.getItem(STORAGE_KEY)");
        expect(shared).toContain('window.localStorage.setItem(STORAGE_KEY');
        expect(shared).toContain('picker.restoreState({');
        // section 不存在（目录变了）→ 回落到 收藏 / 全部指标 ✓
        expect(shared).toContain('saved.section && (knownSections.size === 0');
    });
});

// 双保险：localStorage + 后端设置（Qt webview 里 localStorage 偶发不可用）
describe('指标选择器状态双保险', () => {
    it('localStorage 与后端设置合并，localStorage 优先', () => {
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain('const data: Record<string, unknown> = { ...remote, ...local };');
    });

    it('保存时同时写后端（节流 1s，避免滚动刷爆）', () => {
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain('key: SETTING_KEY');
        expect(shared).toContain('pushTimer = window.setTimeout');
    });

    it('后端设置白名单里有 indicator_picker_state', () => {
        const prefs = readFileSync('../minibt/desk/user_prefs.py', 'utf8');
        expect(prefs).toContain("'indicator_picker_state',");
    });

    it('打开时先播种（第一次打开也能记住）', () => {
        const shared = readFileSync('src/desk/picker-state.ts', 'utf8');
        expect(shared).toContain('savePickerState({ section, filter });');
    });
});

/**
 * 「指标、衡量标准和策略」选择器的**位置记忆**（实时图表 + 本地图表共用 ✓）
 *
 * 记住这些（用户 2026-11-19 / 11-20 要求）：
 *  1. 左侧导航选中的 `section`（收藏 / 指标 / 交易系统 / 各库…）
 *  2. 左侧导航的**收起状态** `collapsed`（每个分组是否折叠 ✓ 11-20 新增）
 *  3. 左侧导航的滚动位置 `treeScroll`（11-20 新增）
 *  4. 顶部筛选：全部 / 主图叠加 / 副图
 *  5. 光标停留（或点过）的指标 `key` —— 有它就直接定位 + 高亮
 *  6. 右侧列表滚动位置 `scroll` —— 没停留过指标时用它
 *
 * 恢复顺序必须是 **收起状态 → section → 筛选 →（指标 / 滚动）**
 * （行数取决于筛选，导航高度取决于收起状态 ✓）。
 *
 * 存储双保险：`localStorage` + 后端设置 `indicator_picker_state`
 * （Qt webview 里 localStorage 偶发不可用 ✓）。
 */

export type PickerFilter = '' | 'all' | 'main' | 'sub';

export interface PickerState {
    section: string;
    scroll: number;
    key: string;
    filter: PickerFilter;
    /** 左侧**收起**的分组 key（默认全部展开 ✓） */
    collapsed: string[];
    /** 左侧导航滚动位置（11-20 新增 ✓） */
    treeScroll: number;
}

const STORAGE_KEY = 'desk.indicatorPicker';
const SETTING_KEY = 'indicator_picker_state';

let remote: Record<string, unknown> = {};
let pushTimer = 0;
let push: ((state: PickerState) => void) | null = null;

/** 后端设置同步进来（`setSettings` 时调用 ✓） */
export function setPickerRemote(value: unknown): void {
    try {
        const parsed = typeof value === 'string' && value
            ? JSON.parse(value) : value;
        if (parsed && typeof parsed === 'object') {
            remote = parsed as Record<string, unknown>;
        }
    } catch { /* 坏数据 → 忽略 ✓ */ }
}

/** `unknown` → 字符串数组（后端存的是 JSON，可能是任意形状 ✓） */
function _strings(value: unknown): string[] {
    if (Array.isArray(value)) {
        return value.map((item) => String(item)).filter(Boolean);
    }
    if (typeof value === 'string' && value) {
        try {
            return _strings(JSON.parse(value));
        } catch { return []; }
    }
    return [];
}

/** 读当前状态（本地优先、后端兜底 ✓） */
export function readPickerState(): PickerState {
    let local: Record<string, unknown> = {};
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) local = JSON.parse(raw) as Record<string, unknown>;
    } catch { /* 无存储 → 只用后端 ✓ */ }
    const data: Record<string, unknown> = { ...remote, ...local };
    const filter = String(data.filter || '');
    return {
        section: String(data.section || ''),
        scroll: Number(data.scroll) || 0,
        key: String(data.key || ''),
        filter: filter === 'main' || filter === 'sub' ? filter
            : (filter === 'all' ? 'all' : ''),
        collapsed: _strings(data.collapsed),
        treeScroll: Number(data.treeScroll) || 0,
    };
}

/**
 * 写状态（localStorage 立刻写；后端节流 1s ✓）
 *
 * @param patch 要改的字段
 * @param force `true` → 只有滚动变化（不需要 `section` / `filter`）时也推后端；
 *              关闭选择器时用它把**最终**滚动位置落盘 ✓
 */
export function savePickerState(patch: Partial<PickerState>,
                                force = false): void {
    const state = readPickerState();
    const next: PickerState = {
        section: patch.section !== undefined ? patch.section : state.section,
        scroll: patch.scroll !== undefined ? patch.scroll : state.scroll,
        key: patch.key !== undefined ? patch.key : state.key,
        filter: patch.filter !== undefined ? patch.filter : state.filter,
        collapsed: patch.collapsed !== undefined
            ? _strings(patch.collapsed) : state.collapsed,
        treeScroll: patch.treeScroll !== undefined
            ? patch.treeScroll : state.treeScroll,
    };
    remote = { ...next };
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch { /* 无存储 → 还有后端那条路 ✓ */ }
    // 只有「结构性」变化才推后端（纯滚动不推，避免刷盘 —— 关闭时强制推 ✓）
    const structural = patch.section !== undefined
        || patch.filter !== undefined || patch.key !== undefined
        || patch.collapsed !== undefined;
    if (!force && !structural) return;
    if (!push) return;
    window.clearTimeout(pushTimer);
    pushTimer = window.setTimeout(() => push?.(next), 1000);
}

/** 设置「推后端」的实现（页面构造时调用一次 ✓） */
export function bindPickerBackend(
    onCommand: (cmd: string, payload: unknown) => void,
): void {
    push = (state: PickerState) => {
        try {
            onCommand('set_setting', {
                key: SETTING_KEY, value: JSON.stringify(state),
            });
        } catch { /* ignore */ }
    };
}

/** 把选择器的变化接到状态存储上（section / 收起 / 滚动 / 光标停留 ✓） */
export function bindPickerState(picker: {
    onSectionCallback?: ((section: string) => void) | null;
    onScrollCallback?: ((top: number) => void) | null;
    onFocusCallback?: ((key: string) => void) | null;
    onFilterCallback?: ((kind: 'all' | 'main' | 'sub') => void) | null;
    onGroupsCallback?: ((collapsed: string[]) => void) | null;
    onCloseCallback?: ((state: {
        section: string; scroll: number; treeScroll: number;
    }) => void) | null;
}): void {
    picker.onSectionCallback = (section) => savePickerState({ section });
    picker.onScrollCallback = (top) => savePickerState({ scroll: top });
    picker.onFocusCallback = (key) => savePickerState({ key });
    // ★ 左侧分组收起 / 展开（11-20 新增 ✓）
    picker.onGroupsCallback = (collapsed) => savePickerState({ collapsed });
    // ★ 关闭时把最终滚动位置（左导航 + 指标列表）落盘（11-20 新增 ✓）
    picker.onCloseCallback = (state) => {
        savePickerState({
            section: state.section,
            scroll: state.scroll,
            treeScroll: state.treeScroll,
        }, true);
    };
    const previous = picker.onFilterCallback;
    picker.onFilterCallback = (kind) => {
        savePickerState({ filter: kind });
        previous?.(kind);
    };
}

/**
 * 打开选择器时恢复「上次的位置」✓
 *
 * @param picker 选择器实例（有 `restoreState()`）
 * @param fallbackSection 没存过 section 时用哪个（收藏 / 全部指标）
 */
export function restorePickerState(picker: {
    restoreState: (state: {
        section?: string; filter?: 'all' | 'main' | 'sub';
        key?: string; scroll?: number;
        collapsed?: string[]; treeScroll?: number;
    }) => void;
    open: (section?: string) => void;
    setOverlayFilter: (kind: 'all' | 'main' | 'sub') => void;
}, fallbackSection: string,
   knownSections: Set<string>): void {
    const saved = readPickerState();
    const filter = (saved.filter || 'all') as 'all' | 'main' | 'sub';
    picker.setOverlayFilter(filter);
    const section = saved.section && (knownSections.size === 0
        || knownSections.has(saved.section))
        ? saved.section
        : fallbackSection;
    picker.open(section);
    picker.restoreState({
        section, filter, key: saved.key, scroll: saved.scroll,
        collapsed: saved.collapsed, treeScroll: saved.treeScroll,
    });
    // ★ 打开即播种：第一次打开也要把这次的 section / 筛选存下来 ✓
    savePickerState({ section, filter });
    // 诊断（F12 Console）：一眼看出"存的什么 / 用的什么"✓
    console.info('[picker] 恢复位置', {
        saved, section, filter, known: [...knownSections].slice(0, 8),
    });
}

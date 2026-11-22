// 「指标、衡量标准和策略」选择器：**真跑一遍 DOM**（不是源码字符串断言）
//
// 为什么需要它：收起 / 展开是纯前端交互，源码里"看起来对了"不代表运行时对
// （class 名、事件绑定、重渲染后节点引用…）。这里用一个 60 行的最小 DOM shim
// 把 `IndicatorPicker` 真正实例化，点分组标题、看 section 是否 hidden、
// 看回调收到的 `collapsed`、看 `close()` 交出的滚动位置 ✓
//
// （仓库没装 jsdom：加依赖会拖慢 CI；这个 shim 只实现选择器用到的那几个 API。）
import { beforeAll, describe, expect, it } from 'vitest';

interface ShimEl {
    tagName: string;
    children: ShimEl[];
    style: Record<string, unknown>;
    dataset: Record<string, string>;
    value: string;
    scrollTop: number;
    classList: {
        add: (...names: string[]) => void;
        remove: (...names: string[]) => void;
        toggle: (name: string, on?: boolean) => void;
        contains: (name: string) => boolean;
    };
    className: string;
    textContent: string;
    appendChild: (child: ShimEl) => ShimEl;
    append: (...children: ShimEl[]) => void;
    addEventListener: (type: string, fn: (ev?: unknown) => void) => void;
    dispatch: (type: string) => void;
    querySelectorAll: (selector: string) => ShimEl[];
    querySelector: (selector: string) => ShimEl | null;
    scrollIntoView: () => void;
    focus: () => void;
}

function makeEl(tag = 'div'): ShimEl {
    let text = '';
    const classes = new Set<string>();
    const listeners: Record<string, Array<(ev?: unknown) => void>> = {};
    const el: ShimEl = {
        tagName: String(tag).toUpperCase(),
        children: [],
        style: { setProperty() {}, display: '' } as Record<string, unknown>,
        dataset: {},
        value: '',
        scrollTop: 0,
        classList: {
            add: (...names) => names.forEach((n) => classes.add(n)),
            remove: (...names) => names.forEach((n) => classes.delete(n)),
            toggle: (name, on) => {
                if (on === false) classes.delete(name);
                else classes.add(name);
            },
            contains: (name) => classes.has(name),
        },
        get className() { return [...classes].join(' '); },
        set className(value: string) {
            classes.clear();
            String(value).split(/\s+/).filter(Boolean)
                .forEach((n) => classes.add(n));
        },
        appendChild: (child) => { el.children.push(child); return child; },
        append: (...children) => children.forEach((c) => el.children.push(c)),
        addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
        dispatch: (type) => (listeners[type] || []).forEach((fn) => fn({})),
        querySelectorAll: (selector) => {
            const want = selector.replace(/^\./, '');
            const out: ShimEl[] = [];
            const walk = (node: ShimEl) => node.children.forEach((child) => {
                if (child.classList.contains(want)) out.push(child);
                walk(child);
            });
            walk(el);
            return out;
        },
        querySelector: (selector) => el.querySelectorAll(selector)[0] || null,
        scrollIntoView: () => {},
        focus: () => {},
    } as unknown as ShimEl;
    // ★ `textContent = ''` 在真 DOM 里会**清空子节点**（`_renderTree()` 靠它清树）；
    //   用普通属性会留下旧节点 → 重渲染后 querySelectorAll 数出双份 ✗
    Object.defineProperty(el, 'textContent', {
        get: () => text,
        set: (value: string) => {
            text = String(value);
            el.children.length = 0;
        },
    });
    return el;
}

const GROUPS = [
    { key: 'personal', label: '个人', sections: [
        { key: 'favorites', label: '收藏' },
        { key: 'my_scripts', label: '我的脚本' },
    ] },
    { key: 'builtin', label: '内置指标', sections: [
        { key: 'all', label: '全部指标' },
        { key: 'pta', label: 'PandasTa' },
    ] },
    { key: 'tradingsystem', label: '交易系统', sections: [
        { key: 'ts_trend', label: '趋势指标' },
    ] },
];

const ITEMS = [
    { key: 'a', label: 'A · BtInd', section: 'all' },
    { key: 'b', label: 'B · 交易系统', section: 'ts_trend' },
];

type Picker = {
    element: ShimEl;
    collapsedGroups: string[];
    onGroupsCallback: ((collapsed: string[]) => void) | null;
    onCloseCallback: ((state: {
        section: string; scroll: number; treeScroll: number;
    }) => void) | null;
    restoreState: (state: Record<string, unknown>) => void;
    toggleGroup: (key: string) => void;
    close: () => void;
};

let IndicatorPicker: new (options: Record<string, unknown>) => Picker;

beforeAll(async () => {
    const body = makeEl('body');
    const head = makeEl('head');
    (globalThis as unknown as { document: unknown }).document = {
        createElement: (tag: string) => makeEl(tag),
        head,
        body,
        getElementById: () => null,
        querySelector: () => null,
    };
    (globalThis as unknown as { window: unknown }).window = {
        localStorage: { getItem: () => null, setItem: () => {} },
        setTimeout: (fn: () => void) => setTimeout(fn, 0),
        clearTimeout,
        requestAnimationFrame: (fn: () => void) => setTimeout(fn, 0),
        addEventListener: () => {},
    };
    // 先装 shim 再**动态** import（静态 import 会先执行，拿不到 document ✗）
    const mod = await import('../src/panels/indicator-picker');
    IndicatorPicker = mod.IndicatorPicker as unknown as typeof IndicatorPicker;
});

function picker(): Picker {
    return new IndicatorPicker({ groups: GROUPS, items: ITEMS,
                                 section: 'all' });
}

const headers = (p: Picker) => p.element.querySelectorAll('pylc-ip-group');
const sections = (p: Picker) => p.element.querySelectorAll('pylc-ip-section');
const hiddenLabels = (p: Picker) => sections(p)
    .filter((s) => s.classList.contains('hidden'))
    .map((s) => s.textContent);

describe('左栏分组：渲染顺序 + 收起 / 展开（真跑 DOM）', () => {
    it('顺序是 个人 → 内置指标 → 交易系统，且每组都有 ▾', () => {
        const p = picker();
        const labels = headers(p).map((h) => h.children[1].textContent);
        expect(labels).toEqual(['个人', '内置指标', '交易系统']);
        expect(headers(p).every((h) => h.querySelector('.pylc-ip-chev')))
            .toBe(true);
    });

    it('默认全部展开', () => {
        const p = picker();
        expect(hiddenLabels(p)).toEqual([]);
    });

    it('点「内置指标」→ 只收起它自己的 2 个 section + 上报 collapsed', () => {
        const p = picker();
        const reported: string[][] = [];
        p.onGroupsCallback = (keys) => reported.push([...keys]);
        headers(p)[1].dispatch('click');
        expect(hiddenLabels(p)).toEqual(['全部指标', 'PandasTa']);
        expect(headers(p)[1].classList.contains('collapsed')).toBe(true);
        expect(reported.at(-1)).toEqual(['builtin']);
        expect(p.collapsedGroups).toEqual(['builtin']);
    });

    it('再点一次 → 展开，并上报空数组', () => {
        const p = picker();
        const reported: string[][] = [];
        p.onGroupsCallback = (keys) => reported.push([...keys]);
        p.toggleGroup('builtin');
        p.toggleGroup('builtin');
        expect(hiddenLabels(p)).toEqual([]);
        expect(reported.at(-1)).toEqual([]);
    });

    it('restoreState：恢复收起状态，但当前 section 所在分组自动展开', () => {
        const p = picker();
        p.restoreState({ section: 'pta', filter: 'all',
                         collapsed: ['builtin', 'tradingsystem'] });
        // builtin 里有 pta（当前选中）→ 自动展开；只剩 tradingsystem 收起 ✓
        expect(hiddenLabels(p)).toEqual(['趋势指标']);
        expect(p.collapsedGroups).toEqual(['tradingsystem']);
    });

    it('close() 交出 最终 section + 两处滚动位置', () => {
        const p = picker();
        let closed: Record<string, unknown> | null = null;
        p.onCloseCallback = (state) => { closed = state; };
        p.restoreState({ section: 'ts_trend', scroll: 321, treeScroll: 77 });
        p.close();
        expect(closed).not.toBeNull();
        expect(closed!.section).toBe('ts_trend');
        expect(typeof closed!.scroll).toBe('number');
        expect(typeof closed!.treeScroll).toBe('number');
    });
});

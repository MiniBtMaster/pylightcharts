// 二级子菜单收起（v1.3.9-18）
//
// 用户 2026-11-17 截图（小BUG.png）：「布局 › 已保存的布局」子菜单展开后，
// 鼠标离开子菜单不会收起来；布局多了会一直挡住下面的「布局管理…」等菜单项。
//
// 以前只有**一级行**有 mouseleave，子菜单是挂在 <body> 上的独立元素，
// 离开它没有任何监听 → 永远收不起来 ✗
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { closeMenu, showMenu } from '../src/desk/menu';
import { DomStub, StubElement, installDom } from './dom';

let dom: DomStub;

/** 一级菜单（`body.children[0]`）里文本为 `label` 的行 ✓ */
function row(label: string): StubElement {
    const menu = dom.body.children[0] as StubElement;
    const found = menu.children.find(
        (child) => child.children[0]?.textContent === label);
    if (!found) throw new Error(`菜单里没有「${label}」`);
    return found;
}

/** 当前展开的二级菜单（挂在 body 上、className 含 desk-menu-sub） */
function subs(): StubElement[] {
    return dom.body.children.filter(
        (child) => String(child.className).includes('desk-menu-sub'));
}

const MENU = [
    { label: '单图', run: () => undefined },
    {
        label: '已保存的布局', submenu: [
            { label: 'pp_l_2609_60 左右两图', run: () => undefined },
            { label: 'test1 左右两图', run: () => undefined },
        ],
    },
    { label: '布局管理…', run: () => undefined },
    { label: '导出 / 导入', submenu: [{ label: '导出', run: () => undefined }] },
];

beforeEach(() => {
    vi.useFakeTimers();
    dom = installDom();
    showMenu(10, 10, MENU as never);
});

afterEach(() => {
    closeMenu();
    vi.useRealTimers();
});

describe('二级子菜单收起', () => {
    it('悬停展开子菜单', () => {
        row('已保存的布局').dispatch('mouseenter');
        expect(subs().length).toBe(1);
        expect(subs()[0].children.length).toBe(2);
    });

    it('鼠标离开**子菜单本身** → 收起（本次修的主 BUG ✓）', () => {
        const owner = row('已保存的布局');
        owner.dispatch('mouseenter');           // 展开
        const sub = subs()[0];
        sub.dispatch('mouseenter');             // 进子菜单
        owner.dispatch('mouseleave');           // 离开一级行（鼠标在子菜单里）
        vi.advanceTimersByTime(300);
        expect(subs().length).toBe(1);          // 还在 ✓
        sub.dispatch('mouseleave');             // 再离开子菜单去空白处
        vi.advanceTimersByTime(300);
        expect(subs().length).toBe(0);          // 这次要收 ✓
    });

    it('从行直接移到子菜单（中途不停留）→ 不会被误收', () => {
        const owner = row('已保存的布局');
        owner.dispatch('mouseenter');
        const sub = subs()[0];
        sub.dispatch('mouseenter');       // 先进子菜单
        owner.dispatch('mouseleave');     // 再离开行
        vi.advanceTimersByTime(300);
        expect(subs().length).toBe(1);    // 子菜单还在（鼠标在里面 ✓）
    });

    it('移到没有子菜单的兄弟行 → 立刻收起', () => {
        row('已保存的布局').dispatch('mouseenter');
        expect(subs().length).toBe(1);
        row('布局管理…').dispatch('mouseenter');
        expect(subs().length).toBe(0);
    });

    it('移到另一个带子菜单的行 → 只留新的那个', () => {
        row('已保存的布局').dispatch('mouseenter');
        row('导出 / 导入').dispatch('mouseenter');
        const open = subs();
        expect(open.length).toBe(1);
        expect(open[0].children.length).toBe(1);   // 导出 / 导入 的子菜单
    });

    it('点同一行两次 → 展开再收起', () => {
        const owner = row('已保存的布局');
        owner.click();
        expect(subs().length).toBe(1);
        owner.click();
        expect(subs().length).toBe(0);
    });

    it('鼠标进子菜单里的项 → 不会把父级子菜单收掉（不闪烁 ✓）', () => {
        const owner = row('已保存的布局');
        owner.dispatch('mouseenter');
        const sub = subs()[0];
        sub.dispatch('mouseenter');
        owner.dispatch('mouseleave');
        // 在子菜单里逐项移动：以前每一项的 mouseenter 都会 closeSubsExcept(null)
        // → 收掉父级子菜单 → 又立刻重新展开 → 疯狂闪烁 ✗
        for (const child of sub.children) {
            child.dispatch('mouseenter');
            vi.advanceTimersByTime(200);
            expect(subs().length).toBe(1);
        }
        // 来回移动也稳定
        for (let i = 0; i < 5; i += 1) {
            sub.children[0].dispatch('mouseenter');
            sub.children[1]?.dispatch('mouseenter');
            vi.advanceTimersByTime(200);
            expect(subs().length).toBe(1);
        }
    });

    it('子菜单里的行不会顺手关掉别的子菜单（只有一级行才管）', () => {
        row('已保存的布局').dispatch('mouseenter');
        expect(subs().length).toBe(1);
        const sub = subs()[0];
        // 直接点一个子菜单项（会 closeMenu → 正常执行）
        sub.children[0].click();
        expect(subs().length).toBe(0);
        expect(dom.body.children.includes(sub)).toBe(false);
    });

    it('closeMenu 会把子菜单一起清掉', () => {
        row('已保存的布局').dispatch('mouseenter');
        closeMenu();
        expect(subs().length).toBe(0);
    });
});

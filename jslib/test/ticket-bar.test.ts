/**
 * 图上「买卖盘」条（`ticket-bar.ts`）：每格一条 + 行尾 👁 ✓
 *
 * 用户 2026-11-03：买卖盘以前是整页一个节点、只挂在格 1 → 多布局看不到、
 * 本地图表其它格调不出来 ✗。现在每格一条，眼睛只切**当前格**。
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { TicketBar } from '../src/desk/ticket-bar';
import { DomStub, StubElement, installDom } from './dom';

let dom: DomStub;

beforeEach(() => {
    dom = installDom();
});

function text(node: StubElement | null | undefined): string {
    return String((node as unknown as { textContent?: string })?.textContent
        || '');
}

describe('TicketBar', () => {
    it('renders buy / spread / sell (no eye anymore)', () => {
        const bar = new TicketBar({ decimals: 1 });
        // 2026-11-04：用户要求去掉行尾 👁 → 显隐统一由工具栏按钮控制 ✓
        expect(bar.element.querySelector('.desk-ticket-eye')).toBeFalsy();
        expect(bar.element.querySelectorAll('.desk-ticket-side').length)
            .toBe(2);
        expect(bar.element.querySelector('.desk-ticket-spread')).toBeTruthy();
        // 默认显示（页面按偏好决定传不传 visible）
        expect(bar.isVisible).toBe(true);
    });

    it('fills bid / ask from the book and computes the spread', () => {
        const bar = new TicketBar({ decimals: 2 });
        bar.setBook({ bids: [{ price: 3500.5 }], asks: [{ price: 3501.5 }] });
        const sides = bar.element.querySelectorAll('.desk-ticket-side');
        const buy = sides[0].querySelector('.desk-ticket-price');
        const sell = sides[1].querySelector('.desk-ticket-price');
        expect(text(buy)).toBe('3501.50');          // 买入 = 卖一 ✓
        expect(text(sell)).toBe('3500.50');         // 卖出 = 买一 ✓
        expect(text(bar.element.querySelector('.desk-ticket-spread')))
            .toBe('1.00');
    });

    it('turns the position label into 平仓', () => {
        const bar = new TicketBar({ decimals: 1 });
        bar.setBook({ bids: [{ price: 10 }], asks: [{ price: 11 }] });
        const labels = () => bar.element
            .querySelectorAll('.desk-ticket-side')
            .map((node) => text(node.querySelector('.desk-ticket-label')));
        expect(labels()).toEqual(['买入', '卖出']);
        bar.setNet(3);          // 多仓 → 右侧平仓 ✓
        expect(labels()).toEqual(['买入', '平仓']);
        bar.setNet(-2);         // 空仓 → 左侧平仓 ✓
        expect(labels()).toEqual(['平仓', '卖出']);
    });

    it('shows / hides by the page-level switch', () => {
        const bar = new TicketBar();
        bar.setVisible(false);
        expect(bar.isVisible).toBe(false);
        expect(bar.element.classList.contains('off')).toBe(true);
        bar.setVisible(true);
        expect(bar.isVisible).toBe(true);
        expect(bar.element.classList.contains('off')).toBe(false);
    });

    it('clicks on a hidden bar do not place orders', () => {
        const orders: string[] = [];
        const bar = new TicketBar({ onOrder: (side) => orders.push(side) });
        bar.setVisible(false);
        (bar as unknown as { _click: (side: string) => void })._click('buy');
        expect(orders).toEqual([]);
        bar.setVisible(true);
        (bar as unknown as { _click: (side: string) => void })._click('buy');
        (bar as unknown as { _click: (side: string) => void })._click('sell');
        expect(orders).toEqual(['buy', 'sell']);
    });
});

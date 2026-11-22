/**
 * 「指标和策略」页：添加分组后**立刻切到该分组** ✓
 *
 * 用户 2026-11-02 反馈：下拉框选「＋ 添加指标和策略」并挑好文件夹后，
 * 分组是加进去了，但列表还停在原来的分组 → 看起来“没反应”。
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { TvPage } from '../src/desk/tv-page';
import { DomStub, installDom } from './dom';

let dom: DomStub;

beforeEach(() => {
    dom = installDom();
});

function makePage(): { page: TvPage; calls: Array<[string, Record<string, unknown>]> } {
    const calls: Array<[string, Record<string, unknown>]> = [];
    const page = new TvPage({
        id: 'tv',
        theme: 'dark',
        onCommand: (cmd, payload) => calls.push([cmd, payload || {}]),
        onToast: () => undefined,
        onApply: () => undefined,
        onOpen: () => undefined,
        charts: () => [],
        onApplyToChart: () => undefined,
    });
    return { page, calls };
}

const GROUPS = [
    { key: 'TradingView', label: 'TradingView', user: false, count: 114 },
    { key: '/repo/style_zoo', label: 'style_zoo', user: true, count: 9 },
];

describe('tv page group add', () => {
    it('jumps to the folder that was just added', () => {
        const { page, calls } = makePage();
        calls.length = 0;
        page.setGroups({ ok: true, path: '/repo/style_zoo', groups: GROUPS });
        const list = calls.filter(([cmd]) => cmd === 'tv_list').pop();
        expect(list, 'tv_list called').toBeTruthy();
        expect(list![1].group).toBe('/repo/style_zoo');
        expect(list![1].page).toBe(1);
    });

    it('keeps the current group on unrelated updates', () => {
        const { page, calls } = makePage();
        page.setGroups({ ok: true, path: '/repo/style_zoo', groups: GROUPS });
        calls.length = 0;
        page.setGroups({ ok: true, path: '', groups: GROUPS });
        const list = calls.filter(([cmd]) => cmd === 'tv_list').pop();
        expect(list![1].group).toBe('/repo/style_zoo');     // 不被重置 ✓
    });

    it('falls back to all groups when the current one disappears', () => {
        const { page, calls } = makePage();
        page.setGroups({ ok: true, path: '/repo/style_zoo', groups: GROUPS });
        calls.length = 0;
        page.setGroups({ ok: true, path: '', groups: [GROUPS[0]] });
        const list = calls.filter(([cmd]) => cmd === 'tv_list').pop();
        expect(list![1].group).toBe('');
    });
});

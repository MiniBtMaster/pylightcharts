// 布局管理悬停卡片：**合约 + 指标（每个指标一段）+ 策略**（v1.3.9-17）
//
// 用户 2026-11-17：
//   ① 卡片里指标全按「线条」列（pta_adx:adxx / adxr / dmp / dmn 各一条）→
//      框式指标（IndFrame）要合并成 `pta_adx(14, 14, 100, rma, 1, 0)`；
//      单线指标（IndSeries）保持 `pta_sma:sma(10, true, 0)` ✓
//   ② 每个指标**各占一段**，合约里有哪些指标、参数多少一眼看清。
import { describe, expect, it, vi } from 'vitest';

import { layoutTipRows } from '../src/desk/layout-dialogs';

const text = (rows: ReturnType<typeof layoutTipRows>): string =>
    rows.map((row) => (row.text ? row.text : `[${row.title}]`)).join('\n');

describe('布局悬停卡片', () => {
    it('用后端的简化清单：一个指标一段，框式指标合并', () => {
        const rows = layoutTipRows({
            key: 'k1', name: 'pp_l_2609_60', cells: [
                { symbol: 'pp_2609_60',
                  tipIndicators: [
                      'pta_sma:sma(10, true, 0)',
                      'pta_adx(14, 14, 100, rma, 1, 0)',
                  ],
                  strategy: { name: 'KalmanFilterStrategy', path: '/x/y.py' } },
            ],
        } as never);
        expect(text(rows)).toBe([
            '[#1 pp_2609_60]', '[指标]',
            'pta_sma:sma(10, true, 0)', 'pta_adx(14, 14, 100, rma, 1, 0)',
            '[策略]', 'KalmanFilterStrategy',
        ].join('\n'));
        // 每项都是 kind=item（一段一条 ✓）
        expect(rows.filter((row) => row.kind === 'item').length).toBe(3);
    });

    it('后端没给 tipIndicators（旧数据）→ 退回按线条列，仍是一段一条', () => {
        const rows = layoutTipRows({
            key: 'k2', name: '布局1',
            cells: [{ symbol: 'DCE.l2701',
                      indicators: [
                          { key: 'pta_sma:sma', params: { length: 10 } },
                          { key: 'pta_adx:adxx', params: {} },
                      ] }],
        } as never);
        const items = rows.filter((row) => row.kind === 'item')
            .map((row) => row.text);
        expect(items).toEqual(['pta_sma:sma(10)', 'pta_adx:adxx']);
    });

    it('没有指标 / 策略的格只显示合约（不出现空行 ✓）', () => {
        const rows = layoutTipRows({
            key: 'k3', name: '单图', cells: [
                { symbol: 'SHFE.ag2612', indicators: [],
                  strategy: { name: '', path: '' } },
            ],
        } as never);
        expect(rows.length).toBe(1);
        expect(rows[0].title).toBe('#1 SHFE.ag2612');
    });

    it('布局管理的搜索框高度是普通输入框的 2 倍（30 → 60 ✓）', async () => {
        const source = await import('node:fs').then((fs) =>
            fs.readFileSync('src/desk/layout-dialogs.ts', 'utf8'));
        expect(source).toContain('.desk-lg-search{height:60px');
        expect(source).toContain(
            "this.search.className = 'desk-lg-input desk-lg-search'");
    });

    it('卡片配色不再写死：CSS 用 --desk-* 变量（切主题立刻生效 ✓）', async () => {
        // 老的 PALS + element.style.setProperty('--lg-*') 只在第一次建窗口时
        // 跑一次 → 之后切主题布局管理窗口不变色（用户实测 ✗）
        const source = await import('node:fs').then((fs) =>
            fs.readFileSync('src/desk/layout-dialogs.ts', 'utf8'));
        expect(source).not.toContain("bg: '#161a20'");        // 已删 PALS
        expect(source).toContain("element.style.removeProperty(`--lg-${key}`)");
        expect(source).toContain('--lg-bg: var(--desk-panel');
        expect(source).toContain('--lg-accent: var(--desk-accent');
    });
});

// 每个编辑器都要拿到 LSP 地址（v1.3.9-32）
//
// 用户实测 2026-11-18：LSP 只对**第一个打开的编辑器**（启动时那个本地图表）
// 生效，实时图表页的编辑器全部「LSP 未启用」+ 红点闪烁。
//
// 根因：`local-chart-page.ts` 把 `lsp` 透传给了 `EditorPanel`，
// 而 `chart-page.ts`（实时图表）**漏了** —— 页面上根本没有 LSP 地址 ✗
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const chartPage = readFileSync('src/desk/chart-page.ts', 'utf8');
const localPage = readFileSync('src/desk/local-chart-page.ts', 'utf8');
const app = readFileSync('src/desk/app.ts', 'utf8');

describe('编辑器 LSP 接线', () => {
    it('实时图表页：ChartPageOptions 有 lsp，EditorPanel 也拿到', () => {
        expect(chartPage).toContain('lsp?: () => {');
        expect(chartPage).toContain('lsp: () => this.options.lsp?.(),');
    });

    it('本地图表页同样透传（原本就有 ✓）', () => {
        expect(localPage).toContain('lsp: () => this.options.lsp?.(),');
    });

    it('app 创建实时图表页时把 lspInfo 传进去', () => {
        const at = app.indexOf('new ChartPage({');
        expect(at).toBeGreaterThan(0);
        const block = app.slice(at, at + 1200);
        expect(block).toContain('lsp: () => this.lspInfo || undefined,');
    });

    it('三种页面的编辑器都能补连（activate 时 refreshLsp）', () => {
        expect(app).toContain('panel?.refreshLsp?.(true);');
        expect(app).toContain('refreshLsp?: (force?: boolean) => void;');
    });
});

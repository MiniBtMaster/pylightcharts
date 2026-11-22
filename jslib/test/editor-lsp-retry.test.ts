// LSP 晚到也要补连（v1.3.9-26）
//
// 用户实测 2026-11-18：编辑器状态栏一直「LSP 未启用」，补全 / 悬停全都没了。
// 根因：编辑器是在后端 `lsp` 补丁到达**之前**建的 → `spec.lsp` 为空，
// 而且之后不会自己重连 ✗
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const editor = readFileSync('src/desk/code-editor.ts', 'utf8');
const panel = readFileSync('src/desk/editor-panel.ts', 'utf8');
const app = readFileSync('src/desk/app.ts', 'utf8');

describe('编辑器 LSP 补连', () => {
    it('CodeEditor 记得自己有没有 LSP，并能补连', () => {
        expect(editor).toContain('get hasLsp(): boolean {');
        expect(editor).toContain('attachLsp(lsp: { url: string; root: string }, force = false): boolean {');
        expect(editor).toContain('this.options.lsp = lsp;');
    });

    it('面板：refreshLsp 给已打开的文件补连', () => {
        expect(panel).toContain('refreshLsp(force = false): void {');
        expect(panel).toContain('if (tab.editor.hasLsp && !force');
        expect(panel).toContain('tab.editor.attachLsp(info, force || !tab.editor.hasLsp)');
    });

    it('打开文件时 LSP 还没就绪 → 退避重试', () => {
        expect(panel).toContain('private _scheduleLspRetry(): void {');
        expect(panel).toContain('const delays = [600, 1600, 3500, 7000];');
        expect(panel).toContain('if (!editor.hasLsp) this._scheduleLspRetry();');
    });

    it('状态栏「重启 LSP」圆点：未启用红点闪烁可点、已启用绿点不可点', () => {
        const css = readFileSync('src/desk/desk.css', 'utf8');
        // 圆点、无文本、tooltip = 重启 LSP 服务 ✓
        expect(panel).toContain("restart.className = 'desk-editor-lsp-dot';");
        expect(panel).toContain("restart.textContent = '';");
        expect(panel).toContain("restart.title = '重启 LSP 服务';");
        expect(panel).toContain('restart.disabled = false;');
        // 未启用 → off（红 + 闪）；已启用 → ok（绿 + 禁用）✓
        expect(panel).toContain('private _syncLspRestart(): void {');
        expect(panel).toContain("dot.dataset.level = ready ? 'ok' : 'off';");
        expect(panel).toContain('dot.disabled = ready;');
        expect(css).toContain('.desk-editor-lsp-dot {');
        expect(css).toContain("animation: desk-lsp-blink 1.1s ease-in-out infinite;");
        expect(css).toContain('.desk-editor-lsp-dot[data-level="ok"] {');
        expect(css).toContain('@keyframes desk-lsp-blink {');
        // 点击 → 后端真重启 + 补连 ✓
        expect(panel).toContain("this.options.onCommand('lsp_start', { restart: true });");
        expect(panel).toContain('this._syncLspRestart();');
    });

    it('多开编辑器：每个新页面 / 每个文件都补连（不是只有第一个 ✓）', () => {
        // 退避重试以前被 `if (this.lspRetried)` 挡死（`[]` 也是 truthy ✗）
        expect(panel).toContain('if (this.lspRetried.length) return;');
        // 切到某一页（重新打开实时图表 / 本地图表）→ 该页编辑器补连 ✓
        expect(app).toContain('panel?.refreshLsp?.(true);');
        // 圆点按**真实连接**（`onLspStatus('ok')`）而不是"有端口" ✓
        expect(panel).toContain('private lspConnected = false;');
        expect(panel).toContain('const ready = this.lspConnected;');
        expect(panel).toContain("this.lspConnected = (level || 'off') === 'ok';");
        // 重启 6.5s 还没连上 → 明说失败，可以再点 ✓
        expect(panel).toContain("'LSP 连接超时（点红点重试）'");
    });

    it('LSP 地址变了（服务重启）→ 强制重连', () => {
        expect(editor).toContain('attachLsp(lsp: { url: string; root: string }, force = false): boolean {');
        expect(panel).toContain('refreshLsp(force = false): void {');
        expect(app).toContain('const force = !!prevUrl && prevUrl !== this.lspInfo.url;');
        expect(app).toContain('panel.refreshLsp?.(force);');
    });

    it('后端 lsp 补丁到达 → 通知所有编辑器面板', () => {
        expect(app).toContain('refreshLsp?: (force?: boolean) => void;');
        expect(app).toContain('panel.refreshLsp?.(force);');
    });
});

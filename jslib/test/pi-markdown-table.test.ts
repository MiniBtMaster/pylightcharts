/**
 * v1.3.7-105：PI 对话 / 悬浮窗的 Markdown 表格渲染（以前只显示一堆 `|` ✗）
 */
import { describe, expect, it } from 'vitest';
import { markdownToHtml, renderPiTable, splitTableRow,
    tableAligns, isTableDivider } from '../src/desk/pi-chat';

const TABLE = [
    '结论如下：',
    '',
    '| 指标 | 数值 | 判断 |',
    '| --- | ---: | :---: |',
    '| RSI(14) | 71.2 | 超买 |',
    '| CCI(20) | -120.5 | 弱势 |',
    '',
    '以上仅供参考。',
].join('\n');

describe('PI markdown 表格', () => {
    it('识别分隔行与对齐', () => {
        expect(isTableDivider('| --- | ---: | :---: |')).toBe(true);
        expect(isTableDivider('| 1 | 2 |')).toBe(false);
        expect(splitTableRow('| a | b |')).toEqual(['a', 'b']);
        // 纯 `---` 不给对齐（CSS 默认左对齐 ✓），`---:` 右、`:---:` 居中
        expect(tableAligns('| --- | ---: | :---: |'))
            .toEqual(['', 'right', 'center']);
    });

    it('渲染出真正的 <table>（不是一堆竖线）', () => {
        const html = markdownToHtml(TABLE);
        expect(html).toContain('<table class="desk-pi-table">');
        expect(html).toContain('<th style="text-align:right">数值</th>');
        expect(html).toContain('<th style="text-align:center">判断</th>');
        expect(html).toContain('<td>RSI(14)</td>');
        expect(html).toContain('<td style="text-align:right">71.2</td>');
        expect(html).toContain('结论如下');
        expect(html).toContain('以上仅供参考');
        // 单元格内容里不应再出现 | 分隔符
        expect(html).not.toContain('| RSI');
    });

    it('单元格里支持粗体 / 行内代码（且不二次转义）', () => {
        const html = markdownToHtml([
            '| 名称 | 说明 |',
            '| --- | --- |',
            '| **RSI** | `超买` 时注意 |',
        ].join('\n'));
        expect(html).toContain('<b>RSI</b>');
        expect(html).toContain('<code>超买</code>');
        expect(html).not.toContain('&lt;b&gt;');
    });

    it('转义 HTML（XSS 安全）', () => {
        const html = renderPiTable(['a'], [['<img src=x>']]);
        expect(html).toContain('&lt;img src=x&gt;');
        expect(html).not.toContain('<img src=x>');
    });

    it('列数不齐时补空单元格', () => {
        const html = renderPiTable(['a', 'b', 'c'], [['1']]);
        expect((html.match(/<td/g) || []).length).toBe(3);
    });

    it('代码块仍带「复制」按钮', () => {
        const html = markdownToHtml('```python\nprint(1)\n```');
        expect(html).toContain('data-pi-copy="1"');
        expect(html).toContain('<code>');
    });
});

describe('PI 悬浮窗 / 对话页接线', () => {
    it('悬浮窗 assistant 气泡用 markdownToHtml（不再 textContent）', async () => {
        const fs = await import('node:fs');
        const url = await import('node:url');
        const path = url.fileURLToPath(new URL('../src/desk/pi-float.ts',
            import.meta.url));
        const src = fs.readFileSync(path, 'utf8');
        expect(src).toContain("from './pi-chat'");
        expect(src).toContain('markdownToHtml(');
        expect(src).toContain("body.classList.add('md')");
        expect(src).toContain('body.innerHTML = markup');
    });

    it('对话页 PiChat 的 markdown 走同一个函数', async () => {
        const fs = await import('node:fs');
        const url = await import('node:url');
        const path = url.fileURLToPath(new URL('../src/desk/pi-chat.ts',
            import.meta.url));
        const src = fs.readFileSync(path, 'utf8');
        expect(src).toContain('private markdown(source: string): string {');
        expect(src).toContain('return markdownToHtml(source);');
    });
});

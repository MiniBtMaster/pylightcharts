// 换合约后账户切换失灵（v1.3.9-37）
//
// 用户实测 2026-11-18：初始化实时图表时可以自由切换实盘 / 快期模拟；
// **换合约之后**就切不动了（按钮闪一下又弹回）。
//
// 根因：`ChartPage.setSymbol()` 只改了 `options.symbol`，没改 `pageId` /
// `dock.pageId` → 切账户命令还发 `page='chart:旧合约'`，后端写进一个
// 已经不用的页；每秒补丁读 `chart:新合约#0`（旧账户）→ 顶回 ✗
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const chartPage = readFileSync('src/desk/chart-page.ts', 'utf8');

describe('ChartPage 换合约同步 pageId', () => {
    it('setSymbol 里更新 options.pageId 和 dock.pageId', () => {
        const at = chartPage.indexOf('setSymbol(symbol: string');
        expect(at).toBeGreaterThan(0);
        const body = chartPage.slice(at, at + 2000);
        // ★ 2026-11-20：换合约要**保留 `~N` 后缀**（同合约多页不能撞 id ✗）
        // 用双引号包外层，避免和内层的单引号打架 ✓
        expect(body).toContain("this.options.pageId = `chart:${symbol}${seq ? seq[0] : ''}`;");
        expect(body).toContain('if (this.dock) this.dock.pageId = this.options.pageId;');
    });
});

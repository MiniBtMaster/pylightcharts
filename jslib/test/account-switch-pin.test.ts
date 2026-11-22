// 切换账户后前端要「钉住」用户的选择（v1.3.9-29）
//
// 用户实测 2026-11-18：交易账户页 / 首页账户概览切到「TqAccount」都失败 ——
// 后端其实已经切了（日志「交易账户 → TqAccount」），但每秒的账户补丁还带着
// 旧 key，下拉框 / 账户卡被顶回「快期模拟」→ 看着就是没切成功 ✗
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const dock = readFileSync('src/desk/account-dock.ts', 'utf8');
const home = readFileSync('src/desk/home-page.ts', 'utf8');

describe('账户切换', () => {
    it('面板下拉框：切换后先钉住，5 秒内不被旧补丁顶回', () => {
        expect(dock).toContain('private pendingKey = ');
        expect(dock).toContain('private pendingAt = 0;');
        expect(dock).toContain('this.pendingKey = key;');
        expect(dock).toContain('Date.now() - this.pendingAt > 5000');
        expect(dock).toContain('active = this.pendingKey;');
        // 切完顺带让后端回一次这一页的账户目录（active 对齐 ✓）
        expect(dock).toContain("this.send('account_kind', {");
    });

    it('首页账户卡：同样钉住 + 标签跟着选择走', () => {
        expect(home).toContain('private _activeKey(): string {');
        expect(home).toContain('this.pendingKey = String(choice.key || \'\');');
        expect(home).toContain("this.options.onCommand('home_account_kind',");
        expect(home).toContain('const chosen = choices.find((item) => item.key === activeKey);');
    });
});

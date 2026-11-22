// 用户主动切换账户推来的补丁必须**一定能落到面板上**（v1.3.9-36）
//
// 用户实测 2026-11-18：开图时切换正常；切到某个合约（有挂单 / 多格）后
// 切换账户"完全没反应"，只有下拉框闪一下。
//
// 根因：`account` / `account_kind` 补丁按 `cell` 过滤 —— 后端推的 cell
// （焦点格）和前端 `activeCellIndex` 不一致时整包被丢弃 ✗
// 现在用户主动切换的包带 `force: true`，前端不看 cell 直接应用 ✓
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';

const app = readFileSync('src/desk/app.ts', 'utf8');
const backend = readFileSync('../minibt/desk/app.py', 'utf8');

describe('账户补丁 force', () => {
    it('后端：用户切换推的 account / state / kind 都带 force', () => {
        // 只看 `set_account_kind` 这个函数体（到下一个同级 `def ` 为止）
        const at = backend.indexOf('def set_account_kind(');
        expect(at).toBeGreaterThan(0);
        const rest = backend.slice(at + 20);
        const end = rest.indexOf(String.fromCharCode(10) + '    def _');
        const body = end > 0 ? rest.slice(0, end) : rest;
        expect(body).toContain("account['force'] = True");
        expect(body).toContain("state['force'] = True");
        expect(body).toContain("kind['force'] = True");
    });

    it('前端：force 的 account 包不看 cell', () => {
        expect(app).toContain("const forced = !!(patch as { force?: boolean }).force;");
        expect(app).toContain('if (!forced && typeof patchCell === \'number\'');
    });

    it('前端：force 的 account_kind 包也不看 cell', () => {
        expect(app).toContain("if (!(patch as { force?: boolean }).force");
    });
});

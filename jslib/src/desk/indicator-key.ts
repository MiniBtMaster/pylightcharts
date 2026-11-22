/**
 * 指标线条 key 的**归一化 + 去重**（回放反复切换时防止图例重复 ✓）
 *
 * 同一个指标在不同链路上会拿到**两种口径**的 key：
 *
 * * 回放 / 布局：`tv:AdaptiveTrendTrail:trend`（目录 key + 线条名）
 * * 实时推送：`AdaptiveTrendTrail.trend`（图例 label 形态）
 *
 * 两套都进 `items` → 图例就出现两行同名指标（用户实测 2026-11-17 ✗）。
 * 这里把「来源前缀 + 标点」抹平后作为家族名，同家族只留**最后一份**
 * （最后一份带最新的数据 ✓），顺序按首次出现的位置（图例不会跳来跳去 ✓）。
 */

/** `tv:AdaptiveTrendTrail:trend` → `adaptivetrendtrailtrend` ✓ */
export function normalizeIndicatorKey(key: string): string {
    // ⚠ 不转小写：内置指标是 `MA20` / `MACD_DIF`，改大小写会变成另一个身份
    //   （样式表 / 显隐集合 / 图例行都按 key 存 ✗）
    let text = String(key || '').trim();
    // 来源前缀（目录 / 个人 / 策略线）不参与比较
    for (const prefix of ['tv:', 'pi:', 'st:', 'editor:']) {
        if (text.startsWith(prefix)) {
            text = text.slice(prefix.length);
            break;
        }
    }
    // `:` `.` `_` `-` 空格 都抹掉：`AdaptiveTrendTrail.trend` == `adaptivetrendtrailtrend`
    return text.replace(/[^A-Za-z0-9\u4e00-\u9fa5]/g, '');
}

/**
 * 同一指标只留一份（后面的覆盖前面的，位置保留首次出现处 ✓）
 *
 * ⚠ 只对**同家族不同口径**生效（见 `normalizeIndicatorKey`），
 * 框式指标的多条线（`pta_adx:adxx` / `pta_adx:adxr`）家族名不同，不会被合并 ✓
 */
/** 哪个 key 更「正式」：带来源冒号的（`tv:X:line`）比点号形态（`X.line`）优先 ✓
 *
 *  ★ 必须**确定**：同一批数据里两种口径都在时，每一拍都要选同一个 key，
 *  否则图例 / 箭头载体会被反复重建（用户实测：回放进出几次就多几组标签 ✗）。
 */
function keyScore(key: string): number {
    return key.includes(':') ? 2 : 1;
}

export function dedupeIndicatorItems<T extends { key?: unknown }>(
    items: readonly T[] | null | undefined,
): T[] {
    const out: T[] = [];
    const slots = new Map<string, number>();
    const canonical = new Map<string, string>();
    for (const item of items || []) {
        if (!item) continue;
        const key = String((item as { key?: unknown }).key || '');
        if (!key) continue;
        const family = normalizeIndicatorKey(key);
        if (!family) continue;
        const at = slots.get(family);
        const best = canonical.get(family);
        if (at === undefined) {
            slots.set(family, out.length);
            canonical.set(family, key);
            out.push(item);
            continue;
        }
        const chosen = best && keyScore(best) >= keyScore(key) ? best : key;
        canonical.set(family, chosen);
        // 数据用最新一份，但 key 统一成**确定的**那个口径 ✓
        out[at] = chosen === key
            ? item
            : ({ ...(item as object), key: chosen } as T);
    }
    return out;
}

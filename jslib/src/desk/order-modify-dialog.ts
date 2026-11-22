/**
 * 「修改当前委托单」弹窗（快期同款 ✓ 2026-11-05）
 *
 * 交易所没有 modify 指令 —— 改单 = **撤掉旧委托 + 按新价 / 新手数重新委托**
 * （方向和开平沿用原委托，由后端 `trading.modify_order()` 处理 ✓）。
 *
 * 界面：一份小表单
 *
 * ```
 * 修改委托单
 * 合约   SHFE.ag2612            （只读）
 * 买卖   买平                   （只读）
 * 手数   [ 2 ]                  （默认=原委托手数）
 * 价格   [ 12,708 ]             （默认=原委托价格，样式同交易页）
 *            [取消]  [提交]
 * ```
 */

export interface OrderModifyOptions {
    /** 合约（只读展示） */
    symbol: string;
    /** 买卖 + 开平（只读展示，如「买平」） */
    sideLabel?: string;
    /** 原委托手数（默认值） */
    volume: number;
    /** 原委托价格（默认值） */
    price: number | null;
    /** 价格小数位（和表格一致 ✓） */
    decimals?: number;
    /** 价格步进（合约最小变动价位 ✓） */
    step?: number;
    /** 提交 */
    onSave: (volume: number, price: number) => void;
}

/** 打开改单弹窗（自带遮罩，Esc / 点遮罩关闭 ✓） */
export function openOrderModifyDialog(options: OrderModifyOptions): void {
    const decimals = Math.max(0, Math.min(6,
        Math.round(Number(options.decimals ?? 2) || 0)));
    const overlay = document.createElement('div');
    overlay.className = 'desk-modal-overlay';
    const box = document.createElement('div');
    box.className = 'desk-modal desk-modify';

    const title = document.createElement('div');
    title.className = 'desk-modal-title';
    title.textContent = '修改委托单';

    const makeRow = (label: string, control: HTMLElement) => {
        const row = document.createElement('div');
        row.className = 'desk-local-ticket-row';
        const key = document.createElement('span');
        key.className = 'k';
        key.textContent = label;
        row.append(key, control);
        return row;
    };
    const readOnly = (text: string) => {
        const node = document.createElement('div');
        node.className = 'desk-modify-value';
        node.textContent = text;
        return node;
    };
    const symbolRow = makeRow('合约', readOnly(options.symbol || '--'));
    const sideRow = makeRow('买卖', readOnly(options.sideLabel || '--'));

    const qty = document.createElement('input');
    qty.type = 'number';
    qty.min = '1';
    qty.step = '1';
    qty.value = String(Math.max(1, Math.round(Number(options.volume) || 1)));
    const qtyRow = makeRow('手数', qty);

    const price = document.createElement('input');
    price.type = 'number';
    price.min = '0';
    const step = Number(options.step);
    price.step = Number.isFinite(step) && step > 0
        ? String(step) : String(Math.pow(10, -decimals));
    price.value = options.price && Number(options.price) > 0
        ? String(options.price) : '';
    price.placeholder = '留空 = 对手价';
    const priceRow = makeRow('价格', price);

    const foot = document.createElement('div');
    foot.className = 'desk-modal-foot';
    const cancel = document.createElement('button');
    cancel.className = 'desk-book-btn plain';
    cancel.textContent = '取消';
    const submit = document.createElement('button');
    submit.className = 'desk-book-btn flat';
    submit.textContent = '提交';
    foot.append(cancel, submit);

    const tip = document.createElement('div');
    tip.className = 'desk-modal-tip';
    tip.textContent = '提交 = 撤掉原委托，再按上面价格 / 手数重新委托';

    box.append(title, symbolRow, sideRow, qtyRow, priceRow, foot, tip);
    overlay.appendChild(box);

    const close = () => {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
    };
    function onKey(event: KeyboardEvent) {
        if (event.key === 'Escape') close();
        if (event.key === 'Enter') submit.click();
    }
    cancel.addEventListener('click', close);
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) close();
    });
    document.addEventListener('keydown', onKey);
    submit.addEventListener('click', () => {
        const volume = Math.round(Number(qty.value));
        if (!Number.isFinite(volume) || volume <= 0) {
            qty.classList.add('bad');
            qty.focus();
            return;
        }
        const value = Number(price.value);
        const limit = Number.isFinite(value) && value > 0 ? value : 0;
        options.onSave(volume, limit);
        close();
    });

    document.body.appendChild(overlay);
    qty.focus();
    qty.select();
}

/**
 * 交易控件（本地模拟 / 天勤模拟 / 实盘共用 ✓）
 *
 * 2026-11-05 按**快期交易页**重做：一行**四个按钮**，按钮随仓位状态变 ✓
 *
 * | 仓位 | 四个按钮 |
 * | --- | --- |
 * | 多仓 | 加多 · 买平 · 平多X · 锁仓 |
 * | 空仓 | 加空 · 卖平 · 平空X · 锁仓 |
 * | 无仓 | 买开 · 卖开 · 买平 · 卖平（后两个禁用） |
 * | 锁仓 | 加多 · 加空 · 平空X · 平多X |
 *
 * - `X` 跟手数框联动，但夹在 `1..持仓` 之间（持仓 2 时填 3 → 仍显示「平多2」）；
 * - 价格留空 = **对手价**（买→卖一 / 卖→买一），由后端解析 ✓；
 * - 一律走 `TqApi.insert_order`（真实委托，能在图上画挂单 / 平仓线 ✓）。
 */
export interface ReplayTicketOptions {
    title?: string;
    /** 当前交易标的（显示在标题行 ✓） */
    symbol?: string;
    /** 是否显示 🔍（本地模拟 / 天勤都开 ✓） */
    searchable?: boolean;
    /** 点 🔍 → 由宿主打开合约搜索（切换**交易标的** ✓） */
    onSearch?: () => void;
    /** 锁定：锁定后不能搜索 / 不跟随图表点击 ✓ */
    locked?: boolean;
    onLockChange?: (locked: boolean) => void;
    /** 点四个按钮之一（方向 + 开平 + 实际手数，价格取输入框）✓ */
    onOrder: (order: TicketOrder) => void;
    /** 点击 主价平仓 / 反手 / 撤单（按输入价的「平仓」走 `onOrder(…, true)`） */
    onAction: (action: 'close_main' | 'reverse' | 'cancel') => void;
    /** 初始价格 */
    price?: number;
    /** 按钮下方提示（可选） */
    info?: string;
    /** 数量单位：期货「手数」/ 股票「股数」✓ */
    qtyLabel?: string;
    /** 初始数量（股票默认 100 股 = 1 手） */
    qtyDefault?: number;
}

export interface TicketOrder {
    /** 方向 */
    side: 'buy' | 'sell';
    /** 开平 */
    offset: 'open' | 'close';
    /** 实际下单手数（「平多X」已经夹到持仓以内 ✓） */
    volume: number;
    /** 按钮文字（日志 / 提示用） */
    label: string;
}

export interface ReplayTicket {
    element: HTMLDivElement;
    /** 跟随最新价刷新输入框（用户没手动改过才覆盖 ✓） */
    setPrice: (price: number | null) => void;
    /** 换标的：强制写价并恢复“跟随最新价” ✓ */
    resetPrice: (price: number | null) => void;
    /** 点二级报价 10 档 → **强制**填进价格框（覆盖用户输入 ✓） */
    setPriceForce: (price: number | null) => void;
    /** 标题（回放 → 「本地模拟交易（回放）」/ 实时 → 「交易」✓） */
    setTitle: (text: string) => void;
    /** 当前交易标的（`SHFE.rb2601` ✓） */
    setSymbol: (symbol: string) => void;
    /** 是否锁定（锁定后 🔍 禁用 ✓） */
    isLocked: () => boolean;
    setLocked: (locked: boolean) => void;
    /** 能不能交易（主连 / 指数只能看行情 → 按钮禁用 ✓） */
    setTradeable: (tradeable: boolean) => void;
    /** 价格步进 = 合约最小变动价位（`price_tick`：rb 1 / ag 1 / au 0.02… ✓） */
    setStep: (tick: number | null) => void;
    /** 买一 / 卖一（价格框为空时 ↑↓ 用 ✓） */
    setBookPrices: (bid: number | null, ask: number | null) => void;
    /** 净仓（正=多 / 负=空）—— 兼容旧调用（等价 `setPosition(net, -net)`） */
    setNet: (net: number) => void;
    /** **多 / 空持仓手数**（决定四个按钮是哪一组 ✓） */
    setPosition: (long: number, short: number) => void;
    setInfo: (text: string) => void;
    setQtyLabel: (text: string) => void;
    priceValue: () => number;
    qtyValue: () => number;
}

export function buildReplayTicket(options: ReplayTicketOptions): ReplayTicket {
    const ticket = document.createElement('div');
    ticket.className = 'desk-local-ticket';

    // ---- 标题行：合约 + 🔍 + 锁定 ✓ ----
    const head = document.createElement('div');
    head.className = 'desk-local-ticket-head';
    const title = document.createElement('span');
    title.className = 'desk-local-ticket-title';
    title.textContent = options.symbol || options.title || '交易';
    title.title = '当前交易标的（点 🔍 可切换）';
    const search = document.createElement('button');
    search.type = 'button';
    search.className = 'desk-local-ticket-search';
    search.textContent = '🔍';
    search.title = '搜索合约（只切换交易标的，不换图表）';
    search.addEventListener('click', () => {
        if (search.disabled) return;
        options.onSearch?.();
    });
    const lockLabel = document.createElement('label');
    lockLabel.className = 'desk-local-ticket-lock';
    lockLabel.title = '锁定后不跟随图表切换（🔍 也不可用）';
    const lockInput = document.createElement('input');
    lockInput.type = 'checkbox';
    lockInput.checked = !!options.locked;
    const lockText = document.createElement('span');
    lockText.textContent = '锁定';
    lockLabel.append(lockInput, lockText);
    lockInput.addEventListener('change', () => {
        search.disabled = lockInput.checked;
        search.classList.toggle('off', lockInput.checked);
        options.onLockChange?.(lockInput.checked);
    });
    head.append(title, search, lockLabel);
    if (options.searchable === false) search.style.display = 'none';

    const priceRow = document.createElement('div');
    priceRow.className = 'desk-local-ticket-row';
    const priceLabel = document.createElement('span');
    priceLabel.className = 'k';
    priceLabel.textContent = '价格';
    const price = document.createElement('input');
    price.type = 'number';
    price.className = 'desk-local-ticket-price';
    // ★ 价格步进 = **合约最小变动价位**（后端 `book.price_tick` 推下来后覆盖 ✓）
    price.step = '0.01';
    price.placeholder = '现价';
    price.value = options.price ? String(options.price) : '';

    // ★ 自定义上下按钮（用户 2026-11-05 要求 ✓）
    //   · 价格框**为空**时：↑ = 卖一价、↓ = 买一价（没有盘口 → 现价 ±1 跳）
    //   · 已有价格：按**最小变动价位**加减（不是 ±1 ✗）
    const priceBox = document.createElement('span');
    priceBox.className = 'desk-local-ticket-price-box';
    const stepButtons = document.createElement('span');
    stepButtons.className = 'desk-local-ticket-steps';
    const makeStep = (dir: 1 | -1, label: string, tip: string) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `desk-local-ticket-step ${dir > 0 ? 'up' : 'down'}`;
        button.textContent = label;
        button.title = tip;
        button.tabIndex = -1;
        stepButtons.appendChild(button);
        return button;
    };
    const upButton = makeStep(1, '▲', '价格框为空时＝卖一价；否则 +1 个最小变动价位');
    const downButton = makeStep(-1, '▼', '价格框为空时＝买一价；否则 −1 个最小变动价位');
    priceBox.append(price, stepButtons);

    const qtyRow = document.createElement('div');
    qtyRow.className = 'desk-local-ticket-row';
    const qtyLabel = document.createElement('span');
    qtyLabel.className = 'k';
    qtyLabel.textContent = options.qtyLabel || '手数';
    const qty = document.createElement('input');
    qty.type = 'number';
    qty.step = '1';
    qty.min = '1';
    qty.value = String(options.qtyDefault || 1);
    priceRow.append(priceLabel, priceBox);
    qtyRow.append(qtyLabel, qty);

    // ---- 四个按钮：随仓位状态切换（快期同款 ✓）----------------------
    const actionButtons: HTMLButtonElement[] = [];
    // ⚠ 必须在**第一次 `renderButtons()` 之前**声明（否则 TDZ 报错 →
    //   交易面板建不出来，整个本地图表页都建不起来 ✗）
    const actionButtonsByKind: Record<string, HTMLButtonElement> = {};
    const buttons = document.createElement('div');
    buttons.className = 'desk-local-ticket-buttons desk-local-ticket-four';
    let longVolume = 0;
    let shortVolume = 0;
    let labels: Array<{ label: string; side: 'buy' | 'sell';
                        offset: 'open' | 'close'; qty(): number;
                        enabled: boolean; cls: string; tip: string }> = [];
    const four: HTMLButtonElement[] = [];
    for (let index = 0; index < 4; index += 1) {
        const button = document.createElement('button');
        button.addEventListener('click', () => {
            const entry = labels[index];
            if (!entry || !entry.enabled) return;
            options.onOrder({
                side: entry.side,
                offset: entry.offset,
                volume: entry.qty(),
                label: entry.label,
            });
        });
        four.push(button);
        buttons.appendChild(button);
    }

    /** 手数框数值（默认 1）✓ */
    const rawQty = (): number => {
        const value = Math.round(Number(qty.value));
        return Number.isFinite(value) && value > 0 ? value : 1;
    };
    /** 「平多X」里的 X：夹在 `1..持仓` ✓（持仓 0 → 1，按钮禁用） */
    const closeQty = (available: number): number => {
        const want = rawQty();
        const cap = Math.max(0, Math.round(available));
        if (cap <= 0) return 1;
        return Math.max(1, Math.min(want, cap));
    };

    const renderButtons = () => {
        const long = Math.max(0, Math.round(longVolume));
        const short = Math.max(0, Math.round(shortVolume));
        const qtyNow = rawQty();
        const bullTip = '按上面的手数 / 价格；价格留空=对手价';
        if (long > 0 && short > 0) {
            // 锁仓：加多 / 加空 / 平空X / 平多X ✓
            labels = [
                { label: '加多', side: 'buy', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'buy', tip: `买入开多 ${qtyNow} 手（${bullTip}）` },
                { label: '加空', side: 'sell', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'sell', tip: `卖出开空 ${qtyNow} 手（${bullTip}）` },
                { label: `平空${closeQty(short)}`, side: 'buy', offset: 'close',
                  qty: () => closeQty(short), enabled: true, cls: 'flat',
                  tip: `买入平掉 ${closeQty(short)} 手空头（可平 ${short}）` },
                { label: `平多${closeQty(long)}`, side: 'sell', offset: 'close',
                  qty: () => closeQty(long), enabled: true, cls: 'flat',
                  tip: `卖出平掉 ${closeQty(long)} 手多头（可平 ${long}）` },
            ];
        } else if (long > 0) {
            // 多仓：加多 / 买平 / 平多X / 锁仓 ✓
            labels = [
                { label: '加多', side: 'buy', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'buy', tip: `买入加多 ${qtyNow} 手（${bullTip}）` },
                { label: '买平', side: 'sell', offset: 'close', qty: rawQty,
                  enabled: true, cls: 'flat',
                  tip: `卖出平多 ${qtyNow} 手（多头持仓 ${long}）` },
                { label: `平多${closeQty(long)}`, side: 'sell', offset: 'close',
                  qty: () => closeQty(long), enabled: true, cls: 'flat',
                  tip: `卖出平掉 ${closeQty(long)} 手多头（可平 ${long}）` },
                { label: '锁仓', side: 'sell', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'plain',
                  tip: `卖出开空 ${qtyNow} 手（和现有多头锁仓）` },
            ];
        } else if (short > 0) {
            // 空仓：加空 / 卖平 / 平空X / 锁仓 ✓
            labels = [
                { label: '加空', side: 'sell', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'sell', tip: `卖出加空 ${qtyNow} 手（${bullTip}）` },
                { label: '卖平', side: 'buy', offset: 'close', qty: rawQty,
                  enabled: true, cls: 'flat',
                  tip: `买入平空 ${qtyNow} 手（空头持仓 ${short}）` },
                { label: `平空${closeQty(short)}`, side: 'buy', offset: 'close',
                  qty: () => closeQty(short), enabled: true, cls: 'flat',
                  tip: `买入平掉 ${closeQty(short)} 手空头（可平 ${short}）` },
                { label: '锁仓', side: 'buy', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'plain',
                  tip: `买入开多 ${qtyNow} 手（和现有空头锁仓）` },
            ];
        } else {
            // 无仓位：买开 / 卖开 / 买平 / 卖平（后两个没有持仓 → 禁用 ✓）
            labels = [
                { label: '买开', side: 'buy', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'buy', tip: `买入开多 ${qtyNow} 手（${bullTip}）` },
                { label: '卖开', side: 'sell', offset: 'open', qty: rawQty,
                  enabled: true, cls: 'sell', tip: `卖出开空 ${qtyNow} 手（${bullTip}）` },
                { label: '买平', side: 'buy', offset: 'close', qty: rawQty,
                  enabled: false, cls: 'flat', tip: '没有空头持仓，无法买入平仓' },
                { label: '卖平', side: 'sell', offset: 'close', qty: rawQty,
                  enabled: false, cls: 'flat', tip: '没有多头持仓，无法卖出平仓' },
            ];
        }
        // ★ 锁仓（多空两边都有）时「反手」不可用（用户要求 2026-11-05 ✓）
        const locked = long > 0 && short > 0;
        const reverseButton = actionButtonsByKind.reverse;
        if (reverseButton) {
            reverseButton.disabled = locked || !tradeable;
            reverseButton.style.opacity = locked ? '.35' : '';
            reverseButton.style.cursor = locked ? 'not-allowed' : 'pointer';
            reverseButton.title = locked
                ? '锁仓状态下不能反手（先平掉一边）'
                : '反手（对手价平掉后反向开相同手数）';
        }
        labels.forEach((entry, index) => {
            const button = four[index];
            if (!button) return;
            button.textContent = entry.label;
            button.title = entry.tip;
            button.className = `${entry.cls}`;
            button.disabled = !entry.enabled || !tradeable;
            button.style.opacity = entry.enabled
                ? (tradeable ? '' : '.45') : '.35';
            button.style.cursor = entry.enabled ? 'pointer' : 'not-allowed';
        });
    };
    let tradeable = true;
    renderButtons();

    const acts = document.createElement('div');
    acts.className = 'desk-local-ticket-buttons desk-local-ticket-acts';
    // ★ 第二排：市价平仓 / 反手 / 撤单（样式跟随二级报价 ✓）
    for (const [action, label, cls, tip] of [
            ['close_main', '市价平仓', 'flat',
             '按**对手价**平掉当前合约全部持仓（上期所等不支持市价单 ✓）'],
            ['reverse', '反手', 'plain', '反手（对手价平掉后反向开相同手数）'],
            ['cancel', '撤单', 'plain', '撤掉当前合约未成交的挂单']] as const) {
        const button = document.createElement('button');
        button.className = `desk-book-btn ${cls}`;
        button.textContent = label;
        button.title = tip;
        button.addEventListener('click', () => {
            if (button.disabled) return;
            options.onAction(action);
        });
        actionButtons.push(button);
        actionButtonsByKind[action] = button;
        acts.appendChild(button);
    }
    actionButtons.push(...four);

    const info = document.createElement('div');
    info.className = 'desk-local-ticket-info';
    info.textContent = options.info || '回放中同样有效';
    ticket.append(head, priceRow, qtyRow, buttons, acts, info);

    let touched = false;
    //: 最新价（只做 placeholder 参考，不再参与下单价 ✓）
    let lastPrice: number | null = null;
    price.addEventListener('input', () => {
        touched = true;
    });
    // ★ 手数框一变，「平多X / 平空X」的 X 跟着变（夹在 1..持仓 ✓）
    qty.addEventListener('input', () => renderButtons());

    //: 最小变动价位（后端 `book.price_tick` 推下来 ✓）
    let stepValue = 0.01;
    //: 买一 / 卖一（价格框为空时点上下按钮用 ✓）
    let bidOne: number | null = null;
    let askOne: number | null = null;

    /** 步进的小数位（0.02 → 2 位；0.5 → 1 位）✓ */
    const stepDecimals = (): number => {
        const text = stepValue.toFixed(10).replace(/0+$/, '');
        const dot = text.indexOf('.');
        return dot < 0 ? 0 : Math.min(6, text.length - dot - 1);
    };
    const formatPrice = (value: number): string => (
        Number.isFinite(value) ? value.toFixed(stepDecimals()) : '');

    /**
     * 上 / 下按钮 ✓
     * * 空 → ↑ 卖一价、↓ 买一价（没有盘口 → 现价 ∓/± 一个最小变动价位）
     * * 有值 → ± 一个**最小变动价位**
     */
    const nudge = (dir: 1 | -1): void => {
        const current = Number(price.value);
        const empty = !(Number.isFinite(current) && current > 0);
        let next: number | null = null;
        if (empty) {
            const book = dir > 0 ? askOne : bidOne;
            if (book !== null && Number.isFinite(book) && book > 0) {
                next = book;
            } else if (lastPrice !== null && Number.isFinite(lastPrice)) {
                next = lastPrice + dir * stepValue;
            }
        } else {
            next = current + dir * stepValue;
        }
        if (next === null || !Number.isFinite(next) || next <= 0) return;
        price.value = formatPrice(next);
        touched = true;
    };
    upButton.addEventListener('click', () => nudge(1));
    downButton.addEventListener('click', () => nudge(-1));
    // ★ 价格框默认**留空**，只把最新价当 placeholder：空 = 市价；
    //   填了价才是**限价挂单**（等价格触发，图上会出现挂单 / 平仓线 ✓）
    const setPrice = (value: number | null) => {
        if (value === null || !Number.isFinite(value) || value <= 0) return;
        lastPrice = value;
        if (!touched) price.placeholder = String(value);
    };
    setPrice(options.price ?? null);
    void lastPrice;         // 仅用于 placeholder / 日志，别被 TS 当未使用 ✓
    return {
        element: ticket,
        setPrice,
        setPriceForce: (value: number | null) => {
            const next = Number(value);
            if (!Number.isFinite(next) || next <= 0) return;
            lastPrice = next;
            price.value = String(next);
            touched = true;          // 用户选的价 → 不再被最新价覆盖 ✓
        },
        // ★ 换交易标的（点了另一张图 / 另一个合约）：强制换成新合约的最新价，
        //   并且**解除 touched**，让后面的实时行情继续更新价格框 ✓
        resetPrice: (value: number | null) => {
            const next = Number(value);
            if (!Number.isFinite(next) || next <= 0) return;
            lastPrice = next;
            price.value = '';            // 换标的 → 清空（回到"市价"）✓
            price.placeholder = String(next);
            touched = false;
        },
        setTitle: (text: string) => {
            title.textContent = text;
        },
        setSymbol: (symbol: string) => {
            if (!symbol) return;
            title.textContent = symbol;
            qtyLabel.textContent = /^(SH|SZ|HK|US|JP)\./i.test(symbol)
                ? '股数' : '手数';
        },
        setQtyLabel: (text: string) => {
            qtyLabel.textContent = text;
        },
        isLocked: () => !!lockInput.checked,
        setLocked: (locked: boolean) => {
            lockInput.checked = !!locked;
            search.disabled = !!locked;
            search.classList.toggle('off', !!locked);
        },
        setTradeable: (value: boolean) => {
            tradeable = value !== false;
            renderButtons();          // 四个按钮按状态重算（含禁用）✓
            for (const button of actionButtons.slice(4)) {
                button.disabled = !tradeable;
                button.style.opacity = tradeable ? '' : '.45';
                button.style.cursor = tradeable ? 'pointer' : 'not-allowed';
            }
        },
        setStep: (tick: number | null) => {
            const value = Number(tick);
            if (!Number.isFinite(value) || value <= 0) return;
            stepValue = value;
            // 用定点字符串，避免 `0.020000000000000004` 这种浮点尾巴 ✓
            const text = value.toFixed(10).replace(/0+$/, '').replace(/\.$/, '');
            price.step = text || '0.01';
        },
        /** 买一 / 卖一（价格框为空时上下按钮的默认值 ✓） */
        setBookPrices: (bid: number | null, ask: number | null) => {
            const b = Number(bid);
            const a = Number(ask);
            bidOne = Number.isFinite(b) && b > 0 ? b : null;
            askOne = Number.isFinite(a) && a > 0 ? a : null;
        },
        setNet: (value: number) => {
            const number = Number(value) || 0;
            longVolume = number > 0 ? number : 0;
            shortVolume = number < 0 ? -number : 0;
            renderButtons();
        },
        setPosition: (long: number, short: number) => {
            longVolume = Math.max(0, Number(long) || 0);
            shortVolume = Math.max(0, Number(short) || 0);
            renderButtons();
        },
        setInfo: (text: string) => {
            info.textContent = text;
        },
        priceValue: () => {
            // ★ 空 = **0（市价）**；以前回退成最新价 → 变成可成交的限价单，
            //   点「平仓」立刻成交、永远看不到挂单（用户实测 2026-11-05 ✗）
            const raw = Number(price.value);
            return Number.isFinite(raw) && raw > 0 ? raw : 0;
        },
        qtyValue: () => {
            const raw = Math.round(Number(qty.value));
            return Number.isFinite(raw) && raw > 0 ? raw : 1;
        },
    };
}

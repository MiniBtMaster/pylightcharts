/**
 * 图上「买卖盘」条 —— **每格一条**，放在该格图例里 ✓
 *
 * 显隐**统一由工具栏的「买卖盘」按钮控制**（一键显示 / 隐藏所有格）——
 * 用户 2026-11-04 要求去掉行尾 👁，不再做逐格开关（"不用搞那么复杂"）。
 *
 * 用户 2026-11-03 反馈的三处问题都源于「整页只有一个买卖盘节点」：
 *
 * 1. 多布局（左右）时买卖盘**完全不出现** —— 节点是单例，固定插进
 *    `cells[0]` 的原生图例；切布局会重建 cells / legend，节点留在被卸载的
 *    旧图例里 → 看不见 ✗；
 * 2. 本地图表买卖盘**只作用于格 1** —— 同一个单例只挂在格 1；
 * 3. 工具栏「买卖盘」按钮其实是「格 1 的开关」，多格时语义错位 ✗。
 *
 * 现在的设计（用户确认 ✓）：
 * - 买卖盘是**图表常驻**功能，每格一条，跟着该格的图例走；
 * - 行尾 **👁 眼睛** 控制**当前格**的显示 / 隐藏（和指标行的眼睛同一套交互）；
 * - 工具栏按钮降级为**全局开关**（全开 / 全关所有格）；
 * - 显隐状态按「合约 / 数据名」落盘（`user_prefs` 的 `ticket_visible`），
 *   下次打开还是原样；打开某格的 👁 才让后端订阅该格盘口（省订阅 ✓）。
 *
 * 视觉沿用原来那套 `desk-ticket*` 样式（买入 | 点差 | 卖出，有仓 → 平仓）。
 */

export interface TicketSide {
    node: HTMLButtonElement;
    price: HTMLSpanElement;
    label: HTMLSpanElement;
}

export interface TicketBarOptions {
    /** 价格小数位（合约最小变动价位推出来 ✓） */
    decimals?: number;
    /** 初始是否显示 */
    visible?: boolean;
    /** 点「买入 / 卖出」（市价 / 目标仓位） */
    onOrder?: (side: 'buy' | 'sell') => void;
    /** 无数据时的标题 */
    title?: string;
}

export class TicketBar {
    readonly element: HTMLDivElement;

    private readonly body: HTMLDivElement;

    private readonly buy: TicketSide;

    private readonly sell: TicketSide;

    private readonly spread: HTMLDivElement;

    private visible: boolean;

    private decimals: number;

    private bid: number | null = null;

    private ask: number | null = null;

    private net = 0;

    private readonly options: TicketBarOptions;

    constructor(options: TicketBarOptions = {}) {
        this.options = options;
        this.visible = options.visible !== false;
        this.decimals = Math.max(0, Math.min(6,
            Math.round(Number(options.decimals ?? 2) || 0)));
        const box = document.createElement('div');
        box.className = 'desk-ticket in-legend';
        const body = document.createElement('div');
        body.className = 'desk-ticket-body';
        const row = document.createElement('div');
        row.className = 'desk-ticket-row';
        this.buy = TicketBar._makeSide('buy', (side) => this._click(side));
        this.spread = document.createElement('div');
        this.spread.className = 'desk-ticket-spread';
        this.spread.textContent = '--';
        this.spread.title = '点差（卖一 − 买一）';
        this.sell = TicketBar._makeSide('sell', (side) => this._click(side));
        row.append(this.buy.node, this.spread, this.sell.node);
        body.append(row);
        box.append(body);
        this.element = box;
        this.body = body;
        this.setVisible(this.visible);
        this.render();
    }

    private static _makeSide(
        side: 'buy' | 'sell',
        onClick: (side: 'buy' | 'sell') => void,
    ): TicketSide {
        const node = document.createElement('button');
        node.className = `desk-ticket-side ${side}`;
        node.type = 'button';
        node.title = side === 'buy'
            ? '买入（市价加多；空头时＝平仓）' : '卖出（市价加空；多头时＝平仓）';
        const price = document.createElement('span');
        price.className = 'desk-ticket-price';
        price.textContent = '--';
        const label = document.createElement('span');
        label.className = 'desk-ticket-label';
        label.textContent = side === 'buy' ? '买入' : '卖出';
        node.append(price, label);
        node.addEventListener('click', (event) => {
            event.stopPropagation();
            onClick(side);
        });
        return { node, price, label };
    }

    private _click(side: 'buy' | 'sell'): void {
        if (!this.visible) return;
        this.options.onOrder?.(side);
    }

    get isVisible(): boolean {
        return this.visible;
    }

    /** 显示 / 隐藏（工具栏「买卖盘」统一控制 ✓） */
    setVisible(visible: boolean): void {
        this.visible = !!visible;
        this.element.classList.add('on');
        this.element.classList.toggle('off', !this.visible);
    }

    setDecimals(value: number): void {
        const number = Number(value);
        if (!Number.isFinite(number)) return;
        const decimals = Math.max(0, Math.min(6, Math.round(number)));
        if (decimals === this.decimals) return;
        this.decimals = decimals;
        this.render();
    }

    setBook(data: {
        bids?: Array<{ price?: number | null }>;
        asks?: Array<{ price?: number | null }>;
    }): void {
        const bid = Number((data?.bids || [])[0]?.price);
        const ask = Number((data?.asks || [])[0]?.price);
        if (Number.isFinite(bid)) this.bid = bid;
        if (Number.isFinite(ask)) this.ask = ask;
        this.render();
    }

    /** 净仓（正 = 多、负 = 空）→ 标签变成「平仓」✓ */
    setNet(net: number): void {
        const value = Math.round(Number(net) || 0);
        if (value === this.net) return;
        this.net = value;
        this.render();
    }

    get netPosition(): number {
        return this.net;
    }

    private _spread(): number | null {
        if (this.bid === null || this.ask === null) return null;
        return Math.abs(this.ask - this.bid);
    }

    render(): void {
        const decimals = this.decimals;
        const leftClose = this.net < 0;
        const rightClose = this.net > 0;
        this.buy.price.textContent = this.ask === null
            ? '--' : this.ask.toFixed(decimals);
        this.buy.label.textContent = leftClose ? '平仓' : '买入';
        this.buy.node.classList.toggle('flat', leftClose);
        this.sell.price.textContent = this.bid === null
            ? '--' : this.bid.toFixed(decimals);
        this.sell.label.textContent = rightClose ? '平仓' : '卖出';
        this.sell.node.classList.toggle('flat', rightClose);
        const spread = this._spread();
        this.spread.textContent = spread === null
            ? '--' : spread.toFixed(decimals);
        this.element.classList.toggle('has-position', !!this.net);
        if (this.options.title) this.body.title = this.options.title;
    }
}

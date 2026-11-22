/**
 * 扩展功能页：交易工作台 / 策略研究 / 数据平台 / 运维。
 *
 * 这些页面只负责「收集参数 + 显示后端补丁」，不直接下单 / 跑回测：
 * 所有动作都通过 `onCommand(cmd, payload)` 回到 Python。
 */
import type { DeskTheme } from './theme';

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] as string));
}

function num(value: unknown, digits = 2): string {
    if (value === null || value === undefined || value === '') return '—';
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return '—';
    return parsed.toLocaleString(undefined, {
        minimumFractionDigits: 0, maximumFractionDigits: digits,
    });
}

function stabilityScore(summary: Record<string, any>, direction = 1): number | null {
    const mean = Number(summary?.mean);
    if (!Number.isFinite(mean)) return null;
    const std = Number(summary?.std) || 0;
    const rate = Number(summary?.positive_rate) || 0;
    const dir = direction === -1 ? -1 : 1;
    const score = 50 + mean * 100 * dir - std * 80 + (rate - 0.5) * 40;
    return Math.max(0, Math.min(100, score));
}

function when(value: unknown): string {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return '—';
    const date = new Date(parsed * 1000);
    return date.toLocaleString(undefined, { hour12: false });
}

function table(headers: string[], rows: string[][], empty = '暂无数据'): string {
    if (!rows.length) return `<div class="desk-suite-empty">${esc(empty)}</div>`;
    return `<table class="desk-suite-table"><thead><tr>${
        headers.map((item) => `<th>${esc(item)}</th>`).join('')
    }</tr></thead><tbody>${rows.map((row) => `<tr>${
        row.map((cell) => `<td>${cell}</td>`).join('')
    }</tr>`).join('')}</tbody></table>`;
}

const STATUS_TEXT: Record<string, string> = {
    PENDING: '已提交', ALIVE: '挂单中', PARTIAL: '部分成交',
    FINISHED: '已成交', CANCELLED: '已撤单', REJECTED: '已拒绝',
    ARMED: '条件待触发', TRIGGERED: '已触发',
};

function stateBadge(status: unknown): string {
    const key = String(status || '').toUpperCase();
    const cls = key === 'REJECTED' ? 'bad' : (
        key === 'FINISHED' ? 'good' : (
            key === 'CANCELLED' ? 'muted' : 'live'));
    return `<span class="desk-suite-state ${cls}">${
        esc(STATUS_TEXT[key] || key || '—')}</span>`;
}

function shell(kind: string, theme: DeskTheme, title: string,
               subtitle: string, body: string): HTMLDivElement {
    const element = document.createElement('div');
    element.className = `desk-suite-page desk-suite-${kind} theme-${theme}`;
    element.innerHTML = `
        <div class="desk-suite-head">
            <div><h2>${esc(title)}</h2><p class="desk-muted">${esc(subtitle)}</p></div>
            <div class="desk-suite-actions" data-suite-actions></div>
        </div>
        ${body}`;
    return element;
}

interface PageOptions {
    theme: DeskTheme;
    onCommand: (cmd: string, payload?: unknown) => void;
    /** 轻提示（可选；运维页新建任务校验用 ✓ v1.3.7-79） */
    onToast?: (kind: string, text: string) => void;
}

// ================================================================ 交易工作台
export class WorkbenchPage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions;
    private theme: DeskTheme;

    constructor(options: PageOptions) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('workbench', this.theme, '交易工作台',
            '订单票 / 条件单 / 风控 / 对账 / 审计。所有下单仍然走 desk 的同一个交易执行器。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            this.onClick(event);
        });
        this.element.addEventListener('change', (event) => {
            const target = event.target as HTMLElement;
            if (target.closest('[data-wb="orderType"]')) this.syncType();
        });
    }

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-workbench theme-${theme}`;
    }

    private skeleton(): string {
        return `
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>订单票</h3>
                <div class="desk-suite-form">
                    <label>合约<input data-wb="symbol" placeholder="SHFE.ag2612"></label>
                    <label>方向<select data-wb="side">
                        <option value="buy">买入 / 开多</option>
                        <option value="sell">卖出 / 开空</option>
                        <option value="close">平仓</option>
                    </select></label>
                    <label>类型<select data-wb="orderType">
                        <option value="market">市价</option>
                        <option value="limit">限价</option>
                        <option value="stop">止损（触发市价）</option>
                        <option value="conditional">条件单</option>
                    </select></label>
                    <label>价格<input data-wb="price" type="number" step="0.01" placeholder="限价 / 触发后限价"></label>
                    <label>触发价<input data-wb="trigger" type="number" step="0.01" placeholder="止损 / 条件单"></label>
                    <label>条件<select data-wb="condition">
                        <option value=">=">价格 ≥ 触发</option>
                        <option value="<=">价格 ≤ 触发</option>
                        <option value="cross_up">上穿</option>
                        <option value="cross_down">下穿</option>
                    </select></label>
                    <label>数量<input data-wb="volume" type="number" min="1" value="1"></label>
                    <label>TIF<select data-wb="tif">
                        <option value="GFD">GFD（当日有效）</option>
                        <option value="IOC">IOC（立即成交否则撤）</option>
                        <option value="FOK">FOK（全部成交否则撤）</option>
                    </select></label>
                    <label class="wide">备注<input data-wb="note" placeholder="可选"></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-wb-submit>下单</button>
                    <button class="desk-tool" data-wb-reconcile>对账</button>
                    <button class="desk-tool" data-wb-export-orders>导出委托</button>
                    <button class="desk-tool" data-wb-export-audit>导出审计</button>
                    <button class="desk-tool danger" data-wb-cancel-all>全撤</button>
                </div>
                <div class="desk-suite-hint" id="wb-note"></div>
            </section>
            <section class="desk-suite-card">
                <h3>风控</h3>
                <div class="desk-suite-form">
                    <label class="inline"><input type="checkbox" data-wb="riskEnabled"> 启用风控</label>
                    <label>单笔最多（手/股）<input data-wb="maxVolume" type="number" min="0"></label>
                    <label>单笔最大金额<input data-wb="maxNotional" type="number" min="0"></label>
                    <label>单日最多委托<input data-wb="maxOrders" type="number" min="0"></label>
                    <label>单日最大亏损<input data-wb="maxLoss" type="number" min="0"></label>
                    <label>净持仓上限<input data-wb="maxPosition" type="number" min="0"></label>
                    <label class="inline"><input type="checkbox" data-wb="allowShort" checked> 允许开空</label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-wb-save-limits>保存风控</button>
                </div>
                <div class="desk-suite-kv" id="wb-stats"></div>
            </section>
        </div>
        <section class="desk-suite-card">
            <h3>委托流水 <span class="desk-muted" id="wb-count"></span></h3>
            <div id="wb-orders"></div>
        </section>
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>条件单</h3>
                <div id="wb-conditional"></div>
            </section>
            <section class="desk-suite-card">
                <h3>对账</h3>
                <div id="wb-reconcile"></div>
            </section>
        </div>
        <section class="desk-suite-card">
            <h3>审计日志</h3>
            <div id="wb-audit"></div>
        </section>`;
    }

    private input(name: string): HTMLInputElement | HTMLSelectElement | null {
        return this.element.querySelector(
            `[data-wb="${name}"]`) as HTMLInputElement | HTMLSelectElement | null;
    }

    private value(name: string): string {
        return String(this.input(name)?.value ?? '').trim();
    }

    private checked(name: string): boolean {
        return !!(this.input(name) as HTMLInputElement | null)?.checked;
    }

    private syncType(): void {
        const type = this.value('orderType');
        const price = this.input('price');
        const trigger = this.input('trigger');
        if (price) price.disabled = type === 'market';
        if (trigger) trigger.disabled = !(type === 'stop' || type === 'conditional');
    }

    private onClick(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        const click = (selector: string) => !!target.closest(selector);
        if (click('[data-wb-reconcile]')) {
            this.options.onCommand('workbench_reconcile', {});
            return;
        }
        if (click('[data-wb-export-orders]')) {
            this.options.onCommand('workbench_export', { table: 'orders' });
            return;
        }
        if (click('[data-wb-export-audit]')) {
            this.options.onCommand('workbench_export', { table: 'audit' });
            return;
        }
        if (click('[data-wb-cancel-all]')) {
            if (!window.confirm('确定撤销全部未成交委托？')) return;
            this.options.onCommand('workbench_cancel',
                { all: true, symbol: this.value('symbol') });
            return;
        }
        if (click('[data-wb-save-limits]')) {
            this.options.onCommand('workbench_limits', {
                enabled: this.checked('riskEnabled'),
                max_volume: Number(this.value('maxVolume') || 0),
                max_notional: Number(this.value('maxNotional') || 0),
                max_orders_per_day: Number(this.value('maxOrders') || 0),
                max_daily_loss: Number(this.value('maxLoss') || 0),
                max_position: Number(this.value('maxPosition') || 0),
                allow_short: this.checked('allowShort'),
            });
            return;
        }
        if (click('[data-wb-submit]')) {
            const type = this.value('orderType');
            const payload: Record<string, unknown> = {
                symbol: this.value('symbol'), side: this.value('side'),
                volume: Number(this.value('volume') || 1),
                order_type: type, tif: this.value('tif'),
                note: this.value('note'),
            };
            if (type !== 'market') payload.price = Number(this.value('price') || 0) || null;
            if (type === 'stop' || type === 'conditional') {
                payload.trigger_price = Number(this.value('trigger') || 0) || null;
                payload.condition = this.value('condition');
            }
            if (!String(payload.symbol || '')) {
                window.alert('请先填合约');
                return;
            }
            this.options.onCommand('workbench_submit', payload);
            return;
        }
        const cancel = target.closest<HTMLElement>('[data-wb-cancel]');
        if (cancel) {
            this.options.onCommand('workbench_cancel', {
                order_id: cancel.dataset.orderId || '',
                symbol: cancel.dataset.symbol || '',
                id: Number(cancel.dataset.localId || 0),
            });
            return;
        }
        const modify = target.closest<HTMLElement>('[data-wb-modify]');
        if (modify) {
            const price = window.prompt('新的限价', modify.dataset.price || '');
            if (!price) return;
            this.options.onCommand('workbench_modify', {
                order_id: modify.dataset.orderId || '',
                symbol: modify.dataset.symbol || '',
                id: Number(modify.dataset.localId || 0),
                side: modify.dataset.side || 'buy',
                volume: Number(modify.dataset.volume || 1),
                price: Number(price),
            });
            return;
        }
        const cond = target.closest<HTMLElement>('[data-wb-cond-cancel]');
        if (cond) {
            this.options.onCommand('workbench_conditional_cancel',
                { id: cond.dataset.id || '' });
        }
    }

    apply(patch: Record<string, any>): void {
        if (patch.type !== 'workbench') return;
        const stats = patch.stats || {};
        const account = String(patch.account || '—');
        const statsBox = this.element.querySelector('#wb-stats');
        if (statsBox) {
            statsBox.innerHTML = `
                <span>账户 <b>${esc(account)}</b></span>
                <span>委托 <b>${esc(stats.orders ?? 0)}</b></span>
                <span>未完成 <b>${esc(stats.open ?? 0)}</b></span>
                <span>失败 <b>${esc(stats.failed ?? 0)}</b></span>
                <span>当日盈亏 <b>${num(stats.daily_pnl, 2)}</b></span>
                <span>交易 <b>${patch.enabled ? '已启用' : '未启用'}</b>${
                    patch.real ? ' · <b class="warn">实盘</b>' : ''}</span>`;
        }
        const limits = patch.limits || {};
        const setValue = (name: string, value: unknown) => {
            const input = this.input(name);
            if (input) input.value = value === null || value === undefined
                ? '' : String(value);
        };
        const enabled = this.input('riskEnabled') as HTMLInputElement | null;
        if (enabled) enabled.checked = !!limits.enabled;
        const allowShort = this.input('allowShort') as HTMLInputElement | null;
        if (allowShort) allowShort.checked = limits.allow_short !== false;
        setValue('maxVolume', limits.max_volume ?? '');
        setValue('maxNotional', limits.max_notional ?? '');
        setValue('maxOrders', limits.max_orders_per_day ?? '');
        setValue('maxLoss', limits.max_daily_loss ?? '');
        setValue('maxPosition', limits.max_position ?? '');
        this.syncType();

        const orders = (patch.orders || []) as Array<Record<string, any>>;
        const orderRows = orders.map((row) => {
            const open = ['PENDING', 'ALIVE', 'PARTIAL'].includes(
                String(row.status || ''));
            const actions = open ? `
                <button class="desk-suite-link" data-wb-cancel data-order-id="${esc(row.order_id || '')}" data-symbol="${esc(row.symbol || '')}" data-local-id="${esc(row.id || '')}">撤</button>
                <button class="desk-suite-link" data-wb-modify data-order-id="${esc(row.order_id || '')}" data-symbol="${esc(row.symbol || '')}" data-side="${esc(row.side || 'buy')}" data-volume="${esc(row.volume || 1)}" data-local-id="${esc(row.id || '')}" data-price="${esc(row.price || '')}">改</button>`
                : '';
            return [
                `<span class="desk-muted">${when(row.ts)}</span>`,
                esc(row.symbol || ''), esc(row.side || ''),
                esc(row.volume ?? ''), row.price ? num(row.price, 4) : '市价',
                esc(row.order_type || ''), stateBadge(row.status),
                `<span class="desk-suite-cell">${esc(row.text || '')}</span>`,
                actions,
            ];
        });
        const ordersBox = this.element.querySelector('#wb-orders');
        if (ordersBox) {
            ordersBox.innerHTML = table(
                ['时间', '合约', '方向', '数量', '价格', '类型', '状态', '说明', '操作'],
                orderRows, '还没有委托');
        }
        const count = this.element.querySelector('#wb-count');
        if (count) count.textContent = orders.length ? `（${orders.length}）` : '';

        const conditional = (patch.conditional || []) as Array<Record<string, any>>;
        const condBox = this.element.querySelector('#wb-conditional');
        if (condBox) {
            condBox.innerHTML = table(['合约', '方向', '数量', '条件', '触发价', '状态', ''],
                conditional.map((row) => [
                    esc(row.symbol || ''), esc(row.side || ''),
                    esc(row.volume ?? ''), esc(row.condition || ''),
                    num(row.trigger_price, 4), stateBadge(row.status || 'ARMED'),
                    `<button class="desk-suite-link" data-wb-cond-cancel data-id="${esc(row.id || '')}">撤销</button>`,
                ]), '没有条件单');
        }

        const recon = patch.reconcile || {};
        const reconBox = this.element.querySelector('#wb-reconcile');
        if (reconBox) {
            const missing = (recon.missing || []) as Array<Record<string, any>>;
            const extra = (recon.extra || []) as Array<Record<string, any>>;
            reconBox.innerHTML = recon.at ? `
                <div class="desk-suite-kv">
                    <span>本地未完成 <b>${esc(recon.local_open ?? 0)}</b></span>
                    <span>券商未成交 <b>${esc(recon.broker_open ?? 0)}</b></span>
                    <span>差异 <b>${missing.length + extra.length}</b></span>
                </div>
                ${table(['差异', '合约', '委托号'], [
                    ...missing.map((row) => ['本地有 / 券商无',
                        esc(row.symbol || ''), esc(row.order_id || '')]),
                    ...extra.map((row) => ['券商有 / 本地无',
                        esc(row.symbol || ''), esc(row.order_id || '')]),
                ], '本地与券商一致')}
                ${(recon.errors || []).length
                    ? `<div class="desk-suite-hint warn">${esc((recon.errors || []).join('；'))}</div>` : ''}`
                : '<div class="desk-suite-empty">还没有对账。点「对账」比较本地流水与券商未成交委托。</div>';
        }

        const audit = (patch.audit || []) as Array<Record<string, any>>;
        const auditBox = this.element.querySelector('#wb-audit');
        if (auditBox) {
            auditBox.innerHTML = table(['时间', '类型', '合约', '方向', '数量', '价格', '状态', '说明'],
                audit.map((row) => [
                    `<span class="desk-muted">${when(row.ts)}</span>`,
                    esc(row.kind || ''), esc(row.symbol || ''),
                    esc(row.side || ''), esc(row.volume ?? ''),
                    row.price === null || row.price === undefined ? '' : num(row.price, 4),
                    stateBadge(row.status || ''), esc(row.text || ''),
                ]), '还没有审计记录');
        }
    }
}

// ================================================================ 研究平台
export class ResearchPage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions;
    private theme: DeskTheme;
    private data: Record<string, any> = {};
    private selected = 0;

    constructor(options: PageOptions) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('research', this.theme, '策略研究平台',
            'Walk-forward / 批量回测 / 参数网格；结果自动写进实验库，可导出 Markdown + CSV。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            this.onClick(event);
        });
        this.element.addEventListener('change', (event) => {
            const target = event.target as HTMLElement;
            if (target.closest('[data-rs="heatMetric"]')) this.renderHeatmap();
        });
    }

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-research theme-${theme}`;
    }

    private skeleton(): string {
        return `
        <section class="desk-suite-card">
            <h3>新实验</h3>
            <div class="desk-suite-form">
                <label>模式<select data-rs="mode">
                    <option value="walk_forward">Walk-forward（滚动训练/测试）</option>
                    <option value="batch">批量回测（多数据文件）</option>
                    <option value="grid">参数网格</option>
                </select></label>
                <label>策略文件<input data-rs="file" placeholder="C:/.../my_strategy.py"></label>
                <label class="wide">数据文件（LocalDatas 名 / CSV 路径）
                    <input data-rs="data" list="rs-data-names"
                           placeholder="留空 = 按策略里的 LocalDatas 自动识别；如 test / l2609_60">
                    <datalist id="rs-data-names"></datalist>
                </label>
                <label>训练根数<input data-rs="train" type="number" value="240"></label>
                <label>测试根数<input data-rs="test" type="number" value="60"></label>
                <label>步长<input data-rs="step" type="number" value="60"></label>
                <label>实验名<input data-rs="name" placeholder="可选"></label>
                <label>指标 1<select data-rs="metric0"></select></label>
                <label>指标 2<select data-rs="metric1"><option value="">（不使用）</option></select></label>
                <label>指标 3<select data-rs="metric2"><option value="">（不使用）</option></select></label>
                <label class="wide">参数（JSON）<textarea data-rs="params" rows="3" placeholder='{"length":[10,20],"std":[1,2]}'></textarea></label>
            </div>
            <div class="desk-suite-buttons">
                <button class="desk-tool primary" data-rs-run>开始</button>
                <button class="desk-tool" data-rs-cancel>取消</button>
                <button class="desk-tool" data-rs-refresh>刷新实验库</button>
            </div>
            <div class="desk-suite-hint" id="rs-status"></div>
        </section>
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>稳定性摘要</h3>
                <div id="rs-summary"></div>
            </section>
            <section class="desk-suite-card">
                <h3>Pareto 前沿</h3>
                <div id="rs-pareto"></div>
            </section>
        </div>
        <section class="desk-suite-card">
            <h3>参数热力图
                <select data-rs="heatMetric" class="desk-suite-inline-select"></select>
                <span class="desk-muted" id="rs-heat-title"></span></h3>
            <div id="rs-heatmap"></div>
        </section>
        <section class="desk-suite-card">
            <h3>窗口 / Trial</h3>
            <div id="rs-windows"></div>
        </section>
        <section class="desk-suite-card">
            <h3>实验库</h3>
            <div id="rs-experiments"></div>
        </section>`;
    }

    private input(name: string): HTMLInputElement | HTMLSelectElement
        | HTMLTextAreaElement | null {
        return this.element.querySelector(
            `[data-rs="${name}"]`) as HTMLInputElement | HTMLSelectElement
            | HTMLTextAreaElement | null;
    }

    private value(name: string): string {
        return String(this.input(name)?.value ?? '').trim();
    }

    private onClick(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        if (target.closest('[data-rs-run]')) {
            let params: Record<string, unknown> = {};
            const raw = this.value('params');
            if (raw) {
                try {
                    params = JSON.parse(raw);
                } catch {
                    window.alert('参数不是合法 JSON');
                    return;
                }
            }
            const metrics = ['metric0', 'metric1', 'metric2']
                .map((name) => this.value(name))
                .filter((name, index, all) => !!name && all.indexOf(name) === index)
                .slice(0, 3);
            this.options.onCommand('research_start', {
                mode: this.value('mode'), file: this.value('file'),
                data: this.value('data'), train: Number(this.value('train') || 240),
                test: Number(this.value('test') || 60),
                step: Number(this.value('step') || 0),
                metrics, metric: metrics[0] || 'profit_ratio',
                name: this.value('name'), params,
            });
            return;
        }
        if (target.closest('[data-rs-cancel]')) {
            this.options.onCommand('research_cancel', {});
            return;
        }
        if (target.closest('[data-rs-refresh]')) {
            this.options.onCommand('research', {});
            return;
        }
        const report = target.closest<HTMLElement>('[data-rs-report]');
        if (report) {
            this.options.onCommand('research_report', {
                experiment: Number(report.dataset.rsReport || 0),
            });
            return;
        }
        const drop = target.closest<HTMLElement>('[data-rs-delete]');
        if (drop) {
            if (!window.confirm('删除这个实验（含 trials）？')) return;
            this.options.onCommand('research_delete', {
                experiment: Number(drop.dataset.rsDelete || 0),
            });
            return;
        }
        const row = target.closest<HTMLElement>('[data-rs-select]');
        if (row) {
            this.selected = Number(row.dataset.rsSelect || 0);
            this.renderExperiments();
        }
    }

    apply(patch: Record<string, any>): void {
        if (patch.type === 'research_state' || patch.type === 'research') {
            const status = String(patch.status || this.data.status || 'idle');
            const statusBox = this.element.querySelector('#rs-status');
            if (statusBox) {
                const error = String(patch.error || this.data.error || '');
                statusBox.innerHTML = status === 'running'
                    ? `运行中… ${esc(this.data.progress_text || '')}`
                    : (error ? `<span class="warn">${esc(error)}</span>`
                        : `状态：${esc(status)}`);
            }
            if (patch.result) this.data.result = patch.result;
            if (patch.experiments) this.data.experiments = patch.experiments;
            if (patch.metrics) this.data.metricOptions = patch.metrics;
            if (patch.metric_directions) {
                this.data.metricDirections = patch.metric_directions;
            }
            if (patch.data_names) this.data.dataNames = patch.data_names;
            if (patch.status) this.data.status = patch.status;
            if (patch.error !== undefined) this.data.error = patch.error;
            this.fillSelectors();
            this.renderAll();
            return;
        }
        if (patch.type === 'research_progress') {
            this.data.progress_text = `${patch.current}/${patch.total} ${patch.text || ''}`;
            const statusBox = this.element.querySelector('#rs-status');
            if (statusBox) {
                statusBox.textContent = `运行中… ${this.data.progress_text}`;
            }
            return;
        }
        if (patch.type === 'research_error') {
            this.data.error = patch.message;
            const statusBox = this.element.querySelector('#rs-status');
            if (statusBox) {
                statusBox.innerHTML = `<span class="warn">${esc(patch.message)}</span>`;
            }
            return;
        }
        if (patch.type === 'research_result') {
            this.data.result = patch;
            this.data.status = 'ready';
            this.fillSelectors();
            this.renderAll();
        }
    }

    private fillSelectors(): void {
        const options = (this.data.metricOptions || []) as string[];
        if (options.length) {
            const previous = ['metric0', 'metric1', 'metric2'].map(
                (name) => this.value(name));
            ['metric0', 'metric1', 'metric2'].forEach((name, index) => {
                const select = this.input(name) as HTMLSelectElement | null;
                if (!select) return;
                const blank = index === 0 ? '' : '<option value="">（不使用）</option>';
                const chosen = previous[index] || (index === 0 ? 'profit_ratio' : '');
                select.innerHTML = blank + options.map((item) =>
                    `<option value="${esc(item)}">${esc(item)}</option>`).join('');
                select.value = options.includes(chosen) ? chosen
                    : (index === 0 ? (options.includes('profit_ratio')
                        ? 'profit_ratio' : options[0]) : '');
            });
        }
        const names = (this.data.dataNames || []) as string[];
        const list = this.element.querySelector('#rs-data-names');
        if (list) {
            list.innerHTML = names.map((name) =>
                `<option value="${esc(name)}"></option>`).join('');
        }
        const result = this.data.result || {};
        const heatOptions = (result.metrics || options) as string[];
        const heatSelect = this.input('heatMetric') as HTMLSelectElement | null;
        if (heatSelect && heatOptions.length) {
            const chosen = heatSelect.value || result.metric || heatOptions[0];
            heatSelect.innerHTML = heatOptions.map((item) =>
                `<option value="${esc(item)}">${esc(item)}</option>`).join('');
            heatSelect.value = heatOptions.includes(chosen) ? chosen : heatOptions[0];
        }
    }

    private renderHeatmap(): void {
        const result = this.data.result || {};
        const select = this.input('heatMetric') as HTMLSelectElement | null;
        const metric = select?.value || result.metric || 'profit_ratio';
        const heat = ((result.heatmaps || {}) as Record<string, any>)[metric]
            || result.heatmap || {};
        const title = this.element.querySelector('#rs-heat-title');
        if (title) {
            title.textContent = heat.x ? `${heat.x} × ${heat.y}` : '';
        }
        const heatBox = this.element.querySelector('#rs-heatmap');
        if (!heatBox) return;
        const xs = (heat.x_values || []) as string[];
        const ys = (heat.y_values || []) as string[];
        const grid = (heat.grid || []) as Array<Array<number | null>>;
        heatBox.innerHTML = xs.length && ys.length ? `
            <table class="desk-suite-table heatmap">
                <thead><tr><th>${esc(heat.y || '')} | ${esc(heat.x || '')}</th>${
                    xs.map((x) => `<th>${esc(x)}</th>`).join('')}</tr></thead>
                <tbody>${ys.map((y, yi) => `<tr><th>${esc(y)}</th>${
                    xs.map((_x, xi) => {
                        const value = grid[yi]?.[xi];
                        if (value === null || value === undefined) {
                            return '<td class="muted">—</td>';
                        }
                        const ratio = Math.max(-1, Math.min(1, value * 5));
                        const color = ratio >= 0
                            ? `rgba(38,166,154,${0.15 + ratio * 0.55})`
                            : `rgba(239,83,80,${0.15 + (-ratio) * 0.55})`;
                        return `<td style="background:${color}">${num(value, 4)}</td>`;
                    }).join('')}</tr>`).join('')}</tbody>
            </table>` : '<div class="desk-suite-empty">参数网格 / Walk-forward 结果会显示在这里。</div>';
    }

    private renderAll(): void {
        const result = this.data.result || {};
        const summaries = (result.summaries || (
            result.summary ? { [result.metric || 'profit_ratio']: result.summary } : {}
        )) as Record<string, Record<string, any>>;
        const directions = (this.data.metricDirections || {}) as Record<string, number>;
        const summaryBox = this.element.querySelector('#rs-summary');
        if (summaryBox) {
            const rows = Object.keys(summaries).map((name) => {
                const item = summaries[name] || {};
                const dir = directions[name] === -1 ? '越小越好' : '越大越好';
                return [
                    esc(name), `<span class="desk-muted">${dir}</span>`,
                    esc(item.count ?? 0), num(item.mean, 4), num(item.std, 4),
                    `${num((item.positive_rate || 0) * 100, 1)}%`,
                    num(item.worst, 4), num(item.best, 4),
                    num(stabilityScore(item, directions[name]), 1),
                ];
            });
            summaryBox.innerHTML = rows.length ? `
                <div class="desk-suite-kv">
                    <span>总稳定性 <b>${num(result.score, 1)}</b></span>
                    <span>指标 <b>${esc((result.metrics || []).join(' / '))}</b></span>
                </div>
                ${table(['指标', '方向', '样本', '均值', '标准差', '胜率', '最差', '最好', '稳定性'],
                    rows, '还没有结果')}`
                : '<div class="desk-suite-empty">跑一次 walk-forward / 网格就会出现。</div>';
        }
        const paretoBox = this.element.querySelector('#rs-pareto');
        if (paretoBox) {
            const rows = (result.pareto || []) as Array<Record<string, any>>;
            paretoBox.innerHTML = table(['#', '参数 / 窗口', '目标'],
                rows.map((row, index) => [
                    String(index + 1),
                    esc(JSON.stringify(row.params || row.name || row.window || {})),
                    esc(JSON.stringify(row._objectives || row.metrics || {})),
                ]), '没有可比较的结果');
        }
        this.renderHeatmap();
        const windows = (result.windows || result.grid_rows
            || result.batch_rows || []) as Array<Record<string, any>>;
        const winBox = this.element.querySelector('#rs-windows');
        if (winBox) {
            winBox.innerHTML = table(['#', '训练 / 数据', '测试 / 参数', '指标'],
                windows.map((row, index) => [
                    String(index + 1), esc(row.train || row.name || ''),
                    esc(row.test || JSON.stringify(row.params || {})),
                    esc(JSON.stringify(row.metrics || {})),
                ]), '还没有窗口结果');
        }
        this.renderExperiments();
    }

    private renderExperiments(): void {
        const experiments = (this.data.experiments || []) as Array<Record<string, any>>;
        const box = this.element.querySelector('#rs-experiments');
        if (!box) return;
        box.innerHTML = table(['ID', '名称', '模式', '分数', '创建', '操作'],
            experiments.map((row) => {
                const id = Number(row.id || 0);
                return [
                    `<button class="desk-suite-link" data-rs-select="${id}">#${id}</button>`,
                    esc(row.name || ''), esc(row.mode || ''),
                    num(row.score, 1), `<span class="desk-muted">${when(row.created)}</span>`,
                    `<button class="desk-suite-link" data-rs-report="${id}">报告</button>
                     <button class="desk-suite-link" data-rs-delete="${id}">删除</button>`,
                ];
            }), '实验库还是空的');
        if (this.selected) {
            const hit = experiments.find((row) => Number(row.id) === this.selected);
            if (hit && hit.windows) {
                const winBox = this.element.querySelector('#rs-windows');
                if (winBox) {
                    winBox.innerHTML = table(['#', '训练 / 数据', '测试 / 参数', '指标'],
                        (hit.windows as Array<Record<string, any>>).map((row, index) => [
                            String(index + 1), esc(row.train || row.name || ''),
                            esc(row.test || JSON.stringify(row.params || {})),
                            esc(JSON.stringify(row.metrics || {})),
                        ]), '这个实验没有窗口明细');
                }
            }
        }
    }
}

// ================================================================ 数据平台
export class DataPage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions;
    private theme: DeskTheme;

    constructor(options: PageOptions) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('data', this.theme, '本地数据平台',
            'CSV / Parquet 行情库：质检、重采样、主力换月复权、Tick 聚合、只读 SQL。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            this.onClick(event);
        });
    }

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-data theme-${theme}`;
    }

    private skeleton(): string {
        return `
        <section class="desk-suite-card">
            <div class="desk-suite-buttons">
                <button class="desk-tool primary" data-dh-refresh>扫描数据目录</button>
                <input data-dh="folder" class="desk-suite-input" placeholder="额外目录（可选）">
                <span class="desk-muted" id="dh-engine"></span>
            </div>
            <div id="dh-items"></div>
        </section>
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>质检 / 重采样 / Tick</h3>
                <div class="desk-suite-form">
                    <label>数据 name<input data-dh="name" placeholder="从上面选一个 name"></label>
                    <label>周期 rule<input data-dh="rule" value="5min"></label>
                    <label>Tick 秒数<input data-dh="seconds" type="number" value="60"></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool" data-dh-quality>数据质检</button>
                    <button class="desk-tool" data-dh-resample>重采样</button>
                    <button class="desk-tool" data-dh-ticks>Tick → K 线</button>
                    <button class="desk-tool" data-dh-export>导出 Parquet</button>
                </div>
                <div id="dh-quality"></div>
                <div id="dh-result"></div>
            </section>
            <section class="desk-suite-card">
                <h3>主力换月 / 复权</h3>
                <div class="desk-suite-form">
                    <label class="wide">合约 names<input data-dh="names" placeholder="rb2610, rb2701（按时间拼接）"></label>
                    <label>复权<select data-dh="mode">
                        <option value="ratio">比例</option>
                        <option value="difference">价差</option>
                        <option value="none">不复权</option>
                    </select></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-dh-roll>拼接连续合约</button>
                </div>
                <div id="dh-roll-result"></div>
            </section>
        </div>
        <section class="desk-suite-card">
            <h3>只读 SQL（DuckDB）</h3>
            <textarea data-dh="sql" rows="4" class="desk-suite-sql">SELECT * FROM ag2612_60 LIMIT 20</textarea>
            <div class="desk-suite-buttons">
                <button class="desk-tool primary" data-dh-query>执行 SELECT</button>
                <span class="desk-muted">只允许 SELECT / WITH；直接查文件名（非字母数字换成 _）</span>
            </div>
            <div id="dh-query"></div>
        </section>`;
    }

    private input(name: string): HTMLInputElement | HTMLSelectElement
        | HTMLTextAreaElement | null {
        return this.element.querySelector(
            `[data-dh="${name}"]`) as HTMLInputElement | HTMLSelectElement
            | HTMLTextAreaElement | null;
    }

    private value(name: string): string {
        return String(this.input(name)?.value ?? '').trim();
    }

    private onClick(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        if (target.closest('[data-dh-refresh]')) {
            this.options.onCommand('datahub_refresh',
                { folder: this.value('folder') });
            return;
        }
        if (target.closest('[data-dh-quality]')) {
            this.options.onCommand('datahub_quality', { name: this.value('name') });
            return;
        }
        if (target.closest('[data-dh-resample]')) {
            this.options.onCommand('datahub_resample',
                { name: this.value('name'), rule: this.value('rule') });
            return;
        }
        if (target.closest('[data-dh-ticks]')) {
            this.options.onCommand('datahub_ticks', {
                name: this.value('name'),
                seconds: Number(this.value('seconds') || 60),
            });
            return;
        }
        if (target.closest('[data-dh-roll]')) {
            this.options.onCommand('datahub_roll', {
                names: this.value('names'), mode: this.value('mode'),
            });
            return;
        }
        if (target.closest('[data-dh-export]')) {
            this.options.onCommand('datahub_export', { name: this.value('name') });
            return;
        }
        if (target.closest('[data-dh-query]')) {
            this.options.onCommand('datahub_query', { sql: this.value('sql') });
            return;
        }
        const pick = target.closest<HTMLElement>('[data-dh-pick]');
        if (pick) {
            const name = pick.dataset.dhPick || '';
            const input = this.input('name') as HTMLInputElement | null;
            if (input) input.value = name;
            this.options.onCommand('datahub_quality', { name });
            return;
        }
    }

    apply(patch: Record<string, any>): void {
        const type = String(patch.type || '');
        if (type === 'datahub') {
            const engine = this.element.querySelector('#dh-engine');
            if (engine) {
                engine.textContent = patch.duckdb
                    ? `DuckDB 已启用 · ${(patch.items || []).length} 个文件`
                    : `未安装 DuckDB（CSV/Parquet 仍可用）· ${(patch.items || []).length} 个文件`;
            }
            const items = (patch.items || []) as Array<Record<string, any>>;
            const box = this.element.querySelector('#dh-items');
            if (box) {
                box.innerHTML = table(['名称', '格式', '行数', '区间', '大小', ''],
                    items.map((row) => [
                        `<button class="desk-suite-link" data-dh-pick="${esc(row.name)}">${esc(row.name)}</button>`,
                        esc(row.format || ''),
                        row.error ? `<span class="warn">${esc(row.error)}</span>`
                            : num(row.rows, 0),
                        `<span class="desk-muted">${esc(row.from || '')}${
                            row.to ? ' → ' + esc(row.to) : ''}</span>`,
                        row.size ? `${(Number(row.size) / 1024).toFixed(0)} KB` : '',
                        esc(row.path || ''),
                    ]), '没有扫描到数据文件');
            }
            return;
        }
        if (type === 'datahub_quality') {
            const report = patch.report || {};
            const box = this.element.querySelector('#dh-quality');
            if (box) {
                box.innerHTML = `
                    <div class="desk-suite-kv">
                        <span>文件 <b>${esc(patch.name || '')}</b></span>
                        <span>分数 <b>${num(report.score, 1)}</b></span>
                        <span>行数 <b>${num(report.rows, 0)}</b></span>
                        <span>状态 <b>${report.ok ? '通过' : '有错误'}</b></span>
                    </div>
                    ${table(['级别', '问题', '数量', '说明'],
                        (report.issues || []).map((row: any) => [
                            esc(row.level || ''), esc(row.kind || ''),
                            esc(row.count ?? ''), esc(row.detail || ''),
                        ]), '没有发现问题')}`;
            }
            return;
        }
        if (type === 'datahub_result') {
            const bars = (patch.bars || []) as Array<Record<string, any>>;
            const first = bars[0] || {};
            const last = bars[bars.length - 1] || {};
            const box = this.element.querySelector(
                patch.action === 'roll' ? '#dh-roll-result' : '#dh-result');
            if (box) {
                box.innerHTML = `
                    <div class="desk-suite-kv">
                        <span>${esc(patch.action || '')}</span>
                        <span>根数 <b>${esc(patch.rows ?? bars.length)}</b></span>
                        <span>首根 <b>${esc(first.time || '')}</b></span>
                        <span>末根 <b>${esc(last.time || '')}</b></span>
                        <span>末收 <b>${num(last.close, 4)}</b></span>
                        ${patch.rule ? `<span>周期 <b>${esc(patch.rule)}</b></span>` : ''}
                        ${patch.seconds ? `<span>秒数 <b>${esc(patch.seconds)}</b></span>` : ''}
                    </div>`;
            }
            return;
        }
        if (type === 'datahub_query') {
            const box = this.element.querySelector('#dh-query');
            if (!box) return;
            if (!patch.ok) {
                box.innerHTML = `<div class="desk-suite-hint warn">${esc(patch.message || '查询失败')}</div>`;
                return;
            }
            const rows = (patch.rows || []) as Array<Record<string, any>>;
            const keys = rows.length ? Object.keys(rows[0]) : [];
            box.innerHTML = `${table(keys, rows.slice(0, 200).map(
                (row) => keys.map((key) => esc(row[key]))),
                '查询没有结果')}
                <div class="desk-suite-hint">${esc(patch.message || '')}（最多显示 200 行）</div>`;
        }
    }
}

// ================================================================ 告警中心
/** 告警中心（v1.3.7-97）：命中的告警做成**时间轴列表**，能回看 / 搜索 / 筛选 ✓
 *
 * 数据源：`ops.AlertLog`（SQLite `alerts_log.db`，保留 180 天）；
 * 每条包含 时间 / 等级 / 规则 / 标题 / 正文 / 发到哪些通道（含被静默压制的）。
 */
export class AlertLogPage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions & {
        /** 一键复现：打开某个合约的图表 ✓ v1.3.7-98 */
        onOpen?: (symbol: string) => void;
    };
    private theme: DeskTheme;
    private items: Array<Record<string, any>> = [];
    private stats: Record<string, any> = {};
    private catalog: Array<Record<string, any>> = [];
    private queryText = '';
    private level = '';
    private rule = '';
    private total = 0;
    private limit = 60;
    private daily: Array<Record<string, any>> = [];

    constructor(options: AlertLogPage['options']) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('alertlog', this.theme, '告警中心',
            '所有命中过的告警（含被静默压制的）：按时间倒序，可搜索 / 按等级或规则筛选。'
            + '记录保留 180 天。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            const target = event.target as HTMLElement;
            if (target.closest('[data-log-refresh]')) {
                this.reload();
                return;
            }
            if (target.closest('[data-log-clear]')) {
                this.options.onCommand('ops_alert_log_clear', {});
                return;
            }
            if (target.closest('[data-log-more]')) {
                this.limit += 60;
                this.reload();
            }
            // ★ 一键复现：点「打开图表」或整行 → 打开该合约 ✓
            const open = target.closest<HTMLElement>('[data-log-open]');
            if (open) {
                this.options.onOpen?.(String(open.dataset.logOpen || ''));
                return;
            }
            const row = target.closest<HTMLElement>('[data-log-row-symbol]');
            if (row) {
                this.options.onOpen?.(
                    String(row.dataset.logRowSymbol || ''));
            }
        });
        this.element.addEventListener('change', (event) => {
            const target = event.target as HTMLInputElement;
            if (target.matches('[data-log-level]')) {
                this.level = String(target.value || '');
                this.reload();
            }
            if (target.matches('[data-log-rule]')) {
                this.rule = String(target.value || '');
                this.reload();
            }
        });
        this.element.addEventListener('input', (event) => {
            const target = event.target as HTMLInputElement;
            if (!target.matches('[data-log-query]')) return;
            this.queryText = String(target.value || '');
            // 输入即搜（后端 LIKE，很轻）；节流 300ms 防连打 ✓
            window.clearTimeout(this._timer);
            this._timer = window.setTimeout(() => this.reload(), 300);
        });
        this.reload();
    }

    private _timer = 0;

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-alertlog theme-${theme}`;
        this.render();
    }

    private skeleton(): string {
        return `
        <div class="desk-suite-card">
            <div class="desk-suite-form">
                <label class="wide">搜索（标题 / 正文 / 规则）<input data-log-query placeholder="例如：拒单 / 保证金 / SHFE.ag"></label>
                <label>等级<select data-log-level>
                    <option value="">全部</option>
                    <option value="error">严重</option>
                    <option value="warning">重要</option>
                    <option value="info">一般</option>
                </select></label>
                <label>规则<select data-log-rule>
                    <option value="">全部</option>
                </select></label>
            </div>
            <div class="desk-suite-buttons">
                <button class="desk-tool primary" data-log-refresh>刷新</button>
                <button class="desk-tool danger" data-log-clear>清空记录</button>
                <span class="desk-suite-hint" id="op-log-stats"></span>
            </div>
            <div class="desk-suite-hint">近 14 天（柱高 = 条数，颜色 = 等级）</div>
            <div id="op-log-daily"></div>
            <div id="op-log-list"></div>
        </div>`;
    }

    apply(patch: Record<string, any>): void {
        if (patch.type !== 'ops_alert_log') return;
        this.items = (patch.items || []) as Array<Record<string, any>>;
        this.stats = patch.stats || {};
        if (Array.isArray(patch.daily)) this.daily = patch.daily;
        this.total = Number(patch.total || 0);
        if (Array.isArray(patch.catalog) && patch.catalog.length) {
            this.catalog = patch.catalog;
        }
        this.render();
    }

    private reload(): void {
        this.options.onCommand('ops_alert_log', {
            query: this.queryText, level: this.level, rule: this.rule,
            limit: this.limit, offset: 0,
        });
    }

    private render(): void {
        const ruleSelect = this.element
            .querySelector<HTMLSelectElement>('[data-log-rule]');
        if (ruleSelect) {
            const keep = this.rule;
            ruleSelect.innerHTML = '<option value="">全部</option>'
                + this.catalog.map((row) => `<option value="${esc(row.id)}">${
                    esc(row.label || row.id)}（${esc(row.source || '')}）`
                    + '</option>').join('');
            ruleSelect.value = keep;
        }
        const statsBox = this.element.querySelector('#op-log-stats');
        if (statsBox) {
            const byLevel = (this.stats.by_level || {}) as Record<string, number>;
            statsBox.textContent = `共 ${this.stats.total || 0} 条`
                + `　今天 ${this.stats.today || 0} 条`
                + `　严重 ${byLevel.error || 0} / 重要 ${byLevel.warning || 0}`
                + ` / 一般 ${byLevel.info || 0}`;
        }
        this.renderDaily();
        const box = this.element.querySelector('#op-log-list');
        if (!box) return;
        if (!this.items.length) {
            box.innerHTML = '<div class="desk-suite-empty">还没有告警记录'
                + '（规则命中后才会出现；去「设置 → 告警通道」看看开关）</div>';
            return;
        }
        // 按天分组 → 时间轴（v1.3.7-97 ✓）
        const groups = new Map<string, Array<Record<string, any>>>();
        for (const row of this.items) {
            const day = this._day(row.ts);
            if (!groups.has(day)) groups.set(day, []);
            groups.get(day)!.push(row);
        }
        let html = '';
        for (const [day, rows] of groups) {
            html += `<div class="desk-log-day">${esc(day)}`
                + `<span class="desk-muted">（${rows.length} 条）</span></div>`;
            for (const row of rows) {
                const level = String(row.level || 'info');
                const mark = level === 'error' ? '严重'
                    : (level === 'warning' ? '重要' : '一般');
                const time = new Date(Number(row.ts || 0) * 1000)
                    .toLocaleTimeString('zh-CN', { hour12: false });
                const channel = String(row.channel || '');
                const failed = row.ok === false ? ' fail' : '';
                const symbol = String(row.symbol || '');
                html += `<div class="desk-log-row ${level}${failed}"${
                    symbol ? ` data-log-row-symbol="${esc(symbol)}"`
                        + ' title="点击打开这个合约的图表"' : ''}>
                    <span class="desk-log-time">${esc(time)}</span>
                    <span class="desk-log-badge ${level}">${mark}</span>
                    <div class="desk-log-text">
                        <div class="desk-log-title">${esc(row.title || '')}</div>
                        ${row.text ? `<div class="desk-log-detail">${
                            esc(row.text)}</div>` : ''}
                        <div class="desk-log-meta">${esc(row.rule || '')}
                        ${channel ? `　·　${esc(channel)}` : ''}
                        ${symbol ? `　·　<button class="desk-suite-link"
                            data-log-open="${esc(symbol)}">打开图表 ${
                            esc(symbol)}</button>` : ''}</div>
                    </div>
                </div>`;
            }
        }
        if (this.items.length < this.total) {
            html += `<div class="desk-suite-buttons">
                <button class="desk-tool" data-log-more>加载更多（还有 ${
                    this.total - this.items.length} 条）</button></div>`;
        }
        box.innerHTML = html;
    }

    /** 近 14 天柱状图（按等级堆叠 + 数字；纯 DOM，跟主题走 ✓） */
    private renderDaily(): void {
        const box = this.element.querySelector('#op-log-daily');
        if (!box) return;
        const rows = this.daily || [];
        if (!rows.length) {
            box.innerHTML = '<div class="desk-suite-hint">还没有数据</div>';
            return;
        }
        const max = Math.max(1, ...rows.map((row) => Number(row.total || 0)));
        box.innerHTML = '<div class="desk-log-bars">'
            + rows.map((row) => {
                const total = Number(row.total || 0);
                const height = Math.round(total / max * 84);
                const parts: Array<[string, number]> = [
                    ['error', Number(row.error || 0)],
                    ['warning', Number(row.warning || 0)],
                    ['info', Number(row.info || 0)]];
                const stack = parts.filter((item) => item[1] > 0)
                    .map((item) => {
                        const seg = Math.max(2, Math.round(
                            item[1] / Math.max(1, total) * height));
                        return `<span class="seg ${item[0]}" style="height:${
                            seg}px"></span>`;
                    }).join('');
                const day = String(row.day || '').slice(5);
                return `<div class="desk-log-bar" title="${
                    esc(String(row.day || ''))}：共 ${total} 条（严重 ${
                    Number(row.error || 0)} / 重要 ${Number(row.warning || 0)}`
                    + ` / 一般 ${Number(row.info || 0)}）">
                    <div class="bar-stack" style="height:${
                        Math.max(height, total ? 3 : 0)}px">${stack}</div>
                    <div class="bar-count">${total || ''}</div>
                    <div class="bar-day">${esc(day)}</div>
                </div>`;
            }).join('') + '</div>';
    }

    private _day(ts: number): string {
        const date = new Date(Number(ts || 0) * 1000);
        return date.toLocaleDateString('zh-CN');
    }
}

// ================================================================ 定时任务
/** 定时任务（v1.3.7-88 从运维页独立出来 ✓）
 *
 * 触发（每 N 秒 / 每天 HH:MM / 前置任务成功后 / 仅手动）·
 * 动作（MCP 工具 / 多步串联 / AI 提示词 / 内置）· 保护（重试 / 补跑 / 推送 /
 * 休市日 / 交易时段）· 模板库 / 导入导出 / 执行历史 / 帮助面板。
 */
export class SchedulePage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions;
    private theme: DeskTheme;
    private data: Record<string, any> = {};

    constructor(options: PageOptions) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('schedule', this.theme, '定时任务',
            '定时把 MCP 工具 / AI 提示词 / 内置任务跑起来：每 N 秒、每天某时刻，'
            + '或「前置任务成功之后」。失败可重试、可推送微信 / 邮件。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            this.onClick(event);
        });
        // 选「动作 / 触发」时切换对应字段 ✓
        this.element.addEventListener('change', (event) => {
            const target = event.target as HTMLElement;
            if (target.closest('[data-op="taskAction"]')
                    || target.closest('[data-op="taskTrigger"]')) {
                this.syncTaskForm();
            }
            // ★ v1.3.7-86：选工具 → 参数框填骨架 + 下面显示参数说明 ✓
            if (target.closest('[data-op="taskTool"]')) {
                this.fillToolSkeleton();
            }
            if (target.closest('[data-op="taskBuiltin"]')) {
                this.renderBuiltinDoc();
            }
        });
    }

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-schedule theme-${theme}`;
    }

    private skeleton(): string {
        return `
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>定时任务 <span class="desk-suite-hint" style="font-weight:400">（每 N 秒 / 每天 HH:MM；动作 = MCP 工具 / AI 提示词 / 内置）</span></h3>
                <div class="desk-suite-form">
                    <label>名称<input data-op="taskName" placeholder="开盘简报"></label>
                    <label>动作<select data-op="taskAction">
                        <option value="tool">调 MCP 工具</option>
                        <option value="sequence">多步串联</option>
                        <option value="ai">发给 AI</option>
                        <option value="builtin">内置任务</option>
                    </select></label>
                    <label class="task-tool">工具<select data-op="taskTool"></select></label>
                    <label class="wide task-tool">工具参数（JSON：{"tool":"…","args":{…}}）<input data-op="taskArgs" placeholder='{"tool":"desk_news","args":{"refresh":true}}'></label>
                    <div class="wide task-tool desk-suite-doc" id="op-task-tool-doc"></div>
                    <div class="wide task-builtin desk-suite-doc" id="op-task-builtin-doc"></div>
                    <label class="wide task-seq">步骤（JSON 数组）<textarea data-op="taskSteps" rows="3" placeholder='[{"tool":"desk_news","args":{"refresh":true}},{"tool":"desk_calendar","args":{"days":2}}]'></textarea></label>
                    <label class="wide task-ai">提示词<input data-op="taskPrompt" placeholder="汇总自选与持仓 + 隔夜资讯，给今日关注点"></label>
                    <label class="task-builtin">内置<select data-op="taskBuiltin"></select></label>
                    <label>触发<select data-op="taskTrigger">
                        <option value="interval">每 N 秒</option>
                        <option value="daily">每天某时刻</option>
                        <option value="after">前置任务成功后</option>
                        <option value="manual">仅手动</option>
                    </select></label>
                    <label class="wide task-after">前置任务（逗号分隔，全部成功后跑）<input data-op="taskAfter" placeholder="资讯刷新,收盘复盘"></label>
                    <label class="wide task-depends">前置依赖（定时任务要求它们最近成功过）<input data-op="taskDepends" placeholder="资讯刷新"></label>
                    <label class="task-interval">间隔（秒）<input data-op="taskInterval" type="number" value="300"></label>
                    <label class="task-daily">时刻（HH:MM）<input data-op="taskAt" value="08:55" placeholder="08:55"></label>
                    <label class="task-daily">周几<select data-op="taskDays">
                        <option value="mon-fri">周一到周五</option>
                        <option value="everyday">每天</option>
                        <option value="weekend">周末</option>
                    </select></label>
                    <label class="inline"><input type="checkbox" data-op="taskEnabled"> 建好就启用</label>
                    <label class="inline"><input type="checkbox" data-op="taskSkipHoliday" checked> 跳过休市日</label>
                    <label class="inline"><input type="checkbox" data-op="taskSession"> 只在交易时段</label>
                    <label>失败重试<select data-op="taskRetries">
                        <option value="0">不重试</option>
                        <option value="1">1 次</option>
                        <option value="2">2 次</option>
                    </select></label>
                    <label>结果推送<select data-op="taskNotify">
                        <option value="error">只在失败时推送</option>
                        <option value="always">成功也推送</option>
                        <option value="never">不推送</option>
                    </select></label>
                    <label class="inline"><input type="checkbox" data-op="taskCatchUp"> 停机后补跑（6 小时内）</label>
                    <label class="inline task-ai"><input type="checkbox" data-op="taskWrite"> 允许 AI 改界面</label>
                    <label class="inline task-tool"><input type="checkbox" data-op="taskDanger"> 允许危险工具（下单/实盘）</label>
                    <label class="wide task-when">前置条件（JSON，可选）<input data-op="taskWhen" placeholder='{"tool":"desk_positions","path":"positions","op":"count","cmp":">","value":0}'></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-op-task-add>添加</button>
                    <button class="desk-tool" data-op-task-reset>清空表单</button>
                    <button class="desk-tool" data-op-task-run>立即跑到期任务</button>
                    <button class="desk-tool" data-op-holiday>标记 / 取消今天休市</button>
                    <button class="desk-tool" data-op-task-help title="看可用工具 / 内置任务的说明与使用场景">帮助 ?</button>
                    <select class="desk-tool" data-op="taskTemplate" title="从模板新建">
                        <option value="">从模板新建…</option>
                    </select>
                    <button class="desk-tool" data-op-task-template>用模板</button>
                    <button class="desk-tool" data-op-tasks-export>导出任务</button>
                    <button class="desk-tool" data-op-tasks-import>导入任务</button>
                </div>
                <div id="op-tasks"></div>
                <div id="op-task-history"></div>
                <div id="op-holidays"></div>
            </section>
        </div>`;
    }

    private input(name: string): HTMLInputElement | HTMLSelectElement | null {
        return this.element.querySelector(
            `[data-op="${name}"]`) as HTMLInputElement | HTMLSelectElement | null;
    }

    private value(name: string): string {
        return String(this.input(name)?.value ?? '').trim();
    }

    private checked(name: string): boolean {
        return !!(this.input(name) as HTMLInputElement | null)?.checked;
    }

    private onClick(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        if (target.closest('[data-op-task-add]')) {
            const payload = this.taskPayload();
            if (!payload.name) {
                this.options.onToast?.('warning', '先给任务起个名字');
                return;
            }
            this.options.onCommand(this.editingTask ? 'ops_task_update'
                : 'ops_task_add', payload);
            this.editingTask = '';
            return;
        }
        if (target.closest('[data-op-task-reset]')) {
            this.resetTaskForm();
            return;
        }
        if (target.closest('[data-op-task-run]')) {
            this.options.onCommand('ops_task_run', {});
            return;
        }
        if (target.closest('[data-op-holiday]')) {
            this.options.onCommand('ops_holidays', { action: 'toggle' });
            return;
        }
        if (target.closest('[data-op-tasks-import]')) {
            this.options.onCommand('ops_task_import', {});
            return;
        }
        if (target.closest('[data-op-task-help]')) {
            this.openHelp();
            return;
        }
        if (target.closest('[data-op-task-template]')) {
            const template = this.value('taskTemplate');
            if (!template) {
                this.options.onToast?.('warning', '先选一个模板');
                return;
            }
            this.options.onCommand('ops_task_template', { template });
            return;
        }
        if (target.closest('[data-op-tasks-export]')) {
            this.options.onCommand('ops_task_export', {});
            return;
        }
        const editTask = target.closest<HTMLElement>('[data-op-task-edit]');
        if (editTask) {
            this.editTask(editTask.dataset.opTaskEdit || '');
            return;
        }
        const execTask = target.closest<HTMLElement>('[data-op-task-exec]');
        if (execTask) {
            this.options.onCommand('ops_task_run',
                { name: execTask.dataset.opTaskExec || '' });
            return;
        }
        const toggle = target.closest<HTMLElement>('[data-op-task-toggle]');
        if (toggle) {
            this.options.onCommand('ops_task_toggle', {
                name: toggle.dataset.opTaskToggle || '',
                enabled: toggle.dataset.enabled !== '1',
            });
            return;
        }
        const drop = target.closest<HTMLElement>('[data-op-task-remove]');
        if (drop) {
            this.options.onCommand('ops_task_remove',
                { name: drop.dataset.opTaskRemove || '' });
        }
    }

    apply(patch: Record<string, any>): void {
        const type = String(patch.type || '');
        if (type === 'ops_task_export') {
            this.download('desk-tasks.json', String(patch.json || ''));
            this.options.onToast?.('success',
                `已导出 ${patch.count || 0} 个任务`);
            return;
        }
        if (type === 'ops_task_import_result') {
            const lines = [`新增 ${(patch.added || []).length} 个`,
                `跳过 ${(patch.skipped || []).length} 个`];
            if ((patch.failed || []).length) {
                lines.push(`失败 ${patch.failed.length} 个：${
                    (patch.failed || []).join('；')}`);
            }
            this.options.onToast?.((patch.failed || []).length ? 'warning'
                : 'success', lines.join('，'));
            return;
        }
        if (type === 'ops_catalog') {
            this.catalog = { tools: patch.tools || [],
                             builtins: patch.builtins || [] };
            const kind = this.value('taskAction');
            if (kind === 'tool') this.fillToolSkeleton();
            if (kind === 'builtin') this.renderBuiltinDoc();
            return;
        }
        if (type === 'ops_task_output') {
            const box = this.element.querySelector('#op-task-history');
            if (box) {
                box.insertAdjacentHTML('afterbegin',
                    `<div class="desk-suite-hint">${esc(patch.name || '')}`
                    + ` 的输出：<pre class="desk-suite-output">${
                        esc(String(patch.text || '').slice(0, 4000))}</pre></div>`);
            }
            return;
        }
        if (type === 'ops_holidays') {
            if (patch.tasks) this.data.tasks = patch.tasks;
            this.data.holidays = patch.days || [];
            this.renderHolidays();
            if (patch.tasks) this.renderTasks();
            return;
        }
        if (type === 'ops_tasks') {
            this.data.tasks = patch.tasks;
            this.renderTasks();
            const results = (patch.results || []) as Array<Record<string, any>>;
            const box = this.element.querySelector('#op-tasks');
            if (box && results.length) {
                box.insertAdjacentHTML('afterbegin', `<div class="desk-suite-hint">${
                    results.map((row) => `${esc(row.name)}: ${
                        row.ok ? 'OK' : '失败 ' + esc(row.error)}`).join('；')
                }</div>`);
            }
        }
    }

    private download(name: string, body: string): void {
        const blob = new Blob([body], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    }

    private renderTasks(): void {
        const data = this.data.tasks || {};
        const tasks = (data.tasks || []) as Array<Record<string, any>>;
        const box = this.element.querySelector('#op-tasks');
        if (box) {
            box.innerHTML = (data.enabled === false
                ? '<div class="desk-suite-hint warn">定时任务总开关是关的'
                  + '（设置 → 定时任务），任何任务都不会跑</div>' : '')
                + '<div class="desk-suite-table-wrap">'
                + table(['名称', '动作', '触发', '前置条件', '下次', '上次', '状态', '操作'],
                    tasks.map((row) => [
                        esc(row.name || ''), esc(this.taskActionText(row)),
                        esc(this.taskTriggerText(row)),
                        esc(this.whenText(row)),
                        row.enabled ? when(row.next_run) : '—',
                        row.last_run ? when(row.last_run) : '—',
                        // ★ v1.3.7-87：状态列只放**短文本**（长原因进 title），
                        //   否则整张表被撑到页面外 ✗
                        row.enabled
                            ? (row.last_status === 'error'
                                ? `<span class="desk-suite-state warn" title="${esc(row.last_error || '')}">失败</span>`
                                : (row.last_status === 'skipped'
                                    ? `<span class="muted" title="${esc(row.last_error || '')}">跳过</span>`
                                    : `<span class="desk-suite-state live">${esc(row.last_status || '待运行')}</span>`))
                            : `<span class="muted" title="${esc((row.disabled_reason || '') + ' ｜ ' + this.taskGuardText(row))}">已停用</span>`,
                        `<button class="desk-suite-link" data-op-task-exec="${esc(row.name)}">立即跑</button>
                 <button class="desk-suite-link" data-op-task-edit="${esc(row.name)}">编辑</button>
                 <button class="desk-suite-link" data-op-task-toggle="${esc(row.name)}" data-enabled="${row.enabled ? '1' : '0'}">${row.enabled ? '停用' : '启用'}</button>
                 <button class="desk-suite-link" data-op-task-remove="${esc(row.name)}">删除</button>`,
                    ]), '还没有任务')
                + '</div>';
        }
        const toolSelect = this.input('taskTool') as HTMLSelectElement | null;
        if (toolSelect && !toolSelect.options.length) {
            // ★ 后端快照带 tools；万一没带（老版本 / 别处的补丁）→ 用目录兜底 ✓
            const names = (data.tools && data.tools.length)
                ? data.tools
                : ((this.catalog.tools || []) as Array<Record<string, any>>)
                    .map((row) => row.name);
            toolSelect.innerHTML = names
                .map((name: string) => `<option value="${esc(name)}">${esc(name)}</option>`)
                .join('');
        }
        const templateSelect = this.input('taskTemplate') as HTMLSelectElement | null;
        if (templateSelect && templateSelect.options.length <= 1) {
            templateSelect.innerHTML = '<option value="">从模板新建…</option>'
                + (data.templates || []).map((row: Record<string, any>) =>
                    `<option value="${esc(row.name)}" title="${esc(row.desc || '')}">${
                        esc(row.name)}</option>`).join('');
        }
        const builtinSelect = this.input('taskBuiltin') as HTMLSelectElement | null;
        if (builtinSelect && !builtinSelect.options.length) {
            builtinSelect.innerHTML = (data.builtins || [])
                .map((name: string) => `<option value="${esc(name)}">${esc(name)}</option>`)
                .join('');
        }
        this.syncTaskForm();
        this.renderTaskHistory();
        this.renderHolidays();
        if (!this.catalogReady()) this.options.onCommand('ops_catalog', {});
        else {
            const kind = this.value('taskAction');
            if (kind === 'tool' && !this.value('taskArgs')) {
                this.fillToolSkeleton();
            }
            if (kind === 'builtin') this.renderBuiltinDoc();
        }
    }

    /** 目录（工具说明 / 参数 / 内置任务说明）由后端 `ops_catalog` 推一次 ✓ */
    private catalog: Record<string, any> = { tools: [], builtins: [] };

    private catalogReady(): boolean {
        return !!((this.catalog.tools || []).length);
    }

    private toolRow(name: string): Record<string, any> | null {
        return ((this.catalog.tools || []) as Array<Record<string, any>>)
            .find((row) => row.name === name) || null;
    }

    /** 选工具 → 参数框填「全部参数 + 默认值」的骨架 ✓ */
    private fillToolSkeleton(): void {
        const name = this.value('taskTool');
        const box = this.input('taskArgs');
        const doc = this.element.querySelector('#op-task-tool-doc');
        const row = this.toolRow(name);
        if (box && row?.skeleton) box.value = String(row.skeleton);
        if (!doc) return;
        if (!row) {
            doc.innerHTML = this.catalogReady() ? ''
                : '<span class="muted">正在读取工具说明…</span>';
            return;
        }
        const params = (row.params || []) as Array<Record<string, any>>;
        // ★ v1.3.7-94：名字一行、说明一行、每个参数两行（上下布局）；
        //   以前名字和解释挤在同一行，解释一长就完全没法看 ✗
        doc.innerHTML = `<div class="desk-suite-doc-head">${esc(row.name)}</div>`
            + `<div class="desk-suite-doc-line">${
                esc(row.description || '')}</div>`
            + (params.length
                ? params.map((item) => {
                    const def = item.default === '' || item.default === null
                        || item.default === undefined
                        ? '无默认（填空串）'
                        : `默认 ${JSON.stringify(item.default)}`;
                    return '<div class="desk-suite-doc-line">'
                        + `<code>${esc(item.name)}</code> `
                        + `<span class="muted">${esc(item.type || '')}`
                        + `${item.required ? ' · 必填' : ''}`
                        + ` · ${esc(def)}</span>`
                        + `<br>${esc(item.description || '')}</div>`;
                }).join('')
                : '<div class="desk-suite-doc-line muted">这个工具不需要参数，'
                  + '直接 {"tool":"' + esc(row.name) + '","args":{}} 就行</div>');
    }

    private renderBuiltinDoc(): void {
        const doc = this.element.querySelector('#op-task-builtin-doc');
        if (!doc) return;
        const name = this.value('taskBuiltin');
        const row = ((this.catalog.builtins || []) as Array<Record<string, any>>)
            .find((item) => item.name === name);
        if (!row) {
            doc.innerHTML = this.catalogReady() ? ''
                : '<span class="muted">正在读取内置任务说明…</span>';
            return;
        }
        doc.innerHTML = `<div class="desk-suite-doc-head">${
                esc(row.label || row.name)}（${esc(row.name)}）</div>`
            + `<div class="desk-suite-doc-line">${
                esc(row.description || '')}</div>`
            + `<div class="desk-suite-doc-line muted">什么时候用：${
                esc(row.usage || '—')}</div>`
            + `<div class="desk-suite-doc-line muted">参数：<code>${
                esc(row.payload || '{}')}</code>（内置任务不需要参数）</div>`;
    }

    /** 「帮助 ?」：列出所有 MCP 工具 + 内置任务的解释 / 参数 / 使用场景 ✓ */
    private openHelp(): void {
        const old = this.element.querySelector('.desk-suite-help');
        if (old) {
            old.remove();
            return;                      // 再点一次关掉 ✓
        }
        if (!this.catalogReady()) this.options.onCommand('ops_catalog', {});
        const mask = document.createElement('div');
        mask.className = 'desk-suite-help';
        const card = document.createElement('div');
        card.className = 'desk-suite-help-card';
        card.innerHTML = `<div class="desk-suite-help-head">
            <b>定时任务：可用工具与内置任务</b>
            <input class="desk-suite-help-search" placeholder="搜工具名 / 说明…">
            <button class="desk-tool" data-help-close>关闭</button></div>
            <div class="desk-suite-help-body"></div>`;
        mask.appendChild(card);
        const body = card.querySelector('.desk-suite-help-body') as HTMLElement;
        const search = card.querySelector<HTMLInputElement>(
            '.desk-suite-help-search');

        const render = (keyword = '') => {
            const word = keyword.trim().toLowerCase();
            const hit = (rows: Array<Record<string, any>>) => rows.filter((row) => {
                if (!word) return true;
                return `${row.name} ${row.description || ''} ${row.label || ''}`
                    .toLowerCase().includes(word);
            });
            const tools = hit((this.catalog.tools || []) as Array<
                Record<string, any>>);
            const builtins = hit((this.catalog.builtins || []) as Array<
                Record<string, any>>);
            body.innerHTML = `<h4>MCP 工具（${tools.length}）</h4>`
                + (tools.length ? tools.map((row) => {
                    const params = (row.params || []) as Array<Record<string, any>>;
                    return `<div class="desk-suite-help-row">
                        <div class="desk-suite-help-name"><code>${
                            esc(row.name)}</code></div>
                        <div class="desk-suite-help-desc">${
                            esc(row.description || '')}</div>
                        <div class="muted">参数：${params.length
                            ? params.map((item) => `${esc(item.name)}${
                                item.required ? '*' : ''}`).join(' / ')
                            : '无'}</div>
                        <div class="desk-suite-help-code">${esc(row.skeleton || '')}</div>
                    </div>`;
                }).join('') : '<div class="muted">没有匹配的工具</div>')
                + `<h4>内置任务（${builtins.length}）</h4>`
                + builtins.map((row) => `<div class="desk-suite-help-row">
                        <div class="desk-suite-help-name"><code>${
                            esc(row.name)}</code>
                        <b>${esc(row.label || '')}</b></div>
                        <div class="desk-suite-help-desc">${
                            esc(row.description || '')}</div>
                        <div class="muted">什么时候用：${esc(row.usage || '—')}</div>
                    </div>`).join('');
        };
        render('');
        search?.addEventListener('input', () => render(search?.value || ''));
        mask.addEventListener('click', (event) => {
            const node = event.target as HTMLElement;
            if (node === mask || node.closest('[data-help-close]')) mask.remove();
        });
        this.element.appendChild(mask);
    }

    private taskActionText(row: Record<string, any>): string {
        const action = row.action || {};
        if (action.kind === 'tool') return `工具 · ${action.tool || '?'}`;
        if (action.kind === 'sequence') {
            const count = (action.steps || []).length;
            return `多步 · ${count} 步`;
        }
        if (action.kind === 'ai') {
            return `AI · ${action.allow_write ? '可改界面' : '只读'}`;
        }
        return `内置 · ${action.name || '?'}`;
    }

    /** 保护项摘要（悬停看：重试 / 推送 / 回补 ✓） */
    private taskGuardText(row: Record<string, any>): string {
        const guard = row.guard || {};
        const parts: string[] = [];
        if (guard.retries) parts.push(`失败重试 ${guard.retries} 次`);
        if (row.notify && row.notify !== 'error') parts.push(`推送：${row.notify}`);
        if (guard.catch_up) parts.push('停机补跑');
        if (guard.max_errors) parts.push(`连续失败 ${guard.max_errors} 次自动停用`);
        return parts.join(' / ') || '默认保护';
    }

    /** 前置条件（`when`）显示成人话；老数据是字符串也照显示 ✓ */
    private whenText(row: Record<string, any>): string {
        const when = row.when;
        if (!when) return '—';
        if (typeof when === 'string') return when;
        if (!when.tool) return '—';
        const op = when.op === 'count' ? (when.cmp || '>') : (when.op || '>');
        const target = when.op === 'count'
            ? `${when.path || ''} 个数` : `${when.path || '值'}`;
        return `${when.tool} · ${target} ${op} ${when.value ?? ''}`;
    }

    private taskTriggerText(row: Record<string, any>): string {
        const trigger = row.trigger || {};
        if (trigger.kind === 'daily') {
            return `每天 ${trigger.at || '?'}（${trigger.days || 'everyday'}）`;
        }
        if (trigger.kind === 'manual') return '仅手动';
        if (trigger.kind === 'after') {
            return `前置成功后：${(trigger.after || []).join('、') || '？'}`;
        }
        const deps = (row.guard && row.guard.depends_on) || [];
        return deps.length
            ? `每 ${trigger.every || row.interval || 60}s ← ${deps.join('、')}`
            : `每 ${trigger.every || row.interval || 60}s`;
    }

    private renderTaskHistory(): void {
        const box = this.element.querySelector('#op-task-history');
        if (!box) return;
        const rows = ((this.data.tasks || {}).history || []) as Array<Record<string, any>>;
        if (!rows.length) {
            box.innerHTML = '';
            return;
        }
        box.innerHTML = `<div class="desk-suite-hint">执行历史（最近 ${
            rows.length} 条）</div><div class="desk-suite-table-wrap">`
            + table(['时间', '任务', '结果', '耗时', '摘要'], rows.map((row) => [
                when(row.at), esc(row.name || ''),
                row.skipped ? `跳过：${esc(row.skipped)}`
                    : (row.ok ? '<span class="desk-suite-state live">成功</span>'
                        : '<span class="desk-suite-state warn">失败</span>'),
                `${row.ms ?? 0}ms`,
                `<span class="desk-suite-cell" title="${
                    esc(String(row.error || row.summary || ''))}">${
                    esc(String(row.error || row.summary || '').slice(0, 60))}</span>`,
            ]), '') + '</div>';
    }

    private renderHolidays(): void {
        const box = this.element.querySelector('#op-holidays');
        if (!box) return;
        const days = ((this.data.tasks || {}).holidays
            || this.data.holidays || []) as string[];
        box.innerHTML = `<div class="desk-suite-hint">手工休市日（任务勾了「跳过休市日」就跳过）：${
            days.length ? days.map((day) => esc(day)).join('、') : '（无）'}</div>`;
    }

    // ---------------------------------------------------------- 表单
    private editingTask = '';

    private syncTaskForm(): void {
        const kind = this.value('taskAction');
        const trigger = this.value('taskTrigger');
        this.element.querySelectorAll('.task-tool').forEach((node) => {
            (node as HTMLElement).style.display = kind === 'tool' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-ai').forEach((node) => {
            (node as HTMLElement).style.display = kind === 'ai' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-seq').forEach((node) => {
            (node as HTMLElement).style.display = kind === 'sequence' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-after').forEach((node) => {
            (node as HTMLElement).style.display = trigger === 'after' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-when').forEach((node) => {
            (node as HTMLElement).style.display = kind === 'manual' ? 'none' : '';
        });
        this.element.querySelectorAll('.task-builtin').forEach((node) => {
            (node as HTMLElement).style.display = kind === 'builtin' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-interval').forEach((node) => {
            (node as HTMLElement).style.display = trigger === 'interval' ? '' : 'none';
        });
        this.element.querySelectorAll('.task-daily').forEach((node) => {
            (node as HTMLElement).style.display = trigger === 'daily' ? '' : 'none';
        });
    }

    private taskPayload(): Record<string, unknown> {
        const kind = this.value('taskAction');
        const trigger = this.value('taskTrigger');
        const payload: Record<string, unknown> = {
            name: this.value('taskName'),
            action_kind: kind,
            trigger_kind: trigger,
            interval: Number(this.value('taskInterval') || 300),
            at: this.value('taskAt') || '08:55',
            days: this.value('taskDays') || 'mon-fri',
            enabled: this.checked('taskEnabled'),
            skip_holidays: this.checked('taskSkipHoliday'),
            only_trading_hours: this.checked('taskSession'),
            after: this.value('taskAfter'),
            depends_on: this.value('taskDepends'),
            retries: Number(this.value('taskRetries') || 0),
            catch_up: this.checked('taskCatchUp'),
            notify: this.value('taskNotify') || 'error',
        };
        const whenRaw = this.value('taskWhen');
        if (whenRaw) payload.when = whenRaw;
        if (kind === 'tool') {
            payload.tool = this.value('taskTool');
            payload.args = this.value('taskArgs') || '{}';
            payload.allow_dangerous = this.checked('taskDanger');
        } else if (kind === 'sequence') {
            payload.steps = this.value('taskSteps') || '[]';
        } else if (kind === 'ai') {
            payload.prompt = this.value('taskPrompt');
            payload.allow_write = this.checked('taskWrite');
        } else {
            payload.builtin = this.value('taskBuiltin');
        }
        return payload;
    }

    private resetTaskForm(): void {
        const name = this.input('taskName');
        if (name) name.value = '';
        const prompt = this.input('taskPrompt');
        if (prompt) prompt.value = '';
        const args = this.input('taskArgs');
        if (args) args.value = '';
        const steps = this.input('taskSteps');
        if (steps) steps.value = '';
        const when = this.input('taskWhen');
        if (when) when.value = '';
        const after = this.input('taskAfter');
        if (after) after.value = '';
        const depends = this.input('taskDepends');
        if (depends) depends.value = '';
        this.editingTask = '';
        const button = this.element.querySelector('[data-op-task-add]');
        if (button) button.textContent = '添加';
    }

    private editTask(name: string): void {
        const tasks = ((this.data.tasks || {}).tasks || []) as Array<Record<string, any>>;
        const row = tasks.find((item) => String(item.name) === name);
        if (!row) return;
        const action = row.action || {};
        const trigger = row.trigger || {};
        const guard = row.guard || {};
        const set = (key: string, value: string) => {
            const node = this.input(key);
            if (node) node.value = value;
        };
        const check = (key: string, value: boolean) => {
            const node = this.input(key) as HTMLInputElement | null;
            if (node) node.checked = value;
        };
        set('taskName', String(row.name || ''));
        set('taskAction', String(action.kind || 'builtin'));
        set('taskTool', String(action.tool || ''));
        set('taskArgs', JSON.stringify(action.args || {}));
        set('taskPrompt', String(action.prompt || ''));
        set('taskSteps', action.steps ? JSON.stringify(action.steps) : '');
        set('taskWhen', row.when ? JSON.stringify(row.when) : '');
        set('taskBuiltin', String(action.name || ''));
        set('taskTrigger', String(trigger.kind || 'interval'));
        set('taskAfter', (trigger.after || []).join(','));
        set('taskDepends', (guard.depends_on || []).join(','));
        set('taskInterval', String(trigger.every || row.interval || 300));
        set('taskAt', String(trigger.at || '08:55'));
        set('taskDays', String(trigger.days || 'mon-fri'));
        check('taskEnabled', !!row.enabled);
        check('taskSkipHoliday', !!guard.skip_holidays);
        check('taskSession', !!guard.only_trading_hours);
        check('taskWrite', !!action.allow_write);
        check('taskDanger', !!action.allow_dangerous);
        check('taskCatchUp', !!guard.catch_up);
        set('taskRetries', String(guard.retries || 0));
        set('taskNotify', String(row.notify || 'error'));
        this.editingTask = name;
        this.syncTaskForm();
        const button = this.element.querySelector('[data-op-task-add]');
        if (button) button.textContent = '保存修改';
        this.options.onToast?.('info', `正在编辑：${name}（改完点「保存修改」）`);
    }

}

// ================================================================ 运维
export class OpsPage {
    public readonly element: HTMLDivElement;
    private readonly options: PageOptions;
    private theme: DeskTheme;
    private data: Record<string, any> = {};

    constructor(options: PageOptions) {
        this.options = options;
        this.theme = options.theme;
        this.element = shell('ops', this.theme, '平台 / 运维',
            'API Token、服务状态、策略版本回滚。'
            + '告警通道在「设置 → 系统设置 → 告警通道」，'
            + '定时任务在「＋ 新建 ▾ → 定时任务」。'
            + 'headless 服务用同一套 token。',
            this.skeleton());
        this.element.addEventListener('click', (event) => {
            this.onClick(event);
        });
    }

    show(): void { this.element.style.display = 'block'; }
    hide(): void { this.element.style.display = 'none'; }
    applyTheme(theme: DeskTheme): void {
        this.theme = theme;
        this.element.className = `desk-suite-page desk-suite-ops theme-${theme}`;
    }

    private skeleton(): string {
        return `
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>API Token</h3>
                <div class="desk-suite-form">
                    <label>名称<input data-op="tokenName" placeholder="ci / mobile"></label>
                    <label>scope<input data-op="tokenScopes" value="read" placeholder="read,trade,research,data,ops"></label>
                    <label>有效期（秒）<input data-op="tokenTtl" type="number" value="604800"></label>
                    <label class="inline">永久（0）<input data-op="tokenTtl0" type="checkbox"></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-op-token>生成 Token</button>
                    <button class="desk-tool danger" data-op-token-all>全部撤销</button>
                </div>
                <div id="op-token-out"></div>
                <div id="op-tokens"></div>
            </section>
        </div>
        <div class="desk-suite-grid">
            <section class="desk-suite-card">
                <h3>策略版本</h3>
                <div class="desk-suite-form">
                    <label class="wide">策略文件<input data-op="versionPath" placeholder="C:/.../my_strategy.py"></label>
                </div>
                <div class="desk-suite-buttons">
                    <button class="desk-tool primary" data-op-version-snapshot>保存快照</button>
                    <button class="desk-tool" data-op-version-list>列出</button>
                </div>
                <div id="op-versions"></div>
            </section>
        </div>
        <section class="desk-suite-card">
            <h3>服务状态</h3>
            <div id="op-status"></div>
        </section>`;
    }

    private input(name: string): HTMLInputElement | HTMLSelectElement | null {
        return this.element.querySelector(
            `[data-op="${name}"]`) as HTMLInputElement | HTMLSelectElement | null;
    }

    private value(name: string): string {
        return String(this.input(name)?.value ?? '').trim();
    }

    private checked(name: string): boolean {
        return !!(this.input(name) as HTMLInputElement | null)?.checked;
    }

    private onClick(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        if (target.closest('[data-op-token]')) {
            const ttl = this.checked('tokenTtl0') ? 0 : Number(this.value('tokenTtl') || 604800);
            this.options.onCommand('ops_token_issue', {
                name: this.value('tokenName') || 'api',
                scopes: this.value('tokenScopes') || 'read', ttl,
            });
            return;
        }
        if (target.closest('[data-op-token-all]')) {
            if (window.confirm('撤销全部 API Token？')) {
                this.options.onCommand('ops_token_revoke_all', {});
            }
            return;
        }
        const revoke = target.closest<HTMLElement>('[data-op-token-revoke]');
        if (revoke) {
            this.options.onCommand('ops_token_revoke',
                { id: revoke.dataset.opTokenRevoke || '' });
            return;
        }
        if (target.closest('[data-op-version-snapshot]')) {
            this.options.onCommand('ops_version_snapshot',
                { path: this.value('versionPath') });
            return;
        }
        if (target.closest('[data-op-version-list]')) {
            this.options.onCommand('ops_versions',
                { path: this.value('versionPath') });
            return;
        }
        const rollback = target.closest<HTMLElement>('[data-op-version-rollback]');
        if (rollback) {
            if (!window.confirm('回滚这个版本？当前文件会先自动备份。')) return;
            this.options.onCommand('ops_version_rollback', {
                path: this.value('versionPath'),
                version: rollback.dataset.opVersionRollback || '',
            });
        }
    }

    apply(patch: Record<string, any>): void {
        const type = String(patch.type || '');
        if (type === 'ops_token' && patch.token) {
            const box = this.element.querySelector('#op-token-out');
            if (box) {
                box.innerHTML = `<div class="desk-suite-token">
                    <span class="desk-muted">只显示一次：</span>
                    <code>${esc(patch.token.token || '')}</code></div>`;
            }
            return;
        }
        if (type === 'ops') {
            this.data = patch;
            this.render(patch);
            return;
        }
        if (type === 'ops_notify') {
            // 告警通道已搬到设置页（v1.3.7-91）→ 运维页只留数据，不再画 ✓
            if (patch.notify) this.data.notify = patch.notify;
            return;
        }
        if (type === 'ops_versions') {
            this.data.versions = patch.items || [];
            this.renderVersions();
        }
    }

    private render(patch: Record<string, any>): void {
        const status = patch.status || {};
        const statusBox = this.element.querySelector('#op-status');
        if (statusBox) {
            statusBox.innerHTML = table(['项', '值'], Object.keys(status).map(
                (key) => [esc(key), esc(JSON.stringify(status[key]))]),
                '还没有状态');
        }
        const tokens = (patch.tokens || []) as Array<Record<string, any>>;
        const tokenBox = this.element.querySelector('#op-tokens');
        if (tokenBox) {
            tokenBox.innerHTML = table(['名称', 'Scope', '创建', '过期', '最近使用', ''],
                tokens.map((row) => [
                    esc(row.name || ''),
                    esc((row.scopes || []).join(',')), when(row.created),
                    row.expires ? when(row.expires) : '永久',
                    row.last_used ? when(row.last_used) : '—',
                    row.revoked ? '<span class="muted">已撤销</span>'
                        : `<button class="desk-suite-link" data-op-token-revoke="${esc(row.id || '')}">撤销</button>`,
                ]), '还没有 token');
        }
        this.renderVersions();
    }

    private renderVersions(): void {
        const items = (this.data.versions || []) as Array<Record<string, any>>;
        const box = this.element.querySelector('#op-versions');
        if (!box) return;
        box.innerHTML = table(['版本', '说明', '时间', '大小', ''],
            items.map((row) => [
                esc(row.version || ''), esc(row.note || ''), when(row.at),
                `${num(Number(row.size || 0) / 1024, 1)} KB`,
                `<button class="desk-suite-link" data-op-version-rollback="${esc(row.version || '')}">回滚</button>`,
            ]), '还没有版本快照');
    }
}

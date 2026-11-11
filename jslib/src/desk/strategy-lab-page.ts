/**
 * StrategyLabPage — 策略回测 / 参数优化（P118+）。
 *
 * 入口在本地图表编辑器的「策略回测 / 参数优化」按钮；本页是**独立 tab**，
 * 原来的本地图表保持不变。退出时由 App 关闭本 tab，回到 source tab。
 *
 * 布局（二级 Tab）：
 *   图表 / 回测结果 / 交易记录 / 参数优化
 * 图表直接用 MiniQT 的原代码生成自包含 HTML，iframe 装载；desk 只负责
 * 二级 Tab、指标卡片、交易记录和参数优化表。
 */

import { closeMenu, showMenu } from './menu';
import { ICON_ERASER, ICON_PENCIL } from './icons';
import {
    axisRange, drawScene, drawTooltip, hitTestPoint, layoutPoints,
    normalizeValue, rad, shortNumber,
    type Camera, type LayoutPoint, type Point3 as Point3D,
} from './chart3d';

/** 优化目标最多几个（后端 `research.MAX_OPT_TARGETS` 同步 ✓） */
const OPT_TARGET_SLOTS = 9;
/** 帕累托前沿最多同时画几个轴（>2 走三维 ✓） */
const PARETO_AXES = 3;

export interface StrategyLabOptions {
    id: string;
    file: string;
    mode: 'backtest' | 'optimize';
    theme: 'light' | 'dark';
    sourceId?: string;
    onCommand: (cmd: string, payload?: Record<string, unknown>) => void;
    onExit: () => void;
    onToast: (level: string, text: string) => void;
    onWriteParams?: (params: Record<string, unknown>) => void;
    /** 图表字体大小（设置 → 图表配置 → `chart_font_size` ✓） */
    fontSize?: number;
    /** 鼠标十字线标签颜色（设置 → 图表颜色 → `chart_color_crosshair` ✓） */
    crosshairColor?: string;
}

interface StrategyRow {
    name: string;
    contracts: string[];
    metrics?: Record<string, number>;
}

interface ResultPayload {
    strategy?: string;
    metrics?: Record<string, number>;
    equity?: { times?: number[]; values?: number[]; drawdown?: number[] };
    pnl?: Array<[number, number]>;
    trade_style?: { show?: boolean; color?: string; width?: number;
                    dash?: string };
    contracts?: Array<{ symbol: string; trade_count?: number; bars?: number }>;
}

interface TradeRow {
    time?: number;
    direction?: string;
    symbol?: string;
    price?: number;
    qty?: number;
    fee?: number;
    equity?: number;
    pnl?: number;
}

const METRIC_GROUPS: Array<[string, Array<[string, string, string]>]> = [
    ['收益指标', [
        ['profit', '最终收益', 'money'], ['return_pct', '累计收益率', 'pct'],
        ['total_fee', '总手续费', 'money'], ['payoff_ratio', '盈亏比', 'num'],
        ['avg_return', '平均收益', 'num'], ['avg_win', '平均盈利', 'num'],
    ]],
    ['风险指标', [
        ['sharpe', '夏普比率', 'num'], ['drawdown', '最大回撤', 'pct'],
        ['var', '风险价值(VaR)', 'num'], ['risk_return', '风险收益比', 'num'],
    ]],
    ['交易指标', [
        ['winrate', '胜率', 'pct'], ['wins', '盈利次数', 'int'],
        ['losses', '亏损次数', 'int'], ['profit_ratio', '收益比率', 'num'],
        ['trades', '交易次数', 'int'], ['avg_loss', '平均亏损', 'num'],
    ]],
];

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

function num(value: unknown, digits = 2): string {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return '--';
    return parsed.toLocaleString('zh-CN', {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
}

function fmt(value: unknown, kind: string): string {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return '--';
    if (kind === 'money') return num(parsed, 2);
    if (kind === 'pct') return `${(parsed * 100).toFixed(2)}%`;
    if (kind === 'int') return String(Math.round(parsed));
    return num(parsed, 4);
}

function timeText(value: unknown): string {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return '--';
    return new Date(parsed * 1000).toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
    });
}

function equitySvg(equity: ResultPayload['equity']): string {
    const values = (equity?.values || []).map(Number);
    const drawdowns = (equity?.drawdown || []).map(Number);
    const count = Math.min(values.length, drawdowns.length);
    const pairs: Array<[number, number]> = [];
    for (let index = 0; index < count; index += 1) {
        const value = values[index];
        const drawdown = drawdowns[index];
        if (Number.isFinite(value) && Number.isFinite(drawdown)) {
            pairs.push([value, drawdown]);
        }
    }
    if (pairs.length < 2) {
        return '<div class="desk-strategy-empty">权益 / 回撤曲线暂不可用</div>';
    }

    const width = 1000;
    const height = 260;
    const left = 66;
    const right = 66;
    const top = 25;
    const bottom = 24;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const xAt = (index: number) => left + index * plotWidth / (pairs.length - 1);

    const equityValues = pairs.map(([value]) => value);
    const drawdownValues = pairs.map(([, value]) => value * 100);
    let equityMin = Math.min(...equityValues);
    let equityMax = Math.max(...equityValues);
    if (equityMax === equityMin) {
        equityMax += 1;
        equityMin -= 1;
    }
    let drawdownMin = Math.min(...drawdownValues, 0);
    let drawdownMax = Math.max(...drawdownValues, 0);
    if (drawdownMax === drawdownMin) {
        // 全 0 回撤：0% 放在顶部，避免整条线贴底
        if (drawdownMax === 0) drawdownMin = -1;
        else drawdownMax = drawdownMin + 1;
    }

    const yEquity = (value: number) =>
        top + (equityMax - value) / (equityMax - equityMin) * plotHeight;
    const yDrawdown = (value: number) =>
        top + (drawdownMax - value) / (drawdownMax - drawdownMin) * plotHeight;

    const pathFor = (series: number[], yAt: (value: number) => number) => {
        const points = series.map((value, index) => ({
            x: xAt(index), y: yAt(value),
        }));
        let line = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
        for (let index = 1; index < points.length; index += 1) {
            const previous = points[index - 1];
            const point = points[index];
            const mid = (previous.x + point.x) / 2;
            line += ` C${mid.toFixed(1)} ${previous.y.toFixed(1)},`
                + `${mid.toFixed(1)} ${point.y.toFixed(1)},`
                + `${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
        }
        return line;
    };

    const equityLine = pathFor(equityValues, yEquity);
    const drawdownLine = pathFor(drawdownValues, yDrawdown);
    const area = `${equityLine} L${xAt(pairs.length - 1).toFixed(1)}`
        + ` ${height - bottom} L${left} ${height - bottom} Z`;
    const ticks = [0, 1, 2, 3, 4];
    const grid = ticks.map((tick) => {
        const y = top + plotHeight * tick / 4;
        const equityValue = equityMax - (equityMax - equityMin) * tick / 4;
        const drawdownValue = drawdownMax
            - (drawdownMax - drawdownMin) * tick / 4;
        return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width - right}"
                y2="${y.toFixed(1)}" stroke="rgba(255,255,255,.07)" stroke-width="1"/>
            <text x="${left - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end"
                class="desk-eq-tick">${num(equityValue, 0)}</text>
            <text x="${width - right + 8}" y="${(y + 3).toFixed(1)}"
                text-anchor="start" class="desk-eq-tick">
                ${drawdownValue.toFixed(2)}%</text>`;
    }).join('');
    return `<svg class="desk-strategy-equity" viewBox="0 0 ${width} ${height}"
        preserveAspectRatio="none" aria-label="权益与回撤曲线">
        <defs><linearGradient id="desk-strategy-eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#38bdf8" stop-opacity=".25"/>
            <stop offset="1" stop-color="#38bdf8" stop-opacity="0"/>
        </linearGradient></defs>
        <g>${grid}</g>
        <line x1="${left}" y1="${height - bottom}" x2="${width - right}"
            y2="${height - bottom}" stroke="rgba(255,255,255,.14)" stroke-width="1"/>
        <path d="${area}" fill="url(#desk-strategy-eq)" stroke="none"/>
        <path d="${equityLine}" fill="none" stroke="#38bdf8" stroke-width="1.8"
            stroke-linecap="round" stroke-linejoin="round"
            vector-effect="non-scaling-stroke"/>
        <path d="${drawdownLine}" fill="none" stroke="#ef5350" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round"
            vector-effect="non-scaling-stroke"/>
        <text x="${left}" y="14" class="desk-eq-label"
            style="fill:#38bdf8">● 权益（左轴）</text>
        <text x="${width - right}" y="14" text-anchor="end"
            class="desk-eq-label" style="fill:#ef5350">● 回撤（右轴）</text>
    </svg>`;
}

import { showMenuBelow } from './menu';
import { REPLAY_SEEKS } from './replay';
import { openParamPopover } from './param-popover';

/** 图表类型（和看盘工具栏一致：蜡烛 / 收盘线 / 面积 / 柱 ✓） */
const CHART_KINDS: Array<{ key: string; label: string }> = [
    { key: 'candle', label: '蜡烛' },
    { key: 'line', label: '收盘线' },
    { key: 'area', label: '面积' },
    { key: 'bar', label: '柱（OHLC）' },
];

/** 回放速度档位（和 MiniQT `ReplayWindow` 一致 ✓） */
const REPLAY_SPEEDS = [1, 2, 5, 10];

/** 优化目标下拉的兜底列表（完整 73 个由后端 `strategy_state` 下发 ✓） */
const DEFAULT_OPT_TARGETS = [
    'profit_ratio', 'sharpe', 'sortino', 'calmar', 'omega',
    'max_drawdown', 'volatility', 'win_rate', 'profit_factor',
];

/** 优化设置的下拉兜底（完整列表由后端 `strategy_state` 下发 ✓） */
const DEFAULT_OPT_METHODS = ['grid', 'optuna', 'ga'];
const DEFAULT_OPT_SAMPLERS = ['NSGAIISampler', 'TPESampler', 'RandomSampler',
    'CmaEsSampler', 'QMCSampler', 'GridSampler'];
const DEFAULT_OPT_PRUNERS = ['HyperbandPruner', 'MedianPruner', 'NopPruner'];
const DEFAULT_OPT_NJOBS = [1, 2, 4, 8, -1];
const DEFAULT_OPT_WEIGHTS = [1, 2, 0.5, -0.5, -1, -2];

/** 参数网格的一行（前端编辑 → `param_space` 字典发回后端 ✓） */
interface OptParamRow {
    name: string;
    kind: 'range' | 'list' | 'fixed';
    low: string;
    high: string;
    step: string;
    list: string;
    value: string;
}

const METHOD_LABELS: Record<string, string> = {
    '': '跟随默认', grid: '网格搜索 grid', optuna: '贝叶斯 optuna',
    ga: '遗传算法 ga',
};

// ---- 回放图标（SVG，和看盘工具栏同一套观感 ✓）----
/** 回放开关：**和看盘窗口工具栏（预警后面）同一个 rewind 图标** ✓ */
const REPLAY_ICON = `<svg width="14" height="14" viewBox="0 0 16 16"
    aria-hidden="true"><g fill="currentColor" stroke="none">
    <path d="M1.5 3 L1.5 13 L7.5 8 Z"/><path d="M8 3 L8 13 L14 8 Z"/>
    </g></svg>`;
const REPLAY_PLAY_ICON = `<svg width="13" height="13" viewBox="0 0 24 24"
    fill="currentColor"><path d="M7 4l13 8-13 8z"/></svg>`;
const REPLAY_PAUSE_ICON = `<svg width="13" height="13" viewBox="0 0 24 24"
    fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect
    x="14" y="4" width="4" height="16"/></svg>`;
const REPLAY_STEP_ICON = `<svg width="13" height="13" viewBox="0 0 24 24"
    fill="currentColor"><path d="M5 4l10 8-10 8z"/><rect x="16" y="4"
    width="3" height="16"/></svg>`;
const REPLAY_EXIT_ICON = `<svg width="13" height="13" viewBox="0 0 24 24"
    fill="currentColor"><path d="M2 4l8 8-8 8z"/><path d="M11 4l8 8-8 8z"/></svg>`;

export class StrategyLabPage {
    public readonly element: HTMLDivElement;
    public readonly id: string;
    public readonly file: string;
    public readonly mode: 'backtest' | 'optimize';
    public readonly sourceId: string;

    private readonly options: StrategyLabOptions;
    private readonly chartFrame: HTMLIFrameElement;
    private readonly resultFrame: HTMLIFrameElement;
    private readonly body: HTMLDivElement;
    private readonly tabs: HTMLDivElement;
    private readonly panels: Record<string, HTMLDivElement> = {};
    private readonly status: HTMLSpanElement;
    private strategies: StrategyRow[] = [];
    private contractTabs: Array<{ key: string; strategy: string;
                                  contract: string; label: string }> = [];
    private active = 'chart';
    private currentResult: ResultPayload = {};
    private frameKey = '';
    private resultKey = '';
    private readonly fileMode = window.location.protocol === 'file:';
    private readonly chartFiles = new Map<string, string>();
    private trades: TradeRow[] = [];
    private optRows: Array<Record<string, any>> = [];
    private optSelected = 0;
    private optFilter = '';
    private optSortKey = '';
    private optSortDir = 1;
    private optChartMode: 'pareto' | 'rank' | 'importance' = 'pareto';
    /** 帕累托前沿选中的轴（1~3 个指标名；空 = 自动取前 3 个 ✓） */
    private optParetoAxes: string[] = [];
    /** 三维图的相机角度（拖动旋转后记住 ✓） */
    private optCamera: Camera = { yaw: rad(-35), pitch: rad(22) };
    /** 当前优化目标 / 权重 / 可选目标（由 `strategy_state` 下发 ✓） */
    private optTargets: string[] = [];
    private optWeights: number[] = [];
    private targetOptions: string[] = [];
    /** 优化设置（method / n_jobs / n_trials / sampler / pruner，空 = 跟随默认） */
    private optOptions: Record<string, any> = {
        method: '', n_jobs: 0, n_trials: 0, sampler: '', pruner: '',
    };
    /** 参数网格（前端可增删改；留空 = 用策略 / 指标的 params ✓） */
    private optParamSpace: OptParamRow[] = [];
    private optParamOptions: string[] = [];
    private optMethodOptions: string[] = [];
    private optSamplerOptions: string[] = [];
    private optPrunerOptions: string[] = [];
    private optNJobsOptions: number[] = [];
    private optWeightOptions: number[] = [];
    private running = false;
    private initialReady = false;
    /** 图表工具栏状态（由 iframe 里的驱动回传 ✓） */
    private chartTools: HTMLDivElement | null = null;
    /** 左上角标签字号（跟设置里的 `chart_font_size` 走 ✓） */
    private fontSize = 13;
    /** 鼠标十字线 X/Y 轴标签颜色（跟 `chart_color_crosshair` 走 ✓） */
    private crosshairColor = '';
    /** 图表设置状态：`replay / playing / kind / toolbox` 由**本页**决定，
     *  `bars / total` 由 iframe 回报（两个图表要一起播放 / 一起暂停 ✓） */
    private toolState = {
        kind: 'candle', toolbox: false, replay: false, playing: false,
        bars: 0, total: 0, speed: 1,
    };
    /** 回放时钟**由本页统一驱动**（两个图表永远同一根，不会各跑各的 ✓） */
    private replayTimer: number | undefined;
    /** 底部回放条（整个图表下方 ✓） */
    private replayBar: HTMLDivElement | null = null;
    private replayPlayButton: HTMLButtonElement | null = null;
    private replayLabel: HTMLSpanElement | null = null;
    private readonly onFrameMessage = (event: MessageEvent) => {
        const data = (event.data || {}) as Record<string, unknown>;
        const fromChartFrame = event.source === this.chartFrame.contentWindow;
        // 图表右键菜单（iframe 里 preventDefault 后交给父页面弹 ✓）
        if (data && data.__deskSL === 'chartMenu') {
            const fromChart = fromChartFrame;
            const frame = fromChart ? this.chartFrame : this.resultFrame;
            this._showChartMenu(frame, Number(data.x) || 0, Number(data.y) || 0);
            return;
        }
        // iframe 内左键 / 滚轮 → 收起右键菜单 ✓
        if (data && data.__deskSL === 'chartMenuClose') {
            closeMenu();
            return;
        }
        // 图表截图：iframe 里 `takeScreenshot()` → dataURL → 后端落盘 ✓
        if (data && data.__deskSL === 'screenshotData') {
            const url = String((data as Record<string, unknown>).dataUrl || '');
            if (!url) {
                this.options.onToast('warning', '截图失败（图表还没渲染好）');
                return;
            }
            this.options.onCommand('screenshot', { dataUrl: url });
            return;
        }
        if (data && data.__deskSL === 'screenshotFail') {
            this.options.onToast('warning', '当前图表暂不支持截图');
            return;
        }
        if (data && data.__deskSL === 'indicatorMenu') {
            this._onIndicatorMenu(data.data as {
                series?: string; kind?: string; payload?: Record<string, any>;
            });
            return;
        }
        if (!data || data.__deskSL !== 'state') return;
        const source = event.source as Window | null;
        const fromChart = source === this.chartFrame.contentWindow;
        const fromResult = source === this.resultFrame.contentWindow;
        if (!fromChart && !fromResult) return;
        const bars = Number(data.bars) || 0;
        const total = Number(data.total) || 0;
        if (total) this.toolState.total = total;
        // 图表驱动回报的开关状态 → 工具栏按钮的高亮 / 再点隐藏都靠它 ✓
        if (typeof data.toolbox === 'boolean') {
            this.toolState.toolbox = data.toolbox;
        }
        if (typeof data.kind === 'string' && data.kind) {
            this.toolState.kind = data.kind;
        }
        if (bars > this.toolState.bars) this.toolState.bars = bars;
        if (this.toolState.total && this.toolState.bars >= this.toolState.total) {
            // 放到最后一根 → 自动停（两个图表都是）✓
            this.toolState.playing = false;
            this._stopReplayClock();
        }
        const frame = fromResult ? this.resultFrame : this.chartFrame;
        // 两个图表「同进同退」：哪个掉队就把它拉回来 ✓
        if (this.toolState.replay && !data.replay) {
            this._post(frame, 'replayStart', { bars: this.toolState.bars });
        } else if (!this.toolState.replay && data.replay) {
            this._post(frame, 'replayExit', {});
        }
        this._renderChartTools();
        this._renderReplayBar();
    };

    constructor(options: StrategyLabOptions) {
        this.options = options;
        this.crosshairColor = String(options.crosshairColor || '');
        this.id = options.id;
        this.file = options.file;
        this.mode = options.mode;
        this.sourceId = options.sourceId || '';

        this.element = document.createElement('div');
        this.element.className = 'desk-strategy-lab';
        // ★ 右键：本页（工具栏 / 指标卡 / 记录表 / 优化表…）**禁用原生菜单**；
        //   图表 iframe 在自己的文档里 preventDefault 后回调 `chartMenu` ✓
        this.element.addEventListener('contextmenu', (event) => {
            const target = event.target as HTMLElement | null;
            // 输入框 / 下拉 / 可编辑区保留原生菜单（复制粘贴要用 ✓）
            if (target?.closest('input, textarea, select,'
                + ' [contenteditable="true"], .cm-editor')) return;
            event.preventDefault();
        });
        this.element.innerHTML = `
            <div class="desk-strategy-head">
                <div class="desk-strategy-title">
                    <span class="eyebrow">STRATEGY LAB</span>
                    <b>${options.mode === 'optimize' ? '参数优化' : '策略回测'}</b>
                    <span class="file">${esc(options.file.split(/[\\/]/).pop() || '')}</span>
                </div>
                <div class="desk-strategy-head-right">
                    <span class="desk-strategy-progress" data-progress>
                        <i></i><em></em>
                    </span>
                    <span class="status" data-status>准备中…</span>
                    <button class="desk-strategy-exit" data-exit>退出${options.mode === 'optimize' ? '参数优化' : '回测'}</button>
                </div>
            </div>
            <div class="desk-strategy-tabs" data-tabs></div>
            <div class="desk-strategy-body" data-body></div>`;
        this.body = this.element.querySelector('[data-body]') as HTMLDivElement;
        this.tabs = this.element.querySelector('[data-tabs]') as HTMLDivElement;
        this.status = this.element.querySelector('[data-status]') as HTMLSpanElement;

        this.chartFrame = document.createElement('iframe');
        this.chartFrame.className = 'desk-strategy-iframe desk-strategy-chart';
        this.chartFrame.title = '合约图表';
        this.chartFrame.style.display = 'none';
        this.body.appendChild(this.chartFrame);

        this.resultFrame = document.createElement('iframe');
        this.resultFrame.className = 'desk-strategy-iframe desk-strategy-result-chart';
        this.resultFrame.title = '回测结果图表';
        this.resultFrame.style.display = 'none';

        // ★ 回测中 / 参数优化中：iframe 还没装图表 → 先给**跟随主题**的
        //   占位页（以前什么都不显示 → 只剩 CSS 里的 #000 黑底，浅色主题下
        //   整个图表区一片黑，用户实测 ✗）
        this._setPlaceholder(this.chartFrame);
        this._setPlaceholder(this.resultFrame);

        this.fontSize = Math.max(9, Math.min(28,
            Number(options.fontSize) || 13));
        this._buildPanels();
        this._bind();
        window.addEventListener('message', this.onFrameMessage);
        this._buildTabs();
        this._showTab('chart');
    }

    // ------------------------------------------------------------- lifecycle
    show(): void {
        this.element.style.display = 'flex';
        this._showTab(this.active);
    }

    hide(): void {
        this.element.style.display = 'none';
    }

    /** 设置 → 图表配置「图表字体大小」/「鼠标标签颜色」同步到两个图表 ✓ */
    setChartConfig(values: Record<string, unknown>): void {
        if (!values) return;
        if ('chart_font_size' in values) {
            const size = Math.max(9, Math.min(28,
                Number(values.chart_font_size) || 13));
            if (size !== this.fontSize) {
                this.fontSize = size;
                this._postFrames('font', { size });
            }
        }
        if ('chart_color_crosshair' in values) {
            this.crosshairColor = String(values.chart_color_crosshair || '');
            this._postFrames('crosshair', { color: this.crosshairColor });
        }
    }

    applyTheme(theme: 'light' | 'dark'): void {
        if (theme === this.options.theme) return;
        this.options.theme = theme;
        this.frameKey = '';
        this.resultKey = '';
        this.chartFiles.clear();
        this._refreshPlaceholders();
        this._loadChartFrame(this.active === 'result' ? 'result' : this.active);
    }

    destroy(): void {
        this._stopReplayClock();
        window.removeEventListener('message', this.onFrameMessage);
        this.element.remove();
    }

    get sourceTabId(): string { return this.sourceId; }

    private _buildTabs(): void {
        const contracts = this.contractTabs.length ? this.contractTabs
            : [{ key: 'chart', label: '图表', strategy: '', contract: '' }];
        const items: Array<[string, string]> = contracts.map((item) =>
            [item.key, item.label]);
        items.push(['result', '回测结果'], ['record', '指标/记录']);
        if (this.mode === 'optimize') items.push(['optimize', '参数优化']);
        // ★ 回放按钮放进**页签行末尾**（看盘窗口工具栏同款图标）：
        //   回测页在「指标/记录」之后，优化页在「参数优化」之后 ✓
        const replay = `<button class="desk-tool desk-tool-replay${
            this.toolState.replay ? ' on' : ''}" data-sl="replay"
                title="${this.toolState.replay
                    ? '退出回放（恢复全部数据）'
                    : '回放：逐根放出策略信号'}">${REPLAY_ICON}</button>`;
        this.tabs.innerHTML = '<div class="desk-strategy-tablist">'
            + items.map(([key, label]) =>
                `<button class="desk-strategy-tab${key === this.active ? ' on' : ''}"
                    data-tab="${esc(key)}">${esc(label)}</button>`).join('')
            + replay
            + '</div><div class="desk-strategy-charttools" data-charttools></div>';
        this.chartTools = this.tabs.querySelector(
            '[data-charttools]') as HTMLDivElement | null;
        this._renderChartTools();
    }

    /**
     * 右侧图表设置：`回放 / 图表类型 / 画线工具 / 删除画线工具`
     *
     * 这些动作都发给 iframe 里的 `__deskSL` 驱动（图表是 MiniQT 生成的 HTML，
     * 由 `miniqt_backtest_chart.DESK_DRIVER_JS` 提供 API ✓）。
     *
     * ★ 「画线工具 / 删除画线工具」改用**图标**（铅笔 / 橡皮擦，和看盘窗口工具栏
     *   同一套 `ICON_PENCIL` / `ICON_ERASER`）：文字太宽、把页签行挤满
     *   （2026-10-30 用户要求 ✓），名称保留在 `title` / `aria-label` 里。
     */
    private _renderChartTools(): void {
        const host = this.chartTools;
        if (host) this._syncReplayTabButton();
        if (!host) return;
        const state = this.toolState;
        const kindLabel = CHART_KINDS.find((item) => item.key === state.kind)
            ?.label || '蜡烛';
        const iconBar = (key: string, icon: string, title: string,
                         on = false) => `<button
                class="desk-sl-btn desk-sl-icon${on ? ' on' : ''}"
                data-sl="${key}" title="${esc(title)}"
                aria-label="${esc(title)}">${icon}</button>`;
        // 回放按钮在**页签行**上（见 `_buildTabs`）→ 这里只放图表设置 ✓
        host.innerHTML = `<button class="desk-sl-btn" data-sl="kind"
                    title="图表类型">${esc(kindLabel)} ▾</button>`
            + iconBar('toolbox', ICON_PENCIL,
                '画线工具（显示 / 隐藏画线工具箱）', state.toolbox)
            + iconBar('clear', ICON_ERASER, '删除画线工具（清空图上所有画线）');
    }

    /**
     * 合约图表 / 回测结果图表的**右键菜单**（2026-11-02 用户要求）✓
     *
     * 菜单项：`全部K线` / `最新K线（300根）` / `画线` / `清除画线` / `截图`
     * —— 全部通过 postMessage 发给 iframe 里的 `__deskSL` 驱动执行。
     */
    private _showChartMenu(frame: HTMLIFrameElement, x: number,
                           y: number): void {
        const box = frame.getBoundingClientRect();
        const anchorX = box.left + x;
        const anchorY = box.top + y;
        const send = (cmd: string, payload: Record<string, unknown> = {}): void => {
            this._post(frame, cmd, payload);
        };
        showMenu(anchorX, anchorY, [
            { label: '全部K线', run: () => send('fitAll') },
            { label: '最新K线（300根）', run: () => send('visibleLast', { bars: 300 }) },
            { label: '画线', run: () => {
                this.toolState.toolbox = true;
                send('toolbox', { show: true });
                this._renderChartTools();
            } },
            { label: '清除画线', run: () => send('clearDrawings') },
            { label: '截图', run: () => send('screenshot') },
        ]);
    }

    /** 进回放时要放出的根数（默认**末尾 30%**，`total` 未知时给 0 ✓） */
    private _initialSeekBars(fraction = 0.3): number {
        const total = Number(this.toolState.total) || 0;
        if (!total) return 0;
        return Math.max(1, Math.round(total * fraction));
    }

    /** 页签行上的回放按钮：回放中高亮 ✓ */
    private _syncReplayTabButton(): void {
        const button = this.tabs.querySelector<HTMLElement>(
            '.desk-strategy-tablist [data-sl="replay"]');
        if (!button) return;
        button.classList.toggle('on', this.toolState.replay);
        button.title = this.toolState.replay
            ? '退出回放（恢复全部数据）' : '回放：逐根放出策略信号';
    }

    /** 右侧图表设置的动作（回放 / 图表类型 / 画线工具 / 删除画线 ✓） */
    private _onChartTool(action: string, anchor: HTMLElement): void {
        switch (action) {
            case 'replay':
                this.toolState.replay = !this.toolState.replay;
                this.toolState.playing = false;
                // ★ 默认截到 **末尾 30%**（和看盘窗口 `seek: 0.3` 一致）：
                //   以前传空 payload → 驱动给 0 根 = 全部数据 → 点播放看不
                //   出变化（用户实测"点播放不动"✗）
                const seek = this._initialSeekBars();
                this.toolState.bars = this.toolState.replay ? seek : 0;
                this._stopReplayClock();
                this._postFrames(this.toolState.replay
                    ? 'replayStart' : 'replayExit',
                    this.toolState.replay ? { bars: seek } : {});
                // ★ 页签行上的按钮 / 底部回放条都要跟着变（优化页也要 ✓）
                this._buildTabs();
                this._syncReplayTabButton();
                this._renderReplayBar();
                break;
            case 'play':
                this.toolState.replay = true;
                this.toolState.playing = true;
                this._startReplayClock();
                break;
            case 'pause':
                this.toolState.playing = false;
                this._stopReplayClock();
                break;
            case 'step':
                this.toolState.playing = false;
                this._stopReplayClock();
                this._postFrames('replayStep', {});
                break;
            case 'replayExit':
                this.toolState.replay = false;
                this.toolState.playing = false;
                this._stopReplayClock();
                this._postFrames('replayExit', {});
                break;
            case 'toolbox':
                // ★ 先更新本地状态再发；否则第二次点击仍看到 `false` → 又发
                //   `show: true`，工具箱永远藏不起来（用户实测 ✗）
                this.toolState.toolbox = !this.toolState.toolbox;
                this._postFrames('toolbox', { show: this.toolState.toolbox });
                this._renderChartTools();
                break;
            case 'clear':
                this._postFrames('clearDrawings', {});
                this.options.onToast('info', '已删除图上所有画线');
                break;
            case 'kind':
                showMenuBelow(anchor, CHART_KINDS.map((item) => ({
                    label: `${item.label}${item.key === this.toolState.kind
                        ? '  ✓' : ''}`,
                    run: () => this._postFrames('type', { kind: item.key }),
                })));
                break;
            default:
                break;
        }
        void anchor;
    }

    /**
     * 回放条（**整个图表的下方**，复刻看盘窗口的底部工具条 ✓）
     *
     * 从左到右：``[选择策略 ▾] [▶] [↦] [1x ▾] 已暂停 · 3051/10000（31%） [▶▶]``
     *
     * 和看盘窗口的区别（用户要求 ✓）：
     * * 「选择K线」→ **选择策略**（这里的标的本来就是策略，不是合约）；
     * * 二级菜单「选择合约」→ **选择策略**（按策略名切）；
     * * 「选择时间段」保留；**周期按钮删除**（回测结果固定周期 ✓）。
     */
    private _ensureReplayBar(): void {
        if (this.replayBar) return;
        const bar = document.createElement('div');
        bar.className = 'desk-replay-bar';

        // ① 选择策略 ▾（策略 / 时间段）
        const select = document.createElement('button');
        select.className = 'desk-tool desk-tool-arrow';
        select.title = '选择策略（策略 / 时间段）';
        const selectLabel = document.createElement('span');
        selectLabel.className = 'desk-tool-label';
        selectLabel.textContent = '选择策略';
        const selectCaret = document.createElement('span');
        selectCaret.className = 'desk-tool-caret';
        selectCaret.textContent = '▾';
        select.append(selectLabel, selectCaret);
        select.addEventListener('click', () => {
            const names: string[] = [];
            for (const item of this.contractTabs) {
                if (item.strategy && !names.includes(item.strategy)) {
                    names.push(item.strategy);
                }
            }
            showMenuBelow(select, [
                {
                    label: '选择策略',
                    submenu: names.length
                        ? names.map((name) => ({
                            label: `${name}${this._activeStrategy() === name
                                ? '  ✓' : ''}`,
                            run: () => this._pickStrategy(name),
                        }))
                        : [{ label: '只有一个策略', disabled: true }],
                },
                {
                    label: '选择时间段',
                    submenu: REPLAY_SEEKS.map((fraction) => ({
                        label: `从 ${Math.round(fraction * 100)}% 处开始`,
                        run: () => this._startReplayAt(fraction),
                    })),
                },
            ]);
        });

        // ② 播放 / 暂停
        const play = document.createElement('button');
        play.className = 'desk-tool desk-tool-replay desk-replay-play';
        play.innerHTML = REPLAY_PLAY_ICON;
        play.title = '播放 / 暂停';
        play.addEventListener('click', () => {
            if (this.toolState.playing) {
                this.toolState.playing = false;
                this._stopReplayClock();
            } else {
                this.toolState.replay = true;
                this.toolState.playing = true;
                this._startReplayClock();
            }
            this._renderReplayBar();
        });
        this.replayPlayButton = play;

        // ③ 前进一根
        const step = document.createElement('button');
        step.className = 'desk-tool';
        step.innerHTML = REPLAY_STEP_ICON;
        step.title = '前进一根';
        step.addEventListener('click', () => {
            this.toolState.playing = false;
            this._stopReplayClock();
            this._postFrames('replayStep', {});
            this._renderReplayBar();
        });

        // ④ 速度 ▾
        const speed = document.createElement('button');
        speed.className = 'desk-tool desk-tool-arrow';
        speed.title = '回放速度';
        const speedLabel = document.createElement('span');
        speedLabel.className = 'desk-tool-label';
        speedLabel.textContent = `${this.toolState.speed}x`;
        const speedCaret = document.createElement('span');
        speedCaret.className = 'desk-tool-caret';
        speedCaret.textContent = '▾';
        speed.append(speedLabel, speedCaret);
        speed.addEventListener('click', () => {
            showMenuBelow(speed, REPLAY_SPEEDS.map((value) => ({
                label: `${value}x${value === this.toolState.speed ? '  ✓' : ''}`,
                run: () => {
                    this.toolState.speed = value;
                    speedLabel.textContent = `${value}x`;
                    if (this.toolState.playing) this._startReplayClock();
                },
            })));
        });

        // ⑤ 进度（`已暂停 · 3051/10000（31%）` ✓）
        this.replayLabel = document.createElement('span');
        this.replayLabel.className = 'desk-muted desk-replay-progress';

        // ⑥ 退出回放（▶▶ 图标，和截图一致 ✓）
        const exit = document.createElement('button');
        exit.className = 'desk-tool desk-tool-replay on';
        exit.title = '退出回放（恢复全部数据）';
        exit.innerHTML = REPLAY_EXIT_ICON;
        exit.addEventListener('click', () => {
            this.toolState.replay = false;
            this.toolState.playing = false;
            this._stopReplayClock();
            this._postFrames('replayExit', {});
            this._renderChartTools();
            this._renderReplayBar();
        });

        bar.append(select, play, step, speed, this.replayLabel, exit);
        this.element.appendChild(bar);          // 整页最下方 = 整个图表下方 ✓
        this.replayBar = bar;
    }

    /** 回放条状态同步（进度 / 播放图标 / 显示与否 ✓） */
    private _renderReplayBar(): void {
        this._ensureReplayBar();
        const state = this.toolState;
        this.replayBar?.classList.toggle('on', state.replay);
        if (this.replayPlayButton) {
            this.replayPlayButton.innerHTML = state.playing
                ? REPLAY_PAUSE_ICON : REPLAY_PLAY_ICON;
            this.replayPlayButton.classList.toggle('on', state.playing);
        }
        if (this.replayLabel) {
            const total = state.total;
            const percent = total
                ? Math.round((state.bars / total) * 100) : 0;
            this.replayLabel.textContent = `${state.playing
                ? '回放中' : '已暂停'} · ${state.bars}/${total || '--'}`
                + `（${percent}%）`;
        }
    }

    /** 当前选中的策略名（回放条「选择策略」打 ✓ 用 ✓） */
    private _activeStrategy(): string {
        const found = this.contractTabs.find((item) => item.key === this.active);
        return found?.strategy || this.strategies[0]?.name || '';
    }

    /** 回放条「选择策略」→ 切到该策略的第一张合约图并继续回放 ✓ */
    private _pickStrategy(name: string): void {
        const target = this.contractTabs.find((item) => item.strategy === name);
        if (target) this._showTab(target.key);
        if (this.toolState.replay) {
            this.toolState.bars = 0;
            this._postFrames('replayStart', {});
        }
        this._renderReplayBar();
        this.options.onToast('info', `回放策略：${name}`);
    }

    /** 回放条「选择时间段」→ 从该位置重新开始 ✓ */
    private _startReplayAt(fraction: number): void {
        this.toolState.replay = true;
        this.toolState.playing = false;
        this._stopReplayClock();
        const bars = this._initialSeekBars(fraction);
        this._postFrames('replayStart', { bars: Math.max(1, bars) });
        // ★ 驱动里的字段名是 `frac`（不是 seek）✓
        this._postFrames('replaySeek', { frac: fraction });
        this.toolState.bars = bars;
        const percent = Math.round(fraction * 100);
        this.options.onToast('info', `回放从 ${percent}% 处开始`);
        this._renderChartTools();
        this._renderReplayBar();
    }

    /**
     * 图例齿轮菜单回调（`kind`：`params` / `style` / `width` / `color` / …）
     *
     * * `params` → 弹参数框，确认后让后端**按新参数重算指标并重建图表** ✓
     * * 其余样式项 → 图表里已经即时生效，这里只提示一下（不重算 ✓）
     */
    private _onIndicatorMenu(data: {
        series?: string; kind?: string; payload?: Record<string, any>;
    }): void {
        const payload0 = data?.payload || {};
        const series = String(payload0.source || data?.series || '');
        const kind = String(data?.kind || '');
        const payload = data?.payload || {};
        if (kind !== 'params') {
            const label: Record<string, string> = {
                style: '线型', width: '线宽', color: '线颜色',
                priceLine: '价格线', priceLabel: '价格标签',
            };
            this.options.onToast('info',
                `${series}：已更新${label[kind] || '样式'}`);
            return;
        }
        const values = (payload.values || {}) as Record<string, number>;
        if (!Object.keys(values).length) return;
        openParamPopover(
            null,
            `${series} 参数`,
            values,
            (next) => {
                this.options.onCommand('strategy_indicator_params', {
                    id: this.id, series, values: next,
                });
                this.options.onToast('info', `${series}：正在按新参数重算…`);
            },
            this.options.theme === 'light' ? 'light' : 'dark',
        );
    }

    /** 回放时钟：1x ≈ 400ms 放一根，倍速只改间隔（两个图表同时单步 ✓） */
    private _startReplayClock(): void {
        this._stopReplayClock();
        const interval = Math.max(30, Math.round(400 / Math.max(1,
            this.toolState.speed)));
        this.replayTimer = window.setInterval(() => {
            if (!this.toolState.replay) {
                this._stopReplayClock();
                return;
            }
            this._postFrames('replayStep', {});
            this._renderChartTools();
        }, interval);
        this._renderChartTools();
    }

    private _stopReplayClock(): void {
        if (this.replayTimer === undefined) return;
        window.clearInterval(this.replayTimer);
        this.replayTimer = undefined;
    }

    /** 把命令发给两个 iframe（图表 / 回测结果都保持同样的类型与画线状态 ✓） */
    private _postFrames(cmd: string, payload: Record<string, unknown>): void {
        this._post(this.chartFrame, cmd, payload);
        if (this.resultFrame.contentWindow) {
            this._post(this.resultFrame, cmd, payload);
        }
    }

    private _post(frame: HTMLIFrameElement, cmd: string,
                  payload: Record<string, unknown>): void {
        const win = frame.contentWindow;
        if (!win) return;
        try {
            win.postMessage({ __deskSL: cmd, ...payload }, '*');
        } catch {
            /* 老 HTML 没有驱动 → 忽略 ✓ */
        }
    }

    private _buildPanels(): void {
        for (const key of ['result', 'record', 'optimize']) {
            const panel = document.createElement('div');
            panel.className = `desk-strategy-panel desk-strategy-${key}`;
            panel.dataset.panel = key;
            panel.style.display = 'none';
            this.panels[key] = panel;
            this.body.appendChild(panel);
        }
        this.panels.result.appendChild(this.resultFrame);
        this.panels.record.innerHTML = '<div class="desk-strategy-empty">回测中…</div>';
        if (this.panels.optimize) {
            this.panels.optimize.innerHTML = '<div class="desk-strategy-empty">参数优化中…</div>';
        }
    }

    private _bind(): void {
        this.element.addEventListener('click', (event) => {
            const target = event.target as HTMLElement;
            if (target.closest('[data-exit]')) {
                this.options.onExit();
                return;
            }
            if (target.closest('[data-opt-restart]')) {
                this._restartOptimize();
                return;
            }
            if (target.closest('[data-opt-target-reset]')) {
                if (this.running) return;
                this.optRows = [];
                this.optTargets = [];
                this.optWeights = [];
                this.optOptions = {
                    method: '', n_jobs: 0, n_trials: 0, sampler: '', pruner: '',
                };
                this.optParamSpace = [];
                this._renderOptimization();
                this.options.onCommand('strategy_start', {
                    file: this.file, mode: 'optimize', metrics: [],
                    weights: [], options: {}, param_space: {},
                });
                return;
            }
            // ---- 参数网格：加一行 / 删一行（行内字段在 change 里改 ✓）----
            if (target.closest('[data-opt-param-add]')) {
                if (this.running) return;
                const used = new Set(this.optParamSpace.map((row) => row.name));
                const name = this.optParamOptions.find((item) => !used.has(item))
                    || this.optParamOptions[0] || '';
                this.optParamSpace = [...this.optParamSpace, {
                    name, kind: 'range', low: '', high: '', step: '', list: '',
                    value: '',
                }];
                this._renderOptimization();
                return;
            }
            const removeRow = target.closest<HTMLElement>('[data-opt-param-del]');
            if (removeRow) {
                if (this.running) return;
                const index = Number(removeRow.dataset.optParamDel);
                this.optParamSpace = this.optParamSpace
                    .filter((_row, position) => position !== index);
                this._renderOptimization();
                return;
            }
            const tool = target.closest<HTMLElement>('[data-sl]');
            if (tool) {
                this._onChartTool(tool.dataset.sl || '', tool);
                return;
            }
            const tab = target.closest<HTMLElement>('[data-tab]');
            if (tab) {
                const key = tab.dataset.tab || 'chart';
                if (key.startsWith('c:')) {
                    const [, strategy, contract] = key.split(':');
                    this.options.onCommand('strategy_select', {
                        id: this.id, strategy, contract,
                    });
                }
                this._showTab(key);
            }
            const sort = target.closest<HTMLElement>('[data-opt-sort]');
            if (sort) {
                const key = sort.dataset.optSort || '';
                if (this.optSortKey === key) this.optSortDir *= -1;
                else { this.optSortKey = key; this.optSortDir = 1; }
                this._renderOptimization();
                return;
            }
            const row = target.closest<HTMLElement>('[data-opt-row]');
            if (row) {
                this.optSelected = Number(row.dataset.optRow || 0);
                this._highlightOptRow();
            }
            if (target.closest('[data-opt-use]')) this._useOptTrial();
            if (target.closest('[data-opt-write]')) this._writeOpt();
            if (target.closest('[data-opt-export]')) this._exportOpt();
            if (target.closest('[data-opt-chart]')) this._showOptChart();
            if (target.closest('[data-opt-table]')) this.setOptimization({ rows: this.optRows });
            const chartTab = target.closest<HTMLElement>('[data-opt-mode]');
            if (chartTab) {
                this.optChartMode = (chartTab.dataset.optMode || 'pareto') as ('pareto' | 'rank' | 'importance');
                this._renderOptChart();
            }
            // 帕累托前沿：「显示」按钮 → 收集 1~3 个轴，确认后再画 ✓
            if (target.closest('[data-pareto-apply]')) {
                const panel = this.panels.optimize;
                const axes: string[] = [];
                [0, 1, 2].forEach((index) => {
                    const value = panel?.querySelector<HTMLSelectElement>(
                        `[data-pareto-axis="${index}"]`)?.value || '';
                    if (value && !axes.includes(value)) axes.push(value);
                });
                if (!axes.length) {
                    this.options.onToast('warning', '至少选 1 个目标作为轴');
                    return;
                }
                this.optParetoAxes = axes.slice(0, PARETO_AXES);
                this._renderOptChart();
            }
        });
        this.element.addEventListener('input', (event) => {
            const node = event.target as HTMLElement;
            const input = node.closest<HTMLInputElement>('[data-opt-filter]');
            if (input) {
                this.optFilter = input.value;
                this._renderOptimization();
                return;
            }
            // 参数网格的数字 / 列表输入：边打边存（不重绘，保住焦点 ✓）
            const field = node.closest<HTMLElement>('[data-opt-param]');
            if (field && field instanceof HTMLInputElement) {
                const index = Number(field.dataset.optParam);
                const key = (field.dataset.field || '') as keyof OptParamRow;
                const row = this.optParamSpace[index];
                if (row && key) {
                    (row as unknown as Record<string, string>)[key] = field.value;
                }
            }
        });
        this.element.addEventListener('change', (event) => {
            const node = event.target as HTMLElement;
            const select = node.closest<HTMLSelectElement>('[data-sl-speed]');
            if (select) {
                this._postFrames('replaySpeed', { speed: Number(select.value) || 1 });
                return;
            }
            // ---- 优化目标权重 / 优化设置 / 参数网格（只更新状态，不重绘 ✓）----
            const weight = node.closest<HTMLSelectElement>('[data-opt-weight]');
            if (weight) {
                const index = Number(weight.dataset.optWeight);
                const value = Number(weight.value);
                if (Number.isFinite(index) && Number.isFinite(value)) {
                    this.optWeights[index] = value;
                }
                this._renderOptimization();
                return;
            }
            const option = node.closest<HTMLElement>('[data-opt-opt]');
            if (option) {
                const key = option.dataset.optOpt || '';
                const value = key === 'n_trials' || key === 'n_jobs'
                    ? Number((option as HTMLInputElement).value) || 0
                    : String((option as HTMLSelectElement).value || '');
                if (key) this.optOptions = { ...this.optOptions, [key]: value };
                return;
            }
            const field = node.closest<HTMLElement>('[data-opt-param]');
            if (field) {
                const index = Number(field.dataset.optParam);
                const key = (field.dataset.field || '') as keyof OptParamRow;
                const row = this.optParamSpace[index];
                if (row && key) {
                    (row as unknown as Record<string, string>)[key] = field
                        instanceof HTMLSelectElement || field instanceof HTMLInputElement
                        ? field.value : '';
                    if (key === 'kind') this._renderOptimization();
                }
                return;
            }
        });
    }

    private _showTab(key: string): void {
        if (key === 'chart' && this.contractTabs.length) {
            key = this.contractTabs[0].key;
        }
        this.active = key;
        const contractTab = key.startsWith('c:') || key === 'chart';
        if (contractTab) {
            this.resultKey = '';
            this.chartFiles.delete('result');
        }
        this.chartFrame.style.display = contractTab ? 'block' : 'none';
        this.resultFrame.style.display = key === 'result' ? 'block' : 'none';
        for (const [name, panel] of Object.entries(this.panels)) {
            panel.style.display = name === key ? 'block' : 'none';
        }
        this.tabs.querySelectorAll<HTMLElement>('[data-tab]').forEach((node) => {
            node.classList.toggle('on', node.dataset.tab === key);
        });
        // 回放中切页签 → 让刚显示出来的图表对齐位置（还在播就继续播 ✓）
        if (this.toolState.replay) {
            this._resyncFrame(key === 'result' ? this.resultFrame
                : this.chartFrame);
        }
        this._loadChartFrame(key);
    }

    // ------------------------------------------------------------- data
    setState(patch: Record<string, any>): void {
        this.strategies = (patch.strategies || []) as StrategyRow[];
        const status = String(patch.status || '');
        this.running = status === 'running';
        if (Array.isArray(patch.target_options)) {
            this.targetOptions = patch.target_options.map(String);
        }
        if (Array.isArray(patch.targets)) {
            this.optTargets = patch.targets.map(String);
        }
        if (Array.isArray(patch.weights)) {
            this.optWeights = patch.weights.map(Number);
        }
        // 优化设置 / 参数网格（后端下发选项列表 → 前端全部做成下拉 ✓）
        if (patch.options && typeof patch.options === 'object') {
            this.optOptions = { ...this.optOptions, ...patch.options };
        }
        if (Array.isArray(patch.param_options) && patch.param_options.length) {
            this.optParamOptions = patch.param_options.map(String);
        }
        if (Array.isArray(patch.method_options) && patch.method_options.length) {
            this.optMethodOptions = patch.method_options.map(String);
        }
        if (Array.isArray(patch.sampler_options) && patch.sampler_options.length) {
            this.optSamplerOptions = patch.sampler_options.map(String);
        }
        if (Array.isArray(patch.pruner_options) && patch.pruner_options.length) {
            this.optPrunerOptions = patch.pruner_options.map(String);
        }
        if (Array.isArray(patch.n_jobs_options) && patch.n_jobs_options.length) {
            this.optNJobsOptions = patch.n_jobs_options.map(Number);
        }
        if (Array.isArray(patch.weight_options) && patch.weight_options.length) {
            this.optWeightOptions = patch.weight_options.map(Number);
        }
        if (patch.param_space && typeof patch.param_space === 'object') {
            this.optParamSpace = this._paramRowsFromSpace(patch.param_space);
        }
        if (status === 'running') {
            this.frameKey = '';
            this.resultKey = '';
            this.chartFiles.clear();
            if (this.mode === 'optimize') this.optRows = [];
        }
        const labels: Record<string, string> = {
            running: '回测中…', ready: '已完成', error: '失败',
            cancelled: '已取消', idle: '准备中…',
        };
        this.status.textContent = labels[status] || status;
        this.status.className = `status ${status}`;
        const progress = this.element.querySelector('[data-progress]') as HTMLElement;
        if (progress) {
            progress.style.display = status === 'running' ? 'inline-flex' : 'none';
        }
        const selected = (patch.selected || {}) as Record<string, string>;
        this._syncContractTabs(selected);
        if (patch.error) {
            this._showError(String(patch.error));
        } else if (status === 'ready') {
            if (!this.initialReady) {
                this.initialReady = true;
                this.active = this.mode === 'optimize'
                    ? 'optimize' : (this.contractTabs[0]?.key || 'chart');
                this._buildTabs();
                this._showTab(this.active);
            } else {
                this._buildTabs();
                this._showTab(this.active);
            }
        }
        if (this.mode === 'optimize') this._renderOptimization();
    }

    private _syncContractTabs(selected: Record<string, string>): void {
        this.contractTabs = [];
        const multiStrategy = this.strategies.length > 1;
        for (const strategy of this.strategies) {
            for (const contract of strategy.contracts || []) {
                const key = `c:${strategy.name}:${contract}`;
                this.contractTabs.push({
                    key, strategy: strategy.name, contract,
                    label: multiStrategy
                        ? `${strategy.name} · ${contract}` : contract,
                });
            }
        }
        const preferred = selected.strategy && selected.contract
            ? `c:${selected.strategy}:${selected.contract}` : '';
        if (preferred && this.contractTabs.some((item) => item.key === preferred)
            && !this.initialReady) {
            this.active = preferred;
        }
        if (this.contractTabs.length
            && !this.contractTabs.some((item) => item.key === this.active)
            && !['result', 'record', 'optimize'].includes(this.active)) {
            this.active = this.contractTabs[0].key;
        }
    }

    setChart(_patch: Record<string, any>): void {
        // 图表现在由后端 MiniQT 代码生成，前端只负责切 iframe；保留接口兼容。
    }

    /** 图表 HTML 被后端重建了 → 清掉前端缓存并重新装载当前页签 ✓ */
    reloadCharts(): void {
        this.chartFiles.clear();
        this.resultKey = '';
        this._loadChartFrame(this.active === 'result' ? 'result' : this.active);
    }

    private _loadChartFrame(key: string): void {
        if (!this.initialReady) return;
        if (key === 'result') {
            const wanted = 'result';
            if (this.resultKey === wanted) return;
            this.resultKey = wanted;
            this._loadFrame(this.resultFrame, wanted);
            return;
        }
        if (!key.startsWith('c:') && key !== 'chart') return;
        const contract = this.contractTabs.find((item) => item.key === key)
            || this.contractTabs[0];
        if (!contract) return;
        if (this.frameKey === contract.key) return;
        this.frameKey = contract.key;
        this._loadFrame(this.chartFrame, contract.key);
    }

    /** Qt 壳是 file://，没有 HTTP 服务 → 用后端写好的本地 HTML 文件。 */
    private _loadFrame(frame: HTMLIFrameElement, key: string): void {
        if (!this.initialReady) {
            // 回测 / 优化还没算完 → 保持主题色占位页（别糊上黑底 ✗）
            this._setPlaceholder(frame);
            return;
        }
        if (!this.fileMode) {
            this._setFrameUrl(frame, this._chartUrl(key));
            return;
        }
        const cached = this.chartFiles.get(key);
        if (cached) {
            this._setFrameUrl(frame, cached);
            return;
        }
        this._setPlaceholder(frame);
        this.options.onCommand('strategy_chart_file', {
            id: this.id, key, theme: this.options.theme,
        });
    }

    /** 回测中 / 参数优化中还没有图表 → 占位页的底色**跟随主题** ✓ */
    private _placeholderHtml(): string {
        const light = this.options.theme === 'light';
        return '<!doctype html><meta charset="utf-8"><body style="'
            + `background:${light ? '#ffffff' : '#111111'};`
            + `color:${light ? '#5c6672' : '#9aa4b2'};`
            + 'font:13px sans-serif;'
            + 'display:flex;align-items:center;justify-content:center;'
            + 'height:100vh;margin:0">正在生成 MiniQT 图表…</body>';
    }

    /** 把 iframe 换回主题色占位页（同时清掉旧 src，否则 srcdoc 不生效 ✓） */
    private _setPlaceholder(frame: HTMLIFrameElement): void {
        frame.removeAttribute('src');
        frame.srcdoc = this._placeholderHtml();
    }

    /** 主题切换后：还没装图表的 iframe 重刷占位页（否则停在上一个主题的底色 ✗） */
    private _refreshPlaceholders(): void {
        for (const frame of [this.chartFrame, this.resultFrame]) {
            if (!frame.getAttribute('src')) this._setPlaceholder(frame);
        }
    }

    /** 后端（Qt/file://）返回图表文件地址后装载 ✓ */
    setChartFile(patch: Record<string, any>): void {
        const key = String(patch.key || '');
        const url = String(patch.url || '');
        if (!key || !url) return;
        this.chartFiles.set(key, url);
        if (key === 'result') {
            if (this.active === 'result') this._setFrameUrl(this.resultFrame, url);
        } else if (this.active === key || this.frameKey === key) {
            this._setFrameUrl(this.chartFrame, url);
        }
    }

    private _setFrameUrl(frame: HTMLIFrameElement, url: string): void {
        // srcdoc 的优先级高于 src：不清掉就会一直停在“正在生成…”页面
        frame.removeAttribute('srcdoc');
        frame.onload = () => this._syncFrameState(frame);
        frame.src = url;
    }

    /**
     * iframe 重载（换合约 / 换主题）后把当前设置再套一次 ✓
     *
     * 回放中重载时**直接恢复播放状态**（以前只恢复位置 → 切到回测结果图
     * 就变成暂停，还得再点一次播放 ✗）
     */
    private _syncFrameState(frame: HTMLIFrameElement): void {
        const { kind, toolbox, replay, playing, bars } = this.toolState;
        this._post(frame, 'font', { size: this.fontSize });
        this._post(frame, 'crosshair', { color: this.crosshairColor });
        if (kind !== 'candle') this._post(frame, 'type', { kind });
        if (toolbox) this._post(frame, 'toolbox', { show: true });
        if (!replay) return;
        this._post(frame, 'replayStart', { bars });
        void playing;
    }

    /** 切页签：让刚显示出来的图表跟上回放位置 / 播放状态 ✓ */
    private _resyncFrame(frame: HTMLIFrameElement): void {
        if (!this.toolState.replay) return;
        this._post(frame, 'replayStart', { bars: this.toolState.bars });
        // 播放状态交给本页的时钟驱动（`replayPlay` 只用于瞬时推进）✓
        if (this.toolState.playing) {
            this._post(frame, 'replayPlay', {});
            this._startReplayClock();
        }
    }

    private _chartUrl(key: string): string {
        const query = new URLSearchParams({
            id: this.id, key, theme: this.options.theme,
        });
        const base = window.location.pathname.replace(/[^/]*$/, '');
        return `${base}strategy_chart?${query.toString()}`;
    }

    setResult(patch: ResultPayload): void {
        this.currentResult = patch || {};
        this._renderRecord();
        if (this.active === 'result') this._loadChartFrame('result');
    }

    setTrades(rows: TradeRow[]): void {
        this.trades = rows || [];
        this._renderRecord();
    }

    setError(message: string): void {
        this._showError(message);
    }

    setProgress(current: number, total: number, text = ''): void {
        const host = this.element.querySelector('[data-progress]') as HTMLElement;
        if (!host) return;
        const bar = host.querySelector('i') as HTMLElement;
        const label = host.querySelector('em') as HTMLElement;
        const percent = total > 0
            ? Math.max(0, Math.min(100, current / total * 100)) : 0;
        host.classList.toggle('indeterminate', total <= 0);
        if (bar) bar.style.width = total > 0 ? `${percent}%` : '';
        if (label) {
            label.textContent = total > 0 ? `${current}/${total}` : '';
        }
        if (text && total > 0) {
            this.status.textContent = `${text} ${current}/${total}`;
        }
    }

    private _renderRecord(): void {
        const metrics = this.currentResult.metrics || {};
        const cards = METRIC_GROUPS.flatMap(([, items]) => items).map(
            ([key, title, kind]) => `
            <div class="desk-strategy-metric-card">
                <span>${title}</span><b>${fmt(metrics[key], kind)}</b>
            </div>`).join('');
        const contracts = (this.currentResult.contracts || []).map((item) => `
            <tr><td>${esc(item.symbol)}</td><td>${item.trade_count ?? 0}</td>
                <td>${item.bars ?? 0}</td></tr>`).join('');
        const tradeRows = this.trades.map((row) => {
            const pnl = Number(row.pnl);
            const cls = !Number.isFinite(pnl) ? '' : (pnl >= 0 ? 'up' : 'down');
            return `<tr>
                <td>${timeText(row.time)}</td>
                <td>${esc(row.direction || '')}</td>
                <td>${esc(row.symbol || '')}</td>
                <td>${Number.isFinite(Number(row.price)) ? num(row.price, 3) : '--'}</td>
                <td>${Number.isFinite(Number(row.qty)) ? Math.round(Number(row.qty)) : '--'}</td>
                <td>${Number.isFinite(Number(row.fee)) ? num(row.fee, 2) : '--'}</td>
                <td class="${cls}">${Number.isFinite(pnl) ? num(pnl, 2) : '--'}</td>
            </tr>`;
        }).join('');
        this.panels.record.innerHTML = `
            <div class="desk-strategy-panel-title">回测结果
                <span>${esc(this.currentResult.strategy || '')}</span></div>
            <div class="desk-strategy-metric-cards">${cards}</div>
            <div class="desk-strategy-equity-title">权益 / 回撤
                <span>${this.currentResult.equity?.values?.length || 0} 点</span></div>
            <div class="desk-strategy-equity-wrap">${equitySvg(this.currentResult.equity)}</div>
            <div class="desk-strategy-panel-title small">分合约结果</div>
            <div class="desk-strategy-table-wrap"><table class="desk-strategy-table">
                <thead><tr><th>合约</th><th>交易记录数</th><th>K线根数</th></tr></thead>
                <tbody>${contracts || '<tr><td colspan="3">--</td></tr>'}</tbody>
            </table></div>
            <div class="desk-strategy-panel-title small">交易记录
                <span>${this.trades.length} 行</span></div>
            <div class="desk-strategy-table-wrap"><table class="desk-strategy-table">
                <thead><tr><th>时间</th><th>方向</th><th>合约</th>
                    <th>成交价</th><th>数量</th><th>手续费</th><th>盈亏</th></tr></thead>
                <tbody>${tradeRows || '<tr><td colspan="7">暂无交易</td></tr>'}</tbody>
            </table></div>`;
    }

    setOptimization(patch: Record<string, any>): void {
        const panel = this.panels.optimize;
        if (!panel) return;
        const rows = (patch.rows || []) as Array<Record<string, any>>;
        this.optRows = rows;
        this.optSelected = 0;
        this.optFilter = '';
        this.optSortKey = '';
        this.optSortDir = 1;
        this._renderOptimization();
    }

    /** 参数网格字典 → 可编辑的行（`[low, high, step]` / 选项列表 / 固定值） */
    private _paramRowsFromSpace(space: Record<string, any>): OptParamRow[] {
        const rows: OptParamRow[] = [];
        for (const [name, value] of Object.entries(space || {})) {
            if (Array.isArray(value) && value.length >= 2
                && value.every((item) => typeof item === 'number')) {
                rows.push({
                    name, kind: 'range',
                    low: String(value[0]), high: String(value[1]),
                    step: value.length > 2 ? String(value[2]) : '',
                    list: '', value: '',
                });
            } else if (Array.isArray(value)) {
                rows.push({
                    name, kind: 'list', low: '', high: '', step: '',
                    list: value.join(','), value: '',
                });
            } else {
                rows.push({
                    name, kind: 'fixed', low: '', high: '', step: '',
                    list: '', value: String(value ?? ''),
                });
            }
        }
        return rows;
    }

    /** 参数网格（行）→ 后端的 `param_space` 字典 ✓ */
    private _optParamPayload(): Record<string, any> {
        const out: Record<string, any> = {};
        for (const row of this.optParamSpace) {
            const name = String(row.name || '').trim();
            if (!name) continue;
            if (row.kind === 'range') {
                // 空字符串不能被 `Number('')` 当成 0（那样会发出 [0, 0] ✗）
                const lowText = String(row.low ?? '').trim();
                const highText = String(row.high ?? '').trim();
                if (!lowText || !highText) continue;
                const low = Number(lowText);
                const high = Number(highText);
                if (!Number.isFinite(low) || !Number.isFinite(high)) continue;
                const stepText = String(row.step ?? '').trim();
                const step = stepText === '' ? NaN : Number(stepText);
                out[name] = Number.isFinite(step) ? [low, high, step] : [low, high];
            } else if (row.kind === 'list') {
                const items = String(row.list || '')
                    .split(/[,，\s]+/)
                    .filter((item) => item !== '')
                    .map((item) => {
                        const number = Number(item);
                        return Number.isFinite(number) ? number : item;
                    });
                if (items.length) out[name] = items;
            } else {
                const text = String(row.value ?? '').trim();
                if (!text) continue;
                const number = Number(text);
                out[name] = Number.isFinite(number) ? number : text;
            }
        }
        return out;
    }

    /** 优化设置（method / n_jobs / n_trials / sampler / pruner）→ 后端 payload */
    private _optOptionsPayload(): Record<string, any> {
        const options: Record<string, any> = { ...this.optOptions };
        this.panels.optimize?.querySelectorAll<HTMLElement>('[data-opt-opt]')
            .forEach((node) => {
                const key = node.dataset.optOpt || '';
                if (!key) return;
                const value = (node as HTMLSelectElement).value
                    ?? (node as HTMLInputElement).value;
                if (key === 'n_trials' || key === 'n_jobs') {
                    options[key] = Number(value) || 0;
                } else {
                    options[key] = String(value || '');
                }
            });
        return options;
    }

    /** 某个目标的当前权重（没设过 → 1.0 最大化 ✓） */
    private _weightFor(index: number): number {
        const value = Number(this.optWeights[index]);
        return Number.isFinite(value) && value !== 0 ? value : 1;
    }

    private _weightSelect(index: number): string {
        const list = this.optWeightOptions.length
            ? this.optWeightOptions : DEFAULT_OPT_WEIGHTS;
        const current = this._weightFor(index);
        return `<select data-opt-weight="${index}">${list.map((value) => {
            const label = `${value > 0 ? '↑' : '↓'} ${value}（${
                value > 0 ? '最大化' : '最小化'}）`;
            return `<option value="${value}"${
                value === current ? ' selected' : ''}>${label}</option>`;
        }).join('')}</select>`;
    }

    /** 「优化设置」下拉：方法 / 并行 / 试验次数 / 采样器 / 剪枝器 ✓ */
    private _optOptionsHtml(): string {
        const methods = this.optMethodOptions.length
            ? this.optMethodOptions : DEFAULT_OPT_METHODS;
        const samplers = this.optSamplerOptions.length
            ? this.optSamplerOptions : DEFAULT_OPT_SAMPLERS;
        const pruners = this.optPrunerOptions.length
            ? this.optPrunerOptions : DEFAULT_OPT_PRUNERS;
        const jobs = this.optNJobsOptions.length
            ? this.optNJobsOptions : DEFAULT_OPT_NJOBS;
        const method = String(this.optOptions.method || '');
        const sampler = String(this.optOptions.sampler || '');
        const pruner = String(this.optOptions.pruner || '');
        const nJobs = Number(this.optOptions.n_jobs) || 0;
        const nTrials = Number(this.optOptions.n_trials) || 0;
        const select = (key: string, value: string,
                        items: Array<[string, string]>): string =>
            `<select data-opt-opt="${key}">${items.map(([val, label]) =>
                `<option value="${esc(val)}"${
                    val === value ? ' selected' : ''}>${esc(label)}</option>`
            ).join('')}</select>`;
        return `<div class="desk-strategy-opt-settings">
            <label>方法${select('method', method,
                [['', '跟随默认'], ...methods.map((name) =>
                    [name, METHOD_LABELS[name] || name] as [string, string])])}</label>
            <label>并行 n_jobs${select('n_jobs', String(nJobs),
                [['0', '跟随默认'], ...jobs.map((value) =>
                    [String(value),
                     value === -1 ? '-1（全部核心）' : String(value)
                    ] as [string, string])])}</label>
            <label>试验次数 n_trials<input type="number" min="1" max="100000"
                data-opt-opt="n_trials" value="${nTrials || ''}"
                placeholder="跟随默认"></label>
            <label>采样器 sampler${select('sampler', sampler,
                [['', '跟随默认'], ...samplers.map((name) =>
                    [name, name] as [string, string])])}</label>
            <label>剪枝器 pruner${select('pruner', pruner,
                [['', '跟随默认'], ...pruners.map((name) =>
                    [name, name] as [string, string])])}</label>
        </div>`;
    }

    /** 「参数网格」：参数名 / 类型 / 范围都能改（参数名是下拉选 ✓） */
    private _optParamsHtml(): string {
        const known = this.optParamOptions.length
            ? this.optParamOptions
            : Array.from(new Set(this.optParamSpace.map((row) => row.name)));
        const rows = this.optParamSpace.map((row, index) => {
            const names = (known.includes(row.name) || !row.name)
                ? known : [row.name, ...known];
            const nameOptions = names.filter((item) => !!item).map((item) =>
                `<option value="${esc(item)}"${
                    item === row.name ? ' selected' : ''}>${esc(item)}</option>`
            ).join('');
            const kindOptions = ([['range', '数值范围'], ['list', '固定选项'],
                ['fixed', '固定值']] as Array<[string, string]>).map(([value, label]) =>
                `<option value="${value}"${
                    value === row.kind ? ' selected' : ''}>${label}</option>`
            ).join('');
            let fields = '';
            if (row.kind === 'range') {
                fields = `<input type="number" data-opt-param="${index}" data-field="low"
                        value="${esc(row.low)}" placeholder="最小" title="最小值">
                    <span class="desk-opt-dash">~</span>
                    <input type="number" data-opt-param="${index}" data-field="high"
                        value="${esc(row.high)}" placeholder="最大" title="最大值">
                    <input type="number" data-opt-param="${index}" data-field="step"
                        value="${esc(row.step)}" placeholder="步长" title="步长（空 = 1）">`;
            } else if (row.kind === 'list') {
                fields = `<input type="text" data-opt-param="${index}" data-field="list"
                    value="${esc(row.list)}" placeholder="选项，逗号分隔：5,10,20">`;
            } else {
                fields = `<input type="text" data-opt-param="${index}" data-field="value"
                    value="${esc(row.value)}" placeholder="固定值">`;
            }
            return `<div class="desk-opt-param-row">
                <select data-opt-param="${index}" data-field="name">${nameOptions}</select>
                <select data-opt-param="${index}" data-field="kind">${kindOptions}</select>
                ${fields}
                <button class="desk-opt-param-del" data-opt-param-del="${index}"
                    title="删除这个参数">✕</button>
            </div>`;
        }).join('');
        return `<div class="desk-strategy-opt-params">
            <div class="desk-strategy-opt-targets-title">
                <b>参数网格</b>
                <span class="desk-muted">留空 = 用策略 / 指标自带的 params</span>
                <button class="desk-strategy-exit" data-opt-param-add
                    ${this.running ? 'disabled' : ''}>＋ 添加参数</button>
            </div>
            ${rows || '<div class="desk-muted">（还没有参数：先跑一次，或点「＋ 添加参数」）</div>'}
        </div>`;
    }

    /** 优化目标 + 权重 + 优化设置 + 参数网格（空 = 用策略 op_config 默认）✓ */
    private _optSettingsHtml(): string {
        const options = this.targetOptions.length
            ? this.targetOptions : DEFAULT_OPT_TARGETS;
        // ★ 目标最多 **9 个**（用户要求 2026-11-02）：每行 3 个，权重跟着各自目标 ✓
        const slots = Array.from({ length: OPT_TARGET_SLOTS }, (_, i) => i);
        const selects = slots.map((index) => {
            const chosen = this.optTargets[index] || '';
            const blank = index === 0 ? '' : '<option value="">（不使用）</option>';
            const used = index >= 3 ? ' desk-opt-extra' : '';
            return `<label class="${used.trim() || 'desk-opt-target-row'}">目标 ${index + 1}<select data-opt-target="${index}">
                ${blank}${options.map((item) =>
                    `<option value="${esc(item)}"${
                        item === chosen ? ' selected' : ''}>${esc(item)}</option>`
                ).join('')}
            </select>${this._weightSelect(index)}</label>`;
        }).join('');
        const running = this.running ? 'disabled' : '';
        return `<div class="desk-strategy-opt-targets">
            <div class="desk-strategy-opt-targets-title">
                <b>优化目标</b>
                <span class="desk-muted">最多 ${OPT_TARGET_SLOTS} 个 ·
                    每个目标可单独设权重（↑最大 / ↓最小）</span>
            </div>
            <div class="desk-strategy-opt-targets-form">${selects}
                <button class="desk-strategy-exit" data-opt-restart
                    ${running}>按当前目标重新优化</button>
                <button class="desk-strategy-exit" data-opt-target-reset
                    ${running}>恢复策略默认</button>
            </div>
            ${this._optOptionsHtml()}
            ${this._optParamsHtml()}
        </div>`;
    }

    private _restartOptimize(): void {
        if (this.running) return;
        const panel = this.panels.optimize;
        const slots = Array.from({ length: OPT_TARGET_SLOTS }, (_, i) => i);
        const metrics = slots
            .map((index) => panel?.querySelector<HTMLSelectElement>(
                `[data-opt-target="${index}"]`)?.value || '')
            .filter((value, index, all) => !!value && all.indexOf(value) === index)
            .slice(0, OPT_TARGET_SLOTS);
        if (!metrics.length) {
            this.options.onToast('warning', '至少选 1 个优化目标');
            return;
        }
        // ★ 权重：按**用户的每个目标**取（以前只画了个方向箭头，重跑时被忽略 ✗）
        const weights = metrics.map((_name, index) => {
            const value = Number(panel?.querySelector<HTMLSelectElement>(
                `[data-opt-weight="${index}"]`)?.value);
            return Number.isFinite(value) && value !== 0
                ? value : this._weightFor(index);
        });
        const options = this._optOptionsPayload();
        const paramSpace = this._optParamPayload();
        this.optRows = [];
        this.optTargets = metrics;
        this.optWeights = weights;
        this.optOptions = options;
        this._renderOptimization();
        this.options.onCommand('strategy_start', {
            file: this.file, mode: 'optimize', metrics, weights,
            options, param_space: paramSpace,
        });
    }

    /** 参数优化表：筛选 + 点击表头排序（文档里的「可筛选 / 排序」✓） */
    private _renderOptimization(): void {
        const panel = this.panels.optimize;
        if (!panel) return;
        const settings = this._optSettingsHtml();
        const rows = this.optRows;
        if (!rows.length) {
            panel.innerHTML = settings
                + '<div class="desk-strategy-empty">暂无参数优化结果</div>';
            return;
        }
        const columns = Object.keys(rows[0]);
        const needle = this.optFilter.trim().toLowerCase();
        let view = rows.map((row, index) => ({ row, index }));
        if (needle) {
            view = view.filter(({ row }) => columns.some((key) =>
                String(row[key] ?? '').toLowerCase().includes(needle)));
        }
        if (this.optSortKey) {
            const key = this.optSortKey;
            view = view.slice().sort((a, b) => {
                const av = a.row[key];
                const bv = b.row[key];
                const an = Number(av);
                const bn = Number(bv);
                let cmp: number;
                if (String(av ?? '').trim() !== ''
                    && String(bv ?? '').trim() !== ''
                    && Number.isFinite(an) && Number.isFinite(bn)) {
                    cmp = an - bn;
                } else {
                    cmp = String(av ?? '').localeCompare(
                        String(bv ?? ''), 'zh-CN', { numeric: true });
                }
                return cmp * this.optSortDir;
            });
        }
        const arrow = (key: string) => this.optSortKey === key
            ? (this.optSortDir > 0 ? ' ▲' : ' ▼') : '';
        panel.innerHTML = `${settings}<div class="desk-strategy-panel-title">参数优化结果
            <span>${view.length}/${rows.length} 个 trial</span></div>
            <div class="desk-strategy-opt-actions">
                <button class="desk-strategy-exit" data-opt-use>用选中回测</button>
                <button class="desk-strategy-exit" data-opt-write>写回最优参数</button>
                <button class="desk-strategy-exit" data-opt-chart>优化图表</button>
                <button class="desk-strategy-exit" data-opt-export>导出 CSV</button>
                <input class="desk-strategy-opt-filter" data-opt-filter
                    placeholder="筛选参数 / 目标…" value="${esc(this.optFilter)}">
            </div>
            <div class="desk-strategy-table-wrap"><table class="desk-strategy-table">
            <thead><tr>${columns.map((key) =>
                `<th data-opt-sort="${esc(key)}" class="sortable">${esc(key)}${arrow(key)}</th>`).join('')}</tr></thead>
            <tbody>${view.map(({ row, index }) => `<tr data-opt-row="${index}"
                class="${index === this.optSelected ? 'on' : ''}">${columns.map((key) =>
                `<td>${esc(row[key])}</td>`).join('')}</tr>`).join('')}</tbody>
            </table></div>`;
    }

    private _highlightOptRow(): void {
        this.panels.optimize?.querySelectorAll<HTMLElement>('[data-opt-row]')
            .forEach((node) => {
                node.classList.toggle('on',
                    Number(node.dataset.optRow) === this.optSelected);
            });
    }

    private _optParams(row: Record<string, any>): Record<string, any> {
        const params: Record<string, any> = {};
        for (const [key, value] of Object.entries(row || {})) {
            if (!key.startsWith('params_')) continue;
            const name = key.slice('params_'.length);
            const number = Number(value);
            params[name] = Number.isFinite(number) && String(value).trim() !== ''
                ? number : value;
        }
        return params;
    }

    private _useOptTrial(): void {
        const row = this.optRows[this.optSelected];
        if (!row) return;
        this.options.onCommand('strategy_trial_run', {
            id: this.id, params: this._optParams(row),
        });
        this._showTab('chart');
    }

    private _writeOpt(): void {
        const row = this.optRows[this.optSelected];
        if (!row) return;
        this.options.onWriteParams?.(this._optParams(row));
    }

    private _showOptChart(): void {
        if (!this.optRows.length) return;
        const panel = this.panels.optimize;
        if (!panel) return;
        panel.innerHTML = `<div class="desk-strategy-panel-title">参数优化图表
            <span>${this.optRows.length} 个 trial</span></div>
            <div class="desk-strategy-opt-actions">
                <button class="desk-strategy-exit" data-opt-table>返回表格</button>
                <button class="desk-strategy-exit" data-opt-mode="pareto">帕累托前沿</button>
                <button class="desk-strategy-exit" data-opt-mode="rank">参数排名</button>
                <button class="desk-strategy-exit" data-opt-mode="importance">参数重要性</button>
            </div>
            <div class="desk-strategy-opt-chart" data-opt-chart-host></div>`;
        this._renderOptChart();
    }

    private _renderOptChart(): void {
        const host = this.panels.optimize?.querySelector(
            '[data-opt-chart-host]') as HTMLElement;
        if (!host) return;
        this.panels.optimize?.querySelectorAll<HTMLElement>('[data-opt-mode]')
            .forEach((node) => node.classList.toggle('on',
                node.dataset.optMode === this.optChartMode));
        const rows = this.optRows;
        // ★ 只留有**真实数值**的指标列：某个目标在某些 trial 里是 None / N/A 时
        //   不能把整张图搞空（用户实测：多目标里一个指标缺值 → 三张图全白 ✗）
        const valueKeys = this._paretoMetricChoices(rows);
        if (this.optChartMode === 'pareto') {
            const axes = this._paretoAxes(rows, valueKeys);
            host.innerHTML = this._paretoAxesHtml(valueKeys, axes)
                + (axes.length >= PARETO_AXES
                    ? this._pareto3DHtml(rows, axes)
                    : this._paretoSvg(rows, axes));
            this._bindPareto3D(host, rows, axes);
            return;
        }
        const params = Object.keys(rows[0] || {})
            .filter((key) => /^params_/.test(key));
        // ★ 参数排名 / 参数重要性都按**参数名**展示（以前 rank 错用了
        //   `values_0` / `values_1` → 单目标时 0 个参数 ✗）
        const targetKey = valueKeys[0] || params[0] || 'number';
        const target = rows.map((row) => Number(row[targetKey]));
        const finite = target.filter((value) => Number.isFinite(value));
        const mean = finite.length
            ? finite.reduce((a, b) => a + b, 0) / finite.length : 0;
        const variance = finite.length
            ? finite.reduce((a, b) => a + (b - mean) ** 2, 0) / finite.length
            : 0;
        const importance = (key: string): number => {
            const list = rows.map((row) => Number(row[key]));
            const valid = list.map((value, index) => [value, target[index]])
                .filter(([value, goal]) => Number.isFinite(value)
                    && Number.isFinite(goal));
            if (!valid.length && !variance) return 0;
            const avg = valid.length
                ? valid.reduce((a, [value]) => a + value, 0) / valid.length : 0;
            let cov = 0;
            valid.forEach(([value, goal]) => {
                cov += (value - avg) * (goal - mean);
            });
            return variance
                ? Math.abs(cov / (valid.length || 1) / Math.sqrt(variance)) : 0;
        };
        let values = params.map((key) =>
            [key, importance(key)] as [string, number]);
        if (this.optChartMode === 'rank') {
            values.sort((a, b) => b[1] - a[1]);
        }
        const max = Math.max(...values.map(([, value]) => value), 1);
        host.innerHTML = `<div class="desk-strategy-opt-chart-title">${this.optChartMode === 'rank' ? '参数排名' : '参数重要性'}
            <span>${values.length} 个参数</span></div>
            <div class="desk-strategy-opt-bars">${values.map(([key, value]) =>
                `<div class="row"><span>${esc(key)}</span>
                 <i><b style="width:${Math.max(2, Math.abs(value) / max * 100)}%"></b></i>
                 <em>${value.toFixed(4)}</em></div>`).join('')}</div>`;
    }

    /**
     * 帕累托前沿图（SVG）：**自适应宽度** + 坐标轴标签 / 刻度 + 网格虚线 ✓
     *
     * 以前固定 `width=920` 还带 `Math.min(..., 0)` → 图只占左边一块、右边一大片空白，
     * x 轴还从 0 起（数值都在 5000+ 时点全挤到右边）✗
     */
    private _paretoSvg(rows: Array<Record<string, any>>,
                       axes: string[]): string {
        // ★ 1 个目标：X = **账户权益**（每次 trial 都是一次完整回测，权益有数据，
        //   能看出"收益规模 vs 目标"）；没有权益列才退回 trial 序号 ✓
        //   2 个目标：X = 目标 1、Y = 目标 2（普通二维帕累托前沿 ✓）
        const single = axes.length < 2;
        const equityKey = this._equityKey(rows);
        const trialKey = this._trialKey(rows);
        const targetKey = single ? (axes[0] || equityKey) : '';
        // ★ 单目标 = 权益（X） × 目标（Y）；如果目标**本身就是权益**
        //   （`result` / `final_equity`），X 退回 **trial 训练序号**，避免两轴
        //   一样 ✗
        const equityAxis = equityKey !== 'number' && equityKey !== targetKey;
        const xKey = single ? (equityAxis ? equityKey : trialKey) : axes[0];
        const yKey = single ? targetKey : (axes[1] || axes[0]);
        const xLabel = single
            ? (equityAxis ? '账户权益' : 'trial 序号')
            : axes[0];
        const yLabel = yKey;
        const points: Array<{ x: number; y: number; index: number }> = [];
        rows.forEach((row, index) => {
            let x = Number(row[xKey]);
            if (single && !equityAxis && !Number.isFinite(x)) x = index + 1;
            const y = Number(row[yKey]);
            if (Number.isFinite(x) && Number.isFinite(y)) {
                points.push({ x, y, index });
            }
        });
        if (!points.length) {
            return '<div class="desk-strategy-empty">没有可画的 trial</div>';
        }
        const xs = points.map((point) => point.x);
        const ys = points.map((point) => point.y);
        const span = (values: number[]) => {
            const min = Math.min(...values);
            const max = Math.max(...values);
            const pad = (max - min || Math.abs(max) || 1) * 0.12;
            return [min - pad, max + pad];
        };
        const [xMin, xMax] = span(xs);
        const [yMin, yMax] = span(ys);
        // 自适应：跟随容器宽度（最大 1600），高度按比例 ✓
        const hostWidth = this.panels.optimize?.clientWidth || 1200;
        const width = Math.max(420, Math.min(1600, hostWidth - 60));
        const height = Math.max(240, Math.min(420, Math.round(width * 0.34)));
        const left = 74;
        const right = 22;
        const top = 18;
        const bottom = 46;
        const plotW = width - left - right;
        const plotH = height - top - bottom;
        const xAt = (value: number) =>
            left + (value - xMin) / (xMax - xMin || 1) * plotW;
        const yAt = (value: number) =>
            top + (yMax - value) / (yMax - yMin || 1) * plotH;
        const tick = (value: number) => {
            const abs = Math.abs(value);
            if (abs >= 10000) return value.toFixed(0);
            if (abs >= 100) return value.toFixed(1);
            if (abs >= 1) return value.toFixed(2);
            return value.toFixed(4);
        };
        const ticks = [0, 1, 2, 3, 4];
        // ★ X 轴是**训练序号**（trial / number）时用整数刻度：
        //   以前按比例插值 → 刻度成了 `-2.36 / 6.32 / 15.00`（看着像轴搞错了 ✗）
        const indexAxis = xKey === 'trial' || xKey === 'number';
        const xTickValues: number[] = indexAxis
            ? (() => {
                const low = Math.max(0, Math.ceil(xMin));
                const high = Math.max(low, Math.floor(xMax));
                const step = Math.max(1, Math.round((high - low) / 4));
                const values: number[] = [];
                for (let value = low; value <= high; value += step) {
                    values.push(value);
                }
                return values.length ? values : [low];
            })()
            : ticks.map((index) => xMin + (xMax - xMin) * (index / 4));
        const grid = ticks.map((index) => {
            const ratio = index / 4;
            const y = top + plotH * ratio;
            return `<line x1="${left}" y1="${y.toFixed(1)}"
                    x2="${(width - right).toFixed(1)}" y2="${y.toFixed(1)}"
                    stroke="var(--desk-border)" stroke-dasharray="4 4"
                    stroke-width="1" opacity=".75"/>
                <text x="${(left - 8).toFixed(1)}" y="${(y + 3.5).toFixed(1)}"
                    text-anchor="end" class="desk-opt-tick"
                >${tick(yMax - (yMax - yMin) * ratio)}</text>`;
        }).join('') + xTickValues.map((value) => {
            const x = xAt(value);
            const label = indexAxis
                ? `#${Math.round(value)}` : tick(value);
            return `<line x1="${x.toFixed(1)}" y1="${top}"
                    x2="${x.toFixed(1)}" y2="${(top + plotH).toFixed(1)}"
                    stroke="var(--desk-border)" stroke-dasharray="4 4"
                    stroke-width="1" opacity=".55"/>
                <text x="${x.toFixed(1)}" y="${(top + plotH + 16).toFixed(1)}"
                    text-anchor="middle" class="desk-opt-tick"
                >${label}</text>`;
        }).join('');
        // 帕累托前沿：按 x 升序把「不被支配」的点连起来 ✓
        const sorted = [...points].sort((a, b) => a.x - b.x);
        const front: typeof sorted = [];
        let best = -Infinity;
        for (const point of sorted) {
            if (point.y > best) {
                front.push(point);
                best = point.y;
            }
        }
        const frontPoints = front.map((point) =>
            `${xAt(point.x).toFixed(1)},${yAt(point.y).toFixed(1)}`).join(' ');
        const frontLine = front.length > 1
            ? `<polyline fill="none" stroke="#ef5350" stroke-width="1.6"`
                + ` opacity=".85" points="${frontPoints}"/>`
            : '';
        const bestPoint = points.reduce(
            (a, b) => (b.y > a.y ? b : a), points[0]);
        const dots = points.map((point) => {
            const best = point === bestPoint;
            return `<circle cx="${xAt(point.x).toFixed(1)}"
                cy="${yAt(point.y).toFixed(1)}" r="${best ? 5 : 3.4}"
                fill="${best ? '#ef5350' : '#2196f3'}"
                opacity="${best ? 1 : .8}">
                <title>Trial ${this._trialLabel(rows, point.index)} · ${esc(rows[point.index][xKey])} / ${esc(rows[point.index][yKey])}</title>
            </circle>`;
        }).join('');
        return `<div class="desk-strategy-opt-chart-title">Pareto-front Plot
            <span>${esc(xLabel)}（X） × ${esc(yLabel)}（Y）· ${points.length} trials</span></div>
            <svg class="desk-strategy-opt-svg" viewBox="0 0 ${width} ${height}"
                preserveAspectRatio="xMidYMid meet">
            ${grid}
            <line x1="${left}" y1="${(top + plotH).toFixed(1)}"
                x2="${(width - right).toFixed(1)}" y2="${(top + plotH).toFixed(1)}"
                stroke="var(--desk-muted)" stroke-width="1"/>
            <line x1="${left}" y1="${top}" x2="${left}"
                y2="${(top + plotH).toFixed(1)}"
                stroke="var(--desk-muted)" stroke-width="1"/>
            ${frontLine}${dots}
            <text x="${(left + plotW / 2).toFixed(1)}"
                y="${(height - 8).toFixed(1)}" text-anchor="middle"
                class="desk-opt-label">${esc(xLabel)}</text>
            <text x="14" y="${(top + plotH / 2).toFixed(1)}" text-anchor="middle"
                class="desk-opt-label"
                transform="rotate(-90 14 ${(top + plotH / 2).toFixed(1)})"
            >${esc(yLabel)}</text>
            </svg>`;
    }

    /** 帕累托前沿可选的指标（目标优先，其余同行的数值列跟在后面 ✓） */
    private _paretoMetricChoices(rows: Array<Record<string, any>>): string[] {
        const skip = new Set(['number', 'trial', 'value']);
        const keys = Object.keys(rows[0] || {}).filter((key) =>
            !skip.has(key) && !/^(values_|params_)/.test(key));
        const usable = (key: string): boolean => rows.some(
            (row) => Number.isFinite(Number(row[key])));
        const targets = this.optTargets.filter(
            (name) => keys.includes(name) && usable(name));
        const rest = keys.filter((key) => usable(key)
            && !targets.includes(key));
        return [...targets, ...rest].slice(0, 12);
    }

    /** trial 训练序号列（grid 引擎叫 `trial`；optuna CSV 叫 `number` ✓） */
    private _trialKey(rows: Array<Record<string, any>>): string {
        if (rows.some((row) => Number.isFinite(Number(row['trial'])))) {
            return 'trial';
        }
        return 'number';
    }

    /**
     * tooltip 里显示的 trial（**和表格里的 `trial` 列完全一致** ✓）
     *
     * 后端 `_normalize_opt_rows()` 已经把 `trial` / `number` 统一成 **1 基**，
     * 这里直接用，不再 +1 —— 以前图上「Trial 26」对应表格里写着 25（差 1，
     * 用户找 Trial 26 找不到 ✗，2026-11-02 实测）。
     */
    private _trialLabel(rows: Array<Record<string, any>>,
                        index: number): string {
        const row = rows[index] || {};
        const trial = Number(row['trial']);
        const number = Number(row['number']);
        const value = Number.isFinite(trial) ? trial
            : (Number.isFinite(number) ? number : index + 1);
        return String(Math.round(value));
    }

    /** 「1 个目标时」的横轴：优先账户权益（`result` / `final_equity`）✓ */
    private _equityKey(rows: Array<Record<string, any>>): string {
        for (const key of ['result', 'final_equity', 'equity_last']) {
            if (rows.some((row) => Number.isFinite(Number(row[key])))) {
                return key;
            }
        }
        return 'number';
    }

    /** 当前要画的帕累托轴（用户选过就用用户的，否则默认前 3 个 ✓） */
    private _paretoAxes(rows: Array<Record<string, any>>,
                        choices: string[]): string[] {
        void rows;
        const picked = this.optParetoAxes.filter(
            (name) => choices.includes(name));
        // ★ 默认轴 = **本次优化选的目标**（1 个目标 → 就 1 个轴 → 二维
        //   权益 × 目标 ✓）；目标都没在行里出现时才退回行内的其它数值列。
        //   以前默认取 choices 前 3 个（目标 + profit + result…）→ 单目标优化
        //   也会画成三维图 ✗（2026-11-02 用户实测）
        const declared = this.optTargets.filter(
            (name) => choices.includes(name));
        const base = declared.length ? declared : choices;
        const axes = picked.length
            ? picked.slice(0, PARETO_AXES)
            : base.slice(0, PARETO_AXES);
        if (axes.length) return axes;
        // 没有任何数值目标 → 退回 trial 序号（图不能空白 ✓）
        return ['number'];
    }

    /** 轴选择（1~3 个）+ 「显示」按钮（选完点按钮确认再画 ✓） */
    private _paretoAxesHtml(choices: string[], axes: string[]): string {
        const list = choices.length ? choices : axes;
        const select = (index: number): string => {
            const chosen = axes[index] || '';
            const blank = index === 0 ? '' : '<option value="">（不使用）</option>';
            return `<label>轴 ${index + 1}<select data-pareto-axis="${index}">
                ${blank}${list.map((item) => `<option value="${esc(item)}"${
                    item === chosen ? ' selected' : ''}>${esc(item)}</option>`
                ).join('')}
            </select></label>`;
        };
        const hint = axes.length >= PARETO_AXES
            ? '三维图：拖动旋转 · 双击复位'
            : (axes.length === 1
                ? '1 个目标：横轴 = 账户权益（没有权益列则用 trial 序号）'
                : '2 个目标：二维帕累托前沿');
        return `<div class="desk-opt-axisbar">
            <span class="desk-muted">帕累托前沿轴（选 1~3 个目标）</span>
            ${[0, 1, 2].map(select).join('')}
            <button class="desk-strategy-exit" data-pareto-apply>显示</button>
            <span class="desk-muted desk-opt-axis-hint">${esc(hint)}</span>
        </div>`;
    }

    /** 三维帕累托前沿：canvas（投影 / 画法见 chart3d.ts ✓） */
    private _pareto3DHtml(rows: Array<Record<string, any>>,
                          axes: string[]): string {
        const hostWidth = this.panels.optimize?.clientWidth || 1100;
        const width = Math.max(520, Math.min(1500, hostWidth - 60));
        const height = Math.max(360, Math.min(600, Math.round(width * 0.5)));
        return `<div class="desk-strategy-opt-chart-title">3D 帕累托前沿
            <span>${axes.map((item) => esc(item)).join(' × ')}
            （X / Y / Z）· ${rows.length} trials</span></div>
            <canvas class="desk-opt-3d" data-opt-3d="1"
                width="${width}" height="${height}"
                style="width:${width}px;height:${height}px"></canvas>
            <div class="desk-muted desk-opt-3d-tip">
                拖动旋转 · 双击复位视角（点越大越靠前；红色 = 综合最优 trial）
            </div>`;
    }

    /**
     * 画三维图 + 交互（`chart3d.ts` 的纯函数 ✓）
     *
     * * 拖动旋转 / 双击复位；
     * * **悬停显示该 trial 的数值**（二维图有 `<title>`，canvas 没有 → 自己画
     *   浮层：trial 序号 + 每个轴的值 + 前几个参数 ✓）
     */
    private _bindPareto3D(host: HTMLElement,
                          rows: Array<Record<string, any>>,
                          axes: string[]): void {
        if (axes.length < PARETO_AXES) return;
        const canvas = host.querySelector(
            'canvas[data-opt-3d]') as HTMLCanvasElement | null;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const lists = axes.map((key) => rows.map((row) => Number(row[key])));
        const ranges = lists.map((list) => axisRange(list));
        const points = rows.map((row, index) => {
            const point: Point3D = {
                x: normalizeValue(Number(row[axes[0]]),
                    ranges[0][0], ranges[0][1]),
                y: normalizeValue(Number(row[axes[1]]),
                    ranges[1][0], ranges[1][1]),
                z: normalizeValue(Number(row[axes[2]]),
                    ranges[2][0], ranges[2][1]),
            };
            return { point, index };
        }).filter((item) => Number.isFinite(
            item.point.x + item.point.y + item.point.z));
        const highlight = this._bestParetoIndex(rows, axes);
        //: 鼠标悬停的 trial 下标（`undefined` = 没悬停 ✓）
        let hovered: number | undefined;
        let hoveredAt: { x: number; y: number } | null = null;
        const projected = (): LayoutPoint[] => layoutPoints({
            width: canvas.width,
            height: canvas.height,
            points,
            camera: this.optCamera,
        });
        const tooltipLines = (index: number): string[] => {
            const row = rows[index] || {};
            const lines = [`Trial ${this._trialLabel(rows, index)}`];
            axes.forEach((key) => {
                const value = Number(row[key]);
                lines.push(`${key}: ${Number.isFinite(value)
                    ? shortNumber(value) : '--'}`);
            });
            // 参数（最多 3 个，长参数名截断 ✓）
            const params = Object.keys(row)
                .filter((key) => key.startsWith('params_'))
                .slice(0, 3)
                .map((key) => `${key.slice(7)}=${row[key]}`);
            if (params.length) lines.push(params.join('  '));
            return lines;
        };
        const draw = (): void => {
            drawScene(ctx, {
                width: canvas.width,
                height: canvas.height,
                points,
                axes: [
                    { min: ranges[0][0], max: ranges[0][1], label: axes[0] },
                    { min: ranges[1][0], max: ranges[1][1], label: axes[1] },
                    { min: ranges[2][0], max: ranges[2][1], label: axes[2] },
                ],
                camera: this.optCamera,
                highlight,
                hovered,
                accent: '#2196f3',
            });
            if (hovered !== undefined && hoveredAt) {
                drawTooltip(ctx, {
                    x: hoveredAt.x,
                    y: hoveredAt.y,
                    width: canvas.width,
                    height: canvas.height,
                    lines: tooltipLines(hovered),
                    accent: '#ef5350',
                });
            }
        };
        /** 鼠标事件坐标 → canvas 内部坐标（CSS 缩放要换回来 ✓） */
        const localPoint = (event: PointerEvent | MouseEvent): {
            x: number; y: number;
        } => {
            const box = canvas.getBoundingClientRect();
            const sx = canvas.width / Math.max(1, box.width);
            const sy = canvas.height / Math.max(1, box.height);
            return {
                x: (event.clientX - box.left) * sx,
                y: (event.clientY - box.top) * sy,
            };
        };
        draw();
        // ---- 拖动旋转（记角度，切页签 / 重画保持视角 ✓）
        let dragging = false;
        let moved = false;
        let lastX = 0;
        let lastY = 0;
        const press = (event: PointerEvent): void => {
            dragging = true;
            moved = false;
            lastX = event.clientX;
            lastY = event.clientY;
            canvas.setPointerCapture?.(event.pointerId);
        };
        const move = (event: PointerEvent): void => {
            if (!dragging) {
                // 悬停：找最近的点（11px 内），有变化才重画 ✓
                const local = localPoint(event);
                const hit = hitTestPoint(projected(), local.x, local.y, 12);
                const next = hit ? hit.index : undefined;
                const at = hit ? { x: hit.sx, y: hit.sy } : null;
                if (next !== hovered) {
                    hovered = next;
                    hoveredAt = at;
                    canvas.style.cursor = hit ? 'pointer' : 'grab';
                    draw();
                } else if (at && hoveredAt
                    && (at.x !== hoveredAt.x || at.y !== hoveredAt.y)) {
                    hoveredAt = at;
                    draw();
                }
                return;
            }
            const dx = event.clientX - lastX;
            const dy = event.clientY - lastY;
            if (Math.abs(dx) + Math.abs(dy) > 1) moved = true;
            lastX = event.clientX;
            lastY = event.clientY;
            this.optCamera = {
                yaw: this.optCamera.yaw + dx * 0.01,
                pitch: Math.max(-1.35, Math.min(1.35,
                    this.optCamera.pitch + dy * 0.01)),
            };
            hovered = undefined;
            hoveredAt = null;
            draw();
        };
        const release = (): void => {
            dragging = false;
            void moved;
        };
        const leave = (): void => {
            if (hovered === undefined) return;
            hovered = undefined;
            hoveredAt = null;
            draw();
        };
        canvas.addEventListener('pointerdown', press);
        canvas.addEventListener('pointermove', move);
        canvas.addEventListener('pointerup', release);
        canvas.addEventListener('pointercancel', release);
        canvas.addEventListener('pointerleave', leave);
        canvas.addEventListener('dblclick', () => {
            this.optCamera = { yaw: rad(-35), pitch: rad(22) };
            draw();
        });
    }

    /** 三维图的「综合最优」：按各目标权重方向的归一化得分最大 ✓ */
    private _bestParetoIndex(rows: Array<Record<string, any>>,
                             axes: string[]): number | undefined {
        const lists = axes.map((key) => rows.map((row) => Number(row[key])));
        const ranges = lists.map((list) => axisRange(list));
        const weights = axes.map((key) => {
            const index = this.optTargets.indexOf(key);
            return index >= 0 ? this._weightFor(index) : 1;
        });
        let best: number | undefined;
        let bestScore = -Infinity;
        rows.forEach((row, index) => {
            let score = 0;
            let ok = true;
            axes.forEach((key, axis) => {
                const value = Number(row[key]);
                if (!Number.isFinite(value)) { ok = false; return; }
                score += weights[axis] * normalizeValue(
                    value, ranges[axis][0], ranges[axis][1]);
            });
            if (ok && score > bestScore) {
                bestScore = score;
                best = index;
            }
        });
        return best;
    }

    private _exportOpt(): void {
        if (!this.optRows.length) return;
        const columns = Object.keys(this.optRows[0]);
        const lines = [columns.join(',')].concat(this.optRows.map((row) =>
            columns.map((key) => `"${String(row[key] ?? '').replace(/"/g, '""')}"`).join(',')));
        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'optimization_trials.csv';
        link.click();
        URL.revokeObjectURL(link.href);
    }

    private _showError(message: string): void {
        const html = `<div class="desk-strategy-error"><b>回测失败</b><p>${esc(message)}</p></div>`;
        this.panels.record.innerHTML = html;
        if (this.panels.optimize) this.panels.optimize.innerHTML = html;
        this._showTab('record');
    }


}

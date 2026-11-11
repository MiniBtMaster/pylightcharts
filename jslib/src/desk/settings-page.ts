/**
 * SettingsPage —— 「设置」页（复刻 miniqt 设置界面 ✓）
 *
 * 结构（`tradingview/设置页面样式*.png`）：
 *
 *   ┌ 左侧导航 ────────┬ 右侧内容 ──────────────────────────────┐
 *   │ 系统设置         │  本地文件 / 个性化 / 关于                │
 *   │ 图表设置         │  图表配置 / 图表颜色                     │
 *   └──────────────────┴────────────────────────────────────────┘
 *
 * 所有值都通过 `onSetting(key, value)` 交给 `DeskApp` → 后端 `set_setting`
 * 落盘（`~/.minibt/desk_user_prefs.json`），重开也在 ✓。
 * 数据目录 / 帮助 / 反馈这些动作走 `onCommand`（`open_data_dir` / `open_url`）。
 */
import { LINE_COLORS } from './indicator-settings';
import { renderMiniChart } from './mini-chart';
import { CROSSHAIR_PRESETS } from './crosshair';

export type SettingsTheme = 'light' | 'dark';

export interface SettingsValues {
    theme?: SettingsTheme;
    theme_accent?: string;
    ui_zoom?: number;
    chart_font_size?: number;
    chart_history?: number;
    chart_data_length?: number;
    chart_color_up?: string;
    chart_color_down?: string;
    chart_color_crosshair?: string;
    chart_crosshair_style?: string;
    /** 持仓线（全局开关，默认开 ✓） */
    position_line?: boolean;
    /** 挂单线（全局开关，默认开 ✓） */
    order_line?: boolean;
    /** 指标 / 策略图表更新频率（ms，10..3000） */
    indicator_refresh_interval_ms?: number;
    /** VP / 表格只在新 K 线更新 */
    indicator_custom_new_bar?: boolean;
    /** 运行日志：终端输出（默认开 ✓） */
    log_terminal?: boolean;
    editor_format_on_save?: boolean;
    /** 编辑器：手动指定 minibt 路径（默认关；找不到 minibt 时用来追踪注释） */
    editor_minibt_path_enabled?: boolean;
    editor_minibt_path?: string;
    /** 运行日志：程序内输出（日志页 / 底部面板） */
    log_ui?: boolean;
    /** 编辑器字号基准（px；跟界面缩放相乘 ✓ v1.3.7） */
    editor_font_size?: number;
    /** 终端（v1.3.7-2：AI 对话改在终端里启动 ✓） */
    terminal_shell?: string;
    terminal_ai_command?: string;
    /** AI 助手（v1.3.7-4：内置会话 + 对话，任意 OpenAI 兼容接口 ✓） */
    ai_base_url?: string;
    ai_model?: string;
    ai_api_key?: string;
    ai_tools?: boolean;
    ai_max_turns?: number;
    /** PI 操控 desk：允许（默认开）/ 允许下单（默认关）✓ */
    ai_desk_allow?: boolean;
    ai_desk_order?: boolean;
    scheduler_enabled?: boolean;
    /** PI 悬浮球背景色（`''` = 默认配色） */
    pi_float_color?: string;
    /** 本机桥 / 外部 MCP 工具（默认都开 ✓） */
    ai_mcp_bridge?: boolean;
    ai_mcp_tools?: boolean;
    ai_price_in?: string;
    ai_price_out?: string;
    ai_context_window?: string;
    /** 图上事件圆点：true = 全部事件（默认只画中 / 高重要性） */
    chart_events_all?: boolean;
    /** 指标选择器默认分组：all / overlay / sub */
    indicator_overlay_filter?: string;
    /** 播放条只显示有报价的合约 */
    ticker_only_quoted?: boolean;
    /** 首页自选默认分组：recent / all / favorites */
    watch_default_group?: string;
}

/** 「设置 → 模拟账户」的数据（后端 `sim_analysis` 补丁 ✓） */
export interface SimAnalysis {
    initial_cash?: number;
    balance?: number;
    realized?: number;
    commission?: number;
    trades?: number;
    closes?: number;
    wins?: number;
}

export interface SimPayload {
    settings?: {
        initial_cash?: number;
        fee_mode?: string;
        fee_value?: number;
    };
    summary?: SimAnalysis;
    equity?: Array<[string, number]>;
    series?: Array<{ name: string; color?: string;
                     points: Array<[string, number]> }>;
    table?: { columns?: string[]; rows?: string[][] };
}

/** 初始现金预设（下拉选了直接填进输入框，也可以手动填任意值 ✓） */
export const CASH_PRESETS: Array<{ value: number; label: string }> = [
    { value: 100000, label: '10 万' },
    { value: 200000, label: '20 万' },
    { value: 300000, label: '30 万' },
    { value: 500000, label: '50 万' },
    { value: 800000, label: '80 万' },
    { value: 1000000, label: '100 万' },
];

/** 手续费模式（只能设置其中之一 ✓） */
export const FEE_MODES: Array<{ value: string; label: string }> = [
    { value: 'fixed', label: '固定手续费用（每手）' },
    { value: 'percent', label: '百分比手续费用（成交额 %）' },
];

export interface SettingsPageOptions {
    theme: SettingsTheme;
    values: SettingsValues;
    version?: string;
    /** 改一个设置项（落盘 + 立即生效 ✓） */
    onSetting: (key: string, value: unknown) => void;
    /** 后端动作：`open_url` / `open_data_dir` ✓ */
    onCommand: (cmd: string, payload?: unknown) => void;
    /** 轻提示（告警通道保存 / 测试用 ✓） */
    onToast?: (level: string, text: string) => void;
}

/** 主题色候选（miniqt「主题色」下拉 ✓） */
export const ACCENTS: Array<{ value: string; label: string }> = [
    { value: '', label: '默认颜色' },
    { value: '#2962ff', label: '蓝色' },
    { value: '#1f9d55', label: '绿色' },
    { value: '#9c27b0', label: '紫色' },
    { value: '#ff9800', label: '橙色' },
    { value: '#e91e63', label: '玫红' },
];

/** 界面缩放（miniqt 有「跟随系统」，这里给固定档位 + 跟随 ✓） */
export const ZOOMS: Array<{ value: number; label: string }> = [
    { value: 0, label: '跟随系统' },
    { value: 0.8, label: '80%' },
    { value: 0.9, label: '90%' },
    { value: 1, label: '100%' },
    { value: 1.1, label: '110%' },
    { value: 1.25, label: '125%' },
];

/** 图表数据长度候选 ✓ */
export const LENGTHS: Array<{ value: number; label: string }> = [
    { value: 500, label: '500' },
    { value: 1000, label: '1000' },
    { value: 2000, label: '2000' },
    { value: 5000, label: '5000' },
];

/** 图表历史长度候选（要 ≥ 数据长度 ✓） */
export const HISTORIES: Array<{ value: number; label: string }> = [
    { value: 1000, label: '1000' },
    { value: 2000, label: '2000' },
    { value: 5000, label: '5000' },
    { value: 10000, label: '10000' },
];

const STYLE_ID = 'desk-settings-style';

const CSS = `
.desk-settings { position: absolute; inset: 0; display: flex;
    background: var(--desk-bg); color: var(--desk-text); overflow: hidden; }
.desk-settings-nav { flex: 0 0 210px; padding: 14px 10px; overflow-y: auto;
    border-right: 1px solid var(--desk-border); }
.desk-settings-group { color: var(--desk-muted); font-size: 10.5px;
    margin: 10px 8px 4px; letter-spacing: .4px; }
.desk-settings-link { display: flex; align-items: center; gap: 8px;
    padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 12.5px;
    user-select: none; }
.desk-settings-link:hover { background: var(--desk-hover); }
.desk-settings-link.on { background: var(--desk-active); color: var(--desk-accent);
    font-weight: 600; }
.desk-settings-body { flex: 1 1 auto; overflow-y: auto; padding: 18px 26px 40px; }
.desk-settings-title { font-size: 20px; font-weight: 600; margin: 0 0 14px; }
.desk-settings-section { font-size: 14px; font-weight: 600; margin: 18px 0 8px; }
.desk-settings-color { width: 34px; min-width: 34px; padding: 0 2px;
    cursor: pointer; }
.desk-settings-input { height: 28px; padding: 0 8px; border-radius: 6px;
    border: 1px solid var(--desk-border); background: var(--desk-bg);
    color: var(--desk-text); font-size: 12px; }
.desk-settings-actions { display: flex; gap: 10px; margin: 14px 0 4px; }
.desk-settings-inline { display: inline-flex; align-items: center; gap: 8px; }
.desk-settings-cards { display: grid; gap: 10px; margin: 6px 0 4px;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
.desk-settings-card { border: 1px solid var(--desk-border); border-radius: 8px;
    padding: 10px 12px; background: var(--desk-panel); }
.desk-settings-card-title { font-size: 11px; color: var(--desk-muted); }
.desk-settings-card-value { font-size: 18px; font-weight: 600; margin-top: 4px; }
.desk-settings-card-value.up { color: var(--desk-up, #f23645); }
.desk-settings-card-value.down { color: var(--desk-down, #089981); }
.desk-settings-chart { border: 1px solid var(--desk-border); border-radius: 8px;
    padding: 8px 6px; background: var(--desk-panel); margin-bottom: 8px; }
.desk-mini-chart-svg { display: block; }
.desk-mini-chart-grid { stroke: var(--desk-border); stroke-width: 1; opacity: .55; }
.desk-mini-chart-zero { stroke: var(--desk-muted); stroke-width: 1;
    stroke-dasharray: 3 3; }
.desk-mini-chart-axis { fill: var(--desk-text); font-size: 12px;
    font-family: inherit; font-weight: 400; }
.desk-mini-chart-empty { color: var(--desk-muted); font-size: 12px;
    padding: 26px 8px; text-align: center; }
.desk-mini-chart-legend { display: flex; flex-wrap: wrap; gap: 10px;
    padding: 6px 8px 2px; }
.desk-mini-chart-chip { display: inline-flex; align-items: center; gap: 5px;
    font-size: 12px; color: var(--desk-text); }
.desk-mini-chart-chip i { width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; }
.desk-settings-table { border: 1px solid var(--desk-border); border-radius: 8px;
    overflow: hidden; }
.desk-settings-table-row { display: grid; gap: 6px; padding: 7px 12px;
    grid-template-columns: 1.3fr .8fr .8fr .8fr 1fr 1fr 1fr; font-size: 12px; }
.desk-settings-table-row.head { background: var(--desk-hover);
    color: var(--desk-muted); font-size: 11px; }
.desk-settings-table-row span.up { color: var(--desk-up, #f23645); }
.desk-settings-table-row span.down { color: var(--desk-down, #089981); }
.desk-settings-row { display: flex; align-items: center; gap: 12px;
    padding: 10px 12px; border: 1px solid var(--desk-border); border-radius: 8px;
    background: var(--desk-panel); margin-bottom: 8px; }
.desk-settings-icon { width: 22px; height: 22px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    color: var(--desk-muted); }
.desk-settings-text { flex: 1 1 auto; min-width: 0; }
.desk-settings-name { font-size: 12.5px; }
.desk-settings-desc { color: var(--desk-muted); font-size: 11px;
    margin-top: 2px; }
.desk-settings-control { flex: 0 0 auto; display: flex; align-items: center;
    gap: 8px; }
.desk-settings-select, .desk-settings-input {
    height: 26px; min-width: 96px; padding: 0 6px; border-radius: 4px;
    border: 1px solid var(--desk-border); background: var(--desk-bg);
    color: var(--desk-text); font-size: 12px; }
/* 路径输入（编辑器 → minibt 路径）宽一点，禁用时淡一点 ✓ */
.desk-settings-row .desk-settings-input[type="text"] { width: 320px;
    min-width: 220px; }
.desk-settings-input:disabled { opacity: .55; cursor: not-allowed; }
.desk-settings-btn { height: 26px; padding: 0 12px; border-radius: 4px;
    border: 1px solid var(--desk-border); background: var(--desk-hover);
    color: var(--desk-text); font-size: 12px; cursor: pointer; }
.desk-settings-btn.primary { background: var(--desk-accent); color: #fff;
    border-color: var(--desk-accent); }
.desk-settings-para { font-size: 11.5px; line-height: 1.6; color: var(--desk-muted);
    margin: 2px 0 10px; white-space: pre-wrap; }
.desk-settings-para.ok { color: #26a69a; }
.desk-settings-para.err { color: #ef5350; }
.desk-settings-btn:hover { filter: brightness(1.08); }
.desk-settings-switch { position: relative; width: 38px; height: 20px;
    border-radius: 10px; background: var(--desk-border); cursor: pointer;
    transition: background .15s ease; }
.desk-settings-switch.on { background: var(--desk-accent); }
.desk-settings-switch::after { content: ''; position: absolute; top: 2px;
    left: 2px; width: 16px; height: 16px; border-radius: 50%;
    background: #fff; transition: transform .15s ease; }
.desk-settings-switch.on::after { transform: translateX(18px); }
.desk-settings-slider { width: 150px; accent-color: var(--desk-accent); }
.desk-settings-slider-value { min-width: 26px; text-align: right;
    font-variant-numeric: tabular-nums; font-size: 12px; }
.desk-settings-colors { display: flex; gap: 4px; }
.desk-settings-chip { width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid transparent; cursor: pointer; }
.desk-settings-chip.on { border-color: var(--desk-text); }
.desk-settings-empty { color: var(--desk-muted); font-size: 12px; }
`;

const ICONS: Record<string, string> = {
    bell: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M6 16V11a6 6 0 '
        + '0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
    folder: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M3 7h6l2 2h10v10H3z"/>'
        + '</svg>',
    theme: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/>'
        + '<path d="M12 4v16"/></svg>',
    money: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/>'
        + '<path d="M12 8v8"/><path d="M9 10h4a1.5 1.5 0 010 3h-3"/></svg>',
    palette: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/>'
        + '<circle cx="9" cy="10" r="1.2"/><circle cx="15" cy="10" r="1.2"/>'
        + '<circle cx="12" cy="15" r="1.2"/></svg>',
    zoom: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><rect x="4" y="5" width="16" '
        + 'height="14" rx="2"/><path d="M9 12h6M12 9v6"/></svg>',
    chart: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M4 19V5M4 19h16"/>'
        + '<path d="M8 15l3-4 3 3 4-6"/></svg>',
    reset: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M4 12a8 8 0 1 1 3 6"/>'
        + '<path d="M4 5v5h5"/></svg>',
    up: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M12 20V4"/>'
        + '<path d="M6 10l6-6 6 6"/></svg>',
    down: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M12 4v16"/>'
        + '<path d="M6 14l6 6 6-6"/></svg>',
    cursor: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M5 3l14 8-6 1-2 6z"/>'
        + '</svg>',
    help: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/>'
        + '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.3c-.7.4-.6 1.2-.6 1.7"/>'
        + '<circle cx="12" cy="16.6" r=".8" fill="currentColor"/></svg>',
    feedback: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><path d="M4 5h16v11H9l-5 4z"/>'
        + '</svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        + 'stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/>'
        + '<path d="M12 11v6"/><circle cx="12" cy="7.6" r=".9" fill="currentColor"/>'
        + '</svg>',
};

/** 左侧导航：分组 → 页面 ✓ */
/** AI 设置在本机的兜底缓存（后端没存成功也不丢 ✓） */
const AI_STORE = 'desk.ai.';

function localAi(key: string): string {
    try {
        return window.localStorage.getItem(AI_STORE + key) || '';
    } catch {
        return '';
    }
}

function saveLocalAi(key: string, value: string): void {
    try {
        if (value === '') window.localStorage.removeItem(AI_STORE + key);
        else window.localStorage.setItem(AI_STORE + key, value);
    } catch {
        /* 隐私模式忽略 */
    }
}

const NAV: Array<{ group: string; items: Array<{ key: string; label: string }> }> = [
    { group: '系统设置', items: [
        { key: 'files', label: '本地文件' },
        { key: 'personal', label: '个性化' },
        { key: 'info-sources', label: '资讯数据源' },
        { key: 'alerts', label: '告警通道' },
        { key: 'about', label: '关于' },
    ] },
    { group: '模拟账户', items: [
        { key: 'sim', label: '模拟账户' },
    ] },
    { group: '图表设置', items: [
        { key: 'chart-config', label: '图表配置' },
        { key: 'chart-colors', label: '图表颜色' },
    ] },
];

export class SettingsPage {
    readonly element: HTMLDivElement;
    private readonly body: HTMLDivElement;
    private readonly links = new Map<string, HTMLDivElement>();
    private options: SettingsPageOptions;
    private active = 'personal';
    /** 「模拟账户」的分析数据（曲线 / 统计表 ✓） */
    private sim: SimPayload = {};
    /** 后端刚推数据回来时的重画：不要再请求一次（否则死循环 ✗） */
    private quiet = false;
    /** 有"待重画"（用户正在输入时跳过的重画 ✓） */
    private pendingRepaint = false;
    /** 最近一次提交的键（用来确认后端到底存了没有 ✓） */
    private lastKey = '';
    /** PI 操控 desk 的审计日志显示区（设置页 ✓） */
    private auditBox: HTMLPreElement | null = null;
    /** 资讯数据源状态（`info_status` 补丁 ✓） */
    private infoStatus: Record<string, unknown> = {};
    /** 告警通道配置 + 历史（`ops` / `ops_notify` 补丁 ✓ v1.3.7-91） */
    private notify: Record<string, any> = {};
    /** 账户净值序列（`ops_equity` 补丁 ✓ v1.3.7-95） */
    private equity: Record<string, any> = {};

    constructor(options: SettingsPageOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-settings';

        const nav = document.createElement('div');
        nav.className = 'desk-settings-nav';
        for (const group of NAV) {
            const title = document.createElement('div');
            title.className = 'desk-settings-group';
            title.textContent = group.group;
            nav.appendChild(title);
            for (const item of group.items) {
                const link = document.createElement('div');
                link.className = 'desk-settings-link';
                link.innerHTML = `<span class="desk-settings-icon">${
                    ICONS[item.key === 'files' ? 'folder'
                        : item.key === 'personal' ? 'theme'
                        : item.key === 'sim' ? 'money'
                        : item.key === 'alerts' ? 'bell'
                        : item.key === 'about' ? 'info' : 'chart']}</span>`;
                const text = document.createElement('span');
                text.textContent = item.label;
                link.appendChild(text);
                link.addEventListener('click', () => this.show(item.key));
                nav.appendChild(link);
                this.links.set(item.key, link);
            }
        }
        this.body = document.createElement('div');
        this.body.className = 'desk-settings-body';
        this.element.append(nav, this.body);
        this.show(this.active);
    }

    /** 后端推来的资讯数据源状态（AkShare 版本 / 缓存条数 ✓） */
    setInfoStatus(payload: Record<string, unknown>): void {
        this.infoStatus = payload || {};
        if (this.active !== 'info-sources') return;
        this.quiet = true;
        try {
            this.show('info-sources');
        } finally {
            this.quiet = false;
        }
    }

    /** 告警通道（`ops` 快照里的 notify / `ops_notify` 补丁）✓ */
    setNotify(payload: Record<string, any>): void {
        const notify = (payload && (payload.notify || payload)) || {};
        this.notify = { ...this.notify, ...notify };
        if (payload && Array.isArray(payload.alert_rules)
                && payload.alert_rules.length) {
            this.notify.alert_rules = payload.alert_rules;
        }
        if (payload && payload.alert_settings
                && typeof payload.alert_settings === 'object') {
            this.notify.alert_settings = payload.alert_settings;
        }
        if (this.active !== 'alerts') return;
        this.quiet = true;
        try {
            this.show('alerts');
        } finally {
            this.quiet = false;
        }
    }

    /** 净值曲线数据（`ops_equity` 补丁）✓ */
    setEquity(payload: Record<string, any>): void {
        this.equity = payload || {};
        if (this.active !== 'alerts') return;
        this.quiet = true;
        try {
            this.show('alerts');
        } finally {
            this.quiet = false;
        }
    }

    /** 后端推来的审计日志 → 填进设置页 ✓ */
    setAudit(rows: Array<Record<string, unknown>>): void {
        if (!this.auditBox) return;
        if (!rows.length) {
            this.auditBox.textContent = '（还没有调用记录）';
            return;
        }
        this.auditBox.textContent = rows.map((row) => {
            const args = row.args ? JSON.stringify(row.args) : '';
            const result = String(row.result || '')
                .replace(/\s+/g, ' ').slice(0, 80);
            return `${String(row.at || '')}  ${String(row.tool || '')}`
                + `  ${args.slice(0, 60)}` + '\n' + `    → ${result}`;
        }).join('\n');
    }

    /** 后端推来的设置（主题 / 缩放等）→ 重画 ✓ */
    setValues(values: SettingsValues): void {
        this.options = { ...this.options, values };
        // ★ 用户正在输入 → **不要重画**（以前整页重建会把刚敲的字冲掉，
        //   若后端没存成功就表现为"写完不显示" ✗ 用户 2026-11-08 实测）
        const active = document.activeElement as HTMLElement | null;
        if (active && this.element.contains(active)
            && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) {
            this.pendingRepaint = true;
            return;
        }
        this.pendingRepaint = false;
        this.show(this.active);
    }

    /** 记下最近提交的设置键（后端回推时对比，确认真的存了 ✓） */
    rememberSetting(key: string): void {
        this.lastKey = key;
    }

    /** 最近提交的键（测试 / 调试用 ✓） */
    get lastSettingKey(): string {
        return this.lastKey;
    }

    /** 重新画当前分区（设置页切回来 / 定时器用 ✓） */
    repaint(): void {
        if (!this.pendingRepaint) return;
        const active = document.activeElement as HTMLElement | null;
        if (active && this.element.contains(active)
            && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) {
            return;
        }
        this.pendingRepaint = false;
        this.show(this.active);
    }

    /** 后端 `sim_analysis` 补丁 → 刷新「模拟账户」分析 ✓ */
    setSim(payload: SimPayload): void {
        this.sim = payload || {};
        if (this.active !== 'sim') return;
        this.quiet = true;
        try {
            this.show('sim');
        } finally {
            this.quiet = false;
        }
    }

    setTheme(theme: SettingsTheme): void {
        this.options = { ...this.options, theme };
        this.show(this.active);
    }

    get current(): string {
        return this.active;
    }

    show(key: string): void {
        this.active = key;
        for (const [name, link] of this.links) {
            link.classList.toggle('on', name === key);
        }
        this._ensureStyle();
        this.body.textContent = '';
        switch (key) {
            case 'files': this._renderFiles(); break;
            case 'about': this._renderAbout(); break;
            case 'chart-config': this._renderChartConfig(); break;
            case 'chart-colors': this._renderChartColors(); break;
            case 'sim': this._renderSim(); break;
            case 'info-sources': this._renderInfoSources(); break;
            case 'alerts': this._renderAlerts(); break;
            default: this._renderPersonal(); break;
        }
    }

    // ------------------------------------------------------------ 本地文件
    private _renderFiles(): void {
        this._title('本地文件');
        this._section('数据目录');
        this._row('folder', 'minibt 本地数据',
            'K 线缓存、模拟盘账本、布局 / 指标设置都保存在这里',
            this._button('打开文件夹', () => {
                this.options.onCommand('open_data_dir', {});
            }, true));
        this._section('导出');
        this._row('feedback', '导出历史',
            '最近导出的 CSV（也可以在看盘窗口的「导出历史」里打开）',
            this._button('查看最近导出', () => {
                this.options.onCommand('exports', {});
            }));
    }

    // ------------------------------------------------------------ 个性化
    private _renderPersonal(): void {
        const v = this.options.values || {};
        this._title('个性化');
        this._section('外观');
        this._row('theme', '应用主题', '调整你的应用的外观',
            this._select(
                [{ value: 'dark', label: '深色' },
                 { value: 'light', label: '浅色' }],
                String(v.theme || this.options.theme || 'dark'),
                (value) => this.options.onSetting('app_theme', value)));
        this._row('palette', '主题色', '调整你的应用的主题色（支持自定义颜色）',
            this._accentControl(String(v.theme_accent || '')));
        // ★ 界面缩放是**整个桌面端**的设置（不是编辑器专属）→ 2026-11-05
        //   用户要求从「编辑器」搬到「外观」，默认 **100%** ✓
        this._row('zoom', '界面缩放', '调整整个 minibt desk 的小部件和字体大小',
            this._select(
                ZOOMS.map((item) => ({ value: String(item.value),
                    label: item.label })),
                String(v.ui_zoom === undefined || v.ui_zoom === null
                    ? 1 : Number(v.ui_zoom)),
                (value) => this.options.onSetting('ui_zoom',
                    Number(value) || 0)));
        // ★ 运行日志输出位置（P92）：终端 / 程序内 ✓
        this._section('运行日志');
        this._row('log_terminal', '终端输出',
            '把运行日志打印到启动 minibt desk 的终端（界面卡住也能复制 ✓）',
            this._switch(v.log_terminal !== false, (checked) =>
                this.options.onSetting('log_terminal', checked)));
        this._row('log_ui', '程序内输出',
            '同时写进「运行日志」页和看盘窗口底部面板',
            this._switch(v.log_ui !== false, (checked) =>
                this.options.onSetting('log_ui', checked)));
        // ★ 编辑器：保存时自动格式化（P127）
        this._section('指标与自选');
        this._row('indicator_filter', '指标选择器默认分组',
            '每次打开指标选择器时默认停在哪个分组',
            this._select(
                [{ value: 'all', label: '全部指标' },
                 { value: 'overlay', label: '主图叠加' },
                 { value: 'sub', label: '副图' }],
                String(v.indicator_overlay_filter || 'all'),
                (value) => this.options.onSetting(
                    'indicator_overlay_filter', value)));
        this._row('ticker_only', '播放条只显示有报价的合约',
            '底部播放条隐藏暂无报价的合约',
            this._switch(v.ticker_only_quoted === true,
                (checked) => this.options.onSetting(
                    'ticker_only_quoted', checked)));
        this._row('watch_default', '自选默认分组',
            '打开首页时默认选中的自选分组',
            this._select(
                [{ value: 'recent', label: '最近打开' },
                 { value: 'all', label: '全部自选' },
                 { value: 'favorites', label: '收藏' }],
                String(v.watch_default_group || 'recent'),
                (value) => this.options.onSetting(
                    'watch_default_group', value)));

        this._section('编辑器');
        this._row('editor_format_on_save', '保存时自动格式化',
            'Ctrl+S 保存前先用 ruff / black 格式化（可 Ctrl+Z 撤销 ✓）',
            this._switch(!!v.editor_format_on_save, (checked) =>
                this.options.onSetting('editor_format_on_save', checked)));
        this._row('editor_font_size', '编辑器字号',
            '编辑器代码字号基准（px），会按「界面缩放」等比放大 ✓',
            this._select(
                [{ value: '11', label: '11' }, { value: '12', label: '12' },
                 { value: '12.5', label: '12.5（默认）' },
                 { value: '13', label: '13' }, { value: '14', label: '14' },
                 { value: '16', label: '16' }, { value: '18', label: '18' }],
                String(v.editor_font_size || '12.5'),
                (value) => this.options.onSetting('editor_font_size',
                                                  Number(value) || 12.5)));
        // ★ 终端（v1.3.7-2）：编辑器底部的 shell；AI 对话也在终端里启动 ✓
        this._section('终端（编辑器）');
        this._row('terminal_shell', 'Shell 命令',
            '留空 = 系统默认（Windows 用 cmd.exe；Linux/macOS 用 $SHELL）',
            this._textInput(String(v.terminal_shell || ''),
                (value) => this.options.onSetting('terminal_shell', value),
                'cmd.exe /Q /K'));
        this._row('terminal_ai_command', 'AI CLI 命令',
            '在终端里手动输入的命令（例如 pi / claude / codex / '
            + 'ollama run qwen2.5-coder）；留空 = pi',
            this._textInput(String(v.terminal_ai_command || ''),
                (value) => this.options.onSetting('terminal_ai_command', value),
                'pi'));
        // ★ PI 操控 desk（v1.3.7-26）：总开关 + 下单开关 + 审计日志 ✓
        this._section('PI 操控 desk');
        this._row('ai_desk_allow', '允许 PI 操控 desk',
            '打开后，对话里可以让 PI 切合约 / 加指标 / 布局 / 跑回测；'
            + '关掉则只能看（只读工具仍然可用）',
            this._switch(v.ai_desk_allow !== false, (checked) =>
                this.options.onCommand('ai_desk_save', { allow: checked })));
        this._row('ai_desk_order', '允许下单 / 策略实盘',
            '**默认关闭**：打开后 PI 才能在用户二次确认后真实下单、'
            + '启动策略实盘（只允许限价单）',
            this._switch(v.ai_desk_order === true, (checked) =>
                this.options.onCommand('ai_desk_save', { order: checked })));
        // ★ v1.3.7-79：定时任务总开关（急停用；关掉后一个都不跑 ✓）
        this._section('定时任务');
        this._row('scheduler_enabled', '启用定时任务',
            '总开关：关掉后运维页里所有定时任务都不会跑（单个任务也能在'
            + '运维页停用）。任务可以调 MCP 工具、也可以定时发给 AI',
            this._switch(v.scheduler_enabled !== false, (checked) =>
                this.options.onSetting('scheduler_enabled', checked)));
        // ★ 悬浮球背景色（用户 2026-11-08：可自选 + 持久化 + 恢复默认 ✓）
        const colorBox = document.createElement('div');
        colorBox.className = 'desk-settings-buttons';
        const picker = document.createElement('input');
        picker.type = 'color';
        picker.className = 'desk-settings-color';
        picker.value = /^#[0-9a-fA-F]{6}$/.test(String(v.pi_float_color || ''))
            ? String(v.pi_float_color) : '#1f8f8f';
        picker.title = 'PI 悬浮球背景色';
        picker.addEventListener('input', () => {
            this.options.onSetting('pi_float_color', picker.value);
        });
        colorBox.append(picker, this._button('默认颜色', () => {
            this.options.onSetting('pi_float_color', '');
            this.show(this.active);
        }));
        this._row('pi_float_color', '悬浮球背景色',
            '设置后 PI 悬浮小球（右下角 π）用这个颜色；'
            + '点「默认颜色」恢复主题配色',
            colorBox);
        this._row('pi_cleanup', '清理重复会话',
            '同一句话反复发送会各建一个会话（老版本的副作用）→ '
            + '这里删掉「空会话」和「内容完全重复」的（每组保留最新一条）',
            this._button('清理…', () => {
                if (!window.confirm('清理空会话 / 重复会话？'
                    + '（每组保留最新一条）')) return;
                this.options.onCommand('pi_cleanup', {});
            }));
        this._row('ai_mcp_bridge', 'MCP 本机桥',
            '在 127.0.0.1 开一个只读本机的端口（带 token）：外部程序 / MCP '
            + '客户端可以操控**这个** desk 窗口（默认开）',
            this._switch(v.ai_mcp_bridge !== false, (checked) =>
                this.options.onSetting('ai_mcp_bridge', checked)));
        this._row('ai_mcp_tools', '接入外部 MCP 工具',
            '把「mcp.json」里其它 server 的工具挂进 PI 对话（名字形如 '
            + 'mcp__server__tool；改完 1 分钟内生效）',
            this._switch(v.ai_mcp_tools !== false, (checked) =>
                this.options.onSetting('ai_mcp_tools', checked)));
        const auditButtons = document.createElement('div');
        auditButtons.className = 'desk-settings-buttons';
        auditButtons.append(
            this._button('查看最近 200 条', () => {
                this.options.onCommand('ai_audit', { limit: 200 });
            }),
            this._button('清空', () => {
                if (!window.confirm('清空审计日志？')) return;
                this.options.onCommand('ai_audit_clear', {});
            }));
        this._row('ai_audit', '审计日志',
            '每次 PI 调用 desk 工具都会记一条（密码 / key 已脱敏）',
            auditButtons);
        this.auditBox = document.createElement('pre');
        this.auditBox.className = 'desk-settings-audit';
        this.auditBox.textContent = '（点上面的「查看最近 200 条」）';
        this._row('ai_audit_list', '最近调用',
            '新的在前；只删日志文件里的记录，不影响其它数据',
            this.auditBox);
        // ★ 手动指定 minibt 路径（默认**不启用**）：编辑器（jedi）找不到
        //   minibt 时，用它来给悬停 / 补全找注释 ✓
        this._row('editor_minibt_path_enabled', '手动指定 minibt 路径',
            '默认自动识别（已安装 / 打开的仓库）。识别不到注释时打开它，'
            + '用下面填的路径追踪',
            this._switch(!!v.editor_minibt_path_enabled, (checked) =>
                this.options.onSetting('editor_minibt_path_enabled', checked)));
        this._row('editor_minibt_path', 'minibt 路径',
            '仓库根（…/owen）或包目录（…/owen/minibt）都行；'
            + '回车保存，留空 = 不指定',
            this._pathInput(String(v.editor_minibt_path || ''),
                !!v.editor_minibt_path_enabled,
                (value) => this.options.onSetting('editor_minibt_path', value)));
    }

    // ------------------------------------------------------------ 关于
    // ------------------------------------------------------------ 资讯数据源
    private _renderInfoSources(): void {
        const data = this.infoStatus;
        const installed = data.installed !== false;
        const cache = (data.cache || {}) as Record<string, unknown>;
        const last = Number(cache.last_fetch || 0);
        this._title('资讯数据源');
        this._section('AkShare（免费、无需 token）');
        this._row('info', 'AkShare',
            installed
                ? `已安装 ${String(data.version || '')}`
                + '　·　快讯 / 要闻 / 财经日历 / 个股新闻都从这里取'
                : '未安装 —— 在终端执行：pip install "minibt[news]"',
            this._button('重新检测', () => {
                this.options.onCommand('info_status', {});
            }));
        this._row('folder', '本地缓存',
            `资讯 ${String(cache.news || 0)} 条 · 日历 `
            + `${String(cache.calendar || 0)} 条`
            + (last ? `　·　上次抓取 ${new Date(last * 1000)
                .toLocaleString('zh-CN', { hour12: false })}` : ''),
            this._button('清空缓存', () => {
                this.options.onCommand('info_clear', {});
            }));
        if (String(data.last_error || '')) {
            this._section('上次抓取错误');
            const box = document.createElement('pre');
            box.className = 'desk-settings-audit';
            box.textContent = String(data.last_error);
            this.body.appendChild(box);
        }
        this._section('说明');
        const note = document.createElement('div');
        note.className = 'desk-settings-note';
        note.innerHTML = '资讯数据全部来自 <b>AkShare</b> 封装的数据源'
            + '（新浪 / 东方财富 / 财新 / 百度股市通 / 上期能源）；'
            + '本机只缓存「标题 + 时间 + 来源 + 链接 + 短摘要」，不存正文。';
        this.body.appendChild(note);
    }

    // ------------------------------------------------------------ 告警通道
    private _renderAlerts(): void {
        const data = this.notify || {};
        const config = (data.config || {}) as Record<string, any>;
        const wecom = config.wecom || {};
        const xtuis = config.xtuis || {};
        const email = config.email || {};
        const hook = config.webhook || {};
        // 打开这一页时向后端要一次（后端刚推回来的那次不要再要 ✗）
        if (!this.quiet) {
            this.options.onCommand('ops', {});
            this.options.onCommand('ops_equity', {});
        }
        this._title('告警通道');
        this._section('微信公众号（推荐：关注公众号就能收到）');
        let xtuisEnabled = !!xtuis.enabled;
        const xtuisOn = this._switch(xtuisEnabled, (checked) => {
            xtuisEnabled = checked;
            this.options.onCommand('ops_notify_config', {
                kind: 'xtuis', values: { enabled: checked } });
        });
        const token = this._input(String(xtuis.token || ''),
            '关注公众号 xtuis → 回复 token 获取');
        const custom = this._input(String(xtuis.url || ''),
            '留空 = https://wx.xtuis.cn/{token}.send');
        const saveX = this._button('保存', () => {
            this.options.onCommand('ops_notify_config', {
                kind: 'xtuis',
                // 填了 token 就顺手启用（少一步 ✓）
                values: { enabled: xtuisEnabled || !!token.value.trim(),
                          token: token.value.trim(),
                          url: custom.value.trim() },
            });
            this.options.onToast?.('success', '公众号推送已保存');
        }, true);
        const wrap = (items: HTMLElement[]) => {
            const box = document.createElement('div');
            box.className = 'desk-settings-inline';
            for (const item of items) box.appendChild(item);
            return box;
        };
        this._row('bell', '启用公众号推送', '定时任务 / 预警 / 交易通知都会发到这里',
            xtuisOn);
        this._row('info', 'Token', '关注公众号后按提示回复 token', token);
        this._row('info', '推送地址', '换同类服务时改这里（{token} 是占位符）',
            wrap([custom, saveX]));

        this._section('企业微信 / 邮件 / 自定义 Webhook');
        const wecomInput = this._input(String(wecom.webhook || ''),
            'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=');
        this._row('bell', '企业微信群机器人', '填 Webhook 地址即可',
            wrap([wecomInput, this._button('保存', () => {
                this.options.onCommand('ops_notify_config', {
                    kind: 'wecom',
                    values: { enabled: true,
                              webhook: wecomInput.value.trim() },
                });
                this.options.onToast?.('success', '企业微信已保存');
            })]));
        const host = this._input(String(email.host || ''), 'smtp.qq.com');
        const port = this._input(String(email.port || 465), '465');
        const user = this._input(String(email.user || ''), '账号');
        const pass = this._input(String(email.password || ''), '授权码',
                                 'password');
        const to = this._input(String(email.to || ''), '收件人');
        this._row('info', 'SMTP 服务器', '发信服务器 + 端口',
            wrap([host, port]));
        this._row('info', '账号 / 授权码', '邮箱账号与 SMTP 授权码',
            wrap([user, pass]));
        this._row('info', '收件人', '测试与告警都发到这里',
            wrap([to, this._button('保存邮件', () => {
                this.options.onCommand('ops_notify_config', {
                    kind: 'email',
                    values: { enabled: true, host: host.value.trim(),
                              port: Number(port.value || 465),
                              user: user.value.trim(),
                              password: pass.value,
                              to: to.value.trim(),
                              from: user.value.trim() },
                });
                this.options.onToast?.('success', '邮件通道已保存');
            })]));
        const hookUrl = this._input(String(hook.url || ''),
            'https://…（Server酱 / PushPlus / 钉钉 / 自建）');
        const hookBody = this._input(String(hook.template || ''),
            '{"title":"{title}","text":"{text}"}');
        this._row('info', '自定义 Webhook', 'POST JSON；模板支持 {title}{text}{level}',
            wrap([hookUrl, hookBody, this._button('保存', () => {
                this.options.onCommand('ops_notify_config', {
                    kind: 'webhook',
                    values: { enabled: true, url: hookUrl.value.trim(),
                              method: String(hook.method || 'POST'),
                              template: hookBody.value.trim() },
                });
                this.options.onToast?.('success', 'Webhook 已保存');
            })]));

        this._section('测试与记录');
        this._row('bell', '发送测试',
            '每个通道各发一条，下面能看到每个通道的返回',
            this._button('发送测试', () => {
                this.options.onCommand('ops_notify_test', {});
            }, true));
        if (String(data.last_error || '')) {
            const box = document.createElement('pre');
            box.className = 'desk-settings-audit';
            box.textContent = String(data.last_error);
            this.body.appendChild(box);
        }
        const history = (data.history || []) as Array<Record<string, any>>;
        if (history.length) {
            const box = document.createElement('pre');
            box.className = 'desk-settings-audit';
            box.textContent = history.slice(0, 8).map((row) => {
                const at = new Date(Number(row.at || 0) * 1000)
                    .toLocaleString('zh-CN', { hour12: false });
                const parts = ((row.results || []) as Array<Record<string, any>>)
                    .map((item) => `${item.channel}:${
                        item.ok ? 'ok' : 'fail'}`);
                return `${at}  ${String(row.title || '')}  ${parts.join(' ')}`;
            }).join('\n');
            this.body.appendChild(box);
        }
        this._renderAlertRules();
    }

    /** 告警规则：哪些事件推手机 / 等级 / 去重窗口（v1.3.7-92 ✓） */
    private _renderAlertRules(): void {
        const rules = (this.notify.alert_rules || []) as Array<Record<string, any>>;
        this._section('告警规则（哪些事要推手机）');
        if (!rules.length) {
            const hint = document.createElement('div');
            hint.className = 'desk-settings-note';
            hint.textContent = '正在读取规则…（保存一次通道或点「发送测试」也会刷新）';
            this.body.appendChild(hint);
            return;
        }
        const draft = new Map<string, Record<string, any>>();
        // ★ v1.3.7-96：按来源分组（交易 / 预警 / 持仓 / 行情 / 定时任务 /
        //   策略 / 资讯 / 系统），顺序跟目录一致，不另造分组名 ✓
        const order: string[] = [];
        for (const row of rules) {
            const group = String(row.source || '其它');
            if (!order.includes(group)) order.push(group);
        }
        for (const group of order) {
            const items = rules.filter((row) =>
                String(row.source || '其它') === group);
            const head = document.createElement('div');
            head.className = 'desk-settings-section';
            head.textContent = `${group}（${items.length}）`;
            this.body.appendChild(head);
        for (const row of items) {
            const id = String(row.id || '');
            draft.set(id, { id, enabled: !!row.enabled,
                            level: String(row.level || 'info'),
                            min_interval: Number(row.min_interval || 0),
                            threshold: Number(row.threshold || 0) });
            const box = document.createElement('div');
            box.className = 'desk-settings-row';
            const icon = document.createElement('span');
            icon.className = 'desk-settings-icon';
            icon.innerHTML = ICONS.bell;
            const text = document.createElement('div');
            text.className = 'desk-settings-text';
            text.innerHTML = `<div class="desk-settings-name">${
                String(row.label || id)}</div>`
                + `<div class="desk-settings-desc">${String(row.desc || '')}`
                + `　·　${String(row.source || '')}</div>`;
            const control = document.createElement('div');
            control.className = 'desk-settings-inline';
            const level = this._select(
                [{ value: 'info', label: '一般' },
                 { value: 'warning', label: '重要' },
                 { value: 'error', label: '严重' }],
                String(row.level || 'info'),
                (value) => {
                    const item = draft.get(id);
                    if (item) item.level = String(value);
                });
            const wait = this._input(String(row.min_interval || 0),
                                     '去重（秒）');
            wait.style.width = '86px';
            wait.addEventListener('input', () => {
                const item = draft.get(id);
                if (item) item.min_interval = Number(wait.value || 0);
            });
            const toggle = this._switch(!!row.enabled, (checked) => {
                const item = draft.get(id);
                if (item) item.enabled = checked;
            });
            control.append(toggle, level);
            // ★ v1.3.7-93：有阈值的规则（浮亏 % / 分钟）多一个输入框 ✓
            if (row.threshold_label) {
                const limit = this._input(String(row.threshold ?? ''),
                                          String(row.threshold_label || '阈值'));
                limit.style.width = '110px';
                limit.title = `${String(row.threshold_label || '阈值')}`
                    + `（${String(row.threshold_unit || '')}）`;
                limit.addEventListener('input', () => {
                    const item = draft.get(id);
                    if (item) item.threshold = Number(limit.value || 0);
                });
                control.appendChild(limit);
            } else {
                control.appendChild(wait);
            }
            box.append(icon, text, control);
            this.body.appendChild(box);
        }
        }
        const bar = document.createElement('div');
        bar.className = 'desk-settings-buttons';
        bar.appendChild(this._button('保存规则', () => {
            this.options.onCommand('ops_alert_rules', {
                action: 'save', rules: [...draft.values()],
            });
            this.options.onToast?.('success', '告警规则已保存');
        }, true));
        bar.appendChild(this._button('恢复默认', () => {
            this.options.onCommand('ops_alert_rules', { action: 'reset' });
        }));
        this.body.appendChild(bar);

        // ★ v1.3.7-94：静默时段 / 每日汇总（默认都关 ✓）
        const settings = (this.notify.alert_settings || {}) as Record<string, any>;
        const quiet = settings.quiet || {};
        const digest = settings.digest || {};
        const quietState: Record<string, any> = {
            enabled: !!quiet.enabled,
            allow: String(quiet.allow_level || 'error') };
        const digestState = { enabled: !!digest.enabled };
        this._section('静默时段 / 每日汇总');
        const qStart = this._input(String(quiet.start || '23:00'), '23:00');
        const qEnd = this._input(String(quiet.end || '08:00'), '08:00');
        qStart.style.width = '90px';
        qEnd.style.width = '90px';
        const allow = this._select(
            [{ value: 'error', label: '只推「严重」' },
             { value: 'warning', label: '推「重要」以上' },
             { value: 'info', label: '全都推' }],
            String(quiet.allow_level || 'error'),
            (value) => { quietState.allow = value; });
        this._row('bell', '静默时段',
            '这段时间里只推送选中的级别（比如半夜只推严重）',
            this._switch(!!quiet.enabled, (checked) => {
                quietState.enabled = checked;
            }));
        this._row('info', '静默起止', '支持跨零点（23:00 → 08:00）',
            (() => {
                const box = document.createElement('div');
                box.className = 'desk-settings-inline';
                box.append(qStart, document.createTextNode('→'), qEnd, allow);
                return box;
            })());
        const digestAt = this._input(String(digest.at || '16:00'), '16:00');
        digestAt.style.width = '90px';
        this._row('bell', '每日汇总', '每天到点发一条，把当天命中 / 被压制的告警汇总',
            this._switch(!!digest.enabled, (checked) => {
                digestState.enabled = checked;
            }));
        this._row('info', '汇总时间', '默认 16:00（收盘后）',
            digestAt);
        // ★ v1.3.7-95：自定义资讯关键词
        const keywordRow = document.createElement('div');
        keywordRow.className = 'desk-settings-row';
        const kIcon = document.createElement('span');
        kIcon.className = 'desk-settings-icon';
        kIcon.innerHTML = ICONS.bell;
        const kText = document.createElement('div');
        kText.className = 'desk-settings-text';
        const kWords = ((settings.keywords || []) as string[]).join(',');
        kText.innerHTML = '<div class="desk-settings-name">资讯关键词</div>'
            + '<div class="desk-settings-desc">标题或摘要命中就推；'
            + '多个用逗号分隔（如「降息,抛储,碳酸锂」）</div>';
        const kInput = this._input(kWords, '降息, 抛储, 碳酸锂');
        kInput.style.width = '260px';
        const kControl = document.createElement('div');
        kControl.className = 'desk-settings-inline';
        kControl.append(kInput, this._button('保存关键词', () => {
            this.options.onCommand('ops_alert_rules', {
                action: 'settings',
                keywords: kInput.value.trim(),
            });
            this.options.onToast?.('success', '资讯关键词已保存');
        }));
        keywordRow.append(kIcon, kText, kControl);
        this.body.appendChild(keywordRow);

        // ★ v1.3.7-95：账户净值曲线（回撤告警的依据）
        this._renderEquityCurve();

        const bar2 = document.createElement('div');
        bar2.className = 'desk-settings-buttons';
        bar2.appendChild(this._button('保存静默 / 汇总', () => {
            this.options.onCommand('ops_alert_rules', {
                action: 'settings',
                quiet: { enabled: quietState.enabled,
                         start: qStart.value.trim() || '23:00',
                         end: qEnd.value.trim() || '08:00',
                         allow_level: quietState.allow
                             || String(quiet.allow_level || 'error') },
                digest: { enabled: digestState.enabled,
                          at: digestAt.value.trim() || '16:00' },
            });
            this.options.onToast?.('success', '静默 / 汇总设置已保存');
        }, true));
        this.body.appendChild(bar2);
    }

    /** 账户净值曲线（近 30 天；没有数据就提示"还没有采样" ✓） */
    private _renderEquityCurve(): void {
        const stats = (this.equity.stats || {}) as Record<string, any>;
        this._section('账户净值曲线（近 30 天）');
        const note = document.createElement('div');
        note.className = 'desk-settings-note';
        const points = (stats.points_list || []) as Array<[number, number]>;
        if (!points.length) {
            note.textContent = '还没有采样（要连上交易账户、跑一会儿才有点）；'
                + '每 60 秒记一条。';
            this.body.appendChild(note);
            return;
        }
        note.textContent = `当前 ${Number(stats.current || 0).toFixed(0)}`
            + ` · 峰值 ${Number(stats.peak || 0).toFixed(0)}`
            + ` · 回撤 ${Number(stats.drawdown || 0).toFixed(1)}%`
            + ` · 近 30 天最大回撤 ${Number(stats.max_drawdown || 0).toFixed(1)}%`
            + ` · 今日 ${Number(stats.today_pnl || 0) >= 0 ? '+' : ''}${
                Number(stats.today_pnl || 0).toFixed(0)}`;
        this.body.appendChild(note);
        const canvas = document.createElement('canvas');
        canvas.className = 'desk-settings-equity';
        canvas.width = 640;
        canvas.height = 140;
        this.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const values = points.map((row) => Number(row[1]) || 0);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = max - min || 1;
        const style = getComputedStyle(this.element);
        const line = style.getPropertyValue('--desk-accent') || '#4c8dff';
        const grid = style.getPropertyValue('--desk-border') || '#333';
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i += 1) {
            const y = 8 + (canvas.height - 16) * i / 4;
            ctx.beginPath();
            ctx.moveTo(4, y);
            ctx.lineTo(canvas.width - 4, y);
            ctx.stroke();
        }
        ctx.strokeStyle = line;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        points.forEach((row, index) => {
            const x = 4 + (canvas.width - 8) * (index / Math.max(1, points.length - 1));
            const y = 8 + (canvas.height - 16)
                * (1 - ((Number(row[1]) || 0) - min) / span);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    private _input(value: string, placeholder: string,
                   type = 'text'): HTMLInputElement {
        const input = document.createElement('input');
        input.className = 'desk-settings-input';
        input.type = type;
        input.value = value;
        input.placeholder = placeholder;
        input.style.width = '220px';
        return input;
    }

    private _renderAbout(): void {
        const version = this.options.version || '1.3.3';
        this._title('关于');
        this._row('help', '帮助', '发现新功能并了解 minibt desk 的使用技巧',
            this._button('打开帮助页面', () => {
                this.options.onCommand('open_url', {
                    url: 'https://www.minibt.cn' });
            }));
        this._row('feedback', '提供反馈', '通过提供反馈帮助我们改进 minibt',
            this._button('提供反馈', () => {
                this.options.onCommand('open_url', {
                    url: 'https://github.com/MiniBtMaster/minibt/issues' });
            }));
        this._row('info', '关于',
            `minibt desk · 当前版本 ${version}`,
            this._button('检查更新', () => {
                this.options.onCommand('open_url', {
                    url: 'https://pypi.org/project/minibt/' });
            }));
    }

    // ------------------------------------------------------------ 图表配置
    private _renderChartConfig(): void {
        const v = this.options.values || {};
        this._title('图表设置');
        this._section('图表配置');
        this._row('reset', '恢复当前页面默认值',
            '只恢复「图表配置」页的设置，不影响图表颜色 / 模拟账户 / 主题',
            this._button('恢复默认', () => {
                this.options.onSetting('chart_reset', true);
            }));
        this._row('chart', '期货历史长度',
            '无限历史能在左加载的总根数（需 ≥ 数据长度；相等 = 无限历史）',
            this._select(
                HISTORIES.map((item) => ({ value: String(item.value),
                    label: item.label })),
                String(Number(v.chart_history || 1000)),
                (value) => this.options.onSetting('chart_history',
                    Number(value) || 1000)));
        this._row('chart', '期货数据长度',
            '设置获取期货K线数据的长度（根数），越大加载越慢',
            this._select(
                LENGTHS.map((item) => ({ value: String(item.value),
                    label: item.label })),
                String(Number(v.chart_data_length || 1000)),
                (value) => this.options.onSetting('chart_data_length',
                    Number(value) || 1000)));
        this._row('chart', '图表字体大小',
            '设置图表左上角标签（图例 / 指标标签 / 买卖盘）的文字大小',
            this._slider(10, 22, Number(v.chart_font_size || 13),
                (value) => this.options.onSetting('chart_font_size', value)));
        this._row('crosshair', '鼠标十字线',
            '设置图表鼠标十字线样式；不选时默认跟随深色 / 浅色主题',
            this._select(
                CROSSHAIR_PRESETS.map((item) => ({
                    value: item.value, label: item.label,
                })),
                String(v.chart_crosshair_style || 'classic'),
                (value) => this.options.onSetting('chart_crosshair_style',
                    value)));
        // ★ 持仓线 / 挂单线：**所有图表**统一由这里控制（默认开 ✓）
        this._row('position_line', '持仓线',
            '在图表上显示持仓成本线（多仓绿 / 空仓红，含天勤模拟与本地模拟）',
            this._switch(v.position_line !== false, (checked) =>
                this.options.onSetting('position_line', checked)));
        this._row('order_line', '挂单线 / 平仓线',
            '在图表上显示未成交委托的价格（开仓=挂单线，平仓=平仓线；'
            + '天勤模拟 / 本地模拟都显示）',
            this._switch(v.order_line !== false, (checked) =>
                this.options.onSetting('order_line', checked)));
        this._section('指标刷新');
        this._row('chart', '指标/策略图表更新频率',
            '主图 / 副图 / VP / 表格，以及策略 Strategy.__init__ 里的指标'
            + '重算，全部按这一个频率更新（10–3000ms；实际最快受 500ms'
            + ' 看盘节拍限制）。策略逻辑 next 的频率由「新K线next / on_close」'
            + '决定，不单独占用刷新频率。',
            this._slider(10, 3000,
                Number(v.indicator_refresh_interval_ms || 1000),
                (value) => this.options.onSetting(
                    'indicator_refresh_interval_ms', value)));
        this._row('chart', 'VP / 表格只在新 K 线更新',
            '开启后 VP 图 / 动态表格只在出现新 K 线时更新'
            + '（默认关闭 = 按上面的统一频率刷新；开启后开销最低）',
            this._switch(v.indicator_custom_new_bar === true, (checked) =>
                this.options.onSetting('indicator_custom_new_bar', checked)));
        this._row('chart', 'K 线推送',
            'K 线不受指标刷新设置影响，始终保持即时推送',
            document.createElement('span'));
    }

    // ------------------------------------------------------------ 图表颜色
    private _renderChartColors(): void {
        const v = this.options.values || {};
        this._title('图表颜色');
        this._row('cursor', '鼠标标签颜色', '设置鼠标悬停时标签的背景颜色',
            this._colorPicker(String(v.chart_color_crosshair || ''),
                (value) => this.options.onSetting('chart_color_crosshair',
                    value)));
        this._row('up', '上涨颜色', '设置K线上涨时的颜色（阳线）',
            this._colorPicker(String(v.chart_color_up || ''),
                (value) => this.options.onSetting('chart_color_up', value)));
        this._row('down', '下跌颜色', '设置K线下跌时的颜色（阴线）',
            this._colorPicker(String(v.chart_color_down || ''),
                (value) => this.options.onSetting('chart_color_down', value)));
    }

    // ------------------------------------------------------------ 小部件
    private _title(text: string): void {
        const title = document.createElement('h2');
        title.className = 'desk-settings-title';
        title.textContent = text;
        this.body.appendChild(title);
    }

    // ------------------------------------------------------------ 模拟账户
    private _renderSim(): void {
        const settings = this.sim.settings || {};
        // 打开这一页时向后端要一次（后端刚推回来的那次不要 ✗）
        if (!this.quiet) this.options.onCommand('sim_analysis', {});
        this._title('模拟账户');
        this._section('账户设置');
        // ★ 回放带策略时以 minibt 的 config / 合约为准（用户要求 ✓）
        const note = document.createElement('div');
        note.className = 'desk-muted';
        note.style.margin = '0 0 8px';
        note.textContent = '回放带策略时：初始资金 / 保证金率 / 手续费 / 合约乘数'
            + ' 跟随策略的 minibt 配置；这里用于手动交易 / 无策略回放。';
        this.body.appendChild(note);
        // 初始现金：下拉预设（10 万 ~ 100 万）+ 手动填任意值 ✓
        const cashBox = document.createElement('div');
        cashBox.className = 'desk-settings-inline';
        const current = Math.round(Number(settings.initial_cash) || 100000);
        const cash = document.createElement('input');
        cash.type = 'number';
        cash.className = 'desk-settings-input';
        cash.min = '1';
        cash.step = '1000';
        cash.style.width = '130px';
        cash.value = String(current);
        cash.title = '本地模拟账户的初始现金（可以直接填任意金额 ✓）';
        const preset = this._select(
            CASH_PRESETS.map((item) => ({ value: String(item.value),
                                          label: item.label })),
            CASH_PRESETS.some((item) => item.value === current)
                ? String(current) : '',
            (value) => {
                const picked = Number(value);
                if (!Number.isFinite(picked) || picked <= 0) return;
                cash.value = String(picked);      // 选了下拉 → 填进输入框 ✓
                this._applyCash(picked);
            });
        // 下拉里加一条「自定义」（当前值不在预设里时选中它 ✓）
        const custom = document.createElement('option');
        custom.value = '';
        custom.textContent = '自定义';
        preset.insertBefore(custom, preset.firstChild);
        const apply = this._button('应用', () => {
            const value = Number(cash.value);
            if (!Number.isFinite(value) || value <= 0) {
                cash.focus();
                return;
            }
            this._applyCash(value);
        });
        cash.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') this._applyCash(Number(cash.value));
        });
        cash.addEventListener('change', () => {
            const value = Number(cash.value);
            if (Number.isFinite(value) && value > 0) this._applyCash(value);
        });
        cashBox.append(preset, cash, apply);
        this._row('money', '账户初始现金',
                  '选 10 万 ~ 100 万，或直接在框里填任意金额（应用后按新金额重置账户 ✓）',
                  cashBox);

        const mode = this._select(FEE_MODES,
                                  String(settings.fee_mode || 'fixed'),
                                  (value) => this.options.onSetting(
                                      'sim_fee_mode', value));
        this._row('chart', '交易手续费用', '只能设置其中之一：固定每手 / 成交额百分比',
                  mode);

        const fee = document.createElement('input');
        fee.type = 'number';
        fee.className = 'desk-settings-input';
        fee.min = '0';
        fee.step = '0.01';
        fee.style.width = '110px';
        fee.value = String(Number(settings.fee_value) || 0);
        const isPercent = String(settings.fee_mode || 'fixed') === 'percent';
        fee.title = isPercent ? '成交额的百分之几（0.5 = 0.5%）'
            : '每手固定多少钱';
        fee.addEventListener('change', () => {
            const value = Number(fee.value);
            if (Number.isFinite(value) && value >= 0) {
                this.options.onSetting('sim_fee_value', value);
            }
        });
        this._row('money', isPercent ? '百分比手续费（%）' : '固定手续费（元 / 手）',
                  isPercent ? '例：0.5 表示成交额的 0.5%'
                      : '例：5 表示每手 5 元', fee);

        const actions = document.createElement('div');
        actions.className = 'desk-settings-actions';
        actions.append(
            this._button('刷新分析', () => this.options.onCommand(
                'sim_analysis', {})),
            this._button('重置模拟账户', () => this.options.onCommand(
                'sim_reset', {}), true));
        this.body.appendChild(actions);

        const summary = this.sim.summary || {};
        this._section('账户概况');
        const cards = document.createElement('div');
        cards.className = 'desk-settings-cards';
        const initial = Number(summary.initial_cash
            || settings.initial_cash || 0);
        for (const [name, value, tone] of [
                ['账户权益', summary.balance, 'vs-initial'],
                ['平仓盈亏', summary.realized, 'sign'],
                ['手续费', summary.commission, 'none'],
                ['成交次数', summary.trades, 'count'],
                ['平仓次数', summary.closes, 'count'],
                ['盈利次数', summary.wins, 'count']] as const) {
            const card = document.createElement('div');
            card.className = 'desk-settings-card';
            const title = document.createElement('div');
            title.className = 'desk-settings-card-title';
            title.textContent = name;
            const number = document.createElement('div');
            number.className = 'desk-settings-card-value';
            if (tone === 'vs-initial') {
                const amount = Number(value) || 0;
                number.textContent = amount.toLocaleString(undefined, {
                    minimumFractionDigits: 2, maximumFractionDigits: 2,
                });
                // 和初始现金比：多 → 红（盈利），少 → 绿（亏损）✓
                number.classList.toggle('up', amount > initial);
                number.classList.toggle('down', amount < initial);
            } else if (tone === 'sign') {
                const amount = Number(value) || 0;
                number.textContent = amount.toLocaleString(undefined, {
                    minimumFractionDigits: 2, maximumFractionDigits: 2,
                });
                number.classList.toggle('up', amount > 0);
                number.classList.toggle('down', amount < 0);
            } else if (tone === 'none') {
                number.textContent = (Number(value) || 0).toLocaleString(
                    undefined, { minimumFractionDigits: 2,
                                 maximumFractionDigits: 2 });
            } else {
                number.textContent = value === undefined || value === null
                    ? '--' : String(value);
            }
            card.append(title, number);
            cards.appendChild(card);
        }
        this.body.appendChild(cards);

        this._section('账户权益曲线');
        const equityHost = document.createElement('div');
        equityHost.className = 'desk-settings-chart';
        this.body.appendChild(equityHost);
        renderMiniChart(equityHost, [{
            name: '账户权益',
            color: 'var(--desk-accent, #2962ff)',
            points: this.sim.equity || [],
        }], {
            height: 180,
            area: true,
            format: (value) => value.toFixed(0),
            empty: '还没有成交，权益曲线为空',
        });

        this._section('各品种累计盈亏');
        const profitHost = document.createElement('div');
        profitHost.className = 'desk-settings-chart';
        this.body.appendChild(profitHost);
        renderMiniChart(profitHost, (this.sim.series || []).map((item) => ({
            name: item.name,
            color: item.color,
            points: item.points || [],
        })), {
            height: 180,
            zeroLine: true,
            format: (value) => value.toFixed(0),
            empty: '还没有平仓记录（平仓后这里会出现累计盈亏曲线）',
        });

        this._section('各品种统计');
        const table = this.sim.table || {};
        const columns = table.columns || [];
        const rows = table.rows || [];
        if (!columns.length || !rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-settings-desc';
            empty.textContent = '暂无成交记录';
            this.body.appendChild(empty);
            return;
        }
        const grid = document.createElement('div');
        grid.className = 'desk-settings-table';
        const head = document.createElement('div');
        head.className = 'desk-settings-table-row head';
        for (const name of columns) {
            const cell = document.createElement('span');
            cell.textContent = name;
            head.appendChild(cell);
        }
        grid.appendChild(head);
        for (const row of rows) {
            const line = document.createElement('div');
            line.className = 'desk-settings-table-row';
            row.forEach((value, index) => {
                const cell = document.createElement('span');
                cell.textContent = String(value);
                const numeric = Number(String(value).replace(/[,\s]/g, ''));
                if (index >= 4 && Number.isFinite(numeric)) {
                    cell.classList.toggle('up', numeric > 0);
                    cell.classList.toggle('down', numeric < 0);
                }
                line.appendChild(cell);
            });
            grid.appendChild(line);
        }
        this.body.appendChild(grid);
    }

    /** 应用初始现金（立刻落盘 + 重置账户 ✓） */
    private _applyCash(value: number): void {
        const amount = Math.round(Number(value) || 0);
        if (amount <= 0) return;
        this.options.onSetting('sim_initial_cash', amount);
    }

    private _section(text: string): void {
        const section = document.createElement('div');
        section.className = 'desk-settings-section';
        section.textContent = text;
        this.body.appendChild(section);
    }

    /** 主题色：预设色 + 「自定义颜色…」→ 系统调色板 ✓ */
    private _accentControl(value: string): HTMLDivElement {
        const box = document.createElement('div');
        box.className = 'desk-settings-control';
        const presetValues = new Set(ACCENTS.map((item) => item.value));
        const isCustom = !!value && !presetValues.has(value);
        const custom = document.createElement('input');
        custom.type = 'color';
        custom.className = 'desk-settings-input desk-settings-color';
        custom.title = '自定义主题色';
        custom.value = value && value.startsWith('#') ? value : '#2962ff';
        custom.style.display = isCustom ? '' : 'none';
        const items = ACCENTS.map((item) => ({
            value: item.value || 'default', label: item.label,
        }));
        items.push({ value: 'custom', label: '自定义颜色…' });
        const select = this._select(
            items, isCustom ? 'custom' : (value || 'default'),
            (picked) => {
                if (picked === 'custom') {
                    custom.style.display = '';
                    custom.click();       // 打开系统调色板（input 时再应用）
                } else {
                    custom.style.display = 'none';
                    this.options.onSetting(
                        'theme_accent', picked === 'default' ? '' : picked);
                }
            });
        custom.addEventListener('input', () =>
            this.options.onSetting('theme_accent', custom.value));
        custom.addEventListener('change', () =>
            this.options.onSetting('theme_accent', custom.value));
        box.append(select, custom);
        return box;
    }

    private _row(icon: string, name: string, desc: string,
                 control: HTMLElement | null): void {
        const row = document.createElement('div');
        row.className = 'desk-settings-row';
        const box = document.createElement('span');
        box.className = 'desk-settings-icon';
        box.innerHTML = ICONS[icon] || ICONS.info;
        const text = document.createElement('div');
        text.className = 'desk-settings-text';
        const title = document.createElement('div');
        title.className = 'desk-settings-name';
        title.textContent = name;
        const detail = document.createElement('div');
        detail.className = 'desk-settings-desc';
        detail.textContent = desc;
        text.append(title, detail);
        row.append(box, text);
        if (control) {
            const right = document.createElement('div');
            right.className = 'desk-settings-control';
            right.appendChild(control);
            row.appendChild(right);
        }
        this.body.appendChild(row);
    }

    private _button(label: string, run: () => void,
                    primary = false): HTMLButtonElement {
        const button = document.createElement('button');
        button.className = 'desk-settings-btn' + (primary ? ' primary' : '');
        button.textContent = label;
        button.addEventListener('click', run);
        return button;
    }

    private _select(items: Array<{ value: string; label: string }>,
                    value: string,
                    onPick: (value: string) => void): HTMLSelectElement {
        const select = document.createElement('select');
        select.className = 'desk-settings-select';
        for (const item of items) {
            const option = document.createElement('option');
            option.value = item.value;
            option.textContent = item.label;
            if (item.value === value) option.selected = true;
            select.appendChild(option);
        }
        select.addEventListener('change', () => onPick(select.value));
        return select;
    }

    /** 路径输入框（回车 / 失焦保存；回车后闪一下「已保存 ✓」） */
    private _pathInput(value: string, enabled: boolean,
                       onCommit: (value: string) => void): HTMLInputElement {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'desk-settings-input';
        input.value = value;
        input.placeholder = '例如 C:\Users\you\Desktop\owen';
        input.spellcheck = false;
        input.disabled = !enabled;
        input.title = enabled
            ? '填 minibt 所在的目录（仓库根或包目录），回车保存'
            : '先在上一行开启「手动指定 minibt 路径」';
        const commit = (): void => {
            if (input.disabled) return;
            const next = input.value.trim();
            if (next === value.trim()) return;
            value = next;
            onCommit(next);
        };
        input.addEventListener('change', commit);
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                commit();
                (event.target as HTMLInputElement).blur();
            }
        });
        return input;
    }

    /** 通用文本输入（AI 地址 / 模型 / 密钥都用它；回车保存 ✓） */
    private _textInput(value: string, onCommit: (value: string) => void,
                       placeholder = '', password = false,
                       storeKey = ''): HTMLInputElement {
        const input = document.createElement('input');
        input.type = password ? 'password' : 'text';
        input.className = 'desk-settings-input';
        // ★ 后端没值 → 用本机缓存（用户填过就不该"消失" ✓）
        input.value = value || (storeKey ? localAi(storeKey) : '');
        input.placeholder = placeholder;
        input.spellcheck = false;
        if (storeKey) {
            // 每一次输入都落本机：哪怕后端不认这个键也不会丢 ✓
            input.addEventListener('input', () => {
                saveLocalAi(storeKey, input.value);
            });
        }
        const commit = (): void => {
            const next = input.value.trim();
            if (next === value.trim()) return;
            value = next;
            // ★ 记住原文：后端若没保存成功，重画时**不要把用户的字冲掉** ✓
            input.dataset.dirty = '1';
            onCommit(next);
        };
        input.addEventListener('change', commit);
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                commit();
                (event.target as HTMLInputElement).blur();
            }
        });
        return input;
    }

    private _switch(checked: boolean,
                    onToggle: (checked: boolean) => void): HTMLDivElement {
        const box = document.createElement('div');
        box.className = 'desk-settings-switch' + (checked ? ' on' : '');
        box.addEventListener('click', () => {
            const next = !box.classList.contains('on');
            box.classList.toggle('on', next);
            onToggle(next);
        });
        return box;
    }

    private _slider(min: number, max: number, value: number,
                    onPick: (value: number) => void): HTMLDivElement {
        const box = document.createElement('div');
        box.className = 'desk-settings-control';
        const input = document.createElement('input');
        input.type = 'range';
        input.className = 'desk-settings-slider';
        input.min = String(min);
        input.max = String(max);
        input.value = String(value);
        const label = document.createElement('span');
        label.className = 'desk-settings-slider-value';
        label.textContent = String(value);
        input.addEventListener('input', () => {
            label.textContent = input.value;
        });
        input.addEventListener('change', () => onPick(Number(input.value)));
        box.append(label, input);
        return box;
    }

    /** 颜色：一排色块 + 「默认颜色」下拉（miniqt 是下拉，这里两者都有 ✓） */
    private _colorPicker(value: string,
                         onPick: (value: string) => void): HTMLDivElement {
        const box = document.createElement('div');
        box.className = 'desk-settings-control';
        const colors = document.createElement('div');
        colors.className = 'desk-settings-colors';
        const choices = ['', ...LINE_COLORS];
        for (const color of choices) {
            const chip = document.createElement('span');
            chip.className = 'desk-settings-chip'
                + (String(color).toLowerCase() === String(value).toLowerCase()
                    ? ' on' : '');
            chip.title = color || '默认颜色';
            chip.style.background = color
                || (this.options.theme === 'light' ? '#d7dbe0' : '#3a4048');
            chip.addEventListener('click', () => {
                colors.querySelectorAll('.desk-settings-chip')
                    .forEach((node) => node.classList.remove('on'));
                chip.classList.add('on');
                onPick(color);
            });
            colors.appendChild(chip);
        }
        const custom = document.createElement('input');
        custom.type = 'color';
        custom.className = 'desk-settings-input';
        custom.style.minWidth = '42px';
        custom.style.padding = '0 2px';
        custom.value = value && value.startsWith('#') ? value : '#2962ff';
        custom.addEventListener('input', () => onPick(custom.value));
        box.append(colors, custom);
        return box;
    }

    private _ensureStyle(): void {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }
}

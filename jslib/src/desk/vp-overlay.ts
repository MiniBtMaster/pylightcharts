/**
 * VpOverlay — **成交量分布（Volume Profile）自绘层**
 *
 * 为什么要自己画（不再用 LWC 的 custom series）：
 *
 * * custom series 的 `shapes.left/right` 是「相对某一根 bar 的根数偏移」，
 *   锚点只能挂在**真实 K 线**上 → 想画到右边缘外，必须知道「最后一根离画布
 *   右边缘有几根」，而这要靠 LWC 内部 API 猜（试了 4 版都失败 ✗）；
 * * minibt 的 bokeh 版之所以能贴右边缘，是因为 `anchor = x1`（**视口右端**）
 *   是它自己算的（`RangesUpdate` 自带 `x0/x1`）—— 也就是说"画在哪"由自己
 *   决定，不依赖图表库 ✓
 *
 * 这里用同一思路：一块 `<canvas>` 覆盖在图表上，自己算 x/y。
 *
 *   xRight = 画布宽度 - 2                   ← 横条 0 刻度（必然贴右边缘 ✓）
 *   width  = value / peak * BAND            ← 满量程 = 可视跨度 × profile_frac
 *   y      = priceToCoordinate(档中心)       ← 价格轴 → 像素（稳定 API ✓）
 *
 * 鼠标跟随（优先级与 minibt `_vp_interactive` 一致）：
 *
 *   1. `onCrosshair(time)` → 画**鼠标那根**的分布（鼠标优先）；
 *   2. `onCrosshair(null)`（MouseLeave）→ 回到最右可见那根；
 *   3. `setBars()` / `setData()`（有新数据）→ 清鼠标覆盖（实时优先）✓
 */
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export interface VpStyleOptions {
    bar_color?: string;
    poc_color?: string;
    fill_alpha?: number;
    bin_ratio?: number;
    profile_frac?: number;
    line_color?: string;
    line_width?: number;
    highlight_poc?: boolean;
}

export interface VpData {
    /** `(根数, 档数)` 的分布矩阵（列 = 等宽价格档 ✓） */
    matrix: number[][];
    /** 每根的滚动档区下/上边界（与指标端同一条规则 ✓） */
    lo: number[];
    hi: number[];
    style?: VpStyleOptions;
    /** 每行对应的 K 线时间（有它就能按**时间**找行 ✓） */
    times?: number[];
}

interface BarLike {
    time: number;
    close: number;
    [key: string]: unknown;
}

export class VpOverlay {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D | null;
    private series: ISeriesApi<'Line'> | null = null;
    private bounds: { width: number; height: number } = { width: 0, height: 0 };
    private bars: BarLike[] = [];
    private data: VpData | null = null;
    /** 鼠标所在那根的**时间**（`null` = 实时/最右 ✓）
     *
     * 记时间而不是下标：实时图表每拍都推 K 线（还可能向左补历史），
     * 下标会漂；时间不会 ✓
     */
    private mouseTime: number | null = null;
    private frame = 0;
    /** 最后一次绘制的位置快照（调试 / 排查用 ✓） */
    lastPaint: {
        row: number; bins: number; xRight: number;
        yTop: number; yBottom: number; lo: number; hi: number; peak: number;
    } | null = null;

    constructor(
        private readonly host: HTMLElement,
        private readonly chart: IChartApi,
        private readonly theme: () => string,
    ) {
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'desk-vp-overlay';
        this.canvas.style.cssText = 'position:absolute;left:0;top:0;'
            + 'pointer-events:none;z-index:6;';
        this.host.style.position = this.host.style.position || 'relative';
        this.host.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d');
    }

    destroy(): void {
        try {
            this.canvas.remove();
        } catch { /* ignore */ }
        if (this.series) {
            try {
                this.chart.removeSeries(this.series);
            } catch { /* ignore */ }
            this.series = null;
        }
        this.data = null;
    }

    /** 价格 → 像素：借用一条**隐形折线序列**（`priceToCoordinate` 唯一稳定入口 ✓） */
    private ensureSeries(): ISeriesApi<'Line'> | null {
        if (this.series) return this.series;
        try {
            const lwc = (window as unknown as {
                LightweightCharts?: { LineSeries?: never };
            }).LightweightCharts;
            if (!lwc?.LineSeries) return null;
            this.series = this.chart.addSeries(lwc.LineSeries as never, {
                color: 'transparent',
                lineVisible: false,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
            } as never) as unknown as ISeriesApi<'Line'>;
        } catch { /* ignore */ }
        return this.series;
    }

    /** 新数据（K 线）：同步隐形序列（**保留鼠标悬停** ✓）
     *
     * 以前这里 `this.mouseIndex = null` → 实时图表每拍都推 K 线 →
     * 鼠标停在历史某根上，下一秒就被清回"最新" → VP 看起来**不跟随鼠标** ✗
     * （用户实测）。现在鼠标位置按**时间**记（`mouseTime`），
     * 数据变了只重算下标，悬停位置保持不变 ✓
     */
    setBars(bars: BarLike[]): void {
        this.bars = bars || [];
        const series = this.ensureSeries();
        if (series && this.bars.length) {
            try {
                series.setData(this.bars.map((bar) => ({
                    time: bar.time as never,
                    value: Number(bar.close) || 0,
                })));
            } catch { /* ignore */ }
        }
        this.draw();
    }

    setData(data: VpData | null): void {
        this.data = data;
        if (!data) {
            // ★ 删指标 → 立刻清画布（否则残留最后一屏 ✗）
            try {
                const ratio = window.devicePixelRatio || 1;
                this.ctx?.clearRect(0, 0, this.canvas.width / ratio,
                    this.canvas.height / ratio);
            } catch { /* ignore */ }
            return;
        }
        this.draw();
    }

    /** 鼠标在某一根上（`null` / 空白区 = 回到实时最新 VP ✓） */
    onCrosshair(time: number | null | undefined): void {
        const stamp = time == null ? null : Number(time);
        if (stamp === this.mouseTime) return;
        this.mouseTime = Number.isFinite(stamp) ? stamp : null;
        this.draw();
    }

    /** VP 矩阵的行数（`vpMatrix` 的行）✓ */
    private _rowCount(): number {
        return this.data?.matrix?.length || 0;
    }

    /** 最后一行的下标（没有鼠标时画"最新那根"的分布 ✓） */
    private _lastRow(): number {
        const rows = this._rowCount();
        const times = this.data?.times || [];
        if (rows) return rows - 1;
        return Math.max(0, (times.length || this.bars.length) - 1);
    }

    /** 时间 → VP 矩阵的**行号**（优先用 `times`，回退图表下标 ✓） */
    private _rowFor(time: number): number | null {
        const times = this.data?.times || [];
        if (times.length) {
            const row = this._search(times, time);
            if (row !== null) return row;
            return null;
        }
        return this._indexOf(time);
    }

    private _search(values: number[], time: number): number | null {
        if (!values.length) return null;
        // ★ 精确命中最好；**找不到就取最近的一根**（真实图表十字线的
        //   `param.time` 时常落在两根之间 / 是可视区右侧空白 → 以前直接
        //   返回 null → 回落到"最新一根"，看起来就是**不跟随鼠标** ✗
        //   用户实测 2026-11-03：实时图表的 VP 永远是最后一根）。
        //   只在时间落在数据范围内时才取近似（超出范围 = 真没数据 ✓）
        const first = Number(values[0]);
        const last = Number(values[values.length - 1]);
        if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
        if (time < first || time > last) return null;
        let low = 0;
        let high = values.length - 1;
        let nearest = 0;
        let best = Number.POSITIVE_INFINITY;
        while (low <= high) {
            const mid = (low + high) >> 1;
            const value = Number(values[mid]);
            if (value === time) return mid;
            const distance = Math.abs(value - time);
            if (distance < best) { best = distance; nearest = mid; }
            if (value < time) low = mid + 1; else high = mid - 1;
        }
        return nearest;
    }

    private _indexOf(time: number): number | null {
        const bars = this.bars;
        if (!bars.length) return null;
        let low = 0;
        let high = bars.length - 1;
        while (low <= high) {
            const mid = (low + high) >> 1;
            const value = Number(bars[mid]?.time);
            if (value === time) return mid;
            if (value < time) low = mid + 1;
            else high = mid - 1;
        }
        return null;
    }

    /** 容器尺寸（由页面在 `resize()` 时调用 ✓） */
    resize(): void {
        const rect = this.host.getBoundingClientRect();
        const width = Math.max(0, Math.round(rect.width));
        const height = Math.max(0, Math.round(rect.height));
        if (!width || !height) return;
        this.bounds = { width, height };
        const ratio = window.devicePixelRatio || 1;
        this.canvas.width = Math.round(width * ratio);
        this.canvas.height = Math.round(height * ratio);
        this.canvas.style.width = `${width}px`;
        this.canvas.style.height = `${height}px`;
        this.draw();
    }

    /** rAF 节流重绘（拖动/缩放时每帧最多一次 ✓） */
    draw(): void {
        if (this.frame) return;
        this.frame = window.requestAnimationFrame(() => {
            this.frame = 0;
            this._paint();
        });
    }

    private _paint(): void {
        const ctx = this.ctx;
        const data = this.data;
        if (!ctx) return;
        if (!data?.matrix?.length) {
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        const width = this.bounds.width;
        const height = this.bounds.height;
        if (!width || !height) return;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const series = this.ensureSeries();
        if (!series) return;
        // ★ 行号优先按 **VP 自己的时间轴**算：
        //   实时图表的 K 线可能比策略那段多（无限历史向左补），
        //   用图表下标去取矩阵会错位 / 取到 undefined → 悬停时啥也不画 ✗
        const hovered = this.mouseTime === null
            ? null : this._rowFor(this.mouseTime);
        const barIndex = hovered ?? this._lastRow();
        const values = data.matrix[barIndex];
        const lo = data.lo[barIndex];
        const hi = data.hi[barIndex];
        if (!values || !Number.isFinite(lo) || !Number.isFinite(hi)
            || hi <= lo) {
            return;
        }
        const style = data.style || {};
        const bins = values.length;
        const step = (hi - lo) / bins;
        const binRatio = Number(style.bin_ratio) || 0.88;
        const frac = Number(style.profile_frac) || 0.30;
        // 满量程 = 可视跨度 × `profile_frac`（minibt 的 `BAND` 同款 ✓）
        const span = Math.max(60, Math.min(width / 8, 420));
        void span;
        const band = span * frac;
        const peak = Math.max(...values.map((v) => Number(v) || 0));
        if (!(peak > 0)) return;
        const alpha = Number(style.fill_alpha) || 0.6;
        // ★ 右边缘 = **时间轴宽度**（价格轴左侧），不是整个容器宽度 ✗
        let paneWidth = width;
        try {
            const scale = this.chart.timeScale() as unknown as {
                width?: () => number; height?: () => number;
            };
            const w = Number(scale.width?.());
            if (Number.isFinite(w) && w > 0) paneWidth = w;
        } catch { /* ignore */ }
        const xRight = paneWidth - 2;
        let peakIndex = 0;
        values.forEach((value, index) => {
            if (Number(value) > Number(values[peakIndex])) peakIndex = index;
        });

        let painted = 0;
        let minY = Number.POSITIVE_INFINITY;
        let maxY = Number.NEGATIVE_INFINITY;
        for (let index = 0; index < bins; index += 1) {
            const value = Number(values[index]) || 0;
            if (value <= 0) continue;
            const top = lo + (index + 1) * step;
            const bottom = lo + index * step;
            const gap = step * (1 - binRatio) / 2;
            const y1 = series.priceToCoordinate(top - gap) as number | null;
            const y2 = series.priceToCoordinate(bottom + gap) as number | null;
            if (y1 === null || y2 === null) continue;
            const h = Math.max(1, Math.abs(y2 - y1));
            const w = Math.max(2.5, (value / peak) * band);
            const isPoc = style.highlight_poc !== false && index === peakIndex;
            const color = isPoc
                ? (style.poc_color || '#f39c12')
                : (style.bar_color || '#3498db');
            ctx.fillStyle = rgba(color, alpha);
            ctx.fillRect(xRight - w, Math.min(y1, y2), w, h);
            painted += 1;
            minY = Math.min(minY, y1, y2);
            maxY = Math.max(maxY, y1, y2);
            if (style.line_color) {
                ctx.strokeStyle = rgba(String(style.line_color), 0.85);
                ctx.lineWidth = Math.max(0.4,
                    Number(style.line_width) || 0.4);
                ctx.strokeRect(xRight - w, Math.min(y1, y2), w, h);
            }
        }
        // 调试快照：最后画了哪一行 / 落在哪个像素区间（排查位置问题 ✓）
        this.lastPaint = {
            row: barIndex, bins: painted, xRight,
            yTop: Math.round(minY), yBottom: Math.round(maxY),
            lo, hi, peak,
        };
        // 0 刻度（右端竖线，minibt 里是成交量轴 ✓）
        ctx.strokeStyle = rgba(this.theme() === 'light' ? '#8a8f98' : '#5a5f66',
            0.5);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xRight, 0);
        ctx.lineTo(xRight, height);
        ctx.stroke();
    }
}

const NAMED: Record<string, [number, number, number]> = {
    skyblue: [135, 206, 235], orange: [255, 165, 0], lime: [0, 255, 0],
    tomato: [255, 99, 71], white: [255, 255, 255], red: [255, 0, 0],
    green: [0, 128, 0], blue: [0, 0, 255], gold: [255, 215, 0],
    steelblue: [70, 130, 180], gray: [128, 128, 128], grey: [128, 128, 128],
};

/** 颜色 → `rgba()`（命名色 / `#rrggbb` 两种 ✓） */
export function rgba(color: string, alpha: number): string {
    const text = String(color || '').trim();
    const named = NAMED[text.toLowerCase()];
    if (named) return `rgba(${named[0]}, ${named[1]}, ${named[2]}, ${alpha})`;
    if (/^#[0-9a-f]{6}$/i.test(text)) {
        const r = parseInt(text.slice(1, 3), 16);
        const g = parseInt(text.slice(3, 5), 16);
        const b = parseInt(text.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    return text;
}

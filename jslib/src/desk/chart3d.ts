/**
 * 极小的 3D 散点（参数优化的「帕累托前沿」三维视图）✓
 *
 * 为什么不引 3D 库：desk 是**离线可用**的产品，不能指望用户联网装依赖；
 * 参数优化的三维图只需要「轴 + 网格 + 点」，用 canvas 2D 手写投影足够，
 * 而且体积是 0（整个文件几 KB）。
 *
 * 约定：输入点先归一到 [-1, 1]（`normalize3D`），再按相机角度旋转
 * （`rotatePoint`：先绕 Y 轴 yaw、再绕 X 轴 pitch），最后做一次**简单透视**
 * 投影（`projectPoint`：越远越小）。旋转 / 投影都是纯函数，方便单测 ✓
 */

export interface Point3 {
    x: number;
    y: number;
    z: number;
}

export interface Projected extends Point3 {
    /** 投影后的屏幕坐标（CSS px） */
    sx: number;
    sy: number;
    /** 透视缩放系数（1 = 与中心同深度；越大越近） */
    k: number;
    /** 原始数据在 `SceneOptions.points` 里的下标 ✓ */
    index?: number;
}

export interface AxisRange {
    min: number;
    max: number;
    label: string;
}

/** 相机（弧度）：yaw 绕 Y 轴转，pitch 绕 X 轴转 ✓ */
export interface Camera {
    yaw: number;
    pitch: number;
}

/** 默认视角：斜 35° / 俯 22°（能同时看到三个面，观感和 matplotlib 类似） */
export const DEFAULT_CAMERA: Camera = { yaw: -0.62, pitch: 0.38 };

const DEG = Math.PI / 180;

/** 角度（度）→ 弧度 */
export function rad(deg: number): number {
    return deg * DEG;
}

/** 数值 → [-1, 1]（全相等时给 0，避免除 0 ✓） */
export function normalizeValue(value: number, min: number, max: number): number {
    if (!Number.isFinite(value)) return 0;
    const span = max - min;
    if (!Number.isFinite(span) || span === 0) return 0;
    return (value - min) / span * 2 - 1;
}

/** 一组数值的显示范围（留 8% 余量；全相等时 ±1） */
export function axisRange(values: number[]): [number, number] {
    const finite = values.filter((value) => Number.isFinite(value));
    if (!finite.length) return [0, 1];
    let min = Math.min(...finite);
    let max = Math.max(...finite);
    if (min === max) {
        const pad = Math.abs(min) * 0.1 || 1;
        return [min - pad, max + pad];
    }
    const pad = (max - min) * 0.08;
    return [min - pad, max + pad];
}

/** 把 `(x, y, z)` 用相机角度旋转（先 yaw 后 pitch，右手系 ✓） */
export function rotatePoint(point: Point3, camera: Camera): Point3 {
    const cy = Math.cos(camera.yaw);
    const sy = Math.sin(camera.yaw);
    const cp = Math.cos(camera.pitch);
    const sp = Math.sin(camera.pitch);
    const x1 = point.x * cy - point.z * sy;
    const z1 = point.x * sy + point.z * cy;
    const y1 = point.y * cp - z1 * sp;
    const z2 = point.y * sp + z1 * cp;
    return { x: x1, y: y1, z: z2 };
}

/** 简单透视投影：`depth` 是相机到中心的距离（归一化单位） */
export function projectPoint(
    point: Point3, camera: Camera, scale: number,
    cx: number, cy: number, depth = 3.4,
): Projected {
    const rotated = rotatePoint(point, camera);
    const k = depth / Math.max(0.2, depth - rotated.z * 0.85);
    return {
        ...rotated,
        sx: cx + rotated.x * scale * k,
        sy: cy - rotated.y * scale * k,
        k,
    };
}

/** 远 → 近排序（先画远的，近的盖在上面 ✓） */
export function depthOrder(points: Projected[]): Projected[] {
    return [...points].sort((a, b) => a.z - b.z);
}

/** 刻度：均匀取 `count + 1` 个值（含两端） */
export function axisTicks(range: [number, number], count = 4): number[] {
    const [min, max] = range;
    const out: number[] = [];
    for (let index = 0; index <= count; index += 1) {
        out.push(min + (max - min) * (index / count));
    }
    return out;
}

/** 刻度上的数字（大数用 k / M 缩写， kecil 用 4 位小数） */
export function shortNumber(value: number): string {
    const abs = Math.abs(value);
    if (!Number.isFinite(value)) return '--';
    if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
    if (abs >= 1e4) return `${(value / 1e4).toFixed(1)}万`;
    if (abs >= 1000) return value.toFixed(0);
    if (abs >= 10) return value.toFixed(1);
    if (abs >= 1) return value.toFixed(2);
    return value.toFixed(4);
}

/** canvas 的 2D 上下文（只用到这几个方法，方便测试时打桩 ✓） */
export interface Ctx2D {
    clearRect(x: number, y: number, w: number, h: number): void;
    beginPath(): void;
    moveTo(x: number, y: number): void;
    lineTo(x: number, y: number): void;
    stroke(): void;
    fill(): void;
    arc(x: number, y: number, r: number, start: number, end: number): void;
    fillRect(x: number, y: number, w: number, h: number): void;
    fillText(text: string, x: number, y: number): void;
    save(): void;
    restore(): void;
    setLineDash?(segments: number[]): void;
    // 用 DOM 的类型：`CanvasRenderingContext2D` 才能直接传进来（渐变也算 ✓）
    fillStyle: CanvasRenderingContext2D['fillStyle'];
    strokeStyle: CanvasRenderingContext2D['strokeStyle'];
    lineWidth: number;
    globalAlpha: number;
    font: string;
    textAlign: string;
    textBaseline: string;
}

/** 投影参数（`drawScene` 与外部命中测试共用，保证坐标一致 ✓） */
export function sceneMetrics(width: number, height: number): {
    scale: number; cx: number; cy: number;
} {
    return {
        scale: Math.min(width, height) * 0.33,
        cx: width / 2,
        cy: height / 2 + Math.min(width, height) * 0.04,
    };
}

export interface LayoutOptions {
    width: number;
    height: number;
    points: Array<{ point: Point3; index: number }>;
    camera?: Camera;
}

export interface LayoutPoint extends Projected {
    index: number;
}

/** 把点投影成屏幕坐标（命中测试 / 画 tooltip 都用它 ✓） */
export function layoutPoints(options: LayoutOptions): LayoutPoint[] {
    const camera = options.camera || DEFAULT_CAMERA;
    const { scale, cx, cy } = sceneMetrics(options.width, options.height);
    return options.points.map((item) => ({
        ...projectPoint(item.point, camera, scale, cx, cy),
        index: item.index,
    }));
}

/** 找鼠标附近最近的点（`radius` = CSS px，未命中返回 undefined ✓） */
export function hitTestPoint(
    points: LayoutPoint[], sx: number, sy: number, radius = 11,
): LayoutPoint | undefined {
    let best: LayoutPoint | undefined;
    let bestDistance = radius * radius;
    for (const item of points) {
        const dx = item.sx - sx;
        const dy = item.sy - sy;
        const distance = dx * dx + dy * dy;
        if (distance <= bestDistance) {
            bestDistance = distance;
            best = item;
        }
    }
    return best;
}

export interface TooltipOptions {
    x: number;
    y: number;
    lines: string[];
    width: number;
    height: number;
    accent?: string;
    background?: string;
    text?: string;
}

/** canvas 里画一个小浮层（二维图有 `<title>`，三维图用这个 ✓） */
export function drawTooltip(ctx: Ctx2D, options: TooltipOptions): void {
    const lines = options.lines.filter((line) => line !== undefined
        && line !== null && String(line).length > 0);
    if (!lines.length) return;
    const lineHeight = 15;
    const pad = 7;
    const charWidth = 7.2;
    const longest = lines.reduce((max, line) => Math.max(
        max, String(line).length), 0);
    const boxWidth = Math.min(options.width - 8,
        pad * 2 + Math.max(60, longest * charWidth));
    const boxHeight = pad * 2 + lines.length * lineHeight;
    const x = Math.max(4, Math.min(options.width - boxWidth - 4,
        options.x + 12));
    const y = Math.max(4, Math.min(options.height - boxHeight - 4,
        options.y - boxHeight - 10));
    ctx.save();
    ctx.globalAlpha = 0.96;
    ctx.fillStyle = options.background || 'rgba(15, 17, 21, 0.94)';
    ctx.beginPath();
    ctx.fillRect(x, y, boxWidth, boxHeight);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = options.accent || '#2962ff';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + boxWidth, y);
    ctx.stroke();
    ctx.fillStyle = options.text || '#e6e8eb';
    ctx.font = '11.5px sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    lines.forEach((line, index) => {
        ctx.fillText(String(line), x + pad,
                     y + pad + lineHeight * index + lineHeight / 2);
    });
    ctx.restore();
}

export interface SceneOptions {
    width: number;
    height: number;
    /** 点（已归一化到 [-1,1]） */
    points: Array<{ point: Point3; index: number }>;
    axes: [AxisRange, AxisRange, AxisRange];
    camera?: Camera;
    /** 高亮的点（`points` 里的 `index`） */
    highlight?: number;
    /** 鼠标悬停的点（画一圈外环，配合 `drawTooltip` ✓） */
    hovered?: number;
    accent?: string;
    highlightColor?: string;
}

/** 画一个 3D 散点：三条轴 + 背面网格 + 点（含高亮） */
export function drawScene(ctx: Ctx2D, options: SceneOptions): void {
    const { width, height } = options;
    const camera = options.camera || DEFAULT_CAMERA;
    const accent = options.accent || '#2962ff';
    const highlightColor = options.highlightColor || '#ef5350';
    const { scale, cx, cy } = sceneMetrics(width, height);
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const axisColors = ['#f0b90b', '#2196f3', '#26a69a'];
    const ends: Point3[] = [
        { x: 1, y: -1, z: -1 },     // X+
        { x: -1, y: 1, z: -1 },     // Y+
        { x: -1, y: -1, z: 1 },     // Z+
    ];
    const origin = { x: -1, y: -1, z: -1 };
    const originScreen = projectPoint(origin, camera, scale, cx, cy);

    // 三条轴（从 (min,min,min) 出发）+ 刻度标签
    ends.forEach((end, index) => {
        const target = projectPoint(end, camera, scale, cx, cy);
        ctx.strokeStyle = axisColors[index];
        ctx.lineWidth = 1.4;
        ctx.globalAlpha = 0.95;
        ctx.beginPath();
        ctx.moveTo(originScreen.sx, originScreen.sy);
        ctx.lineTo(target.sx, target.sy);
        ctx.stroke();
        const range = options.axes[index];
        const ticks = axisTicks([range.min, range.max], 3);
        ctx.fillStyle = axisColors[index];
        ctx.globalAlpha = 0.85;
        ticks.forEach((tick) => {
            const t = (tick - range.min) / ((range.max - range.min) || 1);
            const point: Point3 = {
                x: origin.x + (end.x - origin.x) * t,
                y: origin.y + (end.y - origin.y) * t,
                z: origin.z + (end.z - origin.z) * t,
            };
            const screen = projectPoint(point, camera, scale, cx, cy);
            ctx.fillText(shortNumber(tick), screen.sx, screen.sy - 8);
        });
        // 轴名
        const label = projectPoint(
            { x: end.x * 1.12, y: end.y * 1.12, z: end.z * 1.12 },
            camera, scale, cx, cy);
        ctx.font = '12px sans-serif';
        ctx.fillText(range.label, label.sx, label.sy);
        ctx.font = '11px sans-serif';
    });

    // 另外两条棱（视觉参考线，淡一点）
    const refs: Array<[Point3, Point3]> = [
        [{ x: 1, y: -1, z: -1 }, { x: 1, y: 1, z: -1 }],
        [{ x: 1, y: -1, z: -1 }, { x: 1, y: -1, z: 1 }],
        [{ x: -1, y: 1, z: -1 }, { x: -1, y: 1, z: 1 }],
    ];
    ctx.globalAlpha = 0.18;
    ctx.strokeStyle = '#8b93a1';
    ctx.lineWidth = 1;
    refs.forEach(([from, to]) => {
        const a = projectPoint(from, camera, scale, cx, cy);
        const b = projectPoint(to, camera, scale, cx, cy);
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();
    });

    // 点（远 → 近）
    const projected = layoutPoints({
        width, height, points: options.points, camera,
    });
    depthOrder(projected).forEach((item) => {
        const best = options.highlight !== undefined
            && item.index === options.highlight;
        const hover = options.hovered !== undefined
            && item.index === options.hovered;
        ctx.globalAlpha = best || hover ? 1 : 0.78;
        ctx.fillStyle = best ? highlightColor : accent;
        ctx.beginPath();
        ctx.arc(item.sx, item.sy,
               Math.max(2.2, 3.4 * item.k) * (hover ? 1.5 : 1),
               0, Math.PI * 2);
        ctx.fill();
        if (hover) {
            ctx.globalAlpha = 0.9;
            ctx.strokeStyle = highlightColor;
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            ctx.arc(item.sx, item.sy, Math.max(4.5, 5.2 * item.k),
                   0, Math.PI * 2);
            ctx.stroke();
        }
    });
    ctx.restore();
}

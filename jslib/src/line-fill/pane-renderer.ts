import { IPrimitivePaneRenderer } from "lightweight-charts";
import { CanvasRenderingTarget2D } from "fancy-canvas";
import { FillPoint, LineFillOptions } from "./line-fill";
import { setLineStyle } from "../helpers/canvas-rendering";

export class LineFillPaneRenderer implements IPrimitivePaneRenderer {
    _points: FillPoint[];
    _options: LineFillOptions;

    constructor(points: FillPoint[], options: LineFillOptions) {
        this._points = points;
        this._options = options;
    }

    draw(target: CanvasRenderingTarget2D) {
        if (this._points.length < 2) return;
        target.useBitmapCoordinateSpace(scope => {
            const h = scope.horizontalPixelRatio;
            const v = scope.verticalPixelRatio;
            const ctx = scope.context;

            // upper line left → right, then lower line right → left, closes itself
            ctx.beginPath();
            this._points.forEach((point, index) => {
                const x = point.x * h;
                const y = point.y1 * v;
                if (index === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            });
            for (let index = this._points.length - 1; index >= 0; index--) {
                const point = this._points[index];
                ctx.lineTo(point.x * h, point.y2 * v);
            }
            ctx.closePath();
            const previousAlpha = ctx.globalAlpha;
            if (this._options.opacity !== null && this._options.opacity !== undefined) {
                ctx.globalAlpha = this._options.opacity;
            }
            ctx.fillStyle = this._options.fillColor;
            ctx.fill();
            ctx.globalAlpha = previousAlpha;

            if (this._options.lineColor) {
                ctx.lineWidth = Math.max(1, this._options.width * v);
                ctx.strokeStyle = this._options.lineColor;
                setLineStyle(ctx, this._options.lineStyle as never);
                ctx.stroke();
            }
        });
    }
}

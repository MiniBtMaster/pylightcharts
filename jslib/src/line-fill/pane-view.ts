import { IPrimitivePaneView } from "lightweight-charts";
import { FillPoint, LineFill } from "./line-fill";
import { LineFillPaneRenderer } from "./pane-renderer";

interface PointLike {
    time: unknown;
    value?: number;
}

export class LineFillPaneView implements IPrimitivePaneView {
    _source: LineFill;
    _points: FillPoint[] = [];

    constructor(source: LineFill) {
        this._source = source;
    }

    zOrder(): 'bottom' | 'normal' | 'top' {
        return 'bottom';
    }

    update() {
        const source = this._source;
        const timeScale = source.chart.timeScale();

        // the other line is looked up by time: only the shared stamps are filled
        const others = new Map<unknown, number>();
        for (const point of source._other.data() as PointLike[]) {
            if (point.value !== undefined) {
                others.set(point.time, point.value);
            }
        }

        const points: FillPoint[] = [];
        for (const point of source.series.data() as PointLike[]) {
            const otherValue = others.get(point.time);
            if (point.value === undefined || otherValue === undefined) continue;
            const x = timeScale.timeToCoordinate(point.time as never);
            if (x === null) continue;
            const y1 = source.series.priceToCoordinate(point.value);
            const y2 = source._other.priceToCoordinate(otherValue);
            if (y1 === null || y2 === null) continue;
            points.push({ x: x as number, y1: y1 as number, y2: y2 as number });
        }
        this._points = points;
    }

    renderer() {
        return new LineFillPaneRenderer(this._points, this._source._options);
    }
}

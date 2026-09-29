import { describe, expect, it } from 'vitest';

import { CustomSeriesPaneView } from '../src/custom-series/custom-series';

/**
 * Regression tests for the "off-screen shapes pile up while zooming" bug.
 *
 * The library only writes coordinates for the bars inside `visibleRange`
 * (`TimeScale.indexesToCoordinates`). Bars outside it keep a stale - and still
 * finite - `x` from the previous viewport, so a renderer that iterates `_bars`
 * re-draws them on top of the visible data.
 */

interface Rect {
    x: number;
    y: number;
    width: number;
    height: number;
}

/** A CanvasRenderingTarget2D stand-in that records fillRect calls. */
function makeTarget(recorded: Rect[]) {
    const context = {
        fillStyle: '',
        strokeStyle: '',
        lineWidth: 1,
        font: '',
        textAlign: 'center' as CanvasTextAlign,
        textBaseline: 'middle' as CanvasTextBaseline,
        save() { /* noop */ },
        restore() { /* noop */ },
        beginPath() { /* noop */ },
        fill() { /* noop */ },
        stroke() { /* noop */ },
        setLineDash() { /* noop */ },
        moveTo() { /* noop */ },
        lineTo() { /* noop */ },
        arc() { /* noop */ },
        fillText() { /* noop */ },
        strokeRect() { /* noop */ },
        fillRect(x: number, y: number, width: number, height: number) {
            recorded.push({ x, y, width, height });
        },
    };
    return {
        useBitmapCoordinateSpace(callback: (scope: unknown) => void): void {
            callback({
                context,
                horizontalPixelRatio: 1,
                verticalPixelRatio: 1,
                mediaSize: { width: 800, height: 600 },
                bitmapSize: { width: 800, height: 600 },
            });
        },
    };
}

/** One bar whose rect spans the price range [index, index + 1]. */
function bar(index: number, x: number) {
    return {
        x,
        originalData: {
            time: index,
            value: 100,
            shapes: [
                {
                    type: 'rect',
                    from: index,
                    to: index + 1,
                    left: -0.1,
                    right: 0.1,
                    fillColor: '#00ff00',
                },
            ],
        },
    };
}

const CONVERTER = (price: number): number => price;

describe('custom series visible range', () => {
    it('draws only the bars inside visibleRange', () => {
        const view = new CustomSeriesPaneView();
        // All ten bars carry a coordinate from a previous, wider viewport; the
        // current visible slice is 4..7, the rest are stale.
        const bars = Array.from({ length: 10 }, (_, index) => bar(index, index * 10));
        view.update(
            { bars, barSpacing: 10, visibleRange: { from: 4, to: 7 }, conflationFactor: 1 } as never,
            {} as never,
        );

        const drawn: Rect[] = [];
        view.renderer().draw(makeTarget(drawn) as never, CONVERTER as never);

        // The y coordinate is the bar's price, so it identifies the bar.
        expect(drawn.map(rect => rect.y)).toEqual([4, 5, 6]);
    });

    it('skips bars without a finite coordinate', () => {
        const view = new CustomSeriesPaneView();
        const bars = [bar(0, 0), { x: NaN, originalData: bar(1, 0).originalData }, bar(2, 20)];
        view.update(
            { bars, barSpacing: 10, visibleRange: { from: 0, to: 3 }, conflationFactor: 1 } as never,
            {} as never,
        );

        const drawn: Rect[] = [];
        view.renderer().draw(makeTarget(drawn) as never, CONVERTER as never);

        expect(drawn.map(rect => rect.y)).toEqual([0, 2]);
    });

    it('exposes the visible slice to rendererDraw callbacks', () => {
        const view = new CustomSeriesPaneView();
        const bars = Array.from({ length: 10 }, (_, index) => bar(index, index * 10));
        view.update(
            { bars, barSpacing: 10, visibleRange: { from: 4, to: 7 }, conflationFactor: 1 } as never,
            {} as never,
        );

        expect(view.visibleBars()).toEqual(bars.slice(4, 7));
    });

    it('falls back to every bar when no visible range is known', () => {
        const view = new CustomSeriesPaneView();
        const bars = [bar(0, 0), bar(1, 10)];
        view.update(
            { bars, barSpacing: 10, visibleRange: null, conflationFactor: 1 } as never,
            {} as never,
        );

        expect(view.visibleBars()).toEqual(bars);
    });
});

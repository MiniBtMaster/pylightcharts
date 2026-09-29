import { GlobalParams } from "./global-params";
import { Handler } from "./handler";

declare const window: GlobalParams

/** One divider between two neighbouring charts of a layout. */
interface Divider {
    elem: HTMLDivElement;
    before: Handler;
    after: Handler;
}

interface LayoutState {
    handlers: Handler[];
    kind: string;
    size: number;
    dividers: Divider[];
    detach: () => void;
}

/**
 * Draggable dividers between the charts of a layout.
 *
 * The charts of a `pylightcharts.layout.Layout` are floated siblings sized as
 * fractions of the window, so a separator can simply be floated between them:
 * it takes `size` pixels out of the page and the drag hands those pixels from
 * one chart to the other (see `Layout` in python).
 */
export class LayoutSplitter {
    private static _states = new Map<string, LayoutState>();

    /** (Re)create the dividers of one layout. `size <= 0` removes them. */
    public static set(
        layoutId: string,
        handlers: Handler[],
        kind: string,
        size: number,
        color: string,
        hoverColor: string,
        callbackName?: string,
    ) {
        LayoutSplitter.clear(layoutId);

        LayoutSplitter._fit(handlers, kind, size);

        if (size <= 0 || handlers.length < 2) return;

        const dividers: Divider[] = [];
        for (let i = 0; i + 1 < handlers.length; i++) {
            const before = handlers[i];
            const after = handlers[i + 1];
            const parent = after.wrapper.parentNode;
            if (!parent || before.wrapper.parentNode !== parent) continue;
            const divider = LayoutSplitter._makeDivider(kind, size, color,
                hoverColor, LayoutSplitter._pageHeight());
            parent.insertBefore(divider, after.wrapper);
            LayoutSplitter._bindDrag(divider, before, after, kind,
                handlers, callbackName);
            dividers.push({ elem: divider, before, after });
        }

        // window resizes change the space left for the charts: the fixed
        // divider size has to be subtracted again
        const onResize = () => {
            LayoutSplitter._fit(handlers, kind, size);
            const height = LayoutSplitter._pageHeight();
            for (const divider of dividers) {
                if (kind !== 'vertical') {
                    divider.elem.style.height = `${height}px`;
                }
            }
        };
        window.addEventListener('resize', onResize);
        LayoutSplitter._states.set(layoutId, {
            handlers, kind, size, dividers,
            detach: () => window.removeEventListener('resize', onResize),
        });
    }

    /** Remove the dividers of one layout and give the space back. */
    public static clear(layoutId: string) {
        const state = LayoutSplitter._states.get(layoutId);
        if (!state) return;
        state.detach();
        for (const divider of state.dividers) divider.elem.remove();
        LayoutSplitter._states.delete(layoutId);
        // no re-fit here: the caller applies the new geometry right away, and
        // re-fitting with the *previous* kind would undo a layout switch
    }

    /** Height a chart (or a vertical bar) may use: the window minus its
     *  page-level top bars. */
    private static _pageHeight() {
        return window.innerHeight - Handler.pageHeight();
    }

    /** Size of the charts along the layout axis ('horizontal' -> width). */
    private static _total(kind: string) {
        if (kind === 'vertical') return LayoutSplitter._pageHeight();
        return window.containerDiv.clientWidth;
    }

    /** Give every chart the same share, minus the dividers. */
    private static _fit(handlers: Handler[], kind: string, size: number) {
        if (!handlers.length) return;
        const total = LayoutSplitter._total(kind);
        const usable = total - size * (handlers.length - 1);
        const each = usable / handlers.length;
        for (const handler of handlers) {
            LayoutSplitter._applySize(handler, kind, each, total);
        }
    }

    private static _applySize(handler: Handler, kind: string, px: number,
                              total: number) {
        if (!total) return;
        if (kind === 'vertical') {
            handler.scale.height = px / total;
        } else {
            handler.scale.width = px / total;
        }
        handler.reSize();
    }

    private static _size(handler: Handler, kind: string) {
        const rect = handler.wrapper.getBoundingClientRect();
        return kind === 'vertical' ? rect.height : rect.width;
    }

    private static _makeDivider(kind: string, size: number, color: string,
                                hoverColor: string, pageHeight: number) {
        const divider = document.createElement('div');
        divider.classList.add('layout-divider');
        divider.classList.add(`layout-divider-${kind}`);
        // px, not %: the container's height is auto, so a percentage height
        // would collapse the drag area to 0
        divider.style.cssText = kind === 'vertical'
            ? `float: left; clear: both; width: 100%; height: ${size}px;`
            : `float: left; width: ${size}px; height: ${pageHeight}px;`;
        divider.style.position = 'relative';
        divider.style.zIndex = '100';
        divider.style.cursor = kind === 'vertical'
            ? 'row-resize' : 'col-resize';
        divider.style.backgroundColor = color;
        divider.addEventListener('mouseenter',
            () => divider.style.backgroundColor = hoverColor);
        divider.addEventListener('mouseleave',
            () => divider.style.backgroundColor = color);
        return divider;
    }

    private static _bindDrag(
        divider: HTMLDivElement,
        before: Handler,
        after: Handler,
        kind: string,
        handlers: Handler[],
        callbackName?: string,
    ) {
        const MIN = 40;                       // px, both sides stay usable

        const report = () => {
            if (!callbackName) return;
            const shares = handlers.map((handler) => {
                const value = kind === 'vertical'
                    ? handler.scale.height : handler.scale.width;
                return value.toFixed(6);
            });
            window.callbackFunction(`${callbackName}_~_${shares.join(';;;')}`);
        };

        divider.addEventListener('mousedown', (event: MouseEvent) => {
            event.preventDefault();
            const total = LayoutSplitter._total(kind);
            const start = kind === 'vertical' ? event.clientY : event.clientX;
            const first = LayoutSplitter._size(before, kind);
            const second = LayoutSplitter._size(after, kind);
            const body = document.body;
            const previousSelect = body.style.userSelect;
            body.style.userSelect = 'none';

            const onMove = (move: MouseEvent) => {
                const axis = kind === 'vertical' ? move.clientY : move.clientX;
                const delta = axis - start;
                const room = first + second;
                const limit = room - MIN;
                const left = Math.max(MIN, Math.min(limit, first + delta));
                LayoutSplitter._applySize(before, kind, left, total);
                LayoutSplitter._applySize(after, kind, room - left, total);
            };
            const onUp = () => {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                body.style.userSelect = previousSelect;
                report();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }
}

/** Called from python (`Layout._apply_dividers`). */
export function setLayoutDividers(
    layoutId: string,
    handlers: Handler[],
    kind: string,
    size: number,
    color: string,
    hoverColor: string,
    callbackName?: string,
) {
    LayoutSplitter.set(layoutId, handlers, kind, size, color, hoverColor,
        callbackName);
}

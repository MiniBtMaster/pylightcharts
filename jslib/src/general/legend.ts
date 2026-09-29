import { ISeriesApi, LineData, Logical, MouseEventParams, PriceFormatBuiltIn, SeriesType } from "lightweight-charts";
import { Handler } from "./handler";
import { seriesColor } from "./series-color";


interface LineElement {
    name: string;
    div: HTMLDivElement;
    row: HTMLDivElement;
    toggle?: HTMLDivElement;
    series: ISeriesApi<SeriesType>,
    solid: string;
}

// The eye is drawn by this bundle (upstream Lightweight Charts has no such
// control). `stroke: currentColor` (not a hard-coded white) makes the icon
// follow the legend's text colour, which python sets with `legend(color=...)`
// and a theme re-applies - on a light background a white eye is invisible.
const EYE_OPEN = `
    <path style="fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;stroke:currentColor;stroke-opacity:1;stroke-miterlimit:4;" d="M 21.998437 12 C 21.998437 12 18.998437 18 12 18 C 5.001562 18 2.001562 12 2.001562 12 C 2.001562 12 5.001562 6 12 6 C 18.998437 6 21.998437 12 21.998437 12 Z M 21.998437 12 " transform="matrix(0.833333,0,0,0.833333,0,0)"/>
    <path style="fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;stroke:currentColor;stroke-opacity:1;stroke-miterlimit:4;" d="M 15 12 C 15 13.654687 13.654687 15 12 15 C 10.345312 15 9 13.654687 9 12 C 9 10.345312 10.345312 9 12 9 C 13.654687 9 15 10.345312 15 12 Z M 15 12 " transform="matrix(0.833333,0,0,0.833333,0,0)"/>
`;
const EYE_CLOSED = `
    <path style="fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;stroke:currentColor;stroke-opacity:1;stroke-miterlimit:4;" d="M 20.001562 9 C 20.001562 9 19.678125 9.665625 18.998437 10.514062 M 12 14.001562 C 10.392187 14.001562 9.046875 13.589062 7.95 12.998437 M 12 14.001562 C 13.607812 14.001562 14.953125 13.589062 16.05 12.998437 M 12 14.001562 L 12 17.498437 M 3.998437 9 C 3.998437 9 4.354687 9.735937 5.104687 10.645312 M 7.95 12.998437 L 5.001562 15.998437 M 7.95 12.998437 C 6.689062 12.328125 5.751562 11.423437 5.104687 10.645312 M 16.05 12.998437 L 18.501562 15.998437 M 16.05 12.998437 C 17.38125 12.290625 18.351562 11.320312 18.998437 10.514062 M 5.104687 10.645312 L 2.001562 12 M 18.998437 10.514062 L 21.998437 12 " transform="matrix(0.833333,0,0,0.833333,0,0)"/>
`;

export class Legend {
    private handler: Handler;
    public div: HTMLDivElement;
    public seriesContainer: HTMLDivElement

    private ohlcEnabled: boolean = false;
    private percentEnabled: boolean = false;
    private linesEnabled: boolean = false;
    private colorBasedOnCandle: boolean = false;

    private text: HTMLSpanElement;
    private candle: HTMLDivElement;
    public _lines: LineElement[] = [];
    /** pane the legend is anchored to, and the observer watching it */
    private _observedPane: HTMLElement | null = null;
    private _paneObserver: ResizeObserver | null = null;
    private _containerObserver: MutationObserver | null = null;
    private _scheduled = false;


    constructor(handler: Handler) {
        this.legendHandler = this.legendHandler.bind(this)

        this.handler = handler;
        this.ohlcEnabled = false;
        this.percentEnabled = false
        this.linesEnabled = false
        this.colorBasedOnCandle = false

        this.div = document.createElement('div');
        this.div.classList.add("legend")
        this.div.style.maxWidth = `${(handler.scale.width * 100) - 8}vw`
        this.div.style.display = 'none';
        
        const seriesWrapper = document.createElement('div');
        seriesWrapper.style.display = 'flex';
        seriesWrapper.style.flexDirection = 'row';
        this.seriesContainer = document.createElement("div");
        this.seriesContainer.classList.add("series-container");

        this.text = document.createElement('span')
        this.text.style.lineHeight = '1.8'
        this.candle = document.createElement('div')
        
        seriesWrapper.appendChild(this.seriesContainer);
        this.div.appendChild(this.text)
        this.div.appendChild(this.candle)
        this.div.appendChild(seriesWrapper)
        handler.div.appendChild(this.div)

        // this.makeSeriesRows(handler);

        handler.addCrosshairListener(this.legendHandler)
        this.updatePosition()
    }

    /**
     * Keep the legend clear of the left price scale.
     *
     * The legend is anchored 10px from the container's left edge, which is
     * exactly where a visible left price scale draws its labels (e.g. after
     * `chart.add_symbol(..., scale='left')`), so the two overlapped. Anchoring it
     * to the pane instead fixes that; the pane's rectangle is re-read on every
     * crosshair move and whenever the pane is resized, so a scale that appears,
     * disappears or gets wider is followed.
     */
    updatePosition() {
        const container = this.handler.div.getBoundingClientRect();
        const pane = this.handler.chart.panes()[0]?.getHTMLElement?.();
        if (pane) this._watch(pane);
        // the pane follows the container's top-left corner, but a chart-layout
        // change (a scale appearing / disappearing / growing) can move it
        // without resizing it, so the container's own subtree is watched too
        this._watchContainer();
        if (!pane) return;
        // `getHTMLElement()` is the pane *widget*, which spans the price scales:
        // the drawing area starts after the left one (that is where the legend's
        // text used to land)
        const widget = pane.getBoundingClientRect().left - container.left;
        const left = widget + this.handler.chart.priceScale('left').width();
        const value = `${Math.max(0, Math.round(left)) + 10}px`;
        // assigning the same value must not wake the observer up again
        if (this.div.style.left !== value) this.div.style.left = value;
    }

    private _watch(pane: HTMLElement) {
        if (this._observedPane === pane) return;
        this._paneObserver?.disconnect();
        if (typeof ResizeObserver !== 'undefined') {
            this._paneObserver = new ResizeObserver(() => this.updatePosition());
            this._paneObserver.observe(pane);
        }
        this._observedPane = pane;
    }

    private _watchContainer() {
        if (this._containerObserver || typeof MutationObserver === 'undefined') {
            return;
        }
        this._containerObserver = new MutationObserver(() => {
            if (this._scheduled) return;
            // coalesce the burst of mutations a single layout change produces
            this._scheduled = true;
            requestAnimationFrame(() => {
                this._scheduled = false;
                this.updatePosition();
            });
        });
        this._containerObserver.observe(this.handler.div,
            { childList: true, subtree: true, attributes: true });
    }

    toJSON() {
        // Exclude the chart attribute from serialization
        const {_lines, handler, ...serialized} = this;
        return serialized;
    }

    // makeSeriesRows(handler: Handler) {
    //     if (this.linesEnabled) handler._seriesList.forEach(s => this.makeSeriesRow(s))
    // }

    makeSeriesRow(name: string, series: ISeriesApi<SeriesType>, showToggle: boolean = true) {
        let row = document.createElement('div')
        row.style.display = 'flex'
        row.style.alignItems = 'center'
        let div = document.createElement('div')

        // shared with the tooltips: which option carries a series' colour
        // depends on the series type (`color` / `lineColor` / `topColor`)
        const { solid } = seriesColor(series);

        // The eye is the in-chart entry point for hiding/showing the series.
        // `showToggle` lets a caller turn it off per series (python
        // `legend_toggle=False`) when visibility is handled elsewhere, e.g. by an
        // indicator settings window that calls Line.hide_data()/show_data().
        let toggle: HTMLDivElement | undefined
        if (showToggle) {
            toggle = document.createElement('div')
            toggle.classList.add('legend-toggle-switch')

            let svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.setAttribute("width", "22");
            svg.setAttribute("height", "16");

            let group = document.createElementNS("http://www.w3.org/2000/svg", "g");
            group.innerHTML = EYE_OPEN

            let on = true
            toggle.addEventListener('click', () => {
                on = !on
                group.innerHTML = on ? EYE_OPEN : EYE_CLOSED
                series.applyOptions({ visible: on })
            })

            svg.appendChild(group)
            toggle.appendChild(svg)
        }

        row.appendChild(div)
        if (toggle) row.appendChild(toggle)
        this.seriesContainer.appendChild(row)

        this._lines.push({
            name: name,
            div: div,
            row: row,
            toggle: toggle,
            series: series,
            solid: solid
        });
    }

    legendItemFormat(num: number, decimal: number) { return num.toFixed(decimal).toString().padStart(8, ' ') }

    shorthandFormat(num: number) {
        const absNum = Math.abs(num)
        if (absNum >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (absNum >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString().padStart(8, ' ');
    }

    legendHandler(param: MouseEventParams, usingPoint= false) {
        this.updatePosition()
        if (!this.ohlcEnabled && !this.linesEnabled && !this.percentEnabled) return;
        const options: any = this.handler.series.options()

        if (!param.time) {
            if (this.div.matches(':hover')) {
                // The pointer is on a legend row, which takes the events away from the
                // chart: keep the last values instead of "leaving", otherwise moving
                // across the rows (which steal the pointer) makes the labels flash.
                return
            }
            this.candle.style.color = 'transparent'
            this.candle.innerHTML = this.candle.innerHTML.replace(options['upColor'], '').replace(options['downColor'], '')
            // the value labels are only shown while the crosshair is over a bar
            this._lines.forEach((e) => { e.row.style.display = 'none' })
            return
        }

        let data: any;
        let logical: Logical | null = null;

        if (usingPoint) {
            const timeScale = this.handler.chart.timeScale();
            let coordinate = timeScale.timeToCoordinate(param.time)
            if (coordinate)
            logical = timeScale.coordinateToLogical(coordinate.valueOf())
            if (logical)
            data = this.handler.series.dataByIndex(logical.valueOf())
        }
        else {
            data = param.seriesData.get(this.handler.series);
        }

        this.candle.style.color = ''
        let str = '<span style="line-height: 1.8;">'
        if (data) {
            if (this.ohlcEnabled) {
                str += `O ${this.legendItemFormat(data.open, this.handler.precision)} `
                str += `| H ${this.legendItemFormat(data.high, this.handler.precision)} `
                str += `| L ${this.legendItemFormat(data.low, this.handler.precision)} `
                str += `| C ${this.legendItemFormat(data.close, this.handler.precision)} `
            }

            if (this.percentEnabled) {
                let percentMove = ((data.close - data.open) / data.open) * 100
                let color = percentMove > 0 ? options['upColor'] : options['downColor']
                let percentStr = `${percentMove >= 0 ? '+' : ''}${percentMove.toFixed(2)} %`

                if (this.colorBasedOnCandle) {
                    str += `| <span style="color: ${color};">${percentStr}</span>`
                } else {
                    str += '| ' + percentStr
                }
            }

            if (this.handler.volumeSeries) {
                let volumeData: any;
                if (logical) {
                    volumeData = this.handler.volumeSeries.dataByIndex(logical)
                }
                else {
                    volumeData = param.seriesData.get(this.handler.volumeSeries)
                }
                if (volumeData) {
                    str += this.ohlcEnabled ? `<br>V ${this.shorthandFormat(volumeData.value)}` : ''
                }
            }
        }
        this.candle.innerHTML = str + '</span>'

        this._lines.forEach((e) => {
            if (!this.linesEnabled) {
                e.row.style.display = 'none'
                return
            }
            e.row.style.display = 'flex'

            let data
            if (usingPoint && logical) {
                data = e.series.dataByIndex(logical) as LineData
            }
            else {
                data = param.seriesData.get(e.series) as LineData
            }
            const value = this.rowValue(e, data)
            // The swatch and the name identify the row, so they are always
            // drawn; the value is appended when this point has one. A series
            // without a value used to `return`, which left that row - and every
            // row after it - with nothing but the eye icon.
            const label = `<span style="color: ${e.solid};">▨</span>    ${e.name}`
            e.div.innerHTML = value === null ? label : `${label} : ${value}`
        })
    }

    /** The text one legend row shows for a data point (`null` = no value).
     *
     * Custom series built from range shapes carry `low`/`high` instead of
     * `value` (`priceValueBuilder` derives the price scale from them), so they
     * are shown as a range. */
    rowValue(row: LineElement, data: any): string | null {
        if (!data) return null
        const format = row.series.options().priceFormat as PriceFormatBuiltIn
        const precision = format?.precision ?? this.handler.precision
        if (typeof data.value === 'number' && isFinite(data.value)) {
            return row.series.seriesType() == 'Histogram'
                ? this.shorthandFormat(data.value)
                : this.legendItemFormat(data.value, precision)
        }
        const { low, high } = data
        if (typeof low === 'number' && typeof high === 'number'
            && isFinite(low) && isFinite(high)) {
            return `${this.legendItemFormat(low, precision)} – `
                + this.legendItemFormat(high, precision)
        }
        if (typeof data.close === 'number' && isFinite(data.close)) {
            return this.legendItemFormat(data.close, precision)
        }
        return null
    }
}

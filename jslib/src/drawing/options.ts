import { LineStyle } from "lightweight-charts";


export interface DrawingOptions {
    lineColor: string;
    lineStyle: LineStyle
    width: number;
    /** Optional label rendered on the price/time axis. */
    text?: string;
}

export const defaultOptions: DrawingOptions = {
    lineColor: '#1E80F0',
    lineStyle: LineStyle.Solid,
    width: 4,
};

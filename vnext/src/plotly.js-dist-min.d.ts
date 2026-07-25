declare module "plotly.js-dist-min" {
  export function newPlot(
    root: HTMLElement,
    data: readonly unknown[],
    layout: unknown,
    config?: unknown
  ): Promise<unknown>;
}

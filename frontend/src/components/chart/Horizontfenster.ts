// Ein Primitiv der Bibliothek (v5-Plugin-API): zeichnet die Fenster
// Einstieg .. Einstieg + H als Flaechen ueber die ganze Hoehe der Pane.
// Rechtecke gibt es in der Bibliothek nicht von Haus aus; die Flaeche folgt
// Zoom und Verschieben, weil sie bei jedem Zeichnen aus der Zeitachse
// gerechnet wird.

import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

import type { Zeitfenster } from '@/lib/chartdaten';

export interface Fensterstil {
  farbe: string;
  /** Der gewaehlte Horizont wird kraeftiger gezeichnet. */
  betont: number | null;
}

class Fensterrenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly chart: IChartApi | null,
    private readonly fenster: readonly Zeitfenster[],
    private readonly stil: Fensterstil,
  ) {}

  draw(target: Parameters<IPrimitivePaneRenderer['draw']>[0]): void {
    if (this.chart === null) return;
    const zeitachse = this.chart.timeScale();
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const f of this.fenster) {
        const x1 = zeitachse.timeToCoordinate(f.von as Time);
        const x2 = zeitachse.timeToCoordinate(f.bis as Time);
        if (x1 === null || x2 === null) continue;
        context.globalAlpha = this.stil.betont === f.horizont ? 0.28 : 0.1;
        context.fillStyle = this.stil.farbe;
        context.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1), mediaSize.height);
      }
      context.globalAlpha = 1;
    });
  }
}

class Fensteransicht implements IPrimitivePaneView {
  constructor(private readonly renderer_: Fensterrenderer) {}

  zOrder(): 'bottom' {
    return 'bottom';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class Horizontfenster implements ISeriesPrimitive {
  private chart: IChartApi | null = null;
  private neuZeichnen: (() => void) | null = null;
  private fenster: readonly Zeitfenster[] = [];
  private stil: Fensterstil = { farbe: 'rgba(111, 156, 232, 1)', betont: null };

  attached(param: SeriesAttachedParameter): void {
    this.chart = param.chart;
    this.neuZeichnen = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.neuZeichnen = null;
  }

  setze(fenster: readonly Zeitfenster[], stil: Fensterstil): void {
    this.fenster = fenster;
    this.stil = stil;
    this.neuZeichnen?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [new Fensteransicht(new Fensterrenderer(this.chart, this.fenster, this.stil))];
  }
}

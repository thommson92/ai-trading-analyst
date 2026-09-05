"""Der historische Put-Verkauf an einem Entscheidungspunkt (ADR 0058, Stufe 1).

Reine Rechnung auf einer Kerzenfolge -- kein Netz, keine Datenbank, keine
Uhr. Was hier entsteht, ist **kein gemessener Trade**: Die Praemie ist
modelliert (``domain.options.pricing``), der Verfallskalender konstruiert und
das Strike-Raster angenommen (``domain.options.historical``). Jede Ausgabe
traegt deshalb ihre Annahmen mit.

**Was der Kurspfad beitraegt, ist dagegen gemessen.** Ob die Aktie fiel und
wie weit, steht in den Kerzen. Der Unterschied zwischen einer modellierten
Praemie und einem gemessenen Pfad ist der Grund, warum die Ergebnisse beide
Groessen getrennt ausweisen: Was die Option einbrachte, ist eine Annahme;
was der Kurs tat, ist ein Befund.

Zwei Varianten, wie ADR 0058 Festlegung 7 sie beschliesst -- **halten bis
Verfall** als Grundlinie und **gemanagt** mit Gewinnmitnahme und Rueckkauf.
Einen chartbasierten Ausstieg gibt es nicht; deshalb braucht dieses Modul
weder Indikatoren noch Zonen, sondern allein den Kurspfad und das
Preismodell.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.options import (
    KONTRAKTGROESSE,
    TAGE_JE_JAHR,
    daily_closes,
    price_put,
    realized_volatility,
    select_historical_expiration,
    select_historical_strike,
)
from ai_trading_analyst.domain.screening import CandleSeries

OPTIONS_BACKTEST_VERSION = "optionsbacktest-v2"
"""Version des Simulationsverfahrens, an jedem Ergebnis zu speichern.

Sie deckt Verfallskalender, Strike-Raster, Volatilitaetsannahme,
Ausfuehrungsabschlag und die Managementregeln ab -- alles, was aus demselben
Kurspfad eine andere Zahl macht.

``v2`` stellt die gemanagte Variante am Verfallstag glatt, statt sie auf die
Grundlinie zurueckfallen zu lassen (ADR 0058, Nachtrag zu Festlegung 7). Bei
den vorgegebenen Marken aendert das genau einen von 127 gemessenen Trades --
die Nummer steigt trotzdem, weil dieselben Eingangsdaten sonst je nach Fassung
zwei verschiedene Zahlen ergaeben.
"""


MAX_ABSTAND_ZUM_VERFALL_TAGE = 4
"""Wie weit die Abrechnungskerze hoechstens vor dem Verfall liegen darf.

Vier Tage decken den einzigen Fall, der regulaer vorkommt: Der dritte Freitag
ist ein Feiertag, gehandelt wird zuletzt am Donnerstag. Grosszuegig genug fuer
einen Feiertag am Rand eines Wochenendes und eng genug, dass ein echtes Loch
im Bestand auffaellt statt stillschweigend eine Abrechnung Wochen vor dem
Verfall zu erzeugen.
"""


class TradeOutcome(StrEnum):
    """Wie der Trade endete."""

    EXPIRED_WORTHLESS = "EXPIRED_WORTHLESS"
    """Bis zum Verfall ueber dem Strike geblieben: die volle Praemie."""
    ASSIGNED = "ASSIGNED"
    """Am Verfall unter dem Strike -- angedient. Ob das ein Verlust ist,
    entscheidet die Frage, ob die Aktie gewollt war; die Zahl hier ist der
    reine Optionsverlust."""
    TAKE_PROFIT = "TAKE_PROFIT"
    STOPPED_OUT = "STOPPED_OUT"
    CLOSED_AT_EXPIRATION = "CLOSED_AT_EXPIRATION"
    """Am Verfallstag im Geld glattgestellt statt angedient (ADR 0058,
    Nachtrag zu Festlegung 7). Nur die gemanagte Variante kennt diesen
    Ausgang -- die Grundlinie nimmt die Andienung hin, und genau darin
    besteht der Unterschied."""


@dataclass(frozen=True, slots=True)
class OptionsBacktestParameters:
    """Die Annahmen des historischen Laufs (ADR 0058).

    Alle Festlegungen, die aus demselben Kurspfad eine andere Zahl machen,
    stehen hier -- und werden mit ``OPTIONS_BACKTEST_VERSION`` am Ergebnis
    gespeichert.
    """

    min_days_to_expiration: int = 21
    max_days_to_expiration: int = 60
    target_days_to_expiration: int = 35
    """Wie live (ADR 0048), damit der Rueckblick dieselbe Laufzeit misst, die
    gehandelt wird."""
    target_delta: float = 0.25
    """Die Mitte des produktiven Delta-Bandes 0,10 bis 0,40."""
    volatility_window: int = 30
    """Handelstage fuer die realisierte Volatilitaet, alle **vor** der
    Entscheidungskerze (Look-ahead-Verbot, Doc 10 Paragraph 6.6)."""
    volatility_uplift: float = 1.15
    """Aufschlag von der realisierten auf die implizite Volatilitaet
    (Festlegung 2). **Gesetzt, nicht gemessen** -- solange
    ``cli options-calibrate`` keine belastbare Zahl liefert. Das Ergebnis
    gehoert deshalb als Band ueber mehrere Aufschlaege gelesen, nie als eine
    Zahl."""
    risk_free_rate: float = 0.04
    execution_haircut: float = 0.02
    """Abschlag je Seite und je Transaktion (Festlegung 8). Er macht
    sichtbar, dass jede Managementregel eine zusaetzliche Transaktion
    kostet -- und spaeter, dass ein Spread doppelt so viele Spannen
    ueberquert."""
    take_profit_fraction: float = 0.33
    """Rueckkauf, sobald ein Drittel der Praemie verdient ist."""
    stop_multiple: float = 3.0
    """Rueckkauf, sobald die Option das Dreifache der vereinnahmten Praemie
    kostet -- ein Verlust vom zweifachen der Praemie."""


@dataclass(frozen=True, slots=True)
class OptionTrade:
    """Ein simulierter Put-Verkauf, in beiden Varianten ausgewertet.

    Alle Geldbetraege je Kontrakt, also fuer 100 Aktien.
    """

    entry_index: int
    entry_date: date
    expiration: date
    days_to_expiration: int
    strike: float
    underlying_at_entry: float
    volatility: float
    """Die **unterstellte** implizite Volatilitaet: realisierte mal
    Aufschlag."""
    premium: float
    """Nach Ausfuehrungsabschlag vereinnahmt -- was tatsaechlich ankaeme."""
    delta: float
    capital_at_risk: float

    held_outcome: TradeOutcome
    held_profit: float
    """Grundlinie: bis zum Verfall gehalten."""

    managed_outcome: TradeOutcome
    managed_profit: float
    managed_exit_index: int
    """Gemanagt: Gewinnmitnahme, Rueckkauf -- oder Glattstellung am
    Verfallstag. Ein Ausgang auf der Grundlinie ist hier nicht mehr
    moeglich."""

    underlying_at_expiration: float


def simulate_put_sale(
    series: CandleSeries,
    entry_index: int,
    params: OptionsBacktestParameters,
    *,
    exchange_timezone: ZoneInfo,
) -> OptionTrade | None:
    """Simuliert den Put-Verkauf an ``entry_index``.

    ``None``, wenn kein Trade entstehen kann -- und die Gruende sind alle
    sachlich, keine Fehler:

    * zu wenig Kurshistorie fuer die Volatilitaet,
    * kein Monatsverfall im Laufzeitfenster,
    * kein Strike auf dem Raster mit brauchbarem Delta,
    * der Verfall liegt hinter dem Ende der gespeicherten Kerzen -- der Trade
      waere unvollstaendig, und ein bei Reihenende abgeschnittener Trade
      saehe wie ein Ergebnis aus.

    Ein ``None`` ist damit eine Aussage ueber die Grundlage und wird vom
    Aufrufer gezaehlt, nicht verschluckt.
    """
    einstiegskerze = series.candle(entry_index)
    stichtag = einstiegskerze.timestamp.astimezone(exchange_timezone).date()

    vola = _unterstellte_volatilitaet(series, entry_index, params, exchange_timezone)
    if vola is None:
        return None

    verfall = select_historical_expiration(
        as_of=stichtag,
        min_days=params.min_days_to_expiration,
        max_days=params.max_days_to_expiration,
        target_days=params.target_days_to_expiration,
    )
    if verfall is None:
        return None

    restlaufzeit = (verfall - stichtag).days
    jahre = restlaufzeit / TAGE_JE_JAHR
    kurs = einstiegskerze.close
    strike = select_historical_strike(
        spot=kurs,
        years_to_expiration=jahre,
        volatility=vola,
        risk_free_rate=params.risk_free_rate,
        target_delta=params.target_delta,
    )
    if strike is None:
        return None

    einstieg = price_put(
        spot=kurs,
        strike=strike,
        years_to_expiration=jahre,
        volatility=vola,
        risk_free_rate=params.risk_free_rate,
    )
    if einstieg.premium <= 0.0:
        return None

    # Verkauft wird unter der Mitte: Wer stellt, bekommt weniger als sie.
    vereinnahmt = einstieg.premium * (1.0 - params.execution_haircut)

    verfallsindex = _letzte_kerze_bis(series, verfall, exchange_timezone)
    if verfallsindex is None or verfallsindex <= entry_index:
        return None

    kurs_am_verfall = series.candle(verfallsindex).close
    gehalten_ergebnis, gehalten_gewinn = _bei_verfall(
        vereinnahmt, strike, kurs_am_verfall
    )
    gemanagt = _gemanagt(
        series,
        entry_index=entry_index,
        expiration_index=verfallsindex,
        expiration=verfall,
        strike=strike,
        vereinnahmt=vereinnahmt,
        modellpraemie=einstieg.premium,
        volatility=vola,
        params=params,
        exchange_timezone=exchange_timezone,
    )

    return OptionTrade(
        entry_index=entry_index,
        entry_date=stichtag,
        expiration=verfall,
        days_to_expiration=restlaufzeit,
        strike=strike,
        underlying_at_entry=kurs,
        volatility=vola,
        premium=vereinnahmt,
        delta=einstieg.delta,
        capital_at_risk=strike * KONTRAKTGROESSE,
        held_outcome=gehalten_ergebnis,
        held_profit=gehalten_gewinn,
        managed_outcome=gemanagt[0],
        managed_profit=gemanagt[1],
        managed_exit_index=gemanagt[2],
        underlying_at_expiration=kurs_am_verfall,
    )


def _unterstellte_volatilitaet(
    series: CandleSeries,
    entry_index: int,
    params: OptionsBacktestParameters,
    exchange_timezone: ZoneInfo,
) -> float | None:
    """Realisierte Volatilitaet mal Aufschlag, aus Kerzen **vor** ``entry_index``.

    Der Tag der Entscheidungskerze zaehlt nicht mit: Ihre zweite Tageskerze
    liegt zeitlich nach der Entscheidung, und die erste ist die Entscheidung
    selbst. Beide gehoerten zu einer Volatilitaet, die zum Zeitpunkt des
    Einstiegs noch niemand kannte.
    """
    stichtag = series.candle(entry_index).timestamp.astimezone(exchange_timezone).date()
    schluesse = daily_closes(
        [
            (series.candle(i).timestamp, series.candle(i).close)
            for i in range(entry_index)
        ],
        timezone=exchange_timezone,
    )
    davor = [close for tag, close in schluesse if tag < stichtag]
    realisiert = realized_volatility(davor[-params.volatility_window :])
    if realisiert is None or realisiert <= 0.0:
        return None
    return realisiert * params.volatility_uplift


def _letzte_kerze_bis(
    series: CandleSeries, verfall: date, exchange_timezone: ZoneInfo
) -> int | None:
    """Index der letzten Kerze **am oder kurz vor** dem Verfallstag.

    Nicht genau am: Faellt der dritte Freitag auf einen Feiertag -- Karfreitag
    trifft ihn regelmaessig --, gibt es an ihm keine Kerze. Der Handel des
    Vortags ist dann der letzte, und genau er bestimmt die Andienung.

    ``None`` in zwei Faellen, und beide sind Aussagen ueber die Grundlage:

    * Die Reihe **endet** vor dem Verfall. Der Trade ist nicht ausgelaufen,
      und ein abgeschnittener saehe wie ein Ergebnis aus.
    * Die letzte Kerze liegt **zu weit** vor dem Verfall. Ein Loch mitten in
      der Reihe -- ein ausgesetzter Titel, eine Luecke im Bestand -- fuehrte
      sonst dazu, dass der Trade auf einem Kurs abgerechnet wird, der mit dem
      Verfall nichts zu tun hat, und trotzdem wie ein vollstaendiges Ergebnis
      aussieht.
    """
    letzter: int | None = None
    for i in range(len(series)):
        tag = series.candle(i).timestamp.astimezone(exchange_timezone).date()
        if tag > verfall:
            break
        letzter = i
    if letzter is None:
        return None
    letzter_tag = series.candle(letzter).timestamp.astimezone(exchange_timezone).date()
    if (verfall - letzter_tag).days > MAX_ABSTAND_ZUM_VERFALL_TAGE:
        return None
    return letzter


def _bei_verfall(
    vereinnahmt: float, strike: float, kurs: float
) -> tuple[TradeOutcome, float]:
    """Auszahlung am Verfall -- exakt, ohne Modell.

    Hier rechnet nichts mehr: Der innere Wert eines Puts am Verfallstag steht
    fest, sobald der Schlusskurs feststeht. Auch faellt keine
    Ausfuehrungsspanne an -- ein wertlos verfallener Kontrakt wird nicht
    zurueckgekauft, und eine Andienung ist keine Optionstransaktion.
    """
    innerer_wert = max(strike - kurs, 0.0)
    gewinn = (vereinnahmt - innerer_wert) * KONTRAKTGROESSE
    if innerer_wert > 0.0:
        return TradeOutcome.ASSIGNED, gewinn
    return TradeOutcome.EXPIRED_WORTHLESS, gewinn


def _gemanagt(
    series: CandleSeries,
    *,
    entry_index: int,
    expiration_index: int,
    expiration: date,
    strike: float,
    vereinnahmt: float,
    modellpraemie: float,
    volatility: float,
    params: OptionsBacktestParameters,
    exchange_timezone: ZoneInfo,
) -> tuple[TradeOutcome, float, int]:
    """Der erste Ausstieg nach Gewinnmitnahme, Rueckkaufregel -- oder am Ende
    die Glattstellung.

    **Sie schliesst nicht in die Grundlinie zurueck.** Bis zum Nachtrag zu
    ADR 0058, Festlegung 7 tat sie genau das -- und trug dann Zahl fuer Zahl
    das Ergebnis der Variante, gegen die sie sich beweisen soll. Gemessen ist
    der Fall selten: ueber die vier Golden-Master-Faelle erreicht genau einer
    von 127 Trades keine der beiden Marken, weil ein Put schon durchs Altern
    ein Drittel seines Werts verliert. Beseitigt wird deshalb kein haeufiger
    Fall, sondern ein **stiller Rueckfall** -- ein Ausgang, den diese Variante
    nicht selbst entscheidet. Mit weiteren Marken waechst sein Anteil.

    Beide Marken stehen am **Modellpreis** der Option, nicht am Kurs der
    Aktie. Das ist der Punkt der gemanagten Variante: Sie reagiert auf den
    Wert des Kontrakts, und dessen Wert haengt neben dem Kurs auch am
    Zeitwert. Ein Put, der bei unveraendertem Kurs zwei Wochen altert, faellt
    -- und genau das loest die Gewinnmitnahme aus.

    **Die Volatilitaet bleibt konstant.** Das ist die zweite der beiden
    Verzerrungen aus ADR 0058: In Wirklichkeit steigt sie, wenn der Kurs
    faellt, der Rueckkauf waere also teurer und traefe frueher ein. Die
    Vereinfachung laesst den Stop damit **sauberer** aussehen, als er ist;
    die Richtung ist bekannt und benannt.
    """
    gewinnmarke = modellpraemie * (1.0 - params.take_profit_fraction)
    stoppmarke = modellpraemie * params.stop_multiple

    for i in range(entry_index + 1, expiration_index):
        kerze = series.candle(i)
        tag = kerze.timestamp.astimezone(exchange_timezone).date()
        rest = (expiration - tag).days
        if rest <= 0:
            break
        preis = price_put(
            spot=kerze.close,
            strike=strike,
            years_to_expiration=rest / TAGE_JE_JAHR,
            volatility=volatility,
            risk_free_rate=params.risk_free_rate,
        ).premium
        if preis <= gewinnmarke:
            return TradeOutcome.TAKE_PROFIT, _rueckkauf(preis, vereinnahmt, params), i
        if preis >= stoppmarke:
            return TradeOutcome.STOPPED_OUT, _rueckkauf(preis, vereinnahmt, params), i

    # **Die Glattstellung am Verfallstag** (ADR 0058, Nachtrag zu Festlegung
    # 7). Der Preis ist der **innere Wert**, nicht der Modellpreis: Am
    # Verfallstag steht er fest, sobald der Schlusskurs feststeht, und das
    # Modell waere hier eine Annahme, wo es keine braucht.
    #
    # Zehn Minuten vor Handelsschluss statt am Schluss selbst waere eine
    # Genauigkeit, die die Daten nicht haben -- die Kerzen laufen ueber 195
    # Minuten, zwei je Handelstag. Der Tagesschluss ist das Feinste, was
    # existiert.
    innerer_wert = max(strike - series.candle(expiration_index).close, 0.0)
    if innerer_wert <= 0.0:
        # Nichts zurueckzukaufen, also auch keine Transaktion und kein
        # Abschlag. Hier faellt die gemanagte Variante mit der Grundlinie
        # zusammen, und das ist kein Mangel, sondern die Wirklichkeit.
        return (
            TradeOutcome.EXPIRED_WORTHLESS,
            vereinnahmt * KONTRAKTGROESSE,
            expiration_index,
        )
    return (
        TradeOutcome.CLOSED_AT_EXPIRATION,
        _rueckkauf(innerer_wert, vereinnahmt, params),
        expiration_index,
    )


def _rueckkauf(
    preis: float, vereinnahmt: float, params: OptionsBacktestParameters
) -> float:
    """Ergebnis nach einem Rueckkauf, je Kontrakt.

    Ueber der Mitte gekauft: Wer nimmt, zahlt mehr als sie. Der Abschlag
    wirkt hier zum zweiten Mal -- einmal beim Verkauf, einmal beim
    Rueckkauf -- und genau das soll er zeigen.
    """
    gezahlt = preis * (1.0 + params.execution_haircut)
    return (vereinnahmt - gezahlt) * KONTRAKTGROESSE

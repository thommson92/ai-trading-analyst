"""Deterministische Ableitungen des Research Agent (ADR 0029).

Quellenrang, Abdeckung und Zitatdeckelung stehen **in der Domain**, nicht im
Anbieter-Adapter -- dasselbe Muster wie ``_classify_confidence``
(``domain/backtesting/metrics.py``) oder ``evaluate_earnings_filter``
(``domain/earnings/filter.py``). Der Grund ist nicht Symmetrie: Waere die
Regel im Anthropic-Adapter, haetten zwei Anbieter zwei Antworten auf dieselbe
Frage, und in derselben Spalte ``research_coverage`` stuenden Werte, die nach
verschiedenen Verfahren entstanden sind.

Nichts hier kennt einen Anbieter. Alles hier ist reine Funktion von URL und
gezaehlten Tatsachen -- nie von Modelltext (CLAUDE.md: Klassifikationen nicht
aus LLM-Freitext uebernehmen).
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from .values import (
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    SourceRank,
    rangindex,
)

RESEARCH_ANALYSIS_VERSION = "research-analysis-v2"
"""Version des Verfahrens in dieser Datei -- Rangzuordnung, Abdeckungsschwellen
und Deckelung.

Getrennt von der Prompt-Version: Beide aendern sich unabhaengig voneinander.
Aendert sich eine Domainliste oder eine Schwelle, steigt diese Nummer, damit
ein alter gespeicherter ``research_coverage``-Wert nicht stillschweigend unter
der neuen Regel gelesen wird (Muster ``TECHNICAL_ANALYSIS_VERSION``).
"""

_REGULATORY_DOMAINS = (
    "sec.gov",
    "federalreserve.gov",
    "ftc.gov",
    "justice.gov",
    "europa.eu",
)
"""Amtliche Quellen -- hoechster Rang."""

_COMPANY_RELEASE_DOMAINS = (
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
)
"""Original-Pressemitteilungsdienste: das Unternehmen meldet hier selbst.

``nasdaq.com`` stand hier und ist wieder heraus. Es ist ueberwiegend ein
Portal, das Fremdinhalte weiterveroeffentlicht (Zacks, MT Newswires,
Meinungsbeitraege) -- eine Seite dort ist keine Unternehmensmeldung, und der
Pfad ist an dieser Stelle bewusst kein Kriterium. Ohne Eintrag faellt
nasdaq.com auf ``UNRANKED``, den unschaedlichen Ausgang."""

_COMPANY_HOST_LABELS = frozenset({"investor", "investors", "ir"})
"""Erste Host-Label eines Investor-Relations-Auftritts.

Diese lassen sich nicht ueber die Domain erfassen: ``investor.apple.com``
gehoert dazu, ``apple.com`` nicht."""


def _ist_investor_relations(host: str) -> bool:
    """Ein IR-Auftritt ist eine **Unterdomain** des Unternehmens.

    Beide Bedingungen sind noetig, und die zweite ist die interessante:

    * Ein Zeichenpraefix (``host.startswith("investors.")``) verschluckte
      ganze Domains, die zufaellig so beginnen.
    * Der blosse Label-Vergleich genuegt trotzdem nicht, denn
      ``investors.com`` -- Investor's Business Daily, eine Fachzeitung --
      traegt "investors" als erstes Label und waere damit ein
      Unternehmensauftritt. Es ist aber eine eigenstaendige Domain, keine
      Unterdomain. Deshalb zusaetzlich mindestens drei Labels.

    Ohne die zweite Bedingung bekaeme derselbe Verlag mit und ohne ``www.``
    verschiedene Raenge, und COMPANY zaehlt zu ``RAENGE_MIT_SUBSTANZ``: ein
    Meinungsbeitrag haette einen Bericht auf ``BROAD`` gehoben.
    """
    labels = host.split(".")
    return len(labels) >= 3 and labels[0] in _COMPANY_HOST_LABELS

_FINANCIAL_MEDIA_DOMAINS = (
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
    "investors.com",
    "morningstar.com",
)

_GENERAL_MEDIA_DOMAINS = (
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "cnn.com",
    "nytimes.com",
    "washingtonpost.com",
)

_AGGREGATOR_DOMAINS = (
    "yahoo.com",
    "seekingalpha.com",
    "fool.com",
    "benzinga.com",
    "investing.com",
    "stocktwits.com",
    "nasdaq.com",
)
"""Portale und Meinungsplattformen. Verwertbar, aber selten die
Originalquelle.

Kein Eintrag darf Unterdomain eines anderen sein: ``_domain_matches``
vergleicht ohnehin per Suffix, ein ``finance.yahoo.com`` neben ``yahoo.com``
waere wirkungslos und legte die falsche Lesart nahe, Unterdomains muessten
aufgezaehlt werden."""

BREITE_MINDESTQUELLEN = 3
"""Ab so vielen verschiedenen Quellen kommt ``BROAD`` ueberhaupt in Frage."""

BEGRENZTE_MINDESTQUELLEN = 2
"""Darunter bleibt es bei ``THIN`` -- eine einzige Quelle ist keine Recherche."""

RAENGE_MIT_SUBSTANZ = (SourceRank.REGULATORY, SourceRank.COMPANY)
"""Fuer ``BROAD`` muss mindestens ein Beleg von der Quelle selbst stammen,
nicht nur aus Berichterstattung darueber."""


def host_of(url: str) -> str:
    """Der reine Hostname, ohne Port und ohne Zugangsdaten.

    ``urlparse().netloc`` liefert beides mit -- ``sec.gov:443`` haette gegen
    keine Domainliste gepasst und waere als ``UNRANKED`` durchgefallen.
    """
    return (urlparse(url).hostname or "").lower()


def _domain_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


_UNTERNEHMENSPFADE = (
    "/newsroom",
    "/press-release",
    "/press-releases",
    "/investor-relations",
)
"""Pfade, unter denen ein Unternehmen auf der eigenen Seite selbst meldet.

Der Anlass ist gemessen, nicht ausgedacht: Ein realer Lauf zu AAPL
(2026-08-24) zitierte den CEO-Wechsel aus
``www.apple.com/newsroom/...`` -- die verlaesslichste denkbare Quelle dafuer
-- und die Einstufung meldete ``UNRANKED``. Die Hauptdomain eines
Unternehmens laesst sich nicht auflisten und nicht am Host erkennen; ihr
Newsroom-Pfad dagegen schon.

Bewusst kurz gehalten und **erst nach den Medienlisten** geprueft: Ein
Nachrichtenanbieter mit einem ``/press-release``-Bereich bleibt
Nachrichtenanbieter. Der Pfad hebt nur, was sonst durchfiele."""


def _ist_unternehmensmeldung(url: str) -> bool:
    pfad = urlparse(url).path.lower()
    return pfad.startswith(_UNTERNEHMENSPFADE)


def classify_source_rank(url: str) -> SourceRank:
    """Quellenrang deterministisch aus der URL.

    Die Reihenfolge ist die Rangfolge selbst: Der erste Treffer gewinnt. Nie
    vom Sprachmodell erfragt -- ein Text, der behauptet, eine amtliche Quelle
    zu sein, veraendert hier nichts.

    Eine Ausnahme von der reinen Rangreihenfolge: Der Newsroom-Pfad wird
    **nach** den Medienlisten geprueft. Sonst haette ein
    ``/press-releases``-Bereich einer Nachrichtenseite sie zur
    Unternehmensmeldung gemacht.
    """
    host = host_of(url)
    if _domain_matches(host, _REGULATORY_DOMAINS):
        return SourceRank.REGULATORY
    if _ist_investor_relations(host) or _domain_matches(host, _COMPANY_RELEASE_DOMAINS):
        return SourceRank.COMPANY
    if _domain_matches(host, _FINANCIAL_MEDIA_DOMAINS):
        return SourceRank.FINANCIAL_MEDIA
    if _domain_matches(host, _GENERAL_MEDIA_DOMAINS):
        return SourceRank.GENERAL_MEDIA
    if _domain_matches(host, _AGGREGATOR_DOMAINS):
        return SourceRank.AGGREGATOR
    if _ist_unternehmensmeldung(url):
        return SourceRank.COMPANY
    return SourceRank.UNRANKED


def _ordnung(eintrag: tuple[int, Citation]) -> tuple[int, int]:
    """Rang zuerst, bei gleichem Rang die Reihenfolge der ersten Nennung.

    Der zweite Teil ist die Zusicherung aus ADR 0023, Entscheidung 6 -- hier
    ausdruecklich als Sortierschluessel statt als Nebenwirkung einer stabilen
    Sortierung, weil die Deckelung die Reihenfolge zwischendurch aufbricht.
    """
    index, citation = eintrag
    return (rangindex(citation.source_rank), index)


def rank_and_cap(citations: Iterable[Citation], obergrenze: int) -> tuple[list[Citation], int]:
    """Deckelt die Belege, ohne ganze Quellen zu opfern (ADR 0029).

    **Reihum je Quelle, nicht der Reihe nach.** Eine reine Rangsortierung mit
    anschliessendem Abschneiden haette den Deckel auf *Zitate* angewendet und
    damit Quellen verloren: Zwanzig Fundstellen aus einem einzigen Filing
    haetten alle fuenfzehn Plaetze belegt und jede unabhaengige Bestaetigung
    verdraengt. Der Bericht sagt dann etwas ueber eine Nachricht, deren einzige
    unabhaengige Quelle nicht mehr gespeichert ist -- gegen die Quellenbindung
    aus CLAUDE.md.

    Deshalb bekommt zuerst jede Quelle einen Beleg, in Rangfolge; erst dann
    einen zweiten, und so fort. Quellen gehen damit nur verloren, wenn es mehr
    Quellen als Plaetze gibt.

    Gibt zusaetzlich zurueck, wie viele Zitate weggefallen sind. Eine
    Auslassung, die niemand zaehlt, ist eine stille Auslassung.
    """
    nummeriert = list(enumerate(citations))
    if obergrenze >= len(nummeriert):
        return [citation for _, citation in sorted(nummeriert, key=_ordnung)], 0

    je_quelle: dict[str, list[tuple[int, Citation]]] = {}
    for eintrag in nummeriert:
        je_quelle.setdefault(eintrag[1].url, []).append(eintrag)
    quellen = sorted(je_quelle.values(), key=lambda gruppe: _ordnung(gruppe[0]))

    behalten: list[tuple[int, Citation]] = []
    runde = 0
    while len(behalten) < obergrenze and any(runde < len(gruppe) for gruppe in quellen):
        for gruppe in quellen:
            if len(behalten) == obergrenze:
                break
            if runde < len(gruppe):
                behalten.append(gruppe[runde])
        runde += 1

    behalten.sort(key=_ordnung)
    return [citation for _, citation in behalten], len(nummeriert) - len(behalten)


def derive_coverage(evidence: ResearchEvidence, citations: Iterable[Citation]) -> ResearchCoverage:
    """Abdeckung aus dem, was messbar geschehen ist.

    Ausdruecklich nicht aus einer Selbstauskunft des Modells: Ein Modell, das
    eine duenne Quellenlage nicht erkennt, meldet auch eine gute Abdeckung.
    Der Lauf aus ADR 0023 -- eine Suche, null Abrufe, acht Ablehnungen -- ist
    hier ``THIN``: Er kam ueber eine einzige Quelle nicht hinaus.

    Es gehen **zwei** der vier Zahlen aus ``ResearchEvidence`` ein, die
    anderen beiden bewusst nicht:

    - ``rejected_tool_calls`` sagt etwas ueber verbrannte Kosten, nicht ueber
      die Belegdichte. Gespeichert als Diagnose, nicht als Einstufung.
    - ``successful_fetches`` ging bis ``research-analysis-v1`` in ``BROAD``
      ein und tut es seit ``v2`` nicht mehr (ADR 0029, zweiter Nachtrag). Der
      Grund ist gemessen, nicht theoretisch: ``fetch_allowed_domains`` deckt
      keine Domain ab, die in realen Suchtreffern auftaucht, sodass ein
      typischer Lauf **null** Abrufe hat -- ohne einen einzigen Fehlversuch.
      Die Bedingung machte ``BROAD`` damit unerreichbar, und eine Stufe, die
      nie vergeben wird, ist keine Stufe. Die Zahl wird weiter erhoben und
      gespeichert; sie ist damit rueckholbar, sobald die Allowlist die
      tatsaechlich gefundenen Primaerquellen erreicht.
    """
    if evidence.distinct_sources < BEGRENZTE_MINDESTQUELLEN:
        return ResearchCoverage.THIN
    hat_substanz = any(citation.source_rank in RAENGE_MIT_SUBSTANZ for citation in citations)
    if evidence.distinct_sources >= BREITE_MINDESTQUELLEN and hat_substanz:
        return ResearchCoverage.BROAD
    return ResearchCoverage.LIMITED

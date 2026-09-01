# ADR 0050: Das US-007-Kriterium „relevante Chartmuster" ist gestrichen

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

US-007 (Doc 04, „Technische Bewertung erhalten") verlangt unter seinen
Akzeptanzkriterien „relevante Chartmuster". Seit
[ADR 0026](0026-technical-agent-ki-einordnung.md) steht fest, warum das
System sie nicht liefert: Es gibt keine deterministische Mustererkennung,
und ein Sprachmodell, das aus einer Handvoll Kennzahlen eine Formation
benennt, erfände genau das, was die zentrale Regel des Projekts verbietet.
Der Kopfvermerk von Doc 04 führte den Punkt seither als „offen (E13)" —
das Audit vom 2026-08-23 stellte die Frage als Entscheidungsvorlage E13:
streichen oder als spätere Ausbaustufe vormerken.

## Entscheidung

**Das Kriterium wird gestrichen — mit Vermerk, nicht durch stille
Löschung.** Der Eintrag in Doc 04 bleibt sichtbar und verweist auf dieses
ADR. Eine Wiedereinführung ist nur als spätere Ausbaustufe denkbar, deren
erster Schritt eine **deterministische** Mustererkennung wäre; erst darauf
dürfte eine KI-Einordnung aufsetzen (Muster ADR 0026).

## Begründung

Ein dauerhaft „teilweise erfüllbares" Akzeptanzkriterium ist keine
Anforderung, sondern eine offene Flanke: Jede künftige Traceability-Prüfung
stolperte erneut darüber, und der Druck, es doch „irgendwie" zu erfüllen,
zeigte in die falsche Richtung — auf erfundene Formationen. Die übrigen
Kriterien von US-007 (Trend, Momentum, RSI-Situation, Unterstützungen,
Widerstände) sind vollständig erfüllt; die Story verliert durch die
Streichung keinen gelieferten Wert.

## Konsequenzen

- Doc 04: Der Kopfvermerk führt US-007 nicht länger als offen; am
  Kriterium selbst steht der Streichungsvermerk mit Verweis hierher.
- US-007 ist damit vollständig beschlossen; E13 aus dem Audit vom
  2026-08-23 ist entschieden.
- Keine Codeänderung — es gab nie Code zu diesem Kriterium.
- Wer Chartmuster später doch will, beginnt mit einem ADR zur
  deterministischen Mustererkennung, nicht mit einem Prompt.

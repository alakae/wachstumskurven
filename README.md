# Wachstumskurven

*Plots a child's measurements from a CSV file onto the official Swiss growth charts by pädiatrie schweiz. Documentation in German.*

Trägt Messwerte aus einer CSV in die offiziellen Wachstumskurven von pädiatrie schweiz ein.

## Disclaimer

Ein Just-for-fun-Projekt von einem Vater für Eltern, die das Wachstum ihres Kindes mitverfolgen möchten. Es ist kein Medizinprodukt und ersetzt keine ärztliche Beurteilung. Die Diagramme können Fehler enthalten. Bei Fragen oder Sorgen zur Entwicklung eures Kindes: Kinderärztin oder Kinderarzt fragen.

**Dieses Projekt ist ein unabhängiges, privates Projekt und steht in keinerlei Verbindung zu pädiatrie schweiz. Es wird von pädiatrie schweiz weder betrieben, beauftragt, geprüft, unterstützt noch empfohlen.** Die Nennung von «pädiatrie schweiz» dient ausschliesslich der Angabe der Quelle der Vorlage. Sämtliche Rechte an den Wachstumskurven und an der Vorlage liegen bei den jeweiligen Rechteinhabern.

## Überblick

- Wählt automatisch die passenden Diagramme anhand von Alter und vorhandenen Messwerten (z. B. 0–2 statt 1–18 Jahre).
- Länge, Gewicht, Kopfumfang, Gewicht für Länge und BMI.
- Optional: Wachstumsgeschwindigkeit, Kurven bei Geburt und Zielgrösse aus den Elterngrössen.
- Ausgabe ist ein PDF mit den gewählten Seiten der Vorlage, inklusive Name, Geburtsdatum und Elternangaben.

## Vorlage

Die Vorlage wird nicht mitgeliefert. Lade `PCH_Wachstumskurven_260701_DE.pdf` selbst bei [pädiatrie schweiz](https://www.paediatrieschweiz.ch/unterlagen/wachstumskurven/) herunter.

Die Positionen der Kurven sind für genau diese Version kalibriert. Weicht die Prüfsumme der Vorlage ab, gibt das Skript eine Warnung aus.

## Installation

Voraussetzung ist [uv](https://docs.astral.sh/uv/). Installation direkt aus GitHub:

```sh
uv tool install git+https://github.com/alakae/wachstumskurven
```

Auf den neuesten Stand bringen:

```sh
uv tool upgrade wachstumskurven
```

Tipp: Mit `--exclude-newer "7 days"` werden nur Abhängigkeiten verwendet, die seit mindestens sieben Tagen veröffentlicht sind. Das schützt vor frisch kompromittierten Paketversionen. uv merkt sich dabei ein festes Datum, nicht "7 days". Die Option deshalb auch bei jedem Update angeben, sonst bleiben die Abhängigkeiten auf dem Stand der Installation:

```sh
uv tool install --exclude-newer "7 days" git+https://github.com/alakae/wachstumskurven
uv tool upgrade --exclude-newer "7 days" wachstumskurven
```

## Verwendung

```sh
wachstumskurven messungen.csv \
  -p PCH_Wachstumskurven_260701_DE.pdf \
  -g m -b 2025-07-22 -n "Noah Beispiel"
```

Ergebnis: `messungen_kurven.pdf`

### Optionen

| Option | Bedeutung |
| --- | --- |
| `-p`, `--pdf` | Pfad zur Vorlage (erforderlich) |
| `-g`, `--geschlecht` | `m` oder `w` |
| `-b`, `--geburtsdatum` | `YYYY-MM-DD` oder `TT.MM.JJJJ` |
| `-n`, `--name` | Name auf den Seiten |
| `-o`, `--out` | Ausgabedatei |
| `--ssw` | Gestationsalter bei Geburt, z. B. `39+4`, für die Geburtskurven |
| `--mutter`, `--vater` | Körpergrösse der Eltern in cm, für die Zielgrösse |
| `--mutter-ku`, `--vater-ku` | Kopfumfang der Eltern in cm |
| `--kalibrierung` | Kalibrierungs-Check, siehe unten |

### Konfiguration

Feste Angaben können in `wachstumskurven.toml` im aktuellen Verzeichnis stehen. Danach genügt `wachstumskurven messungen.csv`. Optionen auf der Kommandozeile haben Vorrang.

```toml
pdf = "PCH_Wachstumskurven_260701_DE.pdf"
geschlecht = "m"
geburtsdatum = 2025-07-22
name = "Noah Beispiel"
mutter = 165
vater = 180
mutter-ku = 55
vater-ku = 58
```

Erlaubt sind `pdf`, `geschlecht`, `geburtsdatum`, `name`, `ssw`, `mutter`, `vater`, `mutter-ku` und `vater-ku`.

### CSV

```csv
datum;laenge;gewicht;kopfumfang
2025-07-22;50,5;3,45;35,0
2026-01-26;67,5;7,90;43,5
2026-10-02;78,0S;10,30;
```

- Trenner `;` oder `,`, Dezimalkomma erlaubt.
- Leere Zellen sind erlaubt, nur `datum` ist Pflicht. Die Reihenfolge der Zeilen ist egal. Zeilen mit gleichem Datum werden zusammengeführt, Länge und Gewicht dürfen also auf eigenen Zeilen stehen.
- Länge mit Suffix `L` (liegend) oder `S` (stehend). Ohne Suffix gilt liegend. Wo die Vorlage es verlangt, werden stehende Werte um 1 cm korrigiert.
- Für die Kurven bei Geburt braucht es eine Zeile mit dem Geburtsdatum und `--ssw`.

### Beispiel

In [`examples/`](examples/) liegen synthetische Messwerte eines Jungen (geboren 2025-08-12, SSW 39+4) bis zum Alter von 14 Monaten, samt passender `wachstumskurven.toml`. Beide Dateien und die Vorlage in ein Verzeichnis legen, dann dort:

```sh
wachstumskurven sample.csv
```

### Kalibrierungs-Check

```sh
wachstumskurven --kalibrierung -p PCH_Wachstumskurven_260701_DE.pdf
```

Schreibt `kalibrierung.pdf` mit allen Seiten und zeichnet das berechnete Gitter darüber. Ausser `-p` sind keine Optionen erlaubt, `wachstumskurven.toml` wird nicht gelesen. Liegen die roten und orangen Linien auf den gedruckten, stimmt die Kalibrierung.

## Entwicklung

Im geklonten Repository läuft das Tool mit `uv run`, mit genau den Versionen aus `uv.lock`:

```sh
uv run wachstumskurven messungen.csv
uv run ruff check
uv run ruff format --check
uv run mypy
```

## Quellen

Die Kurven stammen von pädiatrie schweiz. Die wissenschaftlichen Grundlagen sind in der Vorlage auf Seite 2 aufgeführt.

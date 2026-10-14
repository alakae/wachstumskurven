# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=5", "reportlab>=4"]
# ///
"""Messwerte aus einer CSV auf die Wachstumskurven von pädiatrie schweiz (Version 2026) plotten.

Die Vorlage wird nicht mitgeliefert und nicht heruntergeladen. Bitte selbst bei
pädiatrie schweiz beziehen (PCH_Wachstumskurven_260701_DE.pdf) und mit --pdf angeben.

CSV-Spalten: datum, laenge, gewicht, kopfumfang  (leere Zellen erlaubt; ',' oder ';' als Trenner)
Beispiel:    uv run wachstumskurven.py messungen.csv --pdf PCH_Wachstumskurven_260701_DE.pdf -g w -b 2024-03-15 --ssw 39+3 --mutter 165 --vater 180 \
             --mutter-ku 55 --vater-ku 58

Länge mit Suffix L (liegend) oder S (stehend), z.B. 76,5L oder 102S; ohne Suffix = liegend.
Auf den Kurven mit dem Hinweis "Bei stehender Messung: 1 cm hinzufügen"
(Länge 0–2 J., Gewicht für Länge 50–120 cm) werden stehende Werte um 1 cm korrigiert.
Geburtskurven: Zeile mit datum == Geburtsdatum + --ssw.

Kalibrierungs-Check:  uv run wachstumskurven.py --kalibrierung --pdf <vorlage.pdf> [-g m|w]
→ alle Seiten mit nachgezeichnetem Gitter (aus der Kalibrierung berechnet). Liegen die
  roten/orangen Linien und Beschriftungen exakt auf den gedruckten, stimmt die Kalibrierung.
Zielgrösse (Tanner): (Mutter + Vater) / 2 ± 6.5 cm, Zielbereich ± 8.5 cm.
"""

import argparse
import csv
import hashlib
import io
import sys
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import TypedDict

from pypdf import PageObject, PdfReader, PdfWriter
from reportlab.pdfgen import canvas

# SHA-256 der PDF-Version, für die die Kalibrierung unten gilt
PDF_SHA256 = "5d5d9095bfed168d657aefa101296043f413ef0dae84ebe868811609d22e434a"
GIRLS_OFFSET = 12  # Mädchen-Seiten liegen 12 Seiten hinter den Jungen-Seiten

# Messpunkt: "jahre" immer vorhanden, Messwerte nur wenn nicht leer
Point = dict[str, float]
Cal = dict[str, tuple[float, float]]  # Achse/Messgrösse -> (a, b)


class Chart(TypedDict):
    page: int
    x: str
    rng: tuple[float, float]


# Kalibrierung aus dem PDF (Gitterlinien): PDF-Koordinate = a * Wert + b
# x-Einheit: "m" = Monate, "j" = Jahre, "cm" = Länge, "ssw" = Gestationswochen
# fmt: off
CHARTS: dict[str, Chart] = {
    "lg_0_2":     {"page": 3,  "x": "m",   "rng": (0, 2)},
    "lg_0_5":     {"page": 4,  "x": "m",   "rng": (0, 5)},
    "lg_1_18":    {"page": 5,  "x": "j",   "rng": (1, 18)},
    "wfl_50_120": {"page": 6,  "x": "cm",  "rng": (50, 120)},
    "wfl_120":    {"page": 7,  "x": "cm",  "rng": (120, 200)},
    "bmi":        {"page": 8,  "x": "j",   "rng": (0, 18)},
    "ku_0_2":     {"page": 9,  "x": "m",   "rng": (0, 2)},
    "ku_0_5":     {"page": 10, "x": "m",   "rng": (0, 5)},
    "ku_1_18":    {"page": 11, "x": "j",   "rng": (1, 18)},
    "vel":        {"page": 12, "x": "j",   "rng": (2, 18)},
    "geb_lg":     {"page": 13, "x": "ssw", "rng": (20, 42)},
    "geb_ku":     {"page": 14, "x": "ssw", "rng": (20, 42)},
}
CAL_BOTH: dict[str, Cal] = {  # identisch für Jungen und Mädchen
    "vel":        {"x": (28.34637, 14.174),   "vel": (28.3465, 223.229)},
    "geb_lg":     {"x": (20.61705, -341.473), "laenge": (6.4772, 259.794),  "gewicht": (64.75914, 195.074)},
    "geb_ku":     {"x": (20.61255, -341.319), "kopfumfang": (18.89819, -107.49)},
}
CAL: dict[str, dict[str, Cal]] = {
    "m": {
        "lg_0_2":     {"x": (18.87717, 71.111),   "laenge": (6.73549, 8.756),   "gewicht": (16.81933, 160.887)},
        "lg_0_5":     {"x": (7.55853, 70.874),    "laenge": (4.20059, 127.599), "gewicht": (10.1058, 194.853)},
        "lg_1_18":    {"x": (26.68055, 44.182),   "laenge": (2.5197, 144.486),  "gewicht": (2.51762, 195.058)},
        "wfl_50_120": {"x": (6.47918, -253.091),  "gewicht": (15.11836, 194.877)},
        "wfl_120":    {"x": (5.66091, -608.012),  "gewicht": (3.48882, 194.881)},
        "bmi":        {"x": (25.07138, 72.806),   "bmi": (11.347, 80.248)},
        "ku_0_2":     {"x": (18.89761, 70.866),   "kopfumfang": (18.14177, -367.513)},
        "ku_0_5":     {"x": (7.5591, 70.865),     "kopfumfang": (16.79793, -325.854)},
        "ku_1_18":    {"x": (26.67863, 44.191),   "kopfumfang": (22.67647, -757.504)},
    },
    "w": {
        "lg_0_2":     {"x": (18.87717, 71.111),   "laenge": (6.73544, 8.051),   "gewicht": (16.81942, 161.594)},
        "lg_0_5":     {"x": (7.55853, 70.874),    "laenge": (4.20059, 127.599), "gewicht": (10.06817, 195.073)},
        "lg_1_18":    {"x": (26.68055, 44.182),   "laenge": (2.93909, 119.354), "gewicht": (3.02657, 195.066)},
        "wfl_50_120": {"x": (6.47918, -253.091),  "gewicht": (15.11836, 194.877)},
        "wfl_120":    {"x": (6.47852, -706.511),  "gewicht": (3.48882, 194.881)},
        "bmi":        {"x": (25.07138, 72.806),   "bmi": (11.3386, 80.788)},
        "ku_0_2":     {"x": (18.89761, 70.866),   "kopfumfang": (18.14177, -349.371)},
        "ku_0_5":     {"x": (7.5591, 70.865),     "kopfumfang": (16.79793, -325.854)},
        "ku_1_18":    {"x": (26.67884, 44.184),   "kopfumfang": (22.67647, -757.504)},
    },
}
# fmt: on
VEL_MIN_INTERVAL = 0.5  # Jahre zwischen zwei Längenmessungen für die Geschwindigkeit
ZG_DELTA, ZG_RANGE = 6.5, 8.5
STANDING_CHARTS = {"lg_0_2", "wfl_50_120"}  # Kurven für liegende Messung
STANDING_CM = 1.0
# Formularfelder: Unterstrich-Linien im PDF (x-Start bzw. x-Mitte, y der Linie)
NAME_LINE, BIRTH_LINE = (281.7, 726.9), (322.3, 700.9)
# Mutter/Vater-Felder: (x-Mitte der Linie, y der Mutter-Linie); Vater liegt PARENT_GAP tiefer.
# Längen-Kurven: Grösse der Eltern, Kopfumfang-Kurven: Kopfumfang der Eltern.
PARENT_GAP = 13.0
# fmt: off
PARENT_FIELD: dict[str, tuple[float, float]] = {
    "lg_0_2": (163.0, 559.4), "lg_0_5": (163.0, 585.9), "lg_1_18": (163.0, 585.9),
    "ku_0_2": (163.0, 585.9), "ku_0_5": (163.0, 585.9), "ku_1_18": (163.0, 585.9),
}
# fmt: on
PARENT_FIELD_BOYS = {"ku_0_5": (150.6, 586.6)}  # Feld bei Jungen 0–5 J. weiter links
TEXT_LIFT = 2.5  # Grundlinie so weit über dem Strich, damit Unterlängen nicht kreuzen
# Farben: Messwerte klar abgesetzt von den Perzentilen (lila/rosa/orange/rot)
PLOT_RGB, ZG_RGB, TEXT_RGB = (0.0, 0.6, 0.2), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
# Kalibrierungs-Check: beschriftete Achsbereiche (von, bis, Schritt) in Achs-Einheiten
# fmt: off
CHECK: dict[str, dict[str, tuple[float, float, float]]] = {
    "lg_0_2":     {"x": (0, 24, 3),    "laenge": (45, 95, 5),   "gewicht": (2, 18, 2)},
    "lg_0_5":     {"x": (0, 60, 6),    "laenge": (50, 120, 10), "gewicht": (0, 25, 5)},
    "lg_1_18":    {"x": (1, 18, 1),    "laenge": (70, 200, 10), "gewicht": (0, 110, 10)},
    "wfl_50_120": {"x": (50, 120, 10), "gewicht": (0, 30, 5)},
    "wfl_120":    {"x": (120, 200, 10), "gewicht": (0, 130, 10)},
    "bmi":        {"x": (0, 18, 1),    "bmi": (10, 50, 5)},
    "ku_0_2":     {"x": (0, 24, 3),    "kopfumfang": (31, 56, 1)},
    "ku_0_5":     {"x": (0, 60, 6),    "kopfumfang": (31, 58, 1)},
    "ku_1_18":    {"x": (1, 18, 1),    "kopfumfang": (42, 62, 1)},
    "vel":        {"x": (2, 18, 1),    "vel": (0, 15, 1)},
    "geb_lg":     {"x": (20, 42, 2),   "laenge": (20, 60, 10),  "gewicht": (0, 5, 1)},
    "geb_ku":     {"x": (20, 42, 2),   "kopfumfang": (16, 40, 2)},
}
CHECK_GIRLS: dict[str, dict[str, tuple[float, float, float]]] = {
    "lg_1_18":    {"laenge": (70, 180, 10), "gewicht": (0, 90, 10)},
    "wfl_120":    {"x": (120, 190, 10)},
    "ku_0_2":     {"kopfumfang": (30, 55, 1)},
}
# fmt: on
CHECK_RGB = [(0.9, 0.0, 0.0), (1.0, 0.5, 0.0)]  # 1./2. y-Achse; x-Achse = erste Farbe

# Plotbereich in PDF-Koordinaten (Punkte ausserhalb werden ignoriert)
X_MIN, X_MAX, Y_MIN, Y_MAX = 70, 525, 193, 649


def parse_date(s: str) -> date:
    s = s.strip()
    try:
        if "." in s:
            d, m, y = s.split(".")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(s)
    except ValueError:
        msg = f"Unbekanntes Datum: {s!r} (erwartet YYYY-MM-DD oder TT.MM.JJJJ)"
        raise argparse.ArgumentTypeError(msg) from None


def num(s: str | None) -> float | None:
    s = (s or "").strip().replace(",", ".")
    return float(s) if s else None


def read_csv(path: str, born: date) -> list[Point]:
    text = Path(path).read_text(encoding="utf-8-sig")
    rows = csv.DictReader(
        io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ","
    )
    out: list[Point] = []
    for row in rows:
        r = {k.strip().lower(): v for k, v in row.items() if k}
        d = parse_date(r.get("datum") or "")
        p: Point = {"jahre": (d - born).days / 365.25}
        laenge = (r.get("laenge") or "").strip().upper()
        if laenge.endswith(("L", "S")):
            if laenge.endswith("S"):
                p["stehend"] = 1.0
            laenge = laenge[:-1]
        if v := num(laenge):
            p["laenge"] = v
        for k in ("gewicht", "kopfumfang"):
            if v := num(r.get(k)):
                p[k] = v
        if "laenge" in p and "gewicht" in p:
            p["bmi"] = p["gewicht"] / (p["laenge"] / 100) ** 2
        out.append(p)
    return sorted(out, key=lambda p: p["jahre"])


def velocities(points: list[Point]) -> list[Point]:
    """Längenzuwachs in cm/Jahr zwischen Messungen mit mind. VEL_MIN_INTERVAL Abstand, am Intervallmittelpunkt."""
    lp = [p for p in points if "laenge" in p]
    out: list[Point] = []
    i = 0
    while i < len(lp):
        j = next(
            (
                j
                for j in range(i + 1, len(lp))
                if lp[j]["jahre"] - lp[i]["jahre"] >= VEL_MIN_INTERVAL
            ),
            None,
        )
        if j is None:
            break
        dt = lp[j]["jahre"] - lp[i]["jahre"]
        out.append(
            {
                "jahre": (lp[i]["jahre"] + lp[j]["jahre"]) / 2,
                "vel": (lp[j]["laenge"] - lp[i]["laenge"]) / dt,
            }
        )
        i = j
    return out


def for_lying_chart(p: Point) -> Point:
    """Stehend gemessene Länge für Kurven korrigieren, die auf liegender Messung basieren."""
    if "stehend" in p and "laenge" in p:
        return {**p, "laenge": p["laenge"] + STANDING_CM}
    return p


def parse_cm(s: str) -> float:
    """CLI-Zahl, Dezimalkomma erlaubt (z.B. 55,5)."""
    return float(s.replace(",", "."))


def parse_ssw(s: str) -> float:
    w, _, d = s.partition("+")
    return float(w) + (float(d) / 7 if d else 0)


def pick(options: list[str], values: list[float]) -> list[str]:
    """Kleinstmögliche Diagramme wählen, die alle Datenpunkte abdecken (greedy)."""
    rest, chosen = list(values), list[str]()
    while rest:
        best = max(
            options,
            key=lambda o: (
                sum(CHARTS[o]["rng"][0] <= v <= CHARTS[o]["rng"][1] for v in rest),
                -(CHARTS[o]["rng"][1] - CHARTS[o]["rng"][0]),
            ),
        )
        hit = [v for v in rest if CHARTS[best]["rng"][0] <= v <= CHARTS[best]["rng"][1]]
        if not hit:
            break
        chosen.append(best)
        rest = [v for v in rest if v not in hit]
    return [o for o in options if o in chosen]  # Seitenreihenfolge beibehalten


def select_charts(
    points: list[Point], vel: list[Point], birth: Point | None
) -> list[str]:
    def has(*ks: str) -> list[Point]:
        return [p for p in points if all(k in p for k in ks)]

    charts: list[str] = []
    if birth and ("laenge" in birth or "gewicht" in birth):
        charts.append("geb_lg")
    if birth and "kopfumfang" in birth:
        charts.append("geb_ku")
    if any(2 <= v["jahre"] <= 18 for v in vel):
        charts.append("vel")
    if lg := has("laenge") + [p for p in has("gewicht") if "laenge" not in p]:
        charts += pick(["lg_0_2", "lg_0_5", "lg_1_18"], [p["jahre"] for p in lg])
    if both := has("laenge", "gewicht"):
        charts += pick(["wfl_50_120", "wfl_120"], [p["laenge"] for p in both])
        charts.append("bmi")
    if ku := has("kopfumfang"):
        charts += pick(["ku_0_2", "ku_0_5", "ku_1_18"], [p["jahre"] for p in ku])
    return sorted(charts, key=lambda c: CHARTS[c]["page"])


def target_height(sex: str, mutter: float | None, vater: float | None) -> float | None:
    """Zielgrösse nach Tanner, None wenn eine Elterngrösse fehlt."""
    if mutter is None or vater is None:
        return None
    return (mutter + vater) / 2 + (ZG_DELTA if sex == "m" else -ZG_DELTA)


def overlay(
    chart: str,
    sex: str,
    points: list[Point],
    size: tuple[float, float],
    name: str,
    born: date,
    parents: tuple[float | None, float | None],
    zg: float | None,
) -> PageObject:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    c.setFillColorRGB(*TEXT_RGB)
    c.setFont("Helvetica", 10)
    if name:
        c.drawString(NAME_LINE[0] + 3, NAME_LINE[1] + TEXT_LIFT, name)
    c.drawString(
        BIRTH_LINE[0] + 3, BIRTH_LINE[1] + TEXT_LIFT, born.strftime("%d.%m.%Y")
    )
    if chart in PARENT_FIELD:
        px, py = (PARENT_FIELD_BOYS if sex == "m" else {}).get(
            chart, PARENT_FIELD[chart]
        )
        c.setFont("Helvetica", 9)
        for i, v in enumerate(parents):
            if v:
                y = py - i * PARENT_GAP + TEXT_LIFT
                c.drawCentredString(px, y, f"{v:g}")

    cal, xunit = CAL[sex].get(chart) or CAL_BOTH[chart], CHARTS[chart]["x"]
    ax, bx = cal["x"]
    for key, (ay, by) in cal.items():
        if key == "x":
            continue
        xy: list[tuple[float, float]] = []
        for p in points:
            xv = {"cm": p.get("laenge"), "ssw": p.get("ssw"), "m": p["jahre"] * 12}.get(
                xunit, p["jahre"]
            )
            if key not in p or xv is None:
                continue
            x, y = ax * xv + bx, ay * p[key] + by
            if X_MIN - 1 <= x <= X_MAX + 1 and Y_MIN - 1 <= y <= Y_MAX + 1:
                xy.append((x, y))
        c.setStrokeColorRGB(*PLOT_RGB)
        c.setLineWidth(0.9)
        for (x1, y1), (x2, y2) in pairwise(xy):
            c.line(x1, y1, x2, y2)
        c.setFillColorRGB(*PLOT_RGB)
        c.setStrokeColorRGB(1, 1, 1)  # weisser Rand trennt den Punkt von den Kurven
        c.setLineWidth(0.8)
        for x, y in xy:
            c.circle(x, y, 2.4, stroke=1, fill=1)

    if chart == "lg_1_18" and zg is not None:
        ay, by = cal["laenge"]
        x, y = cal["x"][0] * 18 + cal["x"][1] - 6, ay * zg + by
        c.setStrokeColorRGB(*ZG_RGB)
        c.setFillColorRGB(*ZG_RGB)
        c.setLineWidth(1.5)
        c.line(x, ay * (zg - ZG_RANGE) + by, x, ay * (zg + ZG_RANGE) + by)
        c.line(x - 4, y, x + 4, y)
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(x - 6, y - 2.5, f"ZG {zg:.1f}")
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def calibration_page(chart: str, sex: str, size: tuple[float, float]) -> PageObject:
    """Gitter aus der Kalibrierung nachzeichnen, zum Vergleich mit dem gedruckten Gitter."""
    cal = CAL[sex].get(chart) or CAL_BOTH[chart]
    rng = {**CHECK[chart], **(CHECK_GIRLS.get(chart, {}) if sex == "w" else {})}

    def ticks(lo: float, hi: float, step: float) -> list[float]:
        return [lo + i * step for i in range(round((hi - lo) / step) + 1)]

    ax, bx = cal["x"]
    xs = [(v, ax * v + bx) for v in ticks(*rng["x"])]
    ys = {
        k: [(v, cal[k][0] * v + cal[k][1]) for v in ticks(*rng[k])]
        for k in cal
        if k != "x"
    }
    x0, x1 = xs[0][1], xs[-1][1]
    all_y = [y for line in ys.values() for _, y in line]
    y0, y1 = min(all_y), max(all_y)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*CHECK_RGB[0])
    c.drawString(40, size[1] - 30, f"KALIBRIERUNG  {sex.upper()}  {chart}")
    c.setLineWidth(0.4)
    c.setFont("Helvetica", 5)
    c.setStrokeColorRGB(*CHECK_RGB[0])
    for v, x in xs:
        c.line(x, y0, x, y1)
        c.drawCentredString(x, y0 - 7, f"{v:g}")
    for i, (key, line) in enumerate(ys.items()):
        rgb = CHECK_RGB[i % len(CHECK_RGB)]
        c.setStrokeColorRGB(*rgb)
        c.setFillColorRGB(*rgb)
        for v, y in line:
            c.line(x0, y, x1, y)
            if i == 0:
                c.drawRightString(x0 - 2, y - 1.8, f"{v:g}")
            else:
                c.drawString(x1 + 2, y - 1.8, f"{v:g}")
    c.setStrokeColorRGB(*CHECK_RGB[0])
    c.setLineWidth(1.2)
    c.rect(x0, y0, x1 - x0, y1 - y0)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("csv", nargs="?")
    ap.add_argument(
        "-g", "--geschlecht", choices=["m", "w"], help="m = Junge, w = Mädchen"
    )
    ap.add_argument("-b", "--geburtsdatum", type=parse_date)
    ap.add_argument(
        "--kalibrierung",
        action="store_true",
        help="alle Seiten mit nachgezeichnetem Gitter ausgeben (ohne CSV)",
    )
    ap.add_argument("-n", "--name", default="")
    ap.add_argument(
        "--ssw", type=parse_ssw, help="Gestationsalter bei Geburt, z.B. 39+3"
    )
    ap.add_argument("--mutter", type=parse_cm, help="Grösse Mutter in cm")
    ap.add_argument("--vater", type=parse_cm, help="Grösse Vater in cm")
    ap.add_argument("--mutter-ku", type=parse_cm, help="Kopfumfang Mutter in cm")
    ap.add_argument("--vater-ku", type=parse_cm, help="Kopfumfang Vater in cm")
    ap.add_argument("-o", "--out", help="Ausgabe-PDF (Standard: <csv>_kurven.pdf)")
    ap.add_argument(
        "-p",
        "--pdf",
        required=True,
        type=Path,
        help="Pfad zur Vorlage PCH_Wachstumskurven_260701_DE.pdf von pädiatrie schweiz",
    )
    a = ap.parse_args()
    if not a.kalibrierung and not (a.csv and a.geschlecht and a.geburtsdatum):
        ap.error("csv, -g und -b sind erforderlich (ausser mit --kalibrierung)")

    if not a.pdf.is_file():
        ap.error(f"Vorlage nicht gefunden: {a.pdf}")
    if a.csv and not Path(a.csv).is_file():
        ap.error(f"CSV nicht gefunden: {a.csv}")

    if hashlib.sha256(a.pdf.read_bytes()).hexdigest() != PDF_SHA256:
        print(
            f"WARNUNG: Prüfsumme von {a.pdf} weicht ab – die Vorlage wurde geändert.\n"
            "         Die Punkte können falsch liegen; das Gitter muss evtl. NEU kalibriert werden.",
            file=sys.stderr,
        )

    if a.kalibrierung:
        template, writer = PdfReader(a.pdf), PdfWriter()
        for sex in [a.geschlecht] if a.geschlecht else ["m", "w"]:
            for chart in sorted(CHARTS, key=lambda c: CHARTS[c]["page"]):
                off = GIRLS_OFFSET if sex == "w" else 0
                page = template.pages[CHARTS[chart]["page"] - 1 + off]
                size = (float(page.mediabox.width), float(page.mediabox.height))
                page.merge_page(calibration_page(chart, sex, size))
                writer.add_page(page)
        out = Path(a.out or "kalibrierung.pdf")
        writer.write(out)
        print(f"Kalibrierungs-Check: {len(writer.pages)} Seiten → {out}")
        return

    points = read_csv(a.csv, a.geburtsdatum)
    vel = velocities(points)
    birth: Point | None = None
    if a.ssw:
        birth = next((p for p in points if p["jahre"] == 0), None)
        if birth:
            birth = {**birth, "ssw": a.ssw}
        else:
            print(
                "Hinweis: --ssw angegeben, aber keine CSV-Zeile mit datum = Geburtsdatum."
            )
    heights: tuple[float | None, float | None] = (a.mutter, a.vater)
    head: tuple[float | None, float | None] = (a.mutter_ku, a.vater_ku)
    if (zg := target_height(a.geschlecht, *heights)) is not None:
        print(
            f"Zielgrösse: {zg:.1f} cm (Bereich {zg - ZG_RANGE:.1f}–{zg + ZG_RANGE:.1f} cm)"
        )
    charts = select_charts(points, vel, birth)
    if not charts:
        raise SystemExit("Keine verwertbaren Messwerte gefunden.")

    template, writer = PdfReader(a.pdf), PdfWriter()
    offset = GIRLS_OFFSET if a.geschlecht == "w" else 0
    for chart in charts:
        page = template.pages[CHARTS[chart]["page"] - 1 + offset]
        size = (float(page.mediabox.width), float(page.mediabox.height))
        data = vel if chart == "vel" else points
        if chart in STANDING_CHARTS:
            data = [for_lying_chart(p) for p in points]
        if chart.startswith("geb_") and birth:
            data = [birth]
        page.merge_page(
            overlay(
                chart,
                a.geschlecht,
                data,
                size,
                a.name,
                a.geburtsdatum,
                head if chart.startswith("ku_") else heights,
                zg,
            )
        )
        writer.add_page(page)

    out = Path(a.out or Path(a.csv).with_suffix("").as_posix() + "_kurven.pdf")
    writer.write(out)
    print(
        f"{len(points)} Messungen → {len(charts)} Diagramme ({', '.join(charts)}) → {out}"
    )


if __name__ == "__main__":
    main()

"""Strict parser for observed CME Current meeting views (not a pricing model)."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def meeting_date(label):
    match = re.fullmatch(r"\s*(\d{1,2})\s+([A-Za-z]{3})\s*(\d{2}|\d{4})\s*", label)
    if not match:
        raise ValueError("Invalid meeting label")
    day, month, year = match.groups()
    year = "20" + year if len(year) == 2 else year
    return datetime.strptime(f"{day} {month} {year}", "%d %b %Y").date().isoformat()


def parse_view(text, label):
    date = meeting_date(label)
    heading = re.search(r"Target Rate Probabilities for (\d{1,2}\s+[A-Za-z]{3}\s+\d{4}) Fed Meeting", text)
    if not heading or meeting_date(heading[1]) != date:
        raise ValueError("Meeting view has not switched to the requested date")
    current = re.search(r"Current target rate is (\d+)-(\d+)\b", text)
    if not current:
        raise ValueError("Missing current target range")
    lower, upper = map(int, current.groups())
    if upper - lower != 25:
        raise ValueError("Unexpected current target interval")
    stamp = re.search(r"Data as of (\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}) CT", text)
    if not stamp:
        raise ValueError("Missing or unsupported CME source timestamp")
    source_time = datetime.strptime(stamp[1], "%d %b %Y %H:%M:%S").replace(tzinfo=ZoneInfo("America/Chicago"))
    summary = re.search(r"PROBABILITIES\s+EASE\s+NO CHANGE\s+HIKE\s+([\d.]+)\s*%\s+([\d.]+)\s*%\s+([\d.]+)\s*%", text)
    if not summary:
        raise ValueError("Missing probability summary")
    ease, hold, hike = map(float, summary.groups())
    if any(not 0 <= p <= 100 for p in (ease, hold, hike)) or abs(ease + hold + hike - 100) > .2:
        raise ValueError("Invalid summary probabilities")
    table = text.split("TARGET RATE (BPS)", 1)
    if len(table) != 2:
        raise ValueError("Missing probability table")
    rows = []
    current_rows = 0
    for line in table[1].splitlines():
        cells = line.split("\t")
        interval = re.fullmatch(r"(\d+)-(\d+)(\s+\(Current\))?", cells[0].strip())
        if not interval:
            continue
        if len(cells) < 2 or not re.fullmatch(r"\d+(?:\.\d+)?%", cells[1].strip()):
            raise ValueError("Missing NOW probability; not replaced with zero")
        lo, hi = int(interval[1]), int(interval[2])
        probability = float(cells[1].strip().rstrip("%"))
        if hi - lo != 25 or lo < 0 or not 0 <= probability <= 100:
            raise ValueError("Invalid target interval or probability")
        if interval[3]:
            current_rows += 1
            if (lo, hi) != (lower, upper):
                raise ValueError("Current target labels disagree")
        rows.append({"lower": lo, "upper": hi, "probability": probability})
    if not rows or current_rows != 1 or len({r['lower'] for r in rows}) != len(rows):
        raise ValueError("Empty, duplicated, or inconsistent probability rows")
    if abs(sum(r['probability'] for r in rows) - 100) > .6:
        raise ValueError("Probability rows do not sum to 100 percent")
    for expected, selected in ((ease, [r for r in rows if r['lower'] < lower]), (hold, [r for r in rows if r['lower'] == lower]), (hike, [r for r in rows if r['lower'] > lower])):
        if abs(sum(r['probability'] for r in selected) - expected) > .6:
            raise ValueError("Probability table and summary disagree")
    return {"date": date, "currentLower": lower, "currentUpper": upper, "ease": ease, "hold": hold, "hike": hike, "ranges": rows, "sourceAsOf": source_time.astimezone(timezone.utc).isoformat(), "sourceTimeLabel": stamp[0]}


def validate_snapshot(views, collected_at=None):
    now = collected_at or datetime.now(timezone.utc)
    meetings = [parse_view(view['text'], view['tabLabel']) for view in views]
    dates = [m['date'] for m in meetings]
    if not 1 <= len(meetings) <= 24 or dates != sorted(set(dates)):
        raise ValueError("Missing, duplicated, or out-of-order meetings")
    for m in meetings:
        stamp = datetime.fromisoformat(m['sourceAsOf'])
        if (stamp - now).total_seconds() > 300:
            local = stamp.astimezone(ZoneInfo('America/Chicago'))
            candidate = local.replace(hour=0).astimezone(timezone.utc)
            # CME displays 12:xx CT without AM/PM around midnight. Only infer
            # midnight on the same Chicago date within a two-hour window.
            if local.hour != 12 or local.date() != now.astimezone(ZoneInfo('America/Chicago')).date() or not 0 <= (now - candidate).total_seconds() <= 7200:
                raise ValueError("Future source timestamp")
            m['sourceAsOf'] = candidate.isoformat()
            m['sourceTimeInferred'] = True
        if m['date'] < now.astimezone(ZoneInfo('America/Chicago')).date().isoformat():
            raise ValueError("Past meeting in upcoming probability feed")
    if len({(m['currentLower'], m['currentUpper']) for m in meetings}) != 1:
        raise ValueError("Inconsistent current target across meetings")
    return {"schemaVersion": 1, "source": "CME FedWatch", "sourceUrl": "https://www.cmegroup.cn/fed-watch/", "collectedAt": now.isoformat(), "meetings": meetings}

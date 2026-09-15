"""
REMIT Insider — Logic Layer
Parses raw Elexon REMIT JSON into human-readable, severity-classified alerts.
"""

from datetime import datetime, timezone
import re

# ──────────────────────────────────────────────
# Friendly name mapping for well-known UK assets
# ──────────────────────────────────────────────
ASSET_FRIENDLY_NAMES = {
    "DRAXX": "Drax",
    "DIDCB": "Didcot B",
    "WBURB": "West Burton B",
    "WBUPS": "West Burton",
    "COTPS": "Cottam",
    "RATS":  "Ratcliffe",
    "SIZB":  "Sizewell B",
    "HRTL":  "Hartlepool",
    "TORN":  "Torness",
    "HEYM":  "Heysham",
    "HUMR":  "Humber Gateway",
    "PEHE":  "Peterhead",
    "CARR":  "Carrington",
    "SEAB":  "Seabank",
    "STAY":  "Staythorpe",
    "PEMB":  "Pembroke",
    "GRAI":  "Grain",
    "DINO":  "Dinorwig",
    "FFES":  "Ffestiniog",
    "SHBA":  "Shoreham",
    "LBAR":  "Little Barford",
    "SPLN":  "Spalding",
    "COCK":  "Coryton",
    "EECL":  "Enfield Energy",
    "CNQPS": "Connah's Quay",
    "DAMC":  "Damhead Creek",
    "KEAD":  "Keadby",
    "SCCL":  "Saltend",
    "GYAR":  "Great Yarmouth",
    "CDCL":  "Corby",
    "MRWD":  "Marchwood",
    "LAGA":  "Langage",
    "ROCK":  "Rocksavage",
    "SHOS":  "Shotton",
    "MEDP":  "Medway",
    "DEEP":  "Deeside",
    "FELL":  "Fellside",
    "WLNY":  "Wilton",
    "KILL":  "Killingholme",
    "HUMR":  "Immingham",
    "GRIFW": "Griffin Wind",
    "WHILW": "Whitelee Wind",
    "CLDRW": "Clyde Wind",
    "BLLA":  "Beauly",
    "FOYE":  "Foyers",
    "CRUA":  "Cruachan",
}

FUEL_LABELS = {
    "Fossil Gas": "⛽ Gas",
    "Fossil Hard coal": "🪨 Coal",
    "Fossil Oil": "🛢️ Oil",
    "Nuclear": "☢️ Nuclear",
    "Biomass": "🌿 Biomass",
    "Wind Onshore": "🌬️ Wind (Onshore)",
    "Wind Offshore": "🌊 Wind (Offshore)",
    "Hydro Pumped Storage": "💧 Hydro Pumped",
    "Hydro Water Reservoir": "💧 Hydro Reservoir",
    "Hydro Run-of-river and poundage": "💧 Hydro Run-of-river",
    "Solar": "☀️ Solar",
    "Other": "⚡ Other",
    "Waste": "♻️ Waste",
}


def _friendly_name(affected_unit: str) -> str:
    """Resolve a BMU code like 'EECL-1' to 'Enfield Energy Unit 1'."""
    if not affected_unit:
        return "Unknown Asset"
    # Strip T_ prefix
    clean = re.sub(r"^T_", "", affected_unit)
    # Try to match the base code (letters before digits/hyphens)
    base = re.split(r"[-\d]", clean)[0].upper()
    unit_match = re.search(r"[-]?(\d+)$", clean)
    unit_num = unit_match.group(1) if unit_match else ""

    friendly = ASSET_FRIENDLY_NAMES.get(base, clean)
    if unit_num:
        return f"{friendly} Unit {unit_num}"
    return friendly


def _fuel_label(fuel_type: str) -> str:
    """Convert raw fuel type string to a labelled emoji version."""
    if not fuel_type:
        return "⚡ Unknown"
    return FUEL_LABELS.get(fuel_type, f"⚡ {fuel_type}")


def _format_time(iso_str: str) -> str:
    """Parse ISO datetime string to a concise display format."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d %b %H:%M UTC")
    except (ValueError, TypeError):
        return iso_str


def _relative_time(iso_str: str) -> str:
    """Return a human-readable relative time like '3h ago'."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            # Future event
            secs = abs(secs)
            if secs < 3600:
                return f"in {secs // 60}m"
            if secs < 86400:
                return f"in {secs // 3600}h"
            return f"in {secs // 86400}d"
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return ""


def classify_severity(mw_impact: float) -> str:
    """Classify alert severity based on MW capacity change."""
    if mw_impact >= 500:
        return "FLASH"
    if mw_impact >= 200:
        return "MAJOR"
    return "MINOR"


def classify_event_type(raw: dict) -> str:
    """Determine the event category from raw REMIT data."""
    status = (raw.get("eventStatus") or "").lower()
    unavail_type = (raw.get("unavailabilityType") or "").lower()
    normal_cap = raw.get("normalCapacity", 0) or 0
    avail_cap = raw.get("availableCapacity", 0) or 0

    if status == "dismissed" or (avail_cap >= normal_cap and normal_cap > 0):
        return "RETURN"
    if unavail_type == "unplanned":
        if avail_cap == 0:
            return "TRIP"
        return "REDUCED"
    if unavail_type == "planned":
        if avail_cap == 0:
            return "OUTAGE"
        return "REDUCED"
    return "UPDATE"


def parse_alert(raw: dict) -> dict:
    """
    Convert a raw REMIT message dict into a structured, human-readable alert.

    Returns a dict with keys:
        id, mrid, revision, headline, detail, severity, event_type,
        fuel, fuel_label, asset_name, asset_id, participant,
        normal_mw, available_mw, impact_mw, unavailability_type,
        event_status, event_start, event_end, published, cause,
        published_relative, event_start_relative
    """
    normal_cap = raw.get("normalCapacity", 0) or 0
    avail_cap = raw.get("availableCapacity", 0) or 0
    unavail_cap = raw.get("unavailableCapacity", 0) or 0

    # Use unavailableCapacity if provided, otherwise compute
    impact_mw = unavail_cap if unavail_cap > 0 else max(0, normal_cap - avail_cap)

    event_type = classify_event_type(raw)
    severity = classify_severity(impact_mw)

    affected_unit = raw.get("affectedUnit") or raw.get("assetId") or ""
    asset_name = _friendly_name(affected_unit)
    fuel_type = raw.get("fuelType") or ""
    fuel_label = _fuel_label(fuel_type)

    # Build headline
    if event_type == "TRIP":
        headline = f"🔴 {asset_name} TRIPPED — {impact_mw:.0f} MW offline"
    elif event_type == "OUTAGE":
        headline = f"🟠 {asset_name} Planned Outage — {impact_mw:.0f} MW offline"
    elif event_type == "RETURN":
        headline = f"🟢 {asset_name} Returned to Service — {normal_cap:.0f} MW restored"
    elif event_type == "REDUCED":
        headline = f"🟡 {asset_name} Reduced Output — {impact_mw:.0f} MW lost"
    else:
        headline = f"🔵 {asset_name} Update — {impact_mw:.0f} MW impact"

    # Detail line
    cause = raw.get("cause") or ""
    detail_parts = [fuel_label]
    if cause and cause.lower() not in ("", "n/a", '""'):
        detail_parts.append(cause.strip('"').strip())
    detail = " · ".join(detail_parts)

    return {
        "id": raw.get("id"),
        "mrid": raw.get("mrid", ""),
        "revision": raw.get("revisionNumber", 0),
        "headline": headline,
        "detail": detail,
        "severity": severity,
        "event_type": event_type,
        "fuel": fuel_type,
        "fuel_label": fuel_label,
        "asset_name": asset_name,
        "asset_id": affected_unit,
        "participant": raw.get("participantId", ""),
        "normal_mw": normal_cap,
        "available_mw": avail_cap,
        "impact_mw": impact_mw,
        "unavailability_type": raw.get("unavailabilityType", ""),
        "event_status": raw.get("eventStatus", ""),
        "event_start": _format_time(raw.get("eventStartTime")),
        "event_end": _format_time(raw.get("eventEndTime")),
        "published": _format_time(raw.get("publishTime")),
        "cause": cause,
        "published_relative": _relative_time(raw.get("publishTime")),
        "event_start_relative": _relative_time(raw.get("eventStartTime")),
    }

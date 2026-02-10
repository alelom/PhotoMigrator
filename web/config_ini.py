"""
Parse and build Config.ini for the web config page.
Schema defines sections and keys in order; keys containing PASSWORD or API_KEY use password inputs.
"""
from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from typing import Any


# Delimiter for form field names: "section||key" (section may contain spaces; key does not)
FORM_SEP = "||"


# Section-level help text (from Config.ini comments)
SECTION_HINTS: dict[str, str] = {
    "Google Takeout": "No configuration needed for this module for the time being.",
    "Synology Photos": "Set the URL to your Synology server (IP or hostname). Use SYNOLOGY_USERNAME_n and SYNOLOGY_PASSWORD_n for each account (n = 1, 2, or 3).",
    "Immich Photos": "Set the Immich server URL and either API keys (Account Settings → API Keys) or username/password per account. ADMIN_API_KEY is required for some operations (e.g. remove orphan assets).",
    "Apple Photos": "iCloud Apple Photos: use album = all for all albums; set to_directory for download path; date_from/date_to and asset_from/asset_to for date filters; max_photos to limit downloads; shared_library (e.g. PrimarySync) for library selection.",
    "Google Photos": "No configuration needed for this module for the time being.",
    "TimeZone": "Optional timezone for interpreting photo dates. When EXIF/metadata has no timezone (e.g. '2024:06:15 14:30:00' without offset), the tool currently uses the machine's local timezone where the app runs. Photos taken in a different timezone are then interpreted as if they were in that local timezone, which can affect date-based grouping, album naming, and filtering. This setting is stored for features that may use it; set it to the IANA timezone where most of your photos were taken (e.g. US/Central) for future or optional override behavior.",
}

# Per-option help text (from Config.ini inline comments)
OPTION_HINTS: dict[tuple[str, str], str] = {
    ("Synology Photos", "SYNOLOGY_URL"): "URL of your Synology server (e.g. http://192.168.1.11:5000) or your valid Synology hostname.",
    ("Synology Photos", "SYNOLOGY_USERNAME_1"): "Account 1: Your username for Synology Photos.",
    ("Synology Photos", "SYNOLOGY_PASSWORD_1"): "Account 1: Your password for Synology Photos.",
    ("Synology Photos", "SYNOLOGY_USERNAME_2"): "Account 2: Your username for Synology Photos.",
    ("Synology Photos", "SYNOLOGY_PASSWORD_2"): "Account 2: Your password for Synology Photos.",
    ("Synology Photos", "SYNOLOGY_USERNAME_3"): "Account 3: Your username for Synology Photos.",
    ("Synology Photos", "SYNOLOGY_PASSWORD_3"): "Account 3: Your password for Synology Photos.",
    ("Immich Photos", "IMMICH_URL"): "URL of your Immich server (e.g. http://192.168.1.11:2283).",
    ("Immich Photos", "IMMICH_API_KEY_ADMIN"): "Admin API key from Immich (Account Settings → API Keys). Required for some operations.",
    ("Immich Photos", "IMMICH_API_KEY_USER_1"): "Account 1: User API key from Immich (Account Settings → API Keys).",
    ("Immich Photos", "IMMICH_USERNAME_1"): "Account 1: Username (used if API key not provided).",
    ("Immich Photos", "IMMICH_PASSWORD_1"): "Account 1: Password (used if API key not provided).",
    ("Immich Photos", "IMMICH_API_KEY_USER_2"): "Account 2: User API key.",
    ("Immich Photos", "IMMICH_USERNAME_2"): "Account 2: Username.",
    ("Immich Photos", "IMMICH_PASSWORD_2"): "Account 2: Password.",
    ("Immich Photos", "IMMICH_API_KEY_USER_3"): "Account 3: User API key.",
    ("Immich Photos", "IMMICH_USERNAME_3"): "Account 3: Username.",
    ("Immich Photos", "IMMICH_PASSWORD_3"): "Account 3: Password.",
    ("Apple Photos", "appleid"): "Your Apple ID for iCloud.",
    ("Apple Photos", "applepwd"): "Your Apple ID password.",
    ("Apple Photos", "album"): "Album name to download, or 'all' for all albums.",
    ("Apple Photos", "to_directory"): "Directory path where photos will be downloaded (year/month/day structure will be created).",
    ("Apple Photos", "date_from"): "Filter: photos added to library from this date.",
    ("Apple Photos", "date_to"): "Filter: photos added to library until this date.",
    ("Apple Photos", "asset_from"): "Filter: asset date from.",
    ("Apple Photos", "asset_to"): "Filter: asset date to.",
    ("Apple Photos", "max_photos"): "Maximum number of photos to download (safety limit).",
    ("Apple Photos", "shared_library"): "Library identifier (e.g. PrimarySync for main library).",
    ("TimeZone", "timezone"): "IANA timezone name (e.g. US/Central, Europe/London). Used when the tool interprets date/time from photos that have no timezone in metadata; set to the timezone where your photos were typically taken so date-based features (sorting, album names, filters) are consistent. Currently the app may use the server's system timezone if this is not applied yet.",
}


def _strip_inline_comment(value: str) -> str:
    """Remove inline comment (from # to end of line) and strip whitespace."""
    if not value:
        return value
    i = value.find("#")
    if i >= 0:
        value = value[:i]
    return value.strip()


def _get_option_hint(section: str, key: str) -> str:
    return OPTION_HINTS.get((section, key), "")


def _get_section_hint(section: str) -> str:
    return SECTION_HINTS.get(section, "")


def _is_password_key(key: str) -> bool:
    k = key.upper()
    return "PASSWORD" in k or "API_KEY" in k or "SECRET" in k or k in ("APPLEPWD",)


def _section_to_form(section: str) -> str:
    """Section name for use in form field names (spaces to underscores)."""
    return section.replace(" ", "_")


def _form_to_section(form_section: str) -> str:
    """Restore section name from form (underscores to spaces)."""
    return form_section.replace("_", " ")


def parse_config(path: Path) -> list[dict[str, Any]]:
    """
    Read Config.ini and return a list of sections, each with name and list of {key, value, is_password}.
    Preserves section and key order. Returns [] if file missing or invalid.
    """
    if not path.exists():
        return _default_sections_structure()

    cp = ConfigParser()
    cp.optionxform = str  # preserve key case (e.g. SYNOLOGY_URL not synology_url)
    try:
        cp.read(path, encoding="utf-8")
    except Exception:
        return _default_sections_structure()

    sections_out = []
    for section in cp.sections():
        keys_out = []
        for key in cp.options(section):
            raw_value = cp.get(section, key, raw=True)
            value = _strip_inline_comment(raw_value)
            keys_out.append({
                "key": key,
                "value": value,
                "is_password": _is_password_key(key),
                "form_section": _section_to_form(section),
                "hint": _get_option_hint(section, key),
            })
        sections_out.append({
            "name": section,
            "form_section": _section_to_form(section),
            "hint": _get_section_hint(section),
            "options": keys_out,
        })
    if not sections_out:
        return _default_sections_structure()
    return sections_out


def _default_sections_structure() -> list[dict[str, Any]]:
    """Default sections and keys when file is missing (matches Config.ini layout)."""
    return [
        {"name": "Google Takeout", "form_section": _section_to_form("Google Takeout"), "hint": _get_section_hint("Google Takeout"), "options": []},
        {
            "name": "Synology Photos",
            "form_section": _section_to_form("Synology Photos"),
            "hint": _get_section_hint("Synology Photos"),
            "options": [
                {"key": "SYNOLOGY_URL", "value": "", "is_password": False, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_URL")},
                {"key": "SYNOLOGY_USERNAME_1", "value": "", "is_password": False, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_USERNAME_1")},
                {"key": "SYNOLOGY_PASSWORD_1", "value": "", "is_password": True, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_PASSWORD_1")},
                {"key": "SYNOLOGY_USERNAME_2", "value": "", "is_password": False, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_USERNAME_2")},
                {"key": "SYNOLOGY_PASSWORD_2", "value": "", "is_password": True, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_PASSWORD_2")},
                {"key": "SYNOLOGY_USERNAME_3", "value": "", "is_password": False, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_USERNAME_3")},
                {"key": "SYNOLOGY_PASSWORD_3", "value": "", "is_password": True, "form_section": _section_to_form("Synology Photos"), "hint": _get_option_hint("Synology Photos", "SYNOLOGY_PASSWORD_3")},
            ],
        },
        {
            "name": "Immich Photos",
            "form_section": _section_to_form("Immich Photos"),
            "hint": _get_section_hint("Immich Photos"),
            "options": [
                {"key": "IMMICH_URL", "value": "", "is_password": False, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_URL")},
                {"key": "IMMICH_API_KEY_ADMIN", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_API_KEY_ADMIN")},
                {"key": "IMMICH_API_KEY_USER_1", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_API_KEY_USER_1")},
                {"key": "IMMICH_USERNAME_1", "value": "", "is_password": False, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_USERNAME_1")},
                {"key": "IMMICH_PASSWORD_1", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_PASSWORD_1")},
                {"key": "IMMICH_API_KEY_USER_2", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_API_KEY_USER_2")},
                {"key": "IMMICH_USERNAME_2", "value": "", "is_password": False, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_USERNAME_2")},
                {"key": "IMMICH_PASSWORD_2", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_PASSWORD_2")},
                {"key": "IMMICH_API_KEY_USER_3", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_API_KEY_USER_3")},
                {"key": "IMMICH_USERNAME_3", "value": "", "is_password": False, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_USERNAME_3")},
                {"key": "IMMICH_PASSWORD_3", "value": "", "is_password": True, "form_section": _section_to_form("Immich Photos"), "hint": _get_option_hint("Immich Photos", "IMMICH_PASSWORD_3")},
            ],
        },
        {
            "name": "Apple Photos",
            "form_section": _section_to_form("Apple Photos"),
            "hint": _get_section_hint("Apple Photos"),
            "options": [
                {"key": "appleid", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "appleid")},
                {"key": "applepwd", "value": "", "is_password": True, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "applepwd")},
                {"key": "album", "value": "all", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "album")},
                {"key": "to_directory", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "to_directory")},
                {"key": "date_from", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "date_from")},
                {"key": "date_to", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "date_to")},
                {"key": "asset_from", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "asset_from")},
                {"key": "asset_to", "value": "", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "asset_to")},
                {"key": "max_photos", "value": "10000", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "max_photos")},
                {"key": "shared_library", "value": "PrimarySync", "is_password": False, "form_section": _section_to_form("Apple Photos"), "hint": _get_option_hint("Apple Photos", "shared_library")},
            ],
        },
        {"name": "Google Photos", "form_section": _section_to_form("Google Photos"), "hint": _get_section_hint("Google Photos"), "options": []},
        {
            "name": "TimeZone",
            "form_section": _section_to_form("TimeZone"),
            "hint": _get_section_hint("TimeZone"),
            "options": [
                {"key": "timezone", "value": "US/Central", "is_password": False, "form_section": _section_to_form("TimeZone"), "hint": _get_option_hint("TimeZone", "timezone")},
            ],
        },
    ]


def _merge_parsed_with_schema(parsed: list[dict], schema: list[dict]) -> list[dict]:
    """Merge parsed file sections with schema so we have all keys, with values from file when present."""
    by_name = {s["name"]: s for s in parsed}
    out = []
    for sect in schema:
        name = sect["name"]
        schema_keys = {k["key"]: k for k in sect["options"]}
        if name in by_name:
            for k in by_name[name]["options"]:
                if k["key"] in schema_keys:
                    schema_keys[k["key"]]["value"] = k["value"]
        keys_out = list(schema_keys.values())
        for k in keys_out:
            k["form_section"] = _section_to_form(name)
        out.append({"name": name, "form_section": _section_to_form(name), "hint": _get_section_hint(name), "options": keys_out})
    return out


def parse_config_with_schema(path: Path) -> list[dict[str, Any]]:
    """Parse file and merge with default schema so all known keys appear; use file values when present."""
    schema = _default_sections_structure()
    if not path.exists():
        return schema
    parsed = parse_config(path)
    if not parsed:
        return schema
    return _merge_parsed_with_schema(parsed, schema)


def build_ini_from_form(form_data: dict[str, str]) -> str:
    """
    Rebuild INI content from form data. Form keys must be "v" + FORM_SEP + form_section + FORM_SEP + key.
    All schema sections are emitted in order; keys come from form_data.
    """
    prefix = "v" + FORM_SEP
    # Collect (section, key) -> value from form
    by_section: dict[str, list[tuple[str, str]]] = {}
    for form_key, value in form_data.items():
        if not form_key.startswith(prefix) or FORM_SEP not in form_key[len(prefix):]:
            continue
        rest = form_key[len(prefix):]
        parts = rest.split(FORM_SEP, 1)
        if len(parts) != 2:
            continue
        form_section, key = parts
        section = _form_to_section(form_section)
        value = (value or "").strip()
        if section not in by_section:
            by_section[section] = []
        by_section[section].append((key, value))

    schema = _default_sections_structure()
    lines = ["# Config.ini File", ""]
    value_by_section_key: dict[str, dict[str, str]] = {}
    for section, pairs in by_section.items():
        value_by_section_key[section] = dict(pairs)
    for sect in schema:
        name = sect["name"]
        vals = value_by_section_key.get(name, {})
        lines.append(f"[{name}]")
        for key_info in sect["options"]:
            k = key_info["key"]
            v = vals.get(k, "")
            lines.append(f"{k} = {v}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def form_field_name(form_section: str, key: str) -> str:
    """Name attribute for the form input."""
    return "v" + FORM_SEP + form_section + FORM_SEP + key

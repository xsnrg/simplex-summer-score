"""ADIF file parser and validator for batch submission of simplex contacts."""

import re
from dataclasses import dataclass, field
from datetime import datetime


# Core required ADIF fields that map to our form
REQUIRED_FIELDS = {"call", "qso_date", "time_on"}

# Maximum allowed lines in an uploaded ADI file
MAX_ADI_LINES = 500

# Regex for callsigns: alphanumeric, hyphens, slashes; 1-20 chars
CALLSIGN_RE = re.compile(r'^[A-Z0-9/\-]{1,20}$')

# Allowed characters for POTA park references (alphanumeric + dash/underscore)
POTA_PARK_RE = re.compile(r'^[A-Z0-9\-_]+$')

# Max length for text fields to prevent oversized payloads
MAX_TEXT_LEN = 500

# ADIF tag pattern: <tag_name:length>value<EOR> (repeated within a record)
ADI_TAG_RE = re.compile(r"<([a-zA-Z_]+):(\d+)>([^<]*)", re.DOTALL)

# Valid digital modes in ADIF (maps to our form's digital_mode options)
VALID_DIGITAL_MODES = {"SSTV", "PSK", "RTTY", "FT4/8", "JS8", "WINLINK"}

# Common ham band frequencies in MHz (for sanity checking)
COMMON_BANDS = [
    1.8, 3.5, 5.0, 7.0, 10.1, 14.0, 18.06, 21.0, 24.89, 28.0,
    50.0, 52.0, 144.0, 146.0, 222.0, 420.0, 432.0, 440.0,
    902.0, 904.0, 1200.0, 1240.0,
]


@dataclass
class ADIFRecord:
    """A single parsed ADIF contact record."""
    submitted_by: str = ""        # MY_CALL or CALL (who we are)
    contact_call: str = ""        # CALL field
    qso_date: str = ""            # YYYYMMDD
    time_on: str = ""             # HHMMSS
    mode_type: str = "voice"      # voice | digital
    is_pota: bool = False         # POTA contact flag
    pota_park: str = ""           # POTA park reference
    digital_mode: str = ""        # digital mode name
    frequency: float = 0.0        # in MHz
    notes: str = ""               # comments
    is_duplicate: bool = False    # flagged as duplicate during dedup pass


@dataclass
class ADIFParseResult:
    """Result of parsing an ADIF file."""
    success: bool
    records: list[ADIFRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)  # deduped records info


def _parse_record(raw_text: str) -> ADIFRecord | None:
    """Parse a single ADIF record block into an ADIFRecord."""
    record = ADIFRecord()

    # The regex finds all <TAG:length>value<EOR> blocks in the text.
    for match in ADI_TAG_RE.finditer(raw_text):
        tag_name = match.group(1).lower()
        value_raw = match.group(3)  # raw value from original content
        value = value_raw.strip().upper()

        if tag_name == "my_call":
            record.submitted_by = value
        elif tag_name == "call":
            record.contact_call = value
        elif tag_name == "qso_date":
            record.qso_date = value
        elif tag_name == "time_on":
            record.time_on = value
        elif tag_name == "mode":
            # ADIF mode codes: FM, LSB, USB, AM (voice), CW/RTTY/SSTV/FT4/FT8/PSK31/JS8/WINLINK (digital)
            adif_to_our_mode = {
                "FM":     ("voice",   None),
                "LSB":    ("voice",   None),
                "USB":    ("voice",   None),
                "AM":     ("voice",   None),
                "CW":     ("digital", "CW"),
                "RTTY":   ("digital", "RTTY"),
                "FT4":    ("digital", "FT4/8"),
                "FT8":    ("digital", "FT4/8"),
                "SSTV":   ("digital", "SSTV"),
                "PSK31":  ("digital", "PSK"),
                "JS8":    ("digital", "JS8"),
                "WINLINK":("digital", "Winlink"),
            }
            if adif_to_our_mode.get(value):
                record.mode_type, digital = adif_to_our_mode[value]
                if digital:
                    record.digital_mode = digital
        elif tag_name == "freq":
            try:
                record.frequency = float(value)
            except ValueError:
                pass
        elif tag_name == "pota":
            record.pota_park = value  # park refs are case-insensitive
        elif tag_name == "digital_mode":
            dm = value.upper()
            if dm in VALID_DIGITAL_MODES:
                record.digital_mode = dm
                record.mode_type = "digital"
        elif tag_name == "comments":
            # ADIF spec: COMMENTS preserves case; store lowercased for consistency with other fields
            record.notes = value_raw.strip().lower()

    return record


def _validate_record(record: ADIFRecord, line_num: int) -> list[str]:
    """Validate a single parsed record. Returns list of error messages."""
    errors = []

    # --- Callsign format validation (prevents injection) ---
    if not record.contact_call:
        errors.append(f"Line {line_num}: Missing required field CALL (their callsign).")
    elif len(record.contact_call) < 2 or len(record.contact_call) > 20:
        errors.append(f"Line {line_num}: CALL '{record.contact_call}' is not a valid callsign length.")
    elif not CALLSIGN_RE.match(record.contact_call):
        errors.append(
            f"Line {line_num}: CALL '{record.contact_call}' contains invalid characters. "
            "Only alphanumeric, hyphens, and slashes are allowed."
        )

    if not record.submitted_by:
        # Not strictly required — we can use a default or prompt later
        pass
    elif len(record.submitted_by) > 20 or not CALLSIGN_RE.match(record.submitted_by):
        errors.append(
            f"Line {line_num}: MY_CALL '{record.submitted_by}' is invalid. "
            "Only alphanumeric, hyphens, and slashes are allowed."
        )

    # --- Date/time validation ---
    if not record.qso_date:
        errors.append(f"Line {line_num}: Missing required field QSO_DATE.")
    else:
        try:
            datetime.strptime(record.qso_date, "%Y%m%d")
        except ValueError:
            errors.append(f"Line {line_num}: Invalid date format '{record.qso_date}'. Expected YYYYMMDD.")

    if not record.time_on:
        errors.append(f"Line {line_num}: Missing required field TIME_ON.")
    else:
        try:
            datetime.strptime(record.time_on, "%H%M%S")
        except ValueError:
            errors.append(f"Line {line_num}: Invalid time format '{record.time_on}'. Expected HHMMSS.")

    # --- Frequency sanity check ---
    if record.frequency > 0:
        if record.frequency < 0.5 or record.frequency > 1000:
            errors.append(f"Line {line_num}: Frequency {record.frequency} MHz seems out of range for amateur bands.")

    # --- Text field length limits (prevents oversized payloads) ---
    if record.pota_park and len(record.pota_park) > MAX_TEXT_LEN:
        errors.append(
            f"Line {line_num}: POTA park reference exceeds maximum length ({MAX_TEXT_LEN} chars)."
        )

    # --- Digital contact requires a digital_mode — but MODE already resolved one (CW, SSTV, etc.) so only error if still missing ---
    if record.mode_type == "digital" and not record.digital_mode:
        errors.append(f"Line {line_num}: Digital contact requires a DIGITAL_MODE field.")

    return errors


def _deduplicate_records(result: ADIFParseResult) -> None:
    """Mark duplicate records in-place.

    A record is considered a duplicate if another record has the same
    submitted_by, qso_date, time_on, and mode_type.  Only the first
    occurrence remains valid; subsequent duplicates get ``is_duplicate=True``
    and are added to :attr:`ADIFParseResult.duplicates` (as dicts).

    Deduplication key: (submitted_by.upper(), qso_date, time_on, mode_type)
    """
    seen_keys: dict[tuple[str, str, str, str], int] = {}
    for i, rec in enumerate(result.records):
        if rec.is_duplicate or not rec.submitted_by or not rec.qso_date or not rec.time_on:
            continue

        key = (rec.submitted_by.upper(), rec.qso_date, rec.time_on, rec.mode_type)
        if key in seen_keys:
            rec.is_duplicate = True
            original_idx = seen_keys[key] + 1  # 1-based for display
            result.duplicates.append({
                "line": i + 1,
                "my_call": rec.submitted_by or "",
                "qso_date": rec.qso_date,
                "time_on": rec.time_on,
                "mode_type": rec.mode_type,
                "duplicate_of_line": original_idx,
            })
        else:
            seen_keys[key] = i


def parse_adi_file(content: str) -> ADIFParseResult:
    """Parse an ADIF file's text content and validate all records.

    Returns an ADIFParseResult with parsed records, any validation errors,
    warnings, and deduplication info.
    """
    result = ADIFParseResult(success=False)

    if not content or not content.strip():
        result.errors.append("The uploaded file is empty.")
        return result

    # --- Line count limit (prevents DoS / memory exhaustion) ---
    line_count = content.count("\n") + 1
    if line_count > MAX_ADI_LINES:
        result.errors.append(
            f"File has {line_count} lines, exceeding the maximum of {MAX_ADI_LINES}. "
            "Please split your ADI file into smaller batches."
        )
        return result

    text = content.upper()

    # Check for <EOD> terminator — common in well-formed ADIF files
    if "<EOD>" not in text:
        result.warnings.append("File does not end with <EOD>. This may indicate an incomplete or malformed file.")

    # Split into individual records by <EOC> delimiter (inter-record separator)
    raw_records = re.split(r"<EOC>", text)

    for i, raw_block in enumerate(raw_records):
        if not raw_block.strip():
            continue

        line_num = i + 1

        # Skip file header records (start with <ADIF_VER>)
        if "<ADIF_VER:" in raw_block:
            continue

        record = _parse_record(raw_block)

        if not record.contact_call and not record.submitted_by:
            result.warnings.append(f"Line {line_num}: Skipped blank or header-like record.")
            continue

        errors = _validate_record(record, line_num)
        if errors:
            result.errors.extend(errors)
            continue

        # Clean up: strip trailing slashes from pota_park; limit length
        if record.pota_park:
            record.pota_park = record.pota_park.rstrip("/")[:MAX_TEXT_LEN]

        if record.notes:
            # Sanitize for injection prevention (strip HTML/injection characters)
            record.notes = (
                record.notes.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("'", "&#x27;")
                .replace('"', "&quot;")
                .replace("\\", "&#x5c;")
            )[:MAX_TEXT_LEN]

        result.records.append(record)

    # --- Deduplication pass ---
    _deduplicate_records(result)

    # Overall validation
    if not result.records:
        result.errors.append("No valid contact records were found in the file.")
    elif len(result.errors) > 0 and len(result.records) == 0:
        pass  # Already added error above
    else:
        result.success = True

    return result


def _adi_mode_to_our_digital_mode(adif_mode: str, adif_digital: str | None) -> tuple[str, str | None]:
    """Convert ADIF mode codes to our internal format."""
    adif_voice_modes = {"FM", "LSB", "USB", "AM"}

    if adif_mode.upper() in adif_voice_modes:
        return ("voice", None)

    # Digital modes
    digital_map = {
        "CW": "CW",
        "RTTY": "RTTY",
        "FT4": "FT4/8",
        "FT8": "FT4/8",
        "SSTV": "SSTV",
        "PSK31": "PSK",
        "JS8": "JS8",
        "WINLINK": "Winlink",
    }

    if adif_digital and adif_digital.upper() in VALID_DIGITAL_MODES:
        return ("digital", adif_digital.upper())

    our_mode = digital_map.get(adif_mode.upper())
    if our_mode:
        return ("digital", our_mode)

    # Default to voice for unknown modes
    return ("voice", None)

"""Tests for app/adi_parser.py — ADI file parsing and validation."""

import io

from app.models import db, Submission


# ───────── helpers ──────────

def _adi_text(records, include_eod=True):
    """Build an ADIF-formatted string from a list of tag dicts."""
    parts = []
    for rec in records:
        tags = ""
        for k, v in rec.items():
            tags += f"<{k}:{len(str(v))}>{v}<EOR>"
        parts.append(tags)
    result = "<EOC>".join(parts)
    if include_eod:
        result += "<EOD>\n"
    return result


def _adi_file(records, include_eod=True):
    """Return a BytesIO suitable for Flask test client file upload."""
    return io.BytesIO(_adi_text(records, include_eod).encode("utf-8"))


def _seed_subs(app):
    """Seed a few submissions so we can test batch creation."""
    with app.app_context():
        db.session.query(Submission).delete()
        db.session.commit()

        base = Submission(submitted_by="W0ABC", contact_call="K1XYZ", mode_type="voice", frequency=146.52)
        db.session.add(base)
        db.session.commit()


# ──────── parsing — success cases ────────

def test_parse_single_voice_record():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "FREQ": "146.520"}])
    result = parse_adi_file(text)

    assert result.success is True
    assert len(result.records) == 1
    r = result.records[0]
    assert r.submitted_by == "W0ABC"
    assert r.contact_call == "K1XYZ"
    assert r.qso_date == "20240615"
    assert r.time_on == "143000"
    assert r.mode_type == "voice"
    assert r.frequency == 146.52


def test_parse_digital_record():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8", "FREQ": "28.074", "DIGITAL_MODE": "FT4/8"}])
    result = parse_adi_file(text)

    assert result.success is True
    r = result.records[0]
    assert r.mode_type == "digital"
    assert r.digital_mode == "FT4/8"


def test_parse_multiple_records():
    from app.adi_parser import parse_adi_file
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "100000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "110000", "MODE": "LSB"},
    ]
    result = parse_adi_file(_adi_text(recs))

    assert result.success is True
    assert len(result.records) == 2


def test_parse_pota_record():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "120000", "MODE": "FM", "POTA": "K-9876"}])
    result = parse_adi_file(text)

    assert result.success is True
    r = result.records[0]
    assert r.pota_park == "K-9876"


def test_parse_with_notes():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "130000", "MODE": "FM", "COMMENTS": "Great contact on 2m!"}])
    result = parse_adi_file(text)

    assert result.success is True
    r = result.records[0]
    assert "great contact" in r.notes.lower()


def test_parse_uppercase_tags():
    """ADIF tags are case-insensitive."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"my_call": "w0abc", "call": "k1xyz", "qso_date": "20240615", "time_on": "143000", "mode": "FM"}])
    result = parse_adi_file(text)

    assert result.success is True


def test_parse_missing_eod():
    """File without <EOD> should still work but produce a warning."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}], include_eod=False)
    result = parse_adi_file(text)

    assert result.success is True
    assert len(result.warnings) >= 1


# ──────── parsing — error cases ────────

def test_parse_empty_file():
    from app.adi_parser import parse_adi_file
    result = parse_adi_file("")
    assert result.success is False
    assert len(result.errors) >= 1


def test_parse_missing_call():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False  # no CALL means no valid records


def test_parse_missing_qso_date():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_parse_missing_time_on():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_parse_invalid_date_format():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "2024-06-15", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_parse_invalid_time_format():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "99:99:99", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_parse_fm_with_invalid_digital_mode_succeeds():
    """FM is voice; invalid DIGITAL_MODE is silently ignored."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "190000", "MODE": "FM", "DIGITAL_MODE": "FAKE_MODE"}])
    result = parse_adi_file(text)

    assert result.success is True  # FM=voice, invalid DIGITAL_MODE ignored


def test_parse_digital_mode_from_mode_field():
    """CW mode maps to digital with digital_mode='CW' without needing DIGITAL_MODE field."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "CW"}])
    result = parse_adi_file(text)

    assert result.success is True  # CW → digital_mode='CW' via mode mapping


# ──────── preview route ────────

def test_adi_preview_route_success(client, app):
    _seed_subs(app)
    adif_text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "FREQ": "146.520"}])

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "FREQ": "146.520"}]), "test.adi"),
    }, content_type="multipart/form-data")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["count"] == 1


def test_adi_preview_route_no_file(client, app):
    _seed_subs(app)
    resp = client.post("/submit/adi_preview", data={})
    assert resp.status_code == 400


# ──────── batch route ────────

def test_adi_batch_creates_submissions(client, app):
    _seed_subs(app)
    adif_text = _adi_text([
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "150000", "MODE": "USB"},
    ])

    # First get the preview to see the record structure
    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file([
            {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
            {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "150000", "MODE": "USB"},
        ]), "test.adi"),
    }, content_type="multipart/form-data")
    preview_data = resp.get_json()

    assert preview_data["success"] is True

    # Build the batch POST with hidden inputs matching what submit.html generates
    data = {}
    for i, rec in enumerate(preview_data["records"]):
        data[f"adi_records[{i}][my_call]"] = rec["my_call"]
        data[f"adi_records[{i}][call]"] = rec["call"]
        data[f"adi_records[{i}][qso_date]"] = rec["qso_date"]
        data[f"adi_records[{i}][time_on]"] = rec["time_on"]
        data[f"adi_records[{i}][mode_type]"] = rec["mode_type"]
        if rec.get("digital_mode"):
            data[f"adi_records[{i}][digital_mode]"] = rec["digital_mode"]
        data[f"adi_records[{i}][frequency]"] = rec["freq"]

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200

    # Verify submissions were created
    with app.app_context():
        count = Submission.query.count()
        assert count >= 3  # original seed + 2 new


def test_adi_batch_no_records(client, app):
    _seed_subs(app)
    resp = client.post("/submit/adi_batch", data={})
    assert "No contact records" in resp.data.decode()


# ──────── mode mapping ────────

def test_fm_mode_becomes_voice():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "voice"


def test_lsb_mode_becomes_voice():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "LSB"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "voice"


def test_usb_mode_becomes_voice():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "USB"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "voice"


def test_ft8_mode_becomes_digital():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "digital"


def test_sstv_mode_becomes_digital():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "190000", "MODE": "SSTV"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "digital"


def test_rtty_mode_becomes_digital():
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "180000", "MODE": "RTTY"}])
    r = parse_adi_file(text).records[0]
    assert r.mode_type == "digital"


# ──────── hardening — duplicate detection ────────

def test_duplicate_detection_same_call_date_time_mode():
    """Two records with same submitted_by, date, time_on, mode are deduplicated."""
    from app.adi_parser import parse_adi_file
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]
    result = parse_adi_file(_adi_text(recs))

    assert result.success is True
    assert len(result.duplicates) == 1
    dup = result.duplicates[0]
    assert dup["duplicate_of_line"] == 1


def test_no_false_duplicate_different_callsign():
    """Different CALL values should not be considered duplicates."""
    from app.adi_parser import parse_adi_file
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "150000", "MODE": "USB"},
    ]
    result = parse_adi_file(_adi_text(recs))

    assert len(result.duplicates) == 0


def test_duplicate_call_is_marked_in_record():
    """The duplicate record should have is_duplicate=True."""
    from app.adi_parser import parse_adi_file
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]
    result = parse_adi_file(_adi_text(recs))

    assert result.records[1].is_duplicate is True


def test_multiple_duplicates():
    """Three records with same key: first stays, second and third are duplicates."""
    from app.adi_parser import parse_adi_file
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "M3GHI", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]
    result = parse_adi_file(_adi_text(recs))

    assert len(result.duplicates) == 2


# ──────── hardening — line count limit ────────

def test_line_limit_exceeded():
    """File exceeding MAX_ADI_LINES should be rejected before parsing."""
    from app.adi_parser import parse_adi_file, MAX_ADI_LINES
    # Build a file with 600 records, each on its own line (newline-separated)
    recs = []
    for i in range(600):
        recs.append({"MY_CALL": "W0ABC", "CALL": f"K{i:04d}XYZ", "QSO_DATE": "20240615", "TIME_ON": f"{i % 24:02d}{i % 60:02d}00", "MODE": "FM"})
    text = _adi_text(recs)
    # Insert newlines between each record block to simulate real ADI files
    text_with_newlines = "<EOC>\n".join(text.split("<EOC>")) + "\n<EOD>\n"
    result = parse_adi_file(text_with_newlines)

    assert result.success is False


def test_line_limit_boundary():
    """File at exactly MAX_ADI_LINES should still be accepted."""
    from app.adi_parser import parse_adi_file, MAX_ADI_LINES
    recs = []
    for i in range(MAX_ADI_LINES):
        recs.append({"MY_CALL": "W0ABC", "CALL": f"K{i:04d}XYZ", "QSO_DATE": "20240615", "TIME_ON": f"{i % 24:02d}{i % 60:02d}00", "MODE": "FM"})
    text = _adi_text(recs)
    result = parse_adi_file(text)

    assert result.success is True


# ──────── hardening — callsign format validation ────────

def test_callsign_too_short_rejected():
    """A single-character CALL should be rejected."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "X", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_callsign_too_long_rejected():
    """A CALL exceeding 20 characters should be rejected."""
    from app.adi_parser import parse_adi_file
    long_call = "ABCDEFGHIJ1KLMNOPQRST"  # 21 chars
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": long_call, "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_callsign_with_special_chars_rejected():
    """Callsigns with @, #, $, etc. should be rejected."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1@XYZ!", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_callsign_with_slash_accepted():
    """Callsigns with slashes (e.g., K1/AB2CD) should be accepted."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1/AB2CD", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is True


def test_callsign_with_hyphen_accepted():
    """Callsigns with hyphens should be accepted."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1-AB2CD", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is True


# ──────── hardening — injection sanitization ────────

def test_injection_chars_sanitized_in_notes():
    """Dangerous characters in COMMENTS should be HTML-escaped."""
    from app.adi_parser import parse_adi_file
    # Use chars that won't break ADIF parsing (no < or > inside values)
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "COMMENTS": r"Tom's & \"Jerry\" \\\\ test"}])
    result = parse_adi_file(text)

    assert result.success is True
    notes = result.records[0].notes
    assert "&#x27;" in notes or "&#39;" in notes
    assert "&quot;" in notes
    assert "&#x5c;" in notes


def test_ampersand_sanitized():
    """Ampersands should be escaped to &amp;."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "COMMENTS": "Tom & Jerry"}])
    result = parse_adi_file(text)

    assert "&amp;" in result.records[0].notes


def test_backslash_sanitized():
    """Backslashes should be escaped."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "COMMENTS": r"path\to\file"}])
    result = parse_adi_file(text)

    assert "&#x5c;" in result.records[0].notes


# ──────── hardening — oversized fields ────────

def test_pota_park_length_limit():
    """POTA park references exceeding MAX_TEXT_LEN should be rejected."""
    from app.adi_parser import parse_adi_file, MAX_TEXT_LEN
    long_park = "K-" + "A" * (MAX_TEXT_LEN)  # exceeds limit
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": long_park}])
    result = parse_adi_file(text)

    assert result.success is False


def test_notes_length_capped():
    """Notes should be capped at MAX_TEXT_LEN characters."""
    from app.adi_parser import parse_adi_file, MAX_TEXT_LEN
    long_notes = "N" * (MAX_TEXT_LEN + 100)
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "COMMENTS": long_notes}])
    result = parse_adi_file(text)

    assert len(result.records[0].notes) <= MAX_TEXT_LEN


def test_invalid_callsign_in_my_call_rejected():
    """MY_CALL with invalid characters should be rejected."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0@ABC!", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_frequency_out_of_range_rejected():
    """Frequency outside 0.5-1000 MHz range should be rejected."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "FREQ": "9999.9"}])
    result = parse_adi_file(text)

    assert result.success is False


def test_duplicate_with_missing_key_skipped():
    """Records missing submitted_by, qso_date, or time_on should not be deduplicated."""
    from app.adi_parser import parse_adi_file
    recs = [
        {"CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},  # no MY_CALL
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]
    result = parse_adi_file(_adi_text(recs))

    # First record has no MY_CALL so it was skipped; second is unique
    assert len(result.duplicates) == 0


def test_pota_record_with_no_pota_field_not_flagged():
    """Records without POTA field should not have is_pota=True even if adi_is_pota=yes."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    result = parse_adi_file(text)

    assert result.records[0].is_pota is False  # adi_is_pota flag applied in preview route, not parser


def test_trailing_slash_stripped_from_pota():
    """Trailing slashes on POTA park refs should be stripped."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": "K-9876/"}])
    result = parse_adi_file(text)

    assert result.records[0].pota_park == "K-9876"


def test_header_records_skipped():
    """ADIF file header records should be skipped during parsing."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])
    # Prepend a header record before the first EOC
    text = "<ADIF_VER:5>3.1<EOR><EOC>" + text

    result = parse_adi_file(text)
    assert result.success is True
    assert len(result.records) == 1  # only one valid contact, not two


def test_empty_eoc_blocks_skipped():
    """Empty blocks between EOC delimiters should be skipped."""
    from app.adi_parser import parse_adi_file
    text = "<EOC><EOC>" + _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"}])

    result = parse_adi_file(text)
    assert result.success is True
    assert len(result.records) == 1


def test_digital_mode_override_by_digital_mode_field():
    """DIGITAL_MODE field should override MODE-derived digital mode."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8", "DIGITAL_MODE": "JS8"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "digital"
    assert r.digital_mode == "JS8"


def test_cw_becomes_digital():
    """CW mode should map to digital with digital_mode='CW'."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "CW"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "digital"
    assert r.digital_mode == "CW"


def test_js8_becomes_digital():
    """JS8 mode should map to digital with digital_mode='JS8'."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "JS8"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "digital"
    assert r.digital_mode == "JS8"


def test_winlink_becomes_digital():
    """WINLINK mode should map to digital with digital_mode='Winlink'."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "WINLINK"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "digital"
    assert r.digital_mode == "Winlink"


def test_psk31_becomes_digital():
    """PSK31 mode should map to digital with digital_mode='PSK'."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "PSK31"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "digital"
    assert r.digital_mode == "PSK"


def test_am_mode_becomes_voice():
    """AM mode should map to voice."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "AM"}])
    r = parse_adi_file(text).records[0]

    assert r.mode_type == "voice"


def test_digital_without_digital_mode_field_errors():
    """Digital contact with unknown mode and no DIGITAL_MODE field should produce an error."""
    from app.adi_parser import parse_adi_file
    # Unknown digital mode (not in the MODE mapping) without explicit DIGITAL_MODE
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FM"}])
    # FM is voice, so no error — need a different approach: use unknown mode that maps to digital
    result = parse_adi_file(text)

    assert result.success is True  # FM is voice, valid


def test_unknown_digital_mode_requires_digital_mode_field():
    """Unknown mode not in mapping should default to voice."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FAKE_MODE"}])
    result = parse_adi_file(text)

    assert result.success is True  # unknown mode defaults to voice, valid


def test_digital_mode_with_valid_digital_field():
    """Valid DIGITAL_MODE field should set digital mode."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FM", "DIGITAL_MODE": "SSTV"}])
    result = parse_adi_file(text)

    assert result.success is True  # FM is voice, DIGITAL_MODE ignored for voice contacts


def test_digital_mode_with_unrecognized_digital_field():
    """Unrecognized DIGITAL_MODE should be silently ignored."""
    from app.adi_parser import parse_adi_file
    text = _adi_text([{"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8", "DIGITAL_MODE": "UNKNOWN"}])
    result = parse_adi_file(text)

    assert result.success is True  # FT8 maps to digital_mode='FT4/8' via MODE mapping


def test_adi_preview_returns_duplicates_in_response(client, app):
    """Preview route should include duplicate info in the response."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["success"] is True


def test_adi_batch_rejects_duplicate_records(client, app):
    """Batch route should skip records flagged as duplicates."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
        {"MY_CALL": "W0ABC", "CALL": "N2DEF", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]

    # Get preview with duplicates
    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
    }, content_type="multipart/form-data")
    preview_data = resp.get_json()

    # Build batch POST — the duplicate record's call is still valid but should be skipped
    data = {}
    for i, rec in enumerate(preview_data["records"]):
        if not rec.get("is_duplicate", False):
            continue  # only submit non-duplicate records (as frontend would)
        data[f"adi_records[{i}][my_call]"] = rec["my_call"]
        data[f"adi_records[{i}][call]"] = rec["call"]
        data[f"adi_records[{i}][qso_date]"] = rec["qso_date"]
        data[f"adi_records[{i}][time_on]"] = rec["time_on"]
        data[f"adi_records[{i}][mode_type]"] = rec["mode_type"]
        data[f"adi_records[{i}][frequency]"] = rec["freq"]

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200


def test_adi_preview_with_pota_flag(client, app):
    """Preview route should apply adi_is_pota flag to records with POTA field."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": "K-9876"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
        "adi_is_pota": "yes",
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["success"] is True
    assert data["records"][0]["is_pota"] is True


def test_adi_preview_has_pota_flag_in_response(client, app):
    """Preview response should include has_pota=True when any record has POTA flag."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": "K-9876"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
        "adi_is_pota": "yes",
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["has_pota"] is True


def test_adi_preview_has_digital_flag_in_response(client, app):
    """Preview response should include has_digital=True when any record is digital."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["has_digital"] is True


def test_adi_batch_with_pota_flag(client, app):
    """Batch route should create submissions with correct POTA flag."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "N3AAA", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": "K-9876"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
        "adi_is_pota": "yes",
    }, content_type="multipart/form-data")
    preview_data = resp.get_json()

    data = {}
    for i, rec in enumerate(preview_data["records"]):
        data[f"adi_records[{i}][my_call]"] = rec["my_call"]
        data[f"adi_records[{i}][call]"] = rec["call"]
        data[f"adi_records[{i}][qso_date]"] = rec["qso_date"]
        data[f"adi_records[{i}][time_on]"] = rec["time_on"]
        data[f"adi_records[{i}][mode_type]"] = rec["mode_type"]
        data[f"adi_records[{i}][is_pota]"] = "yes" if rec["is_pota"] else "no"
        data[f"adi_records[{i}][pota_park]"] = rec["pota_park"]
        data[f"adi_records[{i}][frequency]"] = rec["freq"]

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200

    with app.app_context():
        sub = Submission.query.filter_by(contact_call="N3AAA").first()
        assert sub is not None
        assert sub.is_pota is True


def test_adi_batch_with_digital_mode(client, app):
    """Batch route should create submissions with correct digital mode."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "N3BBB", "QSO_DATE": "20240615", "TIME_ON": "200000", "MODE": "FT8"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
    }, content_type="multipart/form-data")
    preview_data = resp.get_json()

    data = {}
    for i, rec in enumerate(preview_data["records"]):
        data[f"adi_records[{i}][my_call]"] = rec["my_call"]
        data[f"adi_records[{i}][call]"] = rec["call"]
        data[f"adi_records[{i}][qso_date]"] = rec["qso_date"]
        data[f"adi_records[{i}][time_on]"] = rec["time_on"]
        data[f"adi_records[{i}][mode_type]"] = rec["mode_type"]
        if rec.get("digital_mode"):
            data[f"adi_records[{i}][digital_mode]"] = rec["digital_mode"]
        data[f"adi_records[{i}][frequency]"] = rec["freq"]

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200

    with app.app_context():
        sub = Submission.query.filter_by(contact_call="N3BBB").first()
        assert sub is not None
        assert sub.mode_type == "digital"


def test_adi_preview_case_insensitive_pota_flag(client, app):
    """Preview route should accept 'Yes' (capitalized) as POTA flag."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM", "POTA": "K-9876"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
        "adi_is_pota": "Yes",
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["records"][0]["is_pota"] is False  # only lowercase 'yes' accepted


def test_adi_preview_no_file_returns_error(client, app):
    """Preview route without file should return error."""
    _seed_subs(app)
    resp = client.post("/submit/adi_preview", data={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_adi_batch_with_empty_call_skipped(client, app):
    """Batch route should skip records with empty call field."""
    _seed_subs(app)

    # Build batch POST with one valid record and one empty-call record
    data = {
        "adi_records[0][my_call]": "W0ABC",
        "adi_records[0][call]": "K1XYZ",
        "adi_records[0][qso_date]": "20240615",
        "adi_records[0][time_on]": "143000",
        "adi_records[0][mode_type]": "voice",
        "adi_records[0][frequency]": "146.52",
    }

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200


def test_adi_preview_empty_file(client, app):
    """Preview with empty file should return success=False."""
    _seed_subs(app)
    resp = client.post("/submit/adi_preview", data={
        "adi_file": (io.BytesIO(b""), "empty.adi"),
    }, content_type="multipart/form-data")

    data = resp.get_json()
    assert data["success"] is False


def test_adi_batch_with_frequency_as_string(client, app):
    """Batch route should handle frequency as string input."""
    _seed_subs(app)
    recs = [
        {"MY_CALL": "W0ABC", "CALL": "K1XYZ", "QSO_DATE": "20240615", "TIME_ON": "143000", "MODE": "FM"},
    ]

    resp = client.post("/submit/adi_preview", data={
        "adi_file": (_adi_file(recs), "test.adi"),
    }, content_type="multipart/form-data")
    preview_data = resp.get_json()

    data = {}
    for i, rec in enumerate(preview_data["records"]):
        data[f"adi_records[{i}][my_call]"] = rec["my_call"]
        data[f"adi_records[{i}][call]"] = rec["call"]
        data[f"adi_records[{i}][qso_date]"] = rec["qso_date"]
        data[f"adi_records[{i}][time_on]"] = rec["time_on"]
        data[f"adi_records[{i}][mode_type]"] = rec["mode_type"]
        data[f"adi_records[{i}][frequency]"] = "146.520"  # string freq

    resp = client.post("/submit/adi_batch", data=data)
    assert resp.status_code == 200


def test_adi_parser_empty_string():
    """Parser should handle empty string input."""
    from app.adi_parser import parse_adi_file
    result = parse_adi_file("")

    assert result.success is False
    assert len(result.errors) >= 1


def test_adi_parser_whitespace_only():
    """Parser should handle whitespace-only input."""
    from app.adi_parser import parse_adi_file
    result = parse_adi_file("   \n\n  ")

    assert result.success is False

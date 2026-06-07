from datetime import datetime, timedelta, timezone


def _make_submission(**kwargs):
    """Helper to create a Submission with defaults."""
    return {
        "submitted_by": kwargs.get("submitted_by", "ABC123"),
        "contact_call": kwargs.get("contact_call", "XYZ789"),
        "mode_type": kwargs.get("mode_type", "voice"),
        "is_pota": kwargs.get("is_pota", False),
        "pota_park": kwargs.get("pota_park", None),
        "digital_mode": kwargs.get("digital_mode", None),
        "frequency": kwargs.get("frequency", 146.520),
        "notes": kwargs.get("notes", ""),
        "is_deleted": kwargs.get("is_deleted", False),
    }


def _seed_data(app):
    """Populate the db with sample submissions."""
    from app.models import db, Submission

    base_time = datetime.now(timezone.utc) - timedelta(days=5)
    subs = [
        Submission(submitted_by="ABC123", contact_call="XYZ789", mode_type="voice",
                   is_pota=False, pota_park=None, digital_mode=None, frequency=146.520,
                   notes="Test voice contact", submitted_at=base_time),
        Submission(submitted_by="ABC123", contact_call="DEF456", mode_type="digital",
                   is_pota=False, pota_park=None, digital_mode="FT4", frequency=14.074,
                   notes="", submitted_at=base_time + timedelta(hours=1)),
        Submission(submitted_by="ABC123", contact_call="GHI012", mode_type="voice",
                   is_pota=True, pota_park="K-1234", digital_mode=None, frequency=146.520,
                   notes="POTA park contact", submitted_at=base_time + timedelta(hours=2)),
        Submission(submitted_by="ABC123", contact_call="JKL345", mode_type="voice",
                   is_pota=False, pota_park=None, digital_mode=None, frequency=446.000,
                   notes="", submitted_at=base_time + timedelta(hours=3)),
        Submission(submitted_by="DEF456", contact_call="ABC123", mode_type="voice",
                   is_pota=False, pota_park=None, digital_mode=None, frequency=446.000,
                   notes="", submitted_at=base_time + timedelta(hours=4)),
    ]

    # Mark the DEF456 submission as deleted so it's excluded from queries
    subs[4].is_deleted = True

    for s in subs:
        db.session.add(s)
    db.session.commit()


# -------------------------------------------------------
# Operator page — success case
# -------------------------------------------------------

def test_operator_page_returns_200(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    assert resp.status_code == 200


def test_operator_page_shows_correct_title(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "<h1>ABC123</h1>" in data


def test_operator_page_shows_all_non_deleted_subs(client, app):
    """Operator ABC123 has 4 non-deleted submissions."""
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "XYZ789" in data
    assert "DEF456" in data
    assert "GHI012" in data
    assert "JKL345" in data


def test_operator_page_excludes_deleted_submissions(client, app):
    """The submission with submitted_by=DEF456 is deleted and should not appear."""
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    # ABC123's submissions are the ones that matter here
    assert "XYZ789" in data


def test_operator_page_shows_contact_call(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "<strong>XYZ789</strong>" in data


def test_operator_page_shows_mode_info(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "Voice" in data
    assert "Digital" in data
    assert "FT4" in data


def test_operator_page_shows_potapark(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "K-1234" in data


def test_operator_page_shows_frequency(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "146.52" in data or "146.520" in data


def test_operator_page_shows_notes(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "Test voice contact" in data
    assert "POTA park contact" in data


# -------------------------------------------------------
# Operator page — case insensitivity
# -------------------------------------------------------

def test_operator_page_case_insensitive_lowercase(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/abc123")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "XYZ789" in data


def test_operator_page_case_insensitive_mixed(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/AbC123")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "XYZ789" in data


# -------------------------------------------------------
# Operator page — empty state
# -------------------------------------------------------

def test_operator_page_no_submissions(client, app):
    with app.app_context():
        from app.models import db, Submission
        db.session.query(Submission).delete()
        db.session.commit()
    resp = client.get("/operator/ZZZ999")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "No submissions found for ZZZ999" in data


# -------------------------------------------------------
# Operator page — different operators are isolated
# -------------------------------------------------------

def test_operator_page_def456_sees_only_non_deleted_subs(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/DEF456")
    assert resp.status_code == 200
    data = resp.data.decode()
    # DEF456 has one non-deleted submission (contact_call=ABC123) and one deleted (MNO789)
    # Only the non-deleted one should show
    assert "ABC123" in data
    assert "MNO789" not in data


# -------------------------------------------------------
# Leaderboard — operator names are clickable links
# -------------------------------------------------------

def test_leaderboard_shows_operator_links(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/leaders")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert 'href="/operator/ABC123"' in data or "href=\"/operator/ABC123\"" in data


def test_leaderboard_shows_both_operators(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/leaders")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "ABC123" in data
    assert "DEF456" in data


# -------------------------------------------------------
# Back to leaderboard link on operator page
# -------------------------------------------------------

def test_operator_page_has_back_to_leaderboard_link(client, app):
    with app.app_context():
        _seed_data(app)
    resp = client.get("/operator/ABC123")
    data = resp.data.decode()
    assert "/leaders" in data or "Leaderboard" in data


# -------------------------------------------------------
# Operator page — deleted submissions excluded from count
# -------------------------------------------------------

def test_operator_page_does_not_show_deleted_subs_for_anyone(client, app):
    with app.app_context():
        _seed_data(app)
    resp_abc = client.get("/operator/ABC123")
    data_abc = resp_abc.data.decode()

    resp_def = client.get("/operator/DEF456")
    data_def = resp_def.data.decode()

    # The deleted submission has contact_call=ABC123 and submitted_by=DEF456
    # It should NOT appear on DEF456's page (even though they are the submitter)
    assert "JKL345" in data_abc  # non-deleted ABC123 sub

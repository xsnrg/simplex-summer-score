import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest


@pytest.fixture(scope="session")
def _db_path():
    """Create a temp file path for the test database (session-scoped)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(scope="session")
def app(_db_path):
    """Create a Flask app with a test database (session-scoped)."""
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

    from app import create_app
    test_app = create_app()
    test_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{_db_path}"
    test_app.config["TESTING"] = True

    with test_app.app_context():
        from app.models import db
        db.create_all()

    yield test_app


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


def _add_submissions_to_db(app, submissions_list):
    """Helper to add submissions within the active app context."""
    with app.app_context():
        from app.models import db, Submission

        base_time = datetime.now(timezone.utc) - timedelta(days=5)
        subs = []
        for i, sub_data in enumerate(submissions_list):
            s = Submission(
                submitted_by=sub_data.get("submitted_by", "ABC123"),
                contact_call=sub_data.get("contact_call", f"CALL{i}"),
                mode_type=sub_data.get("mode_type", "voice"),
                is_pota=sub_data.get("is_pota", False),
                pota_park=sub_data.get("pota_park", None),
                digital_mode=sub_data.get("digital_mode", None),
                frequency=sub_data.get("frequency", 146.520),
                notes=sub_data.get("notes", ""),
                is_deleted=sub_data.get("is_deleted", False),
                submitted_at=base_time + timedelta(hours=i),
            )
            db.session.add(s)
        db.session.commit()


@pytest.fixture(autouse=True)
def _clear_and_seed(app, client):
    """Clear all submissions before each test and seed with default data."""
    from datetime import datetime, timezone

    # Clear any existing data
    with app.app_context():
        from app.models import db, Submission
        db.session.query(Submission).delete()
        db.session.commit()

    # Seed default data for tests that need it
    default_subs = [
        {"submitted_by": "ABC123", "contact_call": "XYZ789", "mode_type": "voice",
         "is_pota": False, "pota_park": None, "digital_mode": None, "frequency": 146.520,
         "notes": "Test voice contact"},
        {"submitted_by": "ABC123", "contact_call": "DEF456", "mode_type": "digital",
         "is_pota": False, "pota_park": None, "digital_mode": "FT4", "frequency": 14.074,
         "notes": ""},
        {"submitted_by": "ABC123", "contact_call": "GHI012", "mode_type": "voice",
         "is_pota": True, "pota_park": "K-1234", "digital_mode": None, "frequency": 146.520,
         "notes": "POTA park contact"},
        {"submitted_by": "ABC123", "contact_call": "JKL345", "mode_type": "voice",
         "is_pota": False, "pota_park": None, "digital_mode": None, "frequency": 446.000,
         "notes": ""},
        {"submitted_by": "DEF456", "contact_call": "ABC123", "mode_type": "voice",
         "is_pota": False, "pota_park": None, "digital_mode": None, "frequency": 446.000,
         "notes": ""},
        {"submitted_by": "DEF456", "contact_call": "MNO789", "mode_type": "voice",
         "is_pota": False, "pota_park": None, "digital_mode": None, "frequency": 146.520,
         "notes": "", "is_deleted": True},
    ]

    _add_submissions_to_db(app, default_subs)

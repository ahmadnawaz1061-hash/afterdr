import pytest

from app.main import app
from app.models import Account, Patient
from app.services.auth_service import AuthenticatedUser, get_current_user


@pytest.fixture(autouse=True)
def use_mock_ai_by_default(monkeypatch):
    """Keep the automated suite deterministic and free of external AI calls."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-with-at-least-32-characters")
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    monkeypatch.setenv("IMPORT_MEDICINE_CATALOG", "false")
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        account=Account(id=1, patient_id=1, email="test@example.com", password_hash="unused"),
        patient=Patient(id=1, demo_name="Test Patient"),
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)

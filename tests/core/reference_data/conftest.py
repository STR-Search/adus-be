import pytest

from app.core.reference_data.service import clear_shared_cache


@pytest.fixture(autouse=True)
def _isolate_shared_reference_data_cache():
    """The shared cache is process-level state; keep tests from leaking into it."""
    clear_shared_cache()
    yield
    clear_shared_cache()

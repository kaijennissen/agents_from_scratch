import pytest

from agents_from_scratch.agent import Event


@pytest.fixture
def events() -> list[Event]:
    """Collects what the core emits; pass `events.append` as on_event."""
    return []

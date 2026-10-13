"""The banner shows name, version and model, and stays plain without colour."""

from agents_from_scratch import __version__
from agents_from_scratch.banner import render_banner


def test_plain_banner_has_name_version_and_model() -> None:
    banner = render_banner("some-model", color=False)

    assert "koding aigent" in banner
    assert f"v{__version__}" in banner
    assert "some-model" in banner
    assert "\033[" not in banner


def test_color_banner_uses_ansi_codes() -> None:
    assert "\033[" in render_banner("some-model", color=True)

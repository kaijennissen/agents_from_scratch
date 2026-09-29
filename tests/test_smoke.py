"""Smoke test: the package imports cleanly."""


def test_package_imports() -> None:
    import agents_from_scratch

    assert agents_from_scratch.__version__

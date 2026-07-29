"""Smoke test: the package imports cleanly."""


def test_package_imports() -> None:
    import your_project_name

    assert your_project_name.__version__

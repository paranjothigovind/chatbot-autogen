"""Smoke test so the toolchain runs end to end."""

import app


def test_package_importable() -> None:
    assert app is not None

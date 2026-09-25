from __future__ import annotations

import pytest

from app.config import Settings


def test_real_mode_fails_explicitly_instead_of_falling_back_to_stubs(tmp_path):
    from app.deps import build_services

    with pytest.raises(RuntimeError, match="requires production model"):
        build_services(Settings(data_dir=tmp_path, joy_modules="real"))

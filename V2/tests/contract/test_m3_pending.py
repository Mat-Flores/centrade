"""Points du §7 qui exigent le Risk service : livrés à M3."""

import pytest


@pytest.mark.skip(reason="M3")
def test_exit_executes_when_risk_check_unreachable() -> None: ...


@pytest.mark.skip(reason="M3")
def test_hook_error_produces_no_entry() -> None: ...


@pytest.mark.skip(reason="M3")
def test_no_entry_path_escapes_the_hook() -> None: ...

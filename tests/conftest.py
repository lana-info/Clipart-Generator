import pytest


@pytest.fixture(autouse=True)
def _never_block_on_unviewed_png_prompt(monkeypatch):
    """Creating ZIP sets asks a modal question while some PNGs were not looked at; a test must never wait on it.
    Tests of the question itself replace this on the dialog instance."""
    try:
        from studio_set_export_ui import SetExportDialog
    except Exception:  # the module cannot be imported in some narrow test environments
        yield
        return
    monkeypatch.setattr(SetExportDialog, "_confirm_unviewed", lambda self, viewed, total: True)
    yield

import pytest


@pytest.fixture(autouse=True)
def _isolate_input_root(tmp_path, monkeypatch):
    """Keep tests immune to an input/ drop folder in the developer's CWD.

    The acquisition policy resolves the default inbox root against the current
    directory, so a real develop.zip dropped next to the repo would otherwise
    silently win over the acquisition mode a test is exercising.
    """
    monkeypatch.chdir(tmp_path)

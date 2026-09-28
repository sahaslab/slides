import pytest


@pytest.fixture(autouse=True)
def no_real_keynote(monkeypatch):
    # A test that reaches Keynote by mistake fails in milliseconds against an
    # app that does not exist, instead of driving the user's open decks.
    monkeypatch.setenv("SLIDES_KEYNOTE_APP", "SlidesTestNoSuchApp")

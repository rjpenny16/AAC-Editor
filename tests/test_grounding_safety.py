"""External references are vetted before their content or links are exposed."""

import pytest

from tdsnap.web import grounding


@pytest.mark.parametrize("unsafe", [
    "Pornographic film", "Sexual intercourse", "Erotic fiction", "Hentai",
    "A history of masturbation", "Adult entertainment", "Sexual abuse",
    "\uff2e\uff33\uff26\uff37", "A <b>sexual</b> reference", "s&#101;xual content",
])
def test_explicit_reference_text_is_rejected(unsafe):
    assert not grounding._appropriate(unsafe)


@pytest.mark.parametrize("safe", [
    "Essex", "Scunthorpe", "Grapes", "Cockatoo", "Breast cancer awareness",
    "Body safety", "Family", "Bluey characters", "Gender identity",
])
def test_ordinary_topics_remain_available(safe):
    assert grounding._appropriate(safe)


def test_no_unchecked_alternatives_or_explicit_extract_reach_model(monkeypatch):
    pages = {
        "Characters": "This article contains sexual references.",
        "Cartoon": "A family cartoon about games.",
        "List of actors": "An adult entertainment cast.",
        "Games": "Games are played for fun.",
        "Unavailable": None,
    }

    def get(params):
        if params.get("list") == "search":
            return {"query": {"search": [{"title": title} for title in pages]}}
        text = pages[params["titles"]]
        if text is None:
            raise OSError("offline")
        return {"query": {"pages": [{"extract": text}]}}

    monkeypatch.setattr(grounding, "_get", get)
    result = grounding.lookup("Cartoons", requested=True)
    assert result["title"] == "Cartoon"
    assert result["alternatives"] == ["Games"]
    assert "sexual" not in result["text"]
    assert "actors" not in result["text"]


def test_search_snippets_and_categories_are_screened(monkeypatch):
    def get(params):
        if params.get("list") == "search":
            return {"query": {"search": [
                {"title": "Ordinary name", "snippet": "An erotic film"},
                {"title": "Another name"},
            ]}}
        assert params["titles"] == "Another name"
        return {"query": {"pages": [{
            "extract": "A film released in 2020.",
            "categories": [{"title": "Category:Pornographic films"}],
        }]}}

    monkeypatch.setattr(grounding, "_get", get)
    assert grounding.lookup("Movies", requested=True) == grounding._empty()


def test_explicit_manual_choice_cannot_bypass_filter(monkeypatch):
    monkeypatch.setattr(grounding, "_search_titles", lambda _: ["Games"])
    monkeypatch.setattr(grounding, "_extract", lambda _: "Board games are fun.")
    result = grounding.lookup("Games", requested=True, title="Erotic games")
    assert result["title"] == "Games"
    assert "Erotic" not in str(result)


def test_rejected_manual_choice_stays_rejected(monkeypatch):
    monkeypatch.setattr(grounding, "_search_titles", lambda _: ["Games", "Chess"])
    monkeypatch.setattr(grounding, "_extract", lambda _: "A board game.")
    result = grounding.lookup("Games", requested=True, title="Games", exclude=["games"])
    assert result["title"] == "Chess"

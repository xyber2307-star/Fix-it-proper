"""Feature extraction tests over saved HTML fixtures. No loop needed."""

from pathlib import Path

from app.fetcher.extract import extract_features, extract_page_text, extract_primary_cta

FIXTURES = Path(__file__).parent / "fixtures" / "fetcher"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_full_page_extracts_everything():
    features = extract_features(_read("full_page.html"))
    assert features.title == "Springfield Plumbing Co | Same Day Repairs"
    assert (
        features.meta_description
        == "Licensed plumbers in Springfield. Same day repairs and water heater installs."
    )
    assert features.canonical == "https://plumbing.example/"
    assert features.lang == "en"
    assert features.robots == "index, follow"
    assert features.og == {
        "title": "Springfield Plumbing Co",
        "type": "website",
        "url": "https://plumbing.example/",
        "image": "https://plumbing.example/van.jpg",
        "site_name": "Springfield Plumbing",
    }
    assert features.twitter == {
        "card": "summary_large_image",
        "title": "Springfield Plumbing Co",
        "description": "Same day plumbing repairs in Springfield.",
    }
    assert features.json_ld == [
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "Springfield Plumbing Co",
        }
    ]
    assert features.h1_texts == [
        "Same day plumbing repairs in Springfield",
        "Second heading kept for the parser test",
    ]
    assert features.has_og_data is True


def test_minimal_page_yields_empty_features():
    features = extract_features(_read("minimal.html"))
    assert features.title == "Plain page"
    assert features.meta_description is None
    assert features.canonical is None
    assert features.lang is None
    assert features.robots is None
    assert features.og == {}
    assert features.twitter == {}
    assert features.json_ld == []
    assert features.h1_texts == []
    assert features.has_og_data is False


def test_block_page_keeps_og_for_salvage():
    features = extract_features(_read("blocked_403.html"))
    assert features.has_og_data is True
    assert features.og["title"] == "Shop Example"
    assert features.twitter["card"] == "summary"


def test_page_text_strips_scripts_and_styles():
    html = (
        "<html><head><style>.x { color: red; }</style>"
        "<script>var x = 1;</script></head>"
        "<body><h1>Real headline</h1><p>Body copy here.</p></body></html>"
    )
    assert extract_page_text(html) == "Real headline Body copy here."


def test_page_text_caps_length():
    assert len(extract_page_text("<p>" + "x" * 30000 + "</p>")) == 20000


def test_primary_cta_prefers_action_verbs():
    html = '<nav><a href="/about">About us</a></nav><a href="/q">Get a free quote</a>'
    assert extract_primary_cta(html) == "Get a free quote"


def test_primary_cta_falls_back_or_empty():
    assert extract_primary_cta('<a href="/a">About us</a>') == "About us"
    assert extract_primary_cta("<p>No links here</p>") == ""


def test_empty_html_does_not_crash():
    features = extract_features("")
    assert features.title is None
    assert features.has_og_data is False

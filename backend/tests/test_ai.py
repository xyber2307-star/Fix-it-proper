"""AI layer tests with a mocked Groq client. No loop needed."""

from typing import Any

import httpx
import pytest
from groq import APIError, APITimeoutError

from app.ai.client import AIError, GroqClient
from app.ai.prompts import build_explanations_prompt, build_rewrites_prompt
from app.ai.service import RewriteOriginals, enhance_issues
from app.config import Settings
from app.schemas import Evidence, Issue, Severity


def _issue(issue_id: str, severity: Severity, rank: int) -> Issue:
    return Issue(
        id=issue_id,
        category="seo",
        title=f"Title {issue_id}",
        severity=severity,
        confidence=0.9,
        evidence=Evidence(type="metric", value=f"evidence {issue_id}"),
        source=issue_id,
        why_it_matters=f"why {issue_id}",
        suggested_fix=f"fix {issue_id}",
        impact_rank=rank,
    )


def _issues() -> list[Issue]:
    return [
        _issue("seo-viewport", "high", 1),
        _issue("seo-title-missing", "high", 2),
        _issue("seo-canonical-missing", "medium", 3),
        _issue("seo-img-alt", "medium", 4),
        _issue("seo-lang", "low", 5),
        _issue("seo-twitter-card", "low", 6),
    ]


def _settings() -> Settings:
    return Settings(log_level="WARNING", groq_api_key="test-key", groq_model="test-model")


def _originals() -> RewriteOriginals:
    return RewriteOriginals(
        title="Springfield Plumbing Co | Same Day Repairs",
        meta_description=(
            "Licensed plumbers serving Springfield homes with same day "
            "repairs and installs. Call today."
        ),
        h1="Same day plumbing repairs in Springfield",
        cta="Get a free quote",
    )


def _explanations(ids: list[str]) -> dict[str, Any]:
    return {
        "explanations": [
            {
                "issue_id": issue_id,
                "why_it_matters": f"Why {issue_id}.",
                "suggested_fix": f"Fix {issue_id}.",
            }
            for issue_id in ids
        ]
    }


def _rewrites() -> dict[str, Any]:
    return {
        "rewrites": [
            {
                "target": "title",
                "variants": [
                    "Affordable Plumber in Springfield | Example Co",
                    "Springfield Plumbing Services | Example Co",
                ],
            },
            {
                "target": "meta_description",
                "variants": [
                    "Springfield plumbers for same day repairs and installs. "
                    "Licensed team, upfront pricing, call today.",
                    "Need a plumber in Springfield? Same day repairs from a "
                    "licensed local team. Call now.",
                ],
            },
            {
                "target": "h1",
                "variants": ["Same Day Plumbing Repairs", "Plumbing Help in Springfield"],
            },
            {"target": "cta", "variants": ["Request a Free Quote", "Call for Same Day Service"]},
        ]
    }


class FakeClient:
    """Scripted stand-in for GroqClient. Pops one item per call."""

    def __init__(self, script: list[dict[str, Any] | Exception]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        next_item = self.script.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def test_no_key_skips_without_call():
    client = FakeClient([])
    settings = Settings(log_level="WARNING", groq_api_key="")
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=settings, client=client
    )
    assert client.calls == []
    assert [issue.why_it_matters for issue in result.issues] == [
        f"why {issue.id}" for issue in _issues()
    ]
    assert result.rewrites == []
    expected = ["AI explanations and rewrites unavailable (no API key configured)."]
    assert result.limitations == expected


def test_happy_path_merges_top_five_and_rewrites():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), _rewrites()])
    result = enhance_issues(
        _issues(),
        page_text="Springfield plumber page",
        originals=_originals(),
        settings=_settings(),
        client=client,
    )
    assert len(client.calls) == 2
    for issue in result.issues[:5]:
        assert issue.why_it_matters == f"Why {issue.id}."
        assert issue.suggested_fix == f"Fix {issue.id}."
    assert result.issues[5].why_it_matters == "why seo-twitter-card"
    assert [rewrite.target for rewrite in result.rewrites] == [
        "title",
        "meta_description",
        "h1",
        "cta",
    ]
    for rewrite in result.rewrites:
        assert rewrite.label == "AI generated, test before using"
        assert 2 <= len(rewrite.variants) <= 3
    assert result.limitations == []


def test_severity_rank_evidence_untouched():
    before = _issues()
    ids = [issue.id for issue in before[:5]]
    client = FakeClient([_explanations(ids), _rewrites()])
    result = enhance_issues(
        before, page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    for original, merged in zip(before, result.issues):
        assert merged.severity == original.severity
        assert merged.impact_rank == original.impact_rank
        assert merged.evidence == original.evidence


def test_unknown_ids_ignored():
    payload = _explanations(["seo-viewport"])
    payload["explanations"].append(
        {"issue_id": "nope-1", "why_it_matters": "X.", "suggested_fix": "Y."}
    )
    client = FakeClient([payload, _rewrites()])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert result.issues[0].why_it_matters == "Why seo-viewport."
    assert result.issues[1].why_it_matters == "why seo-title-missing"


def test_malformed_retries_then_succeeds():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([AIError("malformed"), _explanations(ids), _rewrites()])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 3
    assert result.issues[0].why_it_matters == "Why seo-viewport."
    assert len(result.rewrites) == 4


def test_persistent_validation_failure_falls_back():
    client = FakeClient([{"wrong": []}, {"wrong": []}])
    before = _issues()
    result = enhance_issues(
        before, page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 2
    assert [issue.why_it_matters for issue in result.issues] == [
        issue.why_it_matters for issue in before
    ]
    assert result.rewrites == []
    expected = ["AI output failed validation; showing deterministic text with no rewrites."]
    assert result.limitations == expected


def test_timeout_fails_fast_without_retry():
    client = FakeClient([AIError("timeout")])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 1
    assert result.rewrites == []
    assert len(result.limitations) == 1


def test_empty_output_retries():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([AIError("empty"), _explanations(ids), _rewrites()])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 3
    assert len(result.rewrites) == 4


def test_task2_failure_reverts_task1():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), {"bad": 1}, {"bad": 2}])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 3
    assert result.issues[0].why_it_matters == "why seo-viewport"
    assert result.rewrites == []
    assert len(result.limitations) == 1


def test_missing_originals_skips_rewrites():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids)])
    result = enhance_issues(
        _issues(), page_text="text", originals=None, settings=_settings(), client=client
    )
    assert len(client.calls) == 1
    assert result.issues[0].why_it_matters == "Why seo-viewport."
    assert result.rewrites == []
    assert result.limitations == ["Rewrites unavailable (page content missing)."]


def test_empty_target_skipped():
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), _rewrites()])
    originals = RewriteOriginals(
        title=_originals().title,
        meta_description=_originals().meta_description,
        h1=_originals().h1,
        cta="",
    )
    result = enhance_issues(
        _issues(), page_text="text", originals=originals, settings=_settings(), client=client
    )
    assert [rewrite.target for rewrite in result.rewrites] == ["title", "meta_description", "h1"]
    assert result.limitations == []


def test_length_filtering_drops_bad_variants():
    payload = {
        "rewrites": [
            {
                "target": "title",
                "variants": [
                    "short",
                    "Affordable Plumber in Springfield | Example Co",
                    "Springfield Plumbing Services | Example Co",
                ],
            },
            {"target": "meta_description", "variants": ["tiny", "x" * 200]},
        ]
    }
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), payload])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert [rewrite.target for rewrite in result.rewrites] == ["title"]
    assert len(result.rewrites[0].variants) == 2


def test_superlative_and_claim_filters():
    payload = {
        "rewrites": [
            {
                "target": "h1",
                "variants": [
                    "Best plumber guaranteed",
                    "Springfield Plumbing Repairs",
                    "Same Day Plumbing Help",
                ],
            },
            {
                "target": "cta",
                "variants": [
                    "Plans for $99 only",
                    "Request a Free Quote",
                    "Call for Same Day Service",
                ],
            },
        ]
    }
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), payload])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    by_target = {rewrite.target: rewrite.variants for rewrite in result.rewrites}
    assert by_target["h1"] == ["Springfield Plumbing Repairs", "Same Day Plumbing Help"]
    assert by_target["cta"] == ["Request a Free Quote", "Call for Same Day Service"]


def test_currency_kept_when_original_has_it():
    payload = {
        "rewrites": [
            {"target": "cta", "variants": ["Plans from $10/mo", "See Plans Under $20"]},
        ]
    }
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), payload])
    originals = RewriteOriginals(title="", meta_description="", h1="", cta="Plans from $10")
    result = enhance_issues(
        _issues(), page_text="text", originals=originals, settings=_settings(), client=client
    )
    assert [rewrite.target for rewrite in result.rewrites] == ["cta"]
    assert len(result.rewrites[0].variants) == 2


def test_sentence_truncation():
    payload = {
        "explanations": [
            {
                "issue_id": "seo-viewport",
                "why_it_matters": "One. Two. Three. Four.",
                "suggested_fix": "Fix one. Fix two. Fix three.",
            }
        ]
    }
    client = FakeClient([payload, _rewrites()])
    result = enhance_issues(
        _issues(), page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert result.issues[0].why_it_matters == "One. Two."
    assert result.issues[0].suggested_fix == "Fix one. Fix two."


def test_prompt_truncates_inputs():
    page_text = "x" * 5000
    brand = "y" * 600
    _, user = build_explanations_prompt(_issues()[:1], page_text, brand)
    assert page_text not in user
    assert "x" * 4000 in user
    assert "y" * 600 not in user
    system, rewrite_user = build_rewrites_prompt({"title": "T"}, page_text, brand)
    assert system
    assert page_text not in rewrite_user


def test_logs_carry_no_user_content(caplog):
    ids = [issue.id for issue in _issues()[:5]]
    client = FakeClient([_explanations(ids), _rewrites()])
    with caplog.at_level("INFO", logger="fixitproper.ai"):
        enhance_issues(
            _issues(),
            page_text="ZEBRA-UNIQUE-999 body text",
            originals=_originals(),
            brand_voice="BRAND-UNIQUE-888 voice",
            settings=_settings(),
            client=client,
        )
    assert "ZEBRA-UNIQUE-999" not in caplog.text
    assert "BRAND-UNIQUE-888" not in caplog.text


def test_empty_issues_skips_task1():
    client = FakeClient([_rewrites()])
    result = enhance_issues(
        [], page_text="text", originals=_originals(), settings=_settings(), client=client
    )
    assert len(client.calls) == 1
    assert len(result.rewrites) == 4


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeResponse:
    def __init__(self, choices: list[_FakeChoice]) -> None:
        self.choices = choices


class _FakeCompletions:
    def __init__(self, behavior: Any) -> None:
        self.behavior = behavior

    def create(self, **kwargs: Any) -> Any:
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return self.behavior


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeGroq:
    behavior: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.chat = _FakeChat(_FakeCompletions(_FakeGroq.behavior))


def _groq_client(monkeypatch: pytest.MonkeyPatch, behavior: Any) -> GroqClient:
    _FakeGroq.behavior = behavior
    monkeypatch.setattr("app.ai.client.Groq", _FakeGroq)
    return GroqClient(api_key="k", model="m")


def _ok_response(text: str) -> _FakeResponse:
    return _FakeResponse([_FakeChoice(_FakeMessage(text))])


def test_groq_client_parses_json(monkeypatch):
    client = _groq_client(monkeypatch, _ok_response('{"a": 1}'))
    assert client.complete_json("s", "u") == {"a": 1}


def test_groq_client_empty_output(monkeypatch):
    client = _groq_client(monkeypatch, _ok_response("   "))
    with pytest.raises(AIError) as empty:
        client.complete_json("s", "u")
    assert empty.value.kind == "empty"
    nocontent = _groq_client(monkeypatch, _FakeResponse([_FakeChoice(_FakeMessage(None))]))
    with pytest.raises(AIError) as missing:
        nocontent.complete_json("s", "u")
    assert missing.value.kind == "empty"
    nochoices = _groq_client(monkeypatch, _FakeResponse([]))
    with pytest.raises(AIError) as absent:
        nochoices.complete_json("s", "u")
    assert absent.value.kind == "empty"


def test_groq_client_malformed(monkeypatch):
    client = _groq_client(monkeypatch, _ok_response("nope{"))
    with pytest.raises(AIError) as bad:
        client.complete_json("s", "u")
    assert bad.value.kind == "malformed"
    array = _groq_client(monkeypatch, _ok_response("[1]"))
    with pytest.raises(AIError) as nonobject:
        array.complete_json("s", "u")
    assert nonobject.value.kind == "malformed"


def test_groq_client_timeout_and_transport(monkeypatch):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    slow = _groq_client(monkeypatch, APITimeoutError(request=request))
    with pytest.raises(AIError) as timed_out:
        slow.complete_json("s", "u")
    assert timed_out.value.kind == "timeout"
    broken = _groq_client(monkeypatch, APIError(message="boom", request=request, body=None))
    with pytest.raises(AIError) as failed:
        broken.complete_json("s", "u")
    assert failed.value.kind == "transport"

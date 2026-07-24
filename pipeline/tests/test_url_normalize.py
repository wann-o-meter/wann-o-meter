import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core.url_normalize import normalize_url  # noqa: E402


def test_strips_fragment():
    assert normalize_url("https://example.org/events#section-2") == "https://example.org/events"


def test_strips_trailing_slash_but_keeps_root():
    assert normalize_url("https://example.org/events/") == "https://example.org/events"
    assert normalize_url("https://example.org/") == "https://example.org/"


def test_strips_utm_params_but_keeps_others():
    result = normalize_url("https://example.org/events?id=42&utm_source=newsletter&utm_medium=email")
    assert result == "https://example.org/events?id=42"


def test_sorts_query_params_for_stable_dedup():
    a = normalize_url("https://example.org/events?b=2&a=1")
    b = normalize_url("https://example.org/events?a=1&b=2")
    assert a == b


def test_lowercases_scheme_and_host_but_not_path():
    result = normalize_url("HTTPS://Example.ORG/Events")
    assert result == "https://example.org/Events"


def test_fragment_trailing_slash_and_utm_variants_collapse_to_the_same_url():
    variants = [
        "https://example.org/events/",
        "https://example.org/events#top",
        "https://example.org/events?utm_source=x",
        "https://example.org/events/?utm_campaign=y#frag",
    ]
    normalized = {normalize_url(v) for v in variants}
    assert len(normalized) == 1


def test_distinct_real_paths_stay_distinct():
    assert normalize_url("https://example.org/events") != normalize_url("https://example.org/news")

"""subject_slug is the field that decides WHICH data.yaml a source writes
into, so it is both the aggregation switch (several sources, one page) and a
path segment that must never escape data/."""

import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import crawl_config  # noqa: E402


def _raw(**overrides):
    base = {
        "id": "nasa-2001-2100",
        "seed_url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
        "category": "astronomie",
        "scope": {"allowed_domains": ["eclipse.gsfc.nasa.gov"]},
    }
    base.update(overrides)
    return base


def test_a_source_without_a_subject_slug_keeps_writing_to_its_own_page():
    """The pre-existing behavior, and the default every current config
    relies on - a new field must not move anyone's data."""
    source = crawl_config._parse(_raw(), Path("nasa-2001-2100.yaml"))
    assert source.subject_slug == "nasa-2001-2100"


def test_two_sources_can_name_the_same_page():
    slugs = [
        crawl_config._parse(_raw(id=id_, subject_slug="sonnenfinsternis"), Path(f"{id_}.yaml")).subject_slug
        for id_ in ("nasa-1901-2000", "nasa-2001-2100")
    ]
    assert slugs == ["sonnenfinsternis", "sonnenfinsternis"]


@pytest.mark.parametrize("bad", ["../../../etc", "with/slash", "Uppercase", "trailing-", "with space", "dots.in.it"])
def test_a_subject_slug_that_is_not_a_plain_slug_is_rejected(bad):
    """It becomes a directory name under data/, and config files are
    hand-edited - so this is a trust boundary, not a formatting preference."""
    with pytest.raises(crawl_config.CrawlConfigError, match="subject_slug"):
        crawl_config._parse(_raw(subject_slug=bad), Path("x.yaml"))


def test_a_batch_source_sharing_the_directory_is_skipped_not_parsed(tmp_path):
    """data/_sources/ holds BOTH crawler sources and core/runner.py's
    single-fetch batch sources (schulferien_kmk). A batch file has no
    seed_url/scope, so parsing it as a crawl source would raise - it has to
    be skipped on its explicit `kind` instead."""
    (tmp_path / "schulferien_kmk.yaml").write_text(
        "kind: batch\nid: schulferien_kmk\nurl: https://www.kmk.org/service/ferien.html\n",
        encoding="utf-8",
    )
    (tmp_path / "wiesnkini-de.yaml").write_text(
        "id: wiesnkini-de\nseed_url: https://wiesnkini.de/\ncategory: events/feste\n"
        "scope:\n  allowed_domains: [wiesnkini.de]\n",
        encoding="utf-8",
    )

    assert list(crawl_config.load_all_crawl_sources(tmp_path)) == ["wiesnkini-de"]


def test_a_crawl_source_missing_a_field_still_raises_rather_than_being_skipped(tmp_path):
    """The flip side of the test above: absence of `kind` means "crawler
    source", so a malformed one is reported, not quietly dropped."""
    (tmp_path / "broken.yaml").write_text("id: broken\ncategory: astronomie\n", encoding="utf-8")

    with pytest.raises(crawl_config.CrawlConfigError, match="seed_url"):
        crawl_config.load_all_crawl_sources(tmp_path)


def test_a_blank_subject_name_is_normalised_away():
    """Blank means "fall back to the crawled <title>", which crawl_runner
    tests with `or` - whitespace would defeat that."""
    assert crawl_config._parse(_raw(subject_name="   "), Path("x.yaml")).subject_name == ""
    assert (
        crawl_config._parse(_raw(subject_name=" Sonnenfinsternis "), Path("x.yaml")).subject_name == "Sonnenfinsternis"
    )

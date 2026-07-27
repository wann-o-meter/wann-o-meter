"""Dispatch coverage for the `wom` CLI.

The subcommands are thin by design, so the only thing here worth testing is
the routing: `wom run` has to send a source to the runner that owns it, and
the two runners are not interchangeable. Everything downstream of that
decision is covered by test_crawl_runner.py / test_generic_source.py.

No network and no real sources: both registries are pointed at tmp_path.
"""

import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import cli  # noqa: E402
from core import crawl_config, crawl_runner, runner  # noqa: E402

CRAWL_YAML = (
    "id: wiesnkini-de\n"
    "seed_url: https://wiesnkini.de/\n"
    "category: events/feste\n"
    "scope:\n  allowed_domains: [wiesnkini.de]\n"
)
BATCH_YAML = (
    "kind: batch\n"
    "id: schulferien_kmk\n"
    "kategorie: schulferien\n"
    "url: https://www.kmk.org/service/ferien.html\n"
)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    """Both source kinds share data/_sources/, so both loaders must be
    repointed at the same directory - which is also what proves the `kind`
    discriminator keeps them apart."""
    (tmp_path / "wiesnkini-de.yaml").write_text(CRAWL_YAML, encoding="utf-8")
    (tmp_path / "schulferien_kmk.yaml").write_text(BATCH_YAML, encoding="utf-8")
    monkeypatch.setattr(crawl_config, "CRAWL_SOURCES_DIR", tmp_path)
    monkeypatch.setattr(runner, "SOURCES_DIR", tmp_path)
    return tmp_path


def test_sources_lists_both_kinds_with_the_runner_that_owns_each(sources, capsys):
    assert cli.main(["sources"]) == 0

    out = capsys.readouterr().out
    assert "wiesnkini-de" in out and "crawl" in out
    assert "schulferien_kmk" in out and "batch" in out


def test_run_sends_a_batch_source_to_the_batch_runner_with_its_params(sources, monkeypatch):
    """--jahr 2028 is the whole reason batch sources take params at all: the
    KMK page is fetched per school year."""
    seen = {}
    monkeypatch.setattr(runner, "run", lambda source_id, params: seen.update(id=source_id, params=params) or 0)

    assert cli.main(["run", "schulferien_kmk", "--jahr", "2028"]) == 0
    assert seen == {"id": "schulferien_kmk", "params": {"jahr": "2028"}}


def test_run_sends_a_crawl_source_to_the_crawl_runner(sources, monkeypatch):
    seen = {}

    def _fake_run(source, on_progress=None, on_page=None):
        seen["id"] = source.id
        return {"reconfirmed": 0, "needs_review": 3}

    monkeypatch.setattr(crawl_runner, "run", _fake_run)

    assert cli.main(["run", "wiesnkini-de"]) == 0
    assert seen == {"id": "wiesnkini-de"}


def test_run_rejects_params_on_a_crawl_source_rather_than_ignoring_them(sources, monkeypatch):
    """A crawl source's scope is its config file. Silently dropping --jahr
    would look like it had been applied."""
    monkeypatch.setattr(crawl_runner, "run", lambda *a, **kw: pytest.fail("should not have run"))

    assert cli.main(["run", "wiesnkini-de", "--jahr", "2028"]) == 2


def test_an_unknown_source_exits_nonzero_and_names_the_known_ones(sources, capsys):
    assert cli.main(["run", "nope"]) == 1

    err = capsys.readouterr().err
    assert "wiesnkini-de" in err and "schulferien_kmk" in err


def test_a_malformed_param_is_reported_rather_than_passed_through(sources, monkeypatch):
    monkeypatch.setattr(runner, "run", lambda *a, **kw: pytest.fail("should not have run"))

    assert cli.main(["run", "schulferien_kmk", "--jahr"]) == 2

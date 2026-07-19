"""Nested-category support in main.py: path splitting/validation for the
create-page form, the recursive data/ walk (_iter_pages), and the
_category.yaml writer. Each test monkeypatches main.DATA_ROOT to an isolated
tmp_path so this never touches the real repo data/ tree."""

import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import main  # noqa: E402


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path)
    return tmp_path


def _write_page(folder: Path, category: str, slug: str, url: str = "https://example.invalid/x") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "page.yaml").write_text(
        yaml.dump({"title": slug, "description": "", "tags": []}, allow_unicode=True), encoding="utf-8"
    )
    (folder / "data.yaml").write_text(
        yaml.dump(
            {
                "subject": {"slug": slug, "category": category},
                "source": {
                    "url": url,
                    "license": "own_derivation",
                    "retrieved_at": "2026-07-12",
                    "extraction": "manual",
                },
                "raw_data": {"kind": "html_page", "dates": []},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


class TestSlugifyCategoryPath:
    def test_splits_and_slugifies_each_segment_independently(self):
        assert main._slugify_category_path("Sport/Fußball/Bundesliga") == ["sport", "fussball", "bundesliga"]

    def test_single_segment_matches_old_flat_behaviour(self):
        assert main._slugify_category_path("Astronomie") == ["astronomie"]

    def test_ignores_empty_segments_from_stray_slashes(self):
        assert main._slugify_category_path("Sport//Fussball/") == ["sport", "fussball"]


class TestValidateCategorySegments:
    def test_accepts_a_normal_nested_path(self):
        assert main._validate_category_segments(["sport", "fussball", "bundesliga"]) is None

    def test_accepts_up_to_the_max_depth(self):
        assert main._validate_category_segments(["a", "b", "c", "d"]) is None

    def test_rejects_a_path_deeper_than_the_max_depth(self):
        error = main._validate_category_segments(["a", "b", "c", "d", "e"])
        assert error is not None
        assert "too deep" in error

    def test_rejects_a_reserved_top_level_segment(self):
        error = main._validate_category_segments(["kalender", "sub"])
        assert error is not None
        assert "reserved category name" in error

    def test_allows_a_reserved_top_level_name_as_a_deeper_segment(self):
        # RESERVED_CATEGORIES is only checked against segment 1 - a category
        # like "sport/kalender" is fine, only "kalender/..." is not.
        assert main._validate_category_segments(["sport", "kalender"]) is None

    def test_rejects_tag_as_a_segment_at_any_depth(self):
        assert main._validate_category_segments(["tag"]) is not None
        assert main._validate_category_segments(["sport", "tag"]) is not None
        assert main._validate_category_segments(["sport", "tag", "fussball"]) is not None

    def test_rejects_an_empty_path(self):
        assert main._validate_category_segments([]) is not None


class TestIterPagesAndCategoryPaths:
    def test_walks_arbitrary_depth_and_skips_reserved_segments(self, data_root):
        _write_page(data_root / "astronomie" / "eclipse", "astronomie", "eclipse")
        _write_page(data_root / "sport" / "fussball" / "bundesliga" / "spielplan", "sport/fussball/bundesliga", "spielplan")
        _write_page(data_root / "kalender" / "should-be-skipped", "kalender", "should-be-skipped")
        (data_root / "sport" / "tag").mkdir(parents=True, exist_ok=True)  # reserved at any depth, must be skipped

        found = {category: folder.name for category, folder in main._iter_pages()}
        assert found == {
            "astronomie": "eclipse",
            "sport/fussball/bundesliga": "spielplan",
        }

    def test_category_paths_only_reports_leaf_categories_with_pages(self, data_root):
        _write_page(data_root / "sport" / "fussball" / "bundesliga" / "spielplan", "sport/fussball/bundesliga", "spielplan")
        assert main._category_paths() == ["sport/fussball/bundesliga"]

    def test_find_page_by_url_returns_the_full_nested_category_path(self, data_root):
        _write_page(
            data_root / "sport" / "fussball" / "bundesliga" / "spielplan",
            "sport/fussball/bundesliga",
            "spielplan",
            url="https://example.invalid/match-me",
        )
        result = main._find_page_by_url("https://example.invalid/match-me")
        assert result == ("sport/fussball/bundesliga", "spielplan")

    def test_find_page_by_url_returns_none_for_no_match(self, data_root):
        assert main._find_page_by_url("https://example.invalid/nope") is None


class TestCategoryAndSlugForPage:
    def test_builds_a_fresh_nested_path_and_slug_for_a_new_url(self, data_root):
        category_path, slug = main._category_and_slug_for_page(
            "https://example.invalid/new", "Sport/Fußball/Bundesliga", "Spieltag 1"
        )
        assert category_path == "sport/fussball/bundesliga"
        assert slug == "spieltag-1"

    def test_reuses_the_existing_category_and_slug_for_an_already_known_url(self, data_root):
        _write_page(
            data_root / "sport" / "fussball" / "bundesliga" / "spieltag-1",
            "sport/fussball/bundesliga",
            "spieltag-1",
            url="https://example.invalid/existing",
        )
        category_path, slug = main._category_and_slug_for_page(
            "https://example.invalid/existing", "Some Other Category", "Some Other Title"
        )
        assert (category_path, slug) == ("sport/fussball/bundesliga", "spieltag-1")

    def test_disambiguates_a_slug_collision_within_the_same_nested_category(self, data_root):
        _write_page(
            data_root / "sport" / "fussball" / "spieltag-1", "sport/fussball", "spieltag-1", url="https://example.invalid/a"
        )
        category_path, slug = main._category_and_slug_for_page("https://example.invalid/b", "Sport/Fussball", "Spieltag 1")
        assert category_path == "sport/fussball"
        assert slug == "spieltag-1-2"


class TestWriteCategoryMetaIfNew:
    def test_writes_category_yaml_for_every_new_segment_with_its_own_typed_name(self, data_root):
        main._write_category_meta_if_new("Sport/Fußball/Bundesliga")

        assert yaml.safe_load((data_root / "sport" / "_category.yaml").read_text(encoding="utf-8")) == {"name": "Sport"}
        assert yaml.safe_load((data_root / "sport" / "fussball" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Fußball"
        }
        assert yaml.safe_load(
            (data_root / "sport" / "fussball" / "bundesliga" / "_category.yaml").read_text(encoding="utf-8")
        ) == {"name": "Bundesliga"}

    def test_never_overwrites_an_existing_category_yaml(self, data_root):
        meta_path = data_root / "sport" / "_category.yaml"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(yaml.dump({"name": "Hand-edited name"}), encoding="utf-8")

        main._write_category_meta_if_new("Sport/Fußball")

        assert yaml.safe_load(meta_path.read_text(encoding="utf-8"))["name"] == "Hand-edited name"
        # the new, previously-unseen sub-segment still gets written
        assert yaml.safe_load((data_root / "sport" / "fussball" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Fußball"
        }

    def test_single_segment_matches_old_flat_behaviour(self, data_root):
        main._write_category_meta_if_new("Astronomie")
        assert yaml.safe_load((data_root / "astronomie" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Astronomie"
        }


class TestCategoryNameFor:
    def test_joins_each_segments_own_display_name(self, data_root):
        main._write_category_meta_if_new("Sport/Fußball/Bundesliga")
        assert main._category_name_for("sport/fussball/bundesliga") == "Sport/Fußball/Bundesliga"

    def test_falls_back_to_a_capitalized_slug_per_segment_with_no_category_yaml(self, data_root):
        assert main._category_name_for("sport/fussball") == "Sport/Fussball"

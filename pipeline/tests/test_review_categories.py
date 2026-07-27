"""Nested-category support in review/service.py: path splitting/validation for the
create-page form, the recursive data/ walk (_iter_pages), and the
_category.yaml writer. Each test monkeypatches service.DATA_ROOT to an isolated
tmp_path so this never touches the real repo data/ tree."""

import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from review import service  # noqa: E402
from review.app import app  # noqa: E402


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_ROOT", tmp_path)
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
        assert service._slugify_category_path("Sport/Fußball/Bundesliga") == ["sport", "fussball", "bundesliga"]

    def test_single_segment_matches_old_flat_behaviour(self):
        assert service._slugify_category_path("Astronomie") == ["astronomie"]

    def test_ignores_empty_segments_from_stray_slashes(self):
        assert service._slugify_category_path("Sport//Fussball/") == ["sport", "fussball"]


class TestValidateCategorySegments:
    def test_accepts_a_normal_nested_path(self):
        assert service._validate_category_segments(["sport", "fussball", "bundesliga"]) is None

    def test_accepts_up_to_the_max_depth(self):
        assert service._validate_category_segments(["a", "b", "c", "d"]) is None

    def test_rejects_a_path_deeper_than_the_max_depth(self):
        error = service._validate_category_segments(["a", "b", "c", "d", "e"])
        assert error is not None
        assert "too deep" in error

    def test_rejects_a_reserved_top_level_segment(self):
        error = service._validate_category_segments(["kalender", "sub"])
        assert error is not None
        assert "reserved category name" in error

    def test_allows_a_reserved_top_level_name_as_a_deeper_segment(self):
        # RESERVED_CATEGORIES is only checked against segment 1 - a category
        # like "sport/kalender" is fine, only "kalender/..." is not.
        assert service._validate_category_segments(["sport", "kalender"]) is None

    def test_rejects_tag_as_a_segment_at_any_depth(self):
        assert service._validate_category_segments(["tag"]) is not None
        assert service._validate_category_segments(["sport", "tag"]) is not None
        assert service._validate_category_segments(["sport", "tag", "fussball"]) is not None

    def test_rejects_an_empty_path(self):
        assert service._validate_category_segments([]) is not None


class TestIterPagesAndCategoryPaths:
    def test_walks_arbitrary_depth_and_skips_reserved_segments(self, data_root):
        _write_page(data_root / "astronomie" / "eclipse", "astronomie", "eclipse")
        _write_page(data_root / "sport" / "fussball" / "bundesliga" / "spielplan", "sport/fussball/bundesliga", "spielplan")
        _write_page(data_root / "kalender" / "should-be-skipped", "kalender", "should-be-skipped")
        (data_root / "sport" / "tag").mkdir(parents=True, exist_ok=True)  # reserved at any depth, must be skipped

        found = {category: folder.name for category, folder in service._iter_pages()}
        assert found == {
            "astronomie": "eclipse",
            "sport/fussball/bundesliga": "spielplan",
        }

    def test_category_paths_only_reports_leaf_categories_with_pages(self, data_root):
        _write_page(data_root / "sport" / "fussball" / "bundesliga" / "spielplan", "sport/fussball/bundesliga", "spielplan")
        assert service._category_paths() == ["sport/fussball/bundesliga"]


class TestWriteCategoryMetaIfNew:
    def test_writes_category_yaml_for_every_new_segment_with_its_own_typed_name(self, data_root):
        service._write_category_meta_if_new("Sport/Fußball/Bundesliga")

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

        service._write_category_meta_if_new("Sport/Fußball")

        assert yaml.safe_load(meta_path.read_text(encoding="utf-8"))["name"] == "Hand-edited name"
        # the new, previously-unseen sub-segment still gets written
        assert yaml.safe_load((data_root / "sport" / "fussball" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Fußball"
        }

    def test_single_segment_matches_old_flat_behaviour(self, data_root):
        service._write_category_meta_if_new("Astronomie")
        assert yaml.safe_load((data_root / "astronomie" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Astronomie"
        }


class TestCategoryNameFor:
    def test_joins_each_segments_own_display_name(self, data_root):
        service._write_category_meta_if_new("Sport/Fußball/Bundesliga")
        assert service._category_name_for("sport/fussball/bundesliga") == "Sport/Fußball/Bundesliga"

    def test_falls_back_to_a_capitalized_slug_per_segment_with_no_category_yaml(self, data_root):
        assert service._category_name_for("sport/fussball") == "Sport/Fussball"

"""The containment guarantee, tested directly."""

from __future__ import annotations

import pytest

import safety


class TestAssertWithin:
    def test_a_path_inside_the_root_is_allowed(self, tmp_path):
        root = safety.resolve_root(tmp_path)
        assert safety.assert_within(root, "sub/file.jsonl") == (root / "sub" / "file.jsonl")

    def test_the_root_itself_is_allowed(self, tmp_path):
        root = safety.resolve_root(tmp_path)
        assert safety.assert_within(root, root) == root

    def test_dot_dot_cannot_escape(self, tmp_path):
        root = safety.resolve_root(tmp_path / "out")
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_within(root, "../escaped.jsonl")

    def test_an_absolute_path_elsewhere_is_refused(self, tmp_path):
        root = safety.resolve_root(tmp_path / "out")
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_within(root, tmp_path / "elsewhere.jsonl")

    def test_a_symlinked_parent_cannot_escape(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        root = tmp_path / "out"
        root.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_within(safety.resolve_root(root), root / "link" / "x.jsonl")


class TestAssertDisjoint:
    def test_same_folder_refused(self, tmp_path):
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_disjoint(tmp_path, tmp_path)

    def test_output_inside_input_refused(self, tmp_path):
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_disjoint(tmp_path, tmp_path / "out")

    def test_input_inside_output_refused(self, tmp_path):
        with pytest.raises(safety.OutsideOutputRoot):
            safety.assert_disjoint(tmp_path / "in", tmp_path)

    def test_siblings_are_fine(self, tmp_path):
        safety.assert_disjoint(tmp_path / "in", tmp_path / "out")


class TestWriters:
    def test_dry_run_writes_nothing(self, tmp_path):
        root = safety.resolve_root(tmp_path)
        safety.write_json(root, "a.json", {"x": 1}, dry_run=True)
        safety.write_jsonl(root, "b.jsonl", [{"x": 1}], dry_run=True)
        assert list(tmp_path.iterdir()) == []

    def test_writers_create_parents(self, tmp_path):
        root = safety.resolve_root(tmp_path)
        safety.write_jsonl(root, "_audit/a.jsonl", [{"x": 1}])
        assert (tmp_path / "_audit" / "a.jsonl").read_text().strip() == '{"x": 1}'

    def test_a_writer_refuses_to_escape(self, tmp_path):
        root = safety.resolve_root(tmp_path / "out")
        with pytest.raises(safety.OutsideOutputRoot):
            safety.write_json(root, "../escaped.json", {})

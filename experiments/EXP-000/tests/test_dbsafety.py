"""Credential handling, read-only discipline and the data/raw write restriction."""

from __future__ import annotations

from pathlib import Path

import pytest

import dbsafety
import fakedb


class TestCredentials:
    def test_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        assert dbsafety.database_url() == "postgresql://u:p@h/db"

    def test_missing_is_an_error_naming_the_variable(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(dbsafety.MissingCredentials, match="DATABASE_URL"):
            dbsafety.database_url()

    def test_blank_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "   ")
        with pytest.raises(dbsafety.MissingCredentials):
            dbsafety.database_url()

    def test_no_file_in_the_repo_is_consulted(self, monkeypatch, tmp_path):
        # A credential that can come from the repo is a credential that can be committed.
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for name in (".env", "database.url", "secrets.yaml", "extract.yaml"):
            (tmp_path / name).write_text("postgresql://leaked:leaked@host/db", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(dbsafety.MissingCredentials):
            dbsafety.database_url()


class TestSelectOnly:
    @pytest.mark.parametrize("sql", [
        "SELECT 1",
        "  select * from t",
        "WITH x AS (SELECT 1) SELECT * FROM x",
    ])
    def test_selects_pass(self, sql):
        assert dbsafety.assert_select_only(sql) == sql

    @pytest.mark.parametrize("sql", [
        "DELETE FROM messages",
        "UPDATE messages SET body = ''",
        "DROP TABLE messages",
        "INSERT INTO messages VALUES (1)",
        "TRUNCATE messages",
        "CREATE TABLE t (a int)",
    ])
    def test_everything_else_raises(self, sql):
        with pytest.raises(dbsafety.NotASelect):
            dbsafety.assert_select_only(sql)


class TestReadOnlySession:
    def test_the_read_only_statement_runs_first(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        session = dbsafety.connect(fakedb.connect_fn)
        assert session.connection.statements[0][0] == dbsafety.READ_ONLY_STATEMENT
        assert session.connection.read_only_set is True

    def test_the_driver_flag_is_set_too(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        session = dbsafety.connect(fakedb.connect_fn)
        assert session.connection.read_only is True

    def test_select_passes_through_and_non_select_is_refused(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        session = dbsafety.connect(fakedb.connect_fn)
        with session.cursor() as cursor:
            session.select(cursor, "SELECT count(*) FROM messages")
            assert cursor.fetchone()[0] == len(fakedb.MESSAGES)
            with pytest.raises(dbsafety.NotASelect):
                session.select(cursor, "DELETE FROM messages")


class TestOutputRestriction:
    def test_a_relative_name_lands_in_data_raw(self):
        path = dbsafety.assert_in_data_raw("arthryx_messages.csv")
        assert path.parent == dbsafety.data_raw_root()

    def test_an_absolute_path_elsewhere_is_refused(self, tmp_path):
        with pytest.raises(dbsafety.OutsideDataRaw):
            dbsafety.assert_in_data_raw(tmp_path / "escaped.csv")

    def test_dot_dot_cannot_escape(self):
        with pytest.raises(dbsafety.OutsideDataRaw):
            dbsafety.assert_in_data_raw("../../escaped.csv")

    def test_the_repo_root_itself_is_refused(self):
        with pytest.raises(dbsafety.OutsideDataRaw):
            dbsafety.assert_in_data_raw(dbsafety.repo_root() / "notes.csv")

    def test_tests_may_point_the_root_elsewhere(self, tmp_path):
        # Only tests pass allowed_root; the CLI always uses data/raw.
        assert dbsafety.assert_in_data_raw("x.csv", allowed_root=tmp_path).parent == tmp_path

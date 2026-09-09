import json
import os
import sqlite3
import tempfile
import unittest

from ScrapWikiArt import db

import data_validation_script as dvs


def _temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


class TestResolveDbPath(unittest.TestCase):
    def test_cli_arg_wins(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--db-path", default=None)
        args = parser.parse_args(["--db-path", "/custom/db.db"])
        self.assertEqual(dvs.resolve_db_path(args), "/custom/db.db")

    def test_default_from_settings(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--db-path", default=None)
        args = parser.parse_args([])
        self.assertEqual(dvs.resolve_db_path(args), "data/works.db")

    def test_default_mirrors_settings_constant(self):
        from ScrapWikiArt.settings import WIKIART_DB_PATH
        self.assertEqual(dvs.DEFAULT_DB_PATH, WIKIART_DB_PATH)


class TestGeneratePromptMeta(unittest.TestCase):
    def test_skips_db_only_and_pipeline_keys(self):
        gen = dvs.generate_prompt_meta("painting")
        prompt = gen({
            "URL": "https://a.com",
            "image_urls": ["x"],
            "scraped_at": "2024-01-01",
            "ValidatedRaw": "yes",
            "Validated": True,
            "Title": "Mona Lisa",
        })
        # DB-only / pipeline keys must not leak into the prompt
        self.assertNotIn("scraped_at", prompt)
        self.assertNotIn("image_urls", prompt)
        self.assertNotIn("ValidatedRaw", prompt)
        self.assertNotIn("Validated", prompt)
        self.assertNotIn("https://a.com", prompt)
        self.assertIn("Mona Lisa", prompt)

    def test_includes_wikidescription_block(self):
        gen = dvs.generate_prompt_meta("painting")
        prompt = gen({"Title": "X", "WikiDescription": "Some text"})
        self.assertIn("Some text", prompt)


class TestLoadWorks(unittest.TestCase):
    def test_loads_all_rows(self):
        path = _temp_db_path()
        self.addCleanup(os.unlink, path)
        conn = db.connect(path)
        db.create_tables(conn)
        for i in range(3):
            db.insert_ignore(conn, "works", {
                "Id": f"id{i}", "Title": f"Work {i}",
                "URL": f"https://a.com/{i}", "scraped_at": "2024",
            })
        conn.close()

        conn = sqlite3.connect(path)
        try:
            df = dvs.load_works(conn)
            self.assertEqual(len(df), 3)
            self.assertEqual(set(df["Id"]), {"id0", "id1", "id2"})
        finally:
            conn.close()


class TestWriteValidation(unittest.TestCase):
    def test_writes_validatedraw_and_validated(self):
        path = _temp_db_path()
        self.addCleanup(os.unlink, path)
        conn = db.connect(path)
        db.create_tables(conn)
        for i in range(2):
            db.insert_ignore(conn, "works", {
                "Id": f"id{i}", "Title": f"Work {i}",
                "URL": f"https://a.com/{i}", "scraped_at": "2024",
            })
        conn.close()

        import pandas as pd
        df = pd.DataFrame([
            {"Id": "id0", "ValidatedRaw": "yes", "Validated": True},
            {"Id": "id1", "ValidatedRaw": "no", "Validated": False},
        ])
        conn = sqlite3.connect(path)
        try:
            dvs.write_validation(conn, df)
        finally:
            conn.close()

        conn = sqlite3.connect(path)
        try:
            row0 = conn.execute(
                "SELECT ValidatedRaw, Validated FROM works WHERE Id = 'id0'"
            ).fetchone()
            row1 = conn.execute(
                "SELECT ValidatedRaw, Validated FROM works WHERE Id = 'id1'"
            ).fetchone()
            # Validated is a TEXT column; booleans are persisted as
            # "True"/"False" strings (matches the old CSV output).
            self.assertEqual(row0, ("yes", "True"))
            self.assertEqual(row1, ("no", "False"))
        finally:
            conn.close()

    def test_preserves_works_pk(self):
        # Regression for the DV.3 deviation: executemany UPDATE must NOT
        # drop or recreate the works table (df.to_sql(if_exists='replace')
        # would destroy the Id PRIMARY KEY).
        path = _temp_db_path()
        self.addCleanup(os.unlink, path)
        conn = db.connect(path)
        db.create_tables(conn)
        db.insert_ignore(conn, "works", {
            "Id": "pk1", "Title": "T", "URL": "u", "scraped_at": "2024",
        })
        conn.close()

        import pandas as pd
        df = pd.DataFrame([{"Id": "pk1", "ValidatedRaw": "yes", "Validated": True}])
        conn = sqlite3.connect(path)
        try:
            dvs.write_validation(conn, df)
        finally:
            conn.close()

        conn = sqlite3.connect(path)
        try:
            # The Id column must still be the PRIMARY KEY after write-back.
            pk_info = conn.execute(
                "SELECT pk FROM pragma_table_info('works') WHERE name = 'Id'"
            ).fetchone()
            self.assertEqual(pk_info[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM works").fetchone()[0], 1
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
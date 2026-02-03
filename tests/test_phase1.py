#!/usr/bin/env python3
"""
Tests for Phase 1: Foundation
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from unittest import TestCase, main

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import generate_id, get_timestamp, read_jsonl, append_jsonl, format_table
from init_db import init_database, check_database


class TestUtils(TestCase):
    """Test utility functions."""

    def test_generate_id_has_prefix(self):
        id1 = generate_id("test")
        self.assertTrue(id1.startswith("test-"))

    def test_generate_id_unique(self):
        ids = [generate_id("test") for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_timestamp_format(self):
        ts = get_timestamp()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)

    def test_read_jsonl_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            result = read_jsonl(temp_path)
            self.assertEqual(result, [])
        finally:
            temp_path.unlink()

    def test_read_jsonl_with_data(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"a": 1}\n{"b": 2}\n')
            temp_path = Path(f.name)

        try:
            result = read_jsonl(temp_path)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0], {"a": 1})
            self.assertEqual(result[1], {"b": 2})
        finally:
            temp_path.unlink()

    def test_append_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "test.jsonl"

            append_jsonl(temp_path, {"test": 1})
            append_jsonl(temp_path, {"test": 2})

            result = read_jsonl(temp_path)
            self.assertEqual(len(result), 2)

    def test_format_table(self):
        headers = ["A", "B"]
        rows = [["1", "2"], ["3", "4"]]
        result = format_table(headers, rows)
        self.assertIn("A", result)
        self.assertIn("B", result)
        self.assertIn("1", result)

    def test_format_table_empty(self):
        headers = ["A", "B"]
        rows = []
        result = format_table(headers, rows)
        self.assertEqual(result, "No data")


class TestDatabase(TestCase):
    """Test database operations."""

    def test_init_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            schema_path = Path(__file__).parent.parent / "scripts" / "schema.sql"

            result = init_database(db_path, schema_path)
            self.assertTrue(result)
            self.assertTrue(db_path.exists())

    def test_check_database_not_exists(self):
        result = check_database(Path("/nonexistent/db.sqlite"))
        self.assertFalse(result.get("exists"))

    def test_check_database_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            schema_path = Path(__file__).parent.parent / "scripts" / "schema.sql"

            init_database(db_path, schema_path)
            result = check_database(db_path)

            self.assertTrue(result.get("exists"))
            self.assertEqual(result.get("schema_version"), "1")
            self.assertIn("tables", result)


class TestObserveScript(TestCase):
    """Test observation hook script."""

    def setUp(self):
        self.script_path = Path(__file__).parent.parent / "scripts" / "observe.sh"

    def test_script_exists(self):
        self.assertTrue(self.script_path.exists())

    def test_script_executable(self):
        self.assertTrue(os.access(self.script_path, os.X_OK))


class TestCLI(TestCase):
    """Test CLI commands."""

    def setUp(self):
        self.cli_path = Path(__file__).parent.parent / "scripts" / "cli.py"

    def test_cli_exists(self):
        self.assertTrue(self.cli_path.exists())

    def test_cli_help(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "--help"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Homunculus", result.stdout)

    def test_cli_status(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "status"],
            capture_output=True,
            text=True
        )
        self.assertIn("HOMUNCULUS", result.stdout)

    def test_cli_gaps(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "gaps"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_proposals(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "proposals"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_capabilities(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "capabilities"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_config(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "config"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)


class TestDirectoryStructure(TestCase):
    """Test that all directories exist."""

    def setUp(self):
        self.root = Path.home() / "homunculus"

    def test_root_exists(self):
        self.assertTrue(self.root.exists())

    def test_observations_dir(self):
        self.assertTrue((self.root / "observations").exists())

    def test_gaps_dir(self):
        self.assertTrue((self.root / "gaps" / "pending").exists())

    def test_proposals_dir(self):
        self.assertTrue((self.root / "proposals" / "pending").exists())

    def test_evolved_dir(self):
        self.assertTrue((self.root / "evolved" / "skills").exists())

    def test_meta_dir(self):
        self.assertTrue((self.root / "meta" / "detector-rules").exists())

    def test_scripts_dir(self):
        self.assertTrue((self.root / "scripts").exists())

    def test_config_exists(self):
        self.assertTrue((self.root / "config.yaml").exists())

    def test_database_exists(self):
        self.assertTrue((self.root / "homunculus.db").exists())


if __name__ == "__main__":
    main()

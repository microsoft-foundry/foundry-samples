#!/usr/bin/env python3
"""Contract tests for check-docs-referenced-files.py.

Hermetic: every case builds a throwaway git repository in a temp dir, so nothing here depends on
the state of this repo. Run directly:  python .github/scripts/test/test_docs_referenced_files.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-docs-referenced-files.py"
WORKFLOW = ROOT / "workflows" / "docs-referenced-files.yml"
MANIFEST = ROOT.parent / ".github" / "docs-referenced-files.json"

SPEC = importlib.util.spec_from_file_location("docs_referenced_files", CHECKER)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

PY_SAMPLE = """# <create_agent>
agent = client.create_agent()
# </create_agent>

# <run_agent>
agent.run()
# </run_agent>
"""

CS_SAMPLE = """\ufeff// <complete_code>
var items = new List<ToolDefinition>();
// </complete_code>
"""


def run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class RepoFixture:
    """A temp git repo with a manifest and sample files."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "user.email", "t@example.com")
        run_git(self.root, "config", "user.name", "T")
        run_git(self.root, "config", "commit.gpgsign", "false")

    def write(self, rel: str, text: str, newline: str = "\n") -> None:
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.replace("\n", newline), encoding="utf-8", newline="")

    def write_manifest(self, files: list) -> None:
        (self.root / ".github").mkdir(parents=True, exist_ok=True)
        (self.root / ".github" / "docs-referenced-files.json").write_text(
            json.dumps({"schemaVersion": 1, "files": files}, indent=2) + "\n",
            encoding="utf-8",
        )

    def commit(self, message: str = "c") -> None:
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", message)

    def check(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def cleanup(self) -> None:
        self.tmp.cleanup()


class CheckerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = RepoFixture()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("samples/app.py", PY_SAMPLE)
        self.repo.write_manifest(
            [
                {
                    "path": "samples/app.py",
                    "mode": "delimited",
                    "snippets": ["create_agent", "run_agent"],
                }
            ]
        )
        self.repo.commit("initial")

    # --- happy path -------------------------------------------------------------------
    def test_intact_tree_passes(self) -> None:
        result = self.repo.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("intact", result.stdout)

    # --- condition 2: deletion --------------------------------------------------------
    def test_deleted_file_fails(self) -> None:
        (self.repo.root / "samples/app.py").unlink()
        self.repo.commit("delete")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)
        self.assertIn("docs team", result.stdout.lower())

    # --- condition 1: rename/move -----------------------------------------------------
    def test_rename_fails_with_hint(self) -> None:
        base = subprocess.run(
            ["git", "-C", str(self.repo.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        run_git(self.repo.root, "mv", "samples/app.py", "samples/renamed.py")
        self.repo.commit("rename")
        result = self.repo.check("--base-ref", base)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)
        self.assertIn("samples/renamed.py", result.stdout)

    def test_rename_with_edits_still_fails_without_hint(self) -> None:
        run_git(self.repo.root, "mv", "samples/app.py", "samples/renamed.py")
        (self.repo.root / "samples/renamed.py").write_text(
            "# totally rewritten\n", encoding="utf-8"
        )
        self.repo.commit("rename+rewrite")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)

    def test_case_only_rename_fails(self) -> None:
        run_git(self.repo.root, "mv", "samples/app.py", "samples/App.py")
        self.repo.commit("case rename")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)

    # --- condition 3: snippet delimiters ----------------------------------------------
    def test_removed_opening_tag_fails(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE.replace("# <create_agent>\n", ""))
        self.repo.commit("drop open tag")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("create_agent", result.stdout)

    def test_removed_closing_tag_fails(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE.replace("# </run_agent>\n", ""))
        self.repo.commit("drop close tag")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("run_agent", result.stdout)

    def test_whole_snippet_removed_fails(self) -> None:
        self.repo.write("samples/app.py", "# <run_agent>\nagent.run()\n# </run_agent>\n")
        self.repo.commit("drop region")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("`create_agent` is gone", result.stdout)

    def test_emptied_region_fails(self) -> None:
        self.repo.write(
            "samples/app.py",
            "# <create_agent>\n# </create_agent>\n# <run_agent>\nagent.run()\n# </run_agent>\n",
        )
        self.repo.commit("empty region")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("empty", result.stdout)

    def test_moved_region_still_passes(self) -> None:
        self.repo.write(
            "samples/app.py",
            "import os\n\n"
            "# <run_agent>\nagent.run()\n# </run_agent>\n\n"
            "# <create_agent>\nagent = client.create_agent()\n# </create_agent>\n",
        )
        self.repo.commit("reorder")
        self.assertEqual(self.repo.check().returncode, 0)

    def test_crossed_regions_fail(self) -> None:
        self.repo.write(
            "samples/app.py",
            "# <create_agent>\na\n# <run_agent>\nb\n# </create_agent>\nc\n# </run_agent>\n",
        )
        self.repo.commit("crossed")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("out of order", result.stdout)

    def test_duplicate_tag_fails(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE + PY_SAMPLE)
        self.repo.commit("duplicated")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("exactly one", result.stdout)

    # --- parser robustness ------------------------------------------------------------
    def test_bom_and_crlf_csharp_tags_are_found(self) -> None:
        self.repo.write("samples/Program.cs", CS_SAMPLE, newline="\r\n")
        self.repo.write_manifest(
            [
                {
                    "path": "samples/app.py",
                    "mode": "delimited",
                    "snippets": ["create_agent", "run_agent"],
                },
                {
                    "path": "samples/Program.cs",
                    "mode": "delimited",
                    "snippets": ["complete_code"],
                },
            ]
        )
        self.repo.commit("csharp")
        self.assertEqual(self.repo.check().returncode, 0)

    def test_generic_type_is_not_a_tag(self) -> None:
        tags = checker.parse_tags(
            "var items = new List<ToolDefinition>();\n", "samples/Program.cs"
        )
        self.assertEqual(tags, [])

    def test_xml_comment_tags_are_found(self) -> None:
        tags = checker.parse_tags(
            "<Project>\n  <!-- <deps> -->\n  <X/>\n  <!-- </deps> -->\n</Project>\n",
            "samples/x.csproj",
        )
        self.assertEqual([(t.name, t.closing) for t in tags], [("deps", False), ("deps", True)])

    def test_json_cannot_be_delimited(self) -> None:
        with self.assertRaises(checker.CheckerError):
            checker.parse_tags('{"a": "<b>"}\n', "samples/policy.json")

    def test_unknown_extension_is_rejected(self) -> None:
        with self.assertRaises(checker.CheckerError):
            checker.parse_tags("# <a>\n", "samples/thing.wat")

    def test_whole_file_entry_only_checks_existence(self) -> None:
        self.repo.write("samples/policy.json", '{"a": 1}\n')
        self.repo.write_manifest([{"path": "samples/policy.json", "mode": "whole-file"}])
        self.repo.commit("json")
        self.assertEqual(self.repo.check().returncode, 0)
        (self.repo.root / "samples/policy.json").unlink()
        self.repo.commit("rm json")
        self.assertEqual(self.repo.check().returncode, 1)

    def test_symlink_replacement_is_rejected(self) -> None:
        target = self.repo.root / "samples/app.py"
        target.unlink()
        os.symlink("elsewhere.py", target)
        self.repo.commit("symlink")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a file", result.stdout)

    # --- worktree / local pre-push mode ------------------------------------------------
    def test_worktree_mode_sees_uncommitted_edit(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE.replace("# </run_agent>\n", ""))
        result = self.repo.check("--worktree")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run_agent", result.stdout)
        # ...and the committed revision is still clean
        self.assertEqual(self.repo.check("--ref", "HEAD").returncode, 0)

    def test_worktree_mode_sees_unstaged_deletion(self) -> None:
        (self.repo.root / "samples/app.py").unlink()
        result = self.repo.check("--worktree")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)

    # --- fail-loud behavior -------------------------------------------------------------
    def test_missing_manifest_is_error_not_pass(self) -> None:
        (self.repo.root / ".github" / "docs-referenced-files.json").unlink()
        self.repo.commit("rm manifest")
        result = self.repo.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("manifest not found", result.stderr)

    def test_malformed_manifest_is_error(self) -> None:
        (self.repo.root / ".github" / "docs-referenced-files.json").write_text(
            "{not json", encoding="utf-8"
        )
        self.repo.commit("bad manifest")
        self.assertEqual(self.repo.check().returncode, 2)

    def test_schema_version_mismatch_is_error(self) -> None:
        (self.repo.root / ".github" / "docs-referenced-files.json").write_text(
            json.dumps({"schemaVersion": 99, "files": []}), encoding="utf-8"
        )
        self.repo.commit("bad schema")
        self.assertEqual(self.repo.check().returncode, 2)

    def test_absolute_and_traversal_paths_rejected(self) -> None:
        for bad in ("/samples/app.py", "../outside.py"):
            with self.subTest(path=bad):
                self.repo.write_manifest([{"path": bad, "mode": "whole-file"}])
                self.assertEqual(self.repo.check().returncode, 2)

    def test_duplicate_manifest_entry_rejected(self) -> None:
        self.repo.write_manifest(
            [
                {"path": "samples/app.py", "mode": "whole-file"},
                {"path": "samples/app.py", "mode": "whole-file"},
            ]
        )
        self.assertEqual(self.repo.check().returncode, 2)

    def test_delimited_entry_without_snippets_rejected(self) -> None:
        self.repo.write_manifest([{"path": "samples/app.py", "mode": "delimited"}])
        self.assertEqual(self.repo.check().returncode, 2)

    def test_unresolvable_ref_is_error(self) -> None:
        result = self.repo.check("--ref", "does-not-exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot resolve ref", result.stderr)

    # --- notebooks: named cells must survive -------------------------------------------
    def _notebook(self, cells: list[dict]) -> str:
        return json.dumps(
            {
                "cells": cells,
                "metadata": {
                    # Notebook-level `name` keys that a naive `"name":` search would wrongly match.
                    "kernelspec": {"name": "python3", "display_name": "Python 3"},
                    "language_info": {"name": "python"},
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            indent=1,
        )

    def _seed_notebook(self, cells: list[dict], names: list[str]) -> None:
        self.repo.write("samples/demo.ipynb", self._notebook(cells))
        self.repo.write_manifest(
            [{"path": "samples/demo.ipynb", "mode": "notebook-cell", "snippets": names}]
        )
        self.repo.commit("notebook")

    NAMED_CELL = {
        "cell_type": "code",
        "metadata": {"name": "gen-training-data-locally"},
        "source": ["print('train')\n"],
        "outputs": [],
        "execution_count": None,
    }
    PLAIN_CELL = {
        "cell_type": "code",
        "metadata": {},
        "source": ["print('other')\n"],
        "outputs": [],
        "execution_count": None,
    }

    def test_notebook_named_cell_intact_passes(self) -> None:
        self._seed_notebook(
            [self.PLAIN_CELL, self.NAMED_CELL], ["gen-training-data-locally"]
        )
        result = self.repo.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_notebook_deleted_cell_fails(self) -> None:
        self._seed_notebook(
            [self.PLAIN_CELL, self.NAMED_CELL], ["gen-training-data-locally"]
        )
        self.repo.write("samples/demo.ipynb", self._notebook([self.PLAIN_CELL]))
        self.repo.commit("delete named cell")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[notebook cell broken] samples/demo.ipynb", result.stdout)
        self.assertIn("gen-training-data-locally", result.stdout)

    def test_notebook_removed_name_metadata_fails(self) -> None:
        self._seed_notebook([self.NAMED_CELL], ["gen-training-data-locally"])
        stripped = dict(self.NAMED_CELL, metadata={})
        self.repo.write("samples/demo.ipynb", self._notebook([stripped]))
        self.repo.commit("strip name metadata")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("name metadata was removed", result.stdout)

    def test_notebook_renamed_cell_fails(self) -> None:
        self._seed_notebook([self.NAMED_CELL], ["gen-training-data-locally"])
        renamed = dict(self.NAMED_CELL, metadata={"name": "something-else"})
        self.repo.write("samples/demo.ipynb", self._notebook([renamed]))
        self.repo.commit("rename cell")
        self.assertEqual(self.repo.check().returncode, 1)

    def test_notebook_emptied_cell_fails(self) -> None:
        self._seed_notebook([self.NAMED_CELL], ["gen-training-data-locally"])
        emptied = dict(self.NAMED_CELL, source=[])
        self.repo.write("samples/demo.ipynb", self._notebook([emptied]))
        self.repo.commit("empty cell")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("empty", result.stdout)

    def test_notebook_duplicate_cell_name_fails(self) -> None:
        self._seed_notebook(
            [self.NAMED_CELL, dict(self.NAMED_CELL)], ["gen-training-data-locally"]
        )
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("claim this name", result.stdout)

    def test_notebook_edits_to_cell_body_still_pass(self) -> None:
        self._seed_notebook([self.NAMED_CELL], ["gen-training-data-locally"])
        edited = dict(self.NAMED_CELL, source=["print('completely rewritten')\n"])
        self.repo.write("samples/demo.ipynb", self._notebook([edited]))
        self.repo.commit("edit body")
        self.assertEqual(self.repo.check().returncode, 0)

    def test_notebook_level_metadata_name_is_not_a_cell(self) -> None:
        text = self._notebook([self.PLAIN_CELL])
        self.assertEqual(checker.notebook_cell_names(text, "samples/demo.ipynb"), [])

    def test_notebook_rejects_delimited_mode(self) -> None:
        self.repo.write("samples/demo.ipynb", self._notebook([self.NAMED_CELL]))
        self.repo.write_manifest(
            [{"path": "samples/demo.ipynb", "mode": "delimited", "snippets": ["x"]}]
        )
        self.repo.commit("bad mode")
        result = self.repo.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("notebook-cell", result.stderr)

    def test_notebook_cell_mode_rejected_for_non_notebook(self) -> None:
        self.repo.write_manifest(
            [{"path": "samples/app.py", "mode": "notebook-cell", "snippets": ["x"]}]
        )
        self.assertEqual(self.repo.check().returncode, 2)

    def test_malformed_notebook_is_reported(self) -> None:
        self.repo.write("samples/demo.ipynb", "{not json")
        self.repo.write_manifest(
            [{"path": "samples/demo.ipynb", "mode": "notebook-cell", "snippets": ["x"]}]
        )
        self.repo.commit("broken notebook")
        result = self.repo.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[unreadable]", result.stdout)

    def test_notebook_whole_file_mode_ignores_cells(self) -> None:
        self.repo.write("samples/demo.ipynb", self._notebook([self.PLAIN_CELL]))
        self.repo.write_manifest([{"path": "samples/demo.ipynb", "mode": "whole-file"}])
        self.repo.commit("whole notebook")
        self.assertEqual(self.repo.check().returncode, 0)

    # --- seeding -------------------------------------------------------------------------
    def test_seed_writes_bare_paths_by_default(self) -> None:
        self.repo.write("samples/policy.json", '{"a": 1}\n')
        self.repo.commit("add json")
        result = self.repo.check(
            "--seed", "--path", "samples/app.py", "--path", "samples/policy.json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(
            (self.repo.root / ".github" / "docs-referenced-files.json").read_text()
        )
        # samples/app.py was already pinned by the fixture, and a reseed must not downgrade it.
        self.assertIsInstance(data["files"][0], dict)
        self.assertEqual(data["files"][0]["path"], "samples/app.py")
        # A freshly seeded path is written in the everyday bare form.
        self.assertEqual(data["files"][1], "samples/policy.json")

    def test_seed_pin_infers_notebook_cell_mode(self) -> None:
        self.repo.write("samples/demo.ipynb", self._notebook([self.PLAIN_CELL, self.NAMED_CELL]))
        self.repo.commit("add notebook")
        result = self.repo.check("--seed", "--pin", "--path", "samples/demo.ipynb")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(
            (self.repo.root / ".github" / "docs-referenced-files.json").read_text()
        )
        entry = {
            item["path"]: item for item in data["files"] if isinstance(item, dict)
        }["samples/demo.ipynb"]
        self.assertEqual(entry["mode"], "notebook-cell")
        self.assertEqual(entry["snippets"], ["gen-training-data-locally"])

    def test_seed_pin_infers_modes_and_snippets(self) -> None:
        self.repo.write("samples/policy.json", '{"a": 1}\n')
        self.repo.commit("add json")
        result = self.repo.check(
            "--seed", "--pin", "--path", "samples/app.py", "--path", "samples/policy.json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(
            (self.repo.root / ".github" / "docs-referenced-files.json").read_text()
        )
        by_path = {item["path"]: item for item in data["files"]}
        self.assertEqual(by_path["samples/app.py"]["snippets"], ["create_agent", "run_agent"])
        self.assertEqual(by_path["samples/policy.json"]["mode"], "whole-file")


class AutoModeTests(unittest.TestCase):
    """Bare-path manifest entries: expectations discovered from the file, removal caught vs base."""

    def setUp(self) -> None:
        self.repo = RepoFixture()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("samples/app.py", PY_SAMPLE)
        # A bare string, not an object -- the everyday form the docs team maintains.
        self.repo.write_manifest(["samples/app.py"])
        self.repo.commit("initial")
        self.base = subprocess.run(
            ["git", "-C", str(self.repo.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def check(self, *args: str) -> subprocess.CompletedProcess:
        return self.repo.check("--base-ref", self.base, *args)

    def test_bare_path_entry_passes_when_intact(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bare_path_detects_removed_tag_against_base(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE.replace("# <create_agent>\n", ""))
        self.repo.commit("drop tag")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("create_agent", result.stdout)

    def test_bare_path_detects_whole_region_removal(self) -> None:
        self.repo.write("samples/app.py", "# <run_agent>\nagent.run()\n# </run_agent>\n")
        self.repo.commit("drop region")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("`create_agent` is gone", result.stdout)

    def test_bare_path_detects_deletion(self) -> None:
        (self.repo.root / "samples/app.py").unlink()
        self.repo.commit("delete")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[missing] samples/app.py", result.stdout)

    def test_bare_path_allows_adding_a_new_snippet(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE + "\n# <extra>\nx = 1\n# </extra>\n")
        self.repo.commit("add snippet")
        self.assertEqual(self.check().returncode, 0)

    def test_bare_path_allows_editing_snippet_body(self) -> None:
        self.repo.write(
            "samples/app.py",
            PY_SAMPLE.replace("agent = client.create_agent()", "agent = build()  # rewritten"),
        )
        self.repo.commit("edit body")
        self.assertEqual(self.check().returncode, 0)

    def test_bare_path_notebook_cell_removal_detected(self) -> None:
        notebook = json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {"name": "gen-training-data-locally"},
                        "source": ["print('x')\n"],
                        "outputs": [],
                        "execution_count": None,
                    }
                ],
                "metadata": {"language_info": {"name": "python"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            indent=1,
        )
        self.repo.write("samples/demo.ipynb", notebook)
        self.repo.write_manifest(["samples/app.py", "samples/demo.ipynb"])
        self.repo.commit("add notebook")
        base = subprocess.run(
            ["git", "-C", str(self.repo.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        stripped = json.loads(notebook)
        stripped["cells"][0]["metadata"] = {}
        self.repo.write("samples/demo.ipynb", json.dumps(stripped, indent=1))
        self.repo.commit("strip cell name")
        result = self.repo.check("--base-ref", base)
        self.assertEqual(result.returncode, 1)
        self.assertIn("gen-training-data-locally", result.stdout)

    def test_file_added_in_this_pr_is_structurally_validated(self) -> None:
        # Not present at the base: there is nothing to compare to, so the head's own structure
        # is checked rather than the entry silently expecting nothing.
        self.repo.write("samples/new.py", "# <only_open>\nx = 1\n")
        self.repo.write_manifest(["samples/app.py", "samples/new.py"])
        self.repo.commit("add new file")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("never closed", result.stdout)

    def test_missing_base_warns_and_degrades_loudly(self) -> None:
        self.repo.write("samples/app.py", PY_SAMPLE.replace("# <create_agent>\n", ""))
        self.repo.commit("drop tag")
        result = self.repo.check()  # no --base-ref
        self.assertIn("no --base-ref given", result.stderr)
        # Structure is still checked, so the now-orphaned closing tag is caught.
        self.assertEqual(result.returncode, 1)

    def test_auto_entry_may_not_list_snippets(self) -> None:
        self.repo.write_manifest(
            [{"path": "samples/app.py", "mode": "auto", "snippets": ["create_agent"]}]
        )
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("discovers snippets itself", result.stderr)

    def test_pinned_entry_needs_no_base(self) -> None:
        self.repo.write_manifest(
            [{"path": "samples/app.py", "mode": "delimited", "snippets": ["create_agent"]}]
        )
        self.repo.write("samples/app.py", "# <run_agent>\nagent.run()\n# </run_agent>\n")
        self.repo.commit("drop pinned snippet")
        result = self.repo.check()  # no base at all
        self.assertEqual(result.returncode, 1)
        self.assertIn("`create_agent` is gone", result.stdout)
        self.assertNotIn("no --base-ref given", result.stderr)


class RepoManifestTests(unittest.TestCase):
    """The real manifest and workflow in THIS repo must stay coherent."""

    def test_repo_manifest_is_valid(self) -> None:
        entries = checker.load_manifest(MANIFEST)
        self.assertGreater(len(entries), 0)

    def test_workflow_is_fork_safe_and_unskippable(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        directives = "\n".join(
            line for line in text.split("\n") if not line.lstrip().startswith("#")
        )
        self.assertIn("on:\n  pull_request:", directives)
        self.assertNotIn("pull_request_target", directives)
        self.assertIn("permissions:\n  contents: read", directives)
        self.assertNotIn("secrets.", directives)
        # A `paths:` filter under pull_request would let a required check conclude `skipped`.
        pr_block = directives.split("on:\n  pull_request:", 1)[1].split("\npermissions:", 1)[0]
        self.assertNotIn("paths:", pr_block)
        self.assertIn("fetch-depth: 0", directives)
        self.assertIn("check-docs-referenced-files.py", directives)


if __name__ == "__main__":
    unittest.main(verbosity=2)

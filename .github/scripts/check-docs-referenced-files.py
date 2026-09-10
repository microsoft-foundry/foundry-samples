#!/usr/bin/env python3
"""Guard the sample files that Microsoft Learn articles include by reference.

Learn articles pull code out of this repo with `:::code source="<path>" id="<snippet>":::`.
Three changes here break the published docs build:

  1. the referenced file is DELETED
  2. the referenced file is RENAMED or MOVED (the `source=` path stops resolving)
  3. a snippet delimiter comment (`# <create_agent>` ... `# </create_agent>`) is REMOVED,
     so the `id=` region stops resolving
  4. for a notebook, a referenced CELL is deleted, or its `"metadata": {"name": "..."}` is
     removed, so the article's cell reference stops resolving

`.github/docs-referenced-files.json` is the manifest of what the docs reference. Day to day it is
just a list of paths -- add a line to protect a file, delete a line to stop protecting it:

    "files": [
      "samples/python/quickstart/create-agent/quickstart-create-agent.py",
      "samples/REST/quickstart/quickstart-responses.sh"
    ]

A path's snippet ids are discovered from the file itself, so nobody has to maintain them by hand.
Expectations are read from the PR BASE revision, which is what makes a REMOVED tag detectable: the
base still has the delimiter the head just lost. An entry can instead be written as an object to
pin an explicit mode/snippet list, which makes that entry independent of the base revision.

Exit codes:
  0  every referenced file and snippet is intact
  1  a docs reference is broken -- the PR must not merge until the docs team is contacted
  2  checker/manifest/git error (fail loud, never fail open)

Usage:
  python .github/scripts/check-docs-referenced-files.py --base-ref origin/main   # full check
  python .github/scripts/check-docs-referenced-files.py --worktree --base-ref origin/main
  python .github/scripts/check-docs-referenced-files.py --ref <sha> --base-ref <sha>

Docs-team maintenance (regenerates the manifest from the working tree):
  python .github/scripts/check-docs-referenced-files.py --seed --from-codeowners
  python .github/scripts/check-docs-referenced-files.py --seed --path samples/python/x/app.py
  python .github/scripts/check-docs-referenced-files.py --seed --pin   # explicit snippet lists
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

SCHEMA_VERSION = 1
DEFAULT_MANIFEST = ".github/docs-referenced-files.json"
CODEOWNERS_PATH = ".github/CODEOWNERS"
DOCS_TEAM = "@microsoft-foundry/AI-Platform-Docs"
DOCS_TEAM_EMAIL = "General - AI Platform Docs <7f0acdb3.microsoft.com@amer.teams.ms>"

MODE_AUTO = "auto"
MODE_DELIMITED = "delimited"
MODE_WHOLE_FILE = "whole-file"
MODE_NOTEBOOK_CELL = "notebook-cell"
VALID_MODES = (MODE_AUTO, MODE_DELIMITED, MODE_WHOLE_FILE, MODE_NOTEBOOK_CELL)

NOTEBOOK_EXT = ".ipynb"

# A snippet delimiter is a COMMENT-ONLY line: `<id>` or `</id>` and nothing else. Requiring the
# whole comment body to be the tag is what keeps C# generics (`List<ToolDefinition>`) and JSON
# strings out of the tag set.
TAG_RE = re.compile(r"^</?[A-Za-z0-9_.\-]+>$")

# Comment syntax per extension. Unknown extensions are rejected for `delimited` entries rather
# than silently scanned with a guessed marker (a guess that finds zero tags would fail open).
LINE_COMMENT_MARKERS: dict[str, tuple[str, ...]] = {
    ".bicep": ("//",),
    ".cs": ("//",),
    ".env": ("#",),
    ".example": ("#",),  # .env.example
    ".go": ("//",),
    ".java": ("//",),
    ".js": ("//",),
    ".jsx": ("//",),
    ".mjs": ("//",),
    ".ps1": ("#",),
    ".py": ("#",),
    ".rs": ("//",),
    ".sh": ("#",),
    ".sql": ("--",),
    ".template": ("#",),  # .env.template
    ".tf": ("#", "//"),
    ".tfvars": ("#", "//"),
    ".ts": ("//",),
    ".tsx": ("//",),
    ".yaml": ("#",),
    ".yml": ("#",),
}

BLOCK_COMMENT_MARKERS: dict[str, tuple[str, str]] = {
    ".csproj": ("<!--", "-->"),
    ".html": ("<!--", "-->"),
    ".md": ("<!--", "-->"),
    ".props": ("<!--", "-->"),
    ".targets": ("<!--", "-->"),
    ".xml": ("<!--", "-->"),
}

# Formats with no comment syntax at all: they can only ever be whole-file references.
NO_COMMENT_EXTS = {".json", ".ipynb"}

REGULAR_FILE_MODES = {"100644", "100755"}

CONTACT = (
    "Contact the Microsoft Foundry docs team (AI Platform Docs) BEFORE merging this PR:\n"
    f"  Teams channel:  {DOCS_TEAM_EMAIL}\n"
    f"  Or on this PR:  @-mention {DOCS_TEAM}\n"
    "They must retarget the affected Learn articles first; only then can the manifest entry "
    f"in {DEFAULT_MANIFEST} be updated."
)


class CheckerError(Exception):
    """Configuration/manifest/git problem -- exit 2, never a silent pass."""


# --------------------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------------------
def git(repo_root: Path, *args: str, binary: bool = False) -> bytes | str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise CheckerError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def repo_root_from(start: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise CheckerError(f"not inside a git repository: {start}")
    return Path(proc.stdout.strip())


class Tree:
    """The set of tracked paths to validate, plus how to read their content.

    `ref` mode reads a committed revision. `worktree` mode reads the index for path existence
    (so exact case comes from git, not from a case-insensitive macOS/Windows filesystem) and
    on-disk content for uncommitted edits.
    """

    def __init__(self, repo_root: Path, ref: str | None, worktree: bool) -> None:
        self.repo_root = repo_root
        self.ref = ref
        self.worktree = worktree
        self.modes: dict[str, str] = {}
        if worktree:
            self._load_index()
        else:
            self._load_ref()

    @property
    def label(self) -> str:
        return "working tree" if self.worktree else f"revision {self.ref}"

    def _load_ref(self) -> None:
        assert self.ref is not None
        try:
            git(self.repo_root, "rev-parse", "--verify", f"{self.ref}^{{commit}}")
        except CheckerError as exc:
            raise CheckerError(
                f"cannot resolve ref '{self.ref}'. In CI, check out with fetch-depth: 0; "
                f"locally, try `git fetch --unshallow`.\n  {exc}"
            ) from exc
        raw = git(self.repo_root, "ls-tree", "-r", "-z", self.ref, binary=True)
        for record in raw.split(b"\0"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            fields = meta.split(b" ")
            if len(fields) < 3:
                continue
            self.modes[path.decode("utf-8", "surrogateescape")] = fields[0].decode()

    def _load_index(self) -> None:
        raw = git(self.repo_root, "ls-files", "-s", "-z", binary=True)
        for record in raw.split(b"\0"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            fields = meta.split(b" ")
            if len(fields) < 3:
                continue
            self.modes[path.decode("utf-8", "surrogateescape")] = fields[0].decode()

    def file_mode(self, path: str) -> str | None:
        return self.modes.get(path)

    def read_text(self, path: str) -> str:
        if self.worktree:
            disk = self.repo_root / path
            if disk.is_symlink():
                raise CheckerError(f"{path}: worktree path is a symbolic link, not a regular file")
            if disk.is_file():
                raw = disk.read_bytes()
            else:  # staged deletion or a staged-but-not-materialized path
                raw = git(self.repo_root, "cat-file", "blob", f":{path}", binary=True)
        else:
            raw = git(self.repo_root, "cat-file", "blob", f"{self.ref}:{path}", binary=True)
        try:
            text = raw.decode("utf-8-sig")  # utf-8-sig strips a leading BOM
        except UnicodeDecodeError as exc:
            raise CheckerError(f"{path}: not valid UTF-8, cannot scan for snippet tags ({exc})")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def exists_on_disk(self, path: str) -> bool:
        return (self.repo_root / path).is_file()


# --------------------------------------------------------------------------------------
# snippet tag parsing
# --------------------------------------------------------------------------------------
class Tag:
    __slots__ = ("name", "closing", "line")

    def __init__(self, name: str, closing: bool, line: int) -> None:
        self.name = name
        self.closing = closing
        self.line = line


def comment_markers(path: str) -> tuple[tuple[str, ...], tuple[str, str] | None]:
    """Return (line markers, block marker pair) for a path, or raise for unsupported types."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == NOTEBOOK_EXT:
        raise CheckerError(
            f"{path}: notebooks identify snippets by cell metadata, not comment delimiters. "
            f'Use "mode": "{MODE_NOTEBOOK_CELL}" with the cell names, or '
            f'"mode": "{MODE_WHOLE_FILE}".'
        )
    if suffix in NO_COMMENT_EXTS:
        raise CheckerError(
            f"{path}: '{suffix}' has no comment syntax, so it cannot carry snippet delimiters. "
            f"Use \"mode\": \"{MODE_WHOLE_FILE}\" for this entry."
        )
    line = LINE_COMMENT_MARKERS.get(suffix, ())
    block = BLOCK_COMMENT_MARKERS.get(suffix)
    if not line and not block:
        raise CheckerError(
            f"{path}: unknown file type '{suffix or '(no extension)'}'. Add its comment syntax to "
            f"LINE_COMMENT_MARKERS/BLOCK_COMMENT_MARKERS in {Path(__file__).name}, or use "
            f'"mode": "{MODE_WHOLE_FILE}".'
        )
    return line, block


def parse_tags(text: str, path: str) -> list[Tag]:
    """Extract snippet delimiter tags: comment-only lines whose entire body is `<id>`/`</id>`."""
    line_markers, block = comment_markers(path)
    tags: list[Tag] = []
    for number, raw_line in enumerate(text.split("\n"), start=1):
        stripped = raw_line.strip().lstrip("\ufeff").strip()
        body: str | None = None
        if block and stripped.startswith(block[0]):
            inner = stripped[len(block[0]) :]
            if inner.endswith(block[1]):
                body = inner[: -len(block[1])].strip()
        if body is None:
            for marker in line_markers:
                if stripped.startswith(marker):
                    body = stripped[len(marker) :].strip()
                    break
        if body is None or not TAG_RE.match(body):
            continue
        closing = body.startswith("</")
        name = body[2:-1] if closing else body[1:-1]
        tags.append(Tag(name, closing, number))
    return tags


def region_has_content(text: str, open_line: int, close_line: int) -> bool:
    lines = text.split("\n")
    return any(line.strip() for line in lines[open_line : close_line - 1])


def notebook_cell_names(text: str, path: str) -> list[str]:
    """Return `cells[*].metadata.name` values, in order.

    Only per-cell metadata counts. Notebook-level metadata (kernelspec/language_info `name`)
    is deliberately ignored -- a raw text search for `"name":` would match those and produce
    false positives.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckerError(f"{path}: not valid notebook JSON ({exc})") from exc
    if not isinstance(document, dict):
        raise CheckerError(f"{path}: notebook JSON must be an object")
    cells = document.get("cells")
    if not isinstance(cells, list):
        raise CheckerError(f"{path}: notebook has no 'cells' array")
    names: list[str] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        metadata = cell.get("metadata")
        if not isinstance(metadata, dict):
            continue
        name = metadata.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def notebook_cell_source(text: str, name: str) -> str:
    """Concatenated source of the first cell whose metadata.name is `name` ('' if absent)."""
    document = json.loads(text)
    for cell in document.get("cells", []):
        if not isinstance(cell, dict):
            continue
        metadata = cell.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("name") != name:
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            return "".join(str(part) for part in source)
        return str(source)
    return ""


def check_notebook_cells(text: str, path: str, expected: list[str]) -> list[str]:
    """Verify each expected named cell still exists, keeps its name, and has content."""
    names = notebook_cell_names(text, path)
    problems: list[str] = []
    for name in expected:
        count = names.count(name)
        if count == 0:
            problems.append(
                f'cell `{name}` is gone -- no cell has "metadata": {{"name": "{name}"}}. '
                "Either the cell was deleted or its name metadata was removed; a Learn article "
                "includes that cell by this name."
            )
            continue
        if count > 1:
            problems.append(
                f"cell `{name}`: {count} cells claim this name -- it must be unique so the "
                "article includes an unambiguous cell"
            )
            continue
        if not notebook_cell_source(text, name).strip():
            problems.append(
                f"cell `{name}`: the cell is empty -- the docs would publish a blank code block"
            )
    return problems


def check_snippets(text: str, path: str, expected: list[str]) -> list[str]:
    """Return human-readable problems with the expected snippet regions in `text`."""
    tags = parse_tags(text, path)
    problems: list[str] = []

    # Structural nesting: nested regions are fine, crossing regions are not.
    stack: list[Tag] = []
    for tag in tags:
        if not tag.closing:
            stack.append(tag)
            continue
        if not stack:
            problems.append(f"line {tag.line}: `</{tag.name}>` has no matching opening tag")
        elif stack[-1].name != tag.name:
            problems.append(
                f"line {tag.line}: `</{tag.name}>` closes out of order "
                f"(expected `</{stack[-1].name}>` opened on line {stack[-1].line}) -- "
                "snippet regions may nest but must not overlap"
            )
            stack.pop()
        else:
            stack.pop()
    for tag in stack:
        problems.append(f"line {tag.line}: `<{tag.name}>` is never closed")

    for name in expected:
        opens = [t for t in tags if t.name == name and not t.closing]
        closes = [t for t in tags if t.name == name and t.closing]
        if not opens and not closes:
            problems.append(
                f"snippet `{name}` is gone -- both `<{name}>` and `</{name}>` are missing"
            )
            continue
        if not opens:
            problems.append(f"snippet `{name}`: opening tag `<{name}>` was removed")
            continue
        if not closes:
            problems.append(f"snippet `{name}`: closing tag `</{name}>` was removed")
            continue
        if len(opens) > 1 or len(closes) > 1:
            problems.append(
                f"snippet `{name}`: expected exactly one `<{name}>`/`</{name}>` pair, found "
                f"{len(opens)} opening and {len(closes)} closing tags"
            )
            continue
        if opens[0].line > closes[0].line:
            problems.append(
                f"snippet `{name}`: `</{name}>` (line {closes[0].line}) comes before "
                f"`<{name}>` (line {opens[0].line})"
            )
            continue
        if not region_has_content(text, opens[0].line, closes[0].line):
            problems.append(
                f"snippet `{name}`: the region between lines {opens[0].line} and "
                f"{closes[0].line} is empty -- the docs would publish a blank code block"
            )
    return problems


# --------------------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------------------
class Entry:
    __slots__ = ("path", "mode", "snippets", "note")

    def __init__(self, path: str, mode: str, snippets: list[str], note: str) -> None:
        self.path = path
        self.mode = mode
        self.snippets = snippets
        self.note = note


def load_manifest(manifest_path: Path) -> list[Entry]:
    if not manifest_path.is_file():
        raise CheckerError(f"manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckerError(f"{manifest_path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise CheckerError(f"{manifest_path}: top level must be an object")
    version = data.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise CheckerError(
            f"{manifest_path}: schemaVersion {version!r} is not supported "
            f"(this checker understands {SCHEMA_VERSION})"
        )
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise CheckerError(f"{manifest_path}: 'files' must be a non-empty array")

    entries: list[Entry] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        where = f"{manifest_path}: files[{index}]"
        # A bare string is the everyday form: just the path. Everything about it is discovered,
        # and snippet removal is caught by comparing against the PR base.
        if isinstance(item, str):
            item = {"path": item, "mode": MODE_AUTO}
        if not isinstance(item, dict):
            raise CheckerError(f"{where}: must be a path string or an object")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise CheckerError(f"{where}: 'path' must be a non-empty string")
        if path.startswith("/") or "\\" in path or ".." in PurePosixPath(path).parts:
            raise CheckerError(
                f"{where}: 'path' must be a repo-relative POSIX path without '..' (got {path!r})"
            )
        if path in seen:
            raise CheckerError(f"{where}: duplicate path {path!r}")
        seen.add(path)
        mode = item.get("mode", MODE_AUTO)
        if mode not in VALID_MODES:
            raise CheckerError(f"{where}: 'mode' must be one of {VALID_MODES} (got {mode!r})")
        snippets = item.get("snippets", [])
        if not isinstance(snippets, list) or not all(
            isinstance(s, str) and s for s in snippets
        ):
            raise CheckerError(f"{where}: 'snippets' must be an array of non-empty strings")
        if len(set(snippets)) != len(snippets):
            raise CheckerError(f"{where}: 'snippets' contains duplicates")
        if mode == MODE_AUTO and snippets:
            raise CheckerError(
                f"{where}: mode '{MODE_AUTO}' discovers snippets itself and must not list them "
                f"(use '{MODE_DELIMITED}'/'{MODE_NOTEBOOK_CELL}' to pin an explicit list)"
            )
        if mode == MODE_DELIMITED and not snippets:
            raise CheckerError(
                f"{where}: mode '{MODE_DELIMITED}' requires at least one snippet id "
                f"(use '{MODE_WHOLE_FILE}' when the article includes the entire file)"
            )
        if mode == MODE_NOTEBOOK_CELL:
            if PurePosixPath(path).suffix.lower() != NOTEBOOK_EXT:
                raise CheckerError(
                    f"{where}: mode '{MODE_NOTEBOOK_CELL}' only applies to {NOTEBOOK_EXT} files"
                )
            if not snippets:
                raise CheckerError(
                    f"{where}: mode '{MODE_NOTEBOOK_CELL}' requires at least one cell name "
                    f"(use '{MODE_WHOLE_FILE}' when the article includes the whole notebook)"
                )
        if mode == MODE_DELIMITED and PurePosixPath(path).suffix.lower() == NOTEBOOK_EXT:
            raise CheckerError(
                f"{where}: notebooks use cell metadata names -- "
                f"use mode '{MODE_NOTEBOOK_CELL}' instead of '{MODE_DELIMITED}'"
            )
        if mode == MODE_WHOLE_FILE and snippets:
            raise CheckerError(f"{where}: mode '{MODE_WHOLE_FILE}' must not list snippets")
        note = item.get("note", "")
        if not isinstance(note, str):
            raise CheckerError(f"{where}: 'note' must be a string")
        entries.append(Entry(path, mode, snippets, note))
    return entries


# --------------------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------------------
def rename_hints(repo_root: Path, base_ref: str, tree: Tree) -> dict[str, str]:
    """old path -> new path, from git's rename detection. Diagnostics only, never a verdict."""
    # In worktree mode, diff base against the working tree (no second revision) so an
    # uncommitted `git mv` still produces a hint.
    args = ["diff", "-M", "--name-status", "-z", base_ref]
    if not tree.worktree:
        args.append(tree.ref or "HEAD")
    raw = git(repo_root, *args, binary=True)
    fields = [f.decode("utf-8", "surrogateescape") for f in raw.split(b"\0") if f]
    hints: dict[str, str] = {}
    index = 0
    while index < len(fields):
        status = fields[index]
        if status[:1] in ("R", "C") and index + 2 < len(fields):
            hints[fields[index + 1]] = fields[index + 2]
            index += 3
        else:
            index += 2
    return hints


def discover_expected(text: str, path: str) -> tuple[str, list[str]]:
    """Work out what a path's protected snippets are, from its own content.

    Returns (effective mode, snippet names). A file with no recognizable snippet markers --
    or a type that cannot carry them, like .json -- is treated as a whole-file reference.
    """
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == NOTEBOOK_EXT:
        deduped = list(dict.fromkeys(notebook_cell_names(text, path)))
        return (MODE_NOTEBOOK_CELL, deduped) if deduped else (MODE_WHOLE_FILE, [])
    if suffix in NO_COMMENT_EXTS:
        return MODE_WHOLE_FILE, []
    tags = parse_tags(text, path)
    deduped = list(dict.fromkeys(tag.name for tag in tags if not tag.closing))
    return (MODE_DELIMITED, deduped) if deduped else (MODE_WHOLE_FILE, [])


def resolve_entry(
    entry: Entry, head_text: str, base_text: str | None
) -> tuple[str, list[str], str | None]:
    """Return (mode, expected snippet names, warning) for an entry.

    Explicit modes are used as written. For `auto`, expectations come from the file as it exists
    at the PR BASE -- that is what makes removal detectable: the base still has the tag or named
    cell the head just lost. With no base available we can only validate the head's own structure.
    """
    if entry.mode != MODE_AUTO:
        return entry.mode, entry.snippets, None
    if base_text is not None:
        mode, names = discover_expected(base_text, entry.path)
        return mode, names, None
    mode, names = discover_expected(head_text, entry.path)
    return (
        mode,
        names,
        f"{entry.path}: no base revision available, so snippet REMOVAL cannot be detected for "
        "this auto entry; only the current file's own structure was validated.",
    )


def validate(
    entries: list[Entry],
    tree: Tree,
    hints: dict[str, str],
    base: Tree | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    for entry in entries:
        mode = tree.file_mode(entry.path)
        if mode is None:
            hint = hints.get(entry.path)
            moved = f"\n    git suggests it moved to: {hint}" if hint else ""
            failures.append(
                f"[missing] {entry.path}\n"
                f"    This file is referenced by a published Learn article and is no longer at "
                f"this exact path in the {tree.label} (deleted, renamed, or moved).{moved}"
            )
            continue
        if mode not in REGULAR_FILE_MODES:
            failures.append(
                f"[not a file] {entry.path}\n"
                f"    Expected a regular file; git reports mode {mode} "
                "(symlink, submodule, or directory)."
            )
            continue
        if tree.worktree and not tree.exists_on_disk(entry.path):
            failures.append(
                f"[missing] {entry.path}\n"
                "    Tracked by git but not present on disk (unstaged deletion)."
            )
            continue
        if entry.mode == MODE_WHOLE_FILE:
            continue
        try:
            text = tree.read_text(entry.path)
            base_text = None
            if entry.mode == MODE_AUTO and base is not None:
                if base.file_mode(entry.path) in REGULAR_FILE_MODES:
                    base_text = base.read_text(entry.path)
                else:
                    # New in this PR (or absent from the base): nothing to compare against, so
                    # validate the head's own structure instead of silently expecting nothing.
                    base_text = text
            effective_mode, expected, warning = resolve_entry(entry, text, base_text)
            # `warning` only fires when no base exists at all, which main() already reports once;
            # repeating it per entry would bury the real output under one line per manifest path.
            del warning
            if effective_mode == MODE_WHOLE_FILE:
                continue
            if effective_mode == MODE_NOTEBOOK_CELL:
                problems = check_notebook_cells(text, entry.path, expected)
            else:
                problems = check_snippets(text, entry.path, expected)
        except CheckerError as exc:
            failures.append(f"[unreadable] {entry.path}\n    {exc}")
            continue
        if problems:
            detail = "\n".join(f"    {p}" for p in problems)
            label = (
                "notebook cell broken"
                if effective_mode == MODE_NOTEBOOK_CELL
                else "snippet broken"
            )
            failures.append(f"[{label}] {entry.path}\n{detail}")
    return failures


# --------------------------------------------------------------------------------------
# seeding (docs-team maintenance)
# --------------------------------------------------------------------------------------
def codeowners_docs_paths(repo_root: Path) -> list[str]:
    """Docs-team-owned FILE patterns in CODEOWNERS, minus this check's own enforcement paths."""
    enforcement = {
        DEFAULT_MANIFEST,
        ".github/scripts/check-docs-referenced-files.py",
        ".github/workflows/docs-referenced-files.yml",
    }
    paths: list[str] = []
    codeowners = repo_root / CODEOWNERS_PATH
    if not codeowners.is_file():
        raise CheckerError(f"{CODEOWNERS_PATH} not found")
    for line in codeowners.read_text(encoding="utf-8").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if DOCS_TEAM.lower() not in (f.lower() for f in fields[1:]):
            continue
        pattern = fields[0]
        if pattern.endswith("/"):
            continue  # directory ownership is not a file-level docs reference
        relative = pattern.lstrip("/")
        if relative in enforcement:
            continue  # the gate's own files are owned, but they are not docs-referenced samples
        paths.append(relative)
    return sorted(set(paths))


def seed(repo_root: Path, manifest_path: Path, paths: list[str], tree: Tree, pin: bool) -> int:
    """Write the manifest.

    Default output is a bare path string per file -- the everyday form the docs team maintains by
    adding or deleting one line. `--pin` instead records the discovered mode and snippet ids
    explicitly, which makes the check independent of the PR base for those entries.
    """
    existing: dict[str, Entry] = {}
    if manifest_path.is_file():
        try:
            for entry in load_manifest(manifest_path):
                existing[entry.path] = entry
        except CheckerError:
            existing = {}

    files: list[object] = []
    for path in paths:
        if tree.file_mode(path) is None:
            print(f"skip (not tracked): {path}", file=sys.stderr)
            continue
        previous = existing.get(path)
        if not pin and previous is None:
            files.append(path)
            continue
        if not pin and previous is not None:
            item: dict[str, object] = {"path": path, "mode": previous.mode}
            if previous.snippets:
                item["snippets"] = previous.snippets
            if previous.note:
                item["note"] = previous.note
            files.append(item if previous.mode != MODE_AUTO or previous.note else path)
            continue
        try:
            entry_mode, snippets = discover_expected(tree.read_text(path), path)
        except CheckerError as exc:
            print(f"skip (cannot scan): {path}: {exc}", file=sys.stderr)
            entry_mode, snippets = MODE_WHOLE_FILE, []
        item: dict[str, object] = {"path": path, "mode": entry_mode}
        if snippets:
            item["snippets"] = snippets
        if previous and previous.note:
            item["note"] = previous.note
        files.append(item)

    document = {
        "schemaVersion": SCHEMA_VERSION,
        "$comment": (
            "Files that published Microsoft Learn articles include by reference. Owned by the "
            "AI Platform Docs team. To protect a file, add its path to 'files' -- one string per "
            "line is all you need. Renaming or deleting a listed file, or removing one of its "
            "snippet delimiter comments or named notebook cells, breaks the docs build; "
            ".github/workflows/docs-referenced-files.yml enforces this on every PR. "
            "Do not edit without the docs team."
        ),
        "contact": {
            "team": DOCS_TEAM,
            "teamsChannelEmail": DOCS_TEAM_EMAIL,
        },
        "files": sorted(
            files, key=lambda item: item if isinstance(item, str) else str(item["path"])
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path} with {len(files)} entries")
    return EXIT_OK


# --------------------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify that docs-referenced sample files and snippet delimiters are intact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="manifest path")
    parser.add_argument("--ref", default="HEAD", help="revision to validate (default: HEAD)")
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="validate the working tree (staged + unstaged edits) instead of a revision",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help=(
            "the PR base revision. Auto entries take their expected snippets from here, so this "
            "is what makes a REMOVED tag/cell detectable. Also supplies rename hints."
        ),
    )
    parser.add_argument("--seed", action="store_true", help="docs team: regenerate the manifest")
    parser.add_argument(
        "--pin",
        action="store_true",
        help="with --seed: write explicit mode/snippets instead of bare paths",
    )
    parser.add_argument(
        "--from-codeowners",
        action="store_true",
        help=f"with --seed: take paths owned by {DOCS_TEAM} in {CODEOWNERS_PATH}",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="with --seed: add/refresh a specific path (repeatable)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = repo_root_from(Path.cwd())
        manifest_path = repo_root / args.manifest

        if args.seed:
            tree = Tree(repo_root, None, worktree=True)
            paths = list(args.path)
            if args.from_codeowners:
                paths.extend(codeowners_docs_paths(repo_root))
            if not paths and manifest_path.is_file():
                paths = [entry.path for entry in load_manifest(manifest_path)]
            elif args.path and manifest_path.is_file():
                paths.extend(entry.path for entry in load_manifest(manifest_path))
            if not paths:
                raise CheckerError("--seed needs --from-codeowners, --path, or an existing manifest")
            return seed(repo_root, manifest_path, sorted(set(paths)), tree, args.pin)

        entries = load_manifest(manifest_path)
        tree = Tree(repo_root, None if args.worktree else args.ref, worktree=args.worktree)
        hints: dict[str, str] = {}
        base: Tree | None = None
        warnings: list[str] = []
        if args.base_ref:
            try:
                base = Tree(repo_root, args.base_ref, worktree=False)
                hints = rename_hints(repo_root, args.base_ref, tree)
            except CheckerError as exc:
                print(f"note: base revision unavailable ({exc})", file=sys.stderr)
                base = None
        needs_base = any(entry.mode == MODE_AUTO for entry in entries)
        if needs_base and base is None:
            warnings.append(
                "no --base-ref given: auto entries fall back to structure-only validation, so a "
                "REMOVED snippet tag or named notebook cell will NOT be reported. CI always "
                "passes the PR base."
            )
        failures = validate(entries, tree, hints, base, warnings)
    except CheckerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    for warning in dict.fromkeys(warnings):
        print(f"warning: {warning}", file=sys.stderr)

    if not failures:
        print(
            f"OK: all {len(entries)} docs-referenced files and their snippet regions are intact "
            f"({tree.label})."
        )
        return EXIT_OK

    print("")
    print("=" * 88)
    print(" DOCS BUILD WOULD BREAK -- this PR changes files that Microsoft Learn publishes")
    print("=" * 88)
    print("")
    for failure in failures:
        print(failure)
        print("")
    print("-" * 88)
    print("How to fix:")
    print("  * Deleted/renamed a file? Restore the original path. Learn articles point at the")
    print("    exact path; a rename must be published on the docs side FIRST.")
    print("  * Removed a `# <name>` / `# </name>` comment? Put it back -- those delimiters mark")
    print("    the exact region an article includes; they are not dead code.")
    print("  * Deleted a notebook cell, or its `\"metadata\": {\"name\": ...}`? Restore both --")
    print("    articles include notebook cells by that name.")
    print("  * The change is genuinely required? It still cannot merge as-is.")
    print("")
    print(CONTACT)
    print("-" * 88)
    return EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

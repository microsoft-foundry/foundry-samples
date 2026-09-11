#!/usr/bin/env python3
"""Render a static, durable HTML dashboard from validation-pilot result artifacts.

Unlike render-validation-report.py (a run-scoped Markdown summary written to
the GitHub Actions job summary, which disappears once you leave that run),
this renders a single self-contained index.html snapshot meant to be published
somewhere durable (GitHub Pages) so "what is the current status of every
sample" has one stable URL that always reflects the most recent completed
run.

Every discovered sample (from the manifest, which discovery regenerates by
globbing samples/**/sample.yaml on each run) gets exactly one row, so newly
added samples appear automatically the next time the workflow runs -- no
changes needed here or in the workflow.

Security posture for a page that will be public and crawlable:
  - No diagnostic/error text is rendered, only structured fields (outcome,
    stage, duration, completion time). Full diagnostics stay behind the
    existing workflow run / artifact, which is where investigation belongs.
  - Every value is HTML-escaped; links are only ever built from the same
    validated repository/sha pattern render-validation-report.py already
    uses (see validation_pilot_common.sample_url).
  - The only inline script is a small, static, self-contained click-to-sort
    handler. It never interpolates result data into the script itself --
    all row data flows through escaped `data-sort-value` attributes read at
    runtime, so nothing from a sample/result value is ever executed as code.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from validation_pilot_common import (
    OUTCOMES,
    REPOSITORY_PATTERN,
    SHA_PATTERN,
    ContractError,
    collect,
    load_expected,
    sample_url,
)

# Severity-style ordering used both for the default row order and as the
# numeric sort value for the Status column (lower = needs more attention).
OUTCOME_RANK = {
    "sample failure": 0,
    "infrastructure/error": 1,
    "skipped/not-completed": 2,
    "passed": 3,
}
OUTCOME_CSS_CLASS = {
    "passed": "passed",
    "sample failure": "failed",
    "infrastructure/error": "errored",
    "skipped/not-completed": "skipped",
}
STAGE_LABELS = {
    "inventory eligibility": "Not validated",
    "build readiness validation": "Build check",
    "build readiness invocation": "Build check setup error",
    "live-service validation": "Live run",
    "live-service validation invocation": "Live run setup error",
    "reporting": "Reporting issue",
}

# Small inline SVG download glyph for the Artifact column -- avoids pulling
# in an external icon font or network dependency on a page that must render
# standalone from a GitHub Pages deployment.
DOWNLOAD_ICON = (
    '<svg class="icon-download" viewBox="0 0 16 16" width="14" height="14" '
    'aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M8 1a1 1 0 0 1 1 1v6.586l2.293-2.293a1 1 0 0 1 '
    '1.414 1.414l-4 4a1 1 0 0 1-1.414 0l-4-4a1 1 0 0 1 1.414-1.414L7 8.586V2a1 1 0 0 1 1-1z"/>'
    '<path fill="currentColor" d="M2 12a1 1 0 0 1 1 1v1h10v-1a1 1 0 1 1 2 0v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1z"/>'
    "</svg>"
)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def stage_label(stage: Any) -> str:
    if not isinstance(stage, str) or not stage:
        return "Unknown"
    return STAGE_LABELS.get(stage, stage)


def run_metadata(records: list[dict[str, Any]]) -> dict[str, Any]:
    return next((record.get("run") for record in records if record.get("run")), {})


def run_link(run: dict[str, Any], run_url: str | None) -> str | None:
    repository = run.get("repository")
    if run_url:
        return run_url
    run_id = run.get("run_id")
    if (
        isinstance(repository, str)
        and REPOSITORY_PATTERN.fullmatch(repository)
        and isinstance(run_id, str)
        and run_id.isdigit()
    ):
        return f"https://github.com/{repository}/actions/runs/{run_id}"
    return None


def commit_link(run: dict[str, Any]) -> str | None:
    repository = run.get("repository")
    sha = run.get("sha")
    if (
        isinstance(repository, str)
        and REPOSITORY_PATTERN.fullmatch(repository)
        and isinstance(sha, str)
        and SHA_PATTERN.fullmatch(sha)
    ):
        return f"https://github.com/{repository}/commit/{sha}"
    return None


def copilot_issue_link(
    record: dict[str, Any],
    status_href: str | None,
    artifact_href: str | None,
) -> str | None:
    """Build a review-before-submit issue that assigns the failure to Copilot."""
    if record["outcome"] not in {"sample failure", "infrastructure/error"}:
        return None

    sample = record["sample"]
    run = record.get("run", {})
    repository = run.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        return None

    run_id = run.get("run_id")
    sha = run.get("sha")
    details = [
        f"- Sample: `{sample['path']}`",
        f"- Language: `{sample['language']}`",
        f"- Outcome: `{record['outcome']}`",
        f"- Validation: `{stage_label(record.get('completed_stage'))}`",
    ]
    if isinstance(run_id, str) and run_id.isdigit():
        details.append(f"- Run ID: `{run_id}`")
    if isinstance(sha, str) and SHA_PATTERN.fullmatch(sha):
        details.append(f"- Validated commit: `{sha}`")
    if status_href:
        details.append(f"- Workflow job: {status_href}")
    if artifact_href:
        details.append(f"- Diagnostic artifact: {artifact_href}")

    body = "\n".join(
        [
            "## Validation failure",
            "",
            *details,
            "",
            "## Task",
            "",
            "Investigate this validation failure and determine the root cause. "
            "Download and inspect the diagnostic artifact when available, reproduce "
            "the failure, and make the smallest appropriate fix without weakening "
            "validation. Run the relevant tests and open a pull request with the fix.",
            "",
            "> Created from the foundry-samples validation dashboard.",
        ]
    )
    query = urlencode(
        {
            "title": f"Fix validation failure: {sample['path']}",
            "body": body,
            "assignees": "copilot-swe-agent[bot]",
        }
    )
    return f"https://github.com/{repository}/issues/new?{query}"


def load_link_map(path: Path | None, repository: str | None, url_suffix_pattern: str) -> dict[str, str]:
    """Load an optional sample-id -> URL map produced by the workflow.

    Used both for per-sample job links and per-sample artifact links. It's
    best-effort: if the file is missing, malformed, or a URL doesn't match
    the expected GitHub URL shape for this run's own repository, that entry
    (or the whole map) is silently dropped and the caller falls back to a
    less specific link.
    """
    if (
        not path
        or not path.is_file()
        or not isinstance(repository, str)
        or not REPOSITORY_PATTERN.fullmatch(repository)
    ):
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    pattern = re.compile(rf"^https://github\.com/{re.escape(repository)}/{url_suffix_pattern}$")
    return {
        sample_id: url
        for sample_id, url in raw.items()
        if isinstance(sample_id, str) and isinstance(url, str) and pattern.fullmatch(url)
    }


def load_codeowners(path: Path | None) -> list[tuple[str, str]]:
    """Parse a CODEOWNERS file into an ordered list of (pattern, owners).

    Patterns are kept exactly as written (leading "/" stripped, trailing "/"
    kept so directory patterns are distinguishable from file patterns).
    Best-effort: a missing or unreadable file just yields no entries, so the
    Codeowner column falls back to "—" everywhere rather than failing the
    whole render.
    """
    if not path or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    entries: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        pattern, owners = parts[0], " ".join(parts[1:])
        entries.append((pattern.lstrip("/"), owners))
    return entries


def codeowners_for(sample_path: str, codeowners: list[tuple[str, str]]) -> list[str]:
    """Return the distinct owner handles/teams for a sample.

    Combines two kinds of CODEOWNERS entries:
      - The directory-level entry that governs the sample as a whole (the
        pattern is the sample path itself or an ancestor directory of it),
        using CODEOWNERS' own "last matching entry wins" rule for that tier.
      - Any more specific entries nested *inside* the sample directory (e.g.
        a single file referenced from docs, such as
        "/samples/.../Program.cs @microsoft-foundry/AI-Platform-Docs"). These
        don't replace the directory owner -- they're additional reviewers
        with a real stake in that sample -- so their owners are unioned in
        rather than discarded.
    Returned in encounter order (directory owner's tokens first), deduplicated.
    """
    primary_owners: str | None = None
    nested_owner_tokens: list[str] = []
    for pattern, pattern_owners in codeowners:
        pattern_dir = pattern.rstrip("/")
        if sample_path == pattern_dir or sample_path.startswith(pattern_dir + "/"):
            primary_owners = pattern_owners
        elif pattern_dir.startswith(sample_path + "/"):
            nested_owner_tokens.extend(pattern_owners.split())
    tokens: list[str] = []
    for token in (primary_owners.split() if primary_owners else []) + nested_owner_tokens:
        if token not in tokens:
            tokens.append(token)
    return tokens


def codeowner_display_name(owner: str) -> str:
    """Strip a leading '@org/' prefix for the Codeowner column's display text.

    Filter buttons and the underlying data-codeowner match tokens keep the
    full "@org/team" form; only the visible cell text is shortened.
    """
    if owner.startswith("@") and "/" in owner:
        return "@" + owner.split("/", 1)[1]
    return owner


def render_row(
    record: dict[str, Any],
    status_href: str | None,
    artifact_href: str | None,
    codeowners: list[str] | None,
) -> str:
    sample = record["sample"]
    url = sample_url(record)
    path_cell = f'<a href="{esc(url)}"><code>{esc(sample["path"])}</code></a>' if url else f'<code>{esc(sample["path"])}</code>'
    completed_at = record.get("completed_at")
    completed_sort = completed_at.isoformat() if isinstance(completed_at, datetime) else ""
    completed_cell = esc(completed_at.strftime("%Y-%m-%d %H:%M UTC")) if isinstance(completed_at, datetime) else "—"
    duration = record.get("duration_seconds")
    duration_sort = duration if isinstance(duration, (int, float)) else -1
    duration_cell = f"{esc(duration)}s" if isinstance(duration, (int, float)) else "—"
    outcome = record["outcome"]
    badge_text = esc(OUTCOMES.get(outcome, outcome))
    badge = f'<span class="badge {OUTCOME_CSS_CLASS.get(outcome, "")}">{badge_text}</span>'
    status_cell = f'<a href="{esc(status_href)}">{badge}</a>' if status_href else badge
    artifact_sort = "1" if artifact_href else "0"
    artifact_cell = (
        f'<a href="{esc(artifact_href)}" class="artifact-link">{DOWNLOAD_ICON}Diagnostics</a>' if artifact_href else "—"
    )
    copilot_href = copilot_issue_link(record, status_href, artifact_href)
    copilot_cell = (
        f'<a href="{esc(copilot_href)}" class="copilot-link">Fix with Copilot ↗</a>'
        if copilot_href
        else "—"
    )
    copilot_sort = "1" if copilot_href else "0"
    stage = record.get("completed_stage", "")
    stage_display = stage_label(stage)
    stage_title = f' title="{esc(stage)}"' if isinstance(stage, str) and stage != stage_display else ""
    owners = codeowners or []
    codeowner_display = ", ".join(codeowner_display_name(owner) for owner in owners)
    codeowner_cell = esc(codeowner_display) if owners else "—"
    codeowner_tokens = " ".join(esc(owner.lower()) for owner in owners)
    return (
        f'<tr data-outcome="{esc(outcome)}" data-language="{esc(sample["language"].lower())}" '
        f'data-validation="{esc(str(stage).lower())}" data-codeowner="{codeowner_tokens}">'
        f'<td data-sort-value="{esc(sample["path"].lower())}">{path_cell}</td>'
        f'<td data-sort-value="{esc(sample["language"].lower())}">{esc(sample["language"])}</td>'
        f'<td data-sort-value="{OUTCOME_RANK.get(outcome, 99)}">{status_cell}</td>'
        f'<td data-sort-value="{esc(str(stage).lower())}"{stage_title}>{esc(stage_display)}</td>'
        f'<td data-sort-value="{duration_sort}">{duration_cell}</td>'
        f'<td data-sort-value="{esc(completed_sort)}">{completed_cell}</td>'
        f'<td data-sort-value="{artifact_sort}">{artifact_cell}</td>'
        f'<td data-sort-value="{esc(codeowner_display.lower())}">{codeowner_cell}</td>'
        f'<td data-sort-value="{copilot_sort}">{copilot_cell}</td>'
        "</tr>"
    )


SORT_SCRIPT = """
(function () {
  var table = document.getElementById("results");
  if (!table) return;
  var headers = table.querySelectorAll("th[data-sort-index]");
  var currentIndex = null;
  var currentDir = 1;
  headers.forEach(function (th) {
    var button = th.querySelector(".sort-button");
    if (!button) return;
    button.addEventListener("click", function () {
      var index = parseInt(th.getAttribute("data-sort-index"), 10);
      var type = th.getAttribute("data-sort-type") || "text";
      currentDir = index === currentIndex ? -currentDir : 1;
      currentIndex = index;
      var tbody = table.tBodies[0];
      var rows = Array.prototype.slice.call(tbody.rows);
      rows.sort(function (a, b) {
        var av = a.cells[index].getAttribute("data-sort-value") || "";
        var bv = b.cells[index].getAttribute("data-sort-value") || "";
        if (type === "number") {
          av = parseFloat(av); bv = parseFloat(bv);
          return (av - bv) * currentDir;
        }
        if (av < bv) return -1 * currentDir;
        if (av > bv) return 1 * currentDir;
        return 0;
      });
      rows.forEach(function (row) { tbody.appendChild(row); });
      headers.forEach(function (other) {
        other.removeAttribute("data-sort-dir");
        other.setAttribute("aria-sort", "none");
      });
      var dir = currentDir === 1 ? "asc" : "desc";
      th.setAttribute("data-sort-dir", dir);
      th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
    });
  });
})();
"""

FILTER_SCRIPT = """
(function () {
  var table = document.getElementById("results");
  if (!table) return;
  var rows = table.tBodies[0].rows;
  var groups = [
  { bar: document.getElementById("outcome-filters"), attr: "data-filter-outcome", data: "outcome", label: "Status", active: "all" },
  { bar: document.getElementById("language-filters"), attr: "data-filter-language", data: "language", label: "Language", active: "all" },
  { bar: document.getElementById("validation-filters"), attr: "data-filter-validation", data: "validation", label: "Validation", active: "all" },
  { bar: document.getElementById("codeowner-filters"), attr: "data-filter-codeowner", data: "codeowner", label: "Codeowner", active: "all", multi: true },
  ].filter(function (group) { return group.bar; });
  if (!groups.length) return;
  var summary = document.getElementById("filter-summary");
  var total = rows.length;

  function syncPressedState(buttons, activeButton) {
    buttons.forEach(function (button) {
      var isActive = button === activeButton;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function matches(row, group) {
    if (group.active === "all") return true;
    var value = row.getAttribute("data-" + group.data) || "";
    if (group.multi) {
      // A row can have several codeowners (e.g. a directory owner plus a
      // docs-team file-level owner) -- match if the active filter is one of them.
      // An empty active value (the "Unowned" bucket) matches rows with none.
      return group.active === "" ? value === "" : value.split(" ").indexOf(group.active) !== -1;
    }
    return value === group.active;
  }

  function applyFilters() {
    var visibleCount = 0;
    Array.prototype.forEach.call(rows, function (row) {
      var visible = groups.every(function (group) { return matches(row, group); });
      row.style.display = visible ? "" : "none";
      if (visible) visibleCount += 1;
    });
    if (summary) {
      var active = groups
        .filter(function (group) { return group.active !== "all"; })
        .map(function (group) {
          var button = group.bar.querySelector("button.active");
          var label = button ? button.textContent.replace(/\\s*\\([^)]*\\)\\s*$/, "") : group.active;
          return group.label + ": " + label;
        });
      summary.textContent = "Showing " + visibleCount + " of " + total + " samples" +
        (active.length ? " · " + active.join(" · ") : " · All filters");
    }
  }

  groups.forEach(function (group) {
    var buttons = group.bar.querySelectorAll("button[" + group.attr + "]");
    if (!buttons.length) return;
    var initialButton = group.bar.querySelector("button[" + group.attr + "].active") || buttons[0];
    var initialValue = initialButton.getAttribute(group.attr);
    group.active = initialValue === null ? "all" : initialValue;
    syncPressedState(buttons, initialButton);
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        group.active = button.getAttribute(group.attr);
        syncPressedState(buttons, button);
        applyFilters();
      });
    });
  });
  applyFilters();
})();
"""


def render(
    records: list[dict[str, Any]],
    complete: bool,
    run_url: str | None,
    generated_at: datetime,
    job_links: dict[str, str] | None = None,
    artifact_links: dict[str, str] | None = None,
    codeowners: list[tuple[str, str]] | None = None,
) -> str:
    counts = {outcome: sum(record["outcome"] == outcome for record in records) for outcome in OUTCOMES}
    run = run_metadata(records)
    rlink = run_link(run, run_url)
    clink = commit_link(run)
    sha = run.get("sha")

    status_lines = []
    if not complete:
        status_lines.append(
            '<div class="banner banner-incomplete">'
            "⚠️ The most recent validation run reported an <strong>incomplete</strong> result set. "
            "This snapshot is not authoritative fleet status — open the workflow run linked below "
            "for the details that could not be normalized here."
            "</div>"
        )
    meta_bits = [f"Generated {esc(generated_at.strftime('%Y-%m-%d %H:%M UTC'))}"]
    if run.get("run_id") and run.get("run_attempt"):
        meta_bits.append(f"Run {esc(run['run_id'])} · attempt {esc(run['run_attempt'])}")
    if sha and clink:
        meta_bits.append(f'Validated commit <a href="{esc(clink)}"><code>{esc(str(sha)[:12])}</code></a>')
    elif sha:
        meta_bits.append(f"Validated commit <code>{esc(str(sha)[:12])}</code>")
    if rlink:
        meta_bits.append(f'<a href="{esc(rlink)}">Workflow run</a>')
    status_lines.append(f'<p class="meta">{" · ".join(meta_bits)}</p>')

    filter_sections = []
    filter_buttons = [
        f'<button type="button" data-filter-outcome="all" class="active" aria-pressed="true">All ({len(records)})</button>'
    ]
    for outcome in ("passed", "sample failure", "infrastructure/error", "skipped/not-completed"):
        filter_buttons.append(
            f'<button type="button" data-filter-outcome="{esc(outcome)}" class="filter-btn {OUTCOME_CSS_CLASS.get(outcome, "")}" aria-pressed="false">'
            f"{esc(OUTCOMES[outcome])} ({counts[outcome]})</button>"
        )
    filter_sections.append(
        f'<div class="filter-group"><strong>Status</strong><div id="outcome-filters" class="filters">{"".join(filter_buttons)}</div></div>'
    )

    language_counts: dict[str, int] = {}
    for record in records:
        language = record["sample"]["language"]
        language_counts[language] = language_counts.get(language, 0) + 1
    language_buttons = [
        f'<button type="button" data-filter-language="all" class="active" aria-pressed="true">All ({len(records)})</button>'
    ]
    for language in sorted(language_counts, key=str.lower):
        language_buttons.append(
            f'<button type="button" data-filter-language="{esc(language.lower())}" class="filter-btn" aria-pressed="false">'
            f"{esc(language)} ({language_counts[language]})</button>"
        )
    filter_sections.append(
        f'<div class="filter-group"><strong>Language</strong><div id="language-filters" class="filters">{"".join(language_buttons)}</div></div>'
    )

    validation_counts: dict[str, int] = {}
    validation_labels: dict[str, str] = {}
    for record in records:
        stage = record.get("completed_stage", "")
        key = str(stage).lower()
        validation_counts[key] = validation_counts.get(key, 0) + 1
        validation_labels[key] = stage_label(stage)
    validation_buttons = [
        f'<button type="button" data-filter-validation="all" class="active" aria-pressed="true">All ({len(records)})</button>'
    ]
    for key in sorted(validation_counts, key=lambda value: validation_labels[value].lower()):
        validation_buttons.append(
            f'<button type="button" data-filter-validation="{esc(key)}" class="filter-btn" aria-pressed="false">'
            f"{esc(validation_labels[key])} ({validation_counts[key]})</button>"
        )
    filter_sections.append(
        f'<div class="filter-group"><strong>Validation</strong><div id="validation-filters" class="filters">{"".join(validation_buttons)}</div></div>'
    )

    codeowners = codeowners or []
    sample_codeowners = {
        record["sample"]["id"]: codeowners_for(record["sample"]["path"], codeowners) for record in records
    }
    codeowner_counts: dict[str, int] = {}
    unowned_count = 0
    for owners in sample_codeowners.values():
        if not owners:
            unowned_count += 1
            continue
        for owner in owners:
            codeowner_counts[owner] = codeowner_counts.get(owner, 0) + 1
    codeowner_buttons = [
        f'<button type="button" data-filter-codeowner="all" class="active" aria-pressed="true">All ({len(records)})</button>'
    ]
    for owner in sorted(codeowner_counts, key=str.lower):
        codeowner_buttons.append(
            f'<button type="button" data-filter-codeowner="{esc(owner.lower())}" class="filter-btn" aria-pressed="false">'
            f"{esc(codeowner_display_name(owner))} ({codeowner_counts[owner]})</button>"
        )
    if unowned_count:
        codeowner_buttons.append(
            f'<button type="button" data-filter-codeowner="" class="filter-btn" aria-pressed="false">Unowned ({unowned_count})</button>'
        )
    filter_sections.append(
        f'<div class="filter-group"><strong>Codeowner</strong><div id="codeowner-filters" class="filters">{"".join(codeowner_buttons)}</div></div>'
    )
    status_lines.append(
        '<details class="filter-panel">'
        '<summary><strong>Filters</strong><span id="filter-summary">Showing all samples</span></summary>'
        f'{"".join(filter_sections)}'
        "</details>"
    )

    # Prefer linking each row straight to the specific matrix job that
    # produced it -- that job page shows the failing step directly. Only
    # fall back to the overall run-overview link when no per-sample job
    # link was collected (e.g. running this script standalone/locally).
    job_links = job_links or {}
    artifact_links = artifact_links or {}
    ordered_records = sorted(
        records,
        key=lambda record: (OUTCOME_RANK.get(record["outcome"], 99), record["sample"]["language"], record["sample"]["path"]),
    )
    rows = "\n".join(
        render_row(
            record,
            job_links.get(record["sample"]["id"], rlink),
            artifact_links.get(record["sample"]["id"]),
            sample_codeowners.get(record["sample"]["id"]),
        )
        for record in ordered_records
    )
    columns = [
        ("Sample", "text"),
        ("Language", "text"),
        ("Status", "number"),
        ("Validation", "text"),
        ("Duration", "number"),
        ("Last checked", "text"),
        ("Artifact", "number"),
        ("Codeowner", "text"),
        ("Action", "number"),
    ]
    header_cells = "".join(
        f'<th data-sort-index="{index}" data-sort-type="{sort_type}" aria-sort="none">'
        f'<button type="button" class="sort-button">{esc(label)}<span class="sort-indicator"></span></button></th>'
        for index, (label, sort_type) in enumerate(columns)
    )
    table = (
        '<table id="results">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>foundry-samples validation dashboard</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    background: #ffffff; color: #1b1f23; margin: 0; padding: 2rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  h1 {{ margin-bottom: 0.25rem; }}
  .meta {{ color: #57606a; margin: 0.25rem 0; }}
  .filter-panel {{
    border: 1px solid #d0d7de; border-radius: 8px; margin: 1rem 0; background: #ffffff;
  }}
  .filter-panel summary {{
    display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 0.75rem 1rem;
  }}
  .filter-panel summary::-webkit-details-marker {{ display: none; }}
  .filter-panel summary::before {{ content: "▸"; color: #57606a; font-size: 1.15rem; line-height: 1; }}
  .filter-panel[open] summary::before {{ content: "▾"; }}
  #filter-summary {{ color: #57606a; font-size: 0.9rem; }}
  .filter-group {{ border-top: 1px solid #d0d7de; padding: 0.75rem 1rem; }}
  .filter-group strong {{ display: block; margin-bottom: 0.5rem; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0; }}
  .filters button {{
    border: 1px solid #d0d7de; background: #f6f8fa; color: #1b1f23; border-radius: 999px;
    padding: 0.3rem 0.85rem; font-size: 0.85rem; cursor: pointer; font-family: inherit;
  }}
  .filters button:hover {{ background: #eaeef2; }}
  .filters button.active {{ background: #0969da; border-color: #0969da; color: #ffffff; }}
  .filters button.passed.active {{ background: #1a7f37; border-color: #1a7f37; }}
  .filters button.failed.active {{ background: #cf222e; border-color: #cf222e; }}
  .filters button.errored.active {{ background: #9a6700; border-color: #9a6700; }}
  .filters button.skipped.active {{ background: #57606a; border-color: #57606a; }}
  .banner {{ padding: 0.75rem 1rem; border-radius: 6px; margin: 1rem 0; }}
  .banner-incomplete {{ background: #fff8c5; border: 1px solid #d4a72c; color: #6b5900; }}
  table {{ border-collapse: collapse; width: 100%; background: #ffffff; margin-top: 1.5rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #d0d7de; font-size: 0.9rem; }}
  th {{ background: #f6f8fa; color: #1b1f23; white-space: nowrap; padding: 0; }}
  .sort-button {{
    all: unset; display: block; box-sizing: border-box; width: 100%;
    padding: 0.5rem 0.75rem; cursor: pointer; user-select: none;
    font: inherit; color: inherit;
  }}
  .sort-button:hover {{ background: #eaeef2; }}
  .sort-button:focus-visible {{ outline: 2px solid #0969da; outline-offset: -2px; }}
  th .sort-indicator::after {{ content: ""; margin-left: 0.35rem; color: #57606a; }}
  th[data-sort-dir="asc"] .sort-indicator::after {{ content: "▲"; }}
  th[data-sort-dir="desc"] .sort-indicator::after {{ content: "▼"; }}
  code {{ background: #f6f8fa; padding: 0.1rem 0.3rem; border-radius: 4px; }}
  a {{ color: #0969da; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .artifact-link, .copilot-link {{ display: inline-flex; align-items: center; gap: 0.3rem; white-space: nowrap; }}
  .icon-download {{ flex: none; }}
  .badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.85rem; white-space: nowrap; }}
  .badge.passed {{ background: #dafbe1; color: #116329; }}
  .badge.failed {{ background: #ffebe9; color: #82071e; }}
  .badge.errored {{ background: #fff8c5; color: #6b5900; }}
  .badge.skipped {{ background: #eaeef2; color: #57606a; }}
  footer {{ margin-top: 2rem; color: #57606a; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>foundry-samples validation dashboard</h1>
{"".join(status_lines)}
{table}
<footer>
  Full diagnostic logs aren't inlined on this page. Click a status badge, or
  the Diagnostics link when present, for per-sample logs, subject to GitHub
  Actions retention and authentication. For failed or errored samples, Fix
  with Copilot opens a prefilled issue for review; submitting it assigns the
  investigation to Copilot. Click any column header to sort.
</footer>
<script>{SORT_SCRIPT}
{FILTER_SCRIPT}</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--expected-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-url")
    parser.add_argument(
        "--job-links",
        type=Path,
        help="optional JSON file mapping sample id -> matrix job URL, as produced by collect-job-links.py",
    )
    parser.add_argument(
        "--artifact-links",
        type=Path,
        help="optional JSON file mapping sample id -> artifact page URL, as produced by collect-artifact-links.py",
    )
    parser.add_argument(
        "--codeowners",
        type=Path,
        help="optional path to a CODEOWNERS file used to populate the Codeowner column/filter",
    )
    args = parser.parse_args()
    try:
        records, complete = collect(args.results_dir, load_expected(args.expected_samples))
        run = run_metadata(records)
        repository = run.get("repository")
        job_links = load_link_map(args.job_links, repository, r"actions/runs/\d+/job/\d+")
        artifact_links = load_link_map(args.artifact_links, repository, r"actions/runs/\d+/artifacts/\d+")
        codeowners = load_codeowners(args.codeowners)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            render(
                records,
                complete,
                args.run_url,
                datetime.now(timezone.utc),
                job_links,
                artifact_links,
                codeowners,
            ),
            encoding="utf-8",
            newline="\n",
        )
    except (ContractError, OSError) as exc:
        print(f"render-validation-dashboard: {exc}", file=sys.stderr)
        return 1
    # Unlike render-validation-report.py, an incomplete result set does not
    # fail this script: the dashboard must still publish (with its banner)
    # so a broken handoff is visible on the durable page rather than leaving
    # a stale prior deployment looking like current status.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

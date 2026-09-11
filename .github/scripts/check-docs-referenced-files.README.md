# check-docs-referenced-files.py

Published Microsoft Learn articles include code from this repo **by reference**:

```
:::code language="python" source="~/foundry-samples/samples/python/quickstart/create-agent/quickstart-create-agent.py" id="create_agent":::
```

Three changes on this side break the docs build:

| # | Change | Why it breaks |
|---|--------|---------------|
| 1 | The file is **renamed or moved** | `source=` no longer resolves |
| 2 | The file is **deleted** | `source=` no longer resolves |
| 3 | A snippet delimiter comment (`# <create_agent>` … `# </create_agent>`) is **removed** | `id=` no longer resolves |
| 4 | A referenced **notebook cell** is deleted, or its `"metadata": {"name": …}` is removed | the article's cell reference no longer resolves |

This check replaces the old process (every referenced file listed in `CODEOWNERS`, docs team
manually approving every PR that touched one) with an automated PR gate.

**Contact for the docs team:** `General - AI Platform Docs <7f0acdb3.microsoft.com@amer.teams.ms>`
(emailing that address posts to the team's Teams channel), or @-mention
`@microsoft-foundry/AI-Platform-Docs` on the PR.

## The manifest

`.github/docs-referenced-files.json` is the source of truth. It is owned by the AI Platform Docs
team, and it replaces the per-file block in `CODEOWNERS`. Normally an entry is just the path:

```json
"files": [
  "samples/python/quickstart/create-agent/quickstart-create-agent.py",
  "samples/python/fine-tuning/distillation.ipynb"
]
```

That is the whole maintenance story: **one line per file, added when an article starts referencing
a sample and removed when it stops.** You never list snippet ids by hand.

A bare path means `mode: "auto"`. The checker reads the file at the **pull request's base
revision**, records which snippet ids and named notebook cells it had, and requires the head
revision to still have all of them. So:

* Removing a `# <create_agent>` delimiter, or a notebook cell whose `metadata.name` an article
  references, fails the build.
* Adding new snippets, renaming nothing, and freely editing the code *inside* a region all pass.
* Only per-cell `metadata.name` counts — notebook-level `kernelspec`/`language_info` `name` keys
  are ignored, so a raw `"name":` search can't produce false positives.

The tradeoff of the bare form: expectations come from the base revision, so a break that was
already merged in an earlier PR is not re-reported on later PRs. That is why CI always passes
`--base-ref` and fails loudly if it cannot resolve one.

### Pinning an entry (optional)

To make a file's expectations independent of the base revision — or to protect only *some* of a
file's regions — write the long form instead. Generate it with `--seed --pin`.

```json
{
  "path": "samples/python/quickstart/create-agent/quickstart-create-agent.py",
  "mode": "delimited",
  "snippets": ["create_agent"]
}
```

* `mode: "delimited"` — every listed snippet id must exist exactly once as a matched
  `<id>` / `</id>` comment pair with non-empty content between them.
* `mode: "notebook-cell"` — `.ipynb` only. Every listed name must match exactly one cell's
  `metadata.name`, and that cell must be non-empty.
* `mode: "whole-file"` — the article includes the entire file; only its exact path is checked.
* `note` — optional free text (e.g. which article references it).

Pinned entries are checked against the current tree directly, so a break that slipped through
earlier keeps being reported. `--seed` never downgrades a pinned entry back to a bare path.

## Running it

```bash
# validate the committed tree
python .github/scripts/check-docs-referenced-files.py

# validate your local edits before you push
python .github/scripts/check-docs-referenced-files.py --worktree

# what CI runs: compare against the branch you'll merge into
python .github/scripts/check-docs-referenced-files.py --base-ref origin/main
```

Exit codes: `0` intact · `1` a docs reference is broken · `2` checker/manifest/git error.

## Maintenance (docs team)

```bash
# regenerate every entry from the working tree (re-reads snippet ids from the files)
python .github/scripts/check-docs-referenced-files.py --seed

# start from the CODEOWNERS block owned by @microsoft-foundry/AI-Platform-Docs
python .github/scripts/check-docs-referenced-files.py --seed --from-codeowners

# add or refresh one file
python .github/scripts/check-docs-referenced-files.py --seed --path samples/python/x/app.py
```

`--seed` writes bare paths. Add `--pin` to write the long form instead, inferring `mode` and
`snippets` from the file's current contents (comment delimiters for code files,
`cells[*].metadata.name` for notebooks). Review a pinned diff — if an article only includes *some*
of a file's regions, trim `snippets` to the ones the docs actually use so contributors aren't
blocked on delimiters nobody publishes.

To add or drop a file day to day, just edit the `files` list by hand; the path is all it needs.

## Renaming or deleting a referenced file

The rename cannot be atomic across two repos, so the safe order is:

1. Add the sample at the new path, keeping the old path and its delimiters in place.
2. Add the new path to the manifest.
3. Docs team updates and publishes the Learn articles.
4. After publication, docs team removes the old manifest entry.
5. Delete the old path.

## Supported file types

Delimiter scanning is extension-aware: `#` for Python/Bash/Terraform/YAML/`.env`, `//` for
C#/Java/JS/TS/Rust/Bicep/Go, `<!-- -->` for XML/`.csproj`/Markdown, `--` for SQL. Files are decoded
as `utf-8-sig` (BOM-tolerant — several `Program.cs` files start with one) and CRLF-normalized.

Only comment-only lines whose entire body is `<id>` or `</id>` count, so `List<ToolDefinition>` and
JSON strings are never mistaken for delimiters. `.json` has no comment syntax and must be listed as
`whole-file`; `.ipynb` uses `notebook-cell` (or `whole-file`) and is rejected in `delimited` mode.
An unknown extension is a hard error (exit 2) rather than a silent zero-tag pass; add its comment
syntax to the marker tables in the script.

## Enforcement

`.github/workflows/docs-referenced-files.yml` runs this on every PR (`pull_request`, never
`pull_request_target`, `contents: read`, no secrets, no `paths:` filter so the required check can
never conclude `skipped`). Mark **`docs-referenced-files / check`** as a required status check on
`main`.

The gate is only as strong as the files that implement it. Protect all three from unreviewed edits
(branch-ruleset path restriction, or enforced code-owner review with stale approvals dismissed):

* `.github/docs-referenced-files.json`
* `.github/scripts/check-docs-referenced-files.py`
* `.github/workflows/docs-referenced-files.yml`

Once the required check and that protection are both live, the per-file
`@microsoft-foundry/AI-Platform-Docs` block in `.github/CODEOWNERS` can be deleted — the docs team
stops owning sample code and owns only the manifest.

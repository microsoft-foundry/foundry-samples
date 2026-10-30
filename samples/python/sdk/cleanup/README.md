---
ai-usage: ai-assisted
---

# Clean up current sample resources

Use the same virtual environment and `FOUNDRY_PROJECT_ENDPOINT` as the example that created the resource. Don't install this folder's dependencies over an existing framework or preview environment; its `requirements.txt` is for a separate, standalone installation.

Inspect `python cleanup.py --help`, then pass the exact resource kind and identifier printed by your example. `--confirm` acknowledges that you own the selected resource. Never target a production or caller-owned dependency.

```powershell
python cleanup.py agent <sample-agent-name-or-id> --confirm
```

For a versioned resource, add `--version <created-version>`. Deleting an agent deletes its versions too. `--force` is optional and applies only to agents or agent versions; use it only after confirming that no other workflow depends on the selected resource.

No resource operation runs on import or without explicit confirmation. Service errors are reported rather than treated as successful cleanup.

---
ai-usage: ai-assisted
---

# Maintain the client-side documentation examples

This directory is an isolated command-line client package, not the hosted runtime in the sibling `src` directory. Preserve that runtime's dependencies and default deployment entry point.

Keep `requirements.in` and the complete resolved `requirements.txt` synchronized. Preserve the selected SDK generation and any framework compatibility bounds. Never install one generation over another sample's environment.

Run `python -m unittest discover -p 'test_*.py'` for local checks. Don't add sample-owned live-service execution without explicit approval. Keep named snippet regions stable, document required assets, and delete only resources owned by the selected example.

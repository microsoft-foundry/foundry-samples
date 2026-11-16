# Web Scraper Skill

1. Create or reuse a browser session and preserve its `browserSessionId`.
2. Navigate to the target page with the discovered navigation tool.
3. Take a browser snapshot before interacting with the page.
4. Use discovered browser tools to reveal tabs, accordions, pagination, or lazy-loaded content.
5. Extract the requested values from snapshots or the discovered evaluation tool, preserving the source page's meaning and ordering.
6. Continue through all requested pages, then report the data clearly with any missing or inaccessible fields identified.

Pass `browserSessionId` to every browser tool. Use only names and schemas returned by MCP discovery.

# A2A Agent

Demonstrates how foundry agents are A2A compatible. This sample uses the `Azure.AI.Agents.Persistent` to create a foundry agent, but then interacts with the agents via the `a2a-net.Client` SDK. It uses `Azure.Identity` for EntraID auth using the A2A client library.

## Running

```
make restore build run
```
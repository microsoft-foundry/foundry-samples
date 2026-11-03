# Verify Unified WinML Capability (C#)

This sample verifies that the unified `Microsoft.AI.Foundry.Local` package exposes
WinML 2.x execution-provider discovery, download, and registration on supported
Windows hardware. It then loads an accelerated model variant and runs a native v2
streaming chat request.

## Prerequisites

- .NET 9 SDK
- Windows with a compatible GPU or NPU for the accelerated checks

## Build & Run

WinML support is built into `Microsoft.AI.Foundry.Local`. On non-Windows systems,
the sample validates unified-package initialization and reports that dynamic
WinML EPs are unavailable rather than attempting accelerated inference.

```bash
dotnet run
```

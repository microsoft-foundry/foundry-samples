"""Run real sequential/concurrent A -> C and B -> C calls and save receipts."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "agent"))

from azure.identity.aio import DefaultAzureCredential
from client import send


async def experiment(a: str, b: str, output: Path, local: bool = False) -> dict:
    run_id = "repro-" + uuid4().hex
    results: dict = {"run_id": run_id, "local": local, "observations": [], "checks": []}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    def check(name: str, condition: bool) -> None:
        results["checks"].append({"name": name, "passed": condition})
        save()
        if not condition:
            raise AssertionError(name)

    async with DefaultAzureCredential() as credential:
        async def invoke(role: str, label: str, mode: str, c_context: str | None = None, outer: str | None = None) -> dict:
            payload = {"marker": f"{run_id}-{label}-{role}", "mode": mode}
            if c_context is not None:
                payload["c_context_id"] = c_context
            reply = await send(
                a if role == "A" else b,
                payload,
                outer or f"{run_id}-outer-{role}",
                credential,
                {},
            )
            observation = {"label": label, "role": role, **reply}
            results["observations"].append(observation)
            save()
            return reply["receipt"]["downstream"]["receipt"]

        def verify_pair(label: str, pair: list[dict], shared: bool) -> None:
            left, right = pair
            check(f"{label}: C context equality is {shared}",
                  (left["context_id"] == right["context_id"]) == shared)
            check(f"{label}: distinct C task IDs", left["task_id"] != right["task_id"])
            if not local:
                check(f"{label}: actual hosted session IDs are present",
                      bool(left["hosted_session_id"]) and bool(right["hosted_session_id"]))
                check(f"{label}: C hosted session equality is {shared}",
                      (left["hosted_session_id"] == right["hosted_session_id"]) == shared)
                check(f"{label}: same resolved user",
                      bool(left["user_fingerprint"]) and left["user_fingerprint"] == right["user_fingerprint"])
            markers = {left["marker"], right["marker"]}
            if shared:
                check(f"{label}: C saw the other caller's marker",
                      any(item["marker"] in markers - {receipt["marker"]}
                          for receipt in pair for item in receipt["prior_context_messages"]))
            else:
                check(f"{label}: no cross-caller context history",
                      all(item["marker"] not in markers - {receipt["marker"]}
                          for receipt in pair for item in receipt["prior_context_messages"]))

        try:
            pair = [await invoke("A", "fresh-sequential", "fresh"),
                    await invoke("B", "fresh-sequential", "fresh")]
            verify_pair("fresh-sequential", pair, False)
            for index in range(3):
                label = f"fresh-concurrent-{index}"
                pair = list(await asyncio.gather(invoke("A", label, "fresh"), invoke("B", label, "fresh")))
                verify_pair(label, pair, False)

            shared = f"{run_id}-shared-c"
            pair = [await invoke("A", "shared-sequential", "explicit", shared),
                    await invoke("B", "shared-sequential", "explicit", shared)]
            verify_pair("shared-sequential", pair, True)
            pair = list(await asyncio.gather(
                invoke("A", "shared-concurrent", "explicit", shared),
                invoke("B", "shared-concurrent", "explicit", shared),
            ))
            verify_pair("shared-concurrent", pair, True)

            outer = f"{run_id}-same-upstream"
            pair = [await invoke("A", "inherit-same-context", "inherit", outer=outer),
                    await invoke("B", "inherit-same-context", "inherit", outer=outer)]
            verify_pair("inherit-same-context", pair, True)

            unique = [
                await invoke("A", "unique-context", "explicit", f"{run_id}-c-A"),
                await invoke("B", "unique-context", "explicit", f"{run_id}-c-B"),
            ]
            verify_pair("unique-context", unique, False)
            repeat = [
                await invoke("A", "unique-context-repeat", "explicit", f"{run_id}-c-A"),
                await invoke("B", "unique-context-repeat", "explicit", f"{run_id}-c-B"),
            ]
            verify_pair("unique-context-repeat", repeat, False)
            check("each unique C context retains its own prior marker",
                  all(any(item["marker"] == before["marker"] for item in after["prior_context_messages"])
                      for before, after in zip(unique, repeat)))
            fresh_contexts = [
                item["receipt"]["downstream"]["context_id"]
                for item in results["observations"] if item["label"].startswith("fresh-")
            ]
            check("all eight default downstream context IDs are distinct", len(set(fresh_contexts)) == 8)
            if not local:
                fresh_sessions = [
                    item["receipt"]["downstream"]["receipt"]["hosted_session_id"]
                    for item in results["observations"] if item["label"].startswith("fresh-")
                ]
                check("all eight default C hosted sessions are distinct", len(set(fresh_sessions)) == 8)
            results["status"] = "passed"
        except Exception as error:
            results["status"] = "failed"
            results["error"] = f"{type(error).__name__}: {error}"
            save()
            raise
        finally:
            save()
    print(json.dumps({"status": results["status"], "run_id": run_id,
                      "observations": len(results["observations"]), "checks": len(results["checks"]),
                      "evidence": str(output)}, indent=2))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--output", type=Path, default=Path("results") / "remote.json")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    asyncio.run(experiment(args.a, args.b, args.output, args.local))

"""
Foundry Local SDK - Windows ML capability verification

The unified foundry-local-sdk wheel includes Windows ML support on Windows.
This script verifies:
  1. Execution providers are discovered and registered
  2. Accelerated model variants appear after registration
  3. A native SDK v2 streaming chat session runs on an accelerated model

On non-Windows platforms, the same flow validates the accelerated providers
available on that machine instead of expecting a Windows ML provider.
"""

import platform
import sys
import time

from foundry_local_sdk import (
    ChatSession,
    Configuration,
    DeviceType,
    FoundryLocalManager,
    MessageItem,
    Request,
    RequestOptions,
    SearchOptions,
    TextItem,
    TextItemType,
    __version__,
)


PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"
WARN = "\033[93m[WARN]\033[0m"

results = []


def log_result(test_name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    message = f"{status} {test_name}"
    if detail:
        message += f" - {detail}"
    print(message)
    results.append((test_name, passed))


def print_separator(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def is_accelerated_variant(variant) -> bool:
    runtime = variant.info.runtime
    return runtime is not None and runtime.device_type in (
        DeviceType.GPU,
        DeviceType.NPU,
    )


def main():
    # ── 0. Initialize FoundryLocalManager ──────────────────────
    print_separator("Initialization")
    config = Configuration(app_name="verify_winml")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance
    print(f"{INFO} foundry-local-sdk {__version__}")
    print(f"{INFO} Platform: {platform.system()} {platform.machine()}")

    chosen = None
    try:
        # ── 1. Discover & Register EPs ────────────────────────────
        print_separator("Step 1: Discover & Register Execution Providers")
        eps = manager.discover_eps()
        print(f"{INFO} Discovered {len(eps)} execution providers:")
        for ep in eps:
            print(f"  - {ep.name:40s}  Registered: {ep.is_registered}")
        log_result("EP Discovery", bool(eps), f"{len(eps)} EP(s) found")

        if not eps:
            _print_summary()
            return

        missing_eps = [ep.name for ep in eps if not ep.is_registered]
        if missing_eps:
            progress_state = {"ep": None}

            def ep_progress(ep_name: str, percent: float):
                if progress_state["ep"] not in (None, ep_name):
                    print()
                progress_state["ep"] = ep_name
                print(
                    f"\r  Downloading {ep_name}: {percent:.1f}%",
                    end="",
                    flush=True,
                )

            result = manager.download_and_register_eps(
                missing_eps, progress_callback=ep_progress
            )
            if progress_state["ep"] is not None:
                print()
            log_result(
                "EP Download & Registration",
                result.success,
                f"{len(result.registered_eps)} newly registered",
            )
        else:
            log_result(
                "EP Download & Registration",
                True,
                "All discovered EPs were already registered",
            )

        registered_eps = [ep for ep in manager.discover_eps() if ep.is_registered]
        if platform.system() == "Windows":
            log_result(
                "Unified Windows Provider Catalog",
                bool(registered_eps),
                ", ".join(ep.name for ep in registered_eps)
                if registered_eps
                else "No execution provider registered",
            )
        else:
            print(
                f"{INFO} Windows ML is Windows-only; validating current-platform "
                "accelerated providers."
            )

        # ── 2. List Models & Find Accelerated Variants ─────────────
        print_separator("Step 2: Model Catalog - Accelerated Models")
        models = manager.catalog.list_models()
        accelerated_variants = [
            variant
            for model in models
            for variant in model.variants
            if is_accelerated_variant(variant)
        ]

        print(f"{INFO} Total model aliases: {len(models)}")
        print(f"{INFO} Accelerated model variants: {len(accelerated_variants)}")
        for variant in accelerated_variants:
            runtime = variant.info.runtime
            print(
                f"  - {variant.id:50s}  Device: {runtime.device_type.value:3s}  "
                f"EP: {runtime.execution_provider}"
            )

        log_result(
            "Catalog - Accelerated models found",
            bool(accelerated_variants),
            f"{len(accelerated_variants)} accelerated variant(s)",
        )
        if not accelerated_variants:
            _print_summary()
            return

        # ── 3. Download & Load Model ──────────────────────────────
        print_separator("Step 3: Download & Load Model")
        last_load_error = None
        for candidate in accelerated_variants:
            runtime = candidate.info.runtime
            print(
                f"\n{INFO} Trying model: {candidate.id} "
                f"(EP: {runtime.execution_provider})"
            )
            try:
                if candidate.is_cached:
                    print(f"{INFO} Using cached model.")
                else:
                    candidate.download(
                        progress_callback=lambda percent: print(
                            f"\r  Downloading model: {percent:.1f}%",
                            end="",
                            flush=True,
                        )
                    )
                    print()
                candidate.load()
                chosen = candidate
                break
            except Exception as error:
                print(f"\n{WARN} Skipping {candidate.id}: {error}")
                last_load_error = error

        log_result(
            "Model Load",
            chosen is not None,
            f"Loaded {chosen.id}"
            if chosen is not None
            else str(last_load_error or "No accelerated variant could be loaded"),
        )
        if chosen is None:
            _print_summary()
            return

        # ── 4. Streaming Chat Completions (Native SDK v2) ─────────
        print_separator("Step 4: Streaming Chat (Native SDK v2)")
        response_text = ""
        started = time.time()
        with ChatSession(chosen) as session:
            session.set_options(
                RequestOptions(
                    search=SearchOptions(temperature=0, max_output_tokens=16)
                )
            )
            session.set_streaming(True)
            with (
                Request()
                .add_item(MessageItem.system("You are a helpful assistant."))
                .add_item(
                    MessageItem.user("What is 2 + 2? Reply with just the number.")
                ) as request
            ):
                with session.process_streaming_request(request) as stream:
                    for item in stream:
                        if (
                            isinstance(item, TextItem)
                            and item.type == TextItemType.DEFAULT
                        ):
                            response_text += item.text
                            print(item.text, end="", flush=True)
        elapsed = time.time() - started
        print()
        log_result(
            "Streaming Chat (Native SDK v2)",
            bool(response_text),
            f"{len(response_text)} chars in {elapsed:.2f}s",
        )
    except Exception as error:
        log_result("Verification run", False, str(error))
    finally:
        if chosen is not None and chosen.is_loaded:
            chosen.unload()
            print(f"{INFO} Model unloaded.")
        manager.close()

    _print_summary()


def _print_summary():
    print_separator("Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    for name, result in results:
        print(f"  {'PASS' if result else 'FAIL'} {name}")
    print(f"\n  {passed}/{total} tests passed")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()

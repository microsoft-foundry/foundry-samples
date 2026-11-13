"""Own three temporary local servers, run the experiment and clean them up."""

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from run_experiment import experiment


async def main() -> None:
    source = Path(__file__).parent / "src" / "agent"
    processes: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        logs = []
        try:
            for role, port in [("C", 18193), ("A", 18191), ("B", 18192)]:
                log = (root / f"{role}.log").open("w+", encoding="utf-8")
                logs.append(log)
                environment = {
                    **os.environ,
                    "REPRO_ROLE": role,
                    "PORT": str(port),
                    "REPRO_STATE_DIR": str(root / role),
                    "C_AGENT_ENDPOINT": "http://127.0.0.1:18193/a2a",
                }
                process = subprocess.Popen(
                    [sys.executable, str(source / "main.py")],
                    cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT,
                )
                processes.append(process)
                async with httpx.AsyncClient() as http:
                    for _ in range(120):
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(f"{role} exited: {log.read()[-6000:]}")
                        try:
                            response = await http.get(f"http://127.0.0.1:{port}/readiness")
                            if response.status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(0.5)
                    else:
                        raise TimeoutError(f"{role} did not become ready")
            await experiment(
                "http://127.0.0.1:18191/a2a", "http://127.0.0.1:18192/a2a",
                Path(__file__).parent / "results" / "local.json", local=True,
            )
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=30)
            for log in logs:
                log.close()


if __name__ == "__main__":
    asyncio.run(main())

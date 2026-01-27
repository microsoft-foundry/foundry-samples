"""
System Utility Agent (cross-OS, container-aware) — NO local files required.

Tools included (per your request):
- capability_report
- system_info
- resource_snapshot
- list_processes
- process_details
- check_port
- dns_lookup

Notes:
- This is designed to work with any model/server that supports an OpenAI-style tool calling contract.
"""

import os
import platform
import re
import socket
import sys
import time
from typing import Any, Dict, List, Optional

import psutil

# -----------------------------
# Tool implementations
# -----------------------------

def _is_running_in_container() -> bool:
    """
    Best-effort detection for Linux containers. On Windows/macOS Docker Desktop,
    you're still in a Linux VM container, so this often works as well.
    """
    # Common heuristics: /.dockerenv, cgroup hints
    if os.path.exists("/.dockerenv"):
        return True
    cgroup_path = "/proc/1/cgroup"
    if os.path.exists(cgroup_path):
        try:
            with open(cgroup_path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            if "docker" in txt or "containerd" in txt or "kubepods" in txt:
                return True
        except Exception:
            pass
    return False


def _read_first_existing(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()
            except Exception:
                continue
    return None


def _cgroup_limits() -> Dict[str, Any]:
    """
    Best-effort cgroup limits (mostly Linux). Returns supported=false on non-Linux.
    """
    if platform.system().lower() != "linux":
        return {"supported": False, "reason": "cgroup limits only available on Linux", "data": None}

    # Handle cgroup v2 (common) and some v1.
    # v2 memory limit: /sys/fs/cgroup/memory.max
    # v2 cpu max: /sys/fs/cgroup/cpu.max
    mem_max = _read_first_existing([
        "/sys/fs/cgroup/memory.max",                # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes"  # cgroup v1
    ])
    cpu_max = _read_first_existing([
        "/sys/fs/cgroup/cpu.max",                   # cgroup v2
        "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"       # cgroup v1
    ])
    cpu_period = _read_first_existing([
        "/sys/fs/cgroup/cpu/cpu.cfs_period_us"      # cgroup v1 only
    ])

    data: Dict[str, Any] = {}

    # Memory
    if mem_max is not None:
        if mem_max.isdigit():
            lim = int(mem_max)
            # Some systems show huge numbers when "max"/unlimited; v2 uses "max" literal.
            data["memory_limit_bytes"] = lim
            data["memory_limit_human"] = f"{lim / (1024**3):.2f} GiB"
        else:
            data["memory_limit_bytes"] = None
            data["memory_limit_human"] = mem_max  # e.g. "max"

    # CPU
    if cpu_max is not None:
        # cgroup v2: "quota period" like "200000 100000" or "max 100000"
        if " " in cpu_max:
            quota, period = cpu_max.split()[:2]
            data["cpu_quota_raw"] = quota
            data["cpu_period_us"] = int(period) if period.isdigit() else None
            data["cpu_quota_us"] = int(quota) if quota.isdigit() else None
            if quota.isdigit() and period.isdigit() and int(period) > 0:
                data["cpu_limit_cores"] = int(quota) / int(period)
        else:
            # cgroup v1 quota only
            data["cpu_quota_us"] = int(cpu_max) if cpu_max.isdigit() else None
            data["cpu_period_us"] = int(cpu_period) if (cpu_period and cpu_period.isdigit()) else None
            if data.get("cpu_quota_us") is not None and data.get("cpu_period_us"):
                data["cpu_limit_cores"] = data["cpu_quota_us"] / data["cpu_period_us"]

    return {"supported": True, "reason": None, "data": data or None}


def capability_report() -> Dict[str, Any]:
    """
    Report what the agent can likely observe in this runtime environment.
    """
    os_name = platform.system()
    in_container = _is_running_in_container()

    # process listing typically works; may be limited by PID namespace (containers)
    proc_supported = True

    # net connections sometimes restricted by permissions
    try:
        _ = psutil.net_connections(kind="inet")
        net_supported = True
        net_reason = None
    except Exception as e:
        net_supported = False
        net_reason = f"net_connections not accessible: {type(e).__name__}: {e}"

    cgroups = _cgroup_limits()

    # Determine "scope" we can confidently claim
    scope = "container" if in_container else "host"

    return {
        "supported": True,
        "scope": scope,
        "data": {
            "os": os_name,
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "in_container": in_container,
            "process_visibility": {
                "supported": proc_supported,
                "scope": scope,
                "notes": "In containers, you usually only see container processes (PID namespace)."
            },
            "network_visibility": {
                "supported": net_supported,
                "scope": scope,
                "notes": "In containers, ports reflect the container network namespace unless using host networking.",
                "reason": net_reason
            },
            "cgroup_limits": cgroups,
            "optional_binaries": {
                "nvidia_smi": bool(shutil_which("nvidia-smi")),
                "ip": bool(shutil_which("ip")),
                "ss": bool(shutil_which("ss")),
                "netstat": bool(shutil_which("netstat")),
            },
        },
    }


def shutil_which(cmd: str) -> Optional[str]:
    # tiny local equivalent to shutil.which, without importing more
    paths = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""]  # Unix
    if platform.system().lower() == "windows":
        pathext = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
        exts = pathext

    for p in paths:
        p = p.strip('"')
        if not p:
            continue
        for ext in exts:
            full = os.path.join(p, cmd + ext)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
    return None


def system_info() -> Dict[str, Any]:
    boot = None
    try:
        boot = psutil.boot_time()
    except Exception:
        pass

    return {
        "supported": True,
        "scope": "container" if _is_running_in_container() else "host",
        "data": {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version,
            "executable": sys.executable,
            "uptime_seconds": (time.time() - boot) if boot else None,
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
        },
    }


def resource_snapshot(sample_cpu_seconds: float = 0.8) -> Dict[str, Any]:
    # CPU percent: sample over a short interval for more meaningful value
    try:
        cpu = psutil.cpu_percent(interval=sample_cpu_seconds)
    except Exception:
        cpu = None

    try:
        mem = psutil.virtual_memory()
        mem_data = {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        }
    except Exception:
        mem_data = None

    # Disk: use current working dir's mount
    try:
        disk = psutil.disk_usage(os.getcwd())
        disk_data = {
            "path": os.getcwd(),
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }
    except Exception:
        disk_data = None

    # Load average is not available on Windows
    load_avg = None
    try:
        if hasattr(os, "getloadavg"):
            load_avg = os.getloadavg()
    except Exception:
        pass

    return {
        "supported": True,
        "scope": "container" if _is_running_in_container() else "host",
        "data": {
            "cpu_percent": cpu,
            "load_avg": load_avg,
            "memory": mem_data,
            "disk": disk_data,
        },
    }


def list_processes(limit: int = 30, name_regex: Optional[str] = None) -> Dict[str, Any]:
    """
    Lists processes visible in the current PID namespace.
    """
    regex = re.compile(name_regex, re.IGNORECASE) if name_regex else None
    rows: List[Dict[str, Any]] = []

    for p in psutil.process_iter(attrs=["pid", "name", "username", "cpu_percent", "memory_percent", "cmdline", "status"]):
        try:
            info = p.info
            name = info.get("name") or ""
            if regex and not regex.search(name):
                continue
            cmdline = info.get("cmdline") or []
            rows.append({
                "pid": info.get("pid"),
                "name": name,
                "username": info.get("username"),
                "status": info.get("status"),
                "cpu_percent": info.get("cpu_percent"),
                "memory_percent": info.get("memory_percent"),
                "cmdline": " ".join(cmdline) if isinstance(cmdline, list) else str(cmdline),
            })
            if len(rows) >= limit:
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue

    return {
        "supported": True,
        "scope": "container" if _is_running_in_container() else "host",
        "data": {"processes": rows, "limit": limit, "filter": {"name_regex": name_regex}},
    }


def process_details(pid: int) -> Dict[str, Any]:
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            data = {
                "pid": p.pid,
                "name": p.name(),
                "status": p.status(),
                "username": safe_call(p.username),
                "create_time": safe_call(p.create_time),
                "ppid": safe_call(p.ppid),
                "cmdline": " ".join(safe_call(p.cmdline) or []),
                "cpu_percent": safe_call(p.cpu_percent),
                "memory_info": safe_call(lambda: p.memory_info()._asdict()),
                "memory_percent": safe_call(p.memory_percent),
                "num_threads": safe_call(p.num_threads),
                "children": [{"pid": c.pid, "name": safe_call(c.name)} for c in safe_call(lambda: p.children(recursive=False)) or []],
                "connections_count": safe_call(lambda: len(p.connections(kind="inet"))) if hasattr(p, "connections") else None,
            }
        return {"supported": True, "scope": "container" if _is_running_in_container() else "host", "data": data}
    except psutil.NoSuchProcess:
        return {"supported": False, "scope": "container" if _is_running_in_container() else "host", "reason": "No such process", "data": None}
    except psutil.AccessDenied as e:
        return {"supported": False, "scope": "container" if _is_running_in_container() else "host", "reason": f"Access denied: {e}", "data": None}


def safe_call(fn):
    try:
        return fn()
    except Exception:
        return None


def check_port(port: int, protocol: str = "tcp") -> Dict[str, Any]:
    """
    Returns listeners on a port visible to this runtime (container or host).
    """
    proto = protocol.lower()
    kind = "inet"  # includes tcp+udp
    try:
        conns = psutil.net_connections(kind=kind)
    except Exception as e:
        return {
            "supported": False,
            "scope": "container" if _is_running_in_container() else "host",
            "reason": f"Cannot read net connections: {type(e).__name__}: {e}",
            "data": None,
        }

    listeners = []
    for c in conns:
        try:
            if c.laddr is None:
                continue
            lport = c.laddr.port if hasattr(c.laddr, "port") else None
            if lport != port:
                continue

            # Filter protocol if requested
            if proto == "tcp" and c.type != socket.SOCK_STREAM:
                continue
            if proto == "udp" and c.type != socket.SOCK_DGRAM:
                continue

            listeners.append({
                "pid": c.pid,
                "status": getattr(c, "status", None),
                "local_address": f"{c.laddr.ip}:{c.laddr.port}" if hasattr(c.laddr, "ip") else str(c.laddr),
                "remote_address": (
                    f"{c.raddr.ip}:{c.raddr.port}" if getattr(c, "raddr", None) and hasattr(c.raddr, "ip") else (str(c.raddr) if getattr(c, "raddr", None) else None)
                ),
                "family": str(c.family),
                "type": str(c.type),
            })
        except Exception:
            continue

    # Attach process names when possible
    for item in listeners:
        pid = item.get("pid")
        if pid:
            try:
                item["process_name"] = psutil.Process(pid).name()
            except Exception:
                item["process_name"] = None

    return {
        "supported": True,
        "scope": "container" if _is_running_in_container() else "host",
        "data": {"port": port, "protocol": proto, "listeners": listeners, "count": len(listeners)},
    }


def dns_lookup(name: str, record_type: str = "A") -> Dict[str, Any]:
    """
    Portable DNS check using getaddrinfo.
    record_type is advisory; getaddrinfo returns what the system resolver provides.
    """
    try:
        infos = socket.getaddrinfo(name, None)
        ips = sorted({i[4][0] for i in infos if i and i[4]})
        return {
            "supported": True,
            "scope": "container" if _is_running_in_container() else "host",
            "data": {"name": name, "record_type": record_type, "ips": ips},
        }
    except Exception as e:
        return {
            "supported": True,
            "scope": "container" if _is_running_in_container() else "host",
            "data": {"name": name, "record_type": record_type, "ips": []},
            "error": {"type": type(e).__name__, "message": str(e)},
        }

def list_environment_variables(redact: bool = True) -> Dict[str, Any]:
    """
    List environment variables visible to this process.
    By default, redact values that look sensitive.
    """
    sensitive_patterns = [
        "KEY", "TOKEN", "SECRET", "PASSWORD", "PWD",
        "API_KEY", "AUTH", "CREDENTIAL", "PRIVATE"
    ]

    def is_sensitive(name: str) -> bool:
        upper = name.upper()
        return any(p in upper for p in sensitive_patterns)

    env = {}
    for k, v in os.environ.items():
        if redact and is_sensitive(k):
            env[k] = "***REDACTED***"
        else:
            env[k] = v

    return {
        "supported": True,
        "scope": "container" if _is_running_in_container() else "host",
        "data": {
            "count": len(env),
            "redacted": redact,
            "variables": env,
        },
    }


# -----------------------------
# Tool schemas for OpenAI-style tool calling
# -----------------------------

TOOLS = [
    {
        "type": "function",
        "name": "capability_report",
        "description": "Report what the agent can observe (container/host scope, visibility limits, optional binaries, cgroup limits).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "system_info",
        "description": "Return OS, kernel, CPU counts, Python runtime and uptime.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "resource_snapshot",
        "description": "Return CPU/memory/disk usage (best-effort).",
        "parameters": {
            "type": "object",
                "properties": {
                    "sample_cpu_seconds": {"type": "number", "description": "Sampling interval for CPU percent.", "default": 0.8},
                },
                "required": [],
        },
    },
    {
        "type": "function",
        "name": "list_processes",
        "description": "List processes visible to this runtime. Optional name regex filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30},
                "name_regex": {"type": ["string", "null"], "description": "Regex to filter by process name.", "default": None},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "process_details",
        "description": "Return detailed info for a PID (name, cmdline, cpu/mem, children, etc.).",
        "parameters": {
            "type": "object",
            "properties": {"pid": {"type": "integer", "minimum": 1}},
            "required": ["pid"],
        },
    },
    {
        "type": "function",
        "name": "check_port",
        "description": "Check listeners for a given port in the current network namespace.",
        "parameters": {
            "type": "object",
                "properties": {
                    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                    "protocol": {"type": "string", "enum": ["tcp", "udp"], "default": "tcp"},
                },
                "required": ["port"],
        },
    },
    {
        "type": "function",
        "name": "dns_lookup",
        "description": "Resolve a hostname using the system resolver.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "record_type": {"type": "string", "default": "A"},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "list_environment_variables",
        "description": "List environment variables visible to the current process. Sensitive values are redacted by default.",
        "parameters": {
            "type": "object",
            "properties": {
                "redact": {
                    "type": "boolean",
                    "description": "Whether to redact sensitive variables (recommended).",
                    "default": True
                }
            },
            "required": []
        },
    },
]

TOOL_IMPL = {
    "capability_report": lambda **kwargs: capability_report(),
    "system_info": lambda **kwargs: system_info(),
    "resource_snapshot": lambda **kwargs: resource_snapshot(**kwargs),
    "list_processes": lambda **kwargs: list_processes(**kwargs),
    "process_details": lambda **kwargs: process_details(**kwargs),
    "check_port": lambda **kwargs: check_port(**kwargs),
    "dns_lookup": lambda **kwargs: dns_lookup(**kwargs),
    "list_environment_variables": lambda **kwargs: list_environment_variables(**kwargs),
}
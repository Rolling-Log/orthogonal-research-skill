#!/usr/bin/env python3
"""Resolve optional retrieval tools without installing or modifying the environment."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS = ("agent-reach", "mcporter", "yt-dlp", "gh")
NETWORK_ENV = {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "NODE_USE_ENV_PROXY"}
DEFAULT_CONFIG = Path.home() / ".config" / "orthogonal-research" / "retrieval.json"


def read_config(path):
    if not path.exists():
        return {"commands": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("commands", {}), dict):
        raise ValueError("config.commands must be an object")
    for name, argv in data.get("commands", {}).items():
        if name not in TOOLS or not isinstance(argv, list) or not argv:
            raise ValueError("unknown tool or empty command array")
        if not all(isinstance(arg, str) and arg and "\0" not in arg for arg in argv):
            raise ValueError("command arguments must be nonempty strings without NUL")
    network = data.get("network_env", {})
    if not isinstance(network, dict) or any(
            key not in NETWORK_ENV or not isinstance(value, str) or "\0" in value
            for key, value in network.items()):
        raise ValueError("network_env only accepts HTTP_PROXY, HTTPS_PROXY, NO_PROXY, NODE_USE_ENV_PROXY")
    return data


def resolve(name, config):
    argv = config.get("commands", {}).get(name)
    origin = "config" if argv else "PATH"
    argv = list(argv) if argv else [name]
    executable = shutil.which(argv[0])
    if not executable:
        return {"status": "missing", "origin": origin}
    if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat", ".ps1"):
        return {"status": "needs_native_command", "origin": origin,
                "hint": "Configure node.exe + the CLI .js file; shell wrappers are not executed."}
    argv[0] = executable
    return {"status": "installed", "origin": origin, "argv": argv,
            "live_content": "not_tested"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--timeout", type=float, default=60)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("probe", help="Offline discovery; does not assert live availability")
    run = sub.add_parser("run", help="Run the installed upstream tool without a shell")
    run.add_argument("tool", choices=TOOLS)
    run.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be between 0 and 300 seconds")
    try:
        config = read_config(args.config)
        if args.action == "probe":
            print(json.dumps({"config": str(args.config), "config_exists": args.config.exists(),
                              "tools": {name: resolve(name, config) for name in TOOLS}},
                             ensure_ascii=False, indent=2))
            return 0
        tool = resolve(args.tool, config)
        if tool["status"] != "installed":
            print(json.dumps(tool, ensure_ascii=False), file=sys.stderr)
            return 2
        passthrough = args.args[1:] if args.args[:1] == ["--"] else args.args
        env = os.environ.copy()
        env.update(config.get("network_env", {}))
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(tool["argv"] + passthrough, shell=False,
                                env=env, timeout=args.timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print("Upstream tool exceeded the time limit; content is not verified.", file=sys.stderr)
        return 124
    except (OSError, ValueError) as exc:
        print(f"Retrieval configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Simple launcher for DS-Carrera components."""

import os
import platform
import subprocess
import signal
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config.yaml"

processes = []


def resolve_command(command: str) -> str:
    """Resolve command aliases (especially for Windows PowerShell)."""
    if platform.system() != "Windows":
        return command
    
    # Get the first word (the executable)
    parts = command.split(maxsplit=1)
    exe = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    
    # Try to resolve via PowerShell alias
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"(Get-Alias {exe} -ErrorAction SilentlyContinue).Definition"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            resolved = result.stdout.strip()
            return f'"{resolved}" {rest}' if rest else f'"{resolved}"'
    except:
        pass
    
    return command


def stop_all(sig=None, frame=None):
    """Stop all running processes."""
    print("\nStopping all components...")
    for name, proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
            print(f"  Stopped {name}")
    sys.exit(0)


def main():
    # Load config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    # Get profile from args
    profile = sys.argv[1] if len(sys.argv) > 1 else "full"
    
    if profile == "--list":
        print("Profiles:", ", ".join(config["profiles"].keys()))
        print("Components:", ", ".join(config["components"].keys()))
        return

    if profile not in config["profiles"]:
        print(f"Unknown profile: {profile}")
        print(f"Available: {', '.join(config['profiles'].keys())}")
        return

    # Setup signal handler
    signal.signal(signal.SIGINT, stop_all)

    # Start components
    print(f"Starting profile: {profile}")
    for comp_id in config["profiles"][profile]:
        comp = config["components"][comp_id]
        print(f"  Starting {comp['name']}...")
        
        cmd = resolve_command(comp["command"])
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=PROJECT_ROOT,
        )
        processes.append((comp["name"], proc))
        
        if comp.get("delay", 0) > 0:
            time.sleep(comp["delay"])

    print("All components started. Press Ctrl+C to stop.")
    
    # Wait for processes
    while any(p.poll() is None for _, p in processes):
        time.sleep(1)


if __name__ == "__main__":
    main()

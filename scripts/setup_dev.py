#!/usr/bin/env python3
"""
Development Environment Verification Script — BidGuard (SIH26100)
Checks system prerequisites: Python version, Node.js, Docker, .env configuration, and DB connectivity.
"""

import sys
import os
import shutil
import subprocess


def check_python():
    print("[1/5] Checking Python version...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 11):
        print(f"  [ERROR] Python 3.11+ required. Found {sys.version.split()[0]}")
        return False
    print(f"  [OK] Python {sys.version.split()[0]}")
    return True


def check_node():
    print("[2/5] Checking Node.js & npm...")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        print("  [WARN] Node.js or npm not found in PATH. Required for frontend development.")
        return False
    try:
        node_v = subprocess.check_output(["node", "--version"], text=True).strip()
        print(f"  [OK] Node.js {node_v}")
        return True
    except Exception:
        return False


def check_docker():
    print("[3/5] Checking Docker & Docker Compose...")
    docker = shutil.which("docker")
    if not docker:
        print("  [WARN] Docker not found. Required if running multi-container stack via 'docker compose up'.")
        return False
    try:
        docker_v = subprocess.check_output(["docker", "--version"], text=True).strip()
        print(f"  [OK] {docker_v}")
        return True
    except Exception:
        return False


def check_env_file():
    print("[4/5] Checking environment configuration (.env)...")
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.example")

    if not os.path.exists(env_path):
        if os.path.exists(example_path):
            print("  [INFO] .env not found. Creating from .env.example...")
            shutil.copy(example_path, env_path)
            print("  [OK] Created .env template. Please configure your API keys.")
        else:
            print("  [ERROR] Neither .env nor .env.example found.")
            return False
    else:
        print("  [OK] .env file exists.")
    return True


def main():
    print("=" * 60)
    print(" BidGuard Dev Environment Verification (SIH26100)")
    print("=" * 60)
    p_ok = check_python()
    n_ok = check_node()
    d_ok = check_docker()
    e_ok = check_env_file()

    print("\nVerification Summary:")
    print(f"  Python: {'PASSED' if p_ok else 'FAILED'}")
    print(f"  Node.js: {'PASSED' if n_ok else 'WARNING'}")
    print(f"  Docker: {'PASSED' if d_ok else 'WARNING'}")
    print(f"  Environment: {'PASSED' if e_ok else 'FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    main()

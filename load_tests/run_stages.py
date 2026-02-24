from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def parse_users(raw: str) -> list[int]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    users = [int(item) for item in values]
    if not users:
        raise ValueError("At least one user stage is required")
    if any(value <= 0 for value in users):
        raise ValueError("User stages must be > 0")
    return users


def run_stage(
    locustfile: Path,
    host: str,
    users: int,
    spawn_rate: float,
    duration: str,
    out_prefix: Path,
) -> int:
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(locustfile),
        "--host",
        host,
        "--headless",
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "--run-time",
        duration,
        "--csv",
        str(out_prefix),
        "--html",
        f"{out_prefix}.html",
        "--only-summary",
    ]

    print("\n" + "=" * 80)
    print(f"Stage users={users} duration={duration} spawn_rate={spawn_rate}")
    print("Command:", " ".join(command))
    print("=" * 80)

    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged Locust load tests for Streamlit app")
    parser.add_argument("--host", required=True, help="Target host, e.g. http://localhost:8501")
    parser.add_argument(
        "--users",
        default="5,20,50,75,100",
        help="Comma-separated user stages (default: 5,20,50,75,100)",
    )
    parser.add_argument("--duration", default="10m", help="Stage duration, Locust format (default: 10m)")
    parser.add_argument("--spawn-rate", type=float, default=5.0, help="User spawn rate (default: 5)")
    parser.add_argument(
        "--locustfile",
        default="load_tests/locustfile.py",
        help="Path to locustfile (default: load_tests/locustfile.py)",
    )
    parser.add_argument(
        "--output-dir",
        default="load_tests/results",
        help="Directory for stage reports (default: load_tests/results)",
    )

    args = parser.parse_args()
    stages = parse_users(args.users)
    locustfile = Path(args.locustfile)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    failed_stages = []

    print(f"Run ID: {run_id}")
    print(f"Stages: {stages}")
    print(f"Output dir: {output_dir.resolve()}")

    for users in stages:
        prefix = output_dir / f"{run_id}_u{users}"
        code = run_stage(
            locustfile=locustfile,
            host=args.host,
            users=users,
            spawn_rate=args.spawn_rate,
            duration=args.duration,
            out_prefix=prefix,
        )
        if code != 0:
            failed_stages.append((users, code))
            print(f"Stage users={users} failed with exit code {code}")

    if failed_stages:
        print("\nSome stages failed:")
        for users, code in failed_stages:
            print(f"- users={users}, code={code}")
        return 1

    print("\nAll stages completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

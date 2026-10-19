"""Daily refresh: rediscover sources, run every collector, rebuild the site.

A collector that fails keeps yesterday's file, so one broken corporation site never empties
the whole region list. Exit code is non-zero if any step failed, for the scheduler's log.
"""
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
STEPS = ["discover.py", "collect.py", "collect_sugang.py", "collect_html.py", "build.py"]


def main():
    failed = []
    for step in STEPS:
        t0 = time.time()
        r = subprocess.run([sys.executable, "-u", str(ROOT / "scripts" / step)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        print(f"{step:<20} {'ok ' if r.returncode == 0 else 'FAIL'} {time.time() - t0:6.0f}s  {tail}")
        if r.returncode != 0:
            failed.append(step)
            print(r.stderr[-1500:])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

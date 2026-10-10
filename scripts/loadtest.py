#!/usr/bin/env python3
"""
Constant-load tester for the zero-downtime experiments. Python 3 standard library only.

Sends requests in parallel for a fixed duration and prints one line per second:
how many succeeded, how many failed, and which app version answered. During a
rolling update you can watch v1 turn into v2 live, and see exactly when errors happen.

Examples:
  python3 scripts/loadtest.py --url http://<node-ip>:30080 --duration 90 --name e1-naive
  python3 scripts/loadtest.py --url http://<node-ip>:30080 --path "/api/work?ms=2000" --name e3
  python3 scripts/loadtest.py --url http://<node-ip>:30080 --path "/api/cpu?ms=200" --concurrency 20 --duration 300 --name e6
"""
import argparse
import csv
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict


def classify(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    text = str(reason).lower()
    if "refused" in text:
        return "connection refused"
    if "reset" in text:
        return "connection reset"
    if "timed out" in text or isinstance(reason, TimeoutError):
        return "timeout"
    if type(reason).__name__ == "RemoteDisconnected":
        return "connection closed"
    return type(reason).__name__


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))
    return values[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="base URL, e.g. http://10.0.0.5:30080")
    ap.add_argument("--path", default="/api/info")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--duration", type=int, default=60, help="seconds")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--name", default="run", help="results are saved as results/<name>.csv")
    args = ap.parse_args()

    target = args.url.rstrip("/") + args.path
    start = time.time()
    stop_at = start + args.duration
    lock = threading.Lock()
    rows = []  # (t_offset, ok, latency_ms, version, error)

    def worker():
        while time.time() < stop_at:
            t0 = time.time()
            version, error = "", ""
            try:
                with urllib.request.urlopen(target, timeout=args.timeout) as resp:
                    body = resp.read()
                try:
                    version = json.loads(body).get("version", "")
                except ValueError:
                    pass
                ok = True
            except Exception as exc:  # noqa: BLE001 - every failure is a data point
                ok, error = False, classify(exc)
                time.sleep(0.05)  # avoid a hot loop when the target is down
            latency = (time.time() - t0) * 1000
            with lock:
                rows.append((t0 - start, ok, latency, version, error))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.concurrency)]
    for t in threads:
        t.start()

    print(f"Target {target} | concurrency {args.concurrency} | {args.duration}s")
    print(f"{'sec':>4} {'ok':>6} {'err':>5}  versions / errors")
    printed = 0
    while time.time() < stop_at or any(t.is_alive() for t in threads):
        time.sleep(1)
        now_sec = int(time.time() - start)
        with lock:
            snapshot = list(rows)
        while printed < now_sec:
            sec_rows = [r for r in snapshot if int(r[0]) == printed]
            ok = sum(1 for r in sec_rows if r[1])
            err = len(sec_rows) - ok
            versions = Counter(r[3] for r in sec_rows if r[1])
            errors = Counter(r[4] for r in sec_rows if not r[1])
            detail = " ".join(f"{v}={n}" for v, n in sorted(versions.items()))
            if errors:
                detail += "  !! " + ", ".join(f"{e}={n}" for e, n in errors.items())
            marker = " <-- ERRORS" if err else ""
            print(f"{printed:>4} {ok:>6} {err:>5}  {detail}{marker}", flush=True)
            printed += 1
        if printed >= args.duration and not any(t.is_alive() for t in threads):
            break

    total = len(rows)
    failed = [r for r in rows if not r[1]]
    latencies = [r[2] for r in rows if r[1]]
    error_seconds = sorted({int(r[0]) for r in failed})
    by_error = Counter(r[4] for r in failed)

    print("\n=== Summary ===")
    print(f"requests       : {total}")
    print(f"failed         : {len(failed)} ({(len(failed) / total * 100 if total else 0):.2f}%)")
    for e, n in by_error.most_common():
        print(f"  {e:<20}: {n}")
    print(f"seconds w/ err : {len(error_seconds)}" + (f" (from {error_seconds[0]}s to {error_seconds[-1]}s)" if error_seconds else ""))
    print(f"latency p50    : {percentile(latencies, 50):.0f} ms")
    print(f"latency p99    : {percentile(latencies, 99):.0f} ms")
    print(f"latency max    : {max(latencies) if latencies else 0:.0f} ms")

    os.makedirs("results", exist_ok=True)
    path = os.path.join("results", f"{args.name}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_offset_s", "ok", "latency_ms", "version", "error"])
        for r in rows:
            w.writerow([f"{r[0]:.3f}", int(r[1]), f"{r[2]:.1f}", r[3], r[4]])
    print(f"raw data       : {path}")


if __name__ == "__main__":
    main()

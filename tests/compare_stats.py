from __future__ import annotations
import statistics
import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # headless safe for CI/pytest
import matplotlib.pyplot as plt


METRICS = ("mean", "median", "stdev", "stdev_normalized")


@dataclass
class RunStat:
    run_id: str
    stats_path: Path
    ammeters: Dict[str, Dict[str, Optional[float]]]


def _cv(stdev_v, mean_v):
    if stdev_v is None or mean_v is None:
        return None
    if mean_v == 0.0:
        return None
    return stdev_v / mean_v

def _ci95(stdev_v, n_ok):
    if stdev_v is None or n_ok is None:
        return None
    try:
        n_ok = int(n_ok)
    except Exception:
        return None
    if n_ok <= 0:
        return None
    return 1.96 * (stdev_v / math.sqrt(n_ok))

def _summary(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {
        "count": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
    }

def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isfinite(v):
            return v
        return None
    except Exception:
        return None


def _compute_stdev_normalized(stdev: Optional[float], mean: Optional[float]) -> Optional[float]:
    if stdev is None or mean is None:
        return None
    if mean == 0.0:
        return None
    return stdev / mean


def _find_stats_files(runs_dir: Path) -> List[Path]:
    # Expected: tests/out/<timestamp>/analysis/stats.json
    # But we search recursively to be robust.
    return sorted(runs_dir.rglob("stats.json"))


def _load_run(stats_path: Path) -> Optional[RunStat]:
    try:
        data = json.loads(stats_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    run_id = str(data.get("run_id") or stats_path.parents[1].name)  # fallback: run dir name
    ammeters = data.get("ammeters") or {}

    cleaned: Dict[str, Dict[str, Optional[float]]] = {}
    for name, s in ammeters.items():
        if not isinstance(s, dict):
            continue
        mean_v = _safe_float(s.get("mean"))
        median_v = _safe_float(s.get("median"))
        stdev_v = _safe_float(s.get("stdev"))
        stdev_norm = _compute_stdev_normalized(stdev_v, mean_v)

        cleaned[name] = {
            "mean": mean_v,
            "median": median_v,
            "stdev": stdev_v,
            "stdev_normalized": stdev_norm,
            # You can keep counts if you want later:
            "count_ok": _safe_float(s.get("count_ok")),
            "count_total": _safe_float(s.get("count_total")),
        }

    return RunStat(run_id=run_id, stats_path=stats_path, ammeters=cleaned)


def _sort_runs(runs: List[RunStat]) -> List[RunStat]:
    # Your run_id is a timestamp folder name like 2026-02-28T16-03-24
    # Sorting lexicographically works for that format.
    return sorted(runs, key=lambda r: r.run_id)


def _filter_ammeters(runs: List[RunStat], allowed: Optional[List[str]]) -> List[str]:
    found = set()
    for r in runs:
        found.update(r.ammeters.keys())

    if not allowed:
        return sorted(found)

    allowed_set = set(allowed)
    return [a for a in sorted(found) if a in allowed_set]


def _series_for_metric(runs: List[RunStat], ammeter: str, metric: str) -> Tuple[List[int], List[float]]:
    xs: List[int] = []
    ys: List[float] = []
    for i, r in enumerate(runs):
        v = r.ammeters.get(ammeter, {}).get(metric)
        if v is None:
            continue
        xs.append(i)
        ys.append(v)
    return xs, ys


def _dot_plot(xs: List[int], ys: List[float], title: str, xlabel: str, ylabel: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure()
    plt.plot(xs, ys, linestyle="None", marker="o")  # dots only
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _unified_dot_plot(
    runs: List[RunStat],
    ammeters: List[str],
    metric: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure()

    # Each ammeter gets its own dot series.
    for a in ammeters:
        xs, ys = _series_for_metric(runs, a, metric)
        if xs and ys:
            plt.plot(xs, ys, linestyle="None", marker="o", label=a)

    plt.title(f"unified {metric}")
    plt.xlabel("run index")
    plt.ylabel(metric)
    plt.grid(True)
    plt.legend()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare historical ammeter stats across runs.")
    ap.add_argument("--runs-dir", default="tests/out", help="Directory containing run folders (default: tests/out)")
    ap.add_argument("--out-dir", default="out/statistic", help="Output base directory (default: out/statistic)")
    ap.add_argument("--ammeters", nargs="*", help="Ammeter names to include (default: all found)")
    ap.add_argument("--precision", action="store_true", help="Print CV and CI95 across runs per ammeter")
    ap.add_argument("--per-run", action="store_true", help="Also print per-run CV/CI95 lines (with --precision)")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    if not runs_dir.exists():
        print(f"ERROR: runs dir not found: {runs_dir}")
        return 2

    stats_files = _find_stats_files(runs_dir)
    if not stats_files:
        print(f"ERROR: no stats.json found under: {runs_dir}")
        return 2

    loaded: List[RunStat] = []
    for p in stats_files:
        r = _load_run(p)
        if r is not None:
            loaded.append(r)

    if not loaded:
        print("ERROR: found stats.json files but failed to parse any.")
        return 2

    runs = _sort_runs(loaded)
    ammeters = _filter_ammeters(runs, args.ammeters)

    if not ammeters:
        print("ERROR: no matching ammeters found in stats.")
        return 2

    # ----- Precision reporting mode (no plots) -----
    if args.precision:
        print("\n=== Precision report (cross-run) ===")
        for a in ammeters:
            cvs = []
            ci95s = []

            per_run_rows = []
            for r in runs:
                stdev_v = r.ammeters.get(a, {}).get("stdev")
                mean_v = r.ammeters.get(a, {}).get("mean")
                n_ok = r.ammeters.get(a, {}).get("count_ok")

                cv_v = _cv(stdev_v, mean_v)
                ci_v = _ci95(stdev_v, n_ok)

                cvs.append(cv_v)
                ci95s.append(ci_v)

                if args.per_run:
                    per_run_rows.append((r.run_id, cv_v, ci_v, n_ok))

            cv_sum = _summary(cvs)
            ci_sum = _summary(ci95s)

            print(f"\n[{a}]")
            if cv_sum is None:
                print("  CV:   no valid data")
            else:
                print(
                    f"  CV:   count={cv_sum['count']} mean={cv_sum['mean']:.6g} median={cv_sum['median']:.6g} "
                    f"min={cv_sum['min']:.6g} max={cv_sum['max']:.6g}"
                )

            if ci_sum is None:
                print("  CI95: no valid data")
            else:
                print(
                    f"  CI95: count={ci_sum['count']} mean={ci_sum['mean']:.6g} median={ci_sum['median']:.6g} "
                    f"min={ci_sum['min']:.6g} max={ci_sum['max']:.6g}"
                )

            if args.per_run and per_run_rows:
                print("  per-run:")
                for run_id, cv_v, ci_v, n_ok in per_run_rows:
                    cv_s = "None" if cv_v is None else f"{cv_v:.6g}"
                    ci_s = "None" if ci_v is None else f"{ci_v:.6g}"
                    print(f"    {run_id}: CV={cv_s} CI95={ci_s} n_ok={n_ok}")

        return 0

    # Output folder: out/statistic/<timestamp>
    ts = __import__("time").strftime("%Y-%m-%dT%H-%M-%S")
    out_root = Path(args.out_dir) / ts
    out_root.mkdir(parents=True, exist_ok=True)

    # Optional: write a summary.json of what we used
    summary = {
        "runs_dir": str(runs_dir),
        "stats_files_count": len(stats_files),
        "runs_used": [{"run_id": r.run_id, "stats_path": str(r.stats_path)} for r in runs],
        "ammeters": ammeters,
        "metrics": list(METRICS),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Per-ammeter plots
    for a in ammeters:
        for metric in METRICS:
            xs, ys = _series_for_metric(runs, a, metric)
            if not xs:
                continue
            _dot_plot(
                xs,
                ys,
                title=f"{a} {metric}",
                xlabel="run index",
                ylabel=metric,
                out_path=out_root / f"{a}__{metric}.png",
            )

    # Unified plots if multiple ammeters
    if len(ammeters) >= 2:
        for metric in METRICS:
            # Only create if at least one ammeter has points for this metric
            any_points = any(_series_for_metric(runs, a, metric)[0] for a in ammeters)
            if not any_points:
                continue
            _unified_dot_plot(runs, ammeters, metric, out_root / f"unified__{metric}.png")

    print(f"OK: wrote plots to: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
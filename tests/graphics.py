from pathlib import Path
import csv
import matplotlib.pyplot as plt


def simple_value_time_plot(csv_path: Path, output_path: Path) -> Path:
    """
    Plot Y=value over X=measurement index (0..N-1).
    Uses ONLY rows where status == "OK".
    Requires CSV columns: value, status
    """

    ys = []

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "").strip() != "OK":
                continue
            try:
                v = float(row["value"])
            except (KeyError, ValueError, TypeError):
                continue
            ys.append(v)

    xs = list(range(len(ys)))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure()

    plt.plot(xs, ys)
    plt.xlabel("measurement index")
    plt.ylabel("current (A)")
    plt.grid(True)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return output_path
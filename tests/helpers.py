# tests/test_utils.py
import math
import time
import csv

ERROR_CODES = {-1.0: "NO_DATA", -2.0: "TIMEOUT", -3.0: "EXCEPTION", -4.0: "OUT_OF_VALID_RANGE"}
DEFAULT_MEASUREMENTS_COUNT = 20  # if config provides only sampling_frequency_ms

def append_measurement_row(run_context: dict, spec: dict, value: float, out_of_range=False) -> None:
    out_path = run_context["csv_paths"][spec["name"]]
    logger = run_context["logger"]

    status = "OK"
    if value in ERROR_CODES.keys():
        status = ERROR_CODES[value]

    elif out_of_range:
        status = ERROR_CODES[-4]

    t_epoch = time.time()

    row = [
        t_epoch,
        spec["name"],
        spec["port"],
        spec["command"].decode("utf-8", errors="replace"),
        value,
        status,
        spec["expected_min"],
        spec["expected_max"],
    ]

    with out_path.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

    logger.info(f"{spec['name']}: value={value} status={status}")

def build_sampling_plan(sampling_cfg: dict) -> dict:

    mc = sampling_cfg.get("measurements_count")
    td = sampling_cfg.get("total_duration_ms")
    sf = sampling_cfg.get("sampling_frequency_ms")
    min_val = sampling_cfg.get("sampling_frequency_min_val", 25)

    # Normalize
    mc = int(mc) if mc is not None else None
    td = int(td) if td is not None else None
    sf = int(sf) if sf is not None else None
    min_val = int(min_val)

    if min_val <= 0:
        raise RuntimeError("sampling_frequency_min_val must be > 0")

    # Rule: if mc and td exist -> derive sf
    if mc is not None and td is not None:
        if mc <= 0:
            raise RuntimeError("measurements_count must be > 0")
        if td <= 0:
            raise RuntimeError("total_duration_ms must be > 0")

        derived_sf = td / mc
        if derived_sf < min_val:
            raise RuntimeError(
                f"Derived sampling_frequency_ms ({derived_sf:.2f}) < sampling_frequency_min_val ({min_val})"
            )
        sf = int(round(derived_sf))

    # Rule: if td and sf exist -> td must be larger than sf
    if td is not None and sf is not None:
        if td <= sf:
            raise RuntimeError(
                f"total_duration_ms ({td}) must be > sampling_frequency_ms ({sf})"
            )
        if sf < min_val:
            raise RuntimeError(
                f"sampling_frequency_ms ({sf}) < sampling_frequency_min_val ({min_val})"
            )

    # Rule: sf must respect min_val if it exists
    if sf is not None and sf < min_val:
        raise RuntimeError(
            f"sampling_frequency_ms ({sf}) < sampling_frequency_min_val ({min_val})"
        )

    # Decide final measurements_count
    if mc is not None:
        final_mc = mc
    elif td is not None and sf is not None:
        # number of samples implied by duration and frequency (at least 1)
        final_mc = max(1, int(math.floor(td / sf)))
    elif sf is not None:
        # only frequency provided -> choose a default batch size
        final_mc = DEFAULT_MEASUREMENTS_COUNT
    else:
        raise RuntimeError("Invalid sampling config: could not determine sampling plan")

    if sf is None:
        raise RuntimeError("sampling_frequency_ms is required to build the sampling plan")

    return {
        "measurements_count": final_mc,
        "sampling_frequency_ms": sf,
        "period_s": sf / 1000.0,
    }
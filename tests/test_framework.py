import time
import pytest

from Ammeters.client import request_current_from_ammeter
from tests.helpers import build_sampling_plan, append_measurement_row


def test_request_current_from_ammeter_correct_command(spec_name, ammeter_specs, sampling_cfg, run_context):

    spec = next(s for s in ammeter_specs if s["name"] == spec_name)

    plan = build_sampling_plan(sampling_cfg)
    n = plan["measurements_count"]
    period_s = plan["period_s"]

    out_of_range = []
    error_codes = []

    for i in range(n):
        value = request_current_from_ammeter(spec["port"], spec["command"])

        # Log + append to CSV throughout the run
        if value in (-1.0, -2.0, -3.0):
            error_codes.append((i, value))
            append_measurement_row(run_context, spec, value)

        elif spec["expected_min"] <= value <= spec["expected_max"]:
            append_measurement_row(run_context, spec, value)

        else:
            out_of_range.append((i, value))
            # special marker for OUT_OF_RANGE
            append_measurement_row(run_context, spec, value, True)

        time.sleep(period_s)

    # Fail only at the end so we always complete all samples and fill logs/CSVs
    if error_codes or out_of_range:
        parts = []
        if error_codes:
            parts.append(f"error_codes={len(error_codes)} (first 3: {error_codes[:3]})")
        if out_of_range:
            parts.append(f"out_of_range={len(out_of_range)} (first 3: {out_of_range[:3]})")

        pytest.fail(
            f"{spec_name} sampling had failures: " + ", ".join(parts) +
            f". Expected range=[{spec['expected_min']}, {spec['expected_max']}]."
        )


def test_request_current_from_ammeter_invalid_command(spec_name, ammeter_specs, run_context):
    spec = next(s for s in ammeter_specs if s["name"] == spec_name)

    invalid_command = b"INVALID_COMMAND_DOES_NOT_EXIST"
    value = request_current_from_ammeter(spec["port"], invalid_command)

    # Optional: log invalid-command attempts as well (useful for run logs)
    append_measurement_row(run_context, spec, value)

    assert value in (-1.0, -2.0, -3.0), (
        f"{spec_name} should not return a valid measurement for invalid command. "
        f"Got: {value}"
    )
import csv
import json
import math
import socket
import time
from pathlib import Path
from statistics import mean, median, stdev
import pytest
from Ammeters.client import request_current_from_ammeter

import pytest
from Ammeters.client import request_current_from_ammeter


@pytest.mark.parametrize("spec_name", ["greenlee", "entes", "circutor"])
def test_request_current_from_ammeter_correct_command(spec_name, ammeter_specs):
    spec = next(s for s in ammeter_specs if s["name"] == spec_name)

    value = request_current_from_ammeter(spec["port"], spec["command"])

    # Then assert it's within configured expected range:
    assert spec["expected_min"] <= value <= spec["expected_max"], (
        f"{spec_name} value out of range: {value}. "
        f"Expected [{spec['expected_min']}, {spec['expected_max']}]."
    )

@pytest.mark.parametrize("spec_name", ["greenlee", "entes", "circutor"])
def test_request_current_from_ammeter_invalid_command(spec_name, ammeter_specs):
    spec = next(s for s in ammeter_specs if s["name"] == spec_name)

    invalid_command = b"INVALID_COMMAND_DOES_NOT_EXIST"

    value = request_current_from_ammeter(spec["port"], invalid_command)

    assert value in (-1.0, -2.0, -3.0), (
        f"{spec_name} should not return a valid measurement for invalid command. "
        f"Got: {value}"
    )
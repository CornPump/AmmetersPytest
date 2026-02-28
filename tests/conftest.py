import socket
import time
import threading
from pathlib import Path

import pytest
import yaml

from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Circutor_Ammeter import CircutorAmmeter


# add cli arg with test run config
def pytest_addoption(parser):
    parser.addoption(
        "--config",
        action="store",
        default="config/config.yaml",
        help="Path to configuration YAML file",
    )

# reliable server is ready check
def wait_for_port(host: str, port: int, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.05)
    raise RuntimeError(f"Port {port} did not become ready in {timeout_s}s. Last error: {last_err}")


# loads and validate the config for the tests
@pytest.fixture(scope="session")
def config():
    cfg_path = Path("config.yml")
    if not cfg_path.exists():
        raise RuntimeError("config.yml not found in project root")

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    sampling = (((data.get("testing") or {}).get("sampling")) or {})
    min_val = data.get("sampling_frequency_min_val", 25)

    # Normalize null-like values
    measurements_count = int(sampling.get("measurements_count")) if sampling.get("measurements_count") is not None else None
    total_duration_ms = int(sampling.get("total_duration_ms")) if sampling.get("total_duration_ms") is not None else None
    sampling_frequency_ms = int(sampling.get("sampling_frequency_ms")) if sampling.get("sampling_frequency_ms") is not None else None
    min_val = int(min_val)

    if min_val <= 0:
        raise RuntimeError("sampling_frequency_min_val must be > 0")

    # ----- Policy Rules -----

    # Case 1: measurements_count + total_duration_ms
    if measurements_count is not None and total_duration_ms is not None:
        if measurements_count <= 0:
            raise RuntimeError("measurements_count must be > 0")
        if total_duration_ms <= 0:
            raise RuntimeError("total_duration_ms must be > 0")

        derived_sampling_frequency_ms = total_duration_ms / measurements_count

        if derived_sampling_frequency_ms < min_val:
            raise RuntimeError(
                f"Derived sampling_frequency_ms ({derived_sampling_frequency_ms:.2f}) "
                f"is lower than sampling_frequency_min_val ({min_val})"
            )

        sampling_frequency_ms = int(round(derived_sampling_frequency_ms))

    # Case 2: total_duration_ms + sampling_frequency_ms
    if total_duration_ms is not None and sampling_frequency_ms is not None:
        if total_duration_ms <= sampling_frequency_ms:
            raise RuntimeError(
                "total_duration_ms must be greater than sampling_frequency_ms"
            )

        if sampling_frequency_ms < min_val:
            raise RuntimeError(
                "sampling_frequency_ms is lower than sampling_frequency_min_val"
            )

        implied_samples = total_duration_ms / sampling_frequency_ms
        if implied_samples < 1:
            raise RuntimeError("Configuration implies less than 1 sample")

    # Case 3: sampling_frequency_ms only
    if sampling_frequency_ms is not None:
        if sampling_frequency_ms < min_val:
            raise RuntimeError(
                "sampling_frequency_ms is lower than sampling_frequency_min_val"
            )

    # Case 5: everything null
    if measurements_count is None and total_duration_ms is None and sampling_frequency_ms is None:
        raise RuntimeError(
            "Invalid sampling config: all values are null"
        )

    # Save normalized values back
    data["testing"]["sampling"]["measurements_count"] = measurements_count
    data["testing"]["sampling"]["total_duration_ms"] = total_duration_ms
    data["testing"]["sampling"]["sampling_frequency_ms"] = sampling_frequency_ms
    data["sampling_frequency_min_val"] = min_val

    # Validate ammeters exist
    ammeters = data.get("ammeters") or {}
    if not ammeters:
        raise RuntimeError("config.yml: ammeters section is empty")

    return data


# Start the emulator servers (TCP servers) one time for the whole pytest run
@pytest.fixture(scope="session")
def start_emulators(config):
    am = config["ammeters"]

    # Create emulator instances using ports from config
    emulators = []
    if "greenlee" in am:
        emulators.append(GreenleeAmmeter(int(am["greenlee"]["port"])))
    if "entes" in am:
        emulators.append(EntesAmmeter(int(am["entes"]["port"])))
    if "circutor" in am:
        emulators.append(CircutorAmmeter(int(am["circutor"]["port"])))

    # run the ammeters
    threads = []
    for emu in emulators:
        t = threading.Thread(target=emu.start_server, daemon=True)  # daemon ok for pytest session
        t.start()
        threads.append(t)

    # Wait until ready
    for emu in emulators:
        wait_for_port("localhost", emu.port, timeout_s=8.0)

    return emulators

# builds the specs of all the ammeters that are to be run in this session
@pytest.fixture(scope="session")
def ammeter_specs(config, start_emulators):
    specs = []
    for name, v in (config["ammeters"] or {}).items():
        r = v.get("expected_range") or {}
        specs.append({
            "name": name,
            "port": int(v["port"]),
            "command": v["command"].encode("utf-8"),
            "expected_min": float(r["min"]),
            "expected_max": float(r["max"]),
        })
    return specs

# Expose sampling configuration in a clean dict for test
@pytest.fixture(scope="session")
def sampling_cfg(config):
    s = config["testing"]["sampling"]
    return {
        "measurements_count": s.get("measurements_count"),
        "total_duration_seconds": s.get("total_duration_seconds"),
        "sampling_frequency_hz": float(s["sampling_frequency_hz"]),
    }

# create results dir for the test
@pytest.fixture(scope="session")
def results_dir():
    base = Path("results")
    base.mkdir(exist_ok=True)
    run_dir = base / time.strftime("%Y-%m-%dT%H-%M-%S")
    run_dir.mkdir()
    return run_dir
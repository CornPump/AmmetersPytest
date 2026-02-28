import socket
import time
import threading
import csv
import logging
import pytest
import yaml
from pathlib import Path

from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Circutor_Ammeter import CircutorAmmeter

_RUN_LOG_PATH = None
_TEST_RESULTS = []

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
def config(request):
    cfg_path = Path(request.config.getoption("--config"))
    if not cfg_path.exists():
        raise RuntimeError(f"Config file not found: {cfg_path}")

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data["_config_path"] = str(cfg_path)  # for logging

    sampling = (((data.get("testing") or {}).get("sampling")) or {})

    # sampling_frequency_min_val is inside sampling in your YAML
    min_val = sampling.get("sampling_frequency_min_val", 25)

    # Normalize null-like values
    measurements_count = int(sampling.get("measurements_count")) if sampling.get("measurements_count") is not None else None
    total_duration_ms = int(sampling.get("total_duration_ms")) if sampling.get("total_duration_ms") is not None else None
    sampling_frequency_ms = int(sampling.get("sampling_frequency_ms")) if sampling.get("sampling_frequency_ms") is not None else None
    min_val = int(min_val)

    if min_val <= 0:
        raise RuntimeError("sampling_frequency_min_val must be > 0")

    # ----- Policy Rules -----

    # Case 1: measurements_count + total_duration_ms => derive sampling_frequency_ms
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
            raise RuntimeError("total_duration_ms must be greater than sampling_frequency_ms")

        if sampling_frequency_ms < min_val:
            raise RuntimeError("sampling_frequency_ms is lower than sampling_frequency_min_val")

        implied_samples = total_duration_ms / sampling_frequency_ms
        if implied_samples < 1:
            raise RuntimeError("Configuration implies less than 1 sample")

    # Case 3: sampling_frequency_ms exists => min check
    if sampling_frequency_ms is not None and sampling_frequency_ms < min_val:
        raise RuntimeError("sampling_frequency_ms is lower than sampling_frequency_min_val")

    # Everything null => invalid
    if measurements_count is None and total_duration_ms is None and sampling_frequency_ms is None:
        raise RuntimeError("Invalid sampling config: all values are null")

    # Save normalized values back
    data.setdefault("testing", {}).setdefault("sampling", {})
    data["testing"]["sampling"]["measurements_count"] = measurements_count
    data["testing"]["sampling"]["total_duration_ms"] = total_duration_ms
    data["testing"]["sampling"]["sampling_frequency_ms"] = sampling_frequency_ms
    data["testing"]["sampling"]["sampling_frequency_min_val"] = min_val

    # Validate ammeters exist
    ammeters = data.get("ammeters") or {}
    if not ammeters:
        raise RuntimeError("config: ammeters section is empty")

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
        "total_duration_ms": s.get("total_duration_ms"),
        "sampling_frequency_ms": s.get("sampling_frequency_ms"),
        "sampling_frequency_min_val": s.get("sampling_frequency_min_val"),
    }


# create results dir for the test
@pytest.fixture(scope="session")
def results_dir():
    base = Path("results")
    base.mkdir(exist_ok=True)
    run_dir = base / time.strftime("%Y-%m-%dT%H-%M-%S")
    run_dir.mkdir()
    return run_dir


# --- NEW: effective sampling plan helper (ms-based) ---
def _build_sampling_plan_ms(sampling_cfg: dict) -> dict:
    """
    Returns effective plan:
      - measurements_count (int)
      - sampling_frequency_ms (int)
      - period_s (float)
    """
    mc = sampling_cfg.get("measurements_count")
    td = sampling_cfg.get("total_duration_ms")
    sf = sampling_cfg.get("sampling_frequency_ms")
    min_val = sampling_cfg.get("sampling_frequency_min_val", 25)

    mc = int(mc) if mc is not None else None
    td = int(td) if td is not None else None
    sf = int(sf) if sf is not None else None
    min_val = int(min_val)

    # If mc and td exist => derive sf (already derived/validated in config(), but keep safe)
    if mc is not None and td is not None:
        derived = td / mc
        sf = int(round(derived))

    # If mc is missing but td+sf exist => compute mc
    if mc is None and td is not None and sf is not None:
        mc = max(1, td // sf)

    # If still missing mc => default batch size
    if mc is None:
        mc = 20

    if sf is None:
        raise RuntimeError("sampling_frequency_ms must be set (directly or derived)")

    if sf < min_val:
        raise RuntimeError(
            f"sampling_frequency_ms ({sf}) is lower than sampling_frequency_min_val ({min_val})"
        )

    return {"measurements_count": int(mc), "sampling_frequency_ms": int(sf), "period_s": sf / 1000.0}


# settup a logger
def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("ammeter_tests")
    logger.setLevel(logging.INFO)

    # avoid duplicate handlers if pytest reloads modules
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# run context (out dir + log + csvs + effective config print)
@pytest.fixture(scope="session")
def run_context(config, ammeter_specs, sampling_cfg):

    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path("tests") / "out" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    logger = _setup_logger(out_dir / "run.log")
    plan = _build_sampling_plan_ms(sampling_cfg)

    global _RUN_LOG_PATH
    _RUN_LOG_PATH = out_dir / "run.log"

    # Pre-create CSVs with headers
    csv_paths = {}
    for spec in ammeter_specs:
        p = out_dir / f"{spec['name']}.csv"
        csv_paths[spec["name"]] = p
        if not p.exists():
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "t_epoch_s",
                        "spec_name",
                        "port",
                        "command",
                        "value",
                        "status",
                        "expected_min",
                        "expected_max",
                    ]
                )

    # Print/log effective configuration
    logger.info("==== Test Run Configuration ====")
    logger.info(f"Config path: {config.get('_config_path')}")
    logger.info(f"Output dir: {out_dir}")
    logger.info(f"Sampling (raw): {sampling_cfg}")
    logger.info(f"Sampling (effective): {plan}")
    logger.info("Ammeters:")
    for spec in ammeter_specs:
        logger.info(
            f"  - {spec['name']}: port={spec['port']}, command={spec['command']!r}, "
            f"range=[{spec['expected_min']}, {spec['expected_max']}]"
        )
    logger.info("================================")

    run_start_epoch = time.time()

    return {"out_dir": out_dir, "logger": logger, "plan": plan, "csv_paths": csv_paths}

# hook for appending fail/succes for each to ram
def pytest_runtest_logreport(report):
    if report.when == "call":
        _TEST_RESULTS.append((report.nodeid, report.outcome))

# hook for appending success/fail of test to start of log file
def pytest_sessionfinish(session, exitstatus):
    global _RUN_LOG_PATH

    if not _RUN_LOG_PATH or not _RUN_LOG_PATH.exists():
        return

    original = _RUN_LOG_PATH.read_text(encoding="utf-8")

    lines = []
    lines.append("==== TEST RESULTS SUMMARY ====\n")
    for nodeid, outcome in _TEST_RESULTS:
        lines.append(f"{nodeid} -> {outcome.upper()}\n")
    lines.append(f"\nExit status: {exitstatus}\n")
    lines.append("==== END TEST RESULTS SUMMARY ====\n\n")

    _RUN_LOG_PATH.write_text("".join(lines) + original, encoding="utf-8")


def pytest_generate_tests(metafunc):
    if "spec_name" in metafunc.fixturenames:
        cfg_path = Path(metafunc.config.getoption("--config"))
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        ammeters = list((cfg.get("ammeters") or {}).keys())
        metafunc.parametrize("spec_name", ammeters)
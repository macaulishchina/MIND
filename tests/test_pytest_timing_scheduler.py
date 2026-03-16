from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_conftest_module() -> ModuleType:
    module_path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("test_pytest_conftest_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


test_conftest = _load_conftest_module()


def test_load_weighted_file_durations_aggregates_by_file(tmp_path: Path) -> None:
    timing_path = tmp_path / "timing.json"
    timing_path.write_text(
        json.dumps(
            {
                "test_cases": [
                    {
                        "nodeid": "tests/test_a.py::test_one",
                        "duration_seconds": 1.5,
                    },
                    {
                        "nodeid": "tests/test_a.py::test_two",
                        "duration_seconds": 2.0,
                    },
                    {
                        "nodeid": "tests/test_b.py::test_one",
                        "duration_seconds": 0.5,
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert test_conftest._load_weighted_file_durations(timing_path) == {
        "tests/test_a.py": (3.5, 2),
        "tests/test_b.py": (0.5, 1),
    }


def test_weighted_scheduler_prioritizes_heavier_historical_files() -> None:
    scheduler = object.__new__(test_conftest._WeightedLoadFileScheduling)
    scheduler._file_weights = {
        "tests/test_heavy.py": (9.5, 3),
        "tests/test_light.py": (2.0, 2),
    }

    heavy_key = scheduler._weighted_scope_key(
        "tests/test_heavy.py",
        {"tests/test_heavy.py::test_case": False},
    )
    light_key = scheduler._weighted_scope_key(
        "tests/test_light.py",
        {"tests/test_light.py::test_case": False},
    )
    unmatched_key = scheduler._weighted_scope_key(
        "tests/test_unknown.py",
        {
            "tests/test_unknown.py::test_case_one": False,
            "tests/test_unknown.py::test_case_two": False,
        },
    )

    assert heavy_key < light_key
    assert light_key < unmatched_key

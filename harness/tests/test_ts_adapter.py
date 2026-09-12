# harness/tests/test_ts_adapter.py
import json
from pathlib import Path

from harness.ts_adapter import TypeScriptAdapter

JEST_FIXTURE = {
    "testResults": [
        {
            "name": "/repo/src/date.test.ts",
            "assertionResults": [
                {"ancestorTitles": ["formatDate"], "title": "handles UTC offset", "status": "passed"},
                {"ancestorTitles": ["formatDate"], "title": "handles negative offset", "status": "failed"},
            ],
        }
    ]
}

VITEST_FIXTURE = {
    "testResults": [
        {
            "name": "/repo/src/date.test.ts",
            "assertionResults": [
                {"ancestorTitles": ["formatDate"], "title": "handles UTC offset", "status": "passed"},
                {"ancestorTitles": ["formatDate"], "title": "handles negative offset", "status": "failed"},
            ],
        }
    ]
}

MOCHA_FIXTURE = {
    "stats": {"tests": 2, "passes": 1, "failures": 1},
    "passes": [
        {"fullTitle": "formatDate handles UTC offset", "file": "/repo/src/date.test.ts"},
    ],
    "failures": [
        {"fullTitle": "formatDate handles negative offset", "file": "/repo/src/date.test.ts"},
    ],
}


def test_parse_jest():
    adapter = TypeScriptAdapter(repo_path=Path("/repo"))
    result = adapter.parse_results(json.dumps(JEST_FIXTURE), runner="jest")
    assert result == {
        "src/date.test.ts::formatDate > handles UTC offset": True,
        "src/date.test.ts::formatDate > handles negative offset": False,
    }


def test_parse_vitest():
    adapter = TypeScriptAdapter(repo_path=Path("/repo"))
    result = adapter.parse_results(json.dumps(VITEST_FIXTURE), runner="vitest")
    assert result == {
        "src/date.test.ts::formatDate > handles UTC offset": True,
        "src/date.test.ts::formatDate > handles negative offset": False,
    }


def test_parse_mocha():
    adapter = TypeScriptAdapter(repo_path=Path("/repo"))
    result = adapter.parse_results(json.dumps(MOCHA_FIXTURE), runner="mocha")
    assert result == {
        "src/date.test.ts::formatDate handles UTC offset": True,
        "src/date.test.ts::formatDate handles negative offset": False,
    }


def test_parse_package_manager_ignores_unrecognized_field(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "nub@0.8.3"}))
    (tmp_path / "pnpm-lock.yaml").write_text("")
    adapter = TypeScriptAdapter(repo_path=tmp_path)
    manager, _ = adapter._detect_package_manager(tmp_path)
    assert manager == "pnpm"

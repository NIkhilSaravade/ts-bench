import json

from harness.python_adapter import PythonAdapter


def test_parse_results_maps_pytest_nodeids_directly():
    adapter = PythonAdapter(repo_path=None)
    raw = json.dumps(
        {
            "tests": [
                {"nodeid": "tests/test_foo.py::test_pass", "outcome": "passed"},
                {"nodeid": "tests/test_foo.py::test_fail", "outcome": "failed"},
            ]
        }
    )
    assert adapter.parse_results(raw) == {
        "tests/test_foo.py::test_pass": True,
        "tests/test_foo.py::test_fail": False,
    }


def test_detect_package_manager_prefers_lockfiles_over_bare_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    adapter = PythonAdapter(repo_path=tmp_path)
    assert adapter._detect_package_manager(tmp_path) == "pip"

    (tmp_path / "uv.lock").write_text("")
    assert adapter._detect_package_manager(tmp_path) == "uv"


def test_detect_test_extra_finds_pep621_test_group(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project.optional-dependencies]\ntest = ['pytest', 'pytz']\n")
    adapter = PythonAdapter(repo_path=tmp_path)
    assert adapter._detect_test_extra() == "test"


def test_detect_test_extra_returns_none_without_a_matching_group(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project.optional-dependencies]\ndocs = ['sphinx']\n")
    adapter = PythonAdapter(repo_path=tmp_path)
    assert adapter._detect_test_extra() is None

from pathlib import Path


def _requirement_names(path: str) -> set[str]:
    names: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.split("==", 1)[0].split("[", 1)[0].lower())
    return names


def test_runtime_requirements_do_not_include_test_tools() -> None:
    runtime = _requirement_names("requirements.txt")

    assert "pytest" not in runtime
    assert "httpx" not in runtime


def test_development_requirements_include_test_tools() -> None:
    dev = _requirement_names("requirements-dev.txt")

    assert "pytest" in dev
    assert "httpx" in dev

"""Static audit rules from the master spec (violations fail the suite).

§27: no boto3 outside app/infra/s3.py; no shell=True / os.system / string
shell commands; no create_all in production code (tests only).
"""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
PY_FILES = sorted(APP_DIR.rglob("*.py"))


def _sources() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in PY_FILES]


def test_boto3_only_in_infra_s3() -> None:
    offenders = [
        str(p) for p, src in _sources() if "boto3" in src and p.name != "s3.py"
    ]
    assert offenders == [], f"boto3 imported outside infra/s3.py: {offenders}"


def test_no_shell_true_or_os_system() -> None:
    offenders = [
        f"{p}: {'shell=True' if 'shell=True' in src else 'os.system'}"
        for p, src in _sources()
        if "shell=True" in src or "os.system" in src
    ]
    assert offenders == [], f"shell execution found: {offenders}"


def test_no_subprocess_shell_with_string() -> None:
    offenders = []
    for p, src in _sources():
        if "subprocess." in src and 'shell=True' in src:
            offenders.append(str(p))
    assert offenders == []


def test_no_create_all_in_app_code() -> None:
    offenders = [str(p) for p, src in _sources() if ".create_all(" in src]
    assert offenders == [], f"create_all in production code: {offenders}"


def test_no_hardcoded_secrets_keywords() -> None:
    # naive guard: a secret-looking literal assignment in app code
    forbidden = ["AKIA", "AIza", "sk-", "ghp_", "xoxb-"]
    offenders = [
        f"{p}:{token}" for p, src in _sources() for token in forbidden if token in src
    ]
    assert offenders == [], f"hardcoded secret-looking literals: {offenders}"

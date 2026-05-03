from __future__ import annotations

from pathlib import Path


def test_existing_converter_cli_script_contract_is_preserved() -> None:
    run_script = Path("run.sh")
    assert run_script.exists()

    content = run_script.read_text(encoding="utf-8")
    assert "docker build -t pymupdf-extract ." in content
    assert "docker run --rm -p 8001:8001" in content

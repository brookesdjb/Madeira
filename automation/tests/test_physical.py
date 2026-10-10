"""Explicit opt-in only. Never contacts a device during ordinary host pytest."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.getenv("MADEIRA_RUN_PHYSICAL") != "1", reason="requires provisioned Mac, connected iPad and Appium")
def test_physical_ui_smoke():
    result = subprocess.run([sys.executable, "-m", "automation.controller.cli", "smoke"],
                            cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(os.getenv("MADEIRA_RUN_JIT_PHYSICAL") != "1", reason="requires opted-in test build and provisioned physical JIT workflow")
def test_physical_jit_coexistence():
    result = subprocess.run([sys.executable, "-m", "automation.controller.cli", "jit-test"],
                            cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert result.returncode == 0, result.stdout

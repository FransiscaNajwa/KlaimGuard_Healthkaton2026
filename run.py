import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "xgboost": "xgboost",
    "scikit-learn": "sklearn",
    "numpy": "numpy",
    "pandas": "pandas",
    "joblib": "joblib",
    "chromadb": "chromadb",
    "sentence-transformers": "sentence_transformers",
    "pypdf": "pypdf",
    "pdfplumber": "pdfplumber",
    "PyPDF2": "PyPDF2",
    "python-multipart": "multipart",
}


def check_dependencies() -> None:
    missing = [
        distribution
        for distribution, module in REQUIRED_MODULES.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        package_list = ", ".join(missing)
        raise RuntimeError(
            f"Missing Python dependencies: {package_list}. "
            "Install them with: python -m pip install -r requirements.txt"
        )
    print("All required Python packages are importable.", flush=True)


def _format_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_step(step_name: str, command: Sequence[str]) -> None:
    print(f"\n[{step_name}]", flush=True)
    print(f"$ {_format_command(command)}", flush=True)
    process = subprocess.Popen(
        list(command),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="", flush=True)
        return_code = process.wait()
    except KeyboardInterrupt:
        _stop_process(process)
        print(f"\n[{step_name}] Interrupted; child process stopped.", flush=True)
        raise

    if return_code != 0:
        raise RuntimeError(f"Step '{step_name}' failed with exit code {return_code}.")
    print(f"\033[92m[COMPLETE] {step_name}\033[0m", flush=True)


def main() -> int:
    try:
        check_dependencies()
        steps = [
            (
                "Initialize SQLite WAL database and seed 5,500 claims",
                [sys.executable, "-m", "backend.scripts.init_db"],
            ),
            (
                "Train XGBoost risk model",
                [sys.executable, "-m", "backend.scripts.train_xgboost"],
            ),
            (
                "Ingest official regulations into ChromaDB",
                [sys.executable, "-m", "backend.scripts.ingest_regulations"],
            ),
            (
                "Verify audit hash-chain integrity",
                [sys.executable, "-m", "backend.scripts.verify_audit_integrity"],
            ),
            (
                "Start KlaimGuard AI API and dashboard",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8000",
                    "--reload",
                ],
            ),
        ]
        for step_name, command in steps:
            run_step(step_name, command)
        return 0
    except KeyboardInterrupt:
        print("\nKlaimGuard AI stopped by user.", flush=True)
        return 130
    except RuntimeError as exc:
        print(f"\033[91m[FAILED] {exc}\033[0m", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
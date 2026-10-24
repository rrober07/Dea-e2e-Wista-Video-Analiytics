from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "lambda"
OUTPUT.mkdir(parents=True, exist_ok=True)


def create_zip(destination, source_directory):
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source_directory.rglob("*")):
            if path.is_file():
                if "__pycache__" in path.parts:
                    continue
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                archive.write(
                    path,
                    path.relative_to(source_directory).as_posix(),
                )

    print(f"Created: {destination} ({destination.stat().st_size:,} bytes)")


def build_ingestion():
    with TemporaryDirectory() as temporary:
        package = Path(temporary)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--platform",
                "manylinux2014_x86_64",
                "--python-version",
                "3.12",
                "--implementation",
                "cp",
                "--only-binary=:all:",
                "--no-compile",
                "--target",
                str(package),
                "--requirement",
                str(ROOT / "lambda" / "requirements-ingestion.txt"),
            ],
            check=True,
        )

        source = ROOT / "python" / "ingest_wistia_events.py"
        (package / source.name).write_bytes(source.read_bytes())

        create_zip(
            OUTPUT / "wistia-events-ingestion.zip",
            package,
        )


def build_scheduler():
    with TemporaryDirectory() as temporary:
        package = Path(temporary)

        for name in (
            "start_wistia_pipeline.py",
            "wistia_schedule_dates.py",
        ):
            source = ROOT / "lambda" / name
            (package / name).write_bytes(source.read_bytes())

        create_zip(
            OUTPUT / "wistia-pipeline-scheduler.zip",
            package,
        )


if __name__ == "__main__":
    build_ingestion()
    build_scheduler()

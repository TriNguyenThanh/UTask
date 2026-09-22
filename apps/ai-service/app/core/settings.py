import os
from pathlib import Path

WORK_SERVICE_URL = os.getenv("WORK_SERVICE_URL")
INTEGRATION_SERVICE_URL = os.getenv("INTEGRATION_SERVICE_URL")


def _default_datasets_dir() -> Path:
    """Find the repository dataset locally and use the container mount otherwise."""
    source_path = Path(__file__).resolve()
    for parent in source_path.parents:
        candidate = parent / "datasets"
        if candidate.is_dir():
            return candidate
    return Path("/app/datasets")


DATASETS_DIR = Path(os.getenv("DATASETS_DIR", _default_datasets_dir()))

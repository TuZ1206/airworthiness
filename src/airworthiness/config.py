"""Repository location, without a dependency on working directory or secrets."""
import os
from pathlib import Path


def project_root():
    override = os.environ.get("AIRWORTHINESS_ROOT")
    root = Path(override).expanduser().resolve() if override else Path(__file__).resolve().parents[2]
    if not (root / "data/chapters/catalog.json").is_file():
        raise RuntimeError("未找到九章资料。请从仓库执行 pip install -e .，或设置 AIRWORTHINESS_ROOT。")
    return root

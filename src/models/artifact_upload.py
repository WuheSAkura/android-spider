from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ArtifactUploadRecord:
    local_path: Path
    relative_path: str
    object_path: str
    public_url: str
    content_type: str
    file_size: int = 0

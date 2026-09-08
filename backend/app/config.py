import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    abs_url: str = "http://localhost:13378"
    abs_token: str = ""
    media_root: str = "/media"
    # Optional extra volume mappings: ABS_HOST_PATH=CONTAINER_PATH pairs, comma-separated.
    # Example: VOLUME_MAP=/abs/lib1=/media,/abs/lib2=/media2
    volume_map: str = ""
    default_template: str = "{author_lf}/{series}/{series_index_tag} - {title}"
    log_level: str = "INFO"
    debug: bool = False
    app_password: str = ""
    db_path: str = "/data/shelf-renamer.db"
    app_version: str = "dev"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("volume_map")
    @classmethod
    def validate_volume_map(cls, value: str) -> str:
        seen = set()
        for entry in value.split(",") if value.strip() else []:
            pair = entry.strip().split("=")
            if len(pair) != 2 or not all(os.path.isabs(p.strip()) for p in pair):
                raise ValueError(
                    "VOLUME_MAP must contain absolute ABS_ROOT=CONTAINER_ROOT pairs"
                )
            if pair[0].strip().rstrip("/") in seen:
                raise ValueError("VOLUME_MAP contains duplicate ABS roots")
            seen.add(pair[0].strip().rstrip("/"))
        return value

    def parsed_volume_map(self) -> list[tuple[str, str]]:
        """Parse VOLUME_MAP into (abs_root, container_root) pairs."""
        if not self.volume_map.strip():
            return []
        result = []
        for entry in self.volume_map.split(","):
            entry = entry.strip()
            if "=" not in entry:
                continue
            abs_root, _, container_root = entry.partition("=")
            abs_root = os.path.normpath(abs_root.strip())
            container_root = os.path.normpath(container_root.strip())
            if abs_root and container_root:
                result.append((abs_root, container_root))
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()

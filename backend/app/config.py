from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    abs_url: str = "http://localhost:13378"
    abs_token: str = ""
    media_root: str = "/media"
    default_template: str = "{author} - {title} ({year})"
    log_level: str = "INFO"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

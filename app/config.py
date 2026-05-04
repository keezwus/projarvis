from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _default_availability() -> dict[str, list[list[str]]]:
    return {
        "monday":    [["09:00", "12:00"], ["14:00", "18:00"]],
        "tuesday":   [["09:00", "12:00"], ["14:00", "18:00"]],
        "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
        "thursday":  [["09:00", "12:00"], ["14:00", "18:00"]],
        "friday":    [["09:00", "12:00"], ["14:00", "17:00"]],
        "saturday":  [],
        "sunday":    [],
    }


class HorizonConfig(BaseModel):
    weeks: int = 4


class CalDAVConfig(BaseModel):
    url: str = "http://baikal:80/dav.php/calendars/user/default/"
    username: str = "user"
    password: str = "changeme"
    calendar_name: str = "projarvis"


class EngineConfig(BaseModel):
    max_time_seconds: float = 30.0
    random_seed: int = 42


class _TomlSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        path = Path("config/app_config.toml")
        if not path.exists():
            return {}
        with path.open("rb") as f:
            return tomllib.load(f)


class AppConfig(BaseSettings):
    horizon: HorizonConfig = Field(default_factory=HorizonConfig)
    availability: dict[str, list[list[str]]] = Field(default_factory=_default_availability)
    caldav: CalDAVConfig = Field(default_factory=CalDAVConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    state_dir: str = "config/state/"

    model_config = SettingsConfigDict(
        env_prefix="PROJARVIS_",
        env_nested_delimiter="__",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            _TomlSource(settings_cls),
        )


def load_app_config(toml_path: str = "config/app_config.toml") -> AppConfig:
    """Load AppConfig from a TOML file, with env var overrides."""
    return AppConfig()

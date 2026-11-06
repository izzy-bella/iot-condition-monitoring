"""Runtime environment and project configuration loading."""

from pathlib import Path
import os
from typing import Any, Dict, Mapping, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RASPBERRY_PI_ENV_FILE = Path("/home/isabella/.env")


def load_runtime_environment(
    env_file: Path = RASPBERRY_PI_ENV_FILE,
) -> None:
    """Load Raspberry Pi secrets without replacing explicitly exported values."""

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is required to load /home/isabella/.env"
        ) from exc

    if not env_file.is_file():
        raise FileNotFoundError(
            "Runtime environment file not found: {}".format(env_file)
        )

    if not load_dotenv(dotenv_path=env_file, override=False):
        raise RuntimeError(
            "Runtime environment file could not be loaded: {}".format(env_file)
        )


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load project configuration"
        ) from exc

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping: {}".format(path))
    return data


def config_path(
    environment: Mapping[str, str],
    variable: str,
    default_name: str,
) -> Path:
    configured = environment.get(variable)
    return Path(configured) if configured else PROJECT_ROOT / "config" / default_name


def load_project_configuration(
    environment: Optional[Mapping[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    env = environment if environment is not None else os.environ
    return {
        "sensors": load_yaml(config_path(env, "SENSORS_CONFIG", "sensors.yaml")),
        "thresholds": load_yaml(
            config_path(env, "THRESHOLDS_CONFIG", "thresholds.yaml")
        ),
        "fmeca": load_yaml(config_path(env, "FMECA_CONFIG", "fmeca.yaml")),
    }

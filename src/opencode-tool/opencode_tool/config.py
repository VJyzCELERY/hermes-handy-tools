"""Configuration management for OpenCode Python CLI."""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".config" / "opencode-tool-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "opencode_server_url": "http://localhost:4905",
    "monitor_retry_timeout": 60,
    "default_model": "mimo-v2.5",
    "default_variant": "high"
}


def ensure_config_dir():
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            # Merge with defaults for missing keys
            merged = DEFAULT_CONFIG.copy()
            merged.update(config)
            return merged
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_server_url() -> str:
    """Get the configured server URL."""
    # Environment variable takes precedence
    env_url = os.environ.get("OPENCODE_SERVER_URL")
    if env_url:
        return env_url
    
    config = load_config()
    return config.get("opencode_server_url", DEFAULT_CONFIG["opencode_server_url"])


def set_config(key: str, value: str):
    """Set a configuration value."""
    config = load_config()
    config[key] = value
    save_config(config)


def get_config_value(key: str) -> Optional[str]:
    """Get a specific configuration value."""
    config = load_config()
    return config.get(key)

"""
Settings and Environment Configuration for Chaos Zero Nightmare Bot.
Reads .env and ai_config.json directly without homemade/broken obfuscation.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from czn_bot.constants import PROJECT_ROOT

logger = logging.getLogger("ChaosBot.Settings")

ENV_FILE_PATH = os.path.join(PROJECT_ROOT, ".env")
AI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "ai_config.json")


def load_env_file(filepath: str = ENV_FILE_PATH) -> Dict[str, str]:
    """
    Load key-value pairs from a .env file into os.environ (if not already set).
    Pure python implementation to avoid extra dependencies.
    """
    env_vars: Dict[str, str] = {}
    if not os.path.isfile(filepath):
        return env_vars

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    env_vars[key] = val
                    if key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        logger.warning(f"Could not load .env file from {filepath}: {e}")

    return env_vars


# Load .env at module import
load_env_file()

# ── ADB Settings ──────────────────────────────────────────────
ADB_HOST = os.getenv("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.getenv("ADB_PORT", "5555"))
ADB_PATH = os.getenv("ADB_PATH", "")

# ── Notification Settings ─────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ENABLE_WINDOWS_TOAST = os.getenv("ENABLE_WINDOWS_TOAST", "true").lower() in ("1", "true", "yes")

# ── AI Configuration Defaults ─────────────────────────────────
DEFAULT_AI_CONFIG: Dict[str, Any] = {
    "provider": "gemini",
    "model_name": "gemini-2.5-flash",
    "enable_multimodal_fallback": True,
    "temperature": 0.1,
    "max_tokens": 512,
}


def load_ai_config(filepath: str = AI_CONFIG_PATH) -> Dict[str, Any]:
    """Load AI configuration from JSON file."""
    config = dict(DEFAULT_AI_CONFIG)
    if os.path.isfile(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.warning(f"Error loading AI config from {filepath}: {e}")
    return config


def save_ai_config(config: Dict[str, Any], filepath: str = AI_CONFIG_PATH) -> bool:
    """Save AI configuration to JSON file (plain text, no homemade encryption)."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving AI config to {filepath}: {e}")
        return False


def get_gemini_api_key() -> str:
    """
    Get Gemini API Key.
    Priority:
    1. os.environ['GEMINI_API_KEY'] (from .env or system environment)
    2. ai_config.json 'api_key'
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key

    cfg = load_ai_config()
    key = cfg.get("api_key", "").strip()
    if key:
        return key

    return ""


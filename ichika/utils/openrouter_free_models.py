import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
from nonebot import logger

from ichika.utils.fileio import read_json, write_json

_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CATALOG_FILE = Path(__file__).parent.parent / "resources" / "openrouter_free_models.json"
_REFRESH_INTERVAL = 24 * 60 * 60
_REFRESH_RETRY_INTERVAL = 5 * 60
_MAX_MODELS_PER_REQUEST = 8

_lock = asyncio.Lock()
_loaded = False
_models: list[str] = []
_updated_at = 0.0
_last_refresh_attempt = 0.0
_last_success: str | None = None
_cooldowns: dict[str, float] = {}


def _is_free_chat_model(model: dict[str, Any]) -> bool:
    model_id = model.get("id")
    architecture = model.get("architecture") or {}
    pricing = model.get("pricing") or {}
    endpoints = model.get("endpoints") or []

    try:
        is_free = float(pricing.get("prompt", -1)) == 0 and float(
            pricing.get("completion", -1)
        ) == 0
    except (TypeError, ValueError):
        return False

    return bool(
        isinstance(model_id, str)
        and model_id.endswith(":free")
        and "text" in architecture.get("input_modalities", [])
        and "text" in architecture.get("output_modalities", [])
        and "/api/v1/chat/completions" in endpoints
        and is_free
    )


async def _load_catalog() -> None:
    global _loaded, _models, _updated_at, _last_success
    if _loaded:
        return

    data = await read_json(_CATALOG_FILE) or {}
    if isinstance(data, dict):
        models = data.get("models", [])
        if isinstance(models, list):
            _models = [model for model in models if isinstance(model, str)]
        _updated_at = float(data.get("updated_at", 0) or 0)
        last_success = data.get("last_success")
        _last_success = last_success if isinstance(last_success, str) else None
    _loaded = True


async def refresh_openrouter_free_models(force: bool = False) -> bool:
    global _last_refresh_attempt, _models, _updated_at

    async with _lock:
        await _load_catalog()
        now = time.time()
        if not force and now - _last_refresh_attempt < _REFRESH_RETRY_INTERVAL:
            return False
        if not force and now - _updated_at < _REFRESH_INTERVAL:
            return False
        _last_refresh_attempt = now

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(_MODELS_URL)
                response.raise_for_status()
                catalog = response.json().get("data", [])
            models = [model["id"] for model in catalog if _is_free_chat_model(model)]
            models = list(dict.fromkeys(models))
            if not models:
                logger.warning("openrouter: model catalog returned no free chat models")
                return False

            _models = models
            _updated_at = now
            await write_json(
                _CATALOG_FILE,
                {
                    "updated_at": _updated_at,
                    "last_success": _last_success,
                    "models": _models,
                },
            )
            logger.info(f"openrouter: refreshed {len(_models)} free chat models")
            return True
        except Exception as exc:
            logger.warning(f"openrouter: failed to refresh free model catalog: {exc}")
            return False


async def get_openrouter_free_models(preferred: str | None = None) -> list[str]:
    await refresh_openrouter_free_models()

    async with _lock:
        await _load_catalog()
        now = time.time()
        available = [
            model for model in _models if _cooldowns.get(model, 0) <= now
        ]
        ordered = [_last_success, preferred, *available]
        candidates = list(dict.fromkeys(
            model for model in ordered if model in available
        ))
        return candidates[:_MAX_MODELS_PER_REQUEST]


async def record_openrouter_model_result(
    model: str, *, success: bool, status_code: int | None = None
) -> None:
    global _last_success

    async with _lock:
        await _load_catalog()
        if success:
            _last_success = model
            _cooldowns.pop(model, None)
            await write_json(
                _CATALOG_FILE,
                {
                    "updated_at": _updated_at,
                    "last_success": _last_success,
                    "models": _models,
                },
            )
            return

        cooldown = 300 if status_code == 429 else 3600
        if status_code == 404:
            cooldown = 24 * 60 * 60
        _cooldowns[model] = time.time() + cooldown
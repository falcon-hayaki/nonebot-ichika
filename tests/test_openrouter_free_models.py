import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from ichika.utils import llm_translator, openrouter_free_models
from ichika.utils.fileio import read_json


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.is_success = status_code < 400
        self.text = str(body)
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self):
        self.models = []
        self.responses = [
            FakeResponse(429, {"error": {"message": "upstream busy"}}),
            FakeResponse(
                200,
                {"choices": [{"message": {"content": "已翻译"}}]},
            ),
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json, headers):
        self.models.append(json["model"])
        return self.responses.pop(0)


class FakeCatalogClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        return FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "cohere/north-mini-code:free",
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["text"],
                        },
                        "pricing": {"prompt": "0", "completion": "0"},
                        "endpoints": ["/api/v1/chat/completions"],
                    },
                    {
                        "id": "cohere/north-mini-code",
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["text"],
                        },
                        "pricing": {"prompt": "0.000001", "completion": "0"},
                        "endpoints": ["/api/v1/chat/completions"],
                    },
                ]
            },
        )

class OpenRouterFreeModelTests(unittest.IsolatedAsyncioTestCase):
    def test_catalog_filter_keeps_free_text_chat_models(self):
        model = {
            "id": "cohere/north-mini-code:free",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0", "completion": "0"},
            "endpoints": ["/api/v1/chat/completions"],
        }

        self.assertTrue(openrouter_free_models._is_free_chat_model(model))
        model["pricing"]["completion"] = "0.000001"
        self.assertFalse(openrouter_free_models._is_free_chat_model(model))

    async def test_refresh_persists_filtered_catalog(self):
        with (
            TemporaryDirectory() as temp_dir,
            patch.object(
                openrouter_free_models,
                "_CATALOG_FILE",
                Path(temp_dir) / "free-models.json",
            ),
            patch.object(openrouter_free_models, "_loaded", False),
            patch.object(openrouter_free_models, "_models", []),
            patch.object(openrouter_free_models, "_updated_at", 0.0),
            patch.object(openrouter_free_models, "_last_refresh_attempt", 0.0),
            patch.object(openrouter_free_models, "_last_success", None),
            patch.object(openrouter_free_models, "_cooldowns", {}),
            patch.object(
                openrouter_free_models.httpx,
                "AsyncClient",
                return_value=FakeCatalogClient(),
            ),
        ):
            refreshed = await openrouter_free_models.refresh_openrouter_free_models(
                force=True
            )
            catalog = await read_json(openrouter_free_models._CATALOG_FILE)

        self.assertTrue(refreshed)
        self.assertEqual(catalog["models"], ["cohere/north-mini-code:free"])

    async def test_translation_moves_to_next_model_after_rate_limit(self):
        client = FakeClient()
        record_result = AsyncMock()
        config = {
            "twitter.llm_api_key": "test-key",
            "twitter.llm_api_url": "https://openrouter.ai/api/v1/chat/completions",
            "twitter.llm_model": "google/gemma-4-31b-it:free",
        }

        with (
            patch.object(llm_translator, "cfg_get", side_effect=config.get),
            patch.object(
                llm_translator,
                "get_openrouter_free_models",
                new=AsyncMock(
                    return_value=[
                        "google/gemma-4-31b-it:free",
                        "cohere/north-mini-code:free",
                    ]
                ),
            ),
            patch.object(
                llm_translator,
                "record_openrouter_model_result",
                new=record_result,
            ),
            patch.object(llm_translator.httpx, "AsyncClient", return_value=client),
        ):
            result = await llm_translator.translate_tweet_text("こんにちは、テストです")

        self.assertEqual(result, "已翻译")
        self.assertEqual(
            client.models,
            ["google/gemma-4-31b-it:free", "cohere/north-mini-code:free"],
        )
        self.assertEqual(record_result.await_count, 2)


if __name__ == "__main__":
    unittest.main()
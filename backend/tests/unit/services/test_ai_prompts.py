"""Prompt templates and their settings plumbing: placeholder substitution
must never crash a call, and overrides must revert cleanly."""

from unittest.mock import AsyncMock, MagicMock

from igab.services.ai_prompts import DEFAULT_PROMPTS, PROMPT_PLACEHOLDERS, render_prompt
from igab.services.settings_service import DEFAULTS, SettingsService


class TestRenderPrompt:
    def test_substitutes_known_placeholders(self):
        out = render_prompt("Hello {name}, today is {today}", {"name": "IGAB", "today": "x"})
        assert out == "Hello IGAB, today is x"

    def test_json_braces_survive(self):
        template = 'Return {"amount": 0.00} for {payee_name}'
        out = render_prompt(template, {"payee_name": "Costco"})
        assert out == 'Return {"amount": 0.00} for Costco'

    def test_unknown_placeholders_left_alone(self):
        out = render_prompt("Keep {mystery} intact for {payee_name}", {"payee_name": "A"})
        assert out == "Keep {mystery} intact for A"

    def test_default_templates_render_without_error(self):
        sample_values = {
            "categories": "- Groceries (Everyday)",
            "today": "2026-08-02",
            "text": "coffee 5.50",
            "payee_name": "STARBUCKS #123",
            "amount": "5.50",
            "memo": "",
            "names": "STARBUCKS #123\nSTARBUCKS #77",
        }
        for key, template in DEFAULT_PROMPTS.items():
            rendered = render_prompt(template, sample_values)
            for placeholder in PROMPT_PLACEHOLDERS[key]:
                assert placeholder not in rendered, f"{key} left {placeholder} unrendered"

    def test_every_prompt_key_is_a_settings_default(self):
        for key in DEFAULT_PROMPTS:
            assert key in DEFAULTS


class TestSettingsOverrides:
    def make_repo(self, rows: dict[str, str] | None = None) -> MagicMock:
        rows = rows or {}
        repo = MagicMock()

        async def get(key):
            if key in rows:
                setting = MagicMock()
                setting.value = rows[key]
                return setting
            return None

        async def get_all():
            out = []
            for k, v in rows.items():
                s = MagicMock()
                s.key = k
                s.value = v
                out.append(s)
            return out

        async def delete(key):
            rows.pop(key, None)

        repo.get = AsyncMock(side_effect=get)
        repo.get_all = AsyncMock(side_effect=get_all)
        repo.delete = AsyncMock(side_effect=delete)
        repo.set = AsyncMock()
        return repo

    async def test_prompt_default_when_no_override(self):
        svc = SettingsService(self.make_repo())
        assert (
            await svc.get("ai_prompt_normalize_payee")
            == DEFAULT_PROMPTS["ai_prompt_normalize_payee"]
        )

    async def test_override_then_unset_reverts_to_default(self):
        rows = {"ai_prompt_normalize_payee": "my custom prompt {payee_name}"}
        svc = SettingsService(self.make_repo(rows))
        assert await svc.get("ai_prompt_normalize_payee") == "my custom prompt {payee_name}"
        await svc.unset("ai_prompt_normalize_payee")
        assert (
            await svc.get("ai_prompt_normalize_payee")
            == DEFAULT_PROMPTS["ai_prompt_normalize_payee"]
        )

    async def test_get_all_detailed_reports_override_state(self):
        rows = {"ollama_model": "gemma4"}
        svc = SettingsService(self.make_repo(rows))
        detailed = {item["key"]: item for item in await svc.get_all_detailed()}
        assert detailed["ollama_model"]["is_overridden"] is True
        assert detailed["ollama_model"]["value"] == "gemma4"
        assert detailed["ollama_host"]["is_overridden"] is False
        assert detailed["ollama_host"]["default_value"] == DEFAULTS["ollama_host"]

    async def test_vision_model_empty_default(self):
        svc = SettingsService(self.make_repo())
        assert await svc.get("ollama_vision_model") == ""

import json
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, Transaction
from igab.integrations.ollama.client import OllamaClient
from igab.services.settings_service import SettingsService


class AIService:
    def __init__(self, session: AsyncSession, settings: SettingsService) -> None:
        self.session = session
        self.settings = settings

    async def _client(self) -> OllamaClient:
        host = await self.settings.get("ollama_host") or "http://localhost:11434"
        model = await self.settings.get("ollama_model") or "llama3.2"
        return OllamaClient(host, model)

    async def suggest_category(
        self,
        budget_id: uuid.UUID,
        payee_name: str,
        amount: float,
        memo: str | None = None,
    ) -> dict:
        categories = await self._get_categories(budget_id)
        if not categories:
            return {"category_id": None, "category_name": None, "confidence": 0.0}

        cat_list = "\n".join(f"- {c['id']}: {c['name']} ({c['group']})" for c in categories)
        prompt = (
            f"Transaction: payee='{payee_name}', amount={amount}"
            + (f", memo='{memo}'" if memo else "")
            + f"\n\nAvailable categories:\n{cat_list}"
            + '\n\nRespond with JSON: {"category_id": "<uuid>", "confidence": <0-1>}. '
            "Choose the most appropriate category. Only output valid JSON."
        )
        system = "You are a financial transaction categorizer. Return only JSON."

        try:
            client = await self._client()
            raw = await client.generate(prompt, system)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            cat_id = data.get("category_id")
            confidence = float(data.get("confidence", 0.5))
            matched = next((c for c in categories if str(c["id"]) == cat_id), None)
            return {
                "category_id": cat_id if matched else None,
                "category_name": matched["name"] if matched else None,
                "confidence": confidence,
            }
        except Exception:
            return {"category_id": None, "category_name": None, "confidence": 0.0}

    async def normalize_payee(self, payee_name: str) -> str:
        prompt = (
            f"Normalize this bank payee name to a clean, readable merchant name: '{payee_name}'\n"
            "Respond with only the normalized name, nothing else."
        )
        try:
            client = await self._client()
            result = await client.generate(prompt)
            return result.strip().strip('"').strip("'")
        except Exception:
            return payee_name

    async def spending_insights(self, budget_id: uuid.UUID, month: date) -> str:
        month_start = month.replace(day=1)
        next_month = month_start.replace(
            year=month_start.year + (1 if month_start.month == 12 else 0),
            month=1 if month_start.month == 12 else month_start.month + 1,
        )

        q = (
            select(
                Category.name,
                Transaction.amount,
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.date >= month_start,
                Transaction.date < next_month,
                Transaction.parent_transaction_id.is_(None),
            )
        )
        result = await self.session.execute(q)
        rows = result.all()

        if not rows:
            return "No transaction data available for this month."

        summary = {}
        for name, amt in rows:
            summary[name] = summary.get(name, 0) + float(amt)

        summary_text = "\n".join(
            f"- {name}: ${abs(total):.2f} ({'expense' if total < 0 else 'income'})"
            for name, total in sorted(summary.items(), key=lambda x: x[1])
        )

        prompt = (
            f"Monthly budget summary for {month_start.strftime('%B %Y')}:\n{summary_text}\n\n"
            "Provide 2-3 sentences of spending insights and one actionable suggestion."
        )
        system = "You are a helpful personal finance advisor."
        try:
            client = await self._client()
            return await client.generate(prompt, system)
        except Exception:
            return "Unable to generate insights — check Ollama connection in Settings."

    async def suggest_payee_merges(self, budget_id: uuid.UUID) -> list[dict]:
        """Return groups of payees that appear to be the same vendor."""
        from igab.db.models import Payee

        result = await self.session.execute(
            select(Payee.id, Payee.name)
            .where(
                Payee.budget_id == budget_id,
                Payee.is_deleted == False,  # noqa: E712
                Payee.transfer_account_id.is_(None),
            )
            .order_by(Payee.name)
        )
        payees = [{"id": str(r.id), "name": r.name} for r in result.all()]
        if len(payees) < 2:
            return []

        names_list = "\n".join(f"- {p['id']}: {p['name']}" for p in payees)
        prompt = (
            "Below is a list of payee names from a personal budget app (id: name).\n"
            "Identify groups of payees that are likely the same vendor "
            "(e.g. 'AMAZON', 'Amazon.com', 'AMAZON PRIME' are all Amazon).\n"
            "Return a JSON array of groups, each with:\n"
            '  {"canonical": "<display name>", "ids": ["<uuid>", ...]}\n'
            "Only include groups with 2+ entries. Output only valid JSON array.\n\n"
            f"Payees:\n{names_list}"
        )
        system = "You are a data-deduplication assistant. Return only a JSON array."
        try:
            client = await self._client()
            raw = await client.generate(prompt, system)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                raw = raw.rstrip("`").strip()
            groups = json.loads(raw)
            payee_map = {p["id"]: p["name"] for p in payees}
            result_groups = []
            for g in groups:
                valid_ids = [i for i in g.get("ids", []) if i in payee_map]
                if len(valid_ids) >= 2:
                    result_groups.append(
                        {
                            "canonical": g.get("canonical", payee_map[valid_ids[0]]),
                            "payees": [{"id": i, "name": payee_map[i]} for i in valid_ids],
                        }
                    )
            return result_groups
        except Exception:
            return []

    async def _get_categories(self, budget_id: uuid.UUID) -> list[dict]:
        from igab.db.models import CategoryGroup

        result = await self.session.execute(
            select(Category.id, Category.name, CategoryGroup.name.label("group"))
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                Category.is_hidden == False,  # noqa: E712
            )
        )
        return [{"id": r.id, "name": r.name, "group": r.group} for r in result.all()]

from decimal import Decimal

from igab.config import settings
from igab.services.email_service import EmailService


class NotificationService:
    def __init__(self, email_svc: EmailService) -> None:
        self.email = email_svc

    async def notify_category_negative(
        self,
        category_name: str,
        available: Decimal,
        budget_name: str,
    ) -> None:
        await self.email.send(
            to=settings.ADMIN_EMAIL,
            subject=f"[IGAB] Category '{category_name}' is negative",
            template_name="category_negative.html",
            context={
                "category_name": category_name,
                "available": available,
                "budget_name": budget_name,
            },
        )

    async def notify_sync_complete(
        self,
        imported: int,
        skipped: int,
        budget_name: str,
    ) -> None:
        await self.email.send(
            to=settings.ADMIN_EMAIL,
            subject=f"[IGAB] SimpleFIN sync complete for {budget_name}",
            template_name="sync_complete.html",
            context={
                "imported": imported,
                "skipped": skipped,
                "budget_name": budget_name,
            },
        )

    async def notify_monthly_summary(
        self,
        month_label: str,
        total_income: Decimal,
        total_expenses: Decimal,
        budget_name: str,
    ) -> None:
        await self.email.send(
            to=settings.ADMIN_EMAIL,
            subject=f"[IGAB] Monthly summary for {month_label}",
            template_name="monthly_summary.html",
            context={
                "month_label": month_label,
                "total_income": total_income,
                "total_expenses": total_expenses,
                "net": total_income - total_expenses,
                "budget_name": budget_name,
            },
        )

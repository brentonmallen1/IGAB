from fastapi import APIRouter

from igab.api.v1 import (
    accounts,
    ai,
    ai_jobs,
    attachments,
    auth,
    backups,
    budget_views,
    budgets,
    categories,
    imports,
    liabilities,
    reconciliation,
    reports,
    scheduled_transactions,
    settings,
    simplefin,
    tags,
    transactions,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(budgets.router, tags=["budgets"])
api_router.include_router(accounts.router, tags=["accounts"])
api_router.include_router(categories.router, tags=["categories"])
api_router.include_router(transactions.router, tags=["transactions"])
api_router.include_router(imports.router, tags=["imports"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(backups.router, tags=["backups"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(ai.router, tags=["ai"])
api_router.include_router(ai_jobs.router, tags=["ai-jobs"])
api_router.include_router(simplefin.router, tags=["simplefin"])
api_router.include_router(scheduled_transactions.router, tags=["scheduled-transactions"])
api_router.include_router(reconciliation.router, tags=["reconciliation"])
api_router.include_router(budget_views.router, tags=["budget-views"])
api_router.include_router(attachments.router, tags=["attachments"])
api_router.include_router(tags.router, tags=["tags"])
api_router.include_router(liabilities.router, tags=["liabilities"])

from django.urls import path

from apps.transactions.views.creation_views import (
    transaction_draft_save,
    transaction_new,
    transaction_people_search,
    transaction_prepare,
)
from apps.transactions.views.workspace_views import transaction_workspace

urlpatterns = [
    path("transactions/new", transaction_new, name="transaction_new"),
    path(
        "transactions/draft",
        transaction_draft_save,
        name="transaction_draft_save",
    ),
    path(
        "transactions/prepare",
        transaction_prepare,
        name="transaction_prepare",
    ),
    path(
        "transactions/people",
        transaction_people_search,
        name="transaction_people_search",
    ),
    path(
        "transactions/<uuid:public_id>",
        transaction_workspace,
        name="transaction_workspace",
    ),
]

from django.urls import path

from apps.transactions.views.creation_views import (
    transaction_draft_save,
    transaction_new,
    transaction_people_search,
    transaction_prepare,
)
from apps.transactions.views.workspace_views import (
    my_transactions,
    transaction_assignment_save,
    transaction_key_date_end,
    transaction_key_date_save,
    transaction_note_end,
    transaction_note_save,
    transaction_party_end,
    transaction_party_save,
    transaction_property_save,
    transaction_workspace,
)

urlpatterns = [
    path("transactions", my_transactions, name="my_transactions"),
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
    path(
        "transactions/<uuid:public_id>/parties",
        transaction_party_save,
        name="transaction_party_save",
    ),
    path(
        "transactions/<uuid:public_id>/parties/end",
        transaction_party_end,
        name="transaction_party_end",
    ),
    path(
        "transactions/<uuid:public_id>/property",
        transaction_property_save,
        name="transaction_property_save",
    ),
    path(
        "transactions/<uuid:public_id>/key-dates",
        transaction_key_date_save,
        name="transaction_key_date_save",
    ),
    path(
        "transactions/<uuid:public_id>/key-dates/end",
        transaction_key_date_end,
        name="transaction_key_date_end",
    ),
    path(
        "transactions/<uuid:public_id>/notes",
        transaction_note_save,
        name="transaction_note_save",
    ),
    path(
        "transactions/<uuid:public_id>/notes/end",
        transaction_note_end,
        name="transaction_note_end",
    ),
    path(
        "transactions/<uuid:public_id>/assignments",
        transaction_assignment_save,
        name="transaction_assignment_save",
    ),
]

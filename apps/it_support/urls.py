from django.urls import path

from apps.it_support.views import (
    it_support,
    ticket_assign,
    ticket_attach,
    ticket_attachment_download,
    ticket_create,
    ticket_detail_view,
    ticket_prioritise,
    ticket_reply,
    ticket_transition,
)

urlpatterns = [
    # Self-service. Open to every authenticated person.
    path("support/it", it_support, name="it_support"),
    path("support/it/send", ticket_create, name="it_support_create"),
    # Keyed by public id, never the primary key: a sequential id in a URL tells
    # a holder of one link how many tickets exist and what to try next.
    path(
        "support/it/<uuid:public_id>",
        ticket_detail_view,
        name="it_support_ticket",
    ),
    path(
        "support/it/<uuid:public_id>/reply",
        ticket_reply,
        name="it_support_reply",
    ),
    path(
        "support/it/<uuid:public_id>/attachments",
        ticket_attach,
        name="it_support_attach",
    ),
    # Streamed by a view that re-authorizes the reader against the parent
    # ticket on every request. There is no signed link and no public URL.
    path(
        "support/it/<uuid:public_id>/attachments/<uuid:attachment_id>",
        ticket_attachment_download,
        name="it_support_attachment",
    ),
    # Triage. The queue itself is an operations destination registered in
    # `apps.web.views.OPERATIONS_VIEWS`; these are the endpoints it drives.
    path(
        "operations/it-support/<uuid:public_id>/transition",
        ticket_transition,
        name="it_support_transition",
    ),
    path(
        "operations/it-support/<uuid:public_id>/assign",
        ticket_assign,
        name="it_support_assign",
    ),
    path(
        "operations/it-support/<uuid:public_id>/priority",
        ticket_prioritise,
        name="it_support_priority",
    ),
]

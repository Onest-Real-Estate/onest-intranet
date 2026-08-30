from django.urls import path

from apps.feedback.views import (
    feedback_assign,
    feedback_convert,
    feedback_create,
    feedback_detail,
    feedback_mine,
    feedback_note,
    feedback_prioritise,
    feedback_screenshot,
    feedback_submit,
    feedback_transition,
)

urlpatterns = [
    # Self-service. Open to every authenticated person.
    path("support/feedback", feedback_submit, name="feedback_submit"),
    path("support/feedback/send", feedback_create, name="feedback_create"),
    path("support/feedback/mine", feedback_mine, name="feedback_mine"),
    # Keyed by public id, never the primary key: a sequential id in a URL tells
    # a holder of one link how many tickets exist and what to try next.
    path(
        "support/feedback/<uuid:public_id>",
        feedback_detail,
        name="feedback_detail",
    ),
    path(
        "support/feedback/<uuid:public_id>/note",
        feedback_note,
        name="feedback_note",
    ),
    # Streamed by a view that re-authorizes the reader against the parent
    # ticket. There is no signed link and no public URL.
    path(
        "support/feedback/<uuid:public_id>/screenshot/<uuid:screenshot_id>",
        feedback_screenshot,
        name="feedback_screenshot",
    ),
    # Triage.
    # The inbox itself is an operations destination and is registered in
    # `apps.web.views.OPERATIONS_VIEWS`; these are the endpoints it drives.
    path(
        "operations/feedback/<uuid:public_id>/transition",
        feedback_transition,
        name="feedback_transition",
    ),
    path(
        "operations/feedback/<uuid:public_id>/assign",
        feedback_assign,
        name="feedback_assign",
    ),
    path(
        "operations/feedback/<uuid:public_id>/priority",
        feedback_prioritise,
        name="feedback_prioritise",
    ),
    path(
        "operations/feedback/<uuid:public_id>/convert",
        feedback_convert,
        name="feedback_convert",
    ),
]

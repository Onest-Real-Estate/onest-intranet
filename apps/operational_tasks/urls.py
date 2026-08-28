from django.urls import path

from apps.operational_tasks.views import (
    task_assign,
    task_comment,
    task_create,
    task_detail_view,
    task_transition,
    tasks_index,
)

urlpatterns = [
    path("operations/tasks", tasks_index, name="operational_tasks"),
    path("operations/tasks/new", task_create, name="operational_task_create"),
    # Keyed by the public id, never the primary key: a sequential id in a URL
    # tells a holder of one link how many tasks exist and what to try next.
    path(
        "operations/tasks/<uuid:public_id>",
        task_detail_view,
        name="operational_task_detail",
    ),
    path(
        "operations/tasks/<uuid:public_id>/transition",
        task_transition,
        name="operational_task_transition",
    ),
    path(
        "operations/tasks/<uuid:public_id>/assign",
        task_assign,
        name="operational_task_assign",
    ),
    path(
        "operations/tasks/<uuid:public_id>/comment",
        task_comment,
        name="operational_task_comment",
    ),
]

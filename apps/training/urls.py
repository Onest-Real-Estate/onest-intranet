from django.urls import path

from .administration_views import (
    training_create,
    training_duplicate_version,
    training_edit,
    training_lifecycle,
    training_media_manager,
    training_media_remove,
    training_media_reorder,
    training_media_replace,
    training_media_upload,
    training_new,
    training_recipient_search,
    training_update,
)
from .views import training_detail, training_learning, training_media

urlpatterns = [
    path("training-learning", training_learning, name="training_learning"),
    path(
        "training-learning/<int:content_id>",
        training_detail,
        name="training_detail",
    ),
    path(
        "training-learning/media/<int:media_id>",
        training_media,
        name="training_media",
    ),
    path(
        "operations/training/recipients",
        training_recipient_search,
        name="training_recipient_search",
    ),
    path(
        "operations/training/new",
        training_new,
        name="training_new",
    ),
    path(
        "operations/training/create",
        training_create,
        name="training_create",
    ),
    path(
        "operations/training/<int:content_id>/edit",
        training_edit,
        name="training_edit",
    ),
    path(
        "operations/training/<int:content_id>/save",
        training_update,
        name="training_update",
    ),
    path(
        "operations/training/<int:content_id>/lifecycle",
        training_lifecycle,
        name="training_lifecycle",
    ),
    path(
        "operations/training/<int:content_id>/duplicate-version",
        training_duplicate_version,
        name="training_duplicate_version",
    ),
    path(
        "operations/training/<int:content_id>/media",
        training_media_manager,
        name="training_media_manager",
    ),
    path(
        "operations/training/<int:content_id>/media/upload",
        training_media_upload,
        name="training_media_upload",
    ),
    path(
        "operations/training/<int:content_id>/media/reorder",
        training_media_reorder,
        name="training_media_reorder",
    ),
    path(
        "operations/training/media/<int:media_id>/replace",
        training_media_replace,
        name="training_media_replace",
    ),
    path(
        "operations/training/media/<int:media_id>/remove",
        training_media_remove,
        name="training_media_remove",
    ),
]

# Index is wired through OPERATIONS_VIEWS in apps.web.views.

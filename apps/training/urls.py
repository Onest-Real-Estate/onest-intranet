from django.urls import path

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
]

from django.urls import path

from .views import document_detail, document_file, documents_forms

urlpatterns = [
    path("documents-forms", documents_forms, name="documents_forms"),
    path(
        "documents-forms/<int:document_id>",
        document_detail,
        name="document_detail",
    ),
    path(
        "documents-forms/files/<int:file_id>",
        document_file,
        name="document_file",
    ),
]

from django.urls import path

from .administration_views import (
    admin_compliance,
    policy_ack_report,
    policy_ack_waive,
    policy_admin_create,
    policy_admin_duplicate,
    policy_admin_edit,
    policy_admin_file_remove,
    policy_admin_file_upload,
    policy_admin_lifecycle,
    policy_admin_new,
    policy_admin_update,
)
from .views import (
    policies_compliance,
    policy_acknowledge,
    policy_detail,
    policy_document_file,
)

urlpatterns = [
    path("policies-compliance", policies_compliance, name="policies_compliance"),
    path(
        "policies-compliance/<int:policy_id>",
        policy_detail,
        name="policy_detail",
    ),
    path(
        "policies-compliance/<int:policy_id>/acknowledge",
        policy_acknowledge,
        name="policy_acknowledge",
    ),
    path(
        "policies-compliance/files/<int:file_id>",
        policy_document_file,
        name="policy_document_file",
    ),
    # Nested admin routes — index itself is wired via OPERATIONS_VIEWS.
    path(
        "operations/compliance/new",
        policy_admin_new,
        name="policy_admin_new",
    ),
    path(
        "operations/compliance/create",
        policy_admin_create,
        name="policy_admin_create",
    ),
    path(
        "operations/compliance/<int:policy_id>/edit",
        policy_admin_edit,
        name="policy_admin_edit",
    ),
    path(
        "operations/compliance/<int:policy_id>/save",
        policy_admin_update,
        name="policy_admin_update",
    ),
    path(
        "operations/compliance/<int:policy_id>/lifecycle",
        policy_admin_lifecycle,
        name="policy_admin_lifecycle",
    ),
    path(
        "operations/compliance/<int:policy_id>/duplicate-version",
        policy_admin_duplicate,
        name="policy_admin_duplicate",
    ),
    path(
        "operations/compliance/<int:policy_id>/files/upload",
        policy_admin_file_upload,
        name="policy_admin_file_upload",
    ),
    path(
        "operations/compliance/files/<int:file_id>/remove",
        policy_admin_file_remove,
        name="policy_admin_file_remove",
    ),
    path(
        "operations/compliance/acknowledgements",
        policy_ack_report,
        name="policy_ack_report",
    ),
    path(
        "operations/compliance/<int:policy_id>/waive",
        policy_ack_waive,
        name="policy_ack_waive",
    ),
]

# Re-export index view name so OPERATIONS_VIEWS can import it cleanly.
__all__ = ["admin_compliance", "urlpatterns"]

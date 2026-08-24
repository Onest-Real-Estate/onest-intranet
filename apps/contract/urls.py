from django.urls import path

from apps.contract.administration_views import (
    contract_template_action,
    contract_template_create,
    contract_template_index,
    contract_template_update,
    contract_template_workspace,
)

urlpatterns = [
    path(
        "operations/contract-templates",
        contract_template_index,
        name="admin_contract_templates",
    ),
    path(
        "operations/contract-templates/templates/create",
        contract_template_create,
        name="contract_template_create",
    ),
    path(
        "operations/contract-templates/templates/<int:version_id>",
        contract_template_workspace,
        name="contract_template_workspace",
    ),
    path(
        "operations/contract-templates/templates/<int:version_id>/save",
        contract_template_update,
        name="contract_template_update",
    ),
    path(
        "operations/contract-templates/templates/<int:version_id>/action",
        contract_template_action,
        name="contract_template_action",
    ),
]

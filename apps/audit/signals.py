"""Wire audit app signal receivers.

Importing this module (done by AuditConfig.ready) ensures the catalog is
loaded so all events are registered before any publisher calls.
"""

# Load the catalog so all events are registered at startup.
import apps.audit.catalog  # noqa: F401

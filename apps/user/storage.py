"""Protected storage for authenticated-only files.

Resource files are never exposed through public media URLs. Locally they live
in a ``private/`` subtree with no browsable base URL; on S3/RustFS they use a
private ACL with presigned access. In every configuration the only supported
read path is an authorized Django view that streams the bytes itself.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateLocalStorage(FileSystemStorage):
    """Local protected storage under ``MEDIA_ROOT/private`` (no public URL).

    ``MEDIA_ROOT`` is resolved lazily so test overrides apply even after this
    storage has been constructed.
    """

    def __init__(self):
        super().__init__(base_url=None)

    @property
    def location(self) -> str:
        return str(Path(settings.MEDIA_ROOT) / "private")


def private_storage():
    """Return the configured protected-storage backend.

    A callable so Django resolves it lazily at runtime instead of baking a
    backend into migrations.
    """
    if getattr(settings, "USE_S3", False):
        from storages.backends.s3boto3 import S3Boto3Storage

        class PrivateS3Boto3Storage(S3Boto3Storage):
            location = "private"
            default_acl = "private"
            querystring_auth = True
            file_overwrite = False

        return PrivateS3Boto3Storage()
    return PrivateLocalStorage()

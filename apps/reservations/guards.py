from contextlib import contextmanager
from contextvars import ContextVar

_OFFICE_TRANSFER_ALLOWED: ContextVar[bool] = ContextVar(
    "reservation_space_office_transfer_allowed", default=False
)


def office_transfer_is_allowed() -> bool:
    return _OFFICE_TRANSFER_ALLOWED.get()


@contextmanager
def allow_office_transfer():
    token = _OFFICE_TRANSFER_ALLOWED.set(True)
    try:
        yield
    finally:
        _OFFICE_TRANSFER_ALLOWED.reset(token)

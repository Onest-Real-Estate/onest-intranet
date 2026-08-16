from apps.web.tasks import ping
from config.celery import app as celery_app


def test_celery_app_is_configured():
    assert celery_app.main == "onest"
    # Broker/backend point at Redis (settings defaults; the compose stacks
    # override with dedicated Redis DBs).
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.result_backend.startswith("redis://")
    assert celery_app.conf.beat_scheduler == (
        "django_celery_beat.schedulers:DatabaseScheduler"
    )


def test_ping_task_runs_synchronously():
    assert ping.run(message="hello") == "ping: hello"

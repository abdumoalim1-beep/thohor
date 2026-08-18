from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "mersad",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

# Part H6 — each research.execute_run task is a separate OS process under
# Celery's prefork pool, so no in-process semaphore can bound cross-store
# concurrency the way app.research.loop bounds concurrency within one run.
# worker_concurrency is the actual enforcement mechanism for
# STORE_RUN_MAX_CONCURRENCY in production; ties the explicit Settings name
# from the directive to real infrastructure behavior instead of leaving it
# as a config value nothing reads.
celery_app.conf.worker_concurrency = settings.store_run_max_concurrency

# Group F7 — hourly is enough resolution for the coarsest cadence options
# (daily/weekly/monthly); requires a separate `celery -A app.workers.celery_app
# beat` process to actually fire.
celery_app.conf.beat_schedule = {
    "scan-scheduled-research": {
        "task": "research.scan_scheduled",
        "schedule": 3600.0,
    },
    "scan-scheduled-visibility": {
        "task": "visibility.scan_scheduled",
        "schedule": 3600.0,
    },
}

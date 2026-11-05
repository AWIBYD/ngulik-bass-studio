"""Redis/RQ job queue helpers used by the API. The heavy work lives in app.tasks (worker only)."""
from functools import lru_cache

from redis import Redis
from rq import Queue, Worker
from rq.command import send_stop_job_command
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job, JobStatus

from .config import get_settings

QUEUE_NAME = "separation"


@lru_cache
def redis_conn() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=10)


def queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis_conn())


def enqueue_separation(job_id: str) -> str:
    rq_job = queue().enqueue(
        "app.tasks.separation.run_separation", job_id,
        job_timeout=get_settings().separation_job_timeout, result_ttl=3600, failure_ttl=7 * 86400,
    )
    return rq_job.id


def workers_online() -> int:
    try:
        return len([w for w in Worker.all(connection=redis_conn()) if QUEUE_NAME in w.queue_names()])
    except Exception:
        return 0


def queue_length() -> int:
    try:
        return len(queue())
    except Exception:
        return 0


def rq_status(rq_job_id: str | None) -> str | None:
    """RQ status string, or None when the job is gone from Redis."""
    if not rq_job_id:
        return None
    try:
        return Job.fetch(rq_job_id, connection=redis_conn()).get_status(refresh=True)
    except NoSuchJobError:
        return None


DEAD_STATUSES = {JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED, None}


def cancel(rq_job_id: str | None) -> None:
    if not rq_job_id:
        return
    conn = redis_conn()
    try:
        job = Job.fetch(rq_job_id, connection=conn)
    except NoSuchJobError:
        return
    status = job.get_status(refresh=True)
    if status == JobStatus.STARTED:
        try:
            send_stop_job_command(conn, rq_job_id)
        except InvalidJobOperation:
            pass
    elif status in (JobStatus.QUEUED, JobStatus.DEFERRED, JobStatus.SCHEDULED):
        job.cancel()

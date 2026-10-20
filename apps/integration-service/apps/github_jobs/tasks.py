from celery import shared_task

from .services import cleanup_deliveries, dispatch_pending, run_job


@shared_task(ignore_result=True, acks_late=True, reject_on_worker_lost=True)
def process_github_job(job_id):
    run_job(job_id)


@shared_task(ignore_result=True)
def dispatch_github_jobs():
    return dispatch_pending()


@shared_task(ignore_result=True)
def cleanup_github_deliveries():
    return cleanup_deliveries()

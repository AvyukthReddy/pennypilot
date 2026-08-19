from celery import Celery

from worker.config import REDIS_URL

app = Celery("pennypilot", broker=REDIS_URL, backend=REDIS_URL)
app.autodiscover_tasks(["worker"])

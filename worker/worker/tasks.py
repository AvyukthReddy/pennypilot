from worker.celery_app import app


@app.task(name="worker.ping")
def ping() -> str:
    return "pong"

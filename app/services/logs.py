import uuid

from app.models.database_models import Log
from app.models.response_models import LogResponse


def get_logs_row(session, job_id: uuid.UUID):
    logs = session.query(Log).filter(Log.job_id == job_id).order_by(Log.fired_at).all()
    if logs:
        return [LogResponse.model_validate(log) for log in logs]
    else:
        return []
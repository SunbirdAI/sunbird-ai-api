from collections import defaultdict

from sqlalchemy.orm import Session

from app.crud.monitoring import get_logs_by_username
from app.schemas.monitoring import EndpointLog


def aggregate_usage_for_user(db: Session, username: str):
    logs = get_logs_by_username(db, username)
    logs = [EndpointLog.from_orm(endpoint_log) for endpoint_log in logs]
    aggregates = defaultdict(int)
    for endpoint_log in logs:
        aggregates[endpoint_log.endpoint] += 1

    return aggregates

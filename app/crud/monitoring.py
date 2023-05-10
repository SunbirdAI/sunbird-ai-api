from sqlalchemy.orm import Session
from app.models import monitoring as models
from app.schemas import monitoring as schemas


def create_endpoint_log(db: Session, log: schemas.EndpointLog):
    db_log = models.EndpointLog(username=log.username, endpoint=log.endpoint, time_taken=log.time_taken)
    db.add(db_log)
    db.commit()

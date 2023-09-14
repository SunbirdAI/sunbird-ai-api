from contextlib import contextmanager

from sqlalchemy.orm import Session
from app.models import monitoring as models
from app.schemas import monitoring as schemas
from app.database.db import SessionLocal

@contextmanager
def auto_session():
    sess = SessionLocal()
    try:
        yield sess
        sess.commit()
    except:
        sess.rollback()
    finally:
        sess.close()


def create_endpoint_log(log: schemas.EndpointLog):
    with auto_session() as sess:
        db_log = models.EndpointLog(username=log.username, endpoint=log.endpoint, time_taken=log.time_taken)
        sess.add(db_log)


def get_logs_by_username(db: Session, username: str):
    return db.query(models.EndpointLog).filter(models.EndpointLog.username == username).all()

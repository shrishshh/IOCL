from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session

_DB_PATH = Path(__file__).resolve().parent.parent / "iocl.db"
engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

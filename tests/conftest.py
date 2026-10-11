import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import Base, engine
from app.schemas import ChaosConfig


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    main.chaos = ChaosConfig()
    with TestClient(main.app) as c:  # triggers startup -> create tables + seed
        yield c

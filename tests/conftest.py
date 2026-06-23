import os
import sys
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


def _clear_app_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]


@pytest.fixture()
def client() -> Generator[TestClient]:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    _clear_app_modules()

    from app.api.main import app
    from app.db.session import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        _clear_app_modules()
        os.remove(db_path)

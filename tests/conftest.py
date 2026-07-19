from __future__ import annotations

from collections.abc import Iterator

import pytest

from ouroboros_financial_management import create_app
from ouroboros_financial_management.config import Config
from ouroboros_financial_management.extensions import db
from ouroboros_financial_management.models import User
from ouroboros_financial_management.services import seed_user_defaults


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        LOCAL_ONLY = False
        AUTO_CREATE_DB = True
        SECRET_KEY = "test-secret-key-that-is-long-enough"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'ouroboros-test.db'}"

    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def user(app) -> Iterator[User]:
    with app.app_context():
        user = User(username="andrei")
        user.set_password("correct horse battery staple")
        db.session.add(user)
        db.session.flush()
        seed_user_defaults(user)
        db.session.commit()
        yield user

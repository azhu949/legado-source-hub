"""Access user model validation tests."""

import pytest
from pydantic import ValidationError

from app.models.access_user import AccessUserCreate, AccessUserUpdate


def test_access_user_create_trims_name_and_note():
    user = AccessUserCreate(name="  手机  ", note="  自用  ")

    assert user.name == "手机"
    assert user.note == "自用"


def test_access_user_create_rejects_blank_name():
    with pytest.raises(ValidationError):
        AccessUserCreate(name="   ")


def test_access_user_update_rejects_blank_name():
    with pytest.raises(ValidationError):
        AccessUserUpdate(name="   ")

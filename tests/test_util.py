"""Test neba.util."""

import pytest

from neba.util import get_classname, import_item


class Outer:
    pass


class MyClass:
    class Inner:
        pass


def test_import_item():
    assert import_item("tests.test_util.Outer") is Outer

    with pytest.raises(ImportError):
        assert import_item("wrong_package.item")
    with pytest.raises(ImportError):
        assert import_item("tests.test_util.wrong_item")


def test_get_classname():
    class Inner:
        pass

    assert get_classname(Inner, module=False) == "test_get_classname.<locals>.Inner"
    assert get_classname(Inner) == "tests.test_util.test_get_classname.<locals>.Inner"
    assert get_classname(MyClass.Inner, module=False) == "MyClass.Inner"
    assert get_classname(MyClass.Inner) == "tests.test_util.MyClass.Inner"
    assert get_classname(Outer, module=False) == "Outer"
    assert get_classname(Outer) == "tests.test_util.Outer"

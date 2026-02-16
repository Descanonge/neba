"""Test neba.utils."""

import pytest

from neba.utils import cut_in_slices, get_classname, import_item


def test_cut_slices():
    def assert_equal(slices_ref, slices):
        assert len(slices_ref) == len(slices)
        for slc_ref, slc in zip(slices_ref, slices):
            assert slc_ref == slc

    assert_equal(cut_in_slices(9, 3), [slice(0, 3), slice(3, 6), slice(6, None)])
    assert_equal(cut_in_slices(8, 5), [slice(0, 5), slice(5, None)])
    assert_equal(cut_in_slices(3, 5), [slice(0, None)])


class Outer:
    pass


class MyClass:
    class Inner:
        pass


def test_import_item():
    assert import_item("tests.test_utils.Outer") is Outer

    with pytest.raises(ImportError):
        assert import_item("wrong_package.item")
    with pytest.raises(ImportError):
        assert import_item("tests.test_utils.wrong_item")


def test_get_classname():
    class Inner:
        pass

    assert get_classname(Inner, module=False) == "test_get_classname.<locals>.Inner"
    assert get_classname(Inner) == "tests.test_utils.test_get_classname.<locals>.Inner"
    assert get_classname(MyClass.Inner, module=False) == "MyClass.Inner"
    assert get_classname(MyClass.Inner) == "tests.test_utils.MyClass.Inner"
    assert get_classname(Outer, module=False) == "Outer"
    assert get_classname(Outer) == "tests.test_utils.Outer"

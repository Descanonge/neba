"""Test functions from neba.data.util."""

from neba.data.util import cut_slices


def test_cut_slices():
    def assert_equal(slices_ref, slices):
        assert len(slices_ref) == len(slices)
        for slc_ref, slc in zip(slices_ref, slices):
            assert slc_ref == slc

    assert_equal(cut_slices(9, 3), [slice(0, 3), slice(3, 6), slice(6, None)])
    assert_equal(cut_slices(8, 5), [slice(0, 5), slice(5, None)])
    assert_equal(cut_slices(3, 5), [slice(0, None)])

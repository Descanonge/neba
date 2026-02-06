import pytest

from neba.data import Dataset, DatasetStore


class DatasetOnlyId(Dataset):
    ID = "id1"


class DatasetOnlyShortname(Dataset):
    SHORTNAME = "short2"


class DatasetIdAndShortname(Dataset):
    ID = "id3"
    SHORTNAME = "short3"


class DatasetForImport(Dataset):
    pass


ds_import_string = "tests.data.test_store.DatasetForImport"


class TestDatasetStore:
    def get_store(self):
        return DatasetStore(
            DatasetOnlyId, DatasetOnlyShortname, DatasetIdAndShortname, ds_import_string
        )

    def test_mapping(self):
        store = self.get_store()
        all_keys = ["id1", "short2", "id3", "short3", "DatasetForImport"]
        ids = ["id1", "short2", "id3", "DatasetForImport"]

        # __contains__
        for key in all_keys:
            assert key in store

        # __len__
        assert len(store) == 4

        # __str__
        assert str(store) == (
            '{"id1" : DatasetOnlyId, '
            '"short2" : DatasetOnlyShortname, '
            '"id3" | "short3" : DatasetIdAndShortname, '
            f'"DatasetForImport" : "{ds_import_string}"'
            "}"
        )

        # __iter__
        assert list(iter(store)) == ids

        # __delitem__
        store.pop("id1")
        assert "id1" not in store
        store.pop("id3")
        assert "id3" not in store
        assert "short3" not in store
        store.pop("DatasetForImport")
        assert "DatasetForImport" not in store

    def test_get(self):
        store = self.get_store()
        assert store["id1"] is DatasetOnlyId
        assert store["short2"] is DatasetOnlyShortname
        assert store["id3"] is DatasetIdAndShortname
        assert store["short3"] is DatasetIdAndShortname

        assert isinstance(store._datasets["DatasetForImport"], str)
        assert store.get_no_import("DatasetForImport") == ds_import_string
        assert isinstance(store._datasets["DatasetForImport"], str)
        assert store["DatasetForImport"] is DatasetForImport
        assert isinstance(store._datasets["DatasetForImport"], type)

    def test_set(self):
        store = self.get_store()

        class DatasetDuplicateId(Dataset):
            ID = "id1"

        with pytest.raises(KeyError):
            store.add(DatasetDuplicateId)

        store.add(DatasetDuplicateId, name="dupl")
        assert store["dupl"] == DatasetDuplicateId

    def test_multiple_shortnames(self):
        store = self.get_store()

        class DatasetDuplicateShortname(Dataset):
            ID = "id4"
            SHORTNAME = "short3"

        store.add(DatasetDuplicateShortname)

        with pytest.raises(KeyError):
            store["short3"]

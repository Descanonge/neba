import pytest

from neba.data import DataInterface, DataInterfaceStore


class InterfaceOnlyId(DataInterface):
    ID = "id1"


class InterfaceOnlyShortname(DataInterface):
    SHORTNAME = "short2"


class InterfaceIdAndShortname(DataInterface):
    ID = "id3"
    SHORTNAME = "short3"


class InterfaceForImport(DataInterface):
    pass


ds_import_string = "tests.data.test_store.InterfaceForImport"


class TestDataInterfaceStore:
    def get_store(self):
        return DataInterfaceStore(
            InterfaceOnlyId,
            InterfaceOnlyShortname,
            InterfaceIdAndShortname,
            ds_import_string,
        )

    def test_mapping(self):
        store = self.get_store()
        all_keys = ["id1", "short2", "id3", "short3", "InterfaceForImport"]
        ids = ["id1", "short2", "id3", "InterfaceForImport"]

        # __contains__
        for key in all_keys:
            assert key in store

        # __len__
        assert len(store) == 4

        # __str__
        assert str(store) == (
            '{"id1" : InterfaceOnlyId, '
            '"short2" : InterfaceOnlyShortname, '
            '"id3" | "short3" : InterfaceIdAndShortname, '
            f'"InterfaceForImport" : "{ds_import_string}"'
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
        store.pop("InterfaceForImport")
        assert "InterfaceForImport" not in store

    def test_get(self):
        store = self.get_store()
        assert store["id1"] is InterfaceOnlyId
        assert store["short2"] is InterfaceOnlyShortname
        assert store["id3"] is InterfaceIdAndShortname
        assert store["short3"] is InterfaceIdAndShortname

        assert isinstance(store._interfaces["InterfaceForImport"], str)
        assert store.get_no_import("InterfaceForImport") == ds_import_string
        assert isinstance(store._interfaces["InterfaceForImport"], str)
        assert store["InterfaceForImport"] is InterfaceForImport
        assert isinstance(store._interfaces["InterfaceForImport"], type)

    def test_set(self):
        store = self.get_store()

        class InterfaceDuplicateId(DataInterface):
            ID = "id1"

        with pytest.raises(KeyError):
            store.add(InterfaceDuplicateId)

        store.add(InterfaceDuplicateId, name="dupl")
        assert store["dupl"] == InterfaceDuplicateId

    def test_multiple_shortnames(self):
        store = self.get_store()

        class InterfaceDuplicateShortname(DataInterface):
            ID = "id4"
            SHORTNAME = "short3"

        store.add(InterfaceDuplicateShortname)

        with pytest.raises(KeyError):
            store["short3"]

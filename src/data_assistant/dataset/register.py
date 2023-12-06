from .dataset import DatasetAbstract


class DatasetStore(dict):
    """Mapping of registered Datasets.

    Maps ID and/or SHORTNAME to a :class:`DatasetAbstract` subclass.

    Datasets classes are stored using their unique ID, or SHORTNAME if not
    defined. They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: type[DatasetAbstract]):
        # create empty dict
        super().__init__()

        self.shortnames: list[str] = []
        self.ids_for_shortnames: list[str] = []

        for ds in args:
            self.add_dataset(ds)

    def add_dataset(self, ds: type[DatasetAbstract]):
        """Register a DatasetAbstract subclass."""
        if ds.ID is not None:
            key = ds.ID
            key_type = "ID"
        elif ds.SHORTNAME is not None:
            key = ds.SHORTNAME
            key_type = "SHORTNAME"
        else:
            raise TypeError(f"No ID or SHORTNAME defined in class {ds}")

        if key in self:
            raise KeyError(f"Dataset key {key_type}:{key} already exists.")

        if ds.SHORTNAME is not None:
            self.shortnames.append(ds.SHORTNAME)
            self.ids_for_shortnames.append(key)

        super().__setitem__(key, ds)

    def __getitem__(self, key: str) -> type[DatasetAbstract]:
        """Return DatasetAbstract subclass with this ID or SHORTNAME."""
        if key in self.shortnames:
            if self.shortnames.count(key) > 1:
                raise KeyError(f"More than one Dataset with SHORTNAME: {key}")
            idx = self.shortnames.index(key)
            key = self.ids_for_shortnames[idx]
        return super().__getitem__(key)


class register:  # noqa: N801
    """Decorator to register a dataset class in a mapping.

    Parameters
    ----------
    mapping:
        Mapping instance to register the dataset class to.
    """

    def __init__(self, mapping: DatasetStore):
        self.mapping = mapping

    def __call__(self, subclass: type[DatasetAbstract]) -> type[DatasetAbstract]:
        """Register subclass to the mapping.

        Does not change the subclass.
        """
        self.mapping.add_dataset(subclass)
        return subclass

from .dataset import DatasetAbstract


class DataLoadersMap(dict):
    """Mapping of registered DataLoaders.

    Maps ID and/or SHORTNAME to a DataLoaderAbstract subclass.

    DataLoaders classes are stored using their unique ID, or SHORTNAME if not
    defined. They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: type[DatasetAbstract]):
        # create empty dict
        super().__init__()

        self.shortnames: list[str] = []
        self.ids_for_shortnames: list[str] = []

        for dl in args:
            self.add_dataloader(dl)

    def add_dataloader(self, dl: type[DatasetAbstract]):
        """Register a DatasetAbstract subclass."""
        if dl.ID is not None:
            key = dl.ID
            key_type = "ID"
        elif dl.SHORTNAME is not None:
            key = dl.SHORTNAME
            key_type = "SHORTNAME"
        else:
            raise TypeError(f"No ID or SHORTNAME defined in class {dl}")

        if key in self:
            raise KeyError(f"DataLoader key {key_type}:{key} already exists.")

        if dl.SHORTNAME is not None:
            self.shortnames.append(dl.SHORTNAME)
            self.ids_for_shortnames.append(key)

        super().__setitem__(key, dl)

    def __getitem__(self, key: str) -> type[DatasetAbstract]:
        """Return DatasetAbstract subclass with this ID or SHORTNAME."""
        if key in self.shortnames:
            if self.shortnames.count(key) > 1:
                raise KeyError(f"More than one DataLoader with SHORTNAME: {key}")
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

    def __init__(self, mapping: DataLoadersMap):
        self.mapping = mapping

    def __call__(self, subclass: type[DatasetAbstract]) -> type[DatasetAbstract]:
        """Register subclass to the mapping.

        Does not change the subclass.
        """
        self.mapping.add_dataloader(subclass)
        return subclass

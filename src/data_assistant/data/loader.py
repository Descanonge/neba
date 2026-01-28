"""Plugin to load data into python."""

from __future__ import annotations

import typing as t
from collections import abc

from .module import Module
from .util import T_Data, T_Source


class LoaderAbstract(t.Generic[T_Source, T_Data], Module):
    """Abstract class of Loader plugin.

    The Loader is tasked with opening the data into Python.
    It may run post-processing if defined by the user.
    """

    def get_data(
        self,
        /,
        *,
        source: T_Source | None = None,
        ignore_postprocess: bool = False,
        load_kwargs: abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ) -> T_Data:
        """Load data and run post-processing.

        The actual loading is done by :meth:`load_data_concrete` that can be overwritten
        by subclasses.

        Tries to run the method ``postprocess_data`` of the parent dataset. If it raises
        NotImplementedError, postprocess will be ignored.

        Parameters
        ----------
        source
            Source location of the data to load. If left to None,
            :meth:`~.data_manager.DataManagerBase.get_source` is used.
        ignore_postprocess
            If True, do not apply postprocessing. Default is False.
        load_kwargs
            Arguments passed to function loading data.
        kwargs:
            Arguments passed to the postprocessing function.
        """
        if source is None:
            source = self.dm.get_source()

        if load_kwargs is None:
            load_kwargs = {}
        data = self.load_data_concrete(source, **load_kwargs)

        if ignore_postprocess:
            return data

        try:
            data = self.postprocess_data(data, **kwargs)
        except NotImplementedError:
            pass
        return data

    def postprocess_data(self, data: T_Data) -> T_Data:
        """Run operation after loading data.

        :Not implemented: implement (if necessary) on your DataManager subclass.
        """
        raise NotImplementedError("Implement in your DataManager subclass.")

    def load_data_concrete(self, source: T_Source, **kwargs) -> t.Any:
        """Load the data from datafiles.

        This method should be implemented in subclasses to account for different
        format, libraries, etc.

        :Not implemented: implement in a plugin subclass.
        """
        return NotImplementedError("Implement in a plugin subclass.")

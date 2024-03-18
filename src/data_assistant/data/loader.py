"""Plugin to load data into python."""

from __future__ import annotations

import typing as t

from .data_manager import Plugin, T_Data, T_Source


class LoaderPluginAbstract(t.Generic[T_Data, T_Source], Plugin):
    """Abstract class of Loader plugin.

    The Loader is tasked with opening the data into Python.
    It may run post-processing if defined by the user.
    """

    def load_data(
        self, source: T_Source, ignore_postprocess: bool = False, **kwargs
    ) -> T_Data:
        """Load data and run post-processing.

        Uses :meth:`load_data_concrete` that can be overwritten by subclasses.

        Tries to run the method ``postprocess_data`` of the parent dataset. If it raises
        NotImplementedError, postprocess will be ignored.

        Parameters
        ----------
        source
            Source location of the data to load.
        ignore_postprocess
            If True, do not apply postprocessing. Default is False.
        kwargs:
            Arguments passed to function loading data.
        """
        data = self.load_data_concrete(source, **kwargs)

        if ignore_postprocess:
            return data

        try:
            data = self.postprocess_data(data)
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

"""Neba.

Provides:
- a configuration framework to retrieve parameters from configuration files and command
  line arguments,
- a dataset definition framework to help bridge the gap between on-disk files and
  in-memory objects.
"""

from importlib.metadata import version

try:
    __version__ = version("neba")
except Exception:
    # Local copy or not installed with setuptools.
    # Disable minimum version checks on downstream libraries.
    __version__ = "9999"

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html


import sphinx_book_theme

import neba

## Project information

project = "Neba"
copyright = "2023, Clément Haëck"
author = "Clément Haëck"

version = neba.__version__
release = neba.__version__

print(f"{project}: {version}")

## General configuration

nitpicky = False
nitpick_ignore = [
    # ("py:class", "Sphinx"),
    # ("py:class", "ObjectMember"),
    # ("py:class", "DocumenterBridge"),
]
nitpick_ignore_regex = [
    # ("py:.*", r"sphinx.*"),
    # ("py:class", r"(traitlets\.(traitlets\.)?)?TraitType"),
    # ("py:class", r"(traitlets\.(traitlets\.)?)?Int"),
    # ("py:meth", r"__\w+__"),
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

extensions = [
    "neba.autodoc_trait",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx_design",
    "sphinx_copybutton",
]

add_module_names = False
toc_object_entries_show_parents = "hide"

pygments_style = "default"

## Autodoc config
autodoc_use_legacy_class_based = True
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_typehints_description_target = "all"
# autodoc_member_order = "groupwise"
autodoc_class_content = "both"
autodoc_class_signature = "mixed"
autodoc_type_aliases = {
    "traitlets.traitlets.Int": "traitlets.Int",
    "Finder": "filefinder.finder.Finder",
    "CallXr": "tuple[str, xarray.Dataset]",
}

python_use_unqualified_type_names = True

autodoc_default_options = {"show-inheritance": True, "inherited-members": False}

## Autosummary config
autosummary_generate = ["api/config.rst", "api/data.rst"]
autosummary_generate_overwrite = False

## Napoleon config
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_param = True
napoleon_use_rtype = False
napoleon_preprocess_type = False
# napoleon_type_aliases = autodoc_type_aliases.copy()

## Intersphinx config
intersphinx_mapping = {
    "dask": ("https://docs.dask.org/en/stable", None),
    "distributed": ("https://distributed.dask.org/en/stable", None),
    "filefinder": ("https://filefinder.readthedocs.io/en/latest", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "omegaconf": ("https://omegaconf.readthedocs.io/en/latest", None),
    "python": ("https://docs.python.org/3/", None),
    "tomlkit": ("https://tomlkit.readthedocs.io/en/latest/", None),
    "traitlets": ("https://traitlets.readthedocs.io/en/stable", None),
    "xarray": ("https://docs.xarray.dev/en/stable/", None),
    "zarr": ("https://zarr.readthedocs.io/en/stable/", None),
}


## Options for HTML output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_title = project
html_theme_options = dict(
    # TOCs
    show_navbar_depth=2,
    show_toc_level=3,
    toc_title="On this page",
    collapse_navbar=False,
    # Social icons
    icon_links=[
        dict(
            name="Repository",
            url="https://github.com/Descanonge/neba",
            icon="fa-brands fa-square-github",
        ),
    ],
    # Footer
    footer_content_items=[],
    footer_start=["version", "last-updated", "copyright"],
    footer_end=["sphinx-theme-version"],
    # For showing source
    repository_url="https://github.com/Descanonge/neba",
    use_source_button=True,
    repository_branch="main",
    path_to_docs="docs/source",
)

html_last_updated_fmt = "%Y-%m-%d"

html_context = {
    "book_theme_version": sphinx_book_theme.__version__,
}

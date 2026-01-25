# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html


import data_assistant

## Project information

project = "data-assistant"
copyright = "2023, Clément Haëck"
author = "Clément Haëck"

version = data_assistant.__version__
release = data_assistant.__version__

print(f"{project}: {version}")

## General configuration

nitpicky = False
nitpick_ignore = [
    ("py:class", "Sphinx"),
    ("py:class", "ObjectMember"),
    ("py:class", "DocumenterBridge"),
    ("py:class", "dask.distributed.Security"),
]
nitpick_ignore_regex = [
    ("py:.*", r"sphinx.*"),
    ("py:class", r"(traitlets\.(traitlets\.)?)?TraitType"),
    ("py:class", r"(traitlets\.(traitlets\.)?)?Int"),
    ("py:meth", r"__\w+__"),
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

extensions = [
    "data_assistant.autodoc_trait",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
]

add_module_names = False
toc_object_entries_show_parents = "hide"

pygments_style = "default"

## Autodoc config
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_typehints_description_target = "all"
# autodoc_member_order = "groupwise"
autodoc_class_content = "both"
autodoc_class_signature = "mixed"
autodoc_type_aliases = {
    "traitlets.traitlets.Int": "~traitlets.Int",
}

python_use_unqualified_type_names = True

autodoc_default_options = {"show-inheritance": True, "inherited-members": False}

## Autosummary config
autosummary_generate = ["api.rst"]

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
    "dask-jobqueue": ("https://jobqueue.dask.org/en/latest/", None),
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

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_title = project
html_theme_options = dict(
    # Repo links
    github_url="https://gitlab.in2p3.fr/biofronts/data-assistant",
    collapse_navigation=False,
    show_toc_level=2,
    # Social icons
    icon_links=[
        dict(
            name="Repository",
            url="https://gitlab.in2p3.fr/biofronts/data-assistant",
            icon="fa-brands fa-square-gitlab",
        ),
    ],
    # Navigation bar
    navbar_start=["navbar-logo"],
    navbar_center=["navbar-nav"],
    # Footer
    article_footer_items=[],
    content_footer_items=[],
    footer_start=["copyright", "last-updated"],
    footer_end=["sphinx-version", "theme-version"],
)

html_last_updated_fmt = "%Y-%m-%d"

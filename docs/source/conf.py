# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import data_assistant

# -- Project information -----------------------------------------------------

project = 'data-assistant'
copyright = '2023, Clément Haëck'
author = 'Clément Haëck'

version = data_assistant.__version__
release = data_assistant.__version__

print(f'{project}: {version}')

# -- General configuration ---------------------------------------------------

templates_path = ['_templates']
exclude_patterns = ['_build']

extensions =[
    'sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
]

add_module_names = False
toc_object_entries_show_parents = 'hide'

pygments_style = 'default'

# -- Autodoc config
autodoc_typehints = 'description'
autodoc_typehints_format = 'short'
autodoc_member_order = 'groupwise'
autodoc_type_aliases = {
    # show the full path
    'xr.DataArray': 'xarray.DataArray',
    'xr.Dataset': 'xarray.Dataset',
    'np.ndarray': 'numpy.ndarray',
    'ndarray': 'numpy.ndarray',
    'da.Array': 'dask.array.Array',
    # do not show the full path
    'collections.abc.Sequence': '~collections.abc.Sequence'
}

# -- Autosummary config
autosummary_generate = True

# -- Napoleon config
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_param = True
napoleon_use_rtype = False
napoleon_preprocess_type = False
napoleon_type_aliases = autodoc_type_aliases.copy()

# -- Intersphinx config
intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'numpy': ('https://numpy.org/doc/stable', None),
    'dask': ('https://docs.dask.org/en/latest', None),
    'xarray': ('https://docs.xarray.dev/en/stable/', None)
}


# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_book_theme'
html_static_path = ['_static']
html_title = project
html_theme_options = dict(
    collapse_navigation=False,
    use_download_button=True,
    use_fullscreen_button=False,
    show_toc_level=2,

    # Repo links
    repository_url='https://gitlab.in2p3.fr/biofronts/data-assistant',
    use_source_button=True,
    repository_branch='main',
    path_to_docs='docs',

    # Social icons
    icon_links=[
        dict(name='Repository',
             url='https://gitlab.in2p3.fr/biofronts/data-assistant',
             icon='fa-brands fa-square-gitlab'),
        dict(name='Documentation',
             url='https://data-assistant.readthedocs.io',
             icon='fa-solid fa-book')
    ],

    # Footer
    article_footer_items = ['prev-next'],
    content_footer_items = [],
    footer_start = ['footer-left'],
    footer_end = ['footer-right'],
)

html_last_updated_fmt = '%Y-%m-%d'

html_sidebars = {
    '**': ['navbar-logo.html', 'sbt-sidebar-nav.html', 'icon-links.html']
}

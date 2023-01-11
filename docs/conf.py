#  Copyright (c) Thomas Else 2023.
#  License: BSD-3

# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath('../'))

# -- Project information -----------------------------------------------------

project = 'PATATO'
copyright = '2022, Thomas Else'
author = 'Thomas Else'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ["myst_parser",
              "sphinx.ext.napoleon",
              "sphinx.ext.autosummary",
              "sphinx.ext.autodoc",
              "sphinx.ext.viewcode",
              "nbsphinx",
              "IPython.sphinxext.ipython_console_highlighting"
              ]

autosummary_generate = True
autosummary_ignore_module_all = False

autodoc_mock_imports = ["jax", "skfda", "pyopencl", "pylops", "simpa", "sklearn", "seaborn"]
autosummary_mock_imports = autodoc_mock_imports

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_book_theme'

# html_logo = "potato logo.png"
html_theme_options = {
    "repository_url": "https://github.com/tomelse/patato",
    "use_repository_button": True,
    "use_download_button": True,
}

html_title = "PATATO Documentation"
# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

latex_engine = "xelatex"

pygments_style = 'sphinx'

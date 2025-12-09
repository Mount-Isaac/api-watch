# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add project root to path for autodoc
sys.path.insert(0, os.path.abspath('..'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'api-watch'
copyright = '2025, Isaac Kyalo'
author = 'Isaac Kyalo'
release = '0.1.4'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'myst_parser',              # Markdown support
    'sphinx.ext.autodoc',       # Auto-generate docs from docstrings
    'sphinx.ext.napoleon',      # Google/NumPy docstring support
    'sphinx.ext.viewcode',      # Add source code links
    'sphinx.ext.githubpages',   # GitHub Pages support
]

# Markdown file support
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'  # Read the Docs theme
html_static_path = ['_static']

# Theme options
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'display_version': True,
}

# GitHub links
html_context = {
    'display_github': True,
    'github_user': 'mount-isaac',
    'github_repo': 'api-watch',
    'github_version': 'main',
    'conf_py_path': '/docs/',
}
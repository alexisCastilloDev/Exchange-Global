import os
import sys
import django

# -- Path setup --------------------------------------------------------
sys.path.insert(0, os.path.abspath('../..'))

# -- Django setup -------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'global_exchange.settings.dev')
django.setup()

# -- Project information -------------------------------------------------
project = 'Global Exchange'
copyright = '2026, Equipo 11'
author = 'Equipo 11'
release = '0.1'

# -- General configuration ------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
]

napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'es'

# -- Options for HTML output -----------------------------------------------
html_theme = 'alabaster'
html_static_path = ['_static']

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
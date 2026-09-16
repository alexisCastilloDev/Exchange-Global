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
root_doc = 'index'
add_module_names = False
autodoc_typehints = 'description'
autodoc_class_signature = 'separated'
modindex_common_prefix = ['apps.', 'global_exchange.']

# -- Options for HTML output -----------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_title = 'Global Exchange | Documentación técnica'
html_short_title = 'Global Exchange'
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'style_external_links': True,
}
html_static_path = ['_static']
html_css_files = ['custom.css']
html_show_sourcelink = False

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
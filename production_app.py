"""WSGI entry for separately secured production service (NOT synthetic demo)."""
from production.web import build_app
app=build_app()

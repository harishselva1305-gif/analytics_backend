"""
WSGI entrypoint for Vercel (and any other WSGI host).

Vercel's Django framework detector looks for a wsgi.py at the project root
and uses the `application` callable exposed here.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Bootstrap the single-file Django configuration before the WSGI app is built.
import backend  # noqa: F401 – runs settings.configure() as a side-effect

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()


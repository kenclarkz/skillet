"""WSGI entry point for PythonAnywhere (and any WSGI host).

PythonAnywhere's web app config imports `app` from this module.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from skillet import create_app  # noqa: E402

app = create_app()

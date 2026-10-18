import os
import sys

# Add your project directory to the sys.path
path = '/home/YOUR_USERNAME/skillet-flask'  # TODO: replace YOUR_USERNAME
if path not in sys.path:
    sys.path.insert(0, path)

# Activate your virtualenv (PythonAnywhere handles this via Web tab, but safe)
# activate_this = '/home/YOUR_USERNAME/.virtualenvs/skillet-env/bin/activate_this.py'
# with open(activate_this) as file_:
#     exec(file_.read(), dict(__file__=activate_this))

from app import create_app
application = create_app()

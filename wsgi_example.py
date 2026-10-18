# import sys
# path = '/home/yourusername/skillet-flask'
# if path not in sys.path:
#     sys.path.append(path)

from app import create_app

application = create_app()

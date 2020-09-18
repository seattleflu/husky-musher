import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from husky_musher.app import app as application

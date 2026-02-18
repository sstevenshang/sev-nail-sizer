"""Top-level conftest: ensure cv/ is on sys.path so pipeline imports work."""

import os
import sys

# When pytest is run from the repo root (e.g. `pytest cv/`), cv/ may not be
# on sys.path.  Add it so `from pipeline.xxx import yyy` resolves correctly.
_cv_dir = os.path.dirname(__file__)
if _cv_dir not in sys.path:
    sys.path.insert(0, _cv_dir)

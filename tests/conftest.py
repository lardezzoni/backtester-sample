import sys
from pathlib import Path

# Add src/ to sys.path so tests can import the modules directly.
# Walk upward from this file to find the src/ directory, which
# handles both normal runs and mutmut's mutants/ directory.
_here = Path(__file__).resolve().parent
for _ancestor in [_here.parent, _here.parent.parent]:
    _src = _ancestor / "src"
    if _src.is_dir():
        sys.path.insert(0, str(_src))
        break

import sys
import pathlib


def taken(path: pathlib.Path) -> bool:
    if not path.exists():
        return False
    sys.stderr.write("%s already exists; pass -o with a new path\n" % (path,))
    return True

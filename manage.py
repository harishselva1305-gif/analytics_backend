import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main():
    import backend

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend")
    if len(sys.argv) > 1 and sys.argv[1] == "migrate" and "--run-syncdb" not in sys.argv:
        sys.argv.insert(2, "--run-syncdb")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

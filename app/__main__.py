import sys
from pathlib import Path

from streamlit.web import cli as stcli


def main() -> int:
    script = str(Path(__file__).parent / "streamlit_app.py")
    sys.argv = ["streamlit", "run", script, *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())

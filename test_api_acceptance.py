from pathlib import Path
import runpy


def test_api_acceptance():
    runpy.run_path(str(Path(__file__).with_name("test_api.py")), run_name="__main__")

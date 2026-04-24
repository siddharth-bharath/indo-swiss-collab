import importlib.util
import os
import sys
import pytest


@pytest.fixture(scope="session")
def v1_client():
    """Load v1 Flask app and return a test client.

    Avoids module name collision by importing via importlib.util.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    v1_dir = os.path.join(repo_root, "search-application")

    # Save original cwd
    old_cwd = os.getcwd()
    os.chdir(v1_dir)

    try:
        # Import v1 app via importlib to avoid namespace collision
        app_path = os.path.join(v1_dir, "app.py")
        spec = importlib.util.spec_from_file_location("v1_search_app", app_path)
        v1_module = importlib.util.module_from_spec(spec)
        sys.modules["v1_search_app"] = v1_module
        spec.loader.exec_module(v1_module)

        client = v1_module.app.test_client()
        yield client
    finally:
        os.chdir(old_cwd)
        if "v1_search_app" in sys.modules:
            del sys.modules["v1_search_app"]


@pytest.fixture(scope="session")
def v2_client():
    """Load v2 FastAPI app and return a TestClient.

    Sets ISRD_DB_PATH env var before import.
    Uses importlib to avoid namespace collision with v1.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(repo_root, "search-application-v2", "dev_data", "indo_swiss_research_dev.duckdb")

    # Set env var BEFORE importing the app
    os.environ["ISRD_DB_PATH"] = db_path

    v2_dir = os.path.join(repo_root, "search-application-v2")
    old_sys_path = sys.path.copy()
    sys.path.insert(0, v2_dir)

    try:
        # Import v2 app's main module via importlib
        main_path = os.path.join(v2_dir, "app", "main.py")
        spec = importlib.util.spec_from_file_location("v2_search_app_main", main_path)
        v2_main = importlib.util.module_from_spec(spec)
        sys.modules["v2_search_app_main"] = v2_main
        spec.loader.exec_module(v2_main)

        from starlette.testclient import TestClient
        # Must use TestClient as a context manager so FastAPI's lifespan
        # (which loads autocomplete lists) actually fires.
        with TestClient(v2_main.app) as client:
            yield client
    finally:
        sys.path = old_sys_path
        if "v2_search_app_main" in sys.modules:
            del sys.modules["v2_search_app_main"]
        if "ISRD_DB_PATH" in os.environ:
            del os.environ["ISRD_DB_PATH"]

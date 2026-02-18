import shutil
import tempfile
import os


def create_workspace(repo_path: str) -> str:
    """
    Creates a unique temporary workspace and copies the repo into it.
    Returns the path to the workspace.
    """

    # Absolute path of original repo
    repo_path = os.path.abspath(repo_path)

    # Create unique temp directory
    workspace_path = tempfile.mkdtemp(prefix="opsguard_")

    # Copy repo contents into workspace
    shutil.copytree(repo_path, workspace_path, dirs_exist_ok=True)

    return workspace_path


def cleanup_workspace(workspace_path: str):
    """
    Deletes the workspace directory.
    """

    if os.path.exists(workspace_path):
        shutil.rmtree(workspace_path)

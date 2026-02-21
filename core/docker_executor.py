import subprocess
import os


def execute_python(workspace_path: str, script_name: str) -> dict:
    """
    Executes a Python script inside a Docker container.

    Returns:
        {
            "exit_code": int,
            "stdout": str,
            "stderr": str
        }
    """

    # Ensure absolute path
    workspace_path = os.path.abspath(workspace_path)

    # Build Docker command
    docker_command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace_path}:/app",
        "-w",
        "/app",
        "python:3.11-slim",
        "python",
        script_name
    ]

    # Execute Docker command
    result = subprocess.run(
        docker_command,
        capture_output=True,
        text=True
    )

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


def execute_pytest(workspace_path: str) -> dict:
    """
    Runs the pytest suite inside a Docker container.

    Returns:
        {
            "exit_code": int,   # 0 = all tests passed
            "stdout": str,
            "stderr": str
        }
    """

    workspace_path = os.path.abspath(workspace_path)

    docker_command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace_path}:/app",
        "-w",
        "/app",
        "python:3.11-slim",
        "bash",
        "-c",
        "pip install pytest --quiet && pytest"
    ]

    result = subprocess.run(
        docker_command,
        capture_output=True,
        text=True
    )

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }

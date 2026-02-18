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

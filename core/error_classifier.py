def classify_error(stderr: str) -> dict:
    """
    Classifies the error based on stderr output.

    Returns:
        {
            "type": "CODE_ERROR" or "INFRA_ERROR",
            "reason": str
        }
    """

    if not stderr:
        return {
            "type": "NO_ERROR",
            "reason": "No error detected."
        }

    stderr_lower = stderr.lower()

    # Infra-related keywords
    infra_keywords = [
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "rate limit",
        "timeout",
        "connection refused",
        "connectionerror",
        "network is unreachable",
        "ssl error",
        "credential",
        "access denied"
    ]

    for keyword in infra_keywords:
        if keyword in stderr_lower:
            return {
                "type": "INFRA_ERROR",
                "reason": f"Detected infrastructure-related keyword: {keyword}"
            }

    # If no infra keywords found, assume code error
    return {
        "type": "CODE_ERROR",
        "reason": "Detected Python exception (likely code issue)."
    }

"""Explicit deployment boundary; unknown modes fail closed."""
import os

VERSION = "4.9"

def mode():
    value = os.environ.get("MLB_ANALYTICS_MODE", "LOCAL").strip().upper()
    if value not in ("LOCAL", "CLOUD"):
        raise ValueError("MLB_ANALYTICS_MODE must be LOCAL or CLOUD")
    return value

def cloud():
    return mode() == "CLOUD"

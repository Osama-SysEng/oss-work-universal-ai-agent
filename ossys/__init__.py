"""oss-work OS (v1): independent local single system. No keys, no cloud."""

from ossys import config

OS_VERSION = config.OS_VERSION
OS_NAME = config.OS_NAME

__all__ = ["OS_NAME", "OS_VERSION", "config"]

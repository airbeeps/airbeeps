"""Airbeeps - Local-first, self-hosted AI assistant for chat and RAG"""

try:
    from ._version import __version__
except ImportError:
    try:
        from importlib.metadata import version

        __version__ = version("airbeeps")
    except ImportError:
        __version__ = "0.0.0.dev0+unknown"

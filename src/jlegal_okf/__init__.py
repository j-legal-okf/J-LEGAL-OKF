"""J-LEGAL-OKF public reference core (JORI Engine)."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .model import CrosswalkRelation, LegalNode, LegacyCrosswalk, NodeKind, RetrievalDocument, SCHEMA, SourceRef, Temporal

try:
    __version__ = _pkg_version("jlegal-okf")
except PackageNotFoundError:
    # Running from an uninstalled source tree (e.g. `PYTHONPATH=src`). This is
    # a distinct, recognizable string rather than a guess at a version, and it
    # never fails closed just because the package metadata is unavailable.
    __version__ = "0+unknown"

__all__ = ["LegalNode", "NodeKind", "SourceRef", "Temporal", "LegacyCrosswalk", "CrosswalkRelation", "RetrievalDocument", "SCHEMA", "__version__"]

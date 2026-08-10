"""Dependency failure types.

The baseline service does not handle any of these — an exception reaches the
client as a 500. Making the service behave sensibly when they are raised is the
work of Sprint 3.
"""


class DependencyError(RuntimeError):
    """Base class for anything the service depends on and does not control."""

    dependency = "unknown"


class ModelUnavailable(DependencyError):
    dependency = "model"


class RetrievalUnavailable(DependencyError):
    dependency = "retrieval"


class ToolUnavailable(DependencyError):
    dependency = "account_tool"

class AgentFrameworkError(RuntimeError):
    """Base error for agent framework failures."""


class ApprovalRequiredError(AgentFrameworkError):
    """Raised when a run must be approved before execution."""


class CapabilityViolationError(AgentFrameworkError):
    """Raised when a step attempts to use a tool outside its capability scope."""


class DelegationBlockedError(AgentFrameworkError):
    """Raised when delegation violates guardrails."""

"""Application-layer error types."""


class MindApplicationError(Exception):
    """Base error for the maintained application layer."""


class OwnerSelectorError(MindApplicationError):
    """Raised when an owner selector is invalid or conflicting."""


class MemoryNotFoundError(MindApplicationError):
    """Raised when a requested memory does not exist."""

    def __init__(self, memory_id: str) -> None:
        super().__init__(f"Memory '{memory_id}' was not found")
        self.memory_id = memory_id


class ChatModelProfileError(MindApplicationError):
    """Raised when a requested chat model profile is invalid."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"Chat model profile '{profile_id}' is not configured")
        self.profile_id = profile_id

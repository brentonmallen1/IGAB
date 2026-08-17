class IGABError(Exception):
    pass


class NotFoundError(IGABError):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} '{id}' not found")
        self.resource = resource
        self.id = id


class InvariantViolation(IGABError):
    pass


class AuthenticationError(IGABError):
    pass


class DuplicateError(IGABError):
    def __init__(self, resource: str, field: str, value: str):
        super().__init__(f"{resource} with {field}='{value}' already exists")


class ImportError(IGABError):
    pass


class UndoConflict(IGABError):
    """Raised when a change cannot be (re)undone: the entity has changed
    since, is reconciled, or the change was already undone."""

    def __init__(self, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.fields = fields or []

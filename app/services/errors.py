class ServiceError(Exception):
    """Expected workflow failure; the HTTP layer chooses a status code."""


class ResourceNotFound(ServiceError):
    pass


class InvalidInput(ServiceError):
    pass

from __future__ import annotations

from fastapi import Depends

from payments_processing.project.container import get_container


def resolve_depends[T](depends_type: type[T]) -> T:
    """Resolves a type from the shared container as a FastAPI dependency."""
    return Depends(lambda: get_container().resolve(depends_type))

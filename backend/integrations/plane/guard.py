"""Boundary enforcement: a task that Plane owns must not be edited in the PMO.

Plane is the system of record for a work item once it has been pushed. Allowing edits on both sides
is what produces the silent divergence the integration exists to avoid — and a pull would then
overwrite the local edit without a trace. So writes to a mirrored task are refused, with a message
that says where to make the change instead.
"""
from sqlalchemy.orm import Session

from backend.models import PlaneLink, PlaneProjectLink, Task


def plane_ownership(db: Session, task: Task) -> str | None:
    """Return an explanation when this task is Plane-owned, otherwise None."""
    link = db.query(PlaneLink).filter(PlaneLink.task_id == task.id).first()
    if link is None:
        return None
    project_link = (
        db.query(PlaneProjectLink)
        .filter(PlaneProjectLink.project_id == link.project_id)
        .first()
    )
    ref = f"#{link.plane_sequence_id}" if link.plane_sequence_id else link.plane_work_item_id[:8]
    where = (project_link.plane_project_name if project_link else "") or "Plane"
    return (
        f'This task is owned by Plane — work item {ref} in "{where}". '
        "Change it in Plane; the PMO picks the change up on the next sync."
    )

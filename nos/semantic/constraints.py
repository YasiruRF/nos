"""Registry of the ``@constraint`` annotations NOS understands.

One table drives the analyzer's checks (known name, allowed targets,
argument count).  The code generators consume only constraints that are
listed here, so an annotation that is not in the registry is never silently
dropped without a warning.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

PARAMETER = "parameter"
FIELD = "field"
ARGUMENT = "argument"
SUBSCRIPTION = "subscription"
PUBLICATION = "publication"
SERVICE = "service"
ACTION = "action"
INSTANCE = "instance"
COMPONENT = "component"
TRANSITION = "transition"

VALUES = frozenset({PARAMETER, FIELD, ARGUMENT})
ANY_TARGET: Optional[FrozenSet[str]] = None


@dataclass(frozen=True)
class ConstraintSpec:
    """What a constraint may be attached to and how many arguments it takes."""
    name: str
    targets: Optional[FrozenSet[str]]  # None: any declaration
    min_args: int = 0
    max_args: Optional[int] = None  # None: unbounded


def _spec(name, targets=ANY_TARGET, min_args=0, max_args=None):
    return ConstraintSpec(name, frozenset(targets) if targets is not None else None,
                          min_args, max_args)


CONSTRAINTS: Dict[str, ConstraintSpec] = {s.name: s for s in [
    # value constraints
    _spec("range", VALUES, 2, 2),
    _spec("one_of", VALUES, 1),
    _spec("min", VALUES, 1, 1),
    _spec("max", VALUES, 1, 1),
    _spec("pattern", VALUES, 1, 1),
    _spec("description", ANY_TARGET, 1, 1),
    _spec("dynamic", {PARAMETER}, 0, 1),
    _spec("computed", VALUES, 0, 1),
    _spec("validate", VALUES, 0, 1),
    # communication
    _spec("topic", {SUBSCRIPTION, PUBLICATION}, 1, 1),
    _spec("service", {SERVICE}, 1, 1),
    _spec("qos", {SUBSCRIPTION, PUBLICATION}),
    _spec("client", {SERVICE, ACTION}, 0, 0),
    _spec("reentrant", {SUBSCRIPTION, PUBLICATION, SERVICE, ACTION}, 0, 0),
    # launch / lifecycle
    _spec("when", ANY_TARGET, 0, 1),
    _spec("delay", {TRANSITION}, 0, 1),
    _spec("namespace", ANY_TARGET, 0, 1),
    _spec("load_component", ANY_TARGET, 0, 0),
]}

QOS_VALUES = {
    "reliability": {"reliable", "best_effort"},
    "durability": {"volatile", "transient_local"},
    "history": {"keep_last", "keep_all"},
}
QOS_KEYS = frozenset(QOS_VALUES) | {"depth"}

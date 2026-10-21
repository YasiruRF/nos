"""QoS profile utilities for NOS runtime.

Provides convenient creation of common QoS profiles.
"""

from typing import Optional

from rclpy.duration import Duration
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    LivelinessPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

_RELIABILITY = {"reliable": ReliabilityPolicy.RELIABLE, "best_effort": ReliabilityPolicy.BEST_EFFORT}
_DURABILITY = {"volatile": DurabilityPolicy.VOLATILE, "transient_local": DurabilityPolicy.TRANSIENT_LOCAL}
_HISTORY = {"keep_last": HistoryPolicy.KEEP_LAST, "keep_all": HistoryPolicy.KEEP_ALL}
_LIVELINESS = {"automatic": LivelinessPolicy.AUTOMATIC, "manual_by_topic": LivelinessPolicy.MANUAL_BY_TOPIC}


def _lookup(kind: str, table: dict, value: str):
    try:
        return table[value]
    except (KeyError, TypeError):
        raise ValueError(f"invalid QoS {kind} {value!r}; expected one of: {', '.join(sorted(table))}") from None


def create_qos_profile(
    reliability: str = "reliable",
    durability: Optional[str] = None,
    history: str = "keep_last",
    depth: int = 10,
    lifespan: Optional[float] = None,
    deadline: Optional[float] = None,
    liveliness: Optional[str] = None,
    liveliness_lease_duration: Optional[float] = None,
) -> QoSProfile:
    """Create a QoS profile with common settings.

    Args:
        reliability: 'reliable' or 'best_effort'
        durability: 'volatile' (default) or 'transient_local'
        history: 'keep_last' or 'keep_all'
        depth: History depth (a positive integer)
        lifespan: Message lifespan in seconds
        deadline: Expected topic deadline in seconds
        liveliness: 'automatic' or 'manual_by_topic'
        liveliness_lease_duration: Liveliness lease duration in seconds

    Returns:
        Configured QoSProfile

    Raises:
        ValueError: for an unknown policy name or a non-positive depth
    """
    reliability_policy = _lookup("reliability", _RELIABILITY, reliability)
    durability_policy = _lookup("durability", _DURABILITY, durability or "volatile")
    history_policy = _lookup("history", _HISTORY, history)

    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError(f"invalid QoS depth {depth!r}; expected a positive integer")

    qos = QoSProfile(reliability=reliability_policy, durability=durability_policy, history=history_policy, depth=depth)

    if lifespan is not None:
        qos.lifespan = Duration(seconds=lifespan)

    if deadline is not None:
        qos.deadline = Duration(seconds=deadline)

    if liveliness is not None:
        qos.liveliness = _lookup("liveliness", _LIVELINESS, liveliness)

    if liveliness_lease_duration is not None:
        qos.liveliness_lease_duration = Duration(seconds=liveliness_lease_duration)

    return qos


def reliable_qos(depth: int = 10) -> QoSProfile:
    """Create a reliable QoS profile."""
    return create_qos_profile(reliability="reliable", depth=depth)


def best_effort_qos(depth: int = 10) -> QoSProfile:
    """Create a best effort QoS profile."""
    return create_qos_profile(reliability="best_effort", depth=depth)


def sensor_qos(depth: int = 10) -> QoSProfile:
    """Create a sensor data QoS profile (best effort)."""
    return create_qos_profile(reliability="best_effort", durability="volatile", depth=depth)


def parameter_qos() -> QoSProfile:
    """Create a parameter service QoS profile."""
    return create_qos_profile(reliability="reliable", durability="volatile", depth=1)


def latching_qos() -> QoSProfile:
    """Create a latching QoS profile (transient_local)."""
    return create_qos_profile(reliability="reliable", durability="transient_local", depth=1)

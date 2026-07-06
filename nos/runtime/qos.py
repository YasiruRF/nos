"""QoS profile utilities for NOS runtime.

Provides convenient creation of common QoS profiles.
"""

from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from typing import Optional


def create_qos_profile(
    reliability: str = "reliable",
    durability: Optional[str] = None,
    history: str = "keep_last",
    depth: int = 10,
    lifespan: Optional[float] = None,
    deadline: Optional[float] = None,
    liveliness: Optional[str] = None,
    liveliness_lease_duration: Optional[float] = None
) -> QoSProfile:
    """Create a QoS profile with common settings.

    Args:
        reliability: 'reliable' or 'best_effort'
        durability: 'volatile' or 'transient_local'
        history: 'keep_last' or 'keep_all'
        depth: History depth
        lifespan: Message lifespan in seconds
        deadline: Expected topic deadline in seconds
        liveliness: 'automatic' or 'manual_by_topic'
        liveliness_lease_duration: Liveliness lease duration in seconds

    Returns:
        Configured QoSProfile
    """
    reliability_policy = ReliabilityPolicy.RELIABLE if reliability == "reliable" \
        else ReliabilityPolicy.BEST_EFFORT

    durability_policy = DurabilityPolicy.TRANSIENT_LOCAL if durability == "transient_local" \
        else DurabilityPolicy.VOLATILE

    history_policy = HistoryPolicy.KEEP_ALL if history == "keep_all" \
        else HistoryPolicy.KEEP_LAST

    qos = QoSProfile(
        reliability=reliability_policy,
        durability=durability_policy,
        history=history_policy,
        depth=depth
    )

    if lifespan is not None:
        from rclpy.duration import Duration
        qos.lifespan = Duration(seconds=lifespan)

    if deadline is not None:
        from rclpy.duration import Duration
        qos.deadline = Duration(seconds=deadline)

    if liveliness is not None:
        from rclpy.qos import LivelinessPolicy
        qos.liveliness = LivelinessPolicy.AUTOMATIC if liveliness == "automatic" \
            else LivelinessPolicy.MANUAL_BY_TOPIC

    if liveliness_lease_duration is not None:
        from rclpy.duration import Duration
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
    return create_qos_profile(
        reliability="best_effort",
        durability="volatile",
        depth=depth
    )


def parameter_qos() -> QoSProfile:
    """Create a parameter service QoS profile."""
    return create_qos_profile(
        reliability="reliable",
        durability="volatile",
        depth=1
    )


def latching_qos() -> QoSProfile:
    """Create a latching QoS profile (transient_local)."""
    return create_qos_profile(
        reliability="reliable",
        durability="transient_local",
        depth=1
    )

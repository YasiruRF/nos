"""Decorators for NOS runtime.

Provides decorators for declarative definition of parameters,
subscriptions, publishers, services, and actions.
"""

from typing import Any, Callable, Optional, Type
from functools import wraps


def parameter(
    name: str,
    default_value: Any = None,
    description: str = "",
    constraints: Optional[dict] = None
):
    """Decorator to declare a parameter.

    Args:
        name: Parameter name
        default_value: Default value
        description: Parameter description
        constraints: Validation constraints (min, max, etc.)
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_flow_parameters'):
            func._flow_parameters = []
        func._flow_parameters.append({
            'name': name,
            'default': default_value,
            'description': description,
            'constraints': constraints or {}
        })
        return func
    return decorator


def subscription(
    topic: str,
    msg_type: Type,
    qos_profile: Optional[Any] = None,
    callback_name: Optional[str] = None
):
    """Decorator to declare a subscription.

    Args:
        topic: Topic name
        msg_type: Message type class
        qos_profile: QoS profile
        callback_name: Name of callback method
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_flow_subscriptions'):
            func._flow_subscriptions = []
        func._flow_subscriptions.append({
            'topic': topic,
            'msg_type': msg_type,
            'qos': qos_profile,
            'callback': callback_name or func.__name__
        })
        return func
    return decorator


def publisher(
    topic: str,
    msg_type: Type,
    qos_profile: Optional[Any] = None
):
    """Decorator to declare a publisher.

    Args:
        topic: Topic name
        msg_type: Message type class
        qos_profile: QoS profile
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_flow_publishers'):
            func._flow_publishers = []
        func._flow_publishers.append({
            'topic': topic,
            'msg_type': msg_type,
            'qos': qos_profile
        })
        return func
    return decorator


def service(
    service_name: str,
    srv_type: Type,
    callback_name: Optional[str] = None
):
    """Decorator to declare a service.

    Args:
        service_name: Service name
        srv_type: Service type class
        callback_name: Name of callback method
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_flow_services'):
            func._flow_services = []
        func._flow_services.append({
            'name': service_name,
            'srv_type': srv_type,
            'callback': callback_name or func.__name__
        })
        return func
    return decorator


def action(
    action_name: str,
    action_type: Type,
    callback_name: Optional[str] = None
):
    """Decorator to declare an action.

    Args:
        action_name: Action name
        action_type: Action type class
        callback_name: Name of callback method
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_flow_actions'):
            func._flow_actions = []
        func._flow_actions.append({
            'name': action_name,
            'action_type': action_type,
            'callback': callback_name or func.__name__
        })
        return func
    return decorator

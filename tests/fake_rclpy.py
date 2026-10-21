"""A tiny stand-in for rclpy so runtime and generated code can be imported and run in CI.

``install(monkeypatch)`` registers fake ``rclpy`` modules (and ``<pkg>.msg/srv/action``
modules whose attributes are generated message classes) and forgets any
``nos.runtime`` import so it is re-imported against the fakes.
"""

import enum
import sys
import types
from typing import Dict, List

INTERFACE_PACKAGES = (
    "std_msgs",
    "geometry_msgs",
    "sensor_msgs",
    "std_srvs",
    "example_interfaces",
    "action_tutorials_interfaces",
    "nav2_msgs",
    "rcl_interfaces",
    "x_msgs",
    "y_msgs",
)


class FakeLogger:
    def __init__(self):
        self.records: List[tuple] = []

    def _log(self, level, msg):
        self.records.append((level, msg))

    def debug(self, msg):
        self._log("debug", msg)

    def info(self, msg):
        self._log("info", msg)

    def warn(self, msg):
        self._log("warn", msg)

    def error(self, msg):
        self._log("error", msg)


class FakeParameter:
    def __init__(self, value):
        self.value = value


class FakeNode:
    def __init__(self, node_name, **kwargs):
        self._node_name = node_name
        self._logger = FakeLogger()
        self._parameters: Dict[str, object] = {}
        self.entities: List[tuple] = []
        self.destroyed: List[tuple] = []

    # identity / logging
    def get_name(self):
        return self._node_name

    def get_namespace(self):
        return "/"

    def get_fully_qualified_name(self):
        return "/" + self._node_name

    def get_logger(self):
        return self._logger

    # parameters
    def declare_parameter(self, name, value=None, descriptor=None):
        self._parameters[name] = value
        return FakeParameter(value)

    def get_parameter(self, name):
        return FakeParameter(self._parameters[name])

    # communications
    def _create(self, kind, *args, **kwargs):
        entity = types.SimpleNamespace(kind=kind, args=args, kwargs=kwargs)
        self.entities.append((kind, entity))
        return entity

    def create_subscription(self, *a, **k):
        return self._create("subscription", *a, **k)

    def create_publisher(self, *a, **k):
        return self._create("publisher", *a, **k)

    def create_service(self, *a, **k):
        return self._create("service", *a, **k)

    def create_client(self, *a, **k):
        return self._create("client", *a, **k)

    def _destroy(self, kind, entity):
        self.destroyed.append((kind, entity))
        return True

    def destroy_subscription(self, e):
        return self._destroy("subscription", e)

    def destroy_publisher(self, e):
        return self._destroy("publisher", e)

    def destroy_service(self, e):
        return self._destroy("service", e)

    def destroy_client(self, e):
        return self._destroy("client", e)

    def destroy_node(self):
        pass


class TransitionCallbackReturn(enum.Enum):
    SUCCESS = 0
    FAILURE = 1
    ERROR = 2


class FakeState:
    pass


class FakeLifecycleNode(FakeNode):
    def create_lifecycle_publisher(self, *a, **k):
        return self._create("lifecycle_publisher", *a, **k)

    def on_configure(self, state):
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state):
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state):
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state):
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state):
        return TransitionCallbackReturn.SUCCESS

    def destroy_publisher(self, e):
        return self._destroy("publisher", e)


class _Policy(enum.Enum):
    pass


def _enum(name, *members):
    return enum.Enum(name, {m: i for i, m in enumerate(members)})


ReliabilityPolicy = _enum("ReliabilityPolicy", "RELIABLE", "BEST_EFFORT")
DurabilityPolicy = _enum("DurabilityPolicy", "VOLATILE", "TRANSIENT_LOCAL")
HistoryPolicy = _enum("HistoryPolicy", "KEEP_LAST", "KEEP_ALL")
LivelinessPolicy = _enum("LivelinessPolicy", "AUTOMATIC", "MANUAL_BY_TOPIC")


class QoSProfile:
    def __init__(self, **kwargs):
        self.lifespan = self.deadline = self.liveliness = self.liveliness_lease_duration = None
        self.__dict__.update(kwargs)


class Duration:
    def __init__(self, seconds=0, nanoseconds=0, milliseconds=0, microseconds=0):
        self.seconds = seconds
        self.nanoseconds = nanoseconds
        self.milliseconds = milliseconds
        self.microseconds = microseconds


class Executor:
    def __init__(self):
        self.nodes = []

    def add_node(self, node):
        self.nodes.append(node)

    def spin(self):
        pass

    def shutdown(self):
        pass


class _Anything(types.ModuleType):
    """Module whose attributes are generated on demand (messages, services, actions, ...)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs

        cls = type(name, (), {"__module__": self.__name__, "__init__": __init__})
        setattr(self, name, cls)
        return cls


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


def install(monkeypatch):
    modules = {
        "rclpy": _module("rclpy", init=lambda args=None: None, shutdown=lambda: None, ok=lambda: True),
        "rclpy.node": _module("rclpy.node", Node=FakeNode),
        "rclpy.lifecycle": _module(
            "rclpy.lifecycle",
            LifecycleNode=FakeLifecycleNode,
            State=FakeState,
            TransitionCallbackReturn=TransitionCallbackReturn,
        ),
        "rclpy.qos": _module(
            "rclpy.qos",
            QoSProfile=QoSProfile,
            ReliabilityPolicy=ReliabilityPolicy,
            DurabilityPolicy=DurabilityPolicy,
            HistoryPolicy=HistoryPolicy,
            LivelinessPolicy=LivelinessPolicy,
        ),
        "rclpy.duration": _module("rclpy.duration", Duration=Duration),
        "rclpy.time": _module("rclpy.time", Time=type("Time", (), {})),
        "rclpy.executors": _module("rclpy.executors", SingleThreadedExecutor=Executor, MultiThreadedExecutor=Executor),
        "rclpy.callback_groups": _module(
            "rclpy.callback_groups", ReentrantCallbackGroup=type("ReentrantCallbackGroup", (), {})
        ),
        "rclpy.action": _Anything("rclpy.action"),
    }
    for pkg in INTERFACE_PACKAGES:
        modules[pkg] = _Anything(pkg)
        for sub in ("msg", "srv", "action"):
            modules[f"{pkg}.{sub}"] = _Anything(f"{pkg}.{sub}")

    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    for name in [n for n in sys.modules if n == "nos.runtime" or n.startswith("nos.runtime.")]:
        monkeypatch.delitem(sys.modules, name)
    return types.SimpleNamespace(
        **{"modules": modules, "FakeNode": FakeNode, "TransitionCallbackReturn": TransitionCallbackReturn}
    )

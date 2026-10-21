"""Base node classes for NOS generated code.

Generated nodes subclass :class:`NOSNode` (or :class:`NOSLifecycleNode` for
``lifecycle: managed``) and fill in parameters, communications and the user's
callbacks.
"""

from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.node import Node


class _LoggingMixin:
    """``log_*`` helpers shared by both node kinds.

    Keyword arguments are appended as ``key=value`` pairs, e.g.
    ``self.log_info("scan received", points=len(msg.ranges))``.
    """

    def _format_log(self, msg: str, context: dict) -> str:
        if not context:
            return msg
        return f"{msg} | " + " ".join(f"{k}={v!r}" for k, v in context.items())

    def log_debug(self, msg: str, **context) -> None:
        self.get_logger().debug(self._format_log(msg, context))

    def log_info(self, msg: str, **context) -> None:
        self.get_logger().info(self._format_log(msg, context))

    def log_warn(self, msg: str, **context) -> None:
        self.get_logger().warn(self._format_log(msg, context))

    def log_error(self, msg: str, **context) -> None:
        self.get_logger().error(self._format_log(msg, context))


class NOSNode(_LoggingMixin, Node):
    """Base class for NOS-generated ROS2 nodes."""

    def on_init(self) -> None:
        """Called at the end of ``__init__``.

        Overridden by the code generated from ``on_init -> { ... }``.
        """

    def on_shutdown(self) -> None:
        """Called by the generated ``main()`` before the node is destroyed.

        Overridden by the code generated from ``on_shutdown -> { ... }``.
        """


class NOSLifecycleNode(_LoggingMixin, LifecycleNode):
    """Base class for NOS-generated lifecycle nodes (``lifecycle: managed``).

    Generated subclasses create their publishers, subscriptions, services and
    actions in ``on_configure`` and destroy them in ``on_cleanup``.
    """

    def on_init(self) -> None:
        """Called at the end of ``__init__``, before configuration."""

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """Configure the node."""
        self.log_info("Node configured")
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """Activate the node (and its lifecycle publishers)."""
        result = super().on_activate(state)
        self.log_info("Node activated")
        return result

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """Deactivate the node (and its lifecycle publishers)."""
        result = super().on_deactivate(state)
        self.log_info("Node deactivated")
        return result

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """Cleanup the node."""
        self.log_info("Node cleaned up")
        return TransitionCallbackReturn.SUCCESS

    def on_nos_shutdown(self) -> None:
        """User shutdown hook, overridden by the code generated from ``on_shutdown ->``.

        It has a different name from ``on_shutdown`` because ROS calls that one
        with the lifecycle ``state`` argument.
        """

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """Shutdown transition: run the user hook."""
        self.on_nos_shutdown()
        self.log_info("Node shutting down")
        return TransitionCallbackReturn.SUCCESS

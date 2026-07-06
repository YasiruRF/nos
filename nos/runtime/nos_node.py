"""Base node classes for NOS generated code.

Provides enhanced functionality on top of standard ROS2 nodes.
"""

from typing import Optional, Callable, Any
import rclpy
from rclpy.node import Node
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn
from rclpy.lifecycle import State


class NOSNode(Node):
    """Base class for NOS-generated ROS2 nodes.

    Extends standard ROS2 Node with NOS-specific features
    like automatic parameter validation and enhanced logging.
    """

    def __init__(self, node_name: str, **kwargs):
        super().__init__(node_name, **kwargs)
        self._nos_initialized = False

    def on_init(self) -> None:
        """Called after node initialization.

        Override in subclass to perform initialization.
        """
        pass

    def on_shutdown(self) -> None:
        """Called before node shutdown.

        Override in subclass to perform cleanup.
        """
        pass

    def get_logger_context(self) -> dict:
        """Get logging context with node information."""
        return {
            'node_name': self.get_name(),
            'node_namespace': self.get_namespace(),
            'fully_qualified_name': self.get_fully_qualified_name()
        }

    def log_debug(self, msg: str, **kwargs) -> None:
        """Log debug message with context."""
        context = self.get_logger_context()
        context.update(kwargs)
        self.get_logger().debug(f"{msg} | context={context}")

    def log_info(self, msg: str, **kwargs) -> None:
        """Log info message with context."""
        context = self.get_logger_context()
        context.update(kwargs)
        self.get_logger().info(f"{msg} | context={context}")

    def log_warn(self, msg: str, **kwargs) -> None:
        """Log warning message with context."""
        context = self.get_logger_context()
        context.update(kwargs)
        self.get_logger().warn(f"{msg} | context={context}")

    def log_error(self, msg: str, **kwargs) -> None:
        """Log error message with context."""
        context = self.get_logger_context()
        context.update(kwargs)
        self.get_logger().error(f"{msg} | context={context}")


class NOSLifecycleNode(LifecycleNode):
    """Base class for NOS-generated lifecycle nodes.

    Extends standard ROS2 LifecycleNode with NOS-specific
    features and simplified lifecycle management.
    """

    def __init__(self, node_name: str, **kwargs):
        super().__init__(node_name, **kwargs)
        self._nos_configured = False

    def on_init(self) -> None:
        """Called after node creation, before configuration.

        Override in subclass to perform initialization.
        """
        pass

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """Configure the node."""
        self._nos_configured = True
        self.log_info("Node configured")
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """Activate the node."""
        self.log_info("Node activated")
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """Deactivate the node."""
        self.log_info("Node deactivated")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """Cleanup the node."""
        self.on_shutdown()
        self.log_info("Node cleaned up")
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State = None) -> TransitionCallbackReturn:
        """Shutdown the node."""
        self.log_info("Node shutting down")
        return TransitionCallbackReturn.SUCCESS

    def log_info(self, msg: str) -> None:
        """Log info message."""
        self.get_logger().info(msg)

    def log_warn(self, msg: str) -> None:
        """Log warning message."""
        self.get_logger().warn(msg)

    def log_error(self, msg: str) -> None:
        """Log error message."""
        self.get_logger().error(msg)

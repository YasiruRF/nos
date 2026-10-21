"""Integration tests for callback syntax and event handling."""

import pytest

from nos.compiler.pipeline import CompilerPipeline


def test_callback_syntax_integration():
    """Test various callback syntaxes including standard and custom events."""
    pipeline = CompilerPipeline()

    nos_source = """
package test_callbacks

node CallbackNode {
    parameters {
        threshold: float = 0.5
    }

    subscriptions {
        data: std_msgs::Float32 @topic("/data")
    }

    on_init -> {
        self.get_logger().info("Initializing node")
    }

    on_shutdown -> {
        self.get_logger().info("Shutting down node")
    }

    on_parameter_change(threshold: float) -> {
        self.get_logger().info(f"Threshold changed to {threshold}")
    }

    on on_data_received(msg: std_msgs::Float32) -> {
        if msg.data > self.threshold:
            self.get_logger().info("Threshold exceeded!")
    }

    on my_custom_event(value: int) -> {
        self.get_logger().info(f"Custom event received with value: {value}")
    }
}
"""
    result = pipeline.compile_string(nos_source, "test_callbacks.node")

    assert result.success, f"Compilation failed: {result.errors}"
    assert "callback_node_node.py" in result.files

    code = result.files["callback_node_node.py"]

    # Check for callback methods
    assert "def on_init(self):" in code
    assert "def on_shutdown(self):" in code
    assert "def on_parameter_change(self, threshold: float):" in code
    assert "def on_data_received(self, msg: Float32):" in code
    assert "def my_custom_event(self, value: int):" in code

    # Check for security wrapping/try-except
    assert "try:" in code
    assert "except Exception as e:" in code
    assert 'self.get_logger().info("Initializing node")' in code


CALLBACKS = """package demo
node Cb {
    on_init -> {
        self.ready = True
    }
    on_shutdown -> {
        self.get_logger().info("bye")
    }
    on tick(count: int, ratio: float, scan: sensor_msgs::LaserScan) -> {
        total = 0
        for i in range(count):
            total += i

        self.get_logger().info(f"{total} {ratio}")
    }
    on_parameter_change(name: string) -> {
        pass
    }
}
"""


def _compile():
    result = CompilerPipeline().compile_string(CALLBACKS, "cb.node")
    assert result.success, result.errors
    return result


def test_callbacks_parse_into_the_ast():
    callbacks = {cb.event: cb for cb in _compile().ast.declarations[-1].callbacks}
    assert set(callbacks) == {"on_init", "on_shutdown", "tick", "on_parameter_change"}
    assert [p.name for p in callbacks["tick"].parameters] == ["count", "ratio", "scan"]
    assert callbacks["on_init"].parameters == []


def test_callback_parameter_types_are_typed_in_generated_code():
    code = _compile().files["cb_node.py"]
    assert "def tick(self, count: int, ratio: float, scan: LaserScan):" in code
    assert "from sensor_msgs.msg import LaserScan" in code
    assert "def on_parameter_change(self, name: str):" in code


def test_lifecycle_callbacks_are_generated():
    code = _compile().files["cb_node.py"]
    assert "def on_init(self):" in code
    assert "def on_shutdown(self):" in code
    assert "self.on_init()" in code


def test_multiline_callback_body_is_preserved():
    code = _compile().files["cb_node.py"]
    assert "            for i in range(count):\n                total += i\n\n            self.get_logger()" in code


if __name__ == "__main__":
    pytest.main([__file__])

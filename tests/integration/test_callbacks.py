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
    assert "self.get_logger().info(\"Initializing node\")" in code

if __name__ == "__main__":
    pytest.main([__file__])

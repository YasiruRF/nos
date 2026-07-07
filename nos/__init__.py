"""NOS (Node Orchestration System) - A declarative DSL for ROS2 robotics.

NOS Phase 1 (Core Language) provides:
- ANTLR4 grammar definitions for .nos, .node, and .interface files
- AST representation and semantic analysis
- Python code generator for ROS2 nodes
- Launch file transpiler
"""

__version__ = "0.1.6"
__all__ = ["compiler", "ast", "semantic", "codegen"]

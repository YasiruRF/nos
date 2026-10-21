"""Naming helpers shared by the generators and the compiler pipeline.

Keeping ROS package names and executable names derived from one place
guarantees that launch files, ``setup.py`` entry points and generated
module names cannot drift apart.
"""

import re
from typing import Optional

from ..ast import nodes


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def sanitize_package_name(candidate: str) -> str:
    """Turn arbitrary text into a valid ROS 2 package name."""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', candidate).lower()
    if not sanitized:
        return "nos_generated"
    if sanitized[0].isdigit():
        sanitized = f"nos_{sanitized}"
    return sanitized


def ros_package_name(ast: Optional[nodes.ASTNode]) -> str:
    """Name of the ROS 2 package generated for ``ast``."""
    candidate = "nos_generated"

    if isinstance(ast, nodes.File):
        if ast.package and ast.package.name:
            candidate = ast.package.name
        elif ast.declarations:
            first_decl = ast.declarations[0]
            if getattr(first_decl, 'name', None):
                candidate = first_decl.name
    elif ast is not None and getattr(ast, 'name', None):
        candidate = ast.name

    return sanitize_package_name(candidate)


def node_module_name(node_type: str) -> str:
    """Module (and console-script) name generated for a node type."""
    return f"{camel_to_snake(node_type)}_node"


def launch_module_name(launch_name: str) -> str:
    """File stem generated for a launch declaration."""
    return f"{camel_to_snake(launch_name)}_launch"

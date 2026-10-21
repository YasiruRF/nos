"""Base AST visitor implementation.

Provides a default visitor that traverses the AST without action.
Subclass to implement specific AST transformations or analysis.
"""

from typing import Any, List

from . import nodes


class ASTVisitor:
    """Base visitor class for AST traversal.

    Subclass and override specific visit_* methods to customize behavior.
    The default behavior is to recursively visit child nodes.
    """

    def visit(self, node: nodes.ASTNode) -> Any:
        """Visit a node."""
        return node.accept(self)

    def visit_default(self, node: nodes.ASTNode) -> Any:
        """Default visitor for unhandled node types."""
        return None

    def visit_children(self, node: nodes.ASTNode) -> List[Any]:
        """Visit all child nodes and return results."""
        results = []
        for field_name, field_value in node.__dict__.items():
            if field_name == "location":
                continue
            if isinstance(field_value, nodes.ASTNode):
                results.append(self.visit(field_value))
            elif isinstance(field_value, list):
                for item in field_value:
                    if isinstance(item, nodes.ASTNode):
                        results.append(self.visit(item))
        return results

    # Program structure
    def visit_File(self, node: nodes.File) -> Any:
        return self.visit_children(node)

    def visit_PackageDecl(self, node: nodes.PackageDecl) -> Any:
        return self.visit_children(node)

    def visit_ImportDecl(self, node: nodes.ImportDecl) -> Any:
        return self.visit_children(node)

    # Types
    def visit_PrimitiveType(self, node: nodes.PrimitiveType) -> Any:
        return self.visit_children(node)

    def visit_QualifiedType(self, node: nodes.QualifiedType) -> Any:
        return self.visit_children(node)

    def visit_ListType(self, node: nodes.ListType) -> Any:
        return self.visit(node.element_type) if node.element_type else None

    def visit_StructType(self, node: nodes.StructType) -> Any:
        return self.visit_children(node)

    def visit_FieldDecl(self, node: nodes.FieldDecl) -> Any:
        return self.visit_children(node)

    # Expressions
    def visit_LiteralExpression(self, node: nodes.LiteralExpression) -> Any:
        return self.visit_children(node)

    def visit_IdentifierExpression(self, node: nodes.IdentifierExpression) -> Any:
        return self.visit_children(node)

    def visit_QualifiedIdentifierExpression(self, node: nodes.QualifiedIdentifierExpression) -> Any:
        return self.visit_children(node)

    def visit_MemberAccessExpression(self, node: nodes.MemberAccessExpression) -> Any:
        return self.visit_children(node)

    def visit_IndexExpression(self, node: nodes.IndexExpression) -> Any:
        return self.visit_children(node)

    def visit_CallExpression(self, node: nodes.CallExpression) -> Any:
        return self.visit_children(node)

    def visit_InterpolatedExpression(self, node: nodes.InterpolatedExpression) -> Any:
        return self.visit(node.inner) if node.inner else None

    def visit_BinaryExpression(self, node: nodes.BinaryExpression) -> Any:
        return self.visit_children(node)

    def visit_UnaryExpression(self, node: nodes.UnaryExpression) -> Any:
        return self.visit_children(node)

    def visit_ArrayExpression(self, node: nodes.ArrayExpression) -> Any:
        return self.visit_children(node)

    def visit_StructInitializerExpression(self, node: nodes.StructInitializerExpression) -> Any:
        return self.visit_children(node)

    # Constraints
    def visit_Constraint(self, node: nodes.Constraint) -> Any:
        return self.visit_children(node)

    # Node declarations
    def visit_ParameterDecl(self, node: nodes.ParameterDecl) -> Any:
        return self.visit_children(node)

    def visit_SubscriptionDecl(self, node: nodes.SubscriptionDecl) -> Any:
        return self.visit_children(node)

    def visit_PublicationDecl(self, node: nodes.PublicationDecl) -> Any:
        return self.visit_children(node)

    def visit_ServiceDecl(self, node: nodes.ServiceDecl) -> Any:
        return self.visit_children(node)

    def visit_ActionDecl(self, node: nodes.ActionDecl) -> Any:
        return self.visit_children(node)

    def visit_QoSConfig(self, node: nodes.QoSConfig) -> Any:
        return self.visit_children(node)

    def visit_LifecycleDecl(self, node: nodes.LifecycleDecl) -> Any:
        return self.visit_children(node)

    def visit_ComponentDecl(self, node: nodes.ComponentDecl) -> Any:
        return self.visit_children(node)

    def visit_CallbackDecl(self, node: nodes.CallbackDecl) -> Any:
        return self.visit_children(node)

    def visit_NodeDecl(self, node: nodes.NodeDecl) -> Any:
        return self.visit_children(node)

    # Launch declarations
    def visit_ArgumentDecl(self, node: nodes.ArgumentDecl) -> Any:
        return self.visit_children(node)

    def visit_NodeInstance(self, node: nodes.NodeInstance) -> Any:
        return self.visit_children(node)

    def visit_GroupDecl(self, node: nodes.GroupDecl) -> Any:
        return self.visit_children(node)

    def visit_ComponentInstance(self, node: nodes.ComponentInstance) -> Any:
        return self.visit_children(node)

    def visit_ContainerDecl(self, node: nodes.ContainerDecl) -> Any:
        return self.visit_children(node)

    def visit_IncludeDecl(self, node: nodes.IncludeDecl) -> Any:
        return self.visit_children(node)

    def visit_TransitionDecl(self, node: nodes.TransitionDecl) -> Any:
        return self.visit_children(node)

    def visit_LifecycleManagerDecl(self, node: nodes.LifecycleManagerDecl) -> Any:
        return self.visit_children(node)

    def visit_EventAction(self, node: nodes.EventAction) -> Any:
        return self.visit_children(node)

    def visit_LaunchEventDecl(self, node: nodes.LaunchEventDecl) -> Any:
        return self.visit_children(node)

    def visit_LaunchDecl(self, node: nodes.LaunchDecl) -> Any:
        return self.visit_children(node)

    # Interface declarations
    def visit_MessageDecl(self, node: nodes.MessageDecl) -> Any:
        return self.visit_children(node)

    def visit_ServiceInterfaceDecl(self, node: nodes.ServiceInterfaceDecl) -> Any:
        return self.visit_children(node)

    def visit_ActionInterfaceDecl(self, node: nodes.ActionInterfaceDecl) -> Any:
        return self.visit_children(node)

    def visit_InterfaceDecl(self, node: nodes.InterfaceDecl) -> Any:
        return self.visit_children(node)

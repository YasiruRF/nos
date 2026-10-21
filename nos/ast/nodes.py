"""AST node definitions for NOS.

All AST nodes are dataclasses with source location information.
This enables accurate error reporting and debugging.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum, auto


@dataclass
class SourceLocation:
    """Source code location for error reporting."""
    line: int
    column: int
    file: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    location: SourceLocation

    def accept(self, visitor: 'ASTVisitor') -> Any:
        """Visitor pattern accept method."""
        method_name = f'visit_{self.__class__.__name__}'
        method = getattr(visitor, method_name, visitor.visit_default)
        return method(self)


# =============================================================================
# Program Structure
# =============================================================================

@dataclass
class PackageDecl(ASTNode):
    """Package declaration: package robot_navigation version '1.0.0'"""
    name: str
    version: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ImportDecl(ASTNode):
    """Import declaration: import nav2::components as nav"""
    qualified_name: str
    alias: Optional[str] = None


@dataclass
class File(ASTNode):
    """Root node for a NOS file."""
    package: Optional[PackageDecl]
    imports: List[ImportDecl] = field(default_factory=list)
    declarations: List[ASTNode] = field(default_factory=list)


# =============================================================================
# Type System
# =============================================================================

class PrimitiveTypeKind(Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    DOUBLE = "double"
    STRING = "string"
    DURATION = "duration"
    TIME = "time"


@dataclass
class Type(ASTNode):
    """Base class for all types."""
    pass


@dataclass
class PrimitiveType(Type):
    """Primitive type: bool, int, float, etc."""
    kind: PrimitiveTypeKind


@dataclass
class QualifiedType(Type):
    """Qualified type: sensor_msgs::LaserScan or sensor_msgs::msg::LaserScan"""
    package: str
    name: str
    kind: Optional[str] = None  # 'msg', 'srv' or 'action' when written explicitly


@dataclass
class ListType(Type):
    """List type: list<int>"""
    element_type: Type


@dataclass
class FieldDecl(ASTNode):
    """Struct field declaration."""
    name: str
    type: Type
    default_value: Optional['Expression'] = None


@dataclass
class StructType(Type):
    """Struct type: struct { field: type }"""
    fields: List[FieldDecl] = field(default_factory=list)


# =============================================================================
# Expressions
# =============================================================================

@dataclass
class Expression(ASTNode):
    """Base class for expressions."""
    pass


@dataclass
class LiteralExpression(Expression):
    """Literal value: 42, "hello", true"""
    value: Any
    literal_type: str  # 'int', 'float', 'string', 'bool', 'duration'


@dataclass
class IdentifierExpression(Expression):
    """Identifier reference: my_param"""
    name: str


@dataclass
class QualifiedIdentifierExpression(Expression):
    """Qualified identifier: std_msgs::Header"""
    parts: List[str]


@dataclass
class MemberAccessExpression(Expression):
    """Member access: obj.field"""
    object: Expression
    member: str


@dataclass
class IndexExpression(Expression):
    """Index access: arr[i]"""
    array: Expression
    index: Expression


@dataclass
class CallExpression(Expression):
    """Function call: func(arg1, arg2)"""
    callee: Expression
    arguments: List[Expression] = field(default_factory=list)


@dataclass
class InterpolatedExpression(Expression):
    """Interpolated expression: ${expression}"""
    inner: Expression


@dataclass
class BinaryExpression(Expression):
    """Binary expression: a + b, x == y"""
    operator: str
    left: Expression
    right: Expression


@dataclass
class UnaryExpression(Expression):
    """Unary expression: !x, -y"""
    operator: str
    operand: Expression


@dataclass
class ArrayExpression(Expression):
    """Array literal: [1, 2, 3]"""
    elements: List[Expression] = field(default_factory=list)


@dataclass
class StructInitializerExpression(Expression):
    """Struct initializer: struct { field: value }"""
    fields: Dict[str, Expression] = field(default_factory=dict)


# =============================================================================
# Constraints
# =============================================================================

@dataclass
class Constraint(ASTNode):
    """Constraint annotation: @range(0, 100), @qos(depth=5)

    ``arguments`` holds every argument in source order (named ones included);
    ``named_arguments`` additionally maps the ``key=value`` ones by key.
    """
    name: str
    arguments: List[Expression] = field(default_factory=list)
    named_arguments: Dict[str, Expression] = field(default_factory=dict)


# =============================================================================
# Node Declarations
# =============================================================================

@dataclass
class ParameterDecl(ASTNode):
    """Parameter declaration: frame_id: string = "laser" @range(0, 100)"""
    name: str
    type: Type
    default_value: Optional[Expression] = None
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class SubscriptionDecl(ASTNode):
    """Subscription declaration: scan: LaserScan @topic("/scan")"""
    name: str
    message_type: QualifiedType
    topic: Expression
    qos: Optional['QoSConfig'] = None
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class PublicationDecl(ASTNode):
    """Publication declaration: processed_scan: LaserScan @topic("/out")"""
    name: str
    message_type: QualifiedType
    topic: Expression
    qos: Optional['QoSConfig'] = None
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class ServiceDecl(ASTNode):
    """Service declaration: set_param: SetBool @service("~/set")"""
    name: str
    service_type: QualifiedType
    service_name: Expression
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class ActionDecl(ASTNode):
    """Action declaration: navigate: NavigateToGoal"""
    name: str
    action_type: QualifiedType
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class QoSConfig(ASTNode):
    """QoS configuration: reliable, depth=10"""
    reliability: str = "reliable"  # 'reliable' or 'best_effort'
    durability: Optional[str] = None  # 'volatile' or 'transient_local'
    depth: Optional[int] = None
    history: Optional[str] = None  # 'keep_last' or 'keep_all'


@dataclass
class LifecycleDecl(ASTNode):
    """Lifecycle declaration: lifecycle: managed"""
    is_managed: bool


@dataclass
class ComponentDecl(ASTNode):
    """Component declaration: filter: PointCloudFilter { ... }"""
    name: str
    component_type: str
    parameters: Dict[str, Expression] = field(default_factory=dict)


@dataclass
class CallbackDecl(ASTNode):
    """Callback declaration: on_scan_received(msg: LaserScan) { ... }"""
    event: str
    parameters: List[ParameterDecl] = field(default_factory=list)
    body: str = ""  # Python code as string


@dataclass
class NodeDecl(ASTNode):
    """Node declaration: node LidarProcessor { ... }"""
    name: str
    parameters: List[ParameterDecl] = field(default_factory=list)
    subscriptions: List[SubscriptionDecl] = field(default_factory=list)
    publications: List[PublicationDecl] = field(default_factory=list)
    services: List[ServiceDecl] = field(default_factory=list)
    actions: List[ActionDecl] = field(default_factory=list)
    lifecycle: Optional[LifecycleDecl] = None
    components: List[ComponentDecl] = field(default_factory=list)
    callbacks: List[CallbackDecl] = field(default_factory=list)


# =============================================================================
# Launch Declarations
# =============================================================================

@dataclass
class ArgumentDecl(ASTNode):
    """Launch argument declaration."""
    name: str
    type: Type
    default_value: Optional[Expression] = None
    constraints: List[Constraint] = field(default_factory=list)


@dataclass
class NodeInstance(ASTNode):
    """Node instance in launch: lidar: LidarDriver { ... }"""
    name: str
    node_type: str
    parameters: Dict[str, Expression] = field(default_factory=dict)
    remaps: Dict[str, str] = field(default_factory=dict)
    condition: Optional[Expression] = None


@dataclass
class GroupDecl(ASTNode):
    """Group declaration: group sensors @namespace("sensors") { ... }"""
    name: str
    namespace: Expression
    nodes: List[NodeInstance] = field(default_factory=list)


@dataclass
class ComponentInstance(ASTNode):
    """Component instance in container."""
    name: str
    component_type: str
    parameters: Dict[str, Expression] = field(default_factory=dict)


@dataclass
class ContainerDecl(ASTNode):
    """Container declaration for composable nodes."""
    name: str
    container_name: Expression
    components: List[ComponentInstance] = field(default_factory=list)


@dataclass
class IncludeDecl(ASTNode):
    """Include another launch file."""
    target: Union[str, IdentifierExpression]
    arguments: Dict[str, Expression] = field(default_factory=dict)


@dataclass
class TransitionDecl(ASTNode):
    """Lifecycle transition declaration."""
    from_state: str
    to_state: str
    delay: Optional[float] = None


@dataclass
class LifecycleManagerDecl(ASTNode):
    """Lifecycle manager declaration."""
    name: str
    managed_nodes: List[str] = field(default_factory=list)
    transitions: List[TransitionDecl] = field(default_factory=list)


@dataclass
class EventAction(ASTNode):
    """Event action: node.enabled = true"""
    target: str
    property: str
    value: Expression


@dataclass
class LaunchEventDecl(ASTNode):
    """Launch event handler: on "topic" { ... }"""
    trigger: str
    actions: List[EventAction] = field(default_factory=list)


@dataclass
class LaunchDecl(ASTNode):
    """Launch declaration: launch NavigationStack { ... }"""
    name: str
    arguments: List[ArgumentDecl] = field(default_factory=list)
    groups: List[GroupDecl] = field(default_factory=list)
    containers: List[ContainerDecl] = field(default_factory=list)
    includes: List[IncludeDecl] = field(default_factory=list)
    lifecycle_manager: Optional[LifecycleManagerDecl] = None
    events: List[LaunchEventDecl] = field(default_factory=list)


# =============================================================================
# Interface Declarations
# =============================================================================

@dataclass
class MessageDecl(ASTNode):
    """Message interface declaration."""
    name: str
    id: int
    fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class ServiceInterfaceDecl(ASTNode):
    """Service interface declaration."""
    name: str
    id: int
    request_fields: List[FieldDecl] = field(default_factory=list)
    response_fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class ActionInterfaceDecl(ASTNode):
    """Action interface declaration."""
    name: str
    id: int
    goal_fields: List[FieldDecl] = field(default_factory=list)
    feedback_fields: List[FieldDecl] = field(default_factory=list)
    result_fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class InterfaceDecl(ASTNode):
    """Interface file root node."""
    declarations: List[Union[MessageDecl, ServiceInterfaceDecl, ActionInterfaceDecl]] = field(
        default_factory=list
    )

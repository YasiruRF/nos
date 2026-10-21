"""Unit tests for code generation and launch transpilation."""

import pytest
from nos.ast.nodes import (
    SourceLocation, NodeDecl, ParameterDecl, PrimitiveType, PrimitiveTypeKind,
    LiteralExpression, QualifiedType, SubscriptionDecl, PublicationDecl,
    LaunchDecl, GroupDecl, NodeInstance, ContainerDecl, ComponentInstance,
    IdentifierExpression, BinaryExpression, ActionDecl
)
from nos.semantic import SymbolTable, SemanticAnalyzer
from nos.codegen import PythonGenerator, LaunchTranspiler, GenerationOutput


class TestPythonGenerator:
    """Tests for PythonGenerator class."""

    def test_generator_creation(self):
        gen = PythonGenerator()
        assert gen.target == 'python'

    def test_generate_simple_node(self):
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="TestNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        assert isinstance(output, GenerationOutput)
        assert "test_node_node.py" in output.files

    def test_generate_node_with_params(self):
        loc = SourceLocation(1, 0, "test.nos")
        param = ParameterDecl(
            location=loc,
            name="frame_id",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="base", literal_type="string")
        )
        node = NodeDecl(
            location=loc,
            name="ParamNode",
            parameters=[param],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["param_node_node.py"]
        assert "frame_id" in code
        assert "declare_parameter" in code

    def test_generate_subscription(self):
        loc = SourceLocation(1, 0, "test.nos")
        sub = SubscriptionDecl(
            location=loc,
            name="scan",
            message_type=QualifiedType(location=loc, package="sensor_msgs", name="LaserScan"),
            topic=LiteralExpression(location=loc, value="/scan", literal_type="string"),
            qos=None,
            constraints=[]
        )
        node = NodeDecl(
            location=loc,
            name="SubNode",
            parameters=[],
            subscriptions=[sub],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["sub_node_node.py"]
        assert "create_subscription" in code
        assert "LaserScan" in code

    def test_camel_to_snake(self):
        gen = PythonGenerator()
        assert gen._camel_to_snake("TestNode") == "test_node"
        assert gen._camel_to_snake("LidarProcessor") == "lidar_processor"
        assert gen._camel_to_snake("URLParser") == "url_parser"

    def test_indent(self):
        gen = PythonGenerator()
        text = "line1\nline2"
        indented = gen._indent(text, 1)
        assert "    line1" in indented
        assert "    line2" in indented


class TestLaunchTranspiler:
    """Tests for LaunchTranspiler class."""

    def test_transpiler_creation(self):
        trans = LaunchTranspiler()
        assert trans.launch_counter == 0

    def test_generate_launch(self):
        loc = SourceLocation(1, 0, "test.nos")
        launch = LaunchDecl(
            location=loc,
            name="TestLaunch",
            arguments=[],
            groups=[],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        assert isinstance(output, GenerationOutput)
        assert "test_launch_launch.py" in output.files

    def test_generate_launch_with_group(self):
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeInstance(
            location=loc,
            name="lidar",
            node_type="LidarDriver",
            parameters={}
        )
        group = GroupDecl(
            location=loc,
            name="sensors",
            namespace=LiteralExpression(location=loc, value="sensors", literal_type="string"),
            nodes=[node]
        )
        launch = LaunchDecl(
            location=loc,
            name="GroupLaunch",
            arguments=[],
            groups=[group],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        code = output.files["group_launch_launch.py"]
        assert "GroupAction" in code
        assert "lidar" in code

    def test_generate_container(self):
        loc = SourceLocation(1, 0, "test.nos")
        comp = ComponentInstance(
            location=loc,
            name="processor",
            component_type="ImageProcessor",
            parameters={}
        )
        container = ContainerDecl(
            location=loc,
            name="PerceptionContainer",
            container_name=LiteralExpression(location=loc, value="perception_container", literal_type="string"),
            components=[comp]
        )
        launch = LaunchDecl(
            location=loc,
            name="ContainerLaunch",
            arguments=[],
            groups=[],
            containers=[container],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        code = output.files["container_launch_launch.py"]
        assert "ComposableNodeContainer" in code
        assert "ComposableNode" in code

    def test_generate_launch_with_substitutions(self):
        """Test generating launch description with call expressions and interpolated configurations."""
        from nos.ast.nodes import CallExpression, InterpolatedExpression, LiteralExpression, IdentifierExpression, ArgumentDecl, PrimitiveType, PrimitiveTypeKind
        loc = SourceLocation(1, 0, "test.nos")
        
        find_pkg = CallExpression(
            location=loc,
            callee=IdentifierExpression(location=loc, name="FindPackageShare"),
            arguments=[LiteralExpression(location=loc, value="lecture4", literal_type="string")]
        )
        
        path_join = CallExpression(
            location=loc,
            callee=IdentifierExpression(location=loc, name="PathJoinSubstitution"),
            arguments=[
                find_pkg,
                LiteralExpression(location=loc, value="urdf", literal_type="string"),
                InterpolatedExpression(location=loc, inner=IdentifierExpression(location=loc, name="filename"))
            ]
        )
        
        command_call = CallExpression(
            location=loc,
            callee=IdentifierExpression(location=loc, name="Command"),
            arguments=[
                LiteralExpression(location=loc, value="xacro", literal_type="string"),
                path_join
            ]
        )
        
        node_instance = NodeInstance(
            location=loc,
            name="robot_state_publisher",
            node_type="RobotStatePublisher",
            parameters={
                "robot_description": command_call
            },
            condition=None
        )
        
        group = GroupDecl(
            location=loc,
            name="default_group",
            namespace=LiteralExpression(location=loc, value="", literal_type="string"),
            nodes=[node_instance]
        )
        
        launch = LaunchDecl(
            location=loc,
            name="SubLaunch",
            arguments=[
                ArgumentDecl(location=loc, name="filename", type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING), default_value=LiteralExpression(location=loc, value="robot", literal_type="string"))
            ],
            groups=[group],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )
        
        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)
        
        code = output.files["sub_launch_launch.py"]
        assert "from launch.substitutions import LaunchConfiguration, TextSubstitution, PathJoinSubstitution, Command" in code
        assert "from launch_ros.substitutions import FindPackageShare" in code
        assert "filename = LaunchConfiguration('filename')" in code
        assert "Command(\"xacro\", PathJoinSubstitution(FindPackageShare(\"lecture4\"), \"urdf\", filename))" in code


class TestGenerationOutput:
    """Tests for GenerationOutput class."""

    def test_output_creation(self):
        out = GenerationOutput()
        assert len(out.files) == 0

    def test_add_file(self):
        out = GenerationOutput()
        out.add_file("test.py", "print('hello')")
        assert "test.py" in out.files
        assert out.files["test.py"] == "print('hello')"

    def test_get_file(self):
        out = GenerationOutput()
        out.add_file("test.py", "content")
        assert out.get_file("test.py") == "content"
        assert out.get_file("missing.py") == ""


class TestCodeGenerationEdgeCases:
    """Tests for edge cases in code generation."""

    def test_reserved_keyword_escape(self):
        """Test that reserved keywords are escaped."""
        gen = PythonGenerator()
        reserved = gen._reserved_keywords()
        assert "class" in reserved
        assert "def" in reserved

    def test_expression_to_python_literal(self):
        """Test expression conversion to Python."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        # Integer literal
        int_lit = LiteralExpression(location=loc, value=42, literal_type="int")
        assert gen._expression_to_python(int_lit) == "42"

        # String literal
        str_lit = LiteralExpression(location=loc, value="hello", literal_type="string")
        assert gen._expression_to_python(str_lit) == '"hello"'

        # Boolean literal
        bool_lit = LiteralExpression(location=loc, value=True, literal_type="bool")
        assert gen._expression_to_python(bool_lit) == "True"

    def test_expression_to_python_identifier(self):
        """Test identifier expression conversion."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        ident = IdentifierExpression(location=loc, name="my_var")
        assert gen._expression_to_python(ident) == "my_var"

    def test_python_type_conversion(self):
        """Test NOS type to Python type conversion."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        # Primitive types
        int_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.INT)
        assert gen._get_python_type(int_type) == "int"

        float_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.FLOAT)
        assert gen._get_python_type(float_type) == "float"

        string_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING)
        assert gen._get_python_type(string_type) == "str"

    def test_empty_node_generation(self):
        """Test generation of empty node."""
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="EmptyNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["empty_node_node.py"]
        # Should still have valid Python structure
        assert "class" in code
        assert "def __init__" in code

    def test_action_server_generation(self):
        """Test code generation for nodes containing Action Servers."""
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="ActionNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[
                ActionDecl(
                    location=loc,
                    name="navigate",
                    action_type=QualifiedType(location=loc, package="nav2_msgs", name="NavigateToPose"),
                    constraints=[]
                )
            ],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["action_node_node.py"]
        assert "from rclpy.action import ActionServer" in code
        assert "from nav2_msgs.action import NavigateToPose" in code
        assert "ActionServer(" in code
        assert "def _on_navigate_execute(self, goal_handle)" in code
        assert "def navigate_execute(self, goal_handle)" in code

    def test_clients_and_reentrant_generation(self):
        """Test code generation for service/action clients and reentrant callback groups."""
        from nos.ast.nodes import Constraint, ServiceDecl
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="ClientNode",
            parameters=[],
            subscriptions=[
                SubscriptionDecl(
                    location=loc,
                    name="input",
                    message_type=QualifiedType(location=loc, package="std_msgs", name="String"),
                    topic=LiteralExpression(location=loc, value="/input", literal_type="string"),
                    qos=None,
                    constraints=[Constraint(location=loc, name="reentrant", arguments=[])]
                )
            ],
            publications=[],
            services=[
                ServiceDecl(
                    location=loc,
                    name="calc_client",
                    service_type=QualifiedType(location=loc, package="example_interfaces", name="AddTwoInts"),
                    service_name=LiteralExpression(location=loc, value="/add", literal_type="string"),
                    constraints=[
                        Constraint(location=loc, name="client", arguments=[]),
                        Constraint(location=loc, name="reentrant", arguments=[])
                    ]
                )
            ],
            actions=[
                ActionDecl(
                    location=loc,
                    name="nav_client",
                    action_type=QualifiedType(location=loc, package="nav2_msgs", name="NavigateToPose"),
                    constraints=[
                        Constraint(location=loc, name="client", arguments=[]),
                        Constraint(location=loc, name="reentrant", arguments=[])
                    ]
                )
            ],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["client_node_node.py"]
        assert "from rclpy.callback_groups import ReentrantCallbackGroup" in code
        assert "from rclpy.action import ActionClient" in code
        assert "from example_interfaces.srv import AddTwoInts" in code
        assert "from nav2_msgs.action import NavigateToPose" in code
        
        # Check reentrant group creation and usage
        assert "self._reentrant_group = ReentrantCallbackGroup()" in code
        assert "callback_group=self._reentrant_group" in code
        
        # Check client creation
        assert "self.calc_client = self.create_client(" in code
        assert "self.nav_client = ActionClient(" in code
        
        # Ensure no execute/request wrappers are generated for clients
        assert "def _on_nav_client_execute" not in code
        assert "def _calc_client_callback" not in code

    def test_action_server_with_validation_generation(self):
        """Test Action Server generation with user-defined goal and cancel callbacks."""
        from nos.ast.nodes import CallbackDecl
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="ValNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[
                ActionDecl(
                    location=loc,
                    name="navigate",
                    action_type=QualifiedType(location=loc, package="nav2_msgs", name="NavigateToPose"),
                    constraints=[]
                )
            ],
            lifecycle=None,
            components=[],
            callbacks=[
                CallbackDecl(location=loc, event="on_navigate_goal", parameters=[], body="pass"),
                CallbackDecl(location=loc, event="on_navigate_cancel", parameters=[], body="pass")
            ]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["val_node_node.py"]
        assert "from rclpy.action import ActionServer" in code
        assert "goal_callback=self.on_navigate_goal" in code
        assert "cancel_callback=self.on_navigate_cancel" in code

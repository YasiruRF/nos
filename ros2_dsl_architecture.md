# ROS2 DSL Architecture: Node Orchestration System (NOS)

## Executive Summary

NOS (Node Orchestration System) is a declarative domain-specific language designed to address ROS2's verbosity and complexity challenges. It provides a unified syntax for defining robotics systems, generating optimized Python/C++ code while maintaining full compatibility with existing ROS2 tooling.

---

## 1. DSL Syntax Style

### Design Decision: Hybrid Declarative with Embedded Expressions

**Rationale:** Pure declarative languages struggle with complex logic, while imperative languages are verbose for system composition. NOS uses a **declarative-first approach with embedded Python expressions** for dynamic behavior.

### Syntax Philosophy

```
+-------------------------------------------------------------+
|                     NOS SYNTAX LAYERS                       |
+-------------------------------------------------------------+
| Layer 1: Declarative Structure (System composition)         |
| Layer 2: Configuration DSL (Parameters, QoS, Remappings)    |
| Layer 3: Embedded Expressions (Python for dynamic logic)    |
| Layer 4: Extension Hooks (Custom behaviors, plugins)        |
+-------------------------------------------------------------+
```

### File Extensions and Structure

- `.node` - NOS source files: packages, node components and launch declarations
- `.interface` - Message/service/action interface definitions

---

## 2. Core Abstractions

### 2.1 Package and Module System

**NOS (.node)**:
```nos
package robot_navigation
version "1.0.0"
depends: ["rclpy", "geometry_msgs", "nav2_bringup", "sensor_msgs"]

import std::topics
import nav2::components as nav
```

**Equivalent ROS2 (package.xml)**:
```xml
<?xml version="1.0"?>
<package format="3">
  <name>robot_navigation</name>
  <version>1.0.0</version>
  <description>Navigation package</description>
  <depend>rclpy</depend>
  <depend>geometry_msgs</depend>
  <depend>nav2_bringup</depend>
  <depend>sensor_msgs</depend>
</package>
```

### 2.2 Node Definition

**NOS (.node)**:
```nos
node LidarProcessor {
    # Concise parameter declarations with defaults and constraints
    parameters {
        frame_id: string = "laser_frame"
        scan_topic: string = "/scan"
        publish_rate: float = 10.0 @range(1.0, 100.0)
        min_range: float = 0.1 @range(0.0, 30.0)
        max_range: float = 30.0 @range(0.0, 100.0)
        
        # Structured parameters with validation
        filter_config: struct {
            enabled: bool = true
            window_size: int = 5 @range(1, 50)
            algorithm: string = "median" @one_of(["median", "mean", "kalman"])
        }
    }
    
    # Topic declarations with inferred types from message packages
    subscriptions {
        scan: sensor_msgs::LaserScan @topic(${scan_topic}) @qos(reliable, depth=10)
        imu: sensor_msgs::Imu @topic("/imu/data") @qos(best_effort)
    }
    
    publications {
        processed_scan: sensor_msgs::LaserScan @topic("/scan/processed") @qos(reliable, depth=10)
        diagnostics: diagnostic_msgs::DiagnosticArray @topic("/diagnostics") @latch
    }
    
    services {
        set_parameters: std_srvs::SetBool @service("~/set_enabled")
    }
    
    # Lifecycle declaration (optional but concise)
    lifecycle: managed  # vs 'unmanaged' for standard nodes
    
    # Component composition
    components {
        filter: PointCloudFilter {
            window_size: ${filter_config.window_size}
        }
        transformer: FrameTransformer {
            target_frame: "base_link"
        }
    }
    
    # Callbacks with embedded Python
    on_init {
        self.filter.initialize()
        self.get_logger().info("LidarProcessor initialized")
    }
    
    on_scan_received(msg: sensor_msgs::LaserScan) {
        filtered = self.filter.process(msg)
        transformed = self.transformer.transform(filtered, self.frame_id)
        self.processed_scan.publish(transformed)
    }
    
    on_shutdown {
        self.filter.cleanup()
    }
}
```

**Equivalent ROS2 Python (~200 lines)**:
```python
import rclpy
from rclpy.node import Node
from rclpy.lifecycle import LifecycleNode
from rclpy.lifecycle import State, TransitionCallbackReturn
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import LaserScan, Imu
from diagnostic_msgs.msg import DiagnosticArray
from std_srvs.srv import SetBool
from rcl_interfaces.msg import ParameterDescriptor, FloatingPointRange, IntegerRange

class LidarProcessor(LifecycleNode):
    def __init__(self):
        super().__init__('lidar_processor')
        
        # Verbose parameter declarations
        self.declare_parameter('frame_id', 'laser_frame')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('publish_rate', 10.0,
            descriptor=ParameterDescriptor(
                floating_point_range=[FloatingPointRange(from_value=1.0, to_value=100.0)]
            ))
        self.declare_parameter('min_range', 0.1,
            descriptor=ParameterDescriptor(
                floating_point_range=[FloatingPointRange(from_value=0.0, to_value=30.0)]
            ))
        self.declare_parameter('max_range', 30.0)
        
        self.declare_parameter('filter_config.enabled', True)
        self.declare_parameter('filter_config.window_size', 5)
        self.declare_parameter('filter_config.algorithm', 'median')
        
        self.scan_sub = None
        self.imu_sub = None
        self.processed_pub = None
        self.diagnostics_pub = None
        self.set_param_srv = None
        
    def on_configure(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Configuring...')
        
        scan_topic = self.get_parameter('scan_topic').value
        
        qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        self.scan_sub = self.create_subscription(
            LaserScan, scan_topic, self.scan_callback, qos_reliable)
        self.imu_sub = self.create_subscription(
            Imu, '/imu/data', self.imu_callback, 
            QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT))
        
        self.processed_pub = self.create_publisher(
            LaserScan, '/scan/processed', qos_reliable)
        self.diagnostics_pub = self.create_publisher(
            DiagnosticArray, '/diagnostics', QoSProfile(depth=1))
        
        self.set_param_srv = self.create_service(
            SetBool, '~/set_enabled', self.set_enabled_callback)
        
        return TransitionCallbackReturn.SUCCESS
    
    def scan_callback(self, msg):
        pass  # Processing logic
    
    def imu_callback(self, msg):
        pass
    
    def set_enabled_callback(self, request, response):
        response.success = True
        return response

def main(args=None):
    rclpy.init(args=args)
    node = LidarProcessor()
    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 2.3 Launch System

**NOS Launch (.node)**:
```nos
launch NavigationStack {
    # Grouping with implicit namespace
    group sensors @namespace("sensors") {
        # Node with inline parameter override
        lidar: LidarDriver {
            parameters: {
                port: "/dev/ttyUSB0"
                baud_rate: 115200
            }
            # Conditional inclusion
            @when(${use_simulation} == false)
        }
        
        camera: CameraDriver {
            parameters: {
                device_id: 0
                width: 640
                height: 480
                format: "bgr8"
            }
        }
    }
    
    # Composable nodes (intra-process communication)
    component_container PerceptionPipeline @container("perception_container") {
        image_processor: ImageProcessor @load_component
        object_detector: ObjectDetector @load_component {
            parameters: { model_path: ${model_path} }
        }
        fusion: SensorFusion @load_component
    }
    
    # Include other launch files with parameter propagation
    include robot_description.launch {
        args: {
            robot_model: "turtlebot3_waffle"
            use_sim_time: ${use_simulation}
        }
    }
    
    # Lifecycle management
    lifecycle_manager NavigationLifecycle {
        manages: [sensors.lidar, sensors.camera, PerceptionPipeline]
        transitions: [
            { from: unconfigured, to: inactive },
            { from: inactive, to: active, @delay(2.0) }
        ]
    }
    
    # Event-based coordination
    on "sensors.lidar:state=active" {
        log.info("LiDAR is ready, starting safety monitors")
        safety_monitor.enabled = true
    }
    
    # Arguments with validation
    arguments {
        use_simulation: bool = false @description("Use Gazebo simulation")
        model_path: string @required @description("Path to ML model")
        log_level: string = "info" @one_of(["debug", "info", "warn", "error"])
    }
}
```

**Equivalent ROS2 Python Launch (~150 lines)**:
```python
import os
import launch
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node, ComposableNodeContainer, LifecycleNode
from launch_ros.descriptions import ComposableNode
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    use_simulation = LaunchConfiguration('use_simulation')
    model_path = LaunchConfiguration('model_path')
    log_level = LaunchConfiguration('log_level')
    
    declare_use_simulation = DeclareLaunchArgument(
        'use_simulation', default_value='false',
        description='Use Gazebo simulation'
    )
    declare_model_path = DeclareLaunchArgument(
        'model_path', description='Path to ML model'
    )
    declare_log_level = DeclareLaunchArgument(
        'log_level', default_value='info'
    )
    
    # Sensors group
    sensors_group = GroupAction([
        Node(
            package='lidar_driver',
            executable='lidar_node',
            name='lidar',
            namespace='sensors',
            parameters=[{'port': '/dev/ttyUSB0', 'baud_rate': 115200}],
            condition=UnlessCondition(use_simulation)
        ),
        Node(
            package='camera_driver',
            executable='camera_node',
            name='camera',
            namespace='sensors',
            parameters=[{
                'device_id': 0,
                'width': 640,
                'height': 480,
                'format': 'bgr8'
            }]
        ),
    ])
    
    # Component container
    perception_container = ComposableNodeContainer(
        name='perception_container',
        namespace='',
        package='rclcpp_components',
        executable='component_container',
        composable_node_descriptions=[
            ComposableNode(
                package='image_processor',
                plugin='image_processor::ImageProcessor',
                name='image_processor'
            ),
            ComposableNode(
                package='object_detector',
                plugin='object_detector::ObjectDetector',
                name='object_detector',
                parameters=[{'model_path': model_path}]
            ),
            ComposableNode(
                package='sensor_fusion',
                plugin='fusion::SensorFusion',
                name='fusion'
            ),
        ]
    )
    
    # Include other launch
    robot_description_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('robot_description'),
                'launch',
                'robot_description.launch.py'
            ])
        ]),
        launch_arguments={
            'robot_model': 'turtlebot3_waffle',
            'use_sim_time': use_simulation
        }.items()
    )
    
    return LaunchDescription([
        declare_use_simulation,
        declare_model_path,
        declare_log_level,
        sensors_group,
        perception_container,
        robot_description_launch,
    ])
```

### 2.4 Topic and Message Handling

**NOS - Message Interface Definition (.interface)**:
```nos
# Automatic message structure validation and serialization
message SensorFusionOutput @id(1) {
    header: std_msgs::Header
    fused_pose: geometry_msgs::PoseWithCovariance
    confidence: float32 @range(0.0, 1.0)
    sources: list<string> @max_length(10)
    
    # Derived/computed fields
    @computed
    timestamp_age: duration = ${now} - ${header.stamp}
    
    # Validation rules
    @validate
    assert confidence >= 0.0 && confidence <= 1.0
    assert len(sources) > 0
}

service SetNavigationGoal @id(2) {
    request {
        pose: geometry_msgs::PoseStamped
        timeout: duration = 30.0s
        replanning_strategy: string @one_of(["strict", "adaptive", "aggressive"])
    }
    response {
        success: bool
        message: string
        estimated_arrival: duration @optional
    }
    @timeout(5.0s)
    @retry(3, backoff="exponential")
}

action FollowPath @id(3) {
    goal {
        path: nav_msgs::Path
        velocity_profile: string = "optimal"
    }
    feedback {
        current_pose: geometry_msgs::PoseStamped
        distance_remaining: float32
        estimated_time: duration
    }
    result {
        success: bool
        final_pose: geometry_msgs::PoseStamped
        execution_time: duration
    }
}
```

**Generated ROS2 IDL**:
```idl
// Auto-generated from NOS interface
// sensor_fusion_output.idl

#include "std_msgs/msg/Header.idl"
#include "geometry_msgs/msg/PoseWithCovariance.idl"

module robot_navigation {
  module msg {
    struct SensorFusionOutput {
      std_msgs::msg::Header header;
      geometry_msgs::msg::PoseWithCovariance fused_pose;
      float confidence;
      sequence<string, 10> sources;
    };
  };
};
```

### 2.5 Parameter Management

**NOS - Parameter Schemas**:
```nos
# Centralized parameter schema with validation
schema RobotConfiguration {
    # Typed parameters with validation
    max_linear_velocity: float = 1.0 @unit("m/s") @range(0.0, 5.0)
    max_angular_velocity: float = 1.57 @unit("rad/s") @range(0.0, 3.14)
    
    # Nested structures
    safety_limits: struct {
        emergency_stop_distance: float = 0.5 @range(0.1, 2.0)
        collision_avoidance_enabled: bool = true
        
        # Array parameters with constraints
        monitored_zones: list<struct {
            name: string
            polygon: list<geometry_msgs::Point> @min_length(3) @max_length(10)
        }> @max_length(5)
    }
    
    # Dynamic reconfiguration support
    @dynamic
    controller_gains: struct {
        kp: float = 1.0 @range(0.0, 100.0)
        ki: float = 0.1 @range(0.0, 10.0)
        kd: float = 0.01 @range(0.0, 1.0)
    }
    
    # Parameter relationships
    @constraint
    assert safety_limits.emergency_stop_distance < max_linear_velocity * 2.0
}

# Usage in node
node VelocityController {
    parameters: RobotConfiguration
    
    on_parameter_change(${safety_limits.collision_avoidance_enabled}) {
        self.update_safety_monitors(new_value)
    }
}
```

**Generated Python Parameter Handling**:
```python
# Auto-generated parameter validation
from dataclasses import dataclass, field
from typing import List, Optional
from rclpy.parameter import Parameter

@dataclass
class SafetyZone:
    name: str
    polygon: List[geometry_msgs.msg.Point]

@dataclass
class SafetyLimits:
    emergency_stop_distance: float = 0.5
    collision_avoidance_enabled: bool = True
    monitored_zones: List[SafetyZone] = field(default_factory=list)

@dataclass  
class RobotConfiguration:
    max_linear_velocity: float = 1.0
    max_angular_velocity: float = 1.57
    safety_limits: SafetyLimits = field(default_factory=SafetyLimits)
    controller_gains: dict = field(default_factory=lambda: {'kp': 1.0, 'ki': 0.1, 'kd': 0.01})
    
    def validate(self):
        assert self.max_linear_velocity >= 0.0 and self.max_linear_velocity <= 5.0
        assert self.safety_limits.emergency_stop_distance < self.max_linear_velocity * 2.0
        return True
```

---

## 3. Code Generation Architecture

### 3.1 Generation Pipeline

```
+-------------+    +--------------+    +--------------+    +-------------+
|  NOS        |--->|   Parser     |--->|    AST       |--->|   CodeGen   |
|  Source     |    |  (ANTLR4)    |    |  Validation  |    |  (Python/   |
|  (.node)     |    |              |    |              |    |   C++)      |
+-------------+    +--------------+    +--------------+    +------+------+
                                                                  |
                    +--------------+                              |
                    |   Symbol     |<-----------------------------+
                    |   Table      |    (Type Resolution)         |
                    +--------------+                              |
                                                                  v
                    +--------------+                       +-------------+
                    |  Message     |                       |   ROS2      |
                    |  Definitions |<-------------------->|  Runtime    |
                    |  (.idl)      |                       |             |
                    +--------------+                       +-------------+
```

### 3.2 Generation Targets

#### Python Generation Strategy

```python
# Generated base class (users extend this)
# AUTO-GENERATED: Do not edit manually

from nos.runtime import NOSNode, NOSLifecycleNode
from nos.runtime.decorators import parameter, subscription, publisher, service

class LidarProcessorBase(NOSLifecycleNode):
    """Auto-generated base class for LidarProcessor node."""
    
    def __init__(self, node_name: str = "lidar_processor"):
        super().__init__(node_name)
        
        # Parameter declarations with descriptors
        self._declare_flow_parameters()
        
    def _declare_flow_parameters(self):
        self.declare_parameter('frame_id', 'laser_frame')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('publish_rate', 10.0)
        # ... validation descriptors auto-generated
    
    def _setup_communications(self):
        # Auto-generated subscription setup
        scan_topic = self.get_parameter('scan_topic').value
        self._scan_sub = self.create_subscription(
            LaserScan, scan_topic, self._on_scan_received, 
            self._qos_profile('reliable', depth=10)
        )
        
        self._processed_pub = self.create_publisher(
            LaserScan, '/scan/processed',
            self._qos_profile('reliable', depth=10)
        )
    
    def _on_scan_received(self, msg):
        """Wrapper that calls user-defined callback."""
        try:
            self.on_scan_received(msg)
        except Exception as e:
            self.get_logger().error(f"Error in scan callback: {e}")
    
    def on_scan_received(self, msg):
        """Override in subclass."""
        raise NotImplementedError()

# User implementation file (hand-written)
from .lidar_processor_base import LidarProcessorBase

class LidarProcessor(LidarProcessorBase):
    """User implementation - only contains logic."""
    
    def on_init(self):
        super().on_init()
        self.filter.initialize()
    
    def on_scan_received(self, msg):
        # User only writes the actual processing logic
        filtered = self.filter.process(msg)
        self.processed_scan.publish(filtered)
```

#### C++ Generation Strategy

```cpp
// Auto-generated header: lidar_processor_node.hpp
// AUTO-GENERATED: Do not edit manually

#ifndef NOS_LIDAR_PROCESSOR_NODE_HPP
#define NOS_LIDAR_PROCESSOR_NODE_HPP

#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <nos/runtime/flow_lifecycle_node.hpp>

namespace robot_navigation {

class LidarProcessorNode : public nos::NOSLifecycleNode {
public:
    explicit LidarProcessorNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());
    
    // Parameter accessors (type-safe)
    std::string frame_id() const;
    double publish_rate() const;
    
protected:
    // Lifecycle transitions
    LifecycleCallbackReturn on_configure(const State& state) override;
    LifecycleCallbackReturn on_activate(const State& state) override;
    LifecycleCallbackReturn on_deactivate(const State& state) override;
    LifecycleCallbackReturn on_cleanup(const State& state) override;
    
    // User-overridable callbacks
    virtual void on_init() {}
    virtual void on_scan_received(const sensor_msgs::msg::LaserScan::SharedPtr msg) = 0;
    virtual void on_shutdown() {}
    
private:
    void declare_flow_parameters();
    void setup_communications();
    
    rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
    rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr processed_pub_;
};

} // namespace robot_navigation

#endif
```

### 3.3 Compilation and Build Integration

**CMakeLists.txt.nos (NOS-aware CMake)**:
```cmake
nos_package()

nos_generate(
    SRCS 
        src/nodes/lidar_processor.node
        src/nodes/velocity_controller.node
    INTERFACES
        msg/SensorFusionOutput.interface
        srv/SetNavigationGoal.interface
    LAUNCH
        launch/navigation_stack.node
    PYTHON
        OUTPUT_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated
    CPP
        OUTPUT_DIR ${CMAKE_CURRENT_BINARY_DIR}/include
        LIBRARY robot_navigation_nodes
)

nos_add_executable(navigation_main
    src/main.cpp
    USES 
        lidar_processor
        velocity_controller
)

nos_add_component_library(perception_components
    COMPONENTS
        ImageProcessor
        ObjectDetector
        SensorFusion
)
```

**Generated standard CMakeLists.txt**:
```cmake
cmake_minimum_required(VERSION 3.8)
project(robot_navigation)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(nos_runtime REQUIRED)
# ... other dependencies

# Generated targets
add_library(robot_navigation_nodes SHARED
    ${NOS_GENERATED_CPP_SRCS}
)

ament_target_dependencies(robot_navigation_nodes
    rclcpp
    rclcpp_lifecycle
    nos_runtime
)

# Component registration
rclcpp_components_register_nodes(robot_navigation_nodes
    "robot_navigation::LidarProcessorNode"
    "robot_navigation::VelocityControllerNode"
)
```

---

## 4. Integration with ROS2 Tooling

### 4.1 ROS2 CLI Compatibility

NOS generates standard ROS2 package structures, maintaining compatibility:

```bash
# Standard ROS2 commands work unchanged
ros2 pkg list | grep robot_navigation
ros2 node list  # Shows NOS nodes
ros2 topic list  # Shows NOS topics
ros2 param list /lidar_processor  # Shows NOS parameters

# NOS adds enhanced commands
ros2 nos validate  # Validate .node files without building
ros2 nos visualize launch navigation_stack.node  # Generate system diagram
ros2 nos generate --target=cpp  # Trigger code generation
ros2 nos debug /lidar_processor  # Enhanced debugging with source mapping
```

### 4.2 RViz and Visualization Integration

**NOS - RViz Configuration**:
```nos
visualization NavigationView {
    panels {
        # Auto-populated from node definitions
        camera_feed: image @topic("/camera/image_raw")
        laser_scan: laser_scan @topic("/scan") @color(#FF0000)
        path: path @topic("/planned_path") @color(#00FF00)
        
        # Interactive markers from services
        goal_marker: interactive_marker @service("/set_goal")
        
        # Custom panels for complex data
        diagnostics: custom_panel {
            source: diagnostic_msgs::DiagnosticArray @topic("/diagnostics")
            layout: grid
            filter: ${diagnostic_level} >= WARN
        }
    }
    
    # Automatic view configuration
    default_view {
        frame: "map"
        follow: "base_link"
    }
}
```

### 4.3 rosbag Integration

**NOS - Recording Configuration**:
```nos
record Session @bag("session_{date}.bag") {
    # Selective recording with compression
    topics {
        include: ["/scan", "/camera/image_raw", "/odom", "/tf"]
        exclude: ["/camera/image_raw/compressed"]
    }
    
    # Conditional recording based on events
    @record_when ${/system/state} == "active"
    @split_size(1GB)
    @compression(zstd, level=3)
    
    # Metadata
    metadata {
        robot_id: ${ROBOT_ID}
        experiment: ${EXPERIMENT_NAME}
        operator: ${USER}
    }
}
```

### 4.4 Testing Integration

**NOS - Node Testing**:
```nos
test LidarProcessorTest {
    # Test fixture
    setup {
        node: LidarProcessor {
            parameters: { frame_id: "test_frame" }
        }
        mock_scan: sensor_msgs::LaserScan @generator(scan_generator)
    }
    
    test "valid_scan_processing" {
        given: mock_scan with range(0.1, 10.0)
        when: published to /scan
        then: expect processed_scan published within 100ms
        and: expect confidence > 0.8
    }
    
    test "invalid_range_filtering" @parametrize(range: [-0.1, 50.0]) {
        given: mock_scan with range(${range})
        when: published to /scan
        then: expect no output on processed_scan
        and: expect diagnostic message published
    }
    
    test "lifecycle_transitions" {
        sequence:
            1. transition node to configured
            2. expect subscriptions active
            3. transition node to active
            4. expect processing active
            5. transition node to inactive
            6. expect no output
    }
}
```

---

## 5. Advanced Features

### 5.1 Distributed System Coordination

**NOS - Multi-Robot Coordination**:
```nos
swarm RobotFleet @count(${fleet_size}) {
    robot: Robot {
        namespace: "robot_${index}"
        parameters: {
            position: ${formation_positions[index]}
            role: ${roles[index]}
        }
    }
    
    # Inter-robot communication patterns
    communication {
        mesh: full @bandwidth(100Mbps)
        leader_election: consensus
        state_sync: eventual_consistency @interval(100ms)
    }
    
    # Coordination behaviors
    behavior FormationControl {
        type: consensus
        target_formation: ${formation_shape}
        tolerance: 0.1m
        
        on "member_lost" {
            reconfigure_formation()
            elect_new_leader_if_needed()
        }
    }
}
```

### 5.2 Behavior Trees Integration

**NOS - Behavior Trees**:
```nos
behavior_tree NavigateToGoal {
    root: sequence {
        # Actions reference NOS nodes
        action SetNavigationGoal { goal: ${target_pose} }
        
        parallel(2) {
            # Monitor for cancellation or hazards
            monitor ObstacleDetection @on_change
            
            # Main navigation sequence
            sequence {
                action ComputePath { start: ${current_pose}, goal: ${target_pose} }
                action FollowPath { path: ${computed_path} }
                action VerifyArrival { tolerance: 0.1m }
            }
        }
    }
    
    on_failure {
        action ClearCostmaps {}
        action Retry { max_attempts: 3 }
    }
}
```

### 5.3 Simulation Integration

**NOS - Gazebo Integration**:
```nos
simulation NavigationSimulation {
    world: "office_building.world"
    physics: { real_time_factor: 1.0, max_step_size: 0.001 }
    
    models {
        robot: TurtleBot3 {
            pose: ${initial_pose}
            sensors: [lidar, camera, imu, odometry]
        }
        
        dynamic_obstacles: Person @count(5) {
            behavior: random_walk @velocity(0.5m/s)
        }
    }
    
    # Scenario-based testing
    scenario DoorwayNarrowing {
        trigger: ${robot.position} near "doorway_1" @radius(2m)
        action: spawn_obstacles @position("doorway_1/entrance")
        duration: 30s
    }
}
```

---

## 6. Migration Path from Existing ROS2

### 6.1 Gradual Migration Strategy

```
Phase 1: Launch files (.py/.xml -> .node)
Phase 2: Node parameters (yaml -> .node schema)
Phase 3: New nodes in NOS
Phase 4: Legacy node wrappers
Phase 5: Full NOS adoption
```

### 6.2 Interoperability Wrappers

**NOS - Wrapping Existing Nodes**:
```nos
external_node LegacyPlanner @package("nav2_planner") {
    executable: "planner_server"
    parameters: {
        expected_planner_frequency: float = 20.0
        use_astar: bool = true
        tolerance: float = 0.5
    }
    
    # Map NOS types to existing topic names
    remap {
        input: goal_pose -> "/goal_pose"
        output: plan -> "/plan"
    }
    
    # Parameter bridging
    bridge_parameters: true
}
```

---

## 7. Implementation Roadmap

### Phase 1: Core Language (Months 1-3)
- [x] ANTLR4 grammar definition
- [x] AST and semantic analyzer
- [x] Python code generator
- [x] Launch file transpiler

### Phase 2: ROS2 Integration (Months 4-6)
- [ ] C++ code generator
- [ ] Parameter system integration
- [ ] Lifecycle support
- [ ] Component composition

### Phase 3: Tooling (Months 7-9)
- [ ] VSCode/IDE extensions
- [ ] Language server protocol (LSP)
- [ ] Visual diagram generator
- [ ] Debug source mapping

### Phase 4: Advanced Features (Months 10-12)
- [ ] Distributed system coordination
- [ ] Behavior tree integration
- [ ] Simulation hooks
- [ ] Testing framework

---

## 8. Summary: Code Comparison Table

| Aspect | Native ROS2 (Python) | NOS | Reduction |
|--------|---------------------|----------|-----------|
| Simple Node | ~60 lines | ~15 lines | 75% |
| Lifecycle Node | ~120 lines | ~25 lines | 79% |
| Launch File | ~80 lines | ~20 lines | 75% |
| Parameters (10 params) | ~50 lines | ~10 lines | 80% |
| Component Container | ~60 lines | ~12 lines | 80% |
| Interface Definition | IDL + CMake | Single file | 70% |

**Overall**: 70-80% reduction in boilerplate code while maintaining full ROS2 compatibility and adding type safety, validation, and enhanced tooling.

---

## Appendix: Grammar Snippets

```antlr
// NOS.g4 - Core grammar excerpts
grammar NOS;

packageDecl: 'package' identifier version? depends?;

nodeDecl: 'node' identifier '{' 
    parameterBlock?
    communicationBlock?
    lifecycleDecl?
    componentBlock?
    callbackBlock*
'}';

parameterBlock: 'parameters' '{' parameterDecl* '}';
parameterDecl: identifier ':' type ('=' defaultValue)? constraint*;

constraint: '@' identifier ('(' parameterList? ')' | value)?;

type: primitiveType | qualifiedIdentifier | 'list' '<' type '>' | 'struct' '{' fieldDecl* '}';

primitiveType: 'bool' | 'int' | 'float' | 'double' | 'string' | 'duration' | 'time';

communicationBlock: (subscriptionBlock | publicationBlock | serviceBlock)+;
subscriptionBlock: 'subscriptions' '{' subscriptionDecl* '}';
subscriptionDecl: identifier ':' type '@topic' '(' expression ')' constraint*;

callbackBlock: 'on' identifier ('(' parameterList? ')')? '{' embeddedCode '}';

embeddedCode: PYTHON_CODE;

// Lexer rules
PYTHON_CODE: '{' (~[}] | PYTHON_CODE)* '}';
identifier: [a-zA-Z_][a-zA-Z0-9_]*;
```

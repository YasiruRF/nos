# Turtlesim Simulation Guide

This guide demonstrates how to use NOS (Node Orchestration System) to control a ROS2 Turtlesim simulation.

## Prerequisites
- ROS2 (Humble or later) installed in a Linux environment (or WSL).
- `turtlesim` package installed (`sudo apt install ros-$ROS_DISTRO-turtlesim`).
- NOS compiler installed and in your `PYTHONPATH`.

## Example 1: Basic Motion (TurtleController)
This node publishes velocity commands to make the turtle move in a circle.

```node
package turtlesim_test
version "0.1.0"
depends: ["rclpy", "geometry_msgs"]

node TurtleController {
    publications {
        cmd_vel: geometry_msgs::Twist @topic("/turtle1/cmd_vel")
    }

    on_init -> {
        self.get_logger().info("TurtleController initialized")
        # Start a timer to move the turtle (1.0 second period)
        self.create_timer(1.0, self.timer_callback)
    }

    on timer_callback() -> {
        msg = Twist()
        msg.linear.x = 2.0
        msg.angular.z = 1.0
        self.cmd_vel.publish(msg)
        self.get_logger().info("Publishing velocity")
    }
}
```

## Example 2: Boundary Guard (TurtleGuard)
This node monitors the turtle's pose and forces it to stay within a central "safe zone" by reversing and turning when it hits a boundary.

```node
package turtlesim_test
version "0.1.0"
depends: ["rclpy", "geometry_msgs", "turtlesim_msgs"]

node TurtleGuard {
    parameters {
        limit: float = 3.0
    }

    subscriptions {
        pose: turtlesim_msgs::Pose @topic("/turtle1/pose")
    }

    publications {
        cmd_vel: geometry_msgs::Twist @topic("/turtle1/cmd_vel")
    }

    on pose_received(msg: turtlesim_msgs::Pose) -> {
        # Check boundaries (Turtlesim default window is approx 11x11)
        if msg.x < ${limit} or msg.x > (11.0 - ${limit}) or msg.y < ${limit} or msg.y > (11.0 - ${limit}):
            self.get_logger().warn(f"Boundary reached! Pose: x={msg.x:.2f}, y={msg.y:.2f}")
            
            # Simple avoidance: back up and turn
            twist = Twist()
            twist.linear.x = -1.0
            twist.angular.z = 1.5
            self.cmd_vel.publish(twist)
        else:
            # Move forward if safe
            twist = Twist()
            twist.linear.x = 2.0
            twist.angular.z = 0.5
            self.cmd_vel.publish(twist)
    }
}
```

## Running the Examples
1. Start Turtlesim:
   ```bash
   ros2 run turtlesim turtlesim_node
   ```
2. Run your NOS node:
   ```bash
   python3 -m nos.compiler.main your_file.node --run
   ```
3. Change parameters at runtime:
   ```bash
   ros2 param set /turtle_guard limit 1.5
   ```

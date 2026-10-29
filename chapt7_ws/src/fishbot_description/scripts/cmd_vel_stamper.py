#!/usr/bin/env python3
"""Adapt the tutorial's Twist /cmd_vel topic to Jazzy's TwistStamped input."""

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node


class CmdVelStamper(Node):
    def __init__(self):
        super().__init__('cmd_vel_stamper')
        self.declare_parameter('input_topic', '/cmd_vel')
        self.declare_parameter(
            'output_topic', '/fishbot_diff_drive_controller/cmd_vel')
        self._publisher = self.create_publisher(
            TwistStamped, self.get_parameter('output_topic').value, 10)
        self.create_subscription(
            Twist, self.get_parameter('input_topic').value,
            self._callback, 10)

    def _callback(self, message: Twist):
        stamped = TwistStamped()
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = 'base_footprint'
        stamped.twist = message
        self._publisher.publish(stamped)


def main():
    rclpy.init()
    node = CmdVelStamper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

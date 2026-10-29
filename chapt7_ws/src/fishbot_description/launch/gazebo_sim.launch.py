import os

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
    UnsetEnvironmentVariable,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    EnvironmentVariable,
    IfElseSubstitution,
    LaunchConfiguration,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Start Gazebo Harmonic, load the world, and spawn FishBot."""
    robot_name = 'fishbot'
    package_share = get_package_share_directory('fishbot_description')
    package_prefix = get_package_prefix('fishbot_description')
    ros_gz_sim_share = get_package_share_directory('ros_gz_sim')

    default_model_path = os.path.join(
        package_share, 'urdf', 'fishbot', 'fishbot.urdf.xacro')
    default_world_path = os.path.join(
        package_share, 'world', 'custom_room.world')

    model_arg = DeclareLaunchArgument(
        'model',
        default_value=default_model_path,
        description='FishBot xacro 文件的绝对路径',
    )
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world_path,
        description='Gazebo Sim 世界文件的绝对路径',
    )
    spawn_z_arg = DeclareLaunchArgument(
        'spawn_z',
        default_value='0.05',
        description='机器人出生点的 Z 坐标（米）',
    )
    software_rendering_arg = DeclareLaunchArgument(
        'software_rendering',
        default_value='0',
        description='设为 1 强制 Mesa 软件渲染；虚拟机 3D 加速可用后设为 0',
    )
    render_engine_arg = DeclareLaunchArgument(
        'render_engine',
        default_value='ogre',
        description='Gazebo 渲染器；VMware 推荐 ogre，实体机可使用 ogre2',
    )
    server_only_arg = DeclareLaunchArgument(
        'server_only',
        default_value='false',
        description='设为 true 仅启动 Gazebo Server，不打开 Gazebo GUI',
    )
    use_gz_ros2_control_arg = DeclareLaunchArgument(
        'use_gz_ros2_control',
        default_value='true',
        description='使用 Jazzy 的 gz_ros2_control 控制器；设为 false 时回退到原生 Gz DiffDrive',
    )

    # Gazebo Classic plugins are unavailable on ROS 2 Jazzy / Gazebo Harmonic.
    robot_description = ParameterValue(
        Command([
            'xacro ', LaunchConfiguration('model'),
            ' use_gazebo_classic:=false',
            ' use_gz_ros2_control:=', LaunchConfiguration('use_gz_ros2_control'),
        ]),
        value_type=str,
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_share, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': [
                IfElseSubstitution(
                    LaunchConfiguration('server_only'),
                    if_value='-s ',
                    else_value='',
                ),
                '-r -v 4 --render-engine ',
                LaunchConfiguration('render_engine'),
                ' ',
                LaunchConfiguration('world'),
            ],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    spawn_fishbot = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_fishbot',
        output='screen',
        parameters=[{
            'world': 'default',
            'name': robot_name,
            'topic': '/robot_description',
            'z': ParameterValue(LaunchConfiguration('spawn_z'), value_type=float),
        }],
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/model/fishbot/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            '/model/fishbot/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/world/default/model/fishbot/joint_state'
            '@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/camera/image@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/image/camera_info'
            '@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        remappings=[
            ('/model/fishbot/cmd_vel', '/cmd_vel'),
            ('/model/fishbot/odometry', '/odom'),
            ('/world/default/model/fishbot/joint_state', '/joint_states'),
        ],
        output='screen',
    )

    # The native Gz DiffDrive system publishes odometry but not a ROS TF
    # transform. Convert that pose into odom -> base_footprint in fallback mode.
    odom_tf_from_gz = ExecuteProcess(
        cmd=[
            'python3',
            os.path.join(
                package_prefix, 'lib', 'fishbot_description',
                'odom_tf_broadcaster.py'),
        ],
        output='screen',
        condition=UnlessCondition(LaunchConfiguration('use_gz_ros2_control')),
    )

    # In ros2_control mode, the differential-drive controller owns the odometry
    # topic. Its name is namespaced by the controller, so bridge that TF source
    # into the conventional odom -> base_footprint link as well.
    odom_tf_from_controller = ExecuteProcess(
        cmd=[
            'python3',
            os.path.join(
                package_prefix, 'lib', 'fishbot_description',
                'odom_tf_broadcaster.py'),
            '--ros-args',
            '-p', 'odom_topic:=/fishbot_diff_drive_controller/odom',
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_gz_ros2_control')),
    )

    # Jazzy's diff_drive_controller consumes TwistStamped.  Keep the tutorial
    # compatible /cmd_vel (Twist) interface by stamping and forwarding it.
    cmd_vel_stamper = ExecuteProcess(
        cmd=[
            'python3',
            os.path.join(
                package_prefix, 'lib', 'fishbot_description',
                'cmd_vel_stamper.py'),
            '--ros-args', '-p', 'use_sim_time:=true',
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_gz_ros2_control')),
    )

    # gz_ros2_control creates controller_manager inside the spawned model.
    # The spawner waits for it, then activates joint states and differential drive.
    start_controllers = TimerAction(
        period=3.0,
        actions=[Node(
            package='controller_manager',
            executable='spawner',
            arguments=[
                'fishbot_joint_state_broadcaster',
                'fishbot_diff_drive_controller',
                '--controller-manager', '/controller_manager',
                '--controller-manager-timeout', '30',
                '--switch-timeout', '30',
                '--activate-as-group',
            ],
            output='screen',
        )],
        condition=IfCondition(LaunchConfiguration('use_gz_ros2_control')),
    )

    # Gazebo sensor messages use scoped sensor names as frame IDs.  These
    # identity aliases connect them to the matching URDF links for RViz.
    sensor_frame_aliases = [
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='laser_sensor_frame_tf',
            arguments=[
                '--frame-id', 'laser_link',
                '--child-frame-id', 'fishbot/base_footprint/laserscan',
            ],
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='imu_sensor_frame_tf',
            arguments=[
                '--frame-id', 'imu_link',
                '--child-frame-id', 'fishbot/base_footprint/imu_sensor',
            ],
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='camera_sensor_frame_tf',
            arguments=[
                '--frame-id', 'camera_link',
                '--child-frame-id', 'fishbot/base_footprint/camera_sensor',
            ],
        ),
    ]

    # Snap-packaged IDEs export GTK / XDG paths from their Core runtime into
    # integrated terminals. Gazebo's GUI must use the host Ubuntu libraries;
    # mixing the Snap Core20 pthread with the host glibc causes a symbol error.
    snap_gui_environment = [
        'GIO_MODULE_DIR',
        'GSETTINGS_SCHEMA_DIR',
        'GTK_EXE_PREFIX',
        'GTK_IM_MODULE_FILE',
        'GTK_MODULES',
        'GTK_PATH',
        'LOCPATH',
        'QT_ACCESSIBILITY',
        'XDG_DATA_HOME',
    ]

    return LaunchDescription([
        model_arg,
        world_arg,
        spawn_z_arg,
        software_rendering_arg,
        render_engine_arg,
        server_only_arg,
        use_gz_ros2_control_arg,
        *[
            UnsetEnvironmentVariable(variable_name)
            for variable_name in snap_gui_environment
        ],
        SetEnvironmentVariable(
            'XDG_DATA_DIRS',
            EnvironmentVariable(
                'XDG_DATA_DIRS_VSCODE_SNAP_ORIG',
                default_value='/usr/local/share:/usr/share',
            ),
        ),
        # Keep the safe software-rendering default, but allow a 3D-enabled VM
        # to opt into the VMware SVGA3D OpenGL driver.
        SetEnvironmentVariable(
            'LIBGL_ALWAYS_SOFTWARE',
            LaunchConfiguration('software_rendering'),
        ),
        SetEnvironmentVariable(
            'GZ_SIM_RESOURCE_PATH',
            [
                os.path.join(package_share, 'world'),
                os.pathsep,
                package_share,
                os.pathsep,
                EnvironmentVariable('GZ_SIM_RESOURCE_PATH', default_value=''),
            ],
        ),
        robot_state_publisher,
        gazebo,
        spawn_fishbot,
        clock_bridge,
        odom_tf_from_gz,
        odom_tf_from_controller,
        cmd_vel_stamper,
        start_controllers,
        *sensor_frame_aliases,
    ])

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    UnsetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 获取与拼接默认路径
    fishbot_navigation2_dir = get_package_share_directory(
        'fishbot_navigation2')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    rviz_config_dir = os.path.join(
        nav2_bringup_dir, 'rviz', 'nav2_default_view.rviz')
    
    default_map_yaml_path = os.path.join(
        fishbot_navigation2_dir, 'map', 'room.yaml')
    default_nav2_param_path = os.path.join(
        fishbot_navigation2_dir, 'config', 'nav2_params.yaml')

    use_sim_time = LaunchConfiguration('use_sim_time')
    map_yaml_path = LaunchConfiguration('map')
    nav2_param_path = LaunchConfiguration('params_file')

    # Snap-packaged IDE terminals export GUI and locale paths from their Core
    # runtime. RViz, ImageMagick, and Nav2 must use the host Ubuntu libraries.
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
        # 声明新的 Launch 参数
        DeclareLaunchArgument('use_sim_time', default_value='true',
                                             description='Use simulation (Gazebo) clock if true'),
        DeclareLaunchArgument('map', default_value=default_map_yaml_path,
                                             description='Full path to map file to load'),
        DeclareLaunchArgument('params_file', default_value=default_nav2_param_path,
                                             description='Full path to param file to load'),

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

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                [nav2_bringup_dir, '/launch', '/bringup_launch.py']),
            # 使用 Launch 参数替换原有参数
            launch_arguments={
                'map': map_yaml_path,
                'use_sim_time': use_sim_time,
                'params_file': nav2_param_path}.items(),
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config_dir],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen'),
    ])

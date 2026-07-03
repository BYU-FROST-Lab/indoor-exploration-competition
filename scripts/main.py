import os, hydra, time, importlib.util
from environment import World
from datetime import datetime
from omegaconf import OmegaConf
import argparse
from robot import Robot
from base_station import BaseStation
from policy import PlanningEngine
from base_policy import BasePolicy
from policies.nearest_frontier import NearestFrontierPolicy
from comm import CommunicationManager
from scoring import base_station_coverage
#from predict import MapPredictor
import matplotlib.pyplot as plt
import numpy as np
from visualizer import save_multi_robot_viz
from matplotlib.colors import LinearSegmentedColormap, ListedColormap


def load_user_policy(policy_path):
    """Load a competition Policy. Defaults to the baseline NearestFrontierPolicy
    if no path is given; otherwise dynamically imports `policy_path` and
    instantiates the `Policy` class it must define (must subclass BasePolicy)."""
    if policy_path is None:
        return NearestFrontierPolicy()
    spec = importlib.util.spec_from_file_location("submitted_policy", policy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Policy"):
        raise ValueError(f"{policy_path} must define a class named 'Policy'")
    policy_cls = module.Policy
    if not issubclass(policy_cls, BasePolicy):
        raise TypeError(f"Policy in {policy_path} must subclass BasePolicy")
    return policy_cls()

def get_options_dict_from_yml(config_name):
    cwd = os.getcwd()
    hydra_config_dir_path = os.path.join(cwd, '../configs')
    print(hydra_config_dir_path)
    with hydra.initialize_config_dir(config_dir=hydra_config_dir_path):
        cfg = hydra.compose(config_name=config_name)
    options_dict = OmegaConf.to_container(cfg)
    options = OmegaConf.create(options_dict)
    return options

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', '1'):
        return True
    if v.lower() in ('no', 'false', 'f', '0'):
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')

def run_exploration(world, comm_manager, max_steps, collect_opts):
    for t in range(max_steps):
        world.t = t

        if t % 50 == 0:
            print(f"timestep {t}/{max_steps}")

        world.step(comm_manager, collect_opts)

        if collect_opts.save_viz:
            save_multi_robot_viz(world, collect_opts, t)


if __name__ == '__main__':
    config_name = 'multi-robot.yaml'
    today = datetime.today()
    parser = argparse.ArgumentParser()
    parser.add_argument('--num_robots', type=int, help='number of robots')
    parser.add_argument('--environment', type=str, help='environment id')
    parser.add_argument('--start_pose', nargs='+', help='List of start pose')
    parser.add_argument('--policy_path', type=str, default=None, help='path to a .py file defining a Policy(BasePolicy) class; defaults to the baseline NearestFrontierPolicy')
    parser.add_argument('--relay_trigger',type=str,default='periodic',help='relay trigger mode: periodic vs information')
    parser.add_argument('--relay_period', type=int, default=200, help='number of timesteps for relaying (periodic)')
    parser.add_argument('--relay_transfer', type=str2bool, default=True, help='relay task transfer to other robots')
    parser.add_argument('--final_relay',type=str2bool,default=True,help='robot goes back to the base station at the end')
    parser.add_argument('--max_steps',type=int,default=1000,help='maximum number of timesteps')
    parser.add_argument('--traj_sharing',type=str2bool,default=True,help='robots share trajectories and plans')
    parser.add_argument('--save_viz', type=str2bool, default=None, help='save visualizations (overrides config)')
    args = parser.parse_args()
    collect_opts = get_options_dict_from_yml(config_name)
    
    root_path = collect_opts.root_path
    dataset_path = os.path.join(root_path, 'test_maps')
    if args.environment is not None:
        collect_opts.environment = str(args.environment)
    environment = collect_opts.environment
    if args.num_robots is not None:
        collect_opts.num_robots = int(args.num_robots)
    num_robots = collect_opts.num_robots

    if args.relay_trigger is not None:
        collect_opts.relay_trigger = args.relay_trigger
    if args.relay_period is not None:
        collect_opts.relay_period = args.relay_period
    relay_period = collect_opts.relay_period

    if args.relay_transfer is not None:
        collect_opts.relay_transfer = args.relay_transfer
    if args.final_relay is not None:
        collect_opts.final_relay = args.final_relay
    if args.save_viz is not None:
        collect_opts.save_viz = args.save_viz
    if args.max_steps is not None:
        collect_opts.max_steps = args.max_steps
    if args.traj_sharing is not None:
        collect_opts.traj_sharing = args.traj_sharing
    max_steps = collect_opts.max_steps

    if args.start_pose is not None:
        sp = []
        for pose_elem in args.start_pose:
            sp.append(int(pose_elem))
        collect_opts.start_pose = sp
    pd_size = collect_opts.pd_size
    start_pose = [collect_opts.start_pose[1] + pd_size, collect_opts.start_pose[0] + pd_size]

    env_path = os.path.join(dataset_path, environment)
    planning_engine = PlanningEngine()
    user_policy = load_user_policy(args.policy_path)
    robots = []
    for i in range(num_robots):
        robot_id = i+1
        start_delay = i*5
        robot = Robot(robot_id, start_pose, planning_engine, user_policy, collect_opts, start_delay)
        robots.append(robot)

    base_station = BaseStation(start_pose)

    world = World(env_path, robots, base_station)
    for robot in world.robots:
        robot.initialize_map(world)
    world.base_station.initialize_map(world)

    comm_manager = CommunicationManager()

    run_exploration(world, comm_manager, max_steps, collect_opts)

    coverage = base_station_coverage(world.base_station, collect_opts)
    print(f"final base-station coverage: {coverage*100:.2f}%")
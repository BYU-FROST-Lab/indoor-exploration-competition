import os
import numpy as np
from skimage.measure import block_reduce
import sys
sys.path.append('../')
from scripts import utils
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

class World:
    def __init__(self, map_dir_path, robots, base_station):
        occmap_path = os.path.join(map_dir_path, 'occ_map.npy')
        valid_path = os.path.join(map_dir_path, 'valid_space.npy')
        self.occ_map = self.get_kth_occ_validspace_map(occmap_path, valid_path)
        self.robots = robots
        self.base_station = base_station
        self.timestep = 0
    
    def step(self, comm_manager, collect_opts):
        for robot in self.robots:
            robot.step(self)

        #communication
        comm_manager.communicate(self.robots, self, collect_opts)

        for robot in self.robots:
            if self.timestep >= robot.start_delay:
                next_pose = robot.policy.plan(robot.combined_obs_map, robot.pose, collect_opts, robot, self.base_station, comm_manager, self)
                self.move(robot, next_pose)

        #base-communication
        comm_manager.base_communicate(self.base_station, self, collect_opts)
        self.timestep += 1

    def move(self, robot, next_pose):
        robot.pose = next_pose
        robot.pose_list = np.concatenate([robot.pose_list, np.atleast_2d(robot.pose)],axis=0)

    def get_kth_occ_validspace_map(self, occ_npy_path, validspace_npy_path):
        block_size_pix = 2
        occ_npy = np.load(occ_npy_path)
        unique_vals = np.unique(occ_npy)
        assert set(unique_vals).issubset({0, 254, 255}), \
        f"unique values in occ_npy should be a subset of {{0, 254, 255}}, got {unique_vals}"
        occ_map = np.zeros_like(occ_npy)
        occ_map[occ_npy == 0] = 1 # occupied
        occ_map[(occ_npy == 254) | (occ_npy == 255)] = 2 # free
        
        occ_map = block_reduce(occ_map, block_size=(block_size_pix, block_size_pix), func=np.min, cval=1)
        assert np.min(occ_map) == 1, "kth_occ_map should be 1 (occupied) or 2 (free). There is unknown..."
        occ_map = utils.convert_012_labels_to_maskutils_labels(occ_map)
   
        laser_range_pix = 200
        occ_map = np.pad(occ_map, int(laser_range_pix), mode='constant', constant_values=00)
        return occ_map
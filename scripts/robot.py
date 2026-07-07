import os
import range_libc
import sys
sys.path.append('../')
from scripts import utils
import numpy as np
from pdb import set_trace as bp
import time
#from lama_pred_utils import convert_obsimg_to_model_input

def makePyOMap(occ_grid):
    return range_libc.PyOMap(occ_grid)

class Robot:
    def __init__(self, id, start_pose, policy, user_policy, collect_opts, start_delay=0):
        self.id = id
        self.pose = np.array(start_pose)
        self.obs_map = None
        self.policy = policy
        self.user_policy = user_policy
        self.collect_opts = collect_opts
        self.lidar_range = self.collect_opts.lidar_range
        self.num_laser = self.collect_opts.num_laser
        self.pixel_per_meter = self.collect_opts.pixel_per_meter
        self.accum_hit_points = np.zeros((0,2)).astype(int)
        self.pose_list = np.atleast_2d(self.pose)
        self.start_delay = start_delay
        self.intent = None
        self.pose_lists_of_others = {}
        self.intents_of_others = {}

        self.locked_frontier_center = None
        self.frontier_region_centers = None
        self.frontier_score_list = None
        self.flood_grid = None

        self.behavior_mode = 'explore'

    def initialize_map(self, world):
        self.gt_map = world.occ_map
        self.obs_map = np.ones(self.gt_map.shape) * 0.5
        self.combined_obs_map = np.ones(self.gt_map.shape)* 0.5
        self.gt_map_pyomap = makePyOMap(self.gt_map)
        self.unreported_mask = np.zeros(self.gt_map.shape, dtype=bool) #False: already reported or unknown
        self.delegated_mask = np.zeros(self.gt_map.shape,dtype=bool) #False: not delegated to other robot

    def observe(self, world):
        obs_dict = self.get_observation_at_pose(self.pose, world.occ_map)
        self.accumulate_obs_given_dict(obs_dict)

    def accumulate_obs_given_dict(self, obs_dict):
        vis_ind = obs_dict['vis_ind']
        actual_hit_points = obs_dict['actual_hit_points']

        self.accum_hit_points = np.concatenate([self.accum_hit_points, actual_hit_points], axis=0)

        #Incremental info gain tracking 
        new_free_mask = (self.combined_obs_map[vis_ind[:, 0], vis_ind[:, 1]] == 0.5)
        new_occ_mask = (self.combined_obs_map[actual_hit_points[:, 0], actual_hit_points[:, 1]] == 0.5)
        self.unreported_mask[vis_ind[new_free_mask, 0], vis_ind[new_free_mask, 1]] = True
        self.unreported_mask[actual_hit_points[new_occ_mask, 0], actual_hit_points[new_occ_mask, 1]] = True
        ####until here

        occ_mask = (self.combined_obs_map == 1)
        self.obs_map[vis_ind[:,0], vis_ind[:,1]] = 0
        self.obs_map[occ_mask] = 1
        self.obs_map[actual_hit_points[:,0], actual_hit_points[:,1]] = 1

        self.combined_obs_map[vis_ind[:,0], vis_ind[:,1]] = 0
        self.combined_obs_map[occ_mask] = 1
        self.combined_obs_map[actual_hit_points[:,0], actual_hit_points[:,1]] = 1

    
    def get_observation_at_pose(self, pose, gt_map):
        vis_ind, _, _, actual_hit_points, _ = utils.get_vis_mask(gt_map, (pose[0], pose[1]),  
                                                                 laser_range=self.lidar_range * self.pixel_per_meter, 
                                                                 num_laser=self.num_laser,
                                                                 occ_map_type='PyOMap', occ_map_obj=self.gt_map_pyomap)
        obs_dict = {
            'vis_ind': vis_ind,
            'actual_hit_points': actual_hit_points
        }
        return obs_dict


    def step(self, world, comm_manager=None):
        self.observe(world)

    def switch_behavior_mode(self, mode1, mode2):
        self.behavior_mode = mode2

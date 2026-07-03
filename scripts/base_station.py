import numpy as np

class BaseStation():
    def __init__(self, start_pose):
        self.obs_map = None
        self.pose = np.array(start_pose)

    def initialize_map(self, world):
        self.gt_map = world.occ_map
        self.obs_map = np.ones(self.gt_map.shape) * 0.5
    
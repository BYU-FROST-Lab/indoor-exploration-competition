import numpy as np
from skimage.draw import line

class CommunicationManager:
    def __init__(self):
        self.comm_graph = None
        self.base_comm_graph = None

    def communicate(self, robots, world, collect_opts):
        num_robots = len(robots)
        self.comm_graph = np.zeros((num_robots, num_robots),dtype=bool)

        for i, r1 in enumerate(robots):
            for j in range(i+1, num_robots):
                r2 = robots[j]
                can_comm = self.communication_function(r1.pose, r2.pose, world.occ_map, collect_opts)
                self.comm_graph[i,j] = can_comm
                self.comm_graph[j,i] = can_comm

        self._share_information(robots)

    
    def _share_information(self, robots):
        if self.comm_graph is None:
            return
        
        for i, r1 in enumerate(robots):
            for j, r2 in enumerate(robots):
                if i < j and self.comm_graph[i,j]:
                    obs_a = r1.combined_obs_map.copy()
                    obs_b = r2.combined_obs_map.copy()
                    combined = np.ones_like(obs_a)*0.5
                    free_indices = np.where((obs_a == 0.0) | (obs_b == 0.0))
                    occ_indices = np.where((obs_a == 1.0) | (obs_b == 1.0))
                    combined[free_indices] = 0.0
                    combined[occ_indices] = 1.0

                    r1.combined_obs_map = combined.copy()
                    r2.combined_obs_map = combined.copy()

                    #unreported_mask: no changes during peer comm
                    #each robot tracks only its own directly-observed cells;
                    #mask only resets when the robot reaches the base station

                    #delegated_mask: restrict to cells still unreported in own mask
                    r1.delegated_mask &= r1.unreported_mask
                    r2.delegated_mask &= r2.unreported_mask
                    #relay robots carry everything themselves — clear delegated
                    if r1.behavior_mode == 'relay' or r1.behavior_mode == 'predpath_relay':
                        r1.delegated_mask[:] = False
                    if r2.behavior_mode == 'relay' or r2.behavior_mode == 'predpath_relay':
                        r2.delegated_mask[:] = False

                    #share pose lists
                    r1.pose_lists_of_others[f'robot{r2.id}'] = r2.pose_list.copy()
                    r2.pose_lists_of_others[f'robot{r1.id}'] = r1.pose_list.copy()

                    #share intents

                    if r1.intent is not None:
                        r2.intents_of_others[f'robot{r1.id}'] = r1.intent.copy()
                    if r2.intent is not None:
                        r1.intents_of_others[f'robot{r2.id}'] = r2.intent.copy()

    def base_communicate(self, base_station, world, collect_opts):
        num_robots = len(world.robots)
        self.base_comm_graph = np.zeros((num_robots,),dtype=bool)

        for i, robot in enumerate(world.robots):
            can_comm = self.communication_function(robot.pose, base_station.pose, world.occ_map, collect_opts)
            self.base_comm_graph[i] = can_comm

        self._share_information_with_base_station(base_station, world)
    
    def _share_information_with_base_station(self, base_station, world):
        for i, robot in enumerate(world.robots):
            if self.base_comm_graph[i]:
                obsmap = robot.combined_obs_map.copy()
                base_obsmap = base_station.obs_map.copy()
                combined_map = np.ones_like(base_obsmap) * 0.5
                free_indices = np.where((obsmap == 0.0) | (base_obsmap == 0.0))
                occ_indices = np.where((obsmap == 1.0) | (base_obsmap == 1.0))
                combined_map[free_indices] = 0.0
                combined_map[occ_indices] = 1.0
                base_station.obs_map = combined_map.copy()
                robot.combined_obs_map = combined_map.copy()

                #unreported_mask update
                robot.unreported_mask[:] = False

                #delegated_mask update
                robot.delegated_mask[:] = False

                #if the behavior mode is relay, switch to explore
                if robot.behavior_mode == 'relay':
                    robot.switch_behavior_mode('relay', 'explore')
                if robot.behavior_mode == 'predpath_relay':
                    robot.pred_front_to_base = False
                    robot.locked_predicted_frontier_center = None
                    robot.best_path_pose_front_base = None
                    robot.switch_behavior_mode('predpath_relay', 'explore')

    def communication_function(self, pose1, pose2, occ_map, collect_opts):
        distance = np.linalg.norm(pose1 - pose2)
        distance = max(distance, 1e-6)
        distance = distance / collect_opts.pixel_per_meter
        if distance > collect_opts.comm_range:
            return False
        rr, cc = line(pose1[0], pose1[1], pose2[0], pose2[1])
        wall_count = np.sum(occ_map[rr, cc] == 1)
        received_power = (
            collect_opts.transmitted_power
            - 10 * collect_opts.path_loss_exponent * np.log10(distance)
            - wall_count * collect_opts.attenuation_constant
        )
        return received_power > collect_opts.power_threshold
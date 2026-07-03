import numpy as np
import pyastar2d
import policy_utils as putils
from base_policy import Observation


class PlanningEngine:
    """Framework-owned planning/execution engine.

    Handles turning a Policy's decisions into actual simulation effects:
    executing movement toward a chosen explore-goal under the fixed
    per-step motion cap, pathing to base while relaying, and applying the
    bookkeeping (mask transfer, mode switches) for a relay hand-off. This is
    provided infrastructure - not part of the competable surface.

    The competable decisions themselves - which goal to explore toward, when
    to switch to relaying, and who to hand relay duty to - live in each
    robot's `user_policy` (a BasePolicy subclass), called from
    `_choose_goal`/`_build_observation` and the 'explore'/'relay' branches
    of `plan` below.
    """

    def __init__(self):
        self.cur_pose_frontier_dist_threshold = 10
        self.dilate_diameter_for_planning = 3
        self.use_distance_transform_for_planning = True
        self.dt_floor_val = 10

    def plan(self, obs_map, pose, collect_opts, robot, base, comm_manager, world):
        occ_grid_pyastar = self.inflated_planning_maps(obs_map, unknown_as_occ=False)

        if robot.behavior_mode == 'explore':
            obs = self._build_observation(robot, base, comm_manager, collect_opts)
            new_mode = robot.user_policy.should_relay(obs, collect_opts, world.t, collect_opts.max_steps)
            if new_mode in ('relay', 'final_relay'):
                robot.switch_behavior_mode('explore', new_mode)

        if robot.behavior_mode == 'explore':
            if robot.locked_frontier_center is not None:
                if np.linalg.norm(robot.locked_frontier_center - pose) < self.cur_pose_frontier_dist_threshold:
                    robot.locked_frontier_center = None
            if not self.is_locked_frontier_center_valid(robot.locked_frontier_center, occ_grid_pyastar, pose):
                robot.locked_frontier_center = self._choose_goal(robot, base, comm_manager, occ_grid_pyastar, pose, collect_opts)
            local_path = None
            if robot.locked_frontier_center is not None:
                local_path = pyastar2d.astar_path(occ_grid_pyastar, pose, robot.locked_frontier_center, allow_diagonal=False)
            if local_path is None:
                local_path = np.atleast_2d(pose)  # nowhere reachable to explore right now; stay put
        elif robot.behavior_mode == 'relay':
            robot.locked_frontier_center = None
            local_path = pyastar2d.astar_path(occ_grid_pyastar, pose, base.pose, allow_diagonal=False)
            if collect_opts.relay_transfer:
                obs = self._build_observation(robot, base, comm_manager, collect_opts)
                handoff_id = robot.user_policy.decide_relay_handoff(obs, collect_opts)
                if handoff_id is not None and handoff_id != robot.id:
                    target_robot = next((r for r in world.robots if r.id == handoff_id), None)
                    if target_robot is not None:
                        #delegate mask update
                        robot.delegated_mask |= robot.unreported_mask
                        robot.switch_behavior_mode('relay', 'explore')
                        target_robot.switch_behavior_mode('explore', 'relay')
                        target_robot.unreported_mask |= robot.unreported_mask
                        target_robot.delegated_mask &= ~target_robot.unreported_mask
        elif robot.behavior_mode == 'final_relay':
            robot.locked_frontier_center = None
            local_path = pyastar2d.astar_path(occ_grid_pyastar, pose, base.pose, allow_diagonal=False)

        robot.intent = local_path
        local_plan_x = local_path[:,0]
        local_plan_y = local_path[:,1]
        next_pose = self.pseudo_traj_planner(local_plan_x, local_plan_y, 3)
        return next_pose

    def _build_observation(self, robot, base, comm_manager, collect_opts):
        connected_robot_ids = []
        if comm_manager.comm_graph is not None:
            connected_robot_ids = [int(i) + 1 for i in np.where(comm_manager.comm_graph[robot.id - 1, :])[0]]
        return Observation(
            combined_obs_map=robot.combined_obs_map,
            pose=robot.pose,
            unreported_mask=robot.unreported_mask,
            delegated_mask=robot.delegated_mask,
            pose_lists_of_others=robot.pose_lists_of_others,
            intents_of_others=robot.intents_of_others,
            base_pose=base.pose,
            pd_size=collect_opts.pd_size,
            connected_robot_ids=connected_robot_ids,
        )

    def _choose_goal(self, robot, base, comm_manager, occ_grid_pyastar, pose, collect_opts):
        """Ask the participant's policy for an explore-goal and validate it's
        reachable. Falls back to the nearest reachable frontier (using the
        provided toolkit) if the policy returns nothing usable."""
        obs = self._build_observation(robot, base, comm_manager, collect_opts)
        goal = robot.user_policy.decide(obs, collect_opts)
        if goal is not None:
            goal = np.asarray(goal, dtype=int)
            if occ_grid_pyastar[goal[0], goal[1]] != np.inf and \
               pyastar2d.astar_path(occ_grid_pyastar, pose, goal, allow_diagonal=False) is not None:
                return goal

        frontiers = putils.get_frontiers(robot.combined_obs_map)
        if not frontiers:
            return None
        frontiers = sorted(frontiers, key=lambda c: np.linalg.norm(np.asarray(c) - pose))
        for center in frontiers:
            if occ_grid_pyastar[center[0], center[1]] == np.inf:
                continue
            if pyastar2d.astar_path(occ_grid_pyastar, pose, center, allow_diagonal=False) is not None:
                return center
        return None

    def pseudo_traj_planner(self, plan_x, plan_y, plan_ind_to_use=3):
        plan_ind_to_use = np.min([plan_ind_to_use, len(plan_x)-1])
        next_pose = np.array([plan_x[plan_ind_to_use], plan_y[plan_ind_to_use]]).astype(int)
        return next_pose

    def estimate_time_for_path(self, local_path, plan_ind_to_use=3):
        return putils.estimate_time_for_path(local_path, plan_ind_to_use)

    def inflated_planning_maps(self, obs_map, unknown_as_occ=False):
        return putils.inflate_map(
            obs_map,
            dilate_diameter=self.dilate_diameter_for_planning,
            use_distance_transform=self.use_distance_transform_for_planning,
            dt_floor_val=self.dt_floor_val,
            unknown_as_occ=unknown_as_occ,
        )

    def is_locked_frontier_center_valid(self, locked_frontier_center, occ_grid_pyastar, cur_pose):
        if locked_frontier_center is None:
            return False
        if occ_grid_pyastar[locked_frontier_center[0], locked_frontier_center[1]] == np.inf:
            return False
        if np.linalg.norm(locked_frontier_center - cur_pose) < self.cur_pose_frontier_dist_threshold:
            return False
        return True

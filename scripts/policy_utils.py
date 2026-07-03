"""Provided planning utilities.

These are available to both the framework (PlanningEngine) and to
competition policies. Nothing here depends on ground truth - every function
operates only on the data a single robot has legitimately observed or
received over communication.
"""
import math
import numpy as np
import scipy
import pyastar2d
from scipy.ndimage import convolve, label, generate_binary_structure, binary_dilation


def get_frontiers(obs_map, region_size_threshold=10):
    """Return candidate frontier points (row, col) between known-free and unknown space."""
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
    edge_cells = convolve((obs_map == 0.5).astype(int), kernel) > 0
    edge_cells = edge_cells & (obs_map == 0)

    structure = generate_binary_structure(2, 2)
    frontier_regions, num_regions = label(edge_cells, structure)

    region_sizes = np.bincount(frontier_regions.ravel())
    large_regions = region_sizes > region_size_threshold
    large_regions[0] = False

    frontier_region_centers = []
    for i in range(1, num_regions + 1):
        if large_regions[i]:
            region_i = np.argwhere(frontier_regions == i)
            region_center = np.mean(region_i, axis=0)
            dist_to_center = np.linalg.norm(region_i - region_center, axis=1)
            closest_point_to_center = region_i[np.argmin(dist_to_center)]
            frontier_region_centers.append(closest_point_to_center)

    return frontier_region_centers


def crowding_avoidance_penalty(candidate_centers, scores, pose_lists_of_others, intents_of_others, collect_opts):
    """Optional helper: penalize candidates too close to other robots' known
    trajectories/intents (as shared over comm), to reduce redundant coverage.

    Returns a new scores array; does not mutate the input.
    """
    scores = np.array(scores, dtype=float)
    candidate_centers = np.array(candidate_centers)

    if pose_lists_of_others:
        for i, center in enumerate(candidate_centers):
            min_d = np.inf
            for pose_list_of_other in pose_lists_of_others.values():
                if pose_list_of_other is not None and len(pose_list_of_other) > 0:
                    dists = np.linalg.norm(np.array(pose_list_of_other) - center, axis=1)
                    min_d = min(min_d, np.min(dists))
            if np.isfinite(min_d) and min_d < collect_opts.other_traj_threshold * collect_opts.pixel_per_meter:
                scores[i] -= 1_000_000

    if intents_of_others:
        for i, center in enumerate(candidate_centers):
            min_d = np.inf
            for intent in intents_of_others.values():
                if intent is not None:
                    d = np.linalg.norm(intent - center, axis=1)
                    min_d = min(min_d, np.min(d))
            if np.isfinite(min_d) and min_d < collect_opts.other_intent_threshold * collect_opts.pixel_per_meter:
                scores[i] -= 100_000

    return scores


def inflate_map(occ_map, dilate_diameter=3, use_distance_transform=True, dt_floor_val=10, unknown_as_occ=False):
    """Inflate obstacles for safe A* planning and bias the cost field by distance-to-obstacle."""
    dilated = occ_map.copy()
    inverted_binary = occ_map.copy() > 0.5
    inverted_dilated = binary_dilation(inverted_binary, structure=np.ones((dilate_diameter, dilate_diameter)))
    dilated[inverted_dilated] = 1
    planning_grid = np.zeros(dilated.shape, dtype=np.float32)

    if use_distance_transform:
        distance_transform = scipy.ndimage.distance_transform_cdt(dilated == 0) * -1
        biased = np.clip(distance_transform + dt_floor_val, 1, dt_floor_val)
        if unknown_as_occ:
            free_mask = (dilated == 0)
            planning_grid[free_mask] = biased[free_mask]
            planning_grid[dilated > 0] = np.inf
        else:
            free_or_unknown = (dilated >= 0)
            planning_grid[free_or_unknown] = biased[free_or_unknown]
            planning_grid[dilated == 1] = np.inf
    else:
        if unknown_as_occ:
            planning_grid[dilated == 0] = 1
            planning_grid[dilated > 0] = np.inf
        else:
            planning_grid[dilated >= 0] = 1
            planning_grid[dilated == 1] = np.inf
    return planning_grid


def estimate_time_for_path(local_path, plan_ind_to_use=3):
    n_points = len(local_path)
    return math.ceil((n_points - 1) / plan_ind_to_use)


def default_should_relay(obs, collect_opts, t, max_steps):
    """Default relay-trigger strategy, used unless a Policy overrides
    should_relay(): a periodic switch every relay_period steps, plus (if
    final_relay is enabled) a safety trigger near the end of the run that
    forces a return to base regardless of the periodic schedule.
    """
    if collect_opts.final_relay:
        time_left = max_steps - t
        if time_left < collect_opts.relay_period:
            occ_grid = inflate_map(obs.combined_obs_map)
            path = pyastar2d.astar_path(occ_grid, obs.pose, obs.base_pose, allow_diagonal=False)
            if path is not None:
                estimated_time_to_base = estimate_time_for_path(path)
                safety_buffer = 10
                if time_left <= estimated_time_to_base + safety_buffer:
                    return 'final_relay'

    if collect_opts.relay_trigger == 'periodic':
        if t % collect_opts.relay_period == 0 and t > 0:
            return 'relay'

    return None


def default_relay_handoff(obs, collect_opts):
    """Default relay-handoff strategy, used unless a Policy overrides
    decide_relay_handoff(): among currently-connected robots that are closer
    to base than you are, hand off to the nearest one to you.
    """
    if not obs.connected_robot_ids:
        return None

    candidates = []
    for rid in obs.connected_robot_ids:
        pose_list = obs.pose_lists_of_others.get(f'robot{rid}')
        if pose_list is not None and len(pose_list) > 0:
            candidates.append((rid, np.asarray(pose_list[-1])))
    if not candidates:
        return None

    robot_to_base = np.linalg.norm(obs.pose - obs.base_pose)
    closer = [(rid, p) for rid, p in candidates if np.linalg.norm(p - obs.base_pose) < robot_to_base]
    if not closer:
        return None

    closer.sort(key=lambda rp: np.linalg.norm(rp[1] - obs.pose))
    return closer[0][0]

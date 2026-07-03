import numpy as np
from base_policy import BasePolicy
from policy_utils import get_frontiers, crowding_avoidance_penalty


class NearestFrontierPolicy(BasePolicy):
    """Baseline reference policy: go to the nearest frontier, penalizing
    frontiers close to other robots' known trajectories/intents (opt-in
    crowding_avoidance_penalty utility) to reduce redundant coverage."""

    def decide(self, obs, collect_opts):
        frontiers = get_frontiers(obs.combined_obs_map)
        if not frontiers:
            return None
        frontiers = np.array(frontiers)
        distances = np.linalg.norm(frontiers - obs.pose, axis=1)
        scores = -distances
        scores = crowding_avoidance_penalty(
            frontiers, scores, obs.pose_lists_of_others, obs.intents_of_others, collect_opts
        )
        return frontiers[np.argmax(scores)]

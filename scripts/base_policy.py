import policy_utils as putils


class Observation:
    """Sanitized per-robot view of the world.

    Contains only what this robot has directly sensed or received over
    communication - never ground truth. This is what a competition Policy's
    methods receive; they never see the World object or occ_map.
    """

    def __init__(self, combined_obs_map, pose, unreported_mask, delegated_mask,
                 pose_lists_of_others, intents_of_others, base_pose, pd_size,
                 connected_robot_ids=None):
        self.combined_obs_map = combined_obs_map
        self.pose = pose
        self.unreported_mask = unreported_mask
        self.delegated_mask = delegated_mask
        self.pose_lists_of_others = pose_lists_of_others
        self.intents_of_others = intents_of_others
        self.base_pose = base_pose
        self.pd_size = pd_size
        # robot ids this robot is currently (this timestep) in comm range of -
        # not just ones it has ever shared info with, so pose_lists_of_others
        # entries for these ids are guaranteed fresh, not stale.
        self.connected_robot_ids = connected_robot_ids if connected_robot_ids is not None else []


class BasePolicy:
    """Subclass this to compete. All three methods are optional to override
    except decide() - everything not overridden falls back to the provided
    baseline behavior, so you can compete on exploration only, relay
    strategy only, both, or neither.
    """

    def decide(self, obs: Observation, collect_opts):
        """Return a (row, col) goal position for the robot to explore toward.

        Called only while a robot is exploring (behavior_mode == 'explore')
        and only when it needs a new goal (its current one was reached or
        became invalid) - not every timestep.

        May return None if no goal can be determined; the framework will
        fall back to the nearest reachable frontier in that case.
        """
        raise NotImplementedError

    def should_relay(self, obs: Observation, collect_opts, t, max_steps):
        """Called every timestep while a robot is exploring. Return 'relay'
        or 'final_relay' to switch modes now, or None to keep exploring.

        Optional to override - the default reproduces the provided
        periodic/final-only relay strategy (see policy_utils.default_should_relay).
        """
        return putils.default_should_relay(obs, collect_opts, t, max_steps)

    def decide_relay_handoff(self, obs: Observation, collect_opts):
        """Called while this robot is relaying and collect_opts.relay_transfer
        is enabled. `obs.connected_robot_ids` lists robots currently in comm
        range. Return a robot id to hand relay duty to, or None to keep
        relaying yourself.

        Optional to override - the default hands off to the nearest
        connected robot that is closer to base than you are (see
        policy_utils.default_relay_handoff).
        """
        return putils.default_relay_handoff(obs, collect_opts)

# Indoor Exploration Competition

Multi-robot (and single-robot) indoor exploration and relaying under
communication constraints. Robots explore an unknown environment using only
local sensing and limited peer-to-peer communication, and must get what
they've learned back to a fixed base station. **What you write is the
policy** — exploration strategy, and optionally relay strategy too.
Everything else (sensing, motion, communication, the environment) is
provided and identical for every submission.

## Environment setup

```bash
conda env create -f environment.yml
conda activate iig
```

After installing and activating `iig` environment, build from source to install `range_libc`. 

```
cd range_libc/pywrapper

# Install build dependencies (if needed)
conda install -y cython

# Build and install
python3 setup.py install

# Verify installation
cd ../..
python3 -c "import range_libc; print('range_libc installed successfully')"
```

## Quick start

From the `scripts/` directory:

```bash
cd scripts
python3 main.py
```

This runs the simulation defined by `configs/multi-robot.yaml` using the
baseline `NearestFrontierPolicy`. To run your own policy instead:

```bash
python3 main.py --policy_path /path/to/your_policy.py
```

## What's provided (do not modify)

These implement the simulation itself and are the same for every
participant:

| File | What it does |
|---|---|
| `scripts/environment.py` | The `World`: environment/map representation and the main per-timestep loop |
| `scripts/robot.py` | Robot state, raycast-based sensing, motion execution |
| `scripts/comm.py` | The communication model (range, walls, signal attenuation) and info-sharing between robots/base station |
| `scripts/base_station.py` | The base station |
| `scripts/policy.py` (`PlanningEngine`) | Turns your policy's decisions into actual simulation effects: executing movement under the fixed per-step speed cap, pathing to base while relaying, and applying the bookkeeping (mask transfer, mode switches) once a relay hand-off is decided |
| `scripts/main.py` | Simulation entry point and CLI |
| `scripts/visualizer.py` | Per-timestep visualization |
| `scripts/scoring.py` | Scoring metric |

## What you implement

You write a `Policy` class with up to three decisions, all made per-robot:

- **`decide()`** (required) — where to explore next.
- **`should_relay()`** (optional) — when to switch from exploring to relaying info back to base.
- **`decide_relay_handoff()`** (optional) — while relaying, whether to hand relay duty off to a nearer connected robot, and to whom.

If you don't override `should_relay()`/`decide_relay_handoff()`, you get the
provided baseline behavior for free: periodic relaying every `relay_period`
steps (plus an end-of-run safety trigger, `final_relay`), and handoff to the
nearest currently-connected robot that's closer to base than you. Override
either or both to compete on relay strategy as well as exploration.

1. Copy `scripts/policies/nearest_frontier.py` as a starting point, or start from scratch.
2. Subclass `BasePolicy` (`scripts/base_policy.py`) and implement `decide()`
   (and optionally `should_relay()`/`decide_relay_handoff()`):

   ```python
   from base_policy import BasePolicy

   class Policy(BasePolicy):
       def decide(self, obs, collect_opts):
           # obs: your robot's own sanitized view of the world (see below)
           # return: a (row, col) goal position to explore toward
           ...

       # optional — omit to use the provided periodic/final-only default
       def should_relay(self, obs, collect_opts, t, max_steps):
           # return 'relay', 'final_relay', or None to keep exploring
           ...

       # optional — omit to use the provided nearest-closer-robot default
       def decide_relay_handoff(self, obs, collect_opts):
           # return a robot id from obs.connected_robot_ids to hand off to, or None
           ...
   ```

3. Run it with `python3 main.py --policy_path your_policy.py`. Your file must
   define a class named exactly `Policy`.

`decide()` is only called while a robot is in `explore` mode, and only when
it needs a new goal (i.e. its current goal was reached or is no longer
valid) — not every single timestep. `should_relay()` is checked every
timestep while exploring. `decide_relay_handoff()` is checked every timestep
while relaying (only if `relay_transfer` is enabled in the config).

### What `obs` (the `Observation`) contains

Only what your robot has legitimately sensed or received over
communication — never ground truth:

- `obs.combined_obs_map` — your robot's own map so far (unknown / free / occupied)
- `obs.pose` — your robot's current position
- `obs.unreported_mask`, `obs.delegated_mask` — bookkeeping on what's been observed but not yet reported to base
- `obs.pose_lists_of_others`, `obs.intents_of_others` — other robots' trajectories/intents, as last shared over comm (may be stale if out of range)
- `obs.base_pose` — the base station's position (always known)
- `obs.connected_robot_ids` — robot ids currently (this timestep) in comm range, so entries for them in `pose_lists_of_others` are guaranteed fresh, not stale — useful for `decide_relay_handoff()`

### Your goal doesn't have to be frontier-based

Any exploration strategy is allowed (frontier-based, sampling-based,
potential-field, learned, etc.) as long as it only uses `obs`. Returning
`None` from `decide()` is a legitimate way to say "no opinion" - the
framework falls back to the nearest reachable frontier in that case. But if
you return a specific goal, it has to actually be reachable: an
unreachable, occupied, out-of-bounds, or malformed goal raises
`InvalidGoalError` and halts the run immediately, rather than being
silently patched up for you.

### Provided utility toolkit (`scripts/policy_utils.py`)

Optional helpers you can use inside `decide()`, or ignore entirely:

- `get_frontiers(obs_map)` — candidate frontier points between known-free and unknown space
- `crowding_avoidance_penalty(...)` — penalize candidates near other robots' known trajectories/intents, to reduce redundant coverage
- `inflate_map(occ_map)` — an inflated/cost-biased map, useful if you want to reason about path cost yourself
- `estimate_time_for_path(path)` — estimate how many timesteps a path will take
- `default_should_relay(...)` / `default_relay_handoff(...)` — the provided relay-strategy baselines themselves; call these from your own `should_relay()`/`decide_relay_handoff()` if you want to build on top of the default instead of replacing it entirely

## Config file (`configs/multi-robot.yaml`)

Controls the scenario every policy is evaluated on: which environment map,
number of robots, max timesteps, sensing range, communication model
parameters (range, attenuation, power threshold), and visualization options.
`relay_trigger`/`relay_period`/`final_relay`/`relay_transfer` configure the
*default* relay behavior (used unless your policy overrides `should_relay()`/
`decide_relay_handoff()`). Most fields can also be overridden from the
command line — run `python3 main.py --help` for the full list.

## Scoring

At the end of a run, `main.py` prints the final **base-station coverage**:
the fraction of the true map the base station has learned about by
`max_steps`. This rewards actually getting information home, not just
observing it — so both exploration and relay strategy matter for score.

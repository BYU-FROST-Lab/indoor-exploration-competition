import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap, to_rgb
from datetime import datetime
import cv2
import utils

def save_multi_robot_viz(world, collect_opts, t):
    """Visualize multi-robot maps and trajectories at timestep t."""
    # --- Directory setup ---
    today = datetime.today()
    output_subdir = f"{today.year}{today.month:02d}{today.day:02d}_test"
    output_root_dir = os.path.join(collect_opts.root_path, 'experiments', output_subdir)
    os.makedirs(output_root_dir, exist_ok=True)

    exp_title = 'map_' + collect_opts.environment + '_Num' + str(collect_opts.num_robots) + \
        '_start' + str(collect_opts.start_pose[0]) + '_' + str(collect_opts.start_pose[1])


    policy_name = world.robots[0].user_policy.__class__.__name__ if world.robots else 'unknown'
    exp_title += '_method_' + policy_name + '_relaytrigger_' + collect_opts.relay_trigger
    if collect_opts.relay_trigger == 'periodic':
        exp_title += '_period'+str(collect_opts.relay_period)
    exp_title = exp_title + '_relaytransfer' + str(collect_opts.relay_transfer) +'_finalrelay' + str(collect_opts.final_relay)
    if not collect_opts.traj_sharing:
        exp_title = exp_title + '_trajsharingFalse'
    
    exp_dir = os.path.join(output_root_dir, exp_title)
    os.makedirs(exp_dir, exist_ok=True)
    run_viz_dir = os.path.join(exp_dir, 'run_viz')
    base_viz_dir = os.path.join(exp_dir, 'base_viz')
    os.makedirs(run_viz_dir, exist_ok=True)
    os.makedirs(base_viz_dir, exist_ok=True)
    if collect_opts.viz_video:
        video_viz_dir = os.path.join(exp_dir, 'video_viz')
        os.makedirs(video_viz_dir, exist_ok=True)

    if t % collect_opts.viz_freq == 0:
        # --- Figure setup ---
        robots = world.robots
        n_robots = len(robots)
        pd_size = collect_opts.pd_size
        combined_obsmap_colors_ = ["#FFFFFF", "#D8D8D8", "#000000"]
        combined_obs_cmap = ListedColormap(combined_obsmap_colors_)


        # Dynamically compute subplot grid
        n_panels = n_robots + 1
        n_cols = int(np.ceil(np.sqrt(n_panels)))
        n_rows = int(np.ceil(n_panels / n_cols))
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(4*n_cols, 4*n_rows))
        #if n_panels == 1:
        #    axes = np.array([axes])  # handle single-robot case
        axes = axes.flatten()

        # Per-robot trajectory colors — no orange (reserved for locked frontier marker)
        ROBOT_TRAJ_COLORS = ['red', '#7B3F00', '#00008B', 'black', '#006400']
        OBSERVED_OVERLAY_COLOR = '#6CA6E0'  # light blue, same for every robot's observed-map overlay

        if collect_opts.viz_gt_map:
            gt_map = world.occ_map[pd_size:-pd_size, pd_size:-pd_size]

        # --- Draw each robot ---
        for i, robot in enumerate(robots):
            ax = axes[i]
            traj_color = ROBOT_TRAJ_COLORS[(robot.id - 1) % len(ROBOT_TRAJ_COLORS)]
            obs_map = robot.combined_obs_map[pd_size:-pd_size, pd_size:-pd_size]
            if collect_opts.viz_gt_map:
                ax.imshow(gt_map, cmap=combined_obs_cmap, origin='upper')
                observed_overlay = np.zeros((*obs_map.shape, 4))
                observed_overlay[obs_map != 0.5] = (*to_rgb(OBSERVED_OVERLAY_COLOR), 0.25)
                ax.imshow(observed_overlay, origin='upper')
            else:
                ax.imshow(obs_map, cmap=combined_obs_cmap, origin='upper')

            if collect_opts.viz_comm:
                comm_area = visualize_comm_range([robot.pose[0]-pd_size,robot.pose[1]-pd_size],world.occ_map[pd_size:-pd_size,pd_size:-pd_size],collect_opts)
                red = '#FF0000'
                comm_mask_colors = [red,red]
                comm_mask_cmap = LinearSegmentedColormap.from_list('mask_red',comm_mask_colors,N=2)
                comm_mask_alpha = np.zeros_like(comm_area, dtype=float)
                comm_mask_alpha[comm_area ==1] = 0.2
                ax.imshow(comm_area,cmap=comm_mask_cmap, alpha=comm_mask_alpha)
                    
            #base station
            base_pose = world.base_station.pose
            ax.scatter(base_pose[1]-pd_size, base_pose[0]-pd_size, c='black', marker='^',s=20)

            #robot pose
            robot_pose = robot.pose
            #ax.scatter(robot_pose[1]-pd_size, robot_pose[0]-pd_size, c='red', marker='o',s=20)
            ax.scatter(robot.pose[1] - pd_size, robot.pose[0] - pd_size, c=traj_color, s=80, zorder=10, marker='o', linewidths=1.5, edgecolors='black')

            # trajectory
            if hasattr(robot, 'pose_list') and len(robot.pose_list) > 0:
                poses = np.array(robot.pose_list)
                ax.plot(poses[:,1]-pd_size, poses[:,0]-pd_size, c=traj_color, alpha=1.0, label='trajectory')

            # frontiers (red x)
            if getattr(robot, 'frontier_region_centers', None) is not None:
                frontiers = np.array(robot.frontier_region_centers)
                #ax.scatter(frontiers[:,1]-pd_size, frontiers[:,0]-pd_size, marker='x', c='g', s=7, label='frontier')

            if getattr(robot, 'best_path_pose_front_base', None) is not None:
                path_pose_front_base = robot.best_path_pose_front_base
                #ax.plot(path_pose_front_base[:,1]-pd_size, path_pose_front_base[:,0]-pd_size, c='green',alpha=1.0,linestyle='--')
            
            if getattr(robot, 'locked_predicted_frontier_center', None) is not None:
                pass
                #ax.scatter(robot.locked_predicted_frontier_center[1]-pd_size, robot.locked_predicted_frontier_center[0]-pd_size, c='blue', marker='^',s=20)
            


            #visualize other robots' trajectories and intents
            visualize_others = True
            if visualize_others:
                if getattr(robot, 'pose_lists_of_others') is not None:
                    for other_id, pose_list_of_other in robot.pose_lists_of_others.items():
                        other_color = ROBOT_TRAJ_COLORS[(int(other_id.replace('robot', '')) - 1) % len(ROBOT_TRAJ_COLORS)]
                        ax.plot(pose_list_of_other[:,1]-pd_size, pose_list_of_other[:,0]-pd_size, c=other_color, alpha=0.6, linestyle='--', label='trajectory')
                        ax.scatter(pose_list_of_other[-1,1] - pd_size, pose_list_of_other[-1,0] - pd_size, c=other_color, s=40, zorder=9, marker='o', linewidths=1.0, edgecolors='black')
                #if getattr(robot, 'intents_of_others') is not None:
                #    for _, other_intent in robot.intents_of_others.items():
                #        ax.plot(other_intent[:,1]-pd_size, other_intent[:,0]-pd_size, c='black', alpha=0.6, linestyle='-.')

            ax.set_title(f"Robot {robot.id}", fontsize=11)

            #ax.axis('off')

        base_ax = axes[n_robots]
        base_map = world.base_station.obs_map[pd_size:-pd_size, pd_size:-pd_size]
        base_ax.imshow(base_map, cmap=combined_obs_cmap, origin='upper')
        base_ax.set_title("Base Station", fontsize=12)

        # hide unused axes
        for j in range(i+1, len(axes)):
            axes[j].axis('off')

        plt.tight_layout()
        out_path = os.path.join(run_viz_dir, f"{t:04d}.png")
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
    
        cv2.imwrite(base_viz_dir + '/{}.png'.format(str(t).zfill(4)), utils.convert_01_single_channel_to_0_255_3_channel(world.base_station.obs_map))
    
    if collect_opts.viz_video:
        pd_size = collect_opts.pd_size
        combined_obsmap_colors_ = ["#FFFFFF", "#D8D8D8", "#000000"]
        combined_obs_cmap = ListedColormap(combined_obsmap_colors_)

        fig, ax = plt.subplots(1, 1, figsize=(6, 6))
        gt_map = world.occ_map[pd_size:-pd_size, pd_size:-pd_size]
        ax.imshow(gt_map, cmap=combined_obs_cmap, origin='upper')

        # Overlay base station observed map on top of GT
        base_map = world.base_station.obs_map[pd_size:-pd_size, pd_size:-pd_size]
        base_rgba = np.zeros((*base_map.shape, 4), dtype=float)
        base_rgba[base_map < 0.3] = [1.0, 0.85, 0.4, 0.5]   # free → light yellow-orange
        base_rgba[base_map > 0.7] = [0.0, 0.0, 0.0, 0.7]    # occupied → black
        ax.imshow(base_rgba, origin='upper')

        #robot_colors = ['red', '#7B3F00', '#00008B',  '#006400', 'black']
        robot_colors = ['red', 'blue', 'green', '#7B3F00']
        for i, robot in enumerate(world.robots):
            color = robot_colors[(robot.id - 1) % len(robot_colors)]
            if hasattr(robot, 'pose_list') and len(robot.pose_list) > 0:
                poses = np.array(robot.pose_list)
                ax.plot(poses[:, 1] - pd_size, poses[:, 0] - pd_size, c=color, alpha=1.0, linewidth=1.5)
            ax.scatter(robot.pose[1] - pd_size, robot.pose[0] - pd_size, c=color, marker='o', s=30, zorder=5)

        #ax.set_title(f"t={t}", fontsize=12)
        ax.axis('off')
        plt.tight_layout()
        out_path = os.path.join(video_viz_dir, f"{t:04d}.png")
        plt.savefig(out_path, dpi=150)
        plt.close(fig)


def visualize_comm_range(robot_pose, occ_map, collect_opts):
    h, w = occ_map.shape
    max_range = int(min(h, w, collect_opts.comm_range * collect_opts.pixel_per_meter))
    n_angles = 720  # 0.5 degree resolution
    angles = np.linspace(0, 2*np.pi, n_angles)
    x, y = robot_pose
    r = np.arange(max_range)

    dx = np.cos(angles)
    dy = np.sin(angles)
    xi = np.round(x + np.outer(dx, r)).astype(int)
    yi = np.round(y + np.outer(dy, r)).astype(int)
    valid = (xi >= 0) & (xi < h) & (yi >= 0) & (yi < w)
    xi_c = np.clip(xi, 0, h-1)
    yi_c = np.clip(yi, 0, w-1)

    occ_vals = np.where(valid, occ_map[xi_c, yi_c], 0)
    wall_count = np.cumsum(occ_vals == 1, axis=1)
    distance = np.maximum(r / collect_opts.pixel_per_meter, 1e-6)
    received_power = (
        collect_opts.transmitted_power
        - 10 * collect_opts.path_loss_exponent * np.log10(distance)[None, :]
        - wall_count * collect_opts.attenuation_constant
    )
    # signal strictly weakens with range, so once a ray drops below threshold
    # every farther point on that ray is unreachable too (matches the old break-on-fail loop)
    reachable = np.cumprod((received_power > collect_opts.power_threshold) & valid, axis=1).astype(bool)

    comm_mask = np.zeros((h, w), dtype=np.uint8)
    ai, ri = np.where(reachable)
    comm_mask[xi_c[ai, ri], yi_c[ai, ri]] = 1
    return comm_mask
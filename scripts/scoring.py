import numpy as np


def base_station_coverage(base_station, collect_opts):
    """Fraction of the true map area the base station currently knows about.

    Ground truth has no 'unknown' cells, so coverage is simply the fraction
    of the base station's map that is no longer unknown (0.5), cropped to
    the real map area (excluding the laser-range padding border).
    """
    pd_size = collect_opts.pd_size
    obs = base_station.obs_map[pd_size:-pd_size, pd_size:-pd_size]
    return float(np.mean(obs != 0.5))

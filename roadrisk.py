# Load roads from backend/roads_with_risk.json when available so the full set
# is present without manually pasting large arrays. Each record in that file
# may contain `id`, `length`, and `avg_elevation`. We synthesize `min_elev`/`max_elev`
# when missing by creating a small range around `avg_elevation`.
import os, json

def _load_roads_from_backend():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend'))
    path = os.path.join(base, 'roads_with_risk.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception:
        return None
    out = []
    for r in data:
        avg = r.get('avg_elevation') or r.get('avg_elev') or None
        length = r.get('length') or 0.0
        rid = r.get('id')
        # synthesize min/max if not present
        min_e = r.get('min_elev')
        max_e = r.get('max_elev')
        if avg is not None and (min_e is None or max_e is None):
            try:
                a = float(avg)
                min_e = a - 0.5 if min_e is None else float(min_e)
                max_e = a + 0.5 if max_e is None else float(max_e)
            except Exception:
                min_e = min_e or 0.0
                max_e = max_e or 0.0
        out.append({
            'id': str(rid),
            'length': float(length),
            'avg_elevation': avg,
            'min_elev': min_e,
            'max_elev': max_e
        })
    return out


roads = _load_roads_from_backend() or []


# Use the user's requested normalization and weights
RAIN_WEIGHT = 0.55
ELEV_WEIGHT = 0.25
FLAT_WEIGHT = 0.20


def normalize_rain(mm_per_hr, max_rain=50.0):
	"""Normalize rainfall (mm/hr) to 0..1 using a reasonable max value."""
	try:
		mm = float(mm_per_hr)
	except Exception:
		mm = 0.0
	return max(0.0, min(1.0, mm / float(max_rain)))


def compute_road_risk(road, rain_mm=50.0):
	"""Compute risk (0..1) and categorical level for a single road using
	the user's formula.
	Returns: (risk_float, level_str)
	"""
	rain_norm = normalize_rain(rain_mm)

	length = float(road.get('length') or 0.0)
	min_elev = float(road.get('min_elev') or 0.0)
	max_elev = float(road.get('max_elev') or 0.0)
	avg_elev = float(road.get('avg_elevation') or 0.0)

	# slope = (max - min) / length ; guard division by zero
	slope = 0.0
	if length > 0 and (max_elev - min_elev) >= 0:
		slope = (max_elev - min_elev) / length
	slope = max(0.0, min(1.0, slope))
	flatness = 1.0 - slope

	# normalized elevation within its min/max range; guard zero range
	if max_elev - min_elev > 0:
		norm_elev = (avg_elev - min_elev) / (max_elev - min_elev)
		norm_elev = max(0.0, min(1.0, norm_elev))
	else:
		norm_elev = 0.0
	low_elev_factor = 1.0 - norm_elev

	risk = (
		rain_norm * RAIN_WEIGHT +
		low_elev_factor * ELEV_WEIGHT +
		flatness * FLAT_WEIGHT
	)
	risk = max(0.0, min(1.0, risk))

	if risk > 0.7:
		level = 'very high'
	elif risk > 0.45:
		level = 'high'
	elif risk > 0.2:
		level = 'medium'
	else:
		level = 'low'

	return risk, level


def compute_all_roads(rain_mm=50.0):
	"""Compute risk and level for all roads in the `roads` list.
	Returns list of dicts: {id, length, risk, level, avg_elevation}
	"""
	out = []
	for r in roads:
		try:
			risk_val, level = compute_road_risk(r, rain_mm=rain_mm)
		except Exception:
			risk_val, level = 0.0, 'low'
		out.append({
			'id': r.get('id'),
			'length': r.get('length'),
			'risk': round(risk_val, 2),
			'level': level,
			'avg_elevation': r.get('avg_elevation')
		})
	return out


if __name__ == "__main__":
	import sys, json

	rain = 50.0
	if len(sys.argv) > 1:
		try:
			rain = float(sys.argv[1])
		except Exception:
			pass

	results = compute_all_roads(rain_mm=rain)
	print(json.dumps(results, indent=2))

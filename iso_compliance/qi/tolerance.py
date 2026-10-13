# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Tolerance engine for drawing-based inspection templates.

A drawing states a dimension the way a draughtsman writes it -- "Ø6.4 H11",
"12.5 -0.05/-0.15", "32" under an ISO 2768-m title block. ERPNext judges a
reading against two numbers, min_value and max_value. This module turns the
first into the second, and nothing else: no frappe import, so it is tested
without a site (`python -m unittest iso_compliance.qi.test_tolerance`).

Sizes are in mm, angles in decimal degrees. ISO 286 and ISO 2768 values live in
data/*.json, copied from the standards' tables.
"""

import json
import math
import os
import re

# Tolerance types, as stored in `custom_tolerance_type`.
SYMMETRIC = "Symmetric"
DEVIATIONS = "Deviations"
LIMITS = "Limits"
MAX_ONLY = "Maximum only"
MIN_ONLY = "Minimum only"
ISO_FIT = "ISO fit (ISO 286)"
GENERAL = "General (ISO 2768)"
ANGLE = "Angle"
GEOMETRIC = "Geometric (GD&T)"
REFERENCE = "Reference / basic"

TYPES = (SYMMETRIC, DEVIATIONS, LIMITS, MAX_ONLY, MIN_ONLY, ISO_FIT, GENERAL, ANGLE, GEOMETRIC, REFERENCE)

#: Stand-in for "no upper limit" on a Minimum-only row. Float fields cannot hold
#: infinity; prints show "—" for anything at or beyond it.
UNBOUNDED = 999999.0

_DATA = os.path.join(os.path.dirname(__file__), "data")
_cache: dict = {}


class ToleranceError(ValueError):
	"""The inputs do not define a tolerance (unknown class, size out of range…)."""


def _table(name: str) -> dict:
	if name not in _cache:
		with open(os.path.join(_DATA, name + ".json")) as f:
			_cache[name] = json.load(f)
	return _cache[name]


def _range_index(ranges, size: float, what: str) -> int:
	"""Index of the range 'over lo up to and including hi'. The first range
	also includes its lower bound."""
	for i, (lo, hi) in enumerate(ranges):
		if (lo < size <= hi) or (i == 0 and size == lo):
			return i
	raise ToleranceError(f"{what}: size {size:g} mm is outside the table ({ranges[0][0]:g}–{ranges[-1][1]:g} mm)")


def _r(x: float) -> float:
	"""Round away float noise (6.4 + 0.09 = 6.490000000000001)."""
	return round(x, 6)


# ---------------------------------------------------------------- ISO 286 --

_FIT_RE = re.compile(r"^([A-Za-z]{1,2})(\d{1,2})$")


def iso_fit(nominal: float, code: str) -> tuple[float, float]:
	"""(lower deviation, upper deviation) in mm for a fit code such as H11,
	h9, js7, K7. Upper-case = hole, lower-case = shaft."""
	m = _FIT_RE.match((code or "").strip())
	if not m:
		raise ToleranceError(f"'{code}' is not an ISO fit code (letter + grade, e.g. H7, h9)")
	letter, grade = m.group(1), int(m.group(2))
	t = _table("iso286")
	if str(grade) not in t["it"]:
		raise ToleranceError(f"IT{grade} is not in the table (IT1–IT16)")
	i = _range_index(t["ranges"], nominal, "ISO 286")
	it = t["it"][str(grade)][i]

	low = letter.lower()
	if low == "js":
		lo, hi = -it / 2, it / 2
	elif letter.islower():
		lo, hi = _shaft(t, low, grade, i, nominal, it)
	else:
		lo, hi = _hole(t, low, grade, i, nominal, it)
	return _r(lo / 1000), _r(hi / 1000)


def _shaft_ei(t, letter, grade, i, nominal):
	if letter == "k":
		# k's positive deviation applies to IT4..IT7 only; other grades sit on zero.
		return t["shaft_ei"]["k"][i] if 4 <= grade <= 7 else 0
	if letter in t["shaft_ei"]:
		return t["shaft_ei"][letter][i]
	if letter in t["shaft_ei_fine"]:
		return t["shaft_ei_fine"][letter][_range_index(t["fine_ranges"], nominal, "ISO 286")]
	raise ToleranceError(f"Fundamental deviation '{letter}' is not supported (use d–h, js, k, m, n, p, r, s)")


def _shaft(t, letter, grade, i, nominal, it):
	if letter in t["shaft_es"]:
		es = t["shaft_es"][letter][i]
		return es - it, es
	ei = _shaft_ei(t, letter, grade, i, nominal)
	return ei, ei + it


def _hole(t, letter, grade, i, nominal, it):
	# A..H mirror the shaft: EI = -es.
	if letter in t["shaft_es"]:
		ei = -t["shaft_es"][letter][i]
		return ei, ei + it

	# K..S: ES = -ei of the shaft, plus delta for the finer grades.
	delta = t["delta"][i][grade - 3] if 3 <= grade <= 8 else 0
	if letter == "k":
		if grade > 8:
			raise ToleranceError("K above IT8 is not defined by ISO 286")
		es = -_shaft_ei(t, "k", 7, i, nominal) + delta  # k's IT4–7 deviation
	elif letter == "m":
		es = -t["shaft_ei"]["m"][i] + (delta if grade <= 8 else 0)
	elif letter == "n":
		if grade <= 8:
			es = -t["shaft_ei"]["n"][i] + delta
		else:
			es = -t["shaft_ei"]["n"][i] if nominal <= 3 else 0
	else:
		es = -_shaft_ei(t, letter, grade, i, nominal) + (delta if grade <= 7 else 0)
	return es - it, es


# --------------------------------------------------------------- ISO 2768 --

_GENERAL_RE = re.compile(r"^(?:ISO\s*2768\s*-?\s*)?([fmcv])$", re.I)


def general_class(value: str | None) -> str | None:
	"""'ISO 2768-m' → 'm'. None/'None' → None."""
	if not value or value == "None":
		return None
	m = _GENERAL_RE.match(value.strip())
	if not m:
		raise ToleranceError(f"'{value}' is not an ISO 2768-1 class (f, m, c, v)")
	return m.group(1).lower()


def general_linear(nominal: float, cls: str) -> float:
	"""± tolerance in mm for a linear size under an ISO 2768-1 class."""
	t = _table("iso2768")["linear"]
	cls = general_class(cls)
	if not cls:
		raise ToleranceError("No general tolerance class on the template")
	if nominal < 0.5:
		raise ToleranceError("ISO 2768-1 gives no general tolerance below 0.5 mm; state it on the drawing")
	tol = t[cls][_range_index(t["ranges"], nominal, "ISO 2768-1")]
	if tol is None:
		raise ToleranceError(f"ISO 2768-{cls} gives no tolerance for {nominal:g} mm")
	return tol


def general_angular(shorter_side: float, cls: str) -> float:
	"""± tolerance in decimal degrees, keyed by the shorter side in mm."""
	t = _table("iso2768")["angular"]
	cls = general_class(cls)
	if not cls:
		raise ToleranceError("No general tolerance class on the template")
	return t[cls][_range_index(t["ranges"], shorter_side, "ISO 2768-1 angular")]


def general_geometric(kind: str, length: float, cls: str) -> float:
	"""ISO 2768-2 zone in mm. kind: straightness_flatness, perpendicularity,
	symmetry, circular_runout."""
	g = _table("iso2768")["geometric"]
	if kind not in g:
		raise ToleranceError(f"ISO 2768-2 has no general tolerance for '{kind}'")
	cls = (cls or "").strip().upper()
	if cls not in ("H", "K", "L"):
		raise ToleranceError(f"'{cls}' is not an ISO 2768-2 class (H, K, L)")
	t = g[kind]
	return t[cls][_range_index(t["ranges"], length, "ISO 2768-2")]


# ------------------------------------------------------------------ angles --

_ANGLE_RE = re.compile(
	r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:°|deg|d)?\s*"
	r"(?:(\d+(?:\.\d+)?)\s*(?:′|'|min|m)?\s*)?"
	r"(?:(\d+(?:\.\d+)?)\s*(?:″|\"|''|s)?\s*)?$",
	re.I,
)


def parse_angle(text) -> float:
	"""'30°15′' / '30 15' / '30.25' / '0°30′' → decimal degrees."""
	if isinstance(text, (int, float)):
		return float(text)
	s = _normalise(str(text))
	m = _ANGLE_RE.match(s)
	if not m:
		raise ToleranceError(f"'{text}' is not an angle (e.g. 30°15′ or 30.25)")
	deg = float(m.group(1))
	minutes = float(m.group(2) or 0)
	seconds = float(m.group(3) or 0)
	sign = -1 if s.lstrip().startswith("-") else 1
	return _r(sign * (abs(deg) + minutes / 60 + seconds / 3600))


# --------------------------------------------------------------- compute --


def limits(tolerance_type: str, *, nominal=None, tol=None, upper_dev=None, lower_dev=None,
           lower=None, upper=None, fit_class=None, general=None, angle_side=None,
           zone=None, signed=False) -> dict:
	"""The row's acceptance limits.

	Returns {"min_value", "max_value", "numeric", "value", "inspected"}.
	`general` is the template's ISO 2768-1 class (for General rows);
	`angle_side` the shorter side in mm for a General angle.
	"""
	ty = tolerance_type
	out = {"numeric": 1, "value": "", "inspected": 1}

	def need(*names):
		vals = {"nominal": nominal, "tol": tol, "upper_dev": upper_dev, "lower_dev": lower_dev,
		        "lower": lower, "upper": upper, "fit_class": fit_class, "zone": zone}
		missing = [n for n in names if vals[n] in (None, "")]
		if missing:
			label = {"lower": "Min", "upper": "Max", "tol": "± tolerance", "upper_dev": "upper deviation",
			         "lower_dev": "lower deviation", "fit_class": "fit class"}
			raise ToleranceError(f"{ty}: enter {', '.join(label.get(n, n) for n in missing)}")

	if ty == SYMMETRIC:
		need("nominal", "tol")
		lo, hi = nominal - abs(tol), nominal + abs(tol)
	elif ty == DEVIATIONS:
		need("nominal", "upper_dev", "lower_dev")
		a, b = nominal + upper_dev, nominal + lower_dev
		lo, hi = min(a, b), max(a, b)
	elif ty == LIMITS:
		need("lower", "upper")
		lo, hi = min(lower, upper), max(lower, upper)
	elif ty == MAX_ONLY:
		need("upper")
		lo, hi = (-UNBOUNDED if signed else 0.0), upper
	elif ty == MIN_ONLY:
		need("lower")
		lo, hi = lower, UNBOUNDED
	elif ty == ISO_FIT:
		need("nominal", "fit_class")
		d_lo, d_hi = iso_fit(nominal, fit_class)
		lo, hi = nominal + d_lo, nominal + d_hi
	elif ty == GENERAL:
		need("nominal")
		if angle_side not in (None, ""):
			t = general_angular(float(angle_side), general)
		else:
			t = general_linear(nominal, general)
		lo, hi = nominal - t, nominal + t
	elif ty == ANGLE:
		need("nominal", "tol")
		n, t = parse_angle(nominal), abs(parse_angle(tol))
		lo, hi = n - t, n + t
	elif ty == GEOMETRIC:
		need("zone")
		lo, hi = 0.0, abs(zone)
	elif ty == REFERENCE:
		return {"min_value": 0, "max_value": 0, "numeric": 0, "value": "", "inspected": 0}
	else:
		raise ToleranceError(f"Unknown tolerance type '{ty}'")

	out.update(min_value=_r(lo), max_value=_r(hi))
	return out


# ------------------------------------------------------------ parse_spec --

_NUM = r"[+-]?\d+(?:\.\d+)?"
_PREFIX = re.compile(r"^(?:Ø|⌀|DIA\.?|SR|R)\s*", re.I)


def _normalise(s: str) -> str:
	s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("＋", "+")
	s = s.replace("º", "°").replace("’", "′").replace("”", "″")
	s = re.sub(r"(\d),(\d)", r"\1.\2", s)  # decimal comma
	return s.strip()


def parse_spec(text: str) -> dict:
	"""Guess the tolerance type and inputs from a spec typed as printed.

	Returns {"tolerance_type": ..., **fields}; the user confirms in the popup.
	Raises ToleranceError when nothing fits.
	"""
	raw = text or ""
	s = _normalise(raw)
	if not s:
		raise ToleranceError("Type the dimension as printed on the drawing")

	# (12.5) — reference / basic
	m = re.fullmatch(r"\(\s*(?:Ø|⌀|R)?\s*(" + _NUM + r")\s*\)|\[\s*(" + _NUM + r")\s*\]", s)
	if m:
		return {"tolerance_type": REFERENCE, "nominal": float(m.group(1) or m.group(2))}

	# Angles: anything with a degree sign
	if "°" in s:
		m = re.fullmatch(r"([^±]+?)\s*(?:±\s*(.+))?", s)
		nominal = parse_angle(m.group(1))
		if m.group(2):
			return {"tolerance_type": ANGLE, "nominal": nominal, "tol": parse_angle(m.group(2))}
		return {"tolerance_type": GENERAL, "nominal": nominal, "angle": 1}

	# MAX / MIN, ≤ / ≥
	m = re.fullmatch(r"(?:MAX\.?|≤|<=)\s*(" + _NUM + r")|(" + _NUM + r")\s*(?:MAX\.?|MAXIMUM)", s, re.I)
	if m:
		return {"tolerance_type": MAX_ONLY, "upper": float(m.group(1) or m.group(2))}
	m = re.fullmatch(r"(?:MIN\.?|≥|>=)\s*(" + _NUM + r")|(" + _NUM + r")\s*(?:MIN\.?|MINIMUM)", s, re.I)
	if m:
		return {"tolerance_type": MIN_ONLY, "lower": float(m.group(1) or m.group(2))}

	s = _PREFIX.sub("", s)

	# 10 ±0.1
	m = re.fullmatch(r"(" + _NUM + r")\s*±\s*(\d+(?:\.\d+)?)", s)
	if m:
		return {"tolerance_type": SYMMETRIC, "nominal": float(m.group(1)), "tol": float(m.group(2))}

	# 12.5 -0.05/-0.15 · 12.5 +0.1 -0.05 · 12.5 +0.1/0
	m = re.fullmatch(r"(" + _NUM + r")\s+([+-]\d*\.?\d+|0)\s*/?\s*([+-]?\d*\.?\d+)", s)
	if m and (m.group(2)[0] in "+-" or m.group(3)[0] in "+-"):
		a, b = float(m.group(2)), float(m.group(3))
		return {"tolerance_type": DEVIATIONS, "nominal": float(m.group(1)),
		        "upper_dev": max(a, b), "lower_dev": min(a, b)}

	# 6.4 H11 · 6.4H11 · 20 h9
	m = re.fullmatch(r"(" + _NUM + r")\s*([A-Za-z]{1,2}\d{1,2})", s)
	if m:
		iso_fit(float(m.group(1)), m.group(2))  # validates the code
		return {"tolerance_type": ISO_FIT, "nominal": float(m.group(1)), "fit_class": m.group(2)}

	# 12.4/12.6 · 12.4 - 12.6 · 12.4 to 12.6
	m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:/|\s-\s|-|\s+to\s+)\s*(\d+(?:\.\d+)?)", s, re.I)
	if m:
		a, b = float(m.group(1)), float(m.group(2))
		return {"tolerance_type": LIMITS, "lower": min(a, b), "upper": max(a, b)}

	# 32 — untoleranced, falls to the title block
	m = re.fullmatch(_NUM, s)
	if m:
		return {"tolerance_type": GENERAL, "nominal": float(s)}

	raise ToleranceError(f"Could not read '{raw}'; choose the tolerance type and enter the values")


def display_limit(x) -> str:
	"""How a limit prints: '—' for the unbounded stand-ins."""
	if x is None or (isinstance(x, float) and math.isinf(x)) or abs(float(x)) >= UNBOUNDED:
		return "—"
	return f"{float(x):g}"

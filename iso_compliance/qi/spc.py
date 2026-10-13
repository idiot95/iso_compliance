# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Process capability from inspection lots (QI SPEC v2, Phase G).

Pure Python, no frappe: `python -m unittest iso_compliance.qi.test_spc`.

A characteristic's history is a list of lots (one submitted inspection each),
every lot a list of measured values. Two spreads:

- within-lot sigma, pooled across lots (or the average moving range of the
  lot means / 1.128 when every lot has a single value) -- what the process
  does in the short term; gives Cp and Cpk;
- overall sigma of every value -- what the customer actually received; gives
  Pp and Ppk.

One-sided specifications (Maximum only, Minimum only) have no Cp/Pp, and Cpk is
the side that exists.
"""

import math

#: Limits at or beyond this are the "no limit" stand-ins of tolerance.UNBOUNDED.
UNBOUNDED = 999999.0

REDUCE_CPK = 1.67
WATCH_CPK = 1.33
POOR_CPK = 1.0
REDUCE_MIN_LOTS = 20


def _mean(xs):
	return sum(xs) / len(xs)


def _sd(xs):
	"""Sample standard deviation (n - 1)."""
	if len(xs) < 2:
		return None
	m = _mean(xs)
	return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def spec_limits(lsl, usl, one_sided_max=False):
	"""Normalise limits: unbounded stand-ins become None; a Maximum-only spec
	(stored with lower 0) has no lower limit."""
	lo = None if lsl is None or abs(lsl) >= UNBOUNDED else lsl
	hi = None if usl is None or abs(usl) >= UNBOUNDED else usl
	if one_sided_max:
		lo = None
	return lo, hi


def sigma_within(lots):
	"""Pooled within-lot sigma; moving range of lot values when lots are single."""
	multi = [lot for lot in lots if len(lot) >= 2]
	if multi:
		dof = sum(len(lot) - 1 for lot in multi)
		ss = sum((len(lot) - 1) * _sd(lot) ** 2 for lot in multi)
		return math.sqrt(ss / dof) if dof else None
	singles = [lot[0] for lot in lots if lot]
	if len(singles) < 2:
		return None
	mr = [abs(b - a) for a, b in zip(singles, singles[1:])]
	return _mean(mr) / 1.128  # d2 for n = 2


def capability(lots, lsl=None, usl=None, one_sided_max=False) -> dict:
	"""Cp, Cpk, Pp, Ppk and friends for a list of lots of values."""
	lots = [[float(x) for x in lot] for lot in lots if lot]
	values = [x for lot in lots for x in lot]
	lo, hi = spec_limits(lsl, usl, one_sided_max)
	out = {
		"lots": len(lots),
		"n": len(values),
		"mean": _mean(values) if values else None,
		"sigma_within": sigma_within(lots),
		"sigma_overall": _sd(values),
		"lsl": lo,
		"usl": hi,
		"cp": None, "cpk": None, "pp": None, "ppk": None,
		"out_of_spec": sum(1 for x in values if (lo is not None and x < lo) or (hi is not None and x > hi)),
	}
	out["pct_out"] = (100.0 * out["out_of_spec"] / len(values)) if values else None
	mu = out["mean"]
	for sig_key, p, pk in (("sigma_within", "cp", "cpk"), ("sigma_overall", "pp", "ppk")):
		s = out[sig_key]
		if mu is None or not s:
			continue
		if lo is not None and hi is not None:
			out[p] = (hi - lo) / (6 * s)
		sides = []
		if hi is not None:
			sides.append((hi - mu) / (3 * s))
		if lo is not None:
			sides.append((mu - lo) / (3 * s))
		out[pk] = min(sides) if sides else None
	return out


def xbar_chart(lots, sigma=None) -> list[dict]:
	"""Lot means against the grand mean, with 3-sigma limits for each lot's size."""
	lots = [[float(x) for x in lot] for lot in lots if lot]
	if not lots:
		return []
	grand = _mean([x for lot in lots for x in lot])
	s = sigma if sigma is not None else sigma_within(lots)
	points = []
	for i, lot in enumerate(lots, 1):
		m = _mean(lot)
		half = 3 * s / math.sqrt(len(lot)) if s else None
		ucl = grand + half if half is not None else None
		lcl = grand - half if half is not None else None
		points.append({
			"lot": i, "mean": m, "n": len(lot), "center": grand, "ucl": ucl, "lcl": lcl,
			"beyond": bool(half is not None and (m > ucl or m < lcl)),
		})
	return points


def suggestion(cap: dict, recent_out: int = 0) -> str:
	"""What to do with the sampling of this characteristic."""
	cpk = cap.get("cpk")
	if cpk is None:
		return "Not enough data"
	if cpk < POOR_CPK:
		return "Not capable: investigate the process and increase sampling"
	if cpk < WATCH_CPK:
		return "Marginal: keep the current sampling and watch"
	if cpk >= REDUCE_CPK and cap["lots"] >= REDUCE_MIN_LOTS and not recent_out:
		return "Capable over {0} lots: consider reduced sampling".format(cap["lots"])
	return "Capable: keep the current sampling"

# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Tolerance engine tests. No site needed:

    python -m unittest iso_compliance.qi.test_tolerance

Expected values are the published ISO 286-1 / ISO 2768 limits for each case.
"""

import unittest

from iso_compliance.qi import tolerance as T


class TestIso286(unittest.TestCase):
	def fit(self, nominal, code, lo_um, hi_um):
		lo, hi = T.iso_fit(nominal, code)
		self.assertAlmostEqual(lo, lo_um / 1000, places=6, msg=f"{nominal} {code} lower")
		self.assertAlmostEqual(hi, hi_um / 1000, places=6, msg=f"{nominal} {code} upper")

	def test_holes_basic(self):
		self.fit(6.4, "H11", 0, 90)  # the plan doc's example
		self.fit(25, "H7", 0, 21)
		self.fit(50, "H8", 0, 39)
		self.fit(10, "H9", 0, 36)

	def test_shafts_clearance(self):
		self.fit(25, "h6", -13, 0)
		self.fit(25, "g6", -20, -7)
		self.fit(25, "f7", -41, -20)
		self.fit(25, "e8", -73, -40)
		self.fit(25, "d9", -117, -65)
		self.fit(40, "f7", -50, -25)

	def test_shafts_transition_interference(self):
		self.fit(25, "k6", 2, 15)
		self.fit(25, "m6", 8, 21)
		self.fit(25, "n6", 15, 28)
		self.fit(25, "p6", 22, 35)
		self.fit(25, "r6", 28, 41)
		self.fit(25, "s6", 35, 48)
		self.fit(60, "r6", 41, 60)  # r splits at 65
		self.fit(70, "r6", 43, 62)
		self.fit(25, "k8", 0, 33)  # k outside IT4–7 sits on zero

	def test_holes_derived(self):
		self.fit(25, "G7", 7, 28)
		self.fit(25, "F8", 20, 53)
		self.fit(25, "K7", -15, 6)
		self.fit(15, "K6", -9, 2)
		self.fit(25, "M7", -21, 0)
		self.fit(15, "M6", -15, -4)
		self.fit(25, "N7", -28, -7)
		self.fit(25, "N9", -52, 0)
		self.fit(25, "P7", -35, -14)
		self.fit(25, "P6", -31, -18)

	def test_js(self):
		self.fit(25, "js7", -10.5, 10.5)
		self.fit(25, "JS8", -16.5, 16.5)

	def test_range_boundaries(self):
		# "over 3 up to and including 6": 3 belongs to the first range, 3.01 to the second
		self.fit(3, "H7", 0, 10)
		self.fit(3.01, "H7", 0, 12)
		self.fit(6, "H7", 0, 12)
		self.fit(6.01, "H7", 0, 15)
		self.fit(30, "h7", -21, 0)
		self.fit(30.01, "h7", -25, 0)
		self.fit(0.5, "H7", 0, 10)

	def test_errors(self):
		for bad in ("X7", "H", "H20", "7H", ""):
			with self.assertRaises(T.ToleranceError, msg=bad):
				T.iso_fit(10, bad)
		with self.assertRaises(T.ToleranceError):
			T.iso_fit(600, "H7")
		with self.assertRaises(T.ToleranceError):
			T.iso_fit(25, "K9")


class TestIso2768(unittest.TestCase):
	def test_linear(self):
		self.assertEqual(T.general_linear(32, "ISO 2768-m"), 0.3)  # plan doc: 32 → 31.7–32.3
		self.assertEqual(T.general_linear(30, "m"), 0.2)
		self.assertEqual(T.general_linear(30.01, "m"), 0.3)
		self.assertEqual(T.general_linear(3, "f"), 0.05)
		self.assertEqual(T.general_linear(150, "c"), 1.2)
		self.assertEqual(T.general_linear(0.5, "m"), 0.1)

	def test_linear_gaps(self):
		with self.assertRaises(T.ToleranceError):
			T.general_linear(0.3, "m")
		with self.assertRaises(T.ToleranceError):
			T.general_linear(2, "v")  # v has no value up to 3 mm
		with self.assertRaises(T.ToleranceError):
			T.general_linear(10, None)

	def test_angular(self):
		self.assertEqual(T.general_angular(8, "m"), 1)
		self.assertEqual(T.general_angular(40, "m"), 0.5)
		self.assertAlmostEqual(T.general_angular(100, "m"), 20 / 60, places=6)
		self.assertEqual(T.general_angular(40, "c"), 1)

	def test_geometric(self):
		self.assertEqual(T.general_geometric("straightness_flatness", 50, "K"), 0.2)
		self.assertEqual(T.general_geometric("perpendicularity", 50, "H"), 0.2)
		self.assertEqual(T.general_geometric("circular_runout", 10, "L"), 0.5)
		with self.assertRaises(T.ToleranceError):
			T.general_geometric("flatness", 10, "X")


class TestAngles(unittest.TestCase):
	def test_parse(self):
		self.assertEqual(T.parse_angle("30°15′"), 30.25)
		self.assertEqual(T.parse_angle("30°15'"), 30.25)
		self.assertEqual(T.parse_angle("30 15"), 30.25)
		self.assertEqual(T.parse_angle("30.25"), 30.25)
		self.assertEqual(T.parse_angle("0°30′"), 0.5)
		self.assertAlmostEqual(T.parse_angle("45°0′36″"), 45.01, places=6)
		self.assertEqual(T.parse_angle(12), 12.0)
		with self.assertRaises(T.ToleranceError):
			T.parse_angle("abc")


class TestLimits(unittest.TestCase):
	def lim(self, ty, lo, hi, **kw):
		r = T.limits(ty, **kw)
		self.assertAlmostEqual(r["min_value"], lo, places=6)
		self.assertAlmostEqual(r["max_value"], hi, places=6)
		return r

	def test_every_type(self):
		self.lim(T.SYMMETRIC, 9.9, 10.1, nominal=10, tol=0.1)
		self.lim(T.DEVIATIONS, 12.35, 12.45, nominal=12.5, upper_dev=-0.05, lower_dev=-0.15)
		self.lim(T.DEVIATIONS, 19.95, 20.1, nominal=20, upper_dev=-0.05, lower_dev=0.1)  # entered swapped
		self.lim(T.LIMITS, 12.4, 12.6, lower=12.6, upper=12.4)
		self.lim(T.MAX_ONLY, 0, 0.5, upper=0.5)
		self.lim(T.MAX_ONLY, -T.UNBOUNDED, 3, upper=3, signed=True)
		self.lim(T.MIN_ONLY, 2, T.UNBOUNDED, lower=2)
		self.lim(T.ISO_FIT, 6.4, 6.49, nominal=6.4, fit_class="H11")
		self.lim(T.GENERAL, 31.7, 32.3, nominal=32, general="ISO 2768-m")
		self.lim(T.GENERAL, 29.5, 30.5, nominal=30, general="m", angle_side=40)
		self.lim(T.ANGLE, 29.5, 30.5, nominal="30°", tol="0°30′")
		self.lim(T.GEOMETRIC, 0, 0.05, zone=0.05)
		ref = T.limits(T.REFERENCE, nominal=12.5)
		self.assertEqual(ref["inspected"], 0)

	def test_missing_inputs(self):
		with self.assertRaises(T.ToleranceError):
			T.limits(T.SYMMETRIC, nominal=10)
		with self.assertRaises(T.ToleranceError):
			T.limits("Nonsense", nominal=10)

	def test_display(self):
		self.assertEqual(T.display_limit(T.UNBOUNDED), "—")
		self.assertEqual(T.display_limit(-T.UNBOUNDED), "—")
		self.assertEqual(T.display_limit(6.49), "6.49")


class TestParseSpec(unittest.TestCase):
	def p(self, text, ty, **fields):
		r = T.parse_spec(text)
		self.assertEqual(r["tolerance_type"], ty, msg=text)
		for k, v in fields.items():
			self.assertAlmostEqual(r[k], v, places=6, msg=f"{text}: {k}") if isinstance(v, float) else self.assertEqual(r[k], v, msg=f"{text}: {k}")

	def test_forms(self):
		self.p("10 ±0.1", T.SYMMETRIC, nominal=10.0, tol=0.1)
		self.p("Ø10±0.05", T.SYMMETRIC, nominal=10.0, tol=0.05)
		self.p("12.5 −0.05/−0.15", T.DEVIATIONS, nominal=12.5, upper_dev=-0.05, lower_dev=-0.15)
		self.p("12.5 +0.1 -0.05", T.DEVIATIONS, upper_dev=0.1, lower_dev=-0.05)
		self.p("20 +0.1/0", T.DEVIATIONS, upper_dev=0.1, lower_dev=0.0)
		self.p("Ø6.4 H11", T.ISO_FIT, nominal=6.4, fit_class="H11")
		self.p("8h9", T.ISO_FIT, nominal=8.0, fit_class="h9")
		self.p("12.4/12.6", T.LIMITS, lower=12.4, upper=12.6)
		self.p("12.4 - 12.6", T.LIMITS, lower=12.4, upper=12.6)
		self.p("MAX 0.5", T.MAX_ONLY, upper=0.5)
		self.p("0.5 max", T.MAX_ONLY, upper=0.5)
		self.p("≤ 1.6", T.MAX_ONLY, upper=1.6)
		self.p("MIN 2", T.MIN_ONLY, lower=2.0)
		self.p("≥5", T.MIN_ONLY, lower=5.0)
		self.p("30°±0°30′", T.ANGLE, nominal=30.0, tol=0.5)
		self.p("30°", T.GENERAL, nominal=30.0, angle=1)
		self.p("(12.5)", T.REFERENCE, nominal=12.5)
		self.p("32", T.GENERAL, nominal=32.0)
		self.p("R2", T.GENERAL, nominal=2.0)
		self.p("12,5 ±0,1", T.SYMMETRIC, nominal=12.5, tol=0.1)

	def test_unreadable(self):
		for bad in ("", "M6", "see note 3", "6.4 X7"):
			with self.assertRaises(T.ToleranceError, msg=bad):
				T.parse_spec(bad)


if __name__ == "__main__":
	unittest.main()

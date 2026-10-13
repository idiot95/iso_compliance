# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Capability tests. No site needed:

    python -m unittest iso_compliance.qi.test_spc

The 50-value dataset's expected figures were worked out by hand (sums of
squares written out below), not by the code under test.
"""

import unittest

from iso_compliance.qi import spc

# Five lots of ten widths, spec 10.00 ± 0.10.
LOTS = [
	[10.01, 10.02, 9.99, 10.00, 10.01, 9.98, 10.02, 10.00, 9.99, 10.03],
	[10.00, 10.01, 10.02, 9.99, 10.00, 10.01, 9.98, 10.02, 10.00, 10.01],
	[9.99, 10.00, 10.01, 10.02, 9.98, 10.00, 10.01, 9.99, 10.00, 10.00],
	[10.02, 10.01, 10.00, 9.99, 10.03, 10.00, 10.01, 10.02, 10.00, 9.99],
	[10.00, 9.98, 10.01, 10.00, 10.02, 9.99, 10.01, 10.00, 10.00, 10.01],
]
# By hand, in hundredths above 10.00:
#   lot sums 5, 4, 0, 7, 2  -> total 18 over 50 values -> mean 10.0036
#   lot sums of squares 25, 16, 12, 21, 12 -> total 86
#   within: sum over lots of (SS_i - S_i^2/10) = (25-2.5)+(16-1.6)+(12-0)+(21-4.9)+(12-0.4) = 76.6
#           sigma_w = sqrt(76.6 / 45) = 1.30469 hundredths = 0.0130469
#   overall: SS - S^2/50 = 86 - 6.48 = 79.52; sigma_o = sqrt(79.52 / 49) = 1.27391 hundredths = 0.0127391
#   Cp  = 0.20 / (6 * 0.0130469) = 2.555;  Cpk = (10.10 - 10.0036) / (3 * 0.0130469) = 2.463
#   Pp  = 0.20 / (6 * 0.0127391) = 2.617;  Ppk = (10.10 - 10.0036) / (3 * 0.0127391) = 2.522


class TestCapability(unittest.TestCase):
	def test_hand_calculation(self):
		c = spc.capability(LOTS, 9.90, 10.10)
		self.assertEqual(c["n"], 50)
		self.assertEqual(c["lots"], 5)
		self.assertAlmostEqual(c["mean"], 10.0036, places=4)
		self.assertAlmostEqual(c["sigma_within"], 0.0130469, places=6)
		self.assertAlmostEqual(c["sigma_overall"], 0.0127391, places=6)
		self.assertAlmostEqual(c["cp"], 2.555, places=3)
		self.assertAlmostEqual(c["cpk"], 2.463, places=3)
		self.assertAlmostEqual(c["pp"], 2.617, places=3)
		self.assertAlmostEqual(c["ppk"], 2.522, places=3)
		self.assertEqual(c["out_of_spec"], 0)

	def test_one_sided(self):
		lots = [[28, 30, 29], [31, 27, 30]]  # mV drop, max 35
		c = spc.capability(lots, 0, 35, one_sided_max=True)
		self.assertIsNone(c["cp"])
		self.assertIsNone(c["lsl"])
		self.assertAlmostEqual(c["cpk"], (35 - c["mean"]) / (3 * c["sigma_within"]), places=9)
		m = spc.capability([[60], [62], [61]], 56, spc.UNBOUNDED)  # minimum only
		self.assertIsNone(m["usl"])
		self.assertIsNotNone(m["cpk"])

	def test_single_value_lots_use_moving_range(self):
		# MR = 2, 1, 3 -> mean 2 -> sigma = 2 / 1.128
		self.assertAlmostEqual(spc.sigma_within([[10], [12], [11], [14]]), 2 / 1.128, places=9)

	def test_out_of_spec_and_chart(self):
		c = spc.capability([[9.8, 10.0], [10.2, 10.0]], 9.9, 10.1)
		self.assertEqual(c["out_of_spec"], 2)
		self.assertAlmostEqual(c["pct_out"], 50.0)
		pts = spc.xbar_chart(LOTS)
		self.assertEqual(len(pts), 5)
		self.assertAlmostEqual(pts[0]["center"], 10.0036, places=4)
		self.assertAlmostEqual(pts[0]["ucl"] - pts[0]["center"], 3 * 0.0130469 / 10 ** 0.5, places=6)
		self.assertFalse(any(p["beyond"] for p in pts))
		shifted = LOTS + [[10.05] * 10]
		self.assertTrue(spc.xbar_chart(shifted)[-1]["beyond"])

	def test_suggestions(self):
		good = spc.capability(LOTS * 4, 9.90, 10.10)  # 20 lots, Cpk ~2.46
		self.assertIn("reduced sampling", spc.suggestion(good))
		self.assertIn("keep the current", spc.suggestion(spc.capability(LOTS, 9.90, 10.10)))  # only 5 lots
		self.assertIn("Not capable", spc.suggestion(spc.capability(LOTS, 9.98, 10.02)))
		self.assertEqual(spc.suggestion(spc.capability([[10.0]], 9, 11)), "Not enough data")


if __name__ == "__main__":
	unittest.main()

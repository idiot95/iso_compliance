# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whitelisted entry points for the template builder's balloon popup."""

import frappe
from frappe import _

from iso_compliance.qi import tolerance as T


def _float(v):
	return None if v in (None, "") else float(v)


@frappe.whitelist()
def parse_spec(text: str) -> dict:
	try:
		return T.parse_spec(text)
	except T.ToleranceError as e:
		return {"error": str(e)}


@frappe.whitelist()
def compute_limits(tolerance_type: str, general: str | None = None, **fields) -> dict:
	"""min/max for the popup's live preview. Same function the template's
	validate uses, so what the user sees is what gets saved."""
	fields.pop("cmd", None)
	kw = {k: _float(fields.get(k)) for k in ("nominal", "tol", "upper_dev", "lower_dev", "lower", "upper", "angle_side", "zone")}
	if tolerance_type == T.ANGLE:
		kw["nominal"], kw["tol"] = fields.get("nominal"), fields.get("tol")
	try:
		out = T.limits(tolerance_type, fit_class=fields.get("fit_class"), general=general,
		               signed=bool(frappe.utils.cint(fields.get("signed"))), **kw)
	except T.ToleranceError as e:
		return {"error": str(e)}
	out["min_display"] = T.display_limit(out["min_value"])
	out["max_display"] = T.display_limit(out["max_value"])
	return out


@frappe.whitelist()
def tolerance_types() -> list[str]:
	return list(T.TYPES)


def require_quality_manager():
	if not ({"Quality Manager", "System Manager"} & set(frappe.get_roles())):
		frappe.throw(_("Only a Quality Manager can change inspection templates."), frappe.PermissionError)

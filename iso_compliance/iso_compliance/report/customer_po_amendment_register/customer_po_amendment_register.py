# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-022, derived entirely from what ERPNext already recorded.

Nothing here is typed in twice. An amendment is a Sales Order carrying
amended_from, so the amendment itself is already a record. What changed is
obtained by comparing the amendment against the order it superseded, and by
reading the Version rows the framework writes on every save. Who did it and when
come from the same places. The reason, where one was given, is the Comment
somebody already wrote on the order.

That last point is the whole argument for this approach: 2,661 comments already
exist on Sales Orders, carrying notes like "Order Received 22nd July". Asking the
same people to retype that into a separate amendment form would produce a second,
worse copy of information the system already holds.

What this cannot invent is an approval. If clause 8.2.4 evidence of authorisation
is required, that is a workflow on Sales Order, not another register.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, strip_html

#: Header fields worth reporting a change in. Deliberately short: an amendment
#: register that lists every altered field is unreadable, and the ones that matter
#: commercially are quantity, value, dates and the customer's own PO reference.
WATCHED = [
	("po_no", _("Customer PO No.")),
	("po_date", _("Customer PO Date")),
	("delivery_date", _("Delivery Date")),
	("grand_total", _("Order Value")),
	("total_qty", _("Total Qty")),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Amendment"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Order", "width": 165},
		{"label": _("Supersedes"), "fieldname": "amended_from", "fieldtype": "Link", "options": "Sales Order", "width": 165},
		{"label": _("Rev"), "fieldname": "revision", "fieldtype": "Data", "width": 45},
		{"label": _("Date"), "fieldname": "amended_on", "fieldtype": "Date", "width": 95},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 190},
		{"label": _("Customer PO"), "fieldname": "po_no", "fieldtype": "Data", "width": 120},
		{"label": _("What Changed"), "fieldname": "changes", "fieldtype": "Small Text", "width": 320},
		{"label": _("Reason Recorded"), "fieldname": "reason", "fieldtype": "Small Text", "width": 260},
		{"label": _("Amended By"), "fieldname": "amended_by", "fieldtype": "Data", "width": 165},
		{"label": _("Edits After Submit"), "fieldname": "version_count", "fieldtype": "Int", "width": 130},
	]


def get_data(filters):
	conditions = {"amended_from": ("is", "set")}
	if filters.get("customer"):
		conditions["customer"] = filters.customer
	if filters.get("from_date") and filters.get("to_date"):
		conditions["transaction_date"] = ("between", [filters.from_date, filters.to_date])

	amendments = frappe.get_all(
		"Sales Order",
		filters=conditions,
		fields=[
			"name", "amended_from", "customer", "po_no", "po_date", "delivery_date",
			"grand_total", "total_qty", "owner", "creation", "transaction_date", "docstatus",
		],
		# Explicit: newest amendment first, which is how a register of changes is read.
		order_by="creation desc",
		limit_page_length=0,
	)

	rows = []
	for a in amendments:
		original = frappe.db.get_value(
			"Sales Order", a.amended_from,
			["po_no", "po_date", "delivery_date", "grand_total", "total_qty"],
			as_dict=True,
		)
		rows.append(
			{
				"name": a.name,
				"amended_from": a.amended_from,
				"revision": _revision_of(a.name),
				"amended_on": a.creation.date() if a.creation else None,
				"customer": a.customer,
				"po_no": a.po_no,
				"changes": _describe_changes(a, original),
				"reason": _reason_for(a.name, a.amended_from),
				"amended_by": frappe.db.get_value("User", a.owner, "full_name") or a.owner,
				"version_count": frappe.db.count("Version", {"ref_doctype": "Sales Order", "docname": a.name}),
			}
		)
	return rows


def _revision_of(name: str) -> str:
	"""ERPNext suffixes an amendment with -1, -2 ... which is the revision number."""
	tail = name.rsplit("-", 1)[-1]
	return tail if tail.isdigit() else ""


def _describe_changes(amendment, original) -> str:
	"""Diff the amendment against the order it superseded."""
	if not original:
		return _("Superseded order no longer available.")

	parts = []
	for fieldname, label in WATCHED:
		before, after = original.get(fieldname), amendment.get(fieldname)
		if fieldname in ("grand_total", "total_qty"):
			if flt(before, 2) == flt(after, 2):
				continue
			parts.append(f"{label}: {flt(before, 2):,.2f} → {flt(after, 2):,.2f}")
		else:
			if (before or "") == (after or ""):
				continue
			parts.append(f"{label}: {before or '—'} → {after or '—'}")

	item_delta = _item_change(amendment.name, amendment.amended_from)
	if item_delta:
		parts.append(item_delta)

	# An amendment with no visible header or line change was raised for something
	# outside the watched set. Say so rather than implying nothing happened.
	return "; ".join(parts) if parts else _("No change in value, quantity or dates. See the order for detail.")


def _item_change(new_name: str, old_name: str) -> str | None:
	new_items = frappe.get_all("Sales Order Item", filters={"parent": new_name}, fields=["item_code", "qty"])
	old_items = frappe.get_all("Sales Order Item", filters={"parent": old_name}, fields=["item_code", "qty"])
	old_map = {}
	for i in old_items:
		old_map[i.item_code] = old_map.get(i.item_code, 0) + flt(i.qty)
	new_map = {}
	for i in new_items:
		new_map[i.item_code] = new_map.get(i.item_code, 0) + flt(i.qty)

	added = sorted(set(new_map) - set(old_map))
	removed = sorted(set(old_map) - set(new_map))
	changed = sorted(k for k in set(new_map) & set(old_map) if flt(new_map[k], 3) != flt(old_map[k], 3))

	bits = []
	if added:
		bits.append(_("items added: {0}").format(", ".join(added[:3]) + ("…" if len(added) > 3 else "")))
	if removed:
		bits.append(_("items removed: {0}").format(", ".join(removed[:3]) + ("…" if len(removed) > 3 else "")))
	if changed:
		sample = changed[0]
		bits.append(
			_("qty changed on {0} ({1} → {2}){3}").format(
				sample, flt(old_map[sample], 2), flt(new_map[sample], 2),
				_(" and {0} more").format(len(changed) - 1) if len(changed) > 1 else "",
			)
		)
	return "; ".join(bits) if bits else None


def _reason_for(new_name: str, old_name: str) -> str:
	"""The note somebody already wrote, rather than a field nobody fills in."""
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Sales Order",
			"reference_name": ("in", [new_name, old_name]),
			"comment_type": "Comment",
		},
		fields=["content"],
		order_by="creation desc",
		limit_page_length=2,
	)
	text = " | ".join(strip_html(c.content or "").strip() for c in comments if c.content)
	return (text[:220] + "…") if len(text) > 220 else text

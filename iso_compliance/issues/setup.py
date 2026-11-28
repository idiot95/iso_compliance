# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""What Report Issue needs on the site: the Issue Types, and the custom fields
on Issue (one tab per step), Non Conformance and Quality Action. Idempotent;
runs on every migrate. Every field is logged in EXTERNAL_CHANGES.md."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from iso_compliance.issues import routes

KEEP = ("fieldname", "label", "fieldtype", "options", "read_only", "hidden", "in_list_view",
        "in_standard_filter", "description", "depends_on", "length")
WIDE = ("Small Text", "Text Editor", "Table", "Long Text", "HTML")
MODULE = "ISO Compliance"


class Layout:
	"""Custom fields in form order: three short fields to a row, wide ones
	alone, and a labelled Section Break wherever a step names a heading."""

	def __init__(self, after):
		self.after, self.out, self.count = after, [], {}

	def add(self, df):
		df = {k: v for k, v in df.items() if k in KEEP and v is not None}
		df.update(insert_after=self.after, module=MODULE)
		self.out.append(df)
		self.after = df["fieldname"]

	def brk(self, kind, label=None, **more):
		n = self.count[self.prefix] = self.count.get(self.prefix, 0) + 1
		self.add({"fieldname": f"custom_ri_{kind[0].lower()}b_{self.prefix}_{n}", "fieldtype": kind,
		          "label": label, **more})

	def fields(self, prefix, fields, fresh=False):
		"""`fresh`: start a new row first (after a tab's summary box)."""
		self.prefix, run = prefix, -1 if fresh else 0
		for f in fields:
			if "section" in f:
				self.brk("Section Break", f["section"])
				run = 0
				continue
			if f["fieldtype"] in WIDE:
				if run != 0:
					self.brk("Section Break")
				run = -1
			elif run in (-1, 3):
				self.brk("Section Break")
				run = 0
			elif run > 0:
				self.brk("Column Break")
			self.add(f)
			if run >= 0:
				run += 1


def issue_fields():
	lay = Layout("description")
	lay.prefix = "det"
	lay.brk("Section Break", "What was reported", depends_on="eval:doc.custom_steps")
	lay.fields("det", routes.DETAIL_FIELDS)
	lay.prefix = "state"
	lay.brk("Section Break", "Where it stands", depends_on="eval:doc.custom_steps")
	lay.fields("state", routes.STATE_FIELDS)

	lay.after = "content_type"
	for tab in routes.TAB_ORDER:
		keys = [k for k in routes.STEPS if k not in ("log", "closed") and routes.tab_of(k) == tab]
		lay.add({"fieldname": routes.tab_fieldname(tab), "fieldtype": "Tab Break",
		         "label": routes.STEPS[tab]["label"],
		         "depends_on": "eval:" + " || ".join(f"(doc.custom_steps || '').includes('\"{k}\"')" for k in keys)})
		lay.add({"fieldname": routes.intro_fieldname(tab), "fieldtype": "HTML", "label": "Step"})
		lay.fields(tab, routes.STEPS[tab]["fields"], fresh=True)
	return lay.out


def _chain(fields, after):
	lay = Layout(after)
	for f in fields:
		lay.add(f)
	return lay.out


def ensure_issue_setup():
	for name, (_area, _who, description) in routes.ISSUE_TYPES.items():
		if not frappe.db.exists("Issue Type", name):
			frappe.get_doc({"doctype": "Issue Type", "__newname": name, "description": description}).insert(
				ignore_permissions=True)
	create_custom_fields(
		{
			"Issue": issue_fields(),
			"Non Conformance": _chain(routes.NCR_CUSTOM_FIELDS, "custom_closure_date"),
			"Quality Action": _chain(routes.CA_CUSTOM_FIELDS, "custom_verification_date"),
		},
		update=True,
	)
	frappe.db.commit()

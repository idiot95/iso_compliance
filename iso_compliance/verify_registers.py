"""Throwaway: render all 26 register prints, assert every declared heading shows."""

import html as htmllib
import json
import os

import frappe


def run():
	seed_path = os.path.join(frappe.get_app_path("iso_compliance"), "seed_data", "controlled_documents.json")
	docs = json.load(open(seed_path))["documents"]
	failures = 0

	for entry in docs:
		legacy = entry.get("legacy_document_number") or ""
		if not legacy.startswith("REG"):
			continue
		name = entry["name"]

		expected = []
		for item in entry.get("print_columns") or []:
			label = item.get("label") if isinstance(item, dict) else (item[1] if len(item) > 1 else item[0])
			if label:
				expected.append(label)
		static = entry.get("static_table") or {}
		for c in static.get("columns") or []:
			expected.append(c if isinstance(c, str) else c.get("label"))

		try:
			rendered = frappe.get_print("Controlled Document", name, "Controlled Document")
		except Exception as e:
			print(f"FAIL  {legacy}: render error {str(e)[:80]}")
			failures += 1
			continue

		# The print jinja environment does not autoescape, so labels appear raw.
		missing = [x for x in expected if x and x not in rendered]
		if missing:
			print(f"FAIL  {legacy}: missing headings {missing[:4]}")
			failures += 1
		else:
			note = f"{len(expected)} headings" if expected else "fallback columns"
			has_rows = "No entries recorded yet." not in rendered
			print(f"PASS  {legacy}: {note}, {'rows present' if has_rows else 'empty register'}")

	print(f"\n{failures} failures")

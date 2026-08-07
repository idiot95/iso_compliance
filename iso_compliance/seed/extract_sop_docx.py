# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Rebuild the structured SOP bodies in the seed file from the OneDrive export.

Runs on the host with the standard library only -- no frappe, no python-docx --
so a data resync never depends on the bench being up. Usage:

    python3 extract_sop_docx.py "<export>/HCC ISO 2026/SOPs" \
            ../seed_data/controlled_documents.json [--dry-run]

Every SOP in the export follows one Word template: a single numbered list
carries the section headings at level 0 (Purpose, Scope, ... Related Documents)
and the procedure step headings at level 1; sub-points under a step are
ordinary bulleted lists with their own numbering; Definitions and
Responsibilities are two-column tables. The section list's numId differs
between files, so it is located by the heading text, never assumed.

Nesting is the whole point of this extractor. The first import flattened every
bulleted sub-point into its own procedure step, which is how "Document Number"
came to print as step 5 of SOP001. Here a step's sub-points become a nested
<ul> inside that step's content, so the printed procedure keeps the shape the
authors gave it.
"""

import argparse
import html
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: Section headings mapped to what the seed stores. Process Flow (ASCII art)
#: and Revision History (the system's own concern) are recognised so they are
#: skipped deliberately rather than warned about.
SECTION_KEYS = {
	"purpose": "purpose",
	"scope": "scope",
	"references": "references",
	"reference": "references",
	"definitions": "definitions",
	"definition": "definitions",
	"responsibilities": "responsibilities",
	"procedure": "procedure",
	"records": "records_generated",
	"related documents": "related_documents",
	"process flow": None,
	"revision history": None,
}

#: "REG001 – Master Document List" -> ("REG001", "Master Document List").
DOC_LINE = re.compile(r"^\s*([A-Z]{2,5}\s?-?\s?\d{2,4})\s*[–—:-]\s*(.+?)\s*$")

TITLE_LINE = re.compile(r"^\s*(SOP\s?0*\d+)\s*[–—:-]\s*(.+?)\s*$")


def parse_docx(path: str) -> list:
	"""Flatten document.xml into ordered (kind, style, numid, ilvl, payload) items."""
	with zipfile.ZipFile(path) as z:
		root = ET.fromstring(z.read("word/document.xml"))
	items = []
	for el in root.find(W + "body"):
		tag = el.tag.replace(W, "")
		if tag == "p":
			style = numid = None
			ilvl = 0
			pPr = el.find(W + "pPr")
			if pPr is not None:
				s = pPr.find(W + "pStyle")
				style = s.get(W + "val") if s is not None else None
				numPr = pPr.find(W + "numPr")
				if numPr is not None:
					n = numPr.find(W + "numId")
					i = numPr.find(W + "ilvl")
					numid = n.get(W + "val") if n is not None else None
					ilvl = int(i.get(W + "val")) if i is not None else 0
			text = "".join(t.text or "" for t in el.iter(W + "t")).strip()
			items.append(("p", style, numid, ilvl, text))
		elif tag == "tbl":
			rows = []
			for tr in el.findall(W + "tr"):
				cells = []
				for tc in tr.findall(W + "tc"):
					parts = ["".join(t.text or "" for t in p.iter(W + "t")).strip() for p in tc.findall(W + "p")]
					cells.append(" ".join(p for p in parts if p))
				rows.append(cells)
			items.append(("tbl", None, None, 0, rows))
	return items


def _esc(text: str) -> str:
	return html.escape(text, quote=False)


def _nested_list(bullets: list) -> str:
	"""Bulleted (ilvl, text) runs become a nested <ul>, one level per ilvl step."""
	out, level = [], -1
	for ilvl, text in bullets:
		while level < ilvl:
			out.append("<ul>")
			level += 1
		while level > ilvl:
			out.append("</ul>")
			level -= 1
		out.append(f"<li>{_esc(text)}</li>")
	out.extend("</ul>" for _ in range(level + 1))
	return "".join(out)


def _table_html(rows: list) -> str:
	body = "".join(
		"<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows
	)
	return f"<table>{body}</table>"


class _Blocks:
	"""Accumulates paragraphs, bullets and tables into one HTML string."""

	def __init__(self):
		self.html = []
		self.bullets = []

	def flush(self):
		if self.bullets:
			self.html.append(_nested_list(self.bullets))
			self.bullets = []

	def paragraph(self, text):
		self.flush()
		self.html.append(f"<p>{_esc(text)}</p>")

	def bullet(self, ilvl, text):
		self.bullets.append((ilvl, text))

	def table(self, rows):
		self.flush()
		self.html.append(_table_html(rows))

	def result(self) -> str:
		self.flush()
		return "".join(self.html)


def extract_sop(path: str) -> tuple[dict, list]:
	"""One docx -> the seed's `sop` dict, plus warnings for anything odd."""
	items = parse_docx(path)
	warnings = []

	sec_num = next(
		(numid for k, _s, numid, ilvl, t in items
		 if k == "p" and numid and ilvl == 0 and isinstance(t, str)
		 and re.fullmatch(r"purpose:?", t.lower())),
		None,
	)
	if not sec_num:
		return {}, ["no Purpose heading found -- file skipped"]

	sop = {
		"declared_number": None,
		"declared_title": None,
		"purpose": "",
		"scope": "",
		"references": [],
		"definitions": [],
		"responsibilities": [],
		"procedure_steps": [],
		"records_generated": [],
		"related_documents": [],
	}

	for kind, style, _n, _i, text in items:
		if kind == "p" and style == "Title" and isinstance(text, str):
			m = TITLE_LINE.match(text)
			if m:
				sop["declared_number"] = m.group(1).replace(" ", "")
				sop["declared_title"] = m.group(2)

	section = None  # seed key of the section being read
	step = None  # the procedure step being filled
	blocks = _Blocks()  # content for purpose/scope or the current step
	table_rows = []  # first table of definitions/responsibilities

	def close_step():
		nonlocal step
		if step is not None:
			step["step_content"] = blocks.result()
			sop["procedure_steps"].append(step)
			step = None

	def close_section():
		nonlocal table_rows
		close_step()
		if section in ("purpose", "scope"):
			sop[section] = blocks.result()
		elif section == "definitions":
			for row in table_rows[1:]:  # first row is the Term/Definition header
				if len(row) >= 2 and (row[0] or row[1]):
					sop["definitions"].append({"term": row[0], "definition": row[1]})
		elif section == "responsibilities":
			for row in table_rows[1:]:
				if len(row) >= 2 and (row[0] or row[1]):
					sop["responsibilities"].append({"role": row[0], "responsibility": row[1]})
		table_rows = []

	for kind, _style, numid, ilvl, payload in items:
		if kind == "p" and numid == sec_num and ilvl == 0 and payload:
			close_section()
			heading = re.sub(r"[:.]$", "", payload.strip()).lower()
			if heading in SECTION_KEYS:
				section = SECTION_KEYS[heading]
			else:
				section = None
				warnings.append(f"unrecognised section {payload!r} skipped")
			blocks = _Blocks()
			continue

		if section is None:
			continue

		if kind == "p" and numid == sec_num and ilvl == 1 and payload:
			if section == "procedure":
				close_step()
				blocks = _Blocks()
				step = {"step_no": str(len(sop["procedure_steps"]) + 1), "step_title": payload}
			else:
				warnings.append(f"level-1 heading outside Procedure: {payload!r}")
			continue

		if kind == "tbl":
			if section in ("definitions", "responsibilities"):
				if table_rows:
					warnings.append(f"second table in {section} ignored")
				else:
					table_rows = payload
			else:
				blocks.table(payload)
			continue

		if not payload:
			continue

		if section in ("references", "records_generated", "related_documents"):
			if numid is None:
				continue  # section intro sentence, not an item
			if section == "references":
				sop["references"].append({"reference": payload})
			else:
				m = DOC_LINE.match(payload)
				if m:
					number = re.sub(r"[\s-]", "", m.group(1))
					sop[section].append({"number": number, "title": m.group(2)})
				else:
					sop[section].append({"number": "", "title": payload})
					warnings.append(f"{section} line without a document number: {payload!r}")
			continue

		if section == "procedure" and step is None:
			warnings.append(f"procedure text before the first step folded in: {payload[:50]!r}")
			step = {"step_no": str(len(sop["procedure_steps"]) + 1), "step_title": ""}

		if numid is not None:
			blocks.bullet(ilvl, payload)
		else:
			blocks.paragraph(payload)

	close_section()
	return sop, warnings


def main() -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("sops_dir", help="SOPs folder of the OneDrive export")
	ap.add_argument("seed_json", help="seed_data/controlled_documents.json to update")
	ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
	args = ap.parse_args()

	import glob
	import os

	with open(args.seed_json) as fh:
		seed = json.load(fh)
	by_legacy = {d.get("legacy_document_number"): d for d in seed["documents"]}

	updated = 0
	for path in sorted(glob.glob(os.path.join(args.sops_dir, "*.docx"))):
		m = re.search(r"SOP\s?0*(\d+)", os.path.basename(path))
		if not m:
			continue
		legacy = f"SOP{int(m.group(1)):03d}"
		sop, warnings = extract_sop(path)
		for w in warnings:
			print(f"{legacy}: WARN {w}")
		if not sop:
			continue
		entry = by_legacy.get(legacy)
		if entry is None:
			print(f"{legacy}: WARN not in seed file, skipped")
			continue
		if not sop["declared_number"]:
			sop["declared_number"] = entry.get("sop", {}).get("declared_number")
			sop["declared_title"] = entry.get("sop", {}).get("declared_title")
		entry["sop"] = sop
		updated += 1
		print(
			f"{legacy}: {len(sop['procedure_steps'])} steps, "
			f"{len(sop['definitions'])} definitions, {len(sop['responsibilities'])} roles, "
			f"{len(sop['references'])} references, {len(sop['records_generated'])} records, "
			f"{len(sop['related_documents'])} related"
		)

	if args.dry_run:
		print(f"dry run: {updated} SOPs extracted, nothing written")
		return 0

	with open(args.seed_json, "w") as fh:
		json.dump(seed, fh, indent=1, ensure_ascii=False)
		fh.write("\n")
	print(f"{updated} SOPs written to {args.seed_json}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

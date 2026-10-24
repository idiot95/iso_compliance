// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// SOP-006: a posted receipt or Manufacture entry whose rows wait in Inspection
// Required. Nothing opens by itself: the document is assigned to Engineering
// (My Work), and the engineer starts each row's inspection from here.

frappe.provide("hcc.inspection");

hcc.inspection.FLOW = "iso_compliance.overrides.inspection_flow";

hcc.inspection.show_waiting = async function (frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.custom_inspection_pending) return;
	const { message: rows } = await frappe.call({
		method: `${hcc.inspection.FLOW}.waiting`,
		args: { reference_type: frm.doctype, reference_name: frm.doc.name },
	});
	const open = (rows || []).filter((r) => r.state !== "done");
	if (!open.length) return;
	const esc = frappe.utils.escape_html;
	const who = (frm.get_docinfo().assignments || []).map((a) => frappe.user.full_name(a.owner));
	frm.dashboard.add_comment(
		__("{0} row(s) wait in Inspection Required{1}. Stores cannot move them until they are inspected.", [
			open.length, who.length ? ` · ${__("assigned to {0}", [who.map(esc).join(", ")])}` : "",
		]),
		"blue",
		true
	);
	if (!frappe.model.can_create("Quality Inspection")) return;
	frm.add_custom_button(__("Inspect"), () => hcc.inspection.pick(frm.doctype, frm.doc.name, open)).addClass("btn-primary");
};

// One row: straight in. Several: say which, with where each one stands.
hcc.inspection.pick = function (doctype, name, rows) {
	const start = (r, sample_size) =>
		frappe
			.call({
				method: `${hcc.inspection.FLOW}.start_inspection`,
				args: { reference_type: doctype, reference_name: name, row: r.row, sample_size },
				freeze: true,
				freeze_message: __("Starting the inspection…"),
			})
			.then(({ message }) => frappe.set_route("Form", "Quality Inspection", message));
	// a new inspection asks how many pieces; a started one opens as it is
	const go = (r) => (r.state === "todo" ? hcc.inspection.ask_sample(r.qty, r.default_sample, (n) => start(r, n)) : start(r));
	if (rows.length === 1) return go(rows[0]);
	const esc = frappe.utils.escape_html;
	const state = { todo: __("Not started"), started: __("Started") };
	const d = new frappe.ui.Dialog({
		title: __("Which item to inspect?"),
		fields: [{ fieldname: "list", fieldtype: "HTML" }],
	});
	d.fields_dict.list.$wrapper.html(
		`<div class="list-group">${rows
			.map(
				(r, i) => `<button type="button" class="list-group-item list-group-item-action" data-i="${i}" style="display:flex;gap:12px;align-items:center;text-align:left">
				<span class="text-muted">#${r.idx}</span>
				<span style="flex:1"><b>${esc(r.item_code)}</b> <span class="text-muted">${esc(r.item_name || "")}</span>
					<br><span class="small">${format_number(r.qty)} ${esc(r.uom || "")}${r.release ? ` → ${esc(r.release)}` : ""}</span></span>
				<span class="indicator-pill ${r.state === "started" ? "orange" : "gray"}">${state[r.state]}</span></button>`
			)
			.join("")}</div>`
	);
	d.fields_dict.list.$wrapper.on("click", "[data-i]", (e) => {
		d.hide();
		go(rows[cint($(e.currentTarget).attr("data-i"))]);
	});
	d.show();
};

// How many pieces of the lot to measure, the settings' percentage offered.
hcc.inspection.ask_sample = async function (lot, suggested, then) {
	await frappe.require("/assets/iso_compliance/js/qi_sample.js");
	window.iso_qi_sample.ask({ lot, suggested, then });
};

frappe.ui.form.on("Purchase Receipt", { refresh: hcc.inspection.show_waiting });
frappe.ui.form.on("Stock Entry", { refresh: hcc.inspection.show_waiting });

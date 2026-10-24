// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Quality Inspection on a drawing template: open the inspector screen, and
// show what was measured. Inspections on legacy templates are unchanged.

// A drawing inspection fills itself from the template, the lot and the
// inspector screen. The standard fields that would say the same thing again
// (inspection type = stage, the raw readings grid = measurements, manual
// inspection = disposition) are hidden, and what came from the template is read
// only, so the record cannot drift from what was inspected.
const QI_DRAWING_HIDDEN = ["inspection_type", "manual_inspection", "readings", "item_serial_no", "custom_description_from_ref_doc"];
const QI_DRAWING_FIXED = [
	"item_code", "bom_no", "quality_inspection_template", "reference_type", "reference_name", "custom_stage",
	"custom_work_order", "custom_customer", "custom_drawing_no", "custom_drawing_revision", "custom_drawing", "custom_check_point",
];

frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		const drawing = !!frm.doc.custom_stage;
		QI_DRAWING_HIDDEN.forEach((f) => frm.fields_dict[f] && frm.toggle_display(f, !drawing || (f === "item_serial_no" && !!frm.doc.item_serial_no)));
		QI_DRAWING_FIXED.forEach((f) => frm.fields_dict[f] && frm.set_df_property(f, "read_only", drawing && !frm.is_new() ? 1 : 0));
		qi_old_format_note(frm);
		if (frm.is_new()) qi_start_dialog(frm);
		const entry = drawing && !frm.is_new() && frm.doc.docstatus < 2 && qi_wide();
		if (!entry) $(frm.wrapper).find(".qi-entry").remove();
		if (frm.is_new() || !drawing) return;
		qi_focus_layout(frm, entry);
		frm.add_custom_button(frm.doc.docstatus === 0 ? __("Open inspector") : __("View in inspector"), () =>
			frappe.set_route("inspect", frm.doc.name)
		);
		// the drawing with every number marked, and the readings: the record that is kept
		frm.add_custom_button(__("Print inspection record"), () =>
			window.open(
				`/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}` +
					`&format=${encodeURIComponent("Sampling and Inspection Record (QI)")}&no_letterhead=1&trigger_print=1`
			)
		);
		// say which plan this inspection loaded, so there is no guessing old vs new
		const tpl = frm.doc.quality_inspection_template;
		const dwg = [frm.doc.custom_drawing_no, frm.doc.custom_drawing_revision && __("Rev {0}", [frm.doc.custom_drawing_revision])].filter(Boolean).join(" ");
		if (!entry) frm.set_intro(
			__("Inspection plan {0} (new format{1}).", [
				`<a href="/app/quality-inspection-template/${encodeURIComponent(tpl)}">${frappe.utils.escape_html(tpl)}</a>`,
				dwg ? ", " + __("drawing {0}", [frappe.utils.escape_html(dwg)]) : "",
			]),
			"blue"
		);
		if (entry) qi_entry(frm);
		else qi_render_measurements(frm);
	},
});

function qi_render_measurements(frm) {
	const field = frm.fields_dict.custom_measurements_html;
	if (!field) return;
	frappe.call({ method: "iso_compliance.qi.inspector.get_inspection", args: { qi: frm.doc.name } }).then(({ message: d }) => {
		const esc = frappe.utils.escape_html;
		const html = d.rows
			.map((r) => {
				const vals = r.values
					.map((v) => {
						const n = parseFloat(v.value);
						const bad = r.row_type === "Visual" ? v.value === "NG" : !(n >= r.min - 1e-9 && n <= r.max + 1e-9);
						return `<span class="qi-val ${bad ? "bad" : ""}" title="#${v.sample_no}">${esc(v.value)}</span>`;
					})
					.join(" ");
				return `<tr><td><b>${esc(r.balloon)}</b></td><td>${esc(r.specification)}</td>
					<td class="text-muted">${r.row_type === "Visual" ? "OK / NG" : `${esc(r.min_display)} – ${esc(r.max_display)} ${esc(r.unit || "")}`}</td>
					<td>${r.values.length}/${r.required}</td><td>${vals || '<span class="text-muted">—</span>'}</td></tr>`;
			})
			.join("");
		field.$wrapper.html(`<style>.qi-val{display:inline-block;padding:0 4px;margin:1px;border-radius:4px;background:var(--gray-100);font-variant-numeric:tabular-nums}.qi-val.bad{background:var(--red-100);color:var(--red-700)}
			.qi-form-dwg{position:relative;border:1px solid var(--border-color);border-radius:8px;overflow:hidden;margin-bottom:12px;background:#fff;max-width:900px}
			.qi-form-dwg canvas{display:block;width:100%;height:auto}
			.qi-form-dwg .b{position:absolute;border:2px solid #9a9a9a;border-radius:3px}
			.qi-form-dwg .b span{position:absolute;top:-11px;left:-11px;min-width:22px;height:22px;padding:0 4px;border-radius:11px;background:#9a9a9a;color:#fff;font-size:11px;font-weight:600;display:flex;align-items:center;justify-content:center}
			.qi-form-dwg .b.done{border-color:#16794C}.qi-form-dwg .b.done span{background:#16794C}
			.qi-form-dwg .b.failed{border-color:#CC2929;background:rgba(204,41,41,.1)}.qi-form-dwg .b.failed span{background:#CC2929}
			.qi-form-key{font-size:12px;color:var(--text-muted);margin:-6px 0 10px}</style>
			${d.drawing ? `<div class="qi-form-dwg"><canvas></canvas></div><div class="qi-form-key">${__("Green: measured and in spec · Red: out of spec · Grey: not measured yet")}</div>` : ""}
			<table class="table table-sm"><thead><tr><th>#</th><th>${__("Characteristic")}</th><th>${__("Limits")}</th><th>n</th><th>${__("Values")}</th></tr></thead><tbody>${html}</tbody></table>`);
		if (d.drawing) qi_form_drawing(field.$wrapper.find(".qi-form-dwg"), d);
	});
}

// The drawing with every number coloured by its result, as the print shows it.
async function qi_form_drawing($box, d) {
	try {
		await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
		const drawing = await window.iso_qi_pdf.open(d.drawing);
		await drawing.render(1, $box.find("canvas")[0], $box.width() || 800);
		const bad = (r, v) => (r.row_type === "Visual" ? v.value === "NG" : !(parseFloat(v.value) >= r.min - 1e-9 && parseFloat(v.value) <= r.max + 1e-9));
		for (const r of d.rows) {
			let p = null;
			try {
				p = r.position ? JSON.parse(r.position) : null;
			} catch (e) {
				p = null;
			}
			if (!p || (p.page || 1) !== 1) continue;
			const state = r.values.some((v) => bad(r, v)) ? "failed" : r.values.length >= r.required ? "done" : "";
			$(`<div class="b ${state}" title="${frappe.utils.escape_html(r.specification)}"><span>${frappe.utils.escape_html(r.balloon)}</span></div>`)
				.css({ left: p.x + "%", top: p.y + "%", width: p.w + "%", height: p.h + "%" })
				.appendTo($box);
		}
		drawing.close();
	} catch (e) {
		$box.replaceWith(`<div class="text-muted small">${__("Could not show the drawing here")}</div>`);
	}
}

// An inspection on a template from before drawings still works the old way
// (readings typed into the grid); say so, and point at the way out.
function qi_old_format_note(frm) {
	const tpl = frm.doc.quality_inspection_template;
	if (frm.is_new() || frm.doc.custom_stage || frm.doc.docstatus !== 0 || !tpl) return; // saving sets the stage on a drawing template
	frm.set_intro(
		__("Inspection plan {0} is old format (no new-format plan exists for this item yet), so readings are typed into the grid below. Once a new-format plan is tagged on the item, new inspections load it automatically.", [
			`<a href="/app/quality-inspection-template/${encodeURIComponent(tpl)}">${frappe.utils.escape_html(tpl)}</a>`,
		]),
		"orange"
	);
}

// ----------------------------------------------------------- start dialog --
// "+ New Quality Inspection" starts from what is being inspected, not from a
// blank form: the stage, then the receipt row, Job Card or Work Order. The plan
// that will load is shown (with its drawing) before anything is created, and
// the new inspection opens ready for entry.

const QI_INSP = "iso_compliance.qi.inspection";
const QI_START_STAGES = [
	["Incoming", __("Incoming"), __("Goods received: a row of a Purchase Receipt.")],
	["In Process", __("In process"), __("During production: a Job Card, at first-off, patrol or last-off.")],
	["Final", __("Final"), __("Finished goods waiting in Inspection Required after a Work Order is finished.")],
];

function qi_start_dialog(frm) {
	// arrived with what to inspect already filled in (a button elsewhere): leave the form alone
	if (frm.__qi_start || frm.doc.item_code || frm.doc.reference_name) return;
	frm.__qi_start = true;
	const esc = frappe.utils.escape_html;
	const st = { stage: "Final", mode: "new", item: null, bom: null, explicit: null, lot: null };
	const d = new frappe.ui.Dialog({
		title: __("New quality inspection"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", label: __("What is inspected") },
			{ fieldname: "stage_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break" },
			{ fieldname: "purchase_receipt", fieldtype: "Link", options: "Purchase Receipt", label: __("Purchase Receipt"),
				get_query: () => ({ filters: { docstatus: ["<", 2] } }) },
			{ fieldname: "pr_row", fieldtype: "Select", label: __("Item received"), depends_on: "purchase_receipt" },
			{ fieldname: "job_card", fieldtype: "Link", options: "Job Card", label: __("Job Card"), get_query: () => ({ filters: { docstatus: 0 } }) },
			{ fieldname: "check_point", fieldtype: "Select", label: __("Checkpoint"), options: "First-off\nPatrol\nLast-off", depends_on: "job_card" },
			// finishing the Work Order puts its goods in Inspection Required, so the
			// ones to offer are those with goods still waiting -- Completed included
			{ fieldname: "work_order", fieldtype: "Link", options: "Work Order", label: __("Work Order"),
				get_query: () => ({ query: "iso_compliance.overrides.inspection_flow.work_orders_waiting" }) },
			{ fieldtype: "Column Break" },
			{ fieldname: "final_html", fieldtype: "HTML", depends_on: "work_order" },
			// what is inspected (above) is common; how it is recorded is a tab
			{ fieldtype: "Section Break" },
			{ fieldname: "mode_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "new_section", label: __("Inspection plan that will load") },
			{ fieldname: "plan_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "old_section", hidden: 1 },
			{ fieldname: "old_html", fieldtype: "HTML" },
			{ fieldname: "old_template", fieldtype: "Link", options: "Quality Inspection Template", label: __("Old-format template") },
		],
		primary_action_label: __("Start inspection"),
		primary_action: (v) => (st.mode === "old" ? open_old(v) : start(v)),
	});
	// New format: the drawing plan and the inspector screen. Old format:
	// ERPNext's own form, readings typed into its grid, filled in from above.
	const show_mode = () => {
		const tabs = [["new", __("New format")], ["old", __("Old format")]];
		d.fields_dict.mode_html.$wrapper.html(`<div class="qi-start-tabs">${tabs
			.map(([v, label]) => `<button type="button" class="qi-start-tab ${st.mode === v ? "on" : ""}" data-m="${v}">${esc(label)}</button>`)
			.join("")}</div>`);
		d.fields_dict.mode_html.$wrapper.find("[data-m]").on("click", (e) => {
			st.mode = String($(e.currentTarget).data("m"));
			show_mode();
		});
		// an item with a drawing plan always inspects on it: saving swaps any old
		// template for it (inspection.use_new_plan), so the old format is not offered
		const blocked = !!(st.plan && st.plan.new_format);
		d.set_df_property("new_section", "hidden", st.mode !== "new");
		d.set_df_property("old_section", "hidden", st.mode !== "old");
		d.set_df_property("old_template", "hidden", blocked);
		// the checkpoint is recorded on drawing inspections only
		d.set_df_property("check_point", "hidden", st.stage !== "In Process" || st.mode === "old");
		d.fields_dict.old_html.$wrapper.html(blocked
			? `<div class="qi-start-plan warn">${__("{0} has a new-format plan ({1}); inspections load it. Use New format.", [esc(st.item), esc(st.plan.template)])}</div>`
			: `<div class="text-muted small" style="margin-bottom:8px">${__("Opens ERPNext's standard inspection form with what is inspected filled in. Readings are typed into its grid; there is no drawing or inspector screen.")}</div>`);
		d.set_primary_action(st.mode === "old" ? __("Open old-format form") : __("Start inspection"), (v) => (st.mode === "old" ? open_old(v) : start(v)));
		d.get_primary_btn().prop("disabled", st.mode === "old" && blocked);
	};
	const show_stage = () => {
		d.fields_dict.stage_html.$wrapper.html(`<div class="qi-start-stages">${QI_START_STAGES.map(
			([v, label, hint]) => `<button type="button" class="qi-start-stage ${st.stage === v ? "on" : ""}" data-v="${v}"><b>${esc(label)}</b><span>${esc(hint)}</span></button>`
		).join("")}</div>`);
		d.fields_dict.stage_html.$wrapper.find("[data-v]").on("click", (e) => {
			st.stage = String($(e.currentTarget).data("v"));
			st.item = null;
			show_stage();
			plan();
		});
		d.set_df_property("purchase_receipt", "hidden", st.stage !== "Incoming");
		d.set_df_property("pr_row", "hidden", st.stage !== "Incoming");
		d.set_df_property("job_card", "hidden", st.stage !== "In Process");
		d.set_df_property("check_point", "hidden", st.stage !== "In Process" || st.mode === "old");
		d.set_df_property("work_order", "hidden", st.stage !== "Final");
		d.set_df_property("final_html", "hidden", st.stage !== "Final");
	};
	const plan = async () => {
		const $p = d.fields_dict.plan_html.$wrapper;
		st.plan = null;
		d.set_value("old_template", ""); // the last item's
		show_mode();
		if (!st.item) {
			$p.html(`<div class="text-muted small">${__("Choose what is inspected above.")}</div>`);
			return;
		}
		$p.html(`<div class="text-muted small">${__("Finding the plan…")}</div>`);
		const { message: m } = await frappe.call({
			method: `${QI_INSP}.plan_preview`,
			args: { item_code: st.item, bom_no: st.bom, stage: st.stage, explicit: st.explicit },
		});
		st.plan = m;
		show_mode();
		if (!m.template) {
			$p.html(`<div class="qi-start-plan warn">${__("{0} has no inspection plan. Build one from its BOM's Inspection Plan tab first.", [esc(st.item)])}</div>`);
			return;
		}
		if (!m.new_format) {
			$p.html(`<div class="qi-start-plan warn">${__("{0} has only the old-format plan {1}. Use the Old format tab, or build a new plan from the item's BOM.", [esc(st.item), esc(m.template)])}</div>`);
			d.set_value("old_template", m.template);
			return;
		}
		$p.html(`<div class="qi-start-plan">
			<div class="qi-start-thumb">${m.drawing ? "<canvas></canvas>" : `<span class="text-muted small">${__("No drawing")}</span>`}</div>
			<div><a href="/app/quality-inspection-template/${encodeURIComponent(m.template)}" target="_blank"><b>${esc(m.template)}</b></a>
				<div class="text-muted small">${m.drawing_no ? __("Drawing {0}", [esc(m.drawing_no + (m.revision ? " Rev " + m.revision : ""))]) : ""}</div>
				<div class="qi-start-due">${__("{0} of {1} characteristics are checked at this stage", [m.due, m.rows])}</div>
				${m.superseded_by ? `<div class="text-danger small">${__("Superseded by {0}: check with Quality.", [esc(m.superseded_by)])}</div>` : ""}
			</div></div>`);
		if (m.drawing) {
			try {
				await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
				const drawing = await window.iso_qi_pdf.open(m.drawing);
				await drawing.render(1, $p.find("canvas")[0], 220);
				drawing.close();
			} catch (e) {
				$p.find(".qi-start-thumb").html(`<span class="text-muted small">${__("Could not show the drawing")}</span>`);
			}
		}
	};
	d.fields_dict.purchase_receipt.df.onchange = async () => {
		const pr = d.get_value("purchase_receipt");
		if (!pr) return;
		const { message: doc } = await frappe.call({ method: "frappe.client.get", args: { doctype: "Purchase Receipt", name: pr } });
		st.rows = doc.items;
		d.set_df_property("pr_row", "options", doc.items.map((i) => ({ value: i.name, label: `${i.idx}. ${i.item_code} · ${i.item_name} · ${i.received_qty || i.qty} ${i.uom}` })));
		d.set_value("pr_row", doc.items[0] && doc.items[0].name);
	};
	d.fields_dict.pr_row.df.onchange = () => {
		const row = (st.rows || []).find((i) => i.name === d.get_value("pr_row"));
		Object.assign(st, { item: row && row.item_code, bom: null, explicit: null });
		plan();
	};
	d.fields_dict.job_card.df.onchange = async () => {
		const jc = d.get_value("job_card");
		if (!jc) return;
		const { message: v } = await frappe.db.get_value("Job Card", jc, ["production_item", "bom_no", "quality_inspection_template"]);
		const { message: cp } = await frappe.call({ method: `${QI_INSP}.job_card_check_points`, args: { job_card: jc } });
		d.set_value("check_point", cp.default);
		Object.assign(st, { item: v.production_item, bom: v.bom_no, explicit: v.quality_inspection_template });
		plan();
	};
	d.fields_dict.work_order.df.onchange = async () => {
		const wo = d.get_value("work_order");
		if (!wo) return;
		const { message: v } = await frappe.db.get_value("Work Order", wo, ["production_item", "bom_no"]);
		const { message: lots } = await frappe.call({ method: "iso_compliance.overrides.inspection_flow.waiting_for_work_order", args: { work_order: wo } });
		st.lots = lots || [];
		d.fields_dict.final_html.$wrapper.html(`<p class="small ${st.lots.length ? "" : "text-muted"}">${st.lots.length
			? __("Waiting in Inspection Required: {0}", [st.lots.map((r) => `${esc(r.stock_entry)} · ${format_number(r.qty)} ${esc(r.uom || "")}`).join(", ")])
			: __("Nothing waiting. Finish the Work Order first: its Manufacture entry puts the finished goods in Inspection Required.")}</p>`);
		Object.assign(st, { item: v.production_item, bom: v.bom_no, explicit: null });
		plan();
	};
	const start = async (v) => {
		if (!st.plan || !st.plan.new_format) return frappe.msgprint(__("There is no new-format plan to start from."));
		const call =
			st.stage === "Incoming"
				? { method: "start_receipt_inspection", args: { purchase_receipt: v.purchase_receipt, row: v.pr_row } }
				: st.stage === "In Process"
				? { method: "start_job_card_inspection", args: { job_card: v.job_card, check_point: v.check_point } }
				: null;
		if (!call) {
			// Final: the oldest lot of the Work Order waiting in Inspection Required
			const lot = (st.lots || [])[0];
			if (!lot) return frappe.msgprint(__("Finish the Work Order first (Finish → Manufacture entry): that puts the finished goods in Inspection Required."));
			const { message: qi } = await frappe.call({
				method: "iso_compliance.overrides.inspection_flow.start_inspection",
				args: { reference_type: "Stock Entry", reference_name: lot.stock_entry, row: lot.row },
				freeze: true, freeze_message: __("Starting the inspection…"),
			});
			d.__started = true;
			d.hide();
			return frappe.set_route("Form", "Quality Inspection", qi);
		}
		const { message: name } = await frappe.call({ method: `${QI_INSP}.${call.method}`, args: call.args, freeze: true, freeze_message: __("Starting the inspection…") });
		d.__started = true;
		d.hide();
		frappe.set_route("Form", "Quality Inspection", name);
	};
	// Old format: fill ERPNext's own form from what was chosen above
	const open_old = async (v) => {
		if (st.plan && st.plan.new_format) return;
		const lot = (st.lots || [])[0];
		const ref =
			st.stage === "Incoming" ? v.purchase_receipt && { inspection_type: "Incoming", reference_type: "Purchase Receipt", reference_name: v.purchase_receipt, child_row_reference: v.pr_row }
			: st.stage === "In Process" ? v.job_card && { inspection_type: "In Process", reference_type: "Job Card", reference_name: v.job_card }
			: lot && { inspection_type: "Outgoing", reference_type: "Stock Entry", reference_name: lot.stock_entry, child_row_reference: lot.row };
		d.__started = true;
		d.hide();
		if (!ref) return; // nothing chosen: the blank form
		// one at a time, in order: a type's change may reset the name after it
		for (const [f, val] of Object.entries(ref)) if (val) await frm.set_value(f, val);
		if (st.item) await frm.set_value("item_code", st.item);
		if (v.old_template) await frm.set_value("quality_inspection_template", v.old_template);
	};
	d.onhide = () => {
		if (!d.__started) frm.__qi_start_declined = true;
	};
	d.show();
	show_stage();
	show_mode();
	plan();
}

// ------------------------------------------------------- desktop entry --
// On a desktop a drawing inspection opens on its entry screen: a header with
// what is inspected, the drawing, and a grid -- one row per characteristic,
// one column per sample. Values save as they are typed (the call the inspector
// screen uses). It scales to long plans and big samples: the header row and
// the first columns stay put, rows can be filtered and searched, the drawing
// can be put away. Submitted inspections show the same screen, read only.
// Phones and tablets keep the full-screen inspector.

const qi_wide = () => window.matchMedia("(min-width: 992px)").matches;

// What stays on a drawing inspection's form besides the entry screen.
const QI_KEEP = ["custom_disposition", "custom_concession_no", "custom_non_conformance", "custom_accepted_qty", "custom_rejected_qty",
	"custom_transfer_entry", "inspected_by", "verified_by", "remarks", "custom_print_all_sheets"];

function qi_focus_layout(frm, entry) {
	const focus = !frm.__qi_all;
	const meta = frappe.get_meta(frm.doctype);
	meta.fields.forEach((df) => {
		if (["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype) || !frm.fields_dict[df.fieldname]) return;
		const keep = QI_KEEP.includes(df.fieldname) || (!entry && df.fieldname === "custom_measurements_html");
		// "Show all fields": back to the form's own settings, the duplicates still hidden
		const show = focus ? keep : !df.hidden && !QI_DRAWING_HIDDEN.includes(df.fieldname);
		frm.toggle_display(df.fieldname, show);
	});
	frm.toggle_display("custom_measurements_section", !entry);
	// the steps after measuring, as headings
	[["custom_disposition_section", __("2 · Disposition")], ["section_break_14", __("3 · Sign-off")]].forEach(([f, label]) => {
		const sec = frm.fields_dict[f];
		const $w = sec && sec.wrapper && $(sec.wrapper);
		if (!$w || !$w.length) return;
		$w.find(".qi-step-head").remove();
		if (focus) $w.prepend(`<div class="qi-step-head">${label}</div>`);
		$w.find(".section-head").first().toggle(!focus);
	});
	frm.page.add_menu_item(focus ? __("Show all fields") : __("Show inspection fields only"), () => {
		frm.__qi_all = !frm.__qi_all;
		frm.refresh();
	});
}

async function qi_entry(frm) {
	const esc = frappe.utils.escape_html;
	let $e = $(frm.wrapper).find(".qi-entry");
	if (!$e.length) {
		$e = $(`<div class="qi-entry"></div>`);
		// under the form's notes, above its fields
		const $msg = $(frm.wrapper).find(".form-message-container").last();
		$msg.length ? $msg.after($e) : $(frm.layout.wrapper).prepend($e);
	}
	$e.off(); // bound afresh below on every refresh
	const { message: d } = await frappe.call({ method: "iso_compliance.qi.inspector.get_inspection", args: { qi: frm.doc.name } });
	const prev = frm.__qi_entry || {};
	const state = (frm.__qi_entry = { d, row: 0, instrument: {}, filter: prev.filter || "all", q: prev.q || "", hide_dwg: !!prev.hide_dwg });
	const ro = !d.can_write;
	const bad = (r, v) => {
		if (v == null || v === "") return false;
		if (r.row_type === "Visual") return String(v).toUpperCase() === "NG";
		const n = parseFloat(String(v).replace(",", "."));
		return !(n >= r.min - 1e-9 && n <= r.max + 1e-9);
	};
	const limits = (r) => (r.row_type === "Visual" ? "OK / NG" : `${r.min_display} – ${r.max_display}`);
	const value_at = (r, n) => (r.values.find((x) => x.sample_no === n) || {}).value;
	const slots = (r) => Math.max(r.required, r.values.length, 1);
	const row_state = (r) => (r.values.some((x) => bad(r, x.value)) ? "failed" : r.values.length >= r.required ? "done" : "");
	const cols = Math.max(1, ...d.rows.map(slots));
	const type_label = { Dimension: "", Test: __("Operational"), Visual: __("Visual"), Material: __("from 3.1") };

	const cell = (r, i, n) => {
		if (n > slots(r)) return `<td class="qi-e-na"></td>`;
		const v = value_at(r, n);
		const cls = bad(r, v) ? "bad" : v != null ? "ok" : "";
		if (r.row_type === "Visual")
			return `<td><button type="button" class="qi-e-cell vis ${cls}" data-i="${i}" data-n="${n}" title="${__("Sample {0}: click for OK, again for NG", [n])}" ${ro ? "disabled" : ""}>${v || "·"}</button></td>`;
		return `<td><input class="qi-e-cell ${cls}" data-i="${i}" data-n="${n}" inputmode="decimal" autocomplete="off" value="${v == null ? "" : esc(v)}" ${ro ? "disabled" : ""}></td>`;
	};
	const instrument = (r, i) => {
		if (r.row_type === "Visual") return `<span class="text-muted">—</span>`;
		const used = r.values.length ? r.values[r.values.length - 1].instrument : null;
		const cur = state.instrument[r.balloon] || used || (r.instruments.length === 1 ? r.instruments[0].name : "");
		state.instrument[r.balloon] = cur;
		if (ro) return esc((r.instruments.find((a) => a.name === cur) || {}).asset_name || cur || "—");
		return `<select class="qi-e-inst ${!cur ? "need" : ""}" data-i="${i}">
			${!cur ? `<option value="">${__("Choose…")}</option>` : ""}
			${r.instruments.map((a) => `<option value="${esc(a.name)}" ${a.name === cur ? "selected" : ""}>${a.state === "overdue" ? "⚠ " : ""}${esc(a.asset_name || a.name)}</option>`).join("")}</select>`;
	};
	const counts = () => ({
		all: d.rows.length,
		todo: d.rows.filter((r) => r.values.length < r.required).length,
		failed: d.rows.filter((r) => row_state(r) === "failed").length,
		ctq: d.rows.filter((r) => r.class === "CTQ").length,
	});
	const visible = (r) => {
		const q = state.q.toLowerCase();
		if (q && !`${r.balloon} ${r.specification}`.toLowerCase().includes(q)) return false;
		if (state.filter === "todo") return r.values.length < r.required;
		if (state.filter === "failed") return row_state(r) === "failed";
		if (state.filter === "ctq") return r.class === "CTQ";
		return true;
	};
	const meta = (label, value) => (value ? `<div class="qi-e-meta"><span>${label}</span><b>${value}</b></div>` : "");
	const link = (dt, name) => (name ? `<a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${esc(name)}</a>` : "");
	const head = () => {
		const c = counts();
		const done = c.all - c.todo;
		return `<div class="qi-e-head">
			<div class="qi-e-title-row">
				<div><div class="qi-e-kicker">${esc(d.stage || "")}${d.check_point ? " · " + esc(d.check_point) : ""} ${__("inspection")}</div>
					<div class="qi-e-title">${esc(d.item_code)} <span>${esc(d.item_name || "")}</span></div></div>
				<div class="qi-e-progress">
					${c.failed ? `<span class="indicator-pill red">${__("{0} out of spec", [c.failed])}</span>` : ""}
					<span>${__("{0} of {1} done", [done, c.all])}</span>
					<span class="qi-e-bar"><span style="width:${c.all ? Math.round((done / c.all) * 100) : 0}%"></span></span>
					<button class="btn btn-xs btn-default qi-e-full">${__("Full-screen inspector")}</button>
				</div>
			</div>
			<div class="qi-e-metas">
				${meta(__("Plan"), link("Quality Inspection Template", d.template))}
				${meta(__("Drawing"), esc([d.drawing_no, d.drawing_revision && "Rev " + d.drawing_revision].filter(Boolean).join(" ")))}
				${meta(__("Reference"), d.reference_type ? `${esc(d.reference_type)} ${link(d.reference_type, d.reference_name)}` : "")}
				${meta(__("Work Order"), link("Work Order", d.work_order))}
				${meta(__("Lot / sample"), `${esc(d.lot_qty || "—")} / ${esc(d.sample_size)}`)}
				${meta(__("Customer"), esc(d.customer || ""))}
				${d.supplier_cert ? meta(__("Supplier 3.1"), `<a href="${esc(d.supplier_cert)}" target="_blank" rel="noopener">${__("open")}</a>`) : ""}
			</div>
		</div>`;
	};
	const toolbar = () => {
		const c = counts();
		const pill = (k, label) => `<button type="button" class="qi-pill ${state.filter === k ? "on" : ""}" data-f="${k}">${label} <span class="qi-badge">${c[k]}</span></button>`;
		return `<div class="qi-e-tools">
			${pill("all", __("All"))}${pill("todo", __("To do"))}${pill("failed", __("Out of spec"))}${c.ctq ? pill("ctq", __("CTQ")) : ""}
			<input type="search" class="form-control input-sm qi-e-search" placeholder="${__("Find no. or parameter")}" value="${esc(state.q)}">
			<span class="qi-b-spacer"></span>
			${d.drawing ? `<button type="button" class="btn btn-xs btn-default qi-e-dwg-toggle">${state.hide_dwg ? __("Show drawing") : __("Hide drawing")}</button>` : ""}
		</div>`;
	};
	const rows_html = () =>
		d.rows
			.map(
				(r, i) => `<tr data-i="${i}" class="${row_state(r)} ${visible(r) ? "" : "hidden"}">
				<td class="qi-e-s1"><span class="qi-e-num">${esc(r.balloon)}</span></td>
				<td class="qi-e-s2"><div class="qi-e-param">${esc(r.specification)}</div>
					<div class="qi-e-sub">${r.class === "CTQ" ? `<span class="qi-e-ctq">CTQ</span> ` : ""}${esc(type_label[r.row_type] || "")}${
						r.procedure ? ` <a href="/app/controlled-document/${encodeURIComponent(r.procedure)}" target="_blank">${esc(String(r.procedure).split("/").pop())}</a>` : ""
					}</div></td>
				<td class="qi-e-lim">${esc(limits(r))}<div class="qi-e-sub">${esc(r.unit || "")}</div></td>
				<td>${instrument(r, i)}</td>
				${Array.from({ length: cols }, (_, k) => cell(r, i, k + 1)).join("")}
				<td class="qi-e-res"></td></tr>`
			)
			.join("");
	$e.html(`${head()}
		${d.superseded_by ? `<div class="alert alert-warning small">${__("This drawing has a newer revision: {0}. Check with Quality before measuring.", [esc(d.superseded_by)])}</div>` : ""}
		<div class="qi-step-head">${ro ? __("Measurements") : __("1 · Measure")}</div>
		<div class="qi-e-body ${state.hide_dwg || !d.drawing ? "nodwg" : ""}">
			${d.drawing && !state.hide_dwg ? `<div class="qi-e-dwg"><div class="qi-e-close"></div></div>` : ""}
			<div class="qi-e-card">
				${toolbar()}
				<div class="qi-e-scroll"><table class="qi-e-table">
					<thead><tr><th class="qi-e-s1">${__("No.")}</th><th class="qi-e-s2">${__("Parameter")}</th><th>${__("Range")}</th><th>${__("Instrument")}</th>
						${Array.from({ length: cols }, (_, k) => `<th class="qi-e-sn">${k + 1}</th>`).join("")}<th>${__("Result")}</th></tr></thead>
					<tbody>${rows_html()}</tbody></table>
					<div class="qi-e-empty text-muted small" style="display:none">${__("No characteristic matches.")}</div></div>
				${
					d.conditions.length
						? `<details class="qi-e-conds"><summary>${__("Test conditions")} (${d.conditions.length})</summary><table class="table table-sm"><tbody>${d.conditions
								.map(
									(c) => `<tr><td>${esc(c.row_key)}</td><td>${esc(c.condition)}</td><td>${esc(c.set_value)} ${esc(c.unit || "")}${c.tolerance ? " ±" + esc(c.tolerance) : ""}</td>
								<td><input class="qi-e-cond" data-row="${esc(c.name)}" inputmode="decimal" value="${c.actual == null ? "" : esc(c.actual)}" placeholder="${__("Actual")}" ${ro ? "disabled" : ""}></td></tr>`
								)
								.join("")}</tbody></table></details>`
						: ""
				}
				${ro ? "" : `<div class="text-muted small qi-e-foot">${__("Values save as you type. Enter: next sample · ↑ ↓: same sample on the row above or below.")}</div>`}
			</div>
		</div>`);

	const result = (i) => {
		const r = d.rows[i];
		const out = r.values.filter((x) => bad(r, x.value)).length;
		const $tr = $e.find(`tr[data-i="${i}"]`);
		$tr.removeClass("done failed").addClass(row_state(r));
		$tr.find(".qi-e-res").html(`${r.values.length}/${r.required}${out ? `<div class="text-danger">${__("{0} out", [out])}</div>` : ""}`);
	};
	const refresh_counts = () => {
		$e.find(".qi-e-head").replaceWith(head());
		const c = counts();
		$e.find(".qi-e-tools [data-f]").each((_, el) => $(el).find(".qi-badge").text(c[$(el).data("f")]));
	};
	const apply_filter = () => {
		d.rows.forEach((r, i) => $e.find(`tr[data-i="${i}"]`).toggleClass("hidden", !visible(r)));
		$e.find(".qi-e-empty").toggle(!d.rows.some(visible));
		$e.find(".qi-e-tools [data-f]").each((_, el) => $(el).toggleClass("on", $(el).data("f") === state.filter));
	};
	d.rows.forEach((_, i) => result(i));
	apply_filter();

	// the drawing: the focused row's region, every number coloured by its result
	let close = null;
	const pos = (r) => {
		try {
			return r.position ? JSON.parse(r.position) : null;
		} catch (err) {
			return null;
		}
	};
	const show = async (i) => {
		state.row = i;
		$e.find("tr.cur").removeClass("cur");
		$e.find(`tr[data-i="${i}"]`).addClass("cur");
		if (!d.drawing || state.hide_dwg) return;
		const p = pos(d.rows[i]);
		const page = (p && p.page) || 1;
		// sharp page images, kept on the form until the drawing changes
		if (!frm.__qi_pages || frm.__qi_pages.url !== d.drawing) frm.__qi_pages = { url: d.drawing };
		const pages = frm.__qi_pages;
		if (!pages[page]) {
			pages[page] = (async () => {
				await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
				const drawing = await window.iso_qi_pdf.open(d.drawing);
				const c = document.createElement("canvas");
				await drawing.render(page, c, window.iso_qi_pdf.is_pdf(d.drawing) ? 2000 / Math.min(window.devicePixelRatio || 1, 2) : 2000);
				drawing.close();
				return c;
			})();
		}
		const hi = await pages[page];
		if (state.row !== i) return;
		if (!close || state.close_page !== page) {
			close = window.iso_qi_pdf.closeup($e.find(".qi-e-close"), hi, { page: __("Whole sheet") });
			state.close_page = page;
		}
		const colour = { done: "#16794C", failed: "#CC2929" };
		const boxes = d.rows
			.map((r, k) => ({ r, k, q: pos(r) }))
			.filter(({ q }) => q && (q.page || 1) === page)
			.map(({ r, k, q }) => ({ ...q, color: k === i ? "#0289F7" : colour[row_state(r)] || "rgba(120,120,120,.6)" }));
		close.show(p ? boxes.find((b) => b.x === p.x && b.y === p.y && b.w === p.w) : null, boxes);
	};

	const save = async (i, n, value) => {
		const r = d.rows[i];
		const inst = state.instrument[r.balloon] || null;
		if (value && r.row_type !== "Visual" && r.instruments.length > 1 && !inst) {
			frappe.show_alert({ message: __("Choose the instrument for No. {0} first.", [r.balloon]), indicator: "orange" });
			$e.find(`.qi-e-inst[data-i="${i}"]`).addClass("need").focus();
			return false;
		}
		const { message: m } = await frappe.call({
			method: "iso_compliance.qi.inspector.save_measurement",
			args: { qi: frm.doc.name, row_key: r.balloon, sample_no: n, value, instrument: inst },
		});
		r.values = r.values.filter((x) => x.sample_no !== n);
		if (m.value) r.values.push({ sample_no: n, value: m.value, instrument: inst });
		result(i);
		refresh_counts();
		show(i);
		return m.value;
	};

	// keyboard: Enter → next box on the row, then the next row; ↑ ↓ → same sample, row above / below
	const cell_at = (i, n) => $e.find(`.qi-e-cell[data-i="${i}"][data-n="${n}"]`)[0];
	const vis_rows = () => d.rows.map((r, i) => i).filter((i) => visible(d.rows[i]));
	const move = (el, dir) => {
		const i = Number($(el).data("i"));
		const n = Number($(el).data("n"));
		const order = vis_rows();
		let target = null;
		if (dir === "next") {
			target = cell_at(i, n + 1);
			for (let k = order.indexOf(i) + 1; !target && k < order.length; k++) target = cell_at(order[k], 1);
		} else {
			const k = order.indexOf(i) + (dir === "down" ? 1 : -1);
			if (k >= 0 && k < order.length) target = cell_at(order[k], Math.min(n, slots(d.rows[order[k]])));
		}
		if (target) {
			el.blur();
			target.focus();
			target.scrollIntoView({ block: "nearest", inline: "nearest" });
		}
	};
	$e.on("focus", ".qi-e-cell", (ev) => show(Number($(ev.currentTarget).data("i"))));
	$e.on("click", "tr[data-i] td.qi-e-s1, tr[data-i] td.qi-e-s2, tr[data-i] td.qi-e-lim", (ev) => show(Number($(ev.currentTarget).closest("tr").data("i"))));
	$e.on("input", "input.qi-e-cell", (ev) => {
		const el = ev.currentTarget;
		$(el).toggleClass("bad", bad(d.rows[Number($(el).data("i"))], el.value.trim())); // red while typing
	});
	$e.on("change", "input.qi-e-cell", async (ev) => {
		const el = ev.currentTarget;
		const i = Number($(el).data("i"));
		try {
			const v = await save(i, Number($(el).data("n")), el.value.trim());
			if (v === false) return;
			el.value = v || "";
			$(el).toggleClass("bad", bad(d.rows[i], v)).toggleClass("ok", !!v && !bad(d.rows[i], v));
		} catch (err) {
			$(el).addClass("bad");
		}
	});
	$e.on("keydown", ".qi-e-cell", (ev) => {
		const dir = { Enter: "next", ArrowDown: "down", ArrowUp: "up" }[ev.key];
		if (!dir) return;
		ev.preventDefault();
		move(ev.currentTarget, dir);
	});
	$e.on("click", "button.qi-e-cell", async (ev) => {
		const el = ev.currentTarget;
		const i = Number($(el).data("i"));
		const n = Number($(el).data("n"));
		const cur = value_at(d.rows[i], n);
		const v = await save(i, n, !cur ? "OK" : cur === "OK" ? "NG" : "");
		$(el).text(v || "·").toggleClass("ok", v === "OK").toggleClass("bad", v === "NG");
	});
	$e.on("change", ".qi-e-inst", (ev) => {
		state.instrument[d.rows[Number($(ev.currentTarget).data("i"))].balloon] = ev.currentTarget.value;
		$(ev.currentTarget).removeClass("need");
	});
	$e.on("change", ".qi-e-cond", (ev) =>
		frappe.call({ method: "iso_compliance.qi.inspector.save_condition", args: { qi: frm.doc.name, row: $(ev.currentTarget).data("row"), actual: ev.currentTarget.value } })
	);
	$e.on("click", ".qi-e-tools [data-f]", (ev) => {
		state.filter = String($(ev.currentTarget).data("f"));
		apply_filter();
	});
	$e.on(
		"input",
		".qi-e-search",
		frappe.utils.debounce((ev) => {
			state.q = ev.target.value || "";
			apply_filter();
		}, 200)
	);
	$e.on("click", ".qi-e-dwg-toggle", () => {
		state.hide_dwg = !state.hide_dwg;
		qi_entry(frm);
	});
	$e.on("click", ".qi-e-full", () => frappe.set_route("inspect", frm.doc.name));
	show(0);
	if (!ro) {
		const first = $e.find("tr:not(.hidden) input.qi-e-cell").filter((_, el) => !el.value)[0];
		if (first) setTimeout(() => first.focus({ preventScroll: true }), 300);
	}
}

frappe.dom.set_style(`
.qi-start-stages{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.qi-start-stage{text-align:left;border:1px solid var(--border-color);background:var(--fg-color);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:3px}
.qi-start-stage span{font-size:var(--text-sm);color:var(--text-muted)}
.qi-start-stage.on{border-color:var(--primary);box-shadow:0 0 0 1px var(--primary);background:var(--blue-50)}
.qi-start-tabs{display:flex;gap:4px;border-bottom:1px solid var(--border-color);margin-bottom:4px}
.qi-start-tab{border:0;background:none;padding:8px 14px;margin-bottom:-1px;border-bottom:2px solid transparent;color:var(--text-muted);font-weight:500}
.qi-start-tab.on{color:var(--text-color);border-bottom-color:var(--primary)}
.qi-start-plan{display:flex;gap:14px;align-items:flex-start;padding:10px;border:1px solid var(--border-color);border-radius:10px}
.qi-start-plan.warn{background:var(--yellow-50);border-color:var(--yellow-300);display:block}
.qi-start-thumb{width:222px;min-height:80px;border:1px solid var(--border-color);border-radius:6px;background:#fff;display:flex;align-items:center;justify-content:center;flex:none}
.qi-start-thumb canvas{display:block;max-width:100%}
.qi-start-due{margin-top:6px;font-weight:500}
@media (max-width:640px){.qi-start-stages{grid-template-columns:1fr}.qi-start-plan{flex-direction:column}}

.qi-step-head{font-size:var(--text-sm);font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);margin:4px 0 10px}
.form-section .qi-step-head{padding:0 var(--padding-md, 15px);margin-top:12px}
.qi-entry{margin:0 0 8px;padding:16px;container-type:inline-size;display:flex;flex-direction:column;gap:12px}
.qi-e-head{border:1px solid var(--border-color);border-radius:12px;padding:14px 16px;background:var(--card-bg)}
.qi-e-title-row{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.qi-e-kicker{font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--primary)}
.qi-e-title{font-size:var(--text-xl);font-weight:600;line-height:1.3}
.qi-e-title span{font-size:var(--text-base);font-weight:400;color:var(--text-muted);margin-left:6px}
.qi-e-progress{display:flex;gap:10px;align-items:center;font-size:var(--text-sm);color:var(--text-muted)}
.qi-e-bar{width:120px;height:8px;border-radius:4px;background:var(--gray-200);overflow:hidden;display:block}
.qi-e-bar span{display:block;height:100%;background:var(--green-600)}
.qi-e-metas{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border-color)}
.qi-e-meta{display:flex;flex-direction:column;font-size:var(--text-sm)}
.qi-e-meta span{font-size:var(--text-xs);color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em}
.qi-e-meta b{font-weight:500}
.qi-e-body{display:grid;grid-template-columns:minmax(300px,2fr) 3fr;gap:14px;align-items:start}
.qi-e-body.nodwg{grid-template-columns:1fr}
.qi-e-dwg{position:sticky;top:70px}
.qi-e-close .qi-dp canvas{display:block;width:100%;height:min(64vh,580px);border:1px solid var(--border-color);border-radius:12px;touch-action:none;background:#e9e9e9;cursor:grab}
.qi-e-close .qi-dp{position:relative}
.qi-e-close .qi-dp-tools{position:absolute;top:8px;right:8px;display:flex;gap:4px}
.qi-e-close .qi-dp-tools button{min-width:30px;height:28px;border:1px solid var(--border-color);border-radius:6px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.18);font-size:var(--text-sm)}
.qi-e-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);min-width:0;overflow:hidden}
.qi-e-tools{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--border-color)}
.qi-e-search{max-width:200px;height:28px}
.qi-e-tools .qi-pill{border:1px solid var(--border-color);background:var(--fg-color);border-radius:999px;padding:3px 12px;font-size:var(--text-sm);font-weight:500;color:var(--text-color)}
.qi-e-tools .qi-pill.on{background:var(--gray-800);border-color:var(--gray-800);color:var(--white)}
.qi-e-tools .qi-badge{display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;background:rgba(0,0,0,.08);font-size:11px}
.qi-e-tools .qi-pill.on .qi-badge{background:rgba(255,255,255,.25)}
.qi-e-scroll{overflow:auto;max-height:68vh}
.qi-e-table{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;font-size:var(--text-sm)}
.qi-e-table th{position:sticky;top:0;z-index:2;background:var(--subtle-fg, var(--gray-50));font-weight:600;font-size:var(--text-xs);text-transform:uppercase;letter-spacing:.03em;color:var(--text-muted);padding:8px 8px;border-bottom:1px solid var(--border-color);text-align:left;white-space:nowrap}
.qi-e-table td{padding:6px 8px;border-bottom:1px solid var(--border-color);vertical-align:middle;background:var(--card-bg)}
.qi-e-table .qi-e-s1{position:sticky;left:0;z-index:1;width:46px}
.qi-e-table .qi-e-s2{position:sticky;left:46px;z-index:1;min-width:150px;max-width:220px;box-shadow:1px 0 0 var(--border-color)}
.qi-e-table th.qi-e-s1,.qi-e-table th.qi-e-s2{z-index:3}
.qi-e-table th.qi-e-sn{text-align:center;width:72px}
.qi-e-table tr.hidden{display:none}
.qi-e-table tr.cur td{background:var(--blue-50)}
.qi-e-table tr.done .qi-e-num{background:var(--green-600)}
.qi-e-table tr.failed .qi-e-num{background:var(--red-600)}
.qi-e-num{display:inline-flex;min-width:26px;height:26px;padding:0 6px;border-radius:13px;background:var(--gray-500);color:#fff;font-weight:600;font-size:12px;align-items:center;justify-content:center}
.qi-e-param{font-weight:500}
.qi-e-sub{font-size:var(--text-xs);color:var(--text-muted)}
.qi-e-ctq{font-size:10px;font-weight:700;color:var(--red-600);border:1px solid var(--red-300);border-radius:6px;padding:0 4px}
.qi-e-lim{white-space:nowrap;font-variant-numeric:tabular-nums}
.qi-e-na{background:var(--subtle-fg, var(--gray-50)) !important}
.qi-e-cell{width:66px;height:30px;border:1px solid var(--border-color);border-radius:6px;padding:0 6px;text-align:right;font-variant-numeric:tabular-nums;background:var(--control-bg)}
button.qi-e-cell{text-align:center;color:var(--text-muted)}
.qi-e-cell:focus{outline:2px solid var(--blue-400);outline-offset:0}
.qi-e-cell.ok{background:var(--green-50);border-color:var(--green-300);color:var(--green-800)}
.qi-e-cell.bad{background:var(--red-50);border-color:var(--red-400);color:var(--red-700);font-weight:600}
.qi-e-cell:disabled{opacity:1}
.qi-e-inst{max-width:150px;height:30px;border:1px solid var(--border-color);border-radius:6px;font-size:var(--text-sm);background:var(--control-bg)}
.qi-e-inst.need{border-color:var(--orange-400);background:var(--yellow-50)}
.qi-e-res{white-space:nowrap;font-size:var(--text-xs)}
.qi-e-empty{padding:16px}
.qi-e-conds{padding:8px 12px;border-top:1px solid var(--border-color)}
.qi-e-conds summary{font-weight:600;cursor:pointer}
.qi-e-cond{width:90px;height:30px;border:1px solid var(--border-color);border-radius:6px;padding:0 6px}
.qi-e-foot{padding:8px 12px;border-top:1px solid var(--border-color)}
@container (max-width: 1000px){.qi-e-body{grid-template-columns:1fr}.qi-e-dwg{position:static}.qi-e-close .qi-dp canvas{height:340px}}
`);

// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// BOM / Item › Create › Inspection template (EXTERNAL_CHANGES.md §5).
// Opens the drawing template in use, or starts one from the drawing on the
// BOM: the template is created with the drawing attached, so the builder
// opens straight onto it.

frappe.provide("iso_qi");

// Build a new plan: the item's drawings with a preview, drawing no. and
// revision read from the file name. Built from a BOM, the BOM uses it at once.
// From the plan list (no BOM) an existing new-format plan is opened instead.
iso_qi.start_template = async function (item, bom, { fresh = false } = {}) {
	const { message: o } = await frappe.call({ method: "iso_compliance.qi.template.start_options", args: { item, bom } });
	if (o.current && !fresh) {
		frappe.set_route("Form", "Quality Inspection Template", o.current);
		return;
	}
	const esc = frappe.utils.escape_html;
	// "40.054.GA.R03.pdf" → drawing 40.054.GA, revision 03
	const guess = (file) => {
		const base = (file || "").replace(/\.(pdf|png|jpe?g)$/i, "");
		const m = base.match(/^(.*?)[ ._-]?R(?:ev)?[ ._-]?(\d{1,2})$/i);
		return m ? { no: m[1], rev: m[2] } : { no: base, rev: "" };
	};
	await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
	let picker = null;
	const d = new frappe.ui.Dialog({
		title: __("New inspection plan · {0}", [o.item_name || o.item]),
		size: o.drawings.length ? "extra-large" : "small",
		fields: [
			{ fieldname: "drawings", fieldtype: "HTML" },
			{ fieldtype: "Section Break" },
			{ fieldname: "drawing_no", fieldtype: "Data", label: __("Drawing number") },
			{ fieldtype: "Column Break" },
			{ fieldname: "revision", fieldtype: "Data", label: __("Revision") },
		],
		primary_action_label: __("Create plan"),
		primary_action: async (v) => {
			const { message } = await frappe.call({
				method: "iso_compliance.qi.template.start_template",
				args: { item: o.item, drawing_no: v.drawing_no, revision: v.revision, file: (picker && picker.chosen()) || null },
				freeze: true,
			});
			if (bom) await frappe.call({ method: "iso_compliance.qi.template.use_plan", args: { doctype: "BOM", name: bom, template: message } });
			d.hide();
			frappe.set_route("Form", "Quality Inspection Template", message);
		},
	});
	d.onhide = () => picker && picker.close();
	d.show();
	const $w = d.fields_dict.drawings.$wrapper;
	if (o.drawings.length) {
		$w.before(`<div class="qi-step">${__("1. Choose the drawing")}</div>`);
		picker = window.iso_qi_pdf.chooser($w, o.drawings, {
			onpick: (f) => {
				const g = guess(f && f.file_name);
				d.set_values({ drawing_no: g.no, revision: g.rev });
			},
		});
		d.fields_dict.drawing_no.$wrapper.closest(".form-section").before(`<div class="qi-step">${__("2. Check its number and revision")}</div>`);
	} else {
		$w.html(`<p class="text-muted">${__("No drawing is attached to {0}'s BOMs or Item. The plan can be built without one, or a drawing uploaded in it.", [esc(o.item)])}</p>`);
	}
};

iso_qi.can_build_template = () => frappe.user.has_role(["Quality Manager", "System Manager"]);

// The one place a BOM or Item gets its inspection plan: the plan in use, and
// for a Quality Manager the two ways to set it -- an existing plan (an earlier
// one included) or a new one built from the drawing. ERPNext's own template
// field stays underneath and is what this sets.
iso_qi.render_plan = async function (frm, item, bom) {
	const field = frm.fields_dict.custom_inspection_plan_html;
	if (!field) return;
	frm.toggle_display("quality_inspection_template", false);
	const esc = frappe.utils.escape_html;
	const template = frm.doc.quality_inspection_template;
	const can = iso_qi.can_build_template() && !frm.is_new() && frm.doc.docstatus !== 2;
	const where = __(frm.doctype);
	let current = "";
	if (template) {
		const { message: p } = await frappe.call({ method: "iso_compliance.qi.template.plan_summary", args: { template } });
		const rows = p.rows
			.map((r) => `<tr><td>${esc(r.balloon)}</td><td>${esc(r.specification)}</td>
				<td>${esc(r.spec_text)}</td><td>${esc(r.limits)} ${esc(r.unit)}</td><td>${esc(r["class"])}</td><td class="text-muted">${esc(r.stages)}</td></tr>`)
			.join("");
		current = `<div class="qi-plan-card">
			<div class="qi-plan-head">
				<div><div class="qi-plan-label">${__("Inspection plan in use")}</div>
				<a class="qi-plan-name" href="/app/quality-inspection-template/${encodeURIComponent(p.name)}">${esc(p.name)}</a>
				<div class="text-muted small">${p.drawing ? __("Drawing {0}", [esc([p.drawing_no, p.revision && __("Rev {0}", [p.revision])].filter(Boolean).join(" "))]) : __("No drawing")}
					· ${__("{0} characteristics", [p.rows.length])}</div></div>
				<div class="qi-plan-tags">${p.locked ? `<span class="indicator-pill orange">${__("Locked")}</span>` : ""}
					${p.superseded_by ? `<span class="indicator-pill red">${__("Superseded by {0}", [esc(p.superseded_by)])}</span>` : ""}
					${can ? `<button class="btn btn-xs btn-default qi-plan-change">${__("Change plan")}</button>` : ""}</div>
			</div>
			${p.rows.length ? `<table class="table table-sm qi-plan-table"><thead><tr><th>${__("No.")}</th><th>${__("Characteristic")}</th><th>${__("As on drawing")}</th>
				<th>${__("Limits")}</th><th>${__("Importance")}</th><th>${__("Stages")}</th></tr></thead><tbody>${rows}</tbody></table>` : ""}
		</div>`;
	}
	const choose = can
		? `<div class="qi-plan-choose" ${template ? 'style="display:none"' : ""}>
			<div class="qi-plan-opt">
				<div class="qi-plan-label">${__("Use an existing plan")}</div>
				<div class="qi-plan-list text-muted small">${__("Loading…")}</div>
				<div class="qi-plan-search"></div>
			</div>
			<div class="qi-plan-opt">
				<div class="qi-plan-label">${__("Build a new plan")}</div>
				<p class="text-muted small">${__("From the drawing on this {0}: choose it, check its number, then mark the characteristics on it.", [where])}</p>
				<button class="btn btn-sm btn-primary qi-plan-build">${__("Build new plan")}</button>
			</div>
		</div>`
		: "";
	field.$wrapper.html(`<div class="qi-plan">${current || `<div class="qi-plan-none">${__("No inspection plan on this {0} yet.", [where])}</div>`}${choose}</div>`);
	const $w = field.$wrapper;
	$w.find(".qi-plan-change").on("click", () => $w.find(".qi-plan-choose").toggle());
	$w.find(".qi-plan-build").on("click", () => iso_qi.start_template(item, bom, { fresh: true }));
	if (!can) return;
	const use = async (name) => {
		await frappe.call({ method: "iso_compliance.qi.template.use_plan", args: { doctype: frm.doctype, name: frm.doc.name, template: name }, freeze: true });
		frappe.show_alert({ message: __("{0} now uses {1}", [where, name]), indicator: "green" });
		frm.reload_doc();
	};
	const { message: plans } = await frappe.call({ method: "iso_compliance.qi.template.plan_choices", args: { item } });
	$w.find(".qi-plan-list").html(
		plans.length
			? plans
					.map(
						(p) => `<div class="qi-plan-pick ${p.name === template ? "on" : ""}">
						<div><b>${esc(p.name)}</b><div class="text-muted small">${p.custom_drawing_no ? __("Drawing {0}", [esc(p.custom_drawing_no + (p.custom_drawing_revision ? " Rev " + p.custom_drawing_revision : ""))]) + " · " : ""}${__("{0} characteristics", [p.rows])}${
							p.custom_superseded_by ? " · " + __("superseded") : ""
						}</div></div>
						${p.name === template ? `<span class="text-muted small">${__("in use")}</span>` : `<button class="btn btn-xs btn-default" data-use="${esc(p.name)}">${__("Use")}</button>`}</div>`
					)
					.join("")
			: `<span>${__("No plan has been made for this item yet.")}</span>`
	);
	$w.find("[data-use]").on("click", (e) => use(String($(e.currentTarget).data("use"))));
	// any other plan, an older one without a drawing included
	const ctl = frappe.ui.form.make_control({
		parent: $w.find(".qi-plan-search"),
		df: { fieldtype: "Link", options: "Quality Inspection Template", fieldname: "other_plan", placeholder: __("Search all plans"),
			onchange: () => ctl.get_value() && ctl.get_value() !== template && use(ctl.get_value()) },
		render_input: true,
	});
};

frappe.ui.form.on("BOM", {
	refresh(frm) {
		iso_qi.render_plan(frm, frm.doc.item, frm.doc.name);
	},
	quality_inspection_template(frm) {
		iso_qi.render_plan(frm, frm.doc.item, frm.doc.name);
	},
});

frappe.ui.form.on("Item", {
	refresh(frm) {
		iso_qi.render_plan(frm, frm.doc.name);
	},
	quality_inspection_template(frm) {
		iso_qi.render_plan(frm, frm.doc.name);
	},
});

frappe.dom.set_style(`
.qi-plan{padding:4px 0 8px;display:flex;flex-direction:column;gap:12px}
.qi-plan-none{color:var(--text-muted)}
.qi-plan-card{border:1px solid var(--border-color);border-radius:10px;padding:12px 14px}
.qi-plan-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-bottom:8px}
.qi-plan-label{font-size:var(--text-xs);text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);font-weight:600;margin-bottom:4px}
.qi-plan-name{font-size:var(--text-lg);font-weight:600}
.qi-plan-tags{display:flex;gap:6px;align-items:center}
.qi-plan-table td,.qi-plan-table th{font-size:var(--text-sm)}
.qi-plan-choose{display:grid;grid-template-columns:1.4fr 1fr;gap:12px}
.qi-plan-opt{border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;background:var(--subtle-fg, var(--gray-50))}
.qi-plan-pick{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-color);color:var(--text-color)}
.qi-plan-pick.on b{color:var(--primary)}
.qi-plan-search{margin-top:8px}
.qi-step{font-weight:600;margin:4px 0 8px}
@media (max-width:768px){.qi-plan-choose{grid-template-columns:1fr}}
`);

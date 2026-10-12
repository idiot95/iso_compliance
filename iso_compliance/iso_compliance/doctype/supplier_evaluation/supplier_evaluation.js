// FRM-005 in three steps on one panel: pick the category (Critical or
// Non-Critical, which loads that template's criteria), give each criterion
// one to five stars, then choose the decision -- the score suggests one.
// Quality and delivery arrive pre-starred from the last 12 months of
// receipts. The server repeats the arithmetic on save; this file makes it
// visible and quick.

const SE_WORDS = [__("Unacceptable"), __("Poor"), __("Acceptable"), __("Good"), __("Excellent")];

// Must match DECISION_BANDS in supplier_evaluation.py.
const SE_BANDS = [
	[80, "Approved"],
	[60, "Provisional"],
	[0, "Not Approved"],
];

const SE_DECISIONS = [
	["Approved", "green"],
	["Provisional", "orange"],
	["Not Approved", "red"],
	["Suspended", "gray"],
];

let se_templates = null;

function se_get_templates() {
	if (se_templates) return Promise.resolve(se_templates);
	return frappe.db
		.get_list("Supplier Evaluation Template", { fields: ["name", "review_months"], limit: 10 })
		.then((rows) =>
			Promise.all(rows.map((r) => frappe.db.get_doc("Supplier Evaluation Template", r.name)))
		)
		.then((docs) => {
			se_templates = {};
			docs.forEach((d) => (se_templates[d.name] = d));
			return se_templates;
		});
}

function se_apply_template(frm) {
	if (!frm.doc.category || frm.doc.docstatus !== 0) return Promise.resolve();
	return se_get_templates().then((templates) => {
		const template = templates[frm.doc.category];
		if (!template) {
			frappe.msgprint(__("There is no {0} template yet. Ask Quality to create one.", [__(frm.doc.category)]));
			return;
		}
		frm.doc.template = template.name;
		const from = frm.doc.evaluation_date || frappe.datetime.get_today();
		frm.doc.next_review_date = frappe.datetime.add_months(from, template.review_months || 12);
		const rows = frm.doc.criteria || [];
		const same =
			rows.length === template.criteria.length &&
			template.criteria.every((t, i) => rows[i].criterion === t.criterion && rows[i].weight === t.weight);
		if (!same) {
			frm.clear_table("criteria");
			template.criteria.forEach((t) =>
				frm.add_child("criteria", { criterion: t.criterion, weight: t.weight, auto_rate: t.auto_rate })
			);
		}
		frm.refresh_fields();
		// A new evaluation saves itself once it knows supplier and category, so
		// the receipt-based stars arrive without anyone pressing Save.
		if (frm.is_new() && frm.doc.supplier) return frm.save();
		se_render_panel(frm);
	});
}

function se_score(frm) {
	const rows = frm.doc.criteria || [];
	const rated = rows.filter((r) => r.rating);
	const score = rows.reduce((sum, r) => sum + (r.rating ? (r.weight * parseInt(r.rating)) / 5 : 0), 0);
	const suggestion =
		rows.length && rated.length === rows.length ? SE_BANDS.find(([floor]) => score >= floor)[1] : null;
	return { rows, rated: rated.length, score, suggestion };
}

function se_category_picker(frm, field) {
	se_get_templates().then((templates) => {
		const card = (name, line) => {
			const t = templates[name];
			const count = t ? t.criteria.length : 0;
			const months = t ? t.review_months : 0;
			return `<button type="button" class="se-cat" data-cat="${name}">
				<div class="se-cat__name">${__(name)}</div>
				<div class="se-cat__line">${line}</div>
				<div class="se-cat__meta">${__("{0} criteria · re-evaluated every {1} months", [count, months])}</div>
			</button>`;
		};
		field.$wrapper.html(`
			<div class="se-step">${__("What kind of supplier is this?")}</div>
			<div class="se-cats">
				${card("Critical", __("Material that goes into the product or decides its quality"))}
				${card("Non-Critical", __("Everything else: consumables, services, packing"))}
			</div>`);
		field.$wrapper.find(".se-cat").on("click", function () {
			frm.set_value("category", $(this).attr("data-cat"));
		});
	});
}

function se_stars(r, editable) {
	const n = parseInt(r.rating) || 0;
	const stars = [1, 2, 3, 4, 5]
		.map(
			(i) =>
				`<button type="button" class="se-star ${i <= n ? "se-star--on" : ""}" data-row="${r.name}" data-n="${i}"
					title="${SE_WORDS[i - 1]}" ${editable ? "" : "disabled"}>★</button>`
		)
		.join("");
	return `<div class="se-stars" data-row="${r.name}">${stars}</div>`;
}

function se_render_panel(frm) {
	const field = frm.get_field("rating_panel");
	if (!field) return;
	const editable = frm.doc.docstatus === 0;

	if (!frm.doc.supplier) {
		field.$wrapper.html(`<div class="se-step">${__("Pick the supplier above.")}</div>`);
		return;
	}
	if (!frm.doc.category) {
		se_category_picker(frm, field);
		return;
	}
	const s = se_score(frm);
	if (!s.rows.length) {
		field.$wrapper.html(`<div class="se-step">${__("Loading the {0} criteria…", [__(frm.doc.category)])}</div>`);
		return;
	}

	const pct = Math.round(s.score);
	const rows = s.rows
		.map((r) => {
			const word = r.rating ? SE_WORDS[parseInt(r.rating) - 1] : __("Not rated");
			const auto =
				r.auto_rate && r.remarks
					? `<span class="se-auto">${frappe.utils.escape_html(r.remarks.replace(/^auto: /, "").replace(/, last 12 months$/, ""))}</span>`
					: "";
			return `<div class="se-row ${r.rating ? "" : "se-row--open"}">
				<div class="se-crit">
					<div class="se-crit__name">${frappe.utils.escape_html(r.criterion)}</div>
					<div class="se-crit__meta">${r.weight}% ${auto}</div>
				</div>
				<div class="se-rate">${se_stars(r, editable)}<div class="se-word">${word}</div></div>
			</div>`;
		})
		.join("");

	const decisions = SE_DECISIONS.map(
		([status, colour]) =>
			`<button type="button" class="se-dec se-dec--${colour} ${frm.doc.approval_status === status ? "se-dec--on" : ""}"
				data-status="${status}" ${editable ? "" : "disabled"}>
				${__(status)}${s.suggestion === status && editable ? `<span class="se-dec__tag">${__("suggested")}</span>` : ""}
			</button>`
	).join("");

	field.$wrapper.html(`
		<div class="se-panel">
			<div class="se-head">
				<span>${__(frm.doc.category)} · ${__("{0} of {1} rated", [s.rated, s.rows.length])}</span>
				<span class="se-score">${pct}%</span>
			</div>
			<div class="se-bar"><div style="width:${pct}%"></div></div>
			${rows}
			<div class="se-decision">
				<div class="se-step">${
					!editable
						? __("Decision")
						: s.suggestion
						? __("Decision: the score suggests {0}.", [`<b>${__(s.suggestion)}</b>`])
						: __("Decision")
				}</div>
				<div class="se-decs">${decisions}</div>
			</div>
		</div>`);

	if (!editable) return;
	field.$wrapper.find(".se-star").on("click", function () {
		const row = $(this).attr("data-row");
		frappe.model.set_value("Supplier Evaluation Criterion", row, "rating", $(this).attr("data-n")).then(() =>
			se_render_panel(frm)
		);
	});
	// Hover previews the stars a click would give.
	field.$wrapper.find(".se-star").on("mouseenter", function () {
		const n = parseInt($(this).attr("data-n"));
		$(this)
			.parent()
			.find(".se-star")
			.each(function () {
				$(this).toggleClass("se-star--hover", parseInt($(this).attr("data-n")) <= n);
			});
		$(this).closest(".se-rate").find(".se-word").text(SE_WORDS[n - 1]);
	});
	field.$wrapper.find(".se-stars").on("mouseleave", function () {
		$(this).find(".se-star").removeClass("se-star--hover");
		const row = (frm.doc.criteria || []).find((r) => r.name === $(this).attr("data-row"));
		$(this)
			.closest(".se-rate")
			.find(".se-word")
			.text(row && row.rating ? SE_WORDS[parseInt(row.rating) - 1] : __("Not rated"));
	});
	field.$wrapper.find(".se-dec").on("click", function () {
		frm.set_value("approval_status", $(this).attr("data-status")).then(() => se_render_panel(frm));
	});
}

function se_inject_styles() {
	if (document.getElementById("se-form-styles")) return;
	const css = `
	.se-step { font-weight: 600; font-size: var(--text-lg); margin: 4px 0 10px; }
	.se-cats { display: flex; gap: 12px; flex-wrap: wrap; }
	.se-cat { flex: 1 1 240px; text-align: left; padding: 16px; border: 1px solid var(--border-color);
		border-radius: var(--border-radius-lg); background: var(--card-bg); cursor: pointer; }
	.se-cat:hover { border-color: var(--primary); box-shadow: var(--shadow-sm); }
	.se-cat__name { font-size: var(--text-xl); font-weight: 700; }
	.se-cat__line { margin: 4px 0; }
	.se-cat__meta { font-size: var(--text-sm); color: var(--text-muted); }
	.se-head { display: flex; justify-content: space-between; font-weight: 600; font-size: var(--text-lg); }
	.se-score { font-weight: 700; }
	.se-bar { height: 8px; border-radius: 4px; background: var(--gray-200); overflow: hidden; margin: 6px 0 12px; }
	.se-bar > div { height: 100%; background: var(--primary); transition: width .2s; }
	.se-row { display: flex; justify-content: space-between; align-items: center; gap: 12px;
		padding: 10px 14px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); margin-bottom: 6px; }
	.se-row--open { border-left: 3px solid var(--orange-400); }
	.se-crit__name { font-weight: 600; }
	.se-crit__meta { font-size: var(--text-sm); color: var(--text-muted); }
	.se-auto { margin-left: 6px; color: var(--blue-600); }
	.se-rate { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; }
	.se-stars { display: flex; }
	.se-star { background: none; border: none; padding: 0 2px; font-size: 26px; line-height: 1;
		color: var(--gray-300); cursor: pointer; }
	.se-star[disabled] { cursor: default; }
	.se-star--on { color: var(--yellow-500, #f5b301); }
	.se-star--hover { color: var(--yellow-400, #f7c948); }
	.se-word { font-size: var(--text-xs); color: var(--text-muted); min-height: 14px; }
	.se-decision { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border-color); }
	.se-decs { display: flex; flex-wrap: wrap; gap: 8px; }
	.se-dec { padding: 8px 16px; border-radius: var(--border-radius-md); border: 1px solid var(--border-color);
		background: var(--card-bg); font-weight: 600; cursor: pointer; }
	.se-dec__tag { margin-left: 6px; font-size: var(--text-xs); font-weight: 500; opacity: .8; }
	.se-dec--on.se-dec--green { background: var(--green-500); color: #fff; border-color: transparent; }
	.se-dec--on.se-dec--orange { background: var(--orange-500); color: #fff; border-color: transparent; }
	.se-dec--on.se-dec--red { background: var(--red-500); color: #fff; border-color: transparent; }
	.se-dec--on.se-dec--gray { background: var(--gray-600); color: #fff; border-color: transparent; }
	@media (max-width: 640px) { .se-row { flex-direction: column; align-items: flex-start; } .se-rate { align-items: flex-start; } }
	`;
	$("<style>").attr("id", "se-form-styles").text(css).appendTo("head");
}

function se_category_from_supplier(frm) {
	if (!frm.doc.supplier || frm.doc.category) return;
	frappe.db.get_value("Supplier", frm.doc.supplier, "custom_category").then((r) => {
		const category = r && r.message && r.message.custom_category;
		if (category) frm.set_value("category", category);
	});
}

frappe.ui.form.on("Supplier Evaluation", {
	setup() {
		se_inject_styles();
	},

	onload(frm) {
		if (frm.is_new()) {
			// First evaluation of this supplier, or a re-evaluation.
			if (!frm.doc.evaluation_type && frm.doc.supplier) {
				frappe.db
					.count("Supplier Evaluation", { filters: { supplier: frm.doc.supplier, docstatus: 1 } })
					.then((n) => frm.set_value("evaluation_type", n ? "Periodic" : "Initial"));
			} else if (!frm.doc.evaluation_type) {
				frm.doc.evaluation_type = "Initial";
			}
			if (!frm.doc.evaluation_date) frm.doc.evaluation_date = frappe.datetime.get_today();
			// Opened from the queue or the Supplier card, the supplier arrives
			// pre-filled and its change event never fires.
			se_category_from_supplier(frm);
		}
	},

	refresh(frm) {
		frm.set_intro("");
		if (frm.doc.docstatus === 0 && frm.doc.category && !(frm.doc.criteria || []).length) {
			se_apply_template(frm);
		}
		se_render_panel(frm);
	},

	supplier(frm) {
		frm.set_value("category", "");
		se_category_from_supplier(frm);
		se_render_panel(frm);
	},

	category(frm) {
		se_apply_template(frm);
	},

	evaluation_date(frm) {
		se_apply_template(frm);
	},
});

// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Inspector screen (SPEC §4.5): /app/inspect/<Quality Inspection>.
// Phone and tablet first: big touch targets, a numeric keypad, every value
// saved the moment it is entered. Tablet: drawing left, entry card right.
// Phone: the drawing folds into a strip above the card.

const INSPECT_API = "iso_compliance.qi.inspector";

frappe.pages["inspect"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Inspect"), single_column: true });
	wrapper.inspector = new Inspector(wrapper, page);
};

frappe.pages["inspect"].on_page_show = function (wrapper) {
	const name = frappe.get_route()[1];
	if (!name) {
		wrapper.inspector.empty();
		return;
	}
	wrapper.inspector.load(decodeURIComponent(name));
};

const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

class Inspector {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.$root = $(`<div class="qi-insp"></div>`).appendTo(page.main);
		this.zoom = 1;
		this.drawing = null;
		this.drawing_url = null;
		$(window).on("resize", frappe.utils.debounce(() => this.layout(), 200));
	}

	empty() {
		this.$root.html(`<div class="qi-empty">${__("Open an inspection from a Work Order, Purchase Receipt or Job Card.")}</div>`);
	}

	async load(name, keep_position) {
		const { message } = await frappe.call({ method: `${INSPECT_API}.get_inspection`, args: { qi: name } });
		const d = message;
		const prev = this.d && this.d.name === d.name ? { row: this.row, sample: this.sample, review: this.review } : null;
		this.d = d;
		this.page.set_title(`${d.item_code} · ${__(d.stage || "")} ${__("inspection")}${d.check_point ? " · " + __(d.check_point) : ""}`);
		if (keep_position && prev) {
			Object.assign(this, prev);
		} else {
			this.row = Math.max(0, d.rows.findIndex((r) => r.values.length < r.required));
			this.sample = this.next_empty(d.rows[this.row]);
			this.review = d.docstatus !== 0 ? true : false;
		}
		this.render();
	}

	get readonly() {
		return !this.d.can_write;
	}

	next_empty(r) {
		if (!r) return 1;
		const have = new Set(r.values.map((v) => v.sample_no));
		for (let i = 1; i <= Math.max(r.required, 1); i++) if (!have.has(i)) return i;
		return Math.max(r.required, 1);
	}

	row_state(r) {
		if (r.values.some((v) => this.is_bad(r, v.value))) return "failed";
		if (r.values.length >= r.required && r.required) return "done";
		return "pending";
	}

	is_bad(r, value) {
		if (value == null || value === "") return false;
		if (r.row_type === "Visual") return String(value).toUpperCase() === "NG";
		const n = parseFloat(value);
		return isNaN(n) || n < r.min - 1e-9 || n > r.max + 1e-9;
	}

	limit_text(r) {
		if (r.row_type === "Visual") return __("OK / NG");
		const u = r.unit ? " " + r.unit : "";
		if (r.min_display === "—") return `≤ ${r.max_display}${u}`;
		if (r.max_display === "—") return `≥ ${r.min_display}${u}`;
		if (r.tolerance_type === "Maximum only" && Number(r.min) === 0) return `≤ ${r.max_display}${u}`;
		return `${r.min_display} – ${r.max_display}${u}`;
	}

	// ------------------------------------------------------------- render --

	render() {
		const d = this.d;
		const done = d.rows.filter((r) => r.values.length >= r.required).length;
		const pct = d.rows.length ? Math.round((done / d.rows.length) * 100) : 0;
		this.$root.html(`
			<div class="qi-head">
				<div class="qi-head-main">
					<div class="qi-sub">${esc(d.name)} · ${esc(d.drawing_no || "")}${d.drawing_revision ? " " + __("Rev") + " " + esc(d.drawing_revision) : ""} · ${__("Lot")} ${esc(d.lot_qty || "")} · ${__("Sample")} ${esc(d.sample_size)}</div>
				</div>
				<div class="qi-progress">
					<span>${__("{0} of {1} done", [done, d.rows.length])}</span>
					<span class="qi-bar"><span style="width:${pct}%"></span></span>
					<span class="qi-saved">${d.docstatus === 1 ? __("Submitted") : d.docstatus === 2 ? __("Cancelled") : __("Saved")}</span>
				</div>
			</div>
			${d.superseded_by ? `<div class="qi-banner warn">${__("This drawing has a newer revision: {0}. Check with Quality before measuring.", [esc(d.superseded_by)])}</div>` : ""}
			${this.readonly && d.docstatus === 0 ? `<div class="qi-banner">${__("You can view this inspection but not change it.")}</div>` : ""}
			<div class="qi-body">
				<div class="qi-drawing">
					<button class="qi-strip">${__("Drawing")} · ${esc(d.drawing_no || "")} <span>${__("Show")} ▾</span></button>
					<div class="qi-canvas-wrap"><div class="qi-stage"><canvas></canvas><div class="qi-overlay"></div></div></div>
					<div class="qi-zoom"><button data-z="-1" aria-label="${__("Zoom out")}">−</button><button data-z="1" aria-label="${__("Zoom in")}">+</button><span>${__("Tap a balloon")}</span></div>
				</div>
				<div class="qi-panel"></div>
			</div>`);
		this.$root.find(".qi-strip").on("click", () => this.$root.find(".qi-drawing").toggleClass("open") && this.draw_page());
		this.$root.find(".qi-zoom button").on("click", (e) => {
			this.zoom = Math.min(4, Math.max(1, this.zoom + Number($(e.currentTarget).data("z")) * 0.5));
			this.draw_page();
		});
		this.render_panel();
		this.load_drawing();
	}

	render_panel() {
		if (this.review) this.render_review();
		else this.render_card();
		this.render_balloons();
	}

	render_card() {
		const d = this.d;
		const r = d.rows[this.row];
		const $p = this.$root.find(".qi-panel");
		if (!r) {
			$p.html(`<div class="qi-empty">${__("No rows on this inspection.")}</div>`);
			return;
		}
		const value_at = (n) => (r.values.find((v) => v.sample_no === n) || {}).value;
		const bad = r.values.filter((v) => this.is_bad(r, v.value)).length;
		const current = value_at(this.sample);
		const instr = r.values.length ? r.values[r.values.length - 1].instrument : null;
		const instrument_html = r.instruments.length
			? `<label class="qi-field">${__("Instrument")}
				<select class="qi-instrument">${
					// more than one allowed: the inspector says which one is in hand
					r.instruments.length > 1 && !r.instruments.some((a) => a.name === (this.instrument || instr))
						? `<option value="" selected disabled>${__("Which instrument are you using?")}</option>`
						: ""
				}${r.instruments
					.map(
						(a) =>
							`<option value="${esc(a.name)}" ${a.name === (this.instrument || instr) ? "selected" : ""}>${esc(a.asset_name)} (${esc(a.name)})</option>`
					)
					.join("")}</select>
				<span class="qi-cal"></span></label>`
			: "";
		const conds = d.conditions.filter((c) => c.row_key === r.balloon);
		const cond_html = conds.length
			? `<div class="qi-conds"><div class="qi-cond qi-cond-h"><span>${__("Condition")}</span><span>${__("Set")}</span><span>${__("Actual")}</span></div>${conds
					.map((c) => {
						const off = c.actual != null && c.tolerance && Math.abs(c.actual - c.set_value) > c.tolerance + 1e-9;
						return `<div class="qi-cond"><span>${esc(c.condition)}</span><span>${esc(c.set_value)} ${esc(c.unit || "")}${
							c.tolerance ? " ±" + esc(c.tolerance) : ""
						}</span><input inputmode="decimal" class="qi-cond-in ${off ? "bad" : ""}" data-row="${esc(c.name)}" value="${c.actual == null ? "" : esc(c.actual)}" ${
							this.readonly ? "disabled" : ""
						} aria-label="${esc(c.condition)}"></div>`;
					})
					.join("")}</div>`
			: "";
		const wi = r.procedure || (d.work_instructions.find((w) => w.level === "Stage") || {}).controlled_document;
		const entry =
			r.row_type === "Visual"
				? `<div class="qi-okng">
					<button class="qi-ok ${current === "OK" ? "on" : ""}" ${this.readonly ? "disabled" : ""}>OK</button>
					<button class="qi-ng ${current === "NG" ? "on" : ""}" ${this.readonly ? "disabled" : ""}>NG</button></div>`
				: `<label class="qi-field">${__("Reading")}${r.unit ? " (" + esc(r.unit) + ")" : ""}
					<input class="qi-value ${this.is_bad(r, current) ? "bad" : ""}" inputmode="decimal" autocomplete="off" value="${current == null ? "" : esc(current)}" ${
						this.readonly ? "disabled" : ""
					}></label>`;
		const grid = Array.from({ length: Math.max(r.required, r.values.length, 1) }, (_, i) => i + 1)
			.map((n) => {
				const v = value_at(n);
				const cls = n === this.sample ? "cur" : v == null ? "empty" : this.is_bad(r, v) ? "bad" : "ok";
				return `<button class="qi-chip ${cls}" data-n="${n}" aria-label="${__("Sample")} ${n}">${v == null ? n : esc(v)}</button>`;
			})
			.join("");
		$p.html(`
			<div class="qi-card">
				<div class="qi-card-head">
					<div><span class="qi-num">${esc(r.balloon)}</span><span class="qi-name">${esc(r.specification)}</span>
					${r.row_type !== "Dimension" ? `<span class="qi-type">${esc(__(r.row_type === "Material" ? "From 3.1" : r.row_type))}</span>` : ""}</div>
					${r.class ? `<span class="qi-class ${esc(r.class.toLowerCase())}">${esc(r.class)}</span>` : ""}
				</div>
				<div class="qi-spec"><span>${__("As on drawing")}</span><strong>${esc(r.spec_text || "")}${r.spec_text ? " → " : ""}${esc(this.limit_text(r))}</strong></div>
				${r.test_method ? `<div class="qi-muted">${esc(r.test_method)}</div>` : ""}
				${r.row_type === "Material" ? `<div class="qi-banner">${__("Read this value off the supplier's 3.1 certificate.")}
					${d.supplier_cert ? ` <a href="${esc(d.supplier_cert)}" target="_blank" rel="noopener">${__("Open the certificate")}</a>` : ` <b>${__("No certificate is attached to the Purchase Receipt.")}</b>`}</div>` : ""}
				${instrument_html}
				${cond_html}
				<div class="qi-stepper">
					<button class="qi-prev-s" aria-label="${__("Previous sample")}">‹</button>
					<div><div class="qi-muted">${__("Sample")}</div><div class="qi-big">${__("{0} of {1}", [this.sample, r.required])}</div></div>
					<button class="qi-next-s" aria-label="${__("Next sample")}">›</button>
				</div>
				${entry}
				${wi ? `<a class="qi-howto" href="/app/controlled-document/${encodeURIComponent(wi)}" target="_blank">${__("How to do this")} · ${esc(wi.split("/").pop())}</a>` : ""}
			</div>
			<div class="qi-card">
				<div class="qi-card-head small"><strong>${__("Readings")}</strong>${bad ? `<span class="qi-bad-text">${__("{0} out of spec", [bad])}</span>` : ""}</div>
				<div class="qi-grid">${grid}</div>
			</div>
			<div class="qi-nav">
				<button class="qi-prev-r" ${this.row === 0 ? "disabled" : ""}>${this.row > 0 ? __("Previous") + ": #" + esc(d.rows[this.row - 1].balloon) : __("Previous")}</button>
				<button class="qi-next-r primary">${
					this.row < d.rows.length - 1 ? __("Next") + ": #" + esc(d.rows[this.row + 1].balloon) + " " + esc(d.rows[this.row + 1].specification) : __("Review and submit")
				}</button>
			</div>`);
		this.bind_card(r);
	}

	bind_card(r) {
		const $p = this.$root.find(".qi-panel");
		const $in = $p.find(".qi-value");
		const show_cal = () => {
			const a = r.instruments.find((x) => x.name === $p.find(".qi-instrument").val());
			const $c = $p.find(".qi-cal").removeClass("ok warn none");
			if (!a) return;
			if (a.state === "ok") $c.addClass("ok").text("✓ " + __("Calibration due {0}", [frappe.datetime.str_to_user(a.due)]));
			else if (a.state === "overdue") $c.addClass("warn").text("⚠ " + __("Calibration overdue since {0}", [frappe.datetime.str_to_user(a.due)]));
			else $c.addClass("none").text(__("No calibration record"));
		};
		$p.find(".qi-instrument").on("change", (e) => {
			this.instrument = e.target.value;
			show_cal();
		});
		show_cal();
		$p.find(".qi-prev-s").on("click", () => this.go_sample(this.sample - 1));
		$p.find(".qi-next-s").on("click", () => this.go_sample(this.sample + 1));
		$p.find(".qi-chip").on("click", (e) => this.go_sample(Number($(e.currentTarget).data("n"))));
		$p.find(".qi-prev-r").on("click", () => this.go_row(this.row - 1));
		$p.find(".qi-next-r").on("click", () => (this.row < this.d.rows.length - 1 ? this.go_row(this.row + 1) : this.open_review()));
		$p.find(".qi-ok").on("click", () => this.save(r, "OK", true));
		$p.find(".qi-ng").on("click", () => this.save(r, "NG", true));
		$in.on("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				this.save(r, $in.val(), true);
			}
		});
		$in.on("change", () => this.save(r, $in.val(), false));
		$p.find(".qi-cond-in").on("change", (e) => {
			const row = $(e.currentTarget).data("row");
			const val = e.currentTarget.value;
			frappe.call({ method: `${INSPECT_API}.save_condition`, args: { qi: this.d.name, row, actual: val } }).then(() => {
				const c = this.d.conditions.find((x) => x.name === row);
				c.actual = val === "" ? null : parseFloat(val);
				$(e.currentTarget).toggleClass("bad", c.actual != null && c.tolerance && Math.abs(c.actual - c.set_value) > c.tolerance + 1e-9);
			});
		});
		if ($in.length && !this.readonly && window.matchMedia("(min-width: 768px)").matches) $in.trigger("focus").select();
	}

	async save(r, raw, advance) {
		if (this.readonly) return;
		const sample = this.sample;
		const value = String(raw == null ? "" : raw).trim();
		const existing = r.values.find((v) => v.sample_no === sample);
		if ((existing ? existing.value : "") === value && !advance) return;
		this.set_saving(true);
		try {
			const instrument = this.$root.find(".qi-instrument").val() || null;
			const { message: m } = await frappe.call({
				method: `${INSPECT_API}.save_measurement`,
				args: { qi: this.d.name, row_key: r.balloon, sample_no: sample, value, instrument },
			});
			r.values = r.values.filter((v) => v.sample_no !== sample);
			if (m.value) r.values.push({ sample_no: sample, value: m.value, instrument });
			r.values.sort((a, b) => a.sample_no - b.sample_no);
			r.status = m.status;
			if (this.is_bad(r, m.value)) frappe.utils.play_sound && frappe.utils.play_sound("error");
			if (advance && value) {
				if (r.values.length >= r.required && this.row < this.d.rows.length - 1 && sample >= r.required) {
					this.go_row(this.row + 1);
				} else {
					this.sample = Math.min(this.next_empty(r), Math.max(r.required, sample + 1));
					this.render_panel();
					this.update_progress();
				}
			} else {
				this.render_panel();
				this.update_progress();
			}
		} finally {
			this.set_saving(false);
		}
	}

	set_saving(on) {
		this.$root.find(".qi-saved").text(on ? __("Saving…") : __("Saved")).toggleClass("busy", on);
	}

	update_progress() {
		const done = this.d.rows.filter((r) => r.values.length >= r.required).length;
		this.$root.find(".qi-progress > span:first").text(__("{0} of {1} done", [done, this.d.rows.length]));
		this.$root.find(".qi-bar > span").css("width", Math.round((done / this.d.rows.length) * 100) + "%");
	}

	go_sample(n) {
		const r = this.d.rows[this.row];
		this.sample = Math.min(Math.max(1, n), Math.max(r.required, r.values.length, 1));
		this.render_panel();
	}

	go_row(i) {
		this.review = false;
		this.row = Math.min(Math.max(0, i), this.d.rows.length - 1);
		this.sample = this.next_empty(this.d.rows[this.row]);
		this.render_panel();
		this.focus_balloon();
	}

	// ------------------------------------------------------------- review --

	async open_review() {
		this.review = true;
		this.render_panel();
	}

	async render_review() {
		const d = this.d;
		const $p = this.$root.find(".qi-panel");
		$p.html(`<div class="qi-card"><div class="qi-muted">${__("Checking…")}</div></div>`);
		const { message: s } = await frappe.call({ method: `${INSPECT_API}.summary`, args: { qi: d.name } });
		const failed = s.rows.filter((r) => r.status === "Rejected");
		const short = s.rows.filter((r) => r.n < r.required);
		const any_fail = failed.length > 0;
		const disp = d.disposition || (any_fail ? "" : "Accepted");
		const opt = (value, label, note, disabled) =>
			`<label class="qi-radio ${disp === value ? "on" : ""} ${disabled ? "off" : ""}"><input type="radio" name="disp" value="${value}" ${
				disp === value ? "checked" : ""
			} ${disabled || this.readonly ? "disabled" : ""}> ${label}${note ? `<span>${note}</span>` : ""}</label>`;
		$p.html(`
			<div class="qi-card">
				<div class="qi-card-head small"><strong>${__("{0} characteristics", [s.rows.length])}</strong>
				<span><span class="qi-ok-text">${__("{0} pass", [s.rows.length - failed.length])}</span>${
					any_fail ? ` · <span class="qi-bad-text">${__("{0} out of spec", [failed.length])}</span>` : ""
				}</span></div>
				${failed
					.map(
						(r) => `<button class="qi-fail" data-b="${esc(r.balloon)}"><span>#${esc(r.balloon)} ${esc(r.specification)}${r.class ? " (" + esc(r.class) + ")" : ""}</span><span>${__(
							"{0} of {1}",
							[r.out, r.n]
						)}${r.obs_min != null ? " · " + esc(r.obs_min) + " – " + esc(r.obs_max) : ""}</span></button>`
					)
					.join("")}
				${short
					.map(
						(r) =>
							`<button class="qi-short" data-b="${esc(r.balloon)}"><span>#${esc(r.balloon)} ${esc(r.specification)}${r.class === "CTQ" ? " (CTQ)" : ""}</span><span>${__(
								"{0} of {1} measured",
								[r.n, r.required]
							)}</span></button>`
					)
					.join("")}
			</div>
			<fieldset class="qi-card qi-disp"><legend>${__("Disposition")}</legend>
				${opt("Accepted", __("Accepted"), any_fail ? __("needs all in spec") : "", any_fail)}
				${opt("Accept under Concession", __("Accept under concession"))}
				${opt("Rework", __("Rework and re-inspect"))}
				${opt("Rejected", __("Rejected"))}
			</fieldset>
			<div class="qi-concession" style="${disp === "Accept under Concession" ? "" : "display:none"}">
				<div class="qi-banner warn"><strong>${__("These goods don't meet specification")}</strong><br>${__(
					"They will be released as accepted under concession, and the failed readings stay on record."
				)}</div>
				<label class="qi-field">${__("Customer concession no.")} <span class="qi-muted">${__("(if the deviation is from their spec)")}</span>
					<input class="qi-conc-no" value="${esc(d.concession_no || "")}" ${this.readonly ? "disabled" : ""}></label>
			</div>
			${d.non_conformance ? `<div class="qi-muted">${__("Non Conformance")}: <a href="/app/non-conformance/${encodeURIComponent(d.non_conformance)}">${esc(d.non_conformance)}</a></div>` : ""}
			${!this.readonly && any_fail && !d.non_conformance ? `<button class="qi-nc">+ ${__("Raise Non Conformance (pre-filled)")}</button>` : ""}
			<div class="qi-nav">
				<button class="qi-back">${__("Back to readings")}</button>
				${this.d.can_submit ? `<button class="qi-submit primary">${__("Submit inspection")}</button>` : ""}
				${!this.d.can_submit && this.d.can_write ? `<button class="qi-savedraft primary">${__("Save")}</button>` : ""}
			</div>`);
		$p.find("input[name=disp]").on("change", (e) => {
			$p.find(".qi-radio").removeClass("on");
			$(e.currentTarget).closest(".qi-radio").addClass("on");
			$p.find(".qi-concession").toggle(e.currentTarget.value === "Accept under Concession");
		});
		$p.find(".qi-fail, .qi-short").on("click", (e) => this.go_row(d.rows.findIndex((r) => r.balloon === String($(e.currentTarget).data("b")))));
		$p.find(".qi-back").on("click", () => this.go_row(this.row));
		$p.find(".qi-nc").on("click", () => this.raise_nc(failed));
		$p.find(".qi-submit").on("click", () => this.finish(true));
		$p.find(".qi-savedraft").on("click", () => this.finish(false));
	}

	finish(submit) {
		const $p = this.$root.find(".qi-panel");
		const disposition = $p.find("input[name=disp]:checked").val() || "";
		const go = () =>
			frappe
				.call({
					method: `${INSPECT_API}.finish`,
					args: {
						qi: this.d.name,
						disposition,
						concession_no: $p.find(".qi-conc-no").val() || "",
						non_conformance: this.d.non_conformance || "",
						submit: submit ? 1 : 0,
					},
					freeze: true,
				})
				.then(({ message }) => {
					frappe.show_alert({ message: submit ? __("Inspection submitted") : __("Saved"), indicator: "green" });
					this.load(this.d.name, true);
				});
		if (!submit) return go();
		if (!disposition) {
			frappe.msgprint(__("Choose a disposition."));
			return;
		}
		frappe.confirm(__("Submit the inspection as {0}? It can't be changed afterwards.", [__(disposition)]), go);
	}

	raise_nc(failed) {
		const d = this.d;
		frappe.route_options = {
			subject: __("Inspection {0} — {1}", [d.name, d.item_code]),
			status: "Open",
			custom_source: { Incoming: "Incoming", "In Process": "In-Process", Final: "Final Inspection" }[d.stage] || "Production",
			custom_quality_inspection: d.name,
			custom_item: d.item_code,
			custom_qty: d.lot_qty,
			details: __("Failed: {0}", [failed.map((r) => `#${r.balloon} ${r.specification}: ${r.out} of ${r.n} out (${r.obs_min} – ${r.obs_max})`).join("; ")]),
		};
		if (d.reference_type === "Purchase Receipt") frappe.route_options.custom_purchase_receipt = d.reference_name;
		frappe.new_doc("Non Conformance");
	}

	// ------------------------------------------------------------ drawing --

	async load_drawing() {
		const url = this.d.drawing;
		const $wrap = this.$root.find(".qi-canvas-wrap");
		if (!url) {
			this.$root.find(".qi-drawing").addClass("none");
			return;
		}
		try {
			if (this.drawing_url !== url) {
				await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
				this.drawing = await window.iso_qi_pdf.open(url);
				this.drawing_url = url;
			}
			await this.draw_page();
		} catch (e) {
			console.error(e);
			$wrap.html(`<div class="qi-muted" style="padding:12px">${__("Could not show the drawing here")}: ${esc(e.message)}
				· <a href="${esc(url)}" target="_blank" rel="noopener">${__("open the file")}</a></div>`);
		}
	}

	current_page() {
		const r = this.d.rows[this.row];
		const pos = r && this.pos(r);
		return (pos && pos.page) || 1;
	}

	pos(r) {
		try {
			return r.position ? JSON.parse(r.position) : null;
		} catch (e) {
			return null;
		}
	}

	async draw_page() {
		if (!this.drawing) return;
		const $wrap = this.$root.find(".qi-canvas-wrap");
		if (!$wrap.is(":visible")) return;
		this.page_no = this.current_page();
		const width = Math.max(280, $wrap.width() - 2) * this.zoom;
		const size = await this.drawing.render(this.page_no, $wrap.find("canvas")[0], width);
		if (!size) return;
		$wrap.find(".qi-stage").css({ width: size.w, height: size.h });
		this.render_balloons();
		this.focus_balloon();
	}

	render_balloons() {
		const $ov = this.$root.find(".qi-overlay").empty();
		if (!this.drawing) return;
		this.d.rows.forEach((r, i) => {
			const p = this.pos(r);
			if (!p || (p.page || 1) !== this.page_no) return;
			const state = i === this.row && !this.review ? "current" : this.row_state(r);
			$(`<button class="qi-bx ${state}" aria-label="${__("Balloon")} ${esc(r.balloon)}"><span>${esc(r.balloon)}</span></button>`)
				.css({ left: p.x + "%", top: p.y + "%", width: p.w + "%", height: p.h + "%" })
				.on("click", () => {
					this.go_row(i);
					if (window.matchMedia("(max-width: 767px)").matches) this.$root.find(".qi-drawing").removeClass("open");
				})
				.appendTo($ov);
		});
	}

	focus_balloon() {
		if (this.current_page() !== this.page_no) {
			this.draw_page();
			return;
		}
		this.render_balloons();
		const $b = this.$root.find(".qi-bx.current");
		if ($b.length && this.zoom > 1) $b[0].scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
	}

	layout() {
		if (this.d) this.draw_page();
	}
}

frappe.dom.set_style(`
.qi-insp{--ok:#16794C;--okbg:#E4FAEB;--bad:#CC2929;--badbg:#FFE7E7;--cur:#0289F7;--warn:#7A4A00;--warnbg:#FFF8EB;font-size:15px}
.qi-insp button{min-height:44px;border-radius:10px;border:1px solid var(--border-color);background:var(--card-bg);color:var(--text-color);font-size:14px;padding:0 12px}
.qi-insp button.primary{background:var(--gray-900);color:#fff;border-color:var(--gray-900);font-weight:500}
.qi-insp button:disabled{opacity:.45}
.qi-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;padding:8px 0 12px}
.qi-sub{font-size:13px;color:var(--text-muted)}
.qi-progress{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--text-muted)}
.qi-bar{width:140px;height:8px;border-radius:4px;background:var(--gray-200);overflow:hidden;display:block}
.qi-bar span{display:block;height:100%;background:var(--ok)}
.qi-saved{color:var(--ok)}.qi-saved.busy{color:var(--text-muted)}
.qi-banner{padding:10px 12px;border-radius:10px;background:var(--gray-100);margin-bottom:10px;font-size:13px}
.qi-banner.warn{background:var(--warnbg);color:var(--warn);border:1px solid #F5D9A8}
.qi-body{display:flex;gap:16px;align-items:flex-start}
.qi-drawing{flex:1.25;min-width:0;position:sticky;top:60px}
.qi-drawing.none{display:none}
.qi-strip{display:none!important}
.qi-canvas-wrap{border:1px solid var(--border-color);border-radius:12px;background:#fff;overflow:auto;max-height:calc(100vh - 190px);touch-action:pan-x pan-y}
.qi-stage{position:relative;margin:0 auto}.qi-stage canvas{display:block}
.qi-overlay{position:absolute;inset:0}
.qi-insp .qi-bx{position:absolute;min-height:0;padding:0;border-radius:3px;border:2px solid #B3B3B3;background:transparent}
.qi-bx span{position:absolute;top:-13px;left:-13px;width:26px;height:26px;border-radius:13px;background:#B3B3B3;color:#fff;font-size:12px;font-weight:600;display:flex;align-items:center;justify-content:center}
.qi-insp .qi-bx.done{border-color:var(--ok);background:rgba(39,143,94,.08)}.qi-bx.done span{background:var(--ok)}
.qi-insp .qi-bx.failed{border-color:var(--bad);background:rgba(204,41,41,.08)}.qi-bx.failed span{background:var(--bad)}
.qi-insp .qi-bx.current{border-color:var(--cur);border-width:3px;background:rgba(2,137,247,.14)}.qi-bx.current span{background:var(--cur);width:30px;height:30px;top:-15px;left:-15px}
.qi-zoom{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:13px;color:var(--text-muted)}
.qi-zoom button{width:44px;font-size:18px}
.qi-panel{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px}
.qi-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:12px;margin:0}
.qi-card-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
.qi-card-head.small{font-size:13px}
.qi-num{display:inline-flex;min-width:30px;height:30px;padding:0 6px;border-radius:15px;background:var(--cur);color:#fff;align-items:center;justify-content:center;font-weight:600;margin-right:10px}
.qi-name{font-size:18px;font-weight:600}
.qi-type{font-size:11px;padding:2px 7px;border-radius:999px;background:#F1E9FD;color:#6B2FC9;margin-left:8px}
.qi-class{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--gray-100);font-weight:500}
.qi-class.ctq{background:var(--badbg);color:var(--bad)}.qi-class.major{background:#FFF1E7;color:#B54708}
.qi-spec{display:flex;justify-content:space-between;gap:8px;font-size:14px}.qi-spec span{color:var(--text-muted)}
.qi-muted{color:var(--text-muted);font-size:13px}
.qi-field{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--text-muted);margin:0}
.qi-field select,.qi-field input{min-height:44px;border-radius:10px;border:1px solid var(--border-color);padding:0 12px;font-size:15px;background:var(--control-bg);color:var(--text-color)}
.qi-cal.ok{color:var(--ok)}.qi-cal.warn{color:var(--bad)}.qi-cal.none{color:var(--text-muted)}
.qi-insp input.qi-value{height:64px;border:2px solid var(--cur);font-size:30px;font-weight:600}
.qi-insp input.bad{border-color:var(--bad);color:var(--bad);background:var(--badbg)}
.qi-stepper{display:flex;align-items:center;justify-content:space-between;text-align:center}
.qi-stepper button{width:52px;height:52px;font-size:22px}
.qi-big{font-size:22px;font-weight:600}
.qi-okng{display:flex;gap:10px}.qi-okng button{flex:1;height:72px;font-size:22px;font-weight:600}
.qi-insp .qi-ok.on{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.qi-insp .qi-ng.on{background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.qi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}
.qi-insp .qi-chip{min-height:36px;padding:0;font-size:13px;font-variant-numeric:tabular-nums}
.qi-insp .qi-chip.ok{background:var(--okbg);color:var(--ok);border-color:transparent}
.qi-insp .qi-chip.bad{background:var(--badbg);color:var(--bad);border-color:transparent;font-weight:600}
.qi-insp .qi-chip.empty{background:var(--gray-100);color:var(--gray-400);border-color:transparent}
.qi-insp .qi-chip.cur{border:2px solid var(--cur)}
.qi-conds{display:flex;flex-direction:column;gap:6px}
.qi-cond{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr);gap:6px;align-items:center;font-size:13px}
.qi-cond-h{color:var(--text-muted);font-size:12px}
.qi-cond input{height:40px;border-radius:8px;border:1px solid var(--border-color);padding:0 8px;min-width:0}
.qi-howto{font-size:13px}
.qi-nav{display:flex;gap:10px}.qi-nav button{flex:1;height:52px}
.qi-bad-text{color:var(--bad)}.qi-ok-text{color:var(--ok)}
.qi-insp .qi-fail,.qi-insp .qi-short{display:flex;justify-content:space-between;gap:8px;text-align:left;border:0;font-size:13px}
.qi-insp .qi-fail{background:var(--badbg);color:var(--bad)}
.qi-insp .qi-short{background:var(--warnbg);color:var(--warn)}
.qi-disp legend{font-size:13px;font-weight:600;border:0;margin:0 0 4px;width:auto}
.qi-radio{display:flex;align-items:center;gap:10px;min-height:48px;padding:0 12px;border-radius:12px;border:1px solid var(--border-color);font-size:14px;margin:0;color:var(--text-color)}
.qi-radio span{margin-left:auto;font-size:12px;color:var(--text-muted)}
.qi-radio.on{border:2px solid #E79913;background:var(--warnbg)}
.qi-radio.off{color:var(--gray-400)}
.qi-insp .qi-nc{border-style:dashed;width:100%}
.qi-concession{display:flex;flex-direction:column;gap:10px}
.qi-empty{padding:40px 0;text-align:center;color:var(--text-muted)}
@media (max-width:767px){
	.qi-body{flex-direction:column}
	.qi-drawing{position:static;width:100%}
	.qi-strip{display:flex!important;width:100%;justify-content:space-between;align-items:center}
	.qi-strip span{color:var(--cur)}
	.qi-drawing .qi-canvas-wrap,.qi-drawing .qi-zoom{display:none}
	.qi-drawing.open .qi-canvas-wrap{display:block;margin-top:8px;max-height:55vh}
	.qi-drawing.open .qi-zoom{display:flex}
	.qi-panel{width:100%}
	.qi-bar{width:90px}
}
`);

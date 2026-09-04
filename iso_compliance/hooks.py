app_name = "iso_compliance"
app_title = "ISO Compliance"
app_publisher = "Hatim Carbon Co. Pvt. Ltd."
app_description = "ISO 9001 document control, revision history and QMS records"
app_email = "da@alvazarat.org"
app_license = "mit"

# Apps
# ------------------

# Link fields on this app's DocTypes point at Supplier, Department, Designation,
# Asset and Quality Action, so a migrate without ERPNext fails on the first sync.
# Declaring it makes that a clear install-time error instead.
#
# hrms is deliberately NOT required. It owns four of the forty-two register
# mappings (training records and the competency matrix); without it those four
# registers are simply unmapped and the rest of the app is unaffected.
required_apps = ["erpnext"]

# The only records this app writes into another app's DocTypes, each one
# approved and logged in EXTERNAL_CHANGES.md first. Named explicitly so an
# export can never sweep up another app's custom fields.
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["name", "in", ["Quality Meeting-custom_minutes_guidance"]]],
	},
	{
		"dt": "Property Setter",
		"filters": [
			[
				"name",
				"in",
				[
					"BOM-inspection_required-description",
					"Item-inspection_required_before_delivery-description",
				],
			]
		],
	},
]

# Shows ISO Compliance on the desk apps screen, opening straight onto the dashboard.
add_to_apps_screen = [
	{
		"name": "iso_compliance",
		"logo": "/assets/iso_compliance/images/hcc-mark.png",
		"title": "ISO Compliance",
		"route": "/app/iso-compliance",
		"has_permission": "iso_compliance.api.permission.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/iso_compliance/css/iso_compliance.css"
# app_include_js = "/assets/iso_compliance/js/iso_compliance.js"

# include js, css files in header of web template
# web_include_css = "/assets/iso_compliance/css/iso_compliance.css"
# web_include_js = "/assets/iso_compliance/js/iso_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "iso_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}

# Convenience only (the gate itself is server-side): a create button that
# opens FRM-036 pre-filled from the order, and a banner when SOP-004's slabs
# demand a review. Logged in EXTERNAL_CHANGES.md.
doctype_js = {"Sales Order": "public/js/sales_order.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "iso_compliance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# The Certificate of Conformity resolves every inspection behind a delivered
# row (despatch, PDI, in-process) through the batch's own trace.
jinja = {
	"methods": ["iso_compliance.utils.coc_row_inspections", "iso_compliance.utils.coc_row_aggregate"],
}

# Installation
# ------------

# before_install = "iso_compliance.install.before_install"
after_install = "iso_compliance.setup.install.after_install"

# Idempotent and additive, so a routine upgrade brings the lifecycle states with
# it. Seed data is deliberately not here: a migrate must never write 93
# controlled documents into production by itself.
after_migrate = "iso_compliance.setup.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "iso_compliance.uninstall.before_uninstall"
# after_uninstall = "iso_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "iso_compliance.utils.before_app_install"
# after_app_install = "iso_compliance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "iso_compliance.utils.before_app_uninstall"
# after_app_uninstall = "iso_compliance.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "iso_compliance.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "iso_compliance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------

# A Sales Order row's chosen BOM survives into the Work Order made from it;
# ERPNext's own flow would silently substitute the item's default. And an
# order in SOP-004's review slabs cannot be submitted without its approved
# Techno-Commercial Review (FRM-036). Both logged in EXTERNAL_CHANGES.md.
doc_events = {
	"Work Order": {
		"before_insert": "iso_compliance.overrides.work_order.apply_sales_order_bom",
	},
	"Sales Order": {
		"before_submit": "iso_compliance.overrides.sales_order.enforce_techno_commercial_review",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"iso_compliance.tasks.all"
# 	],
# 	"daily": [
# 		"iso_compliance.tasks.daily"
# 	],
# 	"hourly": [
# 		"iso_compliance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"iso_compliance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"iso_compliance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "iso_compliance.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "iso_compliance.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------

# The make-Work-Order and raw-material-request dialogs display and submit the
# Sales Order row's chosen BOM instead of the item default. The wrapper calls
# the core function first; only the BOM values are corrected.
override_whitelisted_methods = {
	"erpnext.selling.doctype.sales_order.sales_order.get_work_order_items": "iso_compliance.overrides.sales_order.get_work_order_items"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "iso_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["iso_compliance.utils.before_request"]
# after_request = ["iso_compliance.utils.after_request"]

# Job Events
# ----------
# before_job = ["iso_compliance.utils.before_job"]
# after_job = ["iso_compliance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"iso_compliance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# External Changes Register

Every change this app makes to a DocType **outside** `iso_compliance` is recorded here
before it is built. That includes Custom Fields, Property Setters, Client Scripts,
Workflows and permission changes applied to `frappe`, `erpnext`, `hrms`,
`india_compliance`, `crm`, `wiki` or `hatim_carbon` DocTypes.

Rules for this file:

1. Nothing is added to any external DocType until the entry below is approved by the
   developer.
2. Every entry names the exact target DocType, fieldname, fieldtype and the reason.
3. Anything listed here ships as a **fixture**, so installing the app on production
   reproduces it exactly and reversibly.
4. Core ERPNext behaviour is not modified. Additive Custom Fields only — no changes to
   existing field definitions, no monkeypatching, no overridden core methods.

## Status: no external changes made

No Custom Fields, Property Setters or other modifications have been applied to any
DocType outside this app.

## Proposed — awaiting approval

_(none yet)_

## Approved and applied

| Date | Target DocType | Field / Change | Type | Reason | Fixture |
| ---- | -------------- | -------------- | ---- | ------ | ------- |
| —    | —              | —              | —    | —      | —       |

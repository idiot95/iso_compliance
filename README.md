# ISO Compliance

Document control, revision history and QMS records for ISO 9001, built as a native
Frappe v16 app.

## What this closes

An ISO 9001 SQA assessment raised a Major Non-Conformity against document control:

> All working processes are available in the ERP Cloud and document control is managed
> through the cloud system only. However, there is no specific evidence of documents,
> procedures, and records being reviewed and approved. Although the latest revision date
> is available in the ERP, there is no revision history maintained.

Two gaps:

1. **No evidence of review/approval.** Closed by durable, role-gated, timestamped
   Prepared / Reviewed / Approved stamps written by workflow transitions — not by
   framework metadata, which is mutable and therefore not evidentiary.
2. **No revision history.** Closed by immutable revision records that render as a
   Change History sheet in the assessor's specified format.

## Design constraints

- **Additive only.** Core ERPNext behaviour is not modified. Anything this app adds to a
  DocType outside `iso_compliance` is recorded in [EXTERNAL_CHANGES.md](EXTERNAL_CHANGES.md)
  and approved before it is built.
- **ERPNext Quality Management is canonical.** `Non Conformance`, `Quality Action`,
  `Quality Review` and `Quality Meeting` already hold live data on the target site. This
  app links to them; it does not replace them.
- **Explicit ordering everywhere.** Frappe v16 defaults list ordering to `creation`. No
  audit-trail or revision query relies on implicit ordering.
- **Config ships as fixtures, seed data ships as idempotent patches.** Installing the app
  on production reproduces the configuration without manual setup.

## Development

The app is developed against a Docker clone of production and bind-mounted into the
bench. From `frappe_docker/`:

```bash
./hcc.sh exec backend bench --site frontend migrate
./hcc.sh exec backend bench --site frontend console
```

After any `--force-recreate` or image rebuild, restore the editable install:

```bash
./hcc.sh exec backend \
  /home/frappe/frappe-bench/env/bin/pip install -e /home/frappe/frappe-bench/apps/iso_compliance
```

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench --site $SITE install-app iso_compliance
```

## Deployment

Production runs on Frappe Cloud, which installs custom apps from a git repository. The
promotion path is deliberate and gated: build on the clone → test on the clone → tag a
release → install or upgrade on production as an explicit step. Nothing in this repo
mutates production automatically.

## License

MIT

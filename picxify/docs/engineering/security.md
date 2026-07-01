# Security

Defaults (SETUP.md §17):

- Dashboards are private by default; share links off until published; slugs unguessable.
- Raw files are never public; signed URLs only.
- Every resource scoped by `workspace_id`; membership verified on every query.
- Access-sensitive actions logged in `audit_events`.
- AI receives compact profiles/stats/samples/facts — not raw datasets.
- Validate MIME type/extension and size before upload; never execute uploaded files;
  reject macro-enabled Office formats initially.
- Customer data is not used for model training.

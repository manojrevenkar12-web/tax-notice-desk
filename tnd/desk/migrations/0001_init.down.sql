drop function if exists firm_metrics, deadline_metrics, correction_metrics, route_taxno, route_document;
drop table if exists outbox, audit_log, layout_memory, corrections, drafts, deadlines, notices, documents, history,
  onfile, filed_returns, clients, people, firms cascade;
drop function if exists forbid_change, frozen_after_confirm, released_is_final;

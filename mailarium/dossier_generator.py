"""Evidence collection report generator for general email archives."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from .db_schema import _sql_in_placeholders
from .formatting import format_date, format_file_size, strip_html_tags, write_html_or_pdf

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .network_analysis import CommunicationNetwork

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

GENERAL_CATEGORY_GLOSSARY: dict[str, str] = {
    "fact": "Source-grounded information that can be checked against the underlying record",
    "decision": "A choice or conclusion recorded in the archive",
    "action_item": "A concrete task or follow-up recorded in the archive",
    "commitment": "A promise, representation, or agreed next step",
    "contradiction": "Material tension between one record and another that requires source-anchored reconciliation",
    "chronology": "Timeline anchor, sequencing conflict, or dated event linkage",
    "provenance": "Source-origin or custody detail needed to confirm where a record came from and how it was handled",
    "quote_repair": "Replacement or repair of a previously unstable quote so later analysis stays source-accurate",
    "omission": "Meaningful missing follow-through, reply, or process step that the record makes visible",
    "risk": "A source-grounded concern or uncertainty that may affect an outcome",
    "requirement": "A constraint, obligation, or acceptance condition recorded in the archive",
    "general": "Other relevant material not fitting a more specific category",
}


class DossierGenerator:
    """Generate evidence collections combining records, provenance, and analysis."""

    def __init__(
        self,
        email_db: EmailDatabase,
        network: CommunicationNetwork | None = None,
    ) -> None:
        """Bind archive and retrieval services used to assemble evidence dossiers."""
        self._db = email_db
        self._network = network
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    def preview(
        self,
        min_relevance: int | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Preview dossier contents without generating HTML.

        Token-efficient check: returns counts and summary only.
        """
        evidence = self._db.evidence_timeline(category=category, min_relevance=min_relevance)

        email_uids = list({item["email_uid"] for item in evidence if item.get("email_uid")})
        categories = list({item["category"] for item in evidence})

        date_range = {}
        if evidence:
            dates = [e["date"] for e in evidence if e.get("date")]
            if dates:
                date_range = {"earliest": min(dates), "latest": max(dates)}

        return {
            "evidence_count": len(evidence),
            "email_count": len(email_uids),
            "categories": sorted(categories),
            "category_count": len(categories),
            "date_range": date_range,
            "verified_count": sum(1 for e in evidence if e.get("verified")),
        }

    def generate(
        self,
        title: str = "Evidence Collection",
        collection_reference: str = "",
        custodian: str = "",
        prepared_by: str = "",
        min_relevance: int | None = None,
        category: str | None = None,
        include_relationships: bool = True,
        include_custody: bool = True,
        persons_of_interest: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete evidence collection as HTML.

        Returns:
            {"html": str, "evidence_count": int, "email_count": int,
             "dossier_hash": str, "generated_at": str}
        """
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        enriched_items = self._enrich_evidence_items(category, min_relevance)
        source_emails, uid_to_appendix = self._collect_source_emails(enriched_items)

        for item in enriched_items:
            item["appendix_ref"] = uid_to_appendix.get(item.get("email_uid", ""), "")

        relationship_data = self._gather_relationships(
            enriched_items,
            include_relationships,
            persons_of_interest,
        )
        custody_events = self._db.get_custody_chain(limit=500) if include_custody else []
        glossary = GENERAL_CATEGORY_GLOSSARY
        stats = self._compute_summary_stats(enriched_items, source_emails, glossary)
        scope = self._build_scope_data(category, min_relevance)

        template_vars = {
            **stats,
            **scope,
            "title": title,
            "collection_reference": collection_reference,
            "custodian": custodian,
            "prepared_by": prepared_by,
            "generated_at": generated_at,
            "evidence_count": len(enriched_items),
            "email_count": len(source_emails),
            "evidence_items": enriched_items,
            "source_emails": source_emails,
            "include_relationships": include_relationships and bool(relationship_data),
            "relationship_data": relationship_data,
            "include_custody": include_custody,
            "custody_events": custody_events,
        }

        # Render HTML without embedded hash, then compute sha256 of the final
        # document.  The hash is returned in the API response only - embedding
        # a document's own hash inside itself creates an unverifiable
        # self-referential value.  With this approach, sha256(html) == dossier_hash.
        template_vars["dossier_hash"] = ""
        html = self._render_template(template_vars)
        dossier_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

        return {
            "html": html,
            "evidence_count": len(enriched_items),
            "email_count": len(source_emails),
            "dossier_hash": dossier_hash,
            "generated_at": generated_at,
        }

    # ── Private helpers ───────────────────────────────────────

    def _enrich_evidence_items(
        self,
        category: str | None,
        min_relevance: int | None,
    ) -> list[dict[str, Any]]:
        """Fetch evidence timeline, enrich with full records and display fields."""
        enriched_items = self._db.evidence_timeline(
            category=category,
            min_relevance=min_relevance,
        )

        thread_topics = self._thread_topics(enriched_items)
        for idx, item in enumerate(enriched_items, 1):
            self._enrich_evidence_item(item, idx, thread_topics)

        return enriched_items

    def _thread_topics(self, items: list[dict[str, Any]]) -> dict[str, str]:
        """Map source message UIDs to their thread topics."""
        uids = list({item["email_uid"] for item in items if item.get("email_uid")})
        if not uids:
            return {}
        placeholders = _sql_in_placeholders(uids)
        rows = self._db.conn.execute(
            f"SELECT uid, thread_topic FROM emails WHERE uid IN ({placeholders})",  # nosec B608
            uids,
        ).fetchall()
        return {row["uid"]: row["thread_topic"] or "" for row in rows}

    @staticmethod
    def _enrich_evidence_item(item: dict[str, Any], index: int, topics: dict[str, str]) -> None:
        """Enrich evidence item in the normalized form consumed by dossier assembly."""
        verified = bool(item.get("verified"))
        relevance = int(item.get("relevance") or 0)
        updated = item.get("updated_at") or ""
        created = item.get("created_at") or ""
        notes = item.get("notes") or ""
        item.update(
            {
                "evidence_number": f"E-{index}",
                "date_formatted": format_date(item.get("date")),
                "created_at_formatted": format_date(item.get("created_at")),
                "thread_topic": topics.get(item.get("email_uid"), ""),
                "notes": notes if notes != "None" else "",
                "has_notes": bool(notes and notes != "None"),
                "verified_text": "Verified" if verified else "Unverified",
                "verified_class": "badge-verified" if verified else "badge-unverified",
                "relevance_stars": "\u2605" * relevance + "\u2606" * (5 - relevance),
                "updated_at_formatted": format_date(updated) if updated else "",
                "has_updated": bool(updated and updated != created),
                "recipients": item.get("recipients") or "",
            }
        )

    def _collect_source_emails(
        self,
        enriched_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Deduplicate UIDs, fetch full emails, number appendices, attach quotes."""
        email_uids = list({item.get("email_uid") for item in enriched_items if item.get("email_uid")})
        uid_to_full = self._db.get_emails_full_batch(sorted(email_uids))
        source_emails = [self._source_email(full) for uid in sorted(email_uids) if (full := uid_to_full.get(uid))]
        uid_to_appendix = self._number_appendices(source_emails, enriched_items)
        self._enrich_source_emails(source_emails, uid_to_full, self._email_quotes(enriched_items))
        return source_emails, uid_to_appendix

    @staticmethod
    def _source_email(full: dict[str, Any]) -> dict[str, Any]:
        """Resolve the source email payload referenced by an evidence item."""
        raw_date, raw_sha = full.get("date", ""), full.get("content_sha256", "")
        return {
            "uid": full["uid"],
            "sender_name": full.get("sender_name", ""),
            "sender_email": full.get("sender_email", ""),
            "date": raw_date,
            "date_formatted": format_date(raw_date),
            "subject": full.get("subject", ""),
            "body_text": strip_html_tags(full.get("body_text")),
            "content_sha256": raw_sha,
            "content_sha256_display": raw_sha or "(not available)",
            "to": ", ".join(full.get("to", [])),
            "cc": ", ".join(full.get("cc", [])),
            "bcc": ", ".join(full.get("bcc", [])),
            "folder": full.get("folder", ""),
        }

    @staticmethod
    def _number_appendices(emails: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, str]:
        """Number appendices in the normalized form consumed by dossier assembly."""
        mapping: dict[str, str] = {}
        for index, email in enumerate(emails, 1):
            appendix = f"A-{index}"
            email["appendix_number"], mapping[email["uid"]] = appendix, appendix
            email["evidence_refs_str"] = ", ".join(
                item["evidence_number"] for item in items if item.get("email_uid") == email["uid"]
            )
        return mapping

    @staticmethod
    def _email_quotes(items: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
        """Group cited quote snippets by source email UID."""
        quotes: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in items:
            if (uid := item.get("email_uid")) and (quote := item.get("key_quote")):
                quotes[uid].append(
                    {
                        "quote": str(quote),
                        "evidence_number": item.get("evidence_number", ""),
                        "category": item.get("category", ""),
                    }
                )
        return quotes

    @staticmethod
    def _enrich_source_emails(
        emails: list[dict[str, Any]], full_by_uid: dict[str, dict[str, Any]], quotes: dict[str, list[dict[str, str]]]
    ) -> None:
        """Enrich source emails in the normalized form consumed by dossier assembly."""
        for email in emails:
            attachments = full_by_uid.get(email["uid"], {}).get("attachments", [])
            email.update(
                {
                    "evidence_quotes": quotes.get(email["uid"], []),
                    "attachment_count": str(len(attachments)),
                    "attachment_list": [
                        {
                            "name": item.get("name", "unnamed"),
                            "mime_type": item.get("mime_type", ""),
                            "size_display": format_file_size(item.get("size")),
                        }
                        for item in attachments
                    ],
                    "has_attachments": bool(attachments),
                }
            )

    def _gather_relationships(
        self,
        enriched_items: list[dict[str, Any]],
        include: bool,
        persons_of_interest: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Build relationship profiles for persons of interest (max 10)."""
        if not include or not self._network:
            return []
        targets = [p for p in (persons_of_interest or []) if p]
        if not targets:
            targets = list({item.get("sender_email") for item in enriched_items if item.get("sender_email")})
        if not targets:
            return []
        return [self._network.relationship_summary(addr) for addr in sorted(targets)[:10]]

    @staticmethod
    def _compute_summary_stats(
        enriched_items: list[dict[str, Any]],
        source_emails: list[dict[str, Any]],
        glossary: dict[str, str],
    ) -> dict[str, Any]:
        """Compute category counts, date range, glossary, verification data, and evidence index."""
        categories, category_breakdown, glossary_items = DossierGenerator._summary_categories(enriched_items, glossary)
        dates = DossierGenerator._summary_dates(enriched_items)
        verified_count, unverified_count, all_verified = DossierGenerator._summary_verification(enriched_items)
        evidence_index = DossierGenerator._summary_evidence_index(enriched_items)

        return {
            **DossierGenerator._category_stats(categories, category_breakdown, glossary_items),
            **DossierGenerator._date_stats(dates),
            **DossierGenerator._verification_stats(enriched_items, verified_count, unverified_count, all_verified),
            "unique_sender_count": len({item.get("sender_email") for item in enriched_items if item.get("sender_email")}),
            "evidence_index": evidence_index,
            "has_evidence_index": bool(evidence_index),
        }

    @staticmethod
    def _summary_categories(
        items: list[dict[str, Any]],
        glossary: dict[str, str],
    ) -> tuple[set[Any], list[dict[str, str]], list[dict[str, str]]]:
        """Aggregate evidence counts by category for the dossier summary."""
        categories = {item.get("category") for item in items if item.get("category")}
        counts = Counter(item.get("category") for item in items if item.get("category"))
        breakdown = [
            {"category": category, "count": str(count)} for category, count in sorted(counts.items(), key=lambda pair: -pair[1])
        ]
        glossary = [
            {"category": category, "definition": glossary[category]} for category in sorted(categories) if category in glossary
        ]
        return categories, breakdown, glossary

    @staticmethod
    def _summary_dates(items: list[dict[str, Any]]) -> list[str]:
        """Compute the dossier date range from source and evidence timestamps."""
        return [item["date"] for item in items if isinstance(item.get("date"), str) and item["date"]]

    @staticmethod
    def _summary_verification(items: list[dict[str, Any]]) -> tuple[int, int, bool]:
        """Aggregate verified and unverified evidence counts."""
        verified = sum(1 for item in items if item.get("verified"))
        unverified = len(items) - verified
        return verified, unverified, bool(items) and unverified == 0

    @staticmethod
    def _summary_evidence_index(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create compact index entries for ordered evidence items."""
        return [DossierGenerator._evidence_index_entry(item) for item in items]

    @staticmethod
    def _category_stats(categories: set[Any], breakdown: list[dict[str, str]], glossary: list[dict[str, str]]) -> dict[str, Any]:
        """Count evidence items per normalized category."""
        dominant = breakdown[0] if breakdown else {"category": "", "count": "0"}
        return {
            "category_count": len(categories),
            "dominant_category": dominant["category"],
            "dominant_count": dominant["count"],
            "category_breakdown": breakdown,
            "glossary_items": glossary,
            "has_glossary": bool(glossary),
        }

    @staticmethod
    def _date_stats(dates: list[str]) -> dict[str, str]:
        """Return the earliest and latest valid dates across evidence items."""
        if not dates:
            return {"date_earliest": "", "date_latest": ""}
        return {"date_earliest": min(dates)[:10], "date_latest": max(dates)[:10]}

    @staticmethod
    def _verification_stats(items: list[dict[str, Any]], verified: int, unverified: int, all_verified: bool) -> dict[str, Any]:
        """Count evidence items by verification state."""
        return {
            "verified_count": verified,
            "has_evidence": bool(items),
            "all_verified": all_verified,
            "unverified_count": unverified,
            "verification_banner_class": "banner-ok" if all_verified else "banner-warn",
        }

    @staticmethod
    def _evidence_index_entry(item: dict[str, Any]) -> dict[str, Any]:
        """Create one summary index row linking evidence number and source."""
        raw_date = item.get("date") or ""
        sender = item.get("sender_name") or item.get("sender_email") or ""
        summary = item.get("summary") or ""
        relevance = int(item.get("relevance") or 0)
        return {
            "evidence_number": item.get("evidence_number", ""),
            "category": item.get("category", ""),
            "date_short": raw_date[:10] if raw_date else "",
            "sender_short": f"{sender[:27]}..." if len(sender) > 30 else sender,
            "summary_short": f"{summary[:80]}..." if len(summary) > 80 else summary,
            "relevance": item.get("relevance", ""),
            "relevance_stars": "\u2605" * relevance + "\u2606" * (5 - relevance),
        }

    def _build_scope_data(
        self,
        category: str | None,
        min_relevance: int | None,
    ) -> dict[str, Any]:
        """Compute scope filter text and archive totals."""
        scope_parts = []
        if category:
            scope_parts.append(f"Category: {category}")
        if min_relevance:
            scope_parts.append(f"Minimum relevance: {min_relevance}/5")
        scope_filter_text = (
            "Filters applied: " + ", ".join(scope_parts) + "."
            if scope_parts
            else "No filters applied \u2014 all evidence items included."
        )
        archive_row = self._db.conn.execute(
            "SELECT COUNT(*) as total, MIN(date) as earliest, MAX(date) as latest FROM emails"
        ).fetchone()
        return {
            "scope_filter_text": scope_filter_text,
            "archive_total": archive_row["total"] if archive_row else 0,
            "archive_earliest": (archive_row["earliest"] or "")[:10] if archive_row else "",
            "archive_latest": (archive_row["latest"] or "")[:10] if archive_row else "",
        }

    def generate_file(
        self,
        output_path: str,
        fmt: str = "html",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate and write dossier to a file.

        Returns:
            {"output_path": str, "format": str, "evidence_count": int, "dossier_hash": str}
        """
        result = self.generate(**kwargs)
        result_meta = write_html_or_pdf(result["html"], output_path, fmt)
        result_meta.update(
            evidence_count=result["evidence_count"],
            email_count=result["email_count"],
            dossier_hash=result["dossier_hash"],
        )
        return result_meta

    def _render_template(self, variables: dict[str, Any]) -> str:
        """Render the dossier HTML template with Jinja2."""
        template = self._env.get_template("dossier.html")
        return template.render(**variables)

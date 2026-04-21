"""Proof dossier generator for legal evidence export."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from .formatting import format_date, format_file_size, strip_html_tags, write_html_or_pdf

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .network_analysis import CommunicationNetwork

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

CATEGORY_GLOSSARY: dict[str, str] = {
    "bossing": "Intimidation, power abuse, or unreasonable demands by a superior",
    "harassment": "Hostile behavior, bullying, or unwanted conduct targeting an individual",
    "discrimination": "Unequal treatment based on protected characteristics (age, gender, race, etc.)",
    "retaliation": "Adverse action taken in response to reporting, complaining, or whistleblowing",
    "hostile_environment": "Pattern of conduct creating a toxic or intimidating workplace atmosphere",
    "micromanagement": "Excessive control, undermining autonomy, or constant surveillance of work",
    "exclusion": "Deliberate isolation from meetings, decisions, communications, or social activities",
    "gaslighting": "Denying facts, rewriting history, or questioning competence to undermine confidence",
    "workload": "Unreasonable assignments, impossible deadlines, or deliberate work overload",
    "general": "Other relevant evidence not fitting a specific category",
}


class DossierGenerator:
    """Generate proof dossiers combining evidence, emails, and analysis."""

    def __init__(
        self,
        email_db: EmailDatabase,
        network: CommunicationNetwork | None = None,
    ) -> None:
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
        title: str = "Proof Dossier",
        case_reference: str = "",
        custodian: str = "",
        prepared_by: str = "",
        min_relevance: int | None = None,
        category: str | None = None,
        include_relationships: bool = True,
        include_custody: bool = True,
        persons_of_interest: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete proof dossier as HTML.

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
        stats = self._compute_summary_stats(enriched_items, source_emails)
        scope = self._build_scope_data(category, min_relevance)

        template_vars = {
            **stats,
            **scope,
            "title": title,
            "case_reference": case_reference,
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
        # document.  The hash is returned in the API response only — embedding
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

        # Batch-fetch thread topics for all referenced emails (1 query)
        evidence_uids = list({item["email_uid"] for item in enriched_items if item.get("email_uid")})
        thread_topics: dict[str, str] = {}
        if evidence_uids:
            ph = ",".join("?" * len(evidence_uids))
            rows = self._db.conn.execute(
                f"SELECT uid, thread_topic FROM emails WHERE uid IN ({ph})",  # nosec B608
                evidence_uids,
            ).fetchall()
            thread_topics = {r["uid"]: r["thread_topic"] or "" for r in rows}

        for idx, item in enumerate(enriched_items, 1):
            item["evidence_number"] = f"E-{idx}"
            item["date_formatted"] = format_date(item.get("date"))
            item["created_at_formatted"] = format_date(item.get("created_at"))
            uid = item.get("email_uid")
            item["thread_topic"] = thread_topics.get(uid, "") if uid else ""
            # Notes cleanup
            raw_notes = item.get("notes") or ""
            item["notes"] = raw_notes if raw_notes and raw_notes != "None" else ""
            item["has_notes"] = bool(item["notes"])
            # Verified badge
            is_verified = bool(item.get("verified"))
            item["verified_text"] = "Verified" if is_verified else "Unverified"
            item["verified_class"] = "badge-verified" if is_verified else "badge-unverified"
            # Star-glyph relevance
            rel = int(item.get("relevance") or 0)
            item["relevance_stars"] = "\u2605" * rel + "\u2606" * (5 - rel)
            # Updated-at display
            updated_raw = item.get("updated_at") or ""
            created_raw = item.get("created_at") or ""
            item["updated_at_formatted"] = format_date(updated_raw) if updated_raw else ""
            item["has_updated"] = bool(updated_raw and updated_raw != created_raw)
            item["recipients"] = item.get("recipients") or ""

        return enriched_items

    def _collect_source_emails(
        self,
        enriched_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Deduplicate UIDs, fetch full emails, number appendices, attach quotes."""
        email_uids = list({item.get("email_uid") for item in enriched_items if item.get("email_uid")})
        uid_to_full = self._db.get_emails_full_batch(sorted(email_uids))
        source_emails: list[dict[str, Any]] = []
        for uid in sorted(email_uids):
            full = uid_to_full.get(uid)
            if full:
                raw_date = full.get("date", "")
                raw_sha = full.get("content_sha256", "")
                source_emails.append(
                    {
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
                )

        # Number appendices and cross-reference with evidence
        uid_to_appendix: dict[str, str] = {}
        for idx, email in enumerate(source_emails, 1):
            email["appendix_number"] = f"A-{idx}"
            uid_to_appendix[email["uid"]] = f"A-{idx}"
            refs = [it["evidence_number"] for it in enriched_items if it.get("email_uid") == email["uid"]]
            email["evidence_refs_str"] = ", ".join(refs)

        # Build quote map and enrich with quotes + attachment data
        email_quotes: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in enriched_items:
            uid = item.get("email_uid")
            quote = item.get("key_quote")
            if uid and quote:
                email_quotes[uid].append(
                    {
                        "quote": str(quote),
                        "evidence_number": item.get("evidence_number", ""),
                        "category": item.get("category", ""),
                    }
                )

        for email in source_emails:
            uid = email["uid"]
            email["evidence_quotes"] = email_quotes.get(uid, [])
            full = uid_to_full.get(uid, {})
            attachments = full.get("attachments", [])
            email["attachment_count"] = str(len(attachments))
            email["attachment_list"] = [
                {
                    "name": a.get("name", "unnamed"),
                    "mime_type": a.get("mime_type", ""),
                    "size_display": format_file_size(a.get("size")),
                }
                for a in attachments
            ]
            email["has_attachments"] = bool(attachments)

        return source_emails, uid_to_appendix

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

    def _compute_summary_stats(
        self,
        enriched_items: list[dict[str, Any]],
        source_emails: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute category counts, date range, glossary, verification data, and evidence index."""
        categories = {item.get("category") for item in enriched_items if item.get("category")}
        verified_count = sum(1 for item in enriched_items if item.get("verified"))

        category_counts = Counter(item.get("category") for item in enriched_items if item.get("category"))
        category_breakdown = [{"category": c, "count": str(n)} for c, n in sorted(category_counts.items(), key=lambda x: -x[1])]
        dates = [item.get("date") for item in enriched_items if item.get("date") and isinstance(item.get("date"), str)]

        glossary_items = [
            {"category": cat, "definition": CATEGORY_GLOSSARY[cat]} for cat in sorted(categories) if cat in CATEGORY_GLOSSARY
        ]

        total_evidence = len(enriched_items)
        unverified_count = total_evidence - verified_count
        all_verified = total_evidence > 0 and unverified_count == 0

        # Evidence index table
        evidence_index = []
        for item in enriched_items:
            raw_date = item.get("date") or ""
            sender_short = item.get("sender_name") or item.get("sender_email") or ""
            if len(sender_short) > 30:
                sender_short = sender_short[:27] + "..."
            summary_raw = item.get("summary") or ""
            idx_rel = int(item.get("relevance") or 0)
            evidence_index.append(
                {
                    "evidence_number": item.get("evidence_number", ""),
                    "category": item.get("category", ""),
                    "date_short": raw_date[:10] if raw_date else "",
                    "sender_short": sender_short,
                    "summary_short": summary_raw[:80] + "..." if len(summary_raw) > 80 else summary_raw,
                    "relevance": item.get("relevance", ""),
                    "relevance_stars": "\u2605" * idx_rel + "\u2606" * (5 - idx_rel),
                }
            )

        return {
            "verified_count": verified_count,
            "category_count": len(categories),
            "date_earliest": (min(dates) or "")[:10] if dates else "",
            "date_latest": (max(dates) or "")[:10] if dates else "",
            "unique_sender_count": len({item.get("sender_email") for item in enriched_items if item.get("sender_email")}),
            "dominant_category": category_breakdown[0]["category"] if category_breakdown else "",
            "dominant_count": category_breakdown[0]["count"] if category_breakdown else "0",
            "category_breakdown": category_breakdown,
            "glossary_items": glossary_items,
            "has_evidence": bool(enriched_items),
            "has_glossary": bool(glossary_items),
            "all_verified": all_verified,
            "unverified_count": unverified_count,
            "verification_banner_class": "banner-ok" if all_verified else "banner-warn",
            "evidence_index": evidence_index,
            "has_evidence_index": bool(evidence_index),
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

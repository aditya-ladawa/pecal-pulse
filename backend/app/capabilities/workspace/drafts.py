"""Evidence-backed email copy. No recipient lookup, sending, or invented promises."""
from collections import defaultdict
from ...contracts.sales_v2 import EmailDraft


def build_email_draft(detail: dict, language: str = "en") -> EmailDraft:
    reasons = [r for r in (detail.get("action") or {}).get("reasons", []) if r["status"] != "suppressed"]
    if not reasons:
        raise ValueError("No current outreach reason for this account; record a manual next step instead")
    labels = {p["group_id"]: p["group_label"] for p in detail["portfolio"]}
    batches = defaultdict(lambda: {"ids": set(), "dates": [], "estimated": False})
    for r in reasons:
        if r["type"] != "upcoming":
            continue
        # This is the shared action ID schema used by the customer preparation UI.
        group = r["id"].split(":")[-3]
        batch = batches[group]
        batch["ids"].update(r["instrument_ids"])
        batch["dates"].extend([r["window_start"], r["window_end"]])
        batch["estimated"] |= any("inferred" in u for u in r.get("unknowns", []))
    de = language == "de"
    lines = ["Guten Tag," if de else "Hello,", ""]
    ref = detail["metadata"]["reference_date"]
    if batches:
        lines.append(
            f"Unsere Kalibrierunterlagen mit Stand {ref} enthalten folgende Termine, die wir gerne mit Ihnen abstimmen möchten:"
            if de else f"Our calibration records, referenced to {ref}, contain the following dates we would like to confirm with you:")
        for group, b in sorted(batches.items(), key=lambda item: -len(item[1]["ids"]))[:5]:
            dates = sorted(d for d in b["dates"] if d)
            timing = " – ".join(dict.fromkeys((dates[0], dates[-1]))) if dates else ("Termin offen" if de else "timing to confirm")
            label = labels.get(group) or group.removeprefix("GRP-").replace("_", " ")
            basis = ("geschätztes Zeitfenster" if de else "estimated window") if b["estimated"] else ("hinterlegter Termin" if de else "recorded date")
            lines.append(f"• {len(b['ids'])} {label} — {timing} ({basis})")
        if len(batches) > 5:
            lines.append("Weitere Gerätegruppen können wir gemeinsam prüfen." if de else "We can review the additional equipment groups together.")
        lines.extend(["", "Können Sie bestätigen, ob diese Arbeiten bereits erledigt sind oder ob sich die Termine geändert haben? Falls eine Kalibrierung geplant ist: Welche Geräte und welcher Zeitraum wären für Sie passend?"
                      if de else "Could you confirm whether this work has already been completed or the timing has changed? If calibration is planned, which equipment and timing would suit you?"])
    if any(r["type"] == "inactivity" for r in reasons):
        lines.extend(["", "Wir möchten außerdem kurz nachfragen, ob sich Ihr Kalibrierbedarf oder Ihre Abläufe geändert haben. Können wir Sie bei einer bevorstehenden Geräteprüfung unterstützen?"
                      if de else "We would also like to check whether your calibration needs or process have changed. Is there an upcoming equipment check we can help you prepare for?"])
    discovery = [r for r in reasons if r["type"] == "discovery"]
    peer_ids = {ref for r in discovery for ref in r["evidence_refs"]}
    peers = [p for p in detail["peer_opportunities"] if f"peer:{p['industry_id']}:{p['group_id']}" in peer_ids][:2]
    if peers:
        categories = ", ".join(p["group_label"] for p in peers)
        lines.extend(["", f"Nutzen Sie in Ihrem Betrieb auch {categories}? Falls ja, wäre eine Abstimmung zu deren Kalibrierung für Sie hilfreich?"
                      if de else f"Do you also use {categories} on site? If so, would a discussion about calibration for that equipment be useful?"])
    lines.extend(["", "Vielen Dank und freundliche Grüße\nPerschmann Calibration" if de else "Thank you and kind regards,\nPerschmann Calibration"])
    checks = detail["workflow"]["checks"]
    notes = [f"Historical evidence through {ref}; verify current timing before sending.", "Add a verified recipient and sender; this draft has not been sent."]
    if checks["quotation_order"] == "in_progress":
        notes.append("A quote/order is already being handled. Coordinate with its owner before sending.")
    elif checks["quotation_order"] == "unknown":
        notes.append("Check whether a quote or order is already being handled.")
    if checks["recent_contact"] == "unknown":
        notes.append("Check recent team contact to avoid duplicate outreach.")
    return EmailDraft(subject="Ihre nächste Kalibrierung – kurze Abstimmung" if de else "Planning your next calibration — a quick check-in",
        body="\n".join(lines), language=language, snapshot_id=detail["metadata"]["snapshot_id"], reference_date=ref,
        reason_ids=[r["id"] for r in reasons][:100], review_notes=notes)

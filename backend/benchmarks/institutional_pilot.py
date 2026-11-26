"""Small read-only diagnostic of the actual institutional website collector.

No database, authentication, messaging, enrichment of personal data or third-party
search API. Only the five public, previously researched corporate contact pages.
An observed mailbox is not a delivery test or proof of commercial interest.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import sleep
from urllib.parse import urlsplit

from app.collectors.site_contacts import discover, _role_box, DiscoveryUnavailable, network_reason
from app.services.cnpj import is_valid_cnpj


def probe(items, *, collect=discover, wait=sleep):
    if len(items) != 5 or len({x["cnpj"] for x in items}) != 5:
        raise ValueError("Expected exactly five distinct pilot companies.")
    for row in items:
        site = urlsplit(row["website"])
        email = row["expected_email"]
        local, _, domain = email.partition("@")
        if (not is_valid_cnpj(row["cnpj"]) or site.scheme != "https"
                or not site.hostname or site.username or site.password or site.port not in (443, None)
                or not _role_box(local) or domain != site.hostname.lower().removeprefix("www.")):
            raise ValueError("Unexpected pilot input.")
    report = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "database_written": False, "messages_sent": False, "items": []}
    for row in items:
        if report["items"]:
            wait(2)
        result = {"name": row["name"], "cnpj": row["cnpj"], "site": row["website"],
                  "pages_read": 0, "status": "unavailable", "expected_email_found": False}
        try:
            batch = collect(row["website"], max_pages=2)
            result["pages_read"] = len(batch["pages_read"])
            result["reason_codes"] = batch.get("reason_codes", [])
            result["status"] = "not_found" if batch["pages_read"] else "unavailable"
            match = next((x for x in batch["emails"] if x["email"] == row["expected_email"]), None)
            if match and match["source_url"] in batch["pages_read"]:
                result.update(status="published", expected_email_found=True,
                              email=row["expected_email"], source_url=match["source_url"])
        except DiscoveryUnavailable as exc:
            result["reason_codes"] = [exc.code]
        except Exception as exc:
            result["reason_codes"] = [network_reason(exc)]
            result["error_type"] = type(exc).__name__
        report["items"].append(result)
    report["companies_processed"] = len(report["items"])
    report["sites_read"] = sum(x["pages_read"] > 0 for x in report["items"])
    report["emails_found"] = sum(x["expected_email_found"] for x in report["items"])
    report["all_expected_emails_found"] = report["emails_found"] == len(items)
    report["production_pilot_completed"] = False
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    source = Path(__file__).resolve().with_name("institutional_pilot_manaus.json")
    result = probe(json.loads(source.read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["all_expected_emails_found"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Attach source-bound access findings, separately from professional approval."""
import json
import warnings
from pathlib import Path

from .acquire_http import canonical_url


def enrich_access_notes(root, records):
    path = Path(root)/'data/verification/standards-access.json'
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        findings = {}
        for standard in payload['standards']:
            reason = standard.get('not_retrieved_reason')
            if not isinstance(reason, str) or not reason.strip():
                continue
            for source in standard.get('input_sources', []):
                key = source['source_id'], canonical_url(source['url_as_recorded'])
                findings[key] = (reason, standard.get('checked_at', ''))
        for record in records:
            key = record.get('source_id'), record.get('url')
            if key in findings:
                reason, checked = findings[key]
                record.update(access_note=reason, access_checked_at=checked)
                if 'reason' in record:
                    record['previous_reason'] = record['reason']
                    record['reason'] = reason
    except (ValueError, KeyError, TypeError, OSError) as exc:
        warnings.warn(f'Standard access evidence not applied: {exc}', RuntimeWarning, stacklevel=2)

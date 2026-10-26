"""Fail closed for the user's zero-charge AWS requirement."""
import json
import sys
from datetime import UTC, datetime

plan = json.load(sys.stdin)
if plan.get('accountPlanType') != 'FREE' or plan.get('accountPlanStatus') != 'ACTIVE':
    raise SystemExit('STOP: an ACTIVE FREE account plan was not verified. Do not upgrade or launch resources.')
credits = plan.get('accountPlanRemainingCredits') or {}
if credits.get('unit') != 'USD' or float(credits.get('amount') or 0) < 5:
    raise SystemExit('STOP: at least USD 5 of remaining Free-plan credit must be confirmed before this demo.')
expiry = plan.get('accountPlanExpirationDate')
if not expiry:
    raise SystemExit('STOP: the Free-plan expiration date could not be verified.')
if isinstance(expiry,(int,float)):
    expires = datetime.fromtimestamp(expiry,UTC)
else:
    expires = datetime.fromisoformat(expiry.replace('Z','+00:00'))
if (expires - datetime.now(UTC)).total_seconds() < 86400:
    raise SystemExit('STOP: fewer than 24 hours remain on this Free plan.')
print('ACTIVE FREE plan and remaining credit verified. This script never upgrades the account.')

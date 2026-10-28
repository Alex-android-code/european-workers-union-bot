from dataclasses import dataclass


class Denied(ValueError):
    """Safe error category; callers must not log sensitive exception bodies."""


@dataclass(frozen=True)
class Actor:
    id: str


STATUSES = ('NEW','PRIVACY_COMPLETED','PROFILE_IN_PROGRESS','PROFILE_COMPLETE','MATCHED',
            'INTERESTED','SUBMITTED_TO_PARTNER','PARTNER_REVIEW','ACCEPTED',
            'START_DATE_CONFIRMED','TRAVEL_PLANNED','ON_THE_WAY','ARRIVED','CHECKED_IN',
            'STARTED_WORK','REJECTED','CANCELLED','ON_HOLD')
NEXT = {a: {b} for a, b in zip(STATUSES[:14], STATUSES[1:15])}
NEXT.update({'STARTED_WORK': set(), 'REJECTED': set(), 'CANCELLED': set(), 'ON_HOLD': {'INTERESTED'}})
for state in STATUSES:
    if state not in ('STARTED_WORK','REJECTED','CANCELLED'):
        NEXT.setdefault(state, set()).update({'CANCELLED', 'ON_HOLD'})
for state in ('SUBMITTED_TO_PARTNER','PARTNER_REVIEW','ACCEPTED'):
    NEXT[state].add('REJECTED')
CANDIDATE_ACTIONS = {'NEW','PRIVACY_COMPLETED','PROFILE_IN_PROGRESS','PROFILE_COMPLETE','MATCHED',
                     'INTERESTED','ON_THE_WAY','ARRIVED','CANCELLED'}
PROFILE_FIELDS = {'name','city','profession','desired_location','experience','housing','relocation','availability'}
RIGHTS = {'view','rectify','copy','delete','withdraw','object','restrict'}

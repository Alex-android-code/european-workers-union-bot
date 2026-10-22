// Advisory vacancy matching only. Never use this module for automatic hiring rejection.
// Each offer has its own partner/contract ID, even when the workplace is identical.
const norm = value => String(value ?? '').trim().toLocaleLowerCase();
const terms = value => norm(value).split(/[,;/\n]+/).map(x => x.trim()).filter(Boolean);
const hasTerm = (text, term) => norm(text).includes(norm(term));

export function matchOffer(candidate, offer) {
  if (!offer || offer.active === false) return null;
  const checks = [];
  const skills = terms(offer.required_skills);
  for (const skill of skills) {
    const evidence = [candidate.profession, candidate.experience, candidate.skills].filter(Boolean).join(' ');
    checks.push({ requirement: 'skill: ' + skill, state: !evidence ? 'unknown' : hasTerm(evidence, skill) ? 'met' : 'needs_review' });
  }
  if (offer.location && candidate.current_location) {
    checks.push({ requirement: 'location', state: hasTerm(candidate.current_location, offer.location) ? 'met' : 'needs_review' });
  } else if (offer.location) {
    checks.push({ requirement: 'location', state: 'unknown' });
  }
  if (offer.driving_category) {
    const evidence = candidate.driving;
    checks.push({ requirement: 'driving category ' + offer.driving_category, state: !evidence ? 'unknown' : hasTerm(evidence, offer.driving_category) ? 'met' : 'needs_review' });
  }
  // Documents and work eligibility require human verification; do not infer legality.
  if (offer.work_authorization_required) checks.push({ requirement: 'work authorization (human verification)', state: 'unknown' });
  const met = checks.filter(x => x.state === 'met').length;
  return {
    offer_id: String(offer.id),
    partner_id: String(offer.partner_id ?? ''),
    contract_id: String(offer.contract_id ?? ''),
    workplace_id: String(offer.workplace_id ?? ''),
    status: checks.some(x => x.state !== 'met') ? 'review' : 'potential_match',
    matched_requirements: met,
    total_requirements: checks.length,
    checks,
    human_review_required: true
  };
}

export function recommendOffers(candidate, offers) {
  return offers.map(offer => matchOffer(candidate, offer)).filter(Boolean)
    .sort((a,b) => b.matched_requirements - a.matched_requirements ||
      a.checks.filter(x=>x.state==='needs_review').length - b.checks.filter(x=>x.state==='needs_review').length);
}

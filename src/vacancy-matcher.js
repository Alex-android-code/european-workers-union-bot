// Pure, deterministic vacancy matching. No Telegram token or database required.
// Eligibility is never inferred from nationality or an AI-generated score.
const norm = x => String(x ?? '').trim().toLowerCase();
const words = x => norm(x).split(/[^\\p{L}\\p{N}]+/u).filter(w => w.length >= 3);
const truthy = x => x === true || ['true','yes','tak','так','да','1'].includes(norm(x));
export function matchVacancies(candidate, vacancies, now = new Date()) {
  const profession = words(candidate.profession);
  const location = norm(candidate.current_location);
  const needsHousing = /житл|housing|accommodation|zakwater|жиль/i.test(String(candidate.work_priority ?? ''));
  return vacancies
    .filter(v => v && v.status === 'approved' && v.employer_verified === true && v.approved === true)
    .filter(v => !v.valid_until || (Number.isFinite(Date.parse(v.valid_until)) && Date.parse(v.valid_until + (v.valid_until.length === 10 ? 'T23:59:59Z' : '')) >= now.getTime()))
    .filter(v => !needsHousing || truthy(v.housing_provided))
    .map(v => {
      const jobWords = words([v.profession, v.title, v.description].join(' '));
      const overlap = profession.filter(w => jobWords.includes(w)).length;
      const professionScore = profession.length ? Math.min(60, Math.round(overlap / profession.length * 60)) : 0;
      const place = norm(v.location);
      const locationScore = location && place && (place.includes(location) || location.includes(place)) ? 20 : 0;
      const housingScore = needsHousing && truthy(v.housing_provided) ? 20 : 0;
      return { vacancy: v, score: professionScore + locationScore + housingScore, reasons: [
        ...(overlap ? ['profession_overlap'] : []),
        ...(locationScore ? ['location_overlap'] : []),
        ...(housingScore ? ['housing_available'] : [])
      ], requiresHumanReview: true };
    })
    .sort((a,b) => b.score - a.score || String(a.vacancy.id).localeCompare(String(b.vacancy.id)));
}

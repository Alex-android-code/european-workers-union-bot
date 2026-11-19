import crypto from 'node:crypto';

const TABLE = {
 id: 'ID', status: 'Статус предложения', project: 'Проект / заказчик',
 city: 'Город / местоположение', requirements: 'Кого мы ищем на работу:',
 quantity: 'Количество', jobType: 'Тип работы', pay: 'ЗАРАБОТНАЯ ПЛАТА',
 bonus: 'Премии / доплаты', hours: 'Часы / RBH',
 housing: 'Жильё — ссылка на папку с фото и видео', transport: 'Транспорт'
};
export const SOURCE_ID = '1JOGzOZ7Wv5RYN6VesoHIlp1aUQ3hsYnl';
export function normalizeVacancy(row, index = 0) {
 const get = k => String(row[TABLE[k]] ?? '').trim();
 const sourceId = get('id') || String(index + 1);
 if (!get('project') || !get('city')) return null;
 const status = get('status').toLowerCase();
 return {
  source_id: SOURCE_ID, source_row: sourceId, project: get('project'),
  city: get('city'), requirements: get('requirements'),
  slots: Number.parseInt(get('quantity'), 10) || 0,
  job_type: get('jobType'), pay_raw: get('pay'), bonus_raw: get('bonus'),
  hours_raw: get('hours'), housing_raw: get('housing'),
  transport_raw: get('transport'), source_status: get('status'),
  source_active: status === 'активная', hash: crypto.createHash('sha256')
   .update(JSON.stringify(row)).digest('hex')
 };
}
export async function initVacancies(pool) {
 await pool.query(`CREATE TABLE IF NOT EXISTS ewu_partner_vacancies (
  source_id text NOT NULL, source_row text NOT NULL, project text NOT NULL,
  city text NOT NULL, requirements text NOT NULL DEFAULT '',
  slots integer NOT NULL DEFAULT 0, job_type text NOT NULL DEFAULT '',
  pay_raw text NOT NULL DEFAULT '', bonus_raw text NOT NULL DEFAULT '',
  hours_raw text NOT NULL DEFAULT '', housing_raw text NOT NULL DEFAULT '',
  transport_raw text NOT NULL DEFAULT '', source_status text NOT NULL DEFAULT '',
  source_active boolean NOT NULL DEFAULT false, hash text NOT NULL,
  verified boolean NOT NULL DEFAULT false, publish_allowed boolean NOT NULL DEFAULT false,
  verified_at timestamptz, imported_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(source_id,source_row)
 )`);
}
export async function importVacancies(pool, rows) {
 if (!Array.isArray(rows)) throw new Error('Expected an array of rows');
 let imported = 0, skipped = 0;
 for (let i = 0; i < rows.length; i++) {
  const v = normalizeVacancy(rows[i], i);
  if (!v) { skipped++; continue; }
  await pool.query(`INSERT INTO ewu_partner_vacancies
   (source_id,source_row,project,city,requirements,slots,job_type,pay_raw,bonus_raw,
    hours_raw,housing_raw,transport_raw,source_status,source_active,hash)
   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
   ON CONFLICT(source_id,source_row) DO UPDATE SET
    project=EXCLUDED.project,city=EXCLUDED.city,requirements=EXCLUDED.requirements,
    slots=EXCLUDED.slots,job_type=EXCLUDED.job_type,pay_raw=EXCLUDED.pay_raw,
    bonus_raw=EXCLUDED.bonus_raw,hours_raw=EXCLUDED.hours_raw,
    housing_raw=EXCLUDED.housing_raw,transport_raw=EXCLUDED.transport_raw,
    source_status=EXCLUDED.source_status,source_active=EXCLUDED.source_active,
    hash=EXCLUDED.hash,imported_at=now(),
    verified=CASE WHEN ewu_partner_vacancies.hash=EXCLUDED.hash THEN ewu_partner_vacancies.verified ELSE false END,
    publish_allowed=CASE WHEN ewu_partner_vacancies.hash=EXCLUDED.hash THEN ewu_partner_vacancies.publish_allowed ELSE false END,
    verified_at=CASE WHEN ewu_partner_vacancies.hash=EXCLUDED.hash THEN ewu_partner_vacancies.verified_at ELSE NULL END`,
   [v.source_id,v.source_row,v.project,v.city,v.requirements,v.slots,v.job_type,
    v.pay_raw,v.bonus_raw,v.hours_raw,v.housing_raw,v.transport_raw,
    v.source_status,v.source_active,v.hash]);
  imported++;
 }
 return {imported,skipped};
}
export async function approvedVacancies(pool, limit = 10) {
 const result = await pool.query(`SELECT source_row,project,city,slots,pay_raw,housing_raw,job_type
 FROM ewu_partner_vacancies WHERE source_active=true AND verified=true
 AND publish_allowed=true ORDER BY project LIMIT $1`,[Math.max(1,Math.min(30,limit))]);
 return result.rows;
}
export function rankVacancies(vacancies, preferences = {}) {
 const city = String(preferences.city || '').toLowerCase().trim();
 const housing = Boolean(preferences.housing);
 return vacancies.map(v => {
  const cityFit = city && String(v.city).toLowerCase().includes(city) ? 3 : 0;
  const housingFit = housing && /bezpłat|безкоштов|free|darmow/i.test(v.housing_raw || '') ? 2 : 0;
  return {...v, match_score: cityFit + housingFit};
 }).sort((a,b) => b.match_score - a.match_score);
}

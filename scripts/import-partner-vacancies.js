import { readFile } from 'node:fs/promises';
import pg from 'pg';
import { initVacancies, importVacancies } from '../partner-vacancies.js';
const path = process.argv[2];
if (!path) throw new Error('Usage: node scripts/import-partner-vacancies.js rows.json');
const rows = JSON.parse(await readFile(path,'utf8'));
if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL required');
const pool = new pg.Pool({connectionString:process.env.DATABASE_URL,max:2});
try {
 await initVacancies(pool);
 const result = await importVacancies(pool,rows);
 console.log(JSON.stringify(result));
} finally { await pool.end(); }

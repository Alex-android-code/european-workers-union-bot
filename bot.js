import crypto from 'node:crypto';
import http from 'node:http';
import pg from 'pg';
import { generateText } from 'ai';

const { Pool } = pg;
const TOKEN = String(process.env.TELEGRAM_TOKEN || '');
const DB = String(process.env.DATABASE_URL || '');
const AI_MODEL = String(process.env.AI_MODEL || '');
const AI_ENABLED = Boolean(process.env.EWU_AI_CHAT_ALLOWED === 'true' && process.env.AI_GATEWAY_API_KEY && AI_MODEL);
if (!TOKEN || !DB) throw new Error('Missing TELEGRAM_TOKEN or DATABASE_URL');

const pool = new Pool({ connectionString: DB, max: 5, connectionTimeoutMillis: 5000, query_timeout: 10000 });
const API = 'https://api.telegram.org/bot' + TOKEN + '/';
const PORT = Number(process.env.PORT || 3000);
let offset = 0;
const START_ALLOWED = process.env.EWU_START_ALLOWED === 'true';
const ADMIN_IDS = new Set((process.env.EWU_ADMIN_IDS || '').split(',').map(x=>x.trim()).filter(Boolean));
const GROUP_IDS = new Set((process.env.EWU_GROUP_IDS || '').split(',').map(x=>x.trim()).filter(Boolean));
let lastPollAt = 0;
function safeError(event){ console.error(JSON.stringify({event})); }
function commandOf(text){ return String(text).split(/\s+/)[0].split('@')[0]; }
function groupAuthorized(msg){ return ADMIN_IDS.has(String(msg.from.id)) && GROUP_IDS.has(String(msg.chat.id)); }


const LANGS = {
  '🇺🇦 Українська':'uk','🇵🇱 Polski':'pl','🇷🇺 Русский':'ru',
  '🇬🇧 English':'en','🇩🇪 Deutsch':'de','🇪🇸 Español':'es','🇵🇹 Português':'pt'
};
const L = {
uk:{candidate:'👷 Шукаю роботу',employer:'🏢 Шукаю працівників',legal:'📄 Легалізація і документи',about:'ℹ️ Про EWU',contact:'📞 Зв’язатися з координатором',menu:'Головне меню',welcome:'Вітаю! Я European Workers Union (EWU). Оберіть напрямок:',aboutText:'European Workers Union — платформа, що з’єднує працівників і роботодавців у Польщі та Європі.',contactAsk:'Напишіть ваше питання або ситуацію. Координатор побачить звернення.',saved:'Готово. Дані збережено, координатор EWU зможе продовжити роботу із заявкою.',error:'Технічна помилка. Натисніть /start і спробуйте ще раз.'},
pl:{candidate:'👷 Szukam pracy',employer:'🏢 Szukam pracowników',legal:'📄 Legalizacja i dokumenty',about:'ℹ️ O EWU',contact:'📞 Kontakt z koordynatorem',menu:'Menu główne',welcome:'Witamy w European Workers Union (EWU). Wybierz opcję:',aboutText:'European Workers Union łączy pracowników i pracodawców w Polsce i Europie.',contactAsk:'Napisz pytanie lub opisz sytuację. Koordynator zobaczy zgłoszenie.',saved:'Gotowe. Dane zostały zapisane, koordynator EWU może kontynuować obsługę zgłoszenia.',error:'Błąd techniczny. Naciśnij /start i spróbuj ponownie.'},
ru:{candidate:'👷 Ищу работу',employer:'🏢 Ищу сотрудников',legal:'📄 Легализация и документы',about:'ℹ️ О EWU',contact:'📞 Связаться с координатором',menu:'Главное меню',welcome:'Добро пожаловать в European Workers Union (EWU). Выберите направление:',aboutText:'European Workers Union соединяет работников и работодателей в Польше и Европе.',contactAsk:'Напишите ваш вопрос или опишите ситуацию. Координатор увидит обращение.',saved:'Готово. Данные сохранены, координатор EWU сможет продолжить работу с заявкой.',error:'Техническая ошибка. Нажмите /start и попробуйте ещё раз.'},
en:{candidate:'👷 I’m looking for work',employer:'🏢 I’m looking for workers',legal:'📄 Legalization and documents',about:'ℹ️ About EWU',contact:'📞 Contact coordinator',menu:'Main menu',welcome:'Welcome to European Workers Union (EWU). Choose an option:',aboutText:'European Workers Union connects workers and employers across Poland and Europe.',contactAsk:'Write your question or describe your situation. The coordinator will see it.',saved:'Done. Your data has been saved and an EWU coordinator can continue with your application.',error:'Technical error. Send /start and try again.'},
de:{candidate:'👷 Ich suche Arbeit',employer:'🏢 Ich suche Mitarbeiter',legal:'📄 Legalisierung und Dokumente',about:'ℹ️ Über EWU',contact:'📞 Koordinator kontaktieren',menu:'Hauptmenü',welcome:'Willkommen bei European Workers Union (EWU). Wählen Sie eine Option:',aboutText:'European Workers Union verbindet Arbeitnehmer und Arbeitgeber in Polen und Europa.',contactAsk:'Schreiben Sie Ihre Frage oder beschreiben Sie Ihre Situation.',saved:'Fertig. Ihre Daten wurden gespeichert und ein EWU-Koordinator kann die Anfrage weiterbearbeiten.',error:'Technischer Fehler. Senden Sie /start und versuchen Sie es erneut.'},
es:{candidate:'👷 Busco trabajo',employer:'🏢 Busco trabajadores',legal:'📄 Legalización y documentos',about:'ℹ️ Sobre EWU',contact:'📞 Contactar coordinador',menu:'Menú principal',welcome:'Bienvenido a European Workers Union (EWU). Elige una opción:',aboutText:'European Workers Union conecta trabajadores y empleadores en Polonia y Europa.',contactAsk:'Escribe tu pregunta o describe tu situación.',saved:'Listo. Tus datos se han guardado y un coordinador de EWU puede continuar con tu solicitud.',error:'Error técnico. Envía /start e inténtalo de nuevo.'},
pt:{candidate:'👷 Procuro trabalho',employer:'🏢 Procuro trabalhadores',legal:'📄 Legalização e documentos',about:'ℹ️ Sobre a EWU',contact:'📞 Contactar coordenador',menu:'Menu principal',welcome:'Bem-vindo à European Workers Union (EWU). Escolha uma opção:',aboutText:'A European Workers Union liga trabalhadores e empregadores na Polónia e na Europa.',contactAsk:'Escreva a sua pergunta ou descreva a situação.',saved:'Concluído. Os seus dados foram guardados e um coordenador da EWU pode continuar o pedido.',error:'Erro técnico. Envie /start e tente novamente.'}
};

const flows = {
 candidate:{
  fields:['full_name','phone','current_location','citizenship','profession','experience','documents','desired_pay','work_priority','duration','driving'],
  q:{
   uk:['Як вас звати? Напишіть ім’я та прізвище латиницею, як у документах.','Ваш номер телефону з кодом країни?','Де ви зараз перебуваєте? Країна та місто.','Ваше громадянство?','Яку роботу або професію шукаєте?','Опишіть досвід роботи: скільки років і що вмієте.','Які документи для перебування/роботи маєте зараз?','Яку оплату очікуєте?','Що для вас найважливіше: ставка, стабільність, швидкий вихід, житло чи інше?','На який термін готові працювати?','Чи маєте водійські права? Якщо так — категорії та досвід водіння в Польщі.'],
   pl:['Imię i nazwisko łacińskimi literami, jak w dokumentach?','Numer telefonu z kodem kraju?','Gdzie teraz jesteś? Kraj i miasto.','Obywatelstwo?','Jakiej pracy lub zawodu szukasz?','Opisz doświadczenie: ile lat i co potrafisz.','Jakie dokumenty pobytowe/do pracy masz obecnie?','Jakiego wynagrodzenia oczekujesz?','Co jest najważniejsze: stawka, stabilność, szybki start, mieszkanie czy coś innego?','Na jak długo możesz podjąć pracę?','Czy masz prawo jazdy? Kategorie i doświadczenie w prowadzeniu w Polsce.'],
   ru:['Имя и фамилия латиницей, как в документах?','Номер телефона с кодом страны?','Где вы сейчас? Страна и город.','Гражданство?','Какую работу или профессию ищете?','Опишите опыт: сколько лет и что умеете.','Какие документы для пребывания/работы у вас сейчас есть?','Какую оплату ожидаете?','Что важнее всего: ставка, стабильность, быстрый выход, жильё или другое?','На какой срок готовы работать?','Есть водительские права? Категории и опыт вождения в Польше.'],
   en:['Your full name in Latin letters, as in your documents?','Phone number with country code?','Where are you now? Country and city.','Citizenship?','What job or profession are you looking for?','Describe your experience: how many years and what can you do?','What residence/work documents do you currently have?','What pay do you expect?','What matters most: pay, stability, fast start, housing, or something else?','How long are you ready to work?','Do you have a driving licence? Categories and driving experience in Poland.'],
   de:['Vor- und Nachname in lateinischen Buchstaben wie in den Dokumenten?','Telefonnummer mit Ländervorwahl?','Wo befinden Sie sich jetzt? Land und Stadt.','Staatsangehörigkeit?','Welche Arbeit oder welchen Beruf suchen Sie?','Beschreiben Sie Ihre Erfahrung: wie viele Jahre und was können Sie?','Welche Aufenthalts-/Arbeitsdokumente haben Sie derzeit?','Welche Bezahlung erwarten Sie?','Was ist am wichtigsten: Lohn, Stabilität, schneller Start, Unterkunft oder etwas anderes?','Wie lange möchten Sie arbeiten?','Haben Sie einen Führerschein? Kategorien und Fahrerfahrung in Polen.'],
   es:['¿Nombre y apellido en letras latinas, como en sus documentos?','¿Número de teléfono con código de país?','¿Dónde está ahora? País y ciudad.','¿Nacionalidad?','¿Qué trabajo o profesión busca?','Describa su experiencia: años y habilidades.','¿Qué documentos de residencia/trabajo tiene actualmente?','¿Qué salario espera?','¿Qué es lo más importante: salario, estabilidad, empezar rápido, alojamiento u otra cosa?','¿Por cuánto tiempo está dispuesto a trabajar?','¿Tiene permiso de conducir? Categorías y experiencia conduciendo en Polonia.'],
   pt:['Nome e apelido em letras latinas, como nos documentos?','Número de telefone com indicativo do país?','Onde está agora? País e cidade.','Nacionalidade?','Que trabalho ou profissão procura?','Descreva a experiência: anos e competências.','Que documentos de residência/trabalho tem atualmente?','Que remuneração espera?','O que é mais importante: salário, estabilidade, início rápido, alojamento ou outra coisa?','Por quanto tempo está disponível para trabalhar?','Tem carta de condução? Categorias e experiência de condução na Polónia.']
  }
 },
 employer:{
  fields:['company','contact_person','phone','email','location','profession','quantity','pay','description','start_date','legalization_service'],
  q:{
   uk:['Назва компанії?','Контактна особа?','Телефон з кодом країни?','Email?','Країна, місто або регіон роботи?','Які працівники потрібні?','Скільки людей потрібно?','Яка оплата?','Коротко опишіть обов’язки, графік, житло та вимоги.','Коли потрібні люди?','Чи потрібен супровід із легалізації працівників?'],
   pl:['Nazwa firmy?','Osoba kontaktowa?','Telefon z kodem kraju?','Email?','Kraj, miasto lub region pracy?','Jakich pracowników potrzebujecie?','Ilu pracowników potrzeba?','Jakie wynagrodzenie?','Krótko opisz obowiązki, grafik, zakwaterowanie i wymagania.','Kiedy pracownicy są potrzebni?','Czy potrzebne jest wsparcie w legalizacji pracowników?'],
   ru:['Название компании?','Контактное лицо?','Телефон с кодом страны?','Email?','Страна, город или регион работы?','Какие работники нужны?','Сколько людей нужно?','Какая оплата?','Кратко опишите обязанности, график, жильё и требования.','Когда нужны работники?','Нужно сопровождение по легализации работников?'],
   en:['Company name?','Contact person?','Phone number with country code?','Email?','Country, city or work region?','What workers do you need?','How many people do you need?','What is the pay?','Briefly describe duties, schedule, housing and requirements.','When do you need the workers?','Do you need worker legalization support?'],
   de:['Firmenname?','Kontaktperson?','Telefonnummer mit Ländervorwahl?','E-Mail?','Land, Stadt oder Arbeitsregion?','Welche Mitarbeiter benötigen Sie?','Wie viele Personen werden benötigt?','Wie hoch ist die Bezahlung?','Beschreiben Sie kurz Aufgaben, Arbeitszeit, Unterkunft und Anforderungen.','Wann werden die Mitarbeiter benötigt?','Benötigen Sie Unterstützung bei der Legalisierung?'],
   es:['¿Nombre de la empresa?','¿Persona de contacto?','¿Teléfono con código de país?','¿Email?','¿País, ciudad o región de trabajo?','¿Qué trabajadores necesita?','¿Cuántas personas necesita?','¿Cuál es el salario?','Describa brevemente tareas, horario, alojamiento y requisitos.','¿Cuándo necesita a los trabajadores?','¿Necesita apoyo con la legalización de trabajadores?'],
   pt:['Nome da empresa?','Pessoa de contacto?','Telefone com indicativo do país?','Email?','País, cidade ou região de trabalho?','Que trabalhadores precisa?','Quantas pessoas precisa?','Qual é a remuneração?','Descreva brevemente funções, horário, alojamento e requisitos.','Quando precisa dos trabalhadores?','Precisa de apoio na legalização dos trabalhadores?']
  }
 },
 legal:{
  fields:['request_type','country','city','current_status','phone'],
  q:{
   uk:['Що саме потрібно: карта побиту, PESEL, дозвіл на роботу, консультація, сім’я чи інше?','У якій країні ви зараз?','У якому місті?','Який у вас зараз статус або документи?','Номер телефону з кодом країни?'],
   pl:['Czego dokładnie potrzebujesz: karta pobytu, PESEL, zezwolenie na pracę, konsultacja, rodzina czy inne?','W jakim kraju jesteś teraz?','W jakim mieście?','Jaki masz obecnie status lub dokumenty?','Numer telefonu z kodem kraju?'],
   ru:['Что именно нужно: карта побыта, PESEL, разрешение на работу, консультация, семья или другое?','В какой стране вы сейчас?','В каком городе?','Какой у вас сейчас статус или документы?','Номер телефона с кодом страны?'],
   en:['What do you need: residence card, PESEL, work permit, consultation, family case, or something else?','Which country are you currently in?','Which city?','What is your current status or documents?','Phone number with country code?'],
   de:['Was benötigen Sie: Aufenthaltstitel, PESEL, Arbeitserlaubnis, Beratung, Familie oder etwas anderes?','In welchem Land sind Sie derzeit?','In welcher Stadt?','Welchen aktuellen Status oder welche Dokumente haben Sie?','Telefonnummer mit Ländervorwahl?'],
   es:['¿Qué necesita: tarjeta de residencia, PESEL, permiso de trabajo, consulta, familia u otra cosa?','¿En qué país está ahora?','¿En qué ciudad?','¿Cuál es su situación o documentos actuales?','¿Número de teléfono con código de país?'],
   pt:['O que precisa: autorização de residência, PESEL, autorização de trabalho, consulta, família ou outro?','Em que país está agora?','Em que cidade?','Qual é o seu estatuto ou documentos atuais?','Número de telefone com indicativo do país?']
  }
 }
};

const q = async (sql,p=[]) => (await pool.query(sql,p)).rows;
const uuid = () => crypto.randomUUID();

async function init(){
 const ddl=[
  "CREATE TABLE IF NOT EXISTS ewu_sessions(telegram_id bigint primary key,lang text,mode text,step int default 0,data jsonb default '{}'::jsonb,updated_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_applications(id uuid primary key,kind text not null,telegram_id bigint not null,username text default '',language text default 'en',full_name text default '',phone text default '',status text default 'NEW',ai_score int,ai_summary text default '',data jsonb default '{}'::jsonb,created_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_messages(id uuid primary key,telegram_id bigint not null,direction text not null,body text not null,created_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_settings(key text primary key,value text not null,updated_at timestamptz default now())"
 ];
 ddl.push("CREATE TABLE IF NOT EXISTS ewu_drafts(telegram_id bigint not null,mode text not null,lang text,step int,data jsonb,updated_at timestamptz default now(),primary key(telegram_id,mode))");
 ddl.push("CREATE TABLE IF NOT EXISTS ewu_delivery(application_id uuid primary key,chat_id bigint not null,body text not null,attempts int default 0,delivered_at timestamptz,next_attempt_at timestamptz default now())");
 ddl.push("CREATE TABLE IF NOT EXISTS ewu_profiles(telegram_id bigint primary key,language text,data jsonb,updated_at timestamptz default now())");
 for(const s of ddl) await pool.query(s);
 await pool.query('ALTER TABLE ewu_sessions ADD COLUMN IF NOT EXISTS last_message_id bigint');
}

async function tg(method, body={}){
 const r=await fetch(API+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(65000)});
 const d=await r.json();
 if(!d.ok){const error=new Error('Telegram request failed');error.code=d.error_code;throw error;}
 return d.result;
}
async function saveMsg(id,direction,body){
 if(process.env.EWU_STORE_MESSAGE_BODIES !== 'true') return;
 try{await pool.query('INSERT INTO ewu_messages(id,telegram_id,direction,body) VALUES($1,$2,$3,$4)',[uuid(),id,direction,String(body||'')]);}catch(e){safeError('saveMsg')}
}
async function send(id,text,keyboard=null){
 const body={chat_id:id,text:String(text).slice(0,3900)};
 if(keyboard) body.reply_markup={keyboard,resize_keyboard:true};
 await tg('sendMessage',body); await saveMsg(id,'out',text);
}
const langKeyboard=()=>Object.keys(LANGS).map(x=>[x]);
const menuKeyboard=lang=>[[L[lang].candidate],[L[lang].employer],[L[lang].legal],[L[lang].about],[L[lang].contact]];
async function setSession(id,lang,mode,step=0,data={},messageId=null,db=pool){
 await db.query(`INSERT INTO ewu_sessions(telegram_id,lang,mode,step,data,last_message_id,updated_at) VALUES($1,$2,$3,$4,$5,$6,now())
 ON CONFLICT(telegram_id) DO UPDATE SET lang=EXCLUDED.lang,mode=EXCLUDED.mode,step=EXCLUDED.step,data=EXCLUDED.data,last_message_id=COALESCE(EXCLUDED.last_message_id,ewu_sessions.last_message_id),updated_at=now()`,[id,lang,mode,step,JSON.stringify(data),messageId]);
}
async function session(id){return (await q('SELECT * FROM ewu_sessions WHERE telegram_id=$1',[id]))[0]||null}
function phoneOk(x){return /^\+[1-9][0-9]{7,14}$/.test(String(x||'').replace(/[\s()\-]/g,''))}

function fallbackCandidate(data){
 const summary=['profession','current_location','experience','desired_pay','work_priority','duration'].filter(k=>data[k]).map(k=>k+': '+data[k]).join(' | ');
 return {summary:summary||'Candidate application collected.',score:null};
}
async function aiCandidate(data,lang){
 // Intake must remain available without AI. No automated person ranking.
 return fallbackCandidate(data);
}
async function aiSummary(kind,data,lang){
 if(!AI_ENABLED) return '';
 try{
  const prompt=`You are European Workers Union (EWU). Language: ${lang}. Create a concise operational summary for a ${kind} application. Do not invent facts. DATA: ${JSON.stringify(data)}`;
  const r=await generateText({model:AI_MODEL,prompt,abortSignal:AbortSignal.timeout(15000),providerOptions:{gateway:{tags:['product:ewu','feature:'+kind+'-summary']}}});
  return r.text.trim();
 }catch(e){safeError('AI summary');return ''}
}
async function aiChat(text,lang){
 if(!AI_ENABLED) return null;
 try{
  const prompt=`You are European Workers Union (EWU), a concise employment coordinator for Poland and Europe. Reply in language code ${lang}. Be practical, friendly, and do not invent job offers or legal guarantees. User: ${text}`;
  const r=await generateText({model:AI_MODEL,prompt,abortSignal:AbortSignal.timeout(15000),providerOptions:{gateway:{tags:['product:ewu','feature:chat']}}});
  return r.text.trim();
 }catch(e){safeError('AI chat');return null}
}
async function getSetting(key){
 const r=await q('SELECT value FROM ewu_settings WHERE key=$1',[key]);
 return r[0]?.value||'';
}
async function setSetting(key,value){
 await pool.query(`INSERT INTO ewu_settings(key,value,updated_at) VALUES($1,$2,now())
 ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()`,[key,String(value)]);
}
function applicationText(kind,data,ai,status){
 const title=kind==='candidate'?'👷 NEW CANDIDATE':kind==='employer'?'🏢 NEW EMPLOYER REQUEST':kind==='legal'?'📄 LEGALIZATION REQUEST':'📩 EWU REQUEST';
 const lines=[title,''];
 for(const [k,v] of Object.entries(data||{})){ if(v) lines.push(k.replaceAll('_',' ').toUpperCase()+': '+v); }
 if(ai?.score) lines.push('', 'SCORE: '+ai.score+'/10');
 if(status) lines.push('STATUS: '+status);
 if(ai?.summary) lines.push('', 'SUMMARY: '+ai.summary);
 return lines.join('\n').slice(0,3900);
}
async function notifyRecruitmentGroup(id,kind,data,ai,status,db=pool){
 const chatId=await getSetting('recruitment_group_chat_id');
 if(!chatId || !GROUP_IDS.has(String(chatId))) return;
 await db.query('INSERT INTO ewu_delivery(application_id,chat_id,body) VALUES($1,$2,$3) ON CONFLICT(application_id) DO NOTHING',[id,chatId,applicationText(kind,data,ai,status)]);
}
async function flushDelivery(){
 const pending=await q('SELECT * FROM ewu_delivery WHERE delivered_at IS NULL AND next_attempt_at <= now() ORDER BY next_attempt_at LIMIT 10');
 for(const item of pending){
  if(!GROUP_IDS.has(String(item.chat_id))) continue;
  try{
   await send(item.chat_id,item.body);
   await pool.query('UPDATE ewu_delivery SET delivered_at=now() WHERE application_id=$1',[item.application_id]);
  }catch{
   await pool.query("UPDATE ewu_delivery SET attempts=attempts+1,next_attempt_at=now()+interval '1 minute' WHERE application_id=$1",[item.application_id]);
   safeError('delivery_retry');
  }
 }
}
async function finalize(msg,s,kind,data){
 const ai=kind==='candidate'?fallbackCandidate(data):{summary:'',score:null};
 const id=msg.message_id ? crypto.createHash('sha256').update(String(msg.chat.id)+':'+String(msg.message_id)).digest('hex').slice(0,32).replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/,'$1-$2-$3-$4-$5') : uuid();
 // Retrying the same final Telegram message cannot create a second application.
 const client=await pool.connect();
 try{
 await client.query('BEGIN');
 await client.query('INSERT INTO ewu_applications(id,kind,telegram_id,username,language,full_name,phone,status,ai_score,ai_summary,data) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT(id) DO NOTHING',
 [id,kind,msg.from.id,msg.from.username||'',s.lang,data.full_name||data.contact_person||'',data.phone||'','NEW',null,ai.summary,JSON.stringify(data)]);
 if(kind==='candidate') await client.query('INSERT INTO ewu_profiles(telegram_id,language,data) VALUES($1,$2,$3) ON CONFLICT(telegram_id) DO UPDATE SET language=EXCLUDED.language,data=EXCLUDED.data,updated_at=now()',[msg.from.id,s.lang,JSON.stringify(data)]);
 await notifyRecruitmentGroup(id,kind,data,ai,'NEW',client);
 await client.query('DELETE FROM ewu_drafts WHERE telegram_id=$1 AND mode=$2',[msg.from.id,kind]);
 await setSession(msg.from.id,s.lang,'menu',0,{},msg.message_id,client);
 await client.query('COMMIT');
 }catch(error){await client.query('ROLLBACK');throw error;}finally{client.release();}
 await send(msg.chat.id,L[s.lang].saved,menuKeyboard(s.lang));
}
async function archiveDraft(id){
 const s=await session(id);
 if(s && flows[s.mode]) await pool.query('INSERT INTO ewu_drafts(telegram_id,mode,lang,step,data) VALUES($1,$2,$3,$4,$5) ON CONFLICT(telegram_id,mode) DO UPDATE SET lang=EXCLUDED.lang,step=EXCLUDED.step,data=EXCLUDED.data,updated_at=now()',[id,s.mode,s.lang,s.step,JSON.stringify(s.data)]);
}
async function openFlow(msg,lang,mode){
 await archiveDraft(msg.from.id);
 const draft=(await q('SELECT * FROM ewu_drafts WHERE telegram_id=$1 AND mode=$2',[msg.from.id,mode]))[0];
 const step=draft?.step||0, data=draft?.data||{};
 await setSession(msg.from.id,lang,mode,step,data);
 return send(msg.chat.id,flows[mode].q[lang][step]);
}
async function start(msg){
 const current=await session(msg.from.id);
 if(current && flows[current.mode]) return send(msg.chat.id,flows[current.mode].q[current.lang||'en'][current.step||0]);
 if(current?.lang){ await setSession(msg.from.id,current.lang,'menu',0,{}); return send(msg.chat.id,L[current.lang].welcome,menuKeyboard(current.lang)); }
 await setSession(msg.from.id,null,'language',0,{});
 await send(msg.chat.id,'European Workers Union (EWU)\n\nОберіть мову / Wybierz język / Choose language:',langKeyboard());
}
async function handleFlow(msg,s,text){
 const f=flows[s.mode], lang=s.lang||'en', data=s.data||{}, idx=s.step||0, field=f.fields[idx];
 if((field==='phone')&&!phoneOk(text)){await send(msg.chat.id,f.q[lang][idx]+'\n\n⚠️ Please include the country code.');return}
 data[field]=text;
 if(idx+1<f.fields.length){await setSession(msg.from.id,lang,s.mode,idx+1,data,msg.message_id);await send(msg.chat.id,f.q[lang][idx+1]);}
 else await finalize(msg,s,s.mode,data);
}
async function handle(msg){
 if(!msg?.from?.id) return;
 const text=String(msg.text||'').trim();
 if(!text) return;

 if(msg.chat?.type==='group' || msg.chat?.type==='supergroup'){
   if(commandOf(text)==='/bindgroup' && groupAuthorized(msg)){
     await setSetting('recruitment_group_chat_id',msg.chat.id);
     return send(msg.chat.id,'✅ Цю групу прив’язано до EWU. Нові заявки будуть надходити сюди.');
   }
   if(commandOf(text)==='/unbindgroup' && groupAuthorized(msg)){
     await setSetting('recruitment_group_chat_id','');
     return send(msg.chat.id,'✅ Групу відв’язано від EWU.');
   }
   return;
 }

 await saveMsg(msg.from.id,'in',text);
 const command=commandOf(text);
 if(command==='/start'||command==='/resume') return start(msg);
 if(command==='/reset') return send(msg.chat.id,'Reset requires confirmation: /confirm_reset');
 if(command==='/confirm_reset'){
  await pool.query('DELETE FROM ewu_drafts WHERE telegram_id=$1',[msg.from.id]);
  await setSession(msg.from.id,null,'language',0,{});
  return send(msg.chat.id,'Choose language:',langKeyboard());
 }
 if(command==='/help') return send(msg.chat.id,'/start /resume /reset /help');
 if(command.startsWith('/')) return send(msg.chat.id,'Use /help');
 let s=await session(msg.from.id);
 if(!s) return start(msg);
 if(msg.message_id && s.last_message_id && msg.message_id<=Number(s.last_message_id)){
  return send(msg.chat.id,flows[s.mode]?flows[s.mode].q[s.lang||'en'][s.step||0]:L[s.lang||'en'].saved,flows[s.mode]?null:menuKeyboard(s.lang||'en'));
 }
 if(s.mode==='language'){
  const lang=LANGS[text]; if(!lang) return send(msg.chat.id,'Please choose a language:',langKeyboard());
  await setSession(msg.from.id,lang,'menu',0,{});
  return send(msg.chat.id,L[lang].welcome,menuKeyboard(lang));
 }
 const lang=s.lang||'en';
 if(text===L[lang].menu){await archiveDraft(msg.from.id);await setSession(msg.from.id,lang,'menu',0,{});return send(msg.chat.id,L[lang].welcome,menuKeyboard(lang))}
 // Let a user switch application sections even when another questionnaire is in progress.
 // Handle menu buttons before treating text as a response to the active questionnaire.
 if(text===L[lang].candidate) return openFlow(msg,lang,'candidate');
 if(text===L[lang].employer) return openFlow(msg,lang,'employer');
 if(text===L[lang].legal) return openFlow(msg,lang,'legal');
 if(text===L[lang].about){await archiveDraft(msg.from.id);await setSession(msg.from.id,lang,'menu',0,{});return send(msg.chat.id,L[lang].aboutText,menuKeyboard(lang))}
 if(text===L[lang].contact){await archiveDraft(msg.from.id);await setSession(msg.from.id,lang,'contact',0,{});return send(msg.chat.id,L[lang].contactAsk)}
 if(['candidate','employer','legal'].includes(s.mode)) return handleFlow(msg,s,text);
 if(s.mode==='contact') return finalize(msg,s,'contact',{message:text});
 const a=await aiChat(text,lang);
 return send(msg.chat.id,a||L[lang].welcome,menuKeyboard(lang));
}

async function setup(){
 const lockClient=await pool.connect();
 const lockKey=crypto.createHash('sha256').update(TOKEN).digest().readInt32BE(0);
 const lock=await lockClient.query('SELECT pg_try_advisory_lock($1) AS acquired',[lockKey]);
 if(!lock.rows[0].acquired){lockClient.release();throw new Error('Polling owner exists');}
 // Keep this dedicated connection for the lifetime of the polling owner.
 lockClient.on('error',()=>{safeError('polling_lock_lost');process.exit(1)});
 const hook=await tg('getWebhookInfo');
 if(hook.url) throw new Error('Webhook configured; polling refused');
 await init();
 console.log('EWU initialized with explicit polling approval');
}
async function poll(){
 await setup();
 while(true){
  try{
   const updates=await tg('getUpdates',{offset,timeout:50,allowed_updates:['message']});
   lastPollAt=Date.now();
   for(const u of updates){if(u.message)await handle(u.message);offset=u.update_id+1;}
   await flushDelivery();
  }catch(e){
   if(e.code===409){safeError('telegram_consumer_conflict');process.exit(1);}
   safeError('poll');await new Promise(r=>setTimeout(r,3000));
  }
 }
}
http.createServer(async (req,res)=>{
  if(req.url==='/api/health'){
    res.writeHead(200,{'content-type':'application/json'});
    return res.end(JSON.stringify({ok:true,name:'EWU',startAllowed:START_ALLOWED}));
  }
  if(req.url==='/api/ready'){
   let ready=START_ALLOWED && lastPollAt>0 && Date.now()-lastPollAt<120000;
   if(ready){try{await pool.query('SELECT 1');const group=await getSetting('recruitment_group_chat_id');ready=GROUP_IDS.has(String(group));}catch{ready=false;}}
   res.writeHead(ready?200:503,{'content-type':'application/json'});return res.end(JSON.stringify({ready}));
  }
  res.writeHead(404,{'content-type':'application/json'});
  res.end(JSON.stringify({error:'Not found'}));
}).listen(PORT,'0.0.0.0',()=>console.log('EWU health server on '+PORT));

if(START_ALLOWED) poll().catch(e=>{safeError('startup');process.exit(1)});
else console.log('EWU start locked; polling disabled');

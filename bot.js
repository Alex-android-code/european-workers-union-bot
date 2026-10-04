import crypto from 'node:crypto';
import http from 'node:http';
import pg from 'pg';
import { generateText } from 'ai';

const { Pool } = pg;
const TOKEN = String(process.env.TELEGRAM_TOKEN || '');
const DB = String(process.env.DATABASE_URL || '');
const AI_MODEL = String(process.env.AI_MODEL || '');
const AI_ENABLED = Boolean(process.env.AI_GATEWAY_API_KEY && AI_MODEL);
if (!TOKEN || !DB) throw new Error('Missing TELEGRAM_TOKEN or DATABASE_URL');

const pool = new Pool({ connectionString: DB, max: 5 });
const API = 'https://api.telegram.org/bot' + TOKEN + '/';
const PORT = Number(process.env.PORT || 3000);
let offset = 0;

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
  "CREATE TABLE IF NOT EXISTS ewu_messages(id uuid primary key,telegram_id bigint not null,direction text not null,body text not null,created_at timestamptz default now())"
 ];
 for(const s of ddl) await pool.query(s);
}

async function tg(method, body={}){
 const r=await fetch(API+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
 const d=await r.json();
 if(!d.ok) throw new Error(method+': '+(d.description||'Telegram API error'));
 return d.result;
}
async function saveMsg(id,direction,body){
 try{await pool.query('INSERT INTO ewu_messages(id,telegram_id,direction,body) VALUES($1,$2,$3,$4)',[uuid(),id,direction,String(body||'')]);}catch(e){console.error('saveMsg',e.message)}
}
async function send(id,text,keyboard=null){
 const body={chat_id:id,text,parse_mode:'HTML'};
 if(keyboard) body.reply_markup={keyboard,resize_keyboard:true};
 await tg('sendMessage',body); await saveMsg(id,'out',text);
}
const langKeyboard=()=>Object.keys(LANGS).map(x=>[x]);
const menuKeyboard=lang=>[[L[lang].candidate],[L[lang].employer],[L[lang].legal],[L[lang].about],[L[lang].contact]];
async function setSession(id,lang,mode,step=0,data={}){
 await pool.query(`INSERT INTO ewu_sessions(telegram_id,lang,mode,step,data,updated_at) VALUES($1,$2,$3,$4,$5,now())
 ON CONFLICT(telegram_id) DO UPDATE SET lang=EXCLUDED.lang,mode=EXCLUDED.mode,step=EXCLUDED.step,data=EXCLUDED.data,updated_at=now()`,[id,lang,mode,step,JSON.stringify(data)]);
}
async function session(id){return (await q('SELECT * FROM ewu_sessions WHERE telegram_id=$1',[id]))[0]||null}
function phoneOk(x){return /\+?[0-9][0-9\s()\-]{7,}[0-9]/.test(String(x||''))}

async function aiCandidate(data,lang){
 if(!AI_ENABLED) return {summary:'Application collected successfully.',score:7};
 try{
  const prompt=`You are an EWU recruiter. Language: ${lang}. Return ONLY JSON {"summary":"...","score":1-10}. Summarize job fit, stability signals, documents, location and risks. Do not invent facts. DATA: ${JSON.stringify(data)}`;
  const r=await generateText({model:AI_MODEL,prompt,providerOptions:{gateway:{tags:['product:ewu','feature:candidate-score']}}});
  const m=r.text.match(/\{[\s\S]*\}/); if(m){const j=JSON.parse(m[0]);return {summary:String(j.summary||''),score:Math.max(1,Math.min(10,Number(j.score)||7))}}
 }catch(e){console.error('AI candidate',e.message)}
 return {summary:'Application collected successfully.',score:7};
}
async function aiSummary(kind,data,lang){
 if(!AI_ENABLED) return '';
 try{
  const prompt=`You are European Workers Union (EWU). Language: ${lang}. Create a concise operational summary for a ${kind} application. Do not invent facts. DATA: ${JSON.stringify(data)}`;
  const r=await generateText({model:AI_MODEL,prompt,providerOptions:{gateway:{tags:['product:ewu','feature:'+kind+'-summary']}}});
  return r.text.trim();
 }catch(e){console.error('AI summary',e.message);return ''}
}
async function aiChat(text,lang){
 if(!AI_ENABLED) return null;
 try{
  const prompt=`You are European Workers Union (EWU), a concise employment coordinator for Poland and Europe. Reply in language code ${lang}. Be practical, friendly, and do not invent job offers or legal guarantees. User: ${text}`;
  const r=await generateText({model:AI_MODEL,prompt,providerOptions:{gateway:{tags:['product:ewu','feature:chat']}}});
  return r.text.trim();
 }catch(e){console.error('AI chat',e.message);return null}
}
async function finalize(msg,s,kind,data){
 let ai={summary:'',score:null};
 if(kind==='candidate') ai=await aiCandidate(data,s.lang);
 else ai.summary=await aiSummary(kind,data,s.lang);
 const status=kind==='candidate'?(ai.score>=8?'HOT CANDIDATE':ai.score>=6?'WARM CANDIDATE':'NEW'):'NEW';
 await pool.query('INSERT INTO ewu_applications(id,kind,telegram_id,username,language,full_name,phone,status,ai_score,ai_summary,data) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)',
  [uuid(),kind,msg.from.id,msg.from.username||'',s.lang,data.full_name||data.contact_person||'',data.phone||'',status,ai.score,ai.summary,JSON.stringify(data)]);
 await setSession(msg.from.id,s.lang,'menu',0,{});
 await send(msg.chat.id,L[s.lang].saved,menuKeyboard(s.lang));
}

async function start(msg){
 await setSession(msg.from.id,null,'language',0,{});
 await send(msg.chat.id,'European Workers Union (EWU)\n\nОберіть мову / Wybierz język / Choose language:',langKeyboard());
}
async function handleFlow(msg,s,text){
 const f=flows[s.mode], lang=s.lang||'en', data=s.data||{}, idx=s.step||0, field=f.fields[idx];
 if((field==='phone')&&!phoneOk(text)){await send(msg.chat.id,f.q[lang][idx]+'\n\n⚠️ Please include the country code.');return}
 data[field]=text;
 if(idx+1<f.fields.length){await setSession(msg.from.id,lang,s.mode,idx+1,data);await send(msg.chat.id,f.q[lang][idx+1]);}
 else await finalize(msg,s,s.mode,data);
}
async function handle(msg){
 if(!msg?.from?.id) return;
 const text=String(msg.text||'').trim();
 if(!text) return;
 await saveMsg(msg.from.id,'in',text);
 if(text==='/start'||text==='/reset') return start(msg);
 let s=await session(msg.from.id);
 if(!s) return start(msg);
 if(s.mode==='language'){
  const lang=LANGS[text]; if(!lang) return send(msg.chat.id,'Please choose a language:',langKeyboard());
  await setSession(msg.from.id,lang,'menu',0,{});
  return send(msg.chat.id,L[lang].welcome,menuKeyboard(lang));
 }
 const lang=s.lang||'en';
 if(text===L[lang].menu){await setSession(msg.from.id,lang,'menu',0,{});return send(msg.chat.id,L[lang].welcome,menuKeyboard(lang))}
 if(['candidate','employer','legal'].includes(s.mode)) return handleFlow(msg,s,text);
 if(s.mode==='contact'){
  const data={message:text};
  await pool.query('INSERT INTO ewu_applications(id,kind,telegram_id,username,language,status,data) VALUES($1,$2,$3,$4,$5,$6,$7)',[uuid(),'contact',msg.from.id,msg.from.username||'',lang,'NEW',JSON.stringify(data)]);
  await setSession(msg.from.id,lang,'menu',0,{});
  return send(msg.chat.id,L[lang].saved,menuKeyboard(lang));
 }
 if(text===L[lang].candidate){await setSession(msg.from.id,lang,'candidate',0,{});return send(msg.chat.id,flows.candidate.q[lang][0])}
 if(text===L[lang].employer){await setSession(msg.from.id,lang,'employer',0,{});return send(msg.chat.id,flows.employer.q[lang][0])}
 if(text===L[lang].legal){await setSession(msg.from.id,lang,'legal',0,{});return send(msg.chat.id,flows.legal.q[lang][0])}
 if(text===L[lang].about) return send(msg.chat.id,L[lang].aboutText,menuKeyboard(lang));
 if(text===L[lang].contact){await setSession(msg.from.id,lang,'contact',0,{});return send(msg.chat.id,L[lang].contactAsk)}
 const a=await aiChat(text,lang);
 return send(msg.chat.id,a||L[lang].welcome,menuKeyboard(lang));
}

async function setup(){
 await init();
 try{await tg('deleteWebhook',{drop_pending_updates:false})}catch{}
 try{await tg('setMyName',{name:'European Workers Union'})}catch{}
 try{await tg('setMyDescription',{description:'EWU — jobs, workers and legalization support across Poland and Europe.'})}catch{}
 try{await tg('setMyCommands',{commands:[{command:'start',description:'Start / choose language'},{command:'reset',description:'Reset dialogue'}]})}catch{}
 console.log('EWU production bot initialized. AI='+AI_ENABLED);
}
async function poll(){
 await setup();
 while(true){
  try{
   const updates=await tg('getUpdates',{offset,timeout:50,allowed_updates:['message']});
   for(const u of updates){offset=u.update_id+1;try{if(u.message)await handle(u.message)}catch(e){console.error('handle',e)}}
  }catch(e){console.error('poll',e.message);await new Promise(r=>setTimeout(r,3000))}
 }
}
http.createServer((req,res)=>{
  if(req.url==='/api/health'){
    res.writeHead(200,{'content-type':'application/json'});
    return res.end(JSON.stringify({ok:true,name:'European Workers Union Bot',ai:AI_ENABLED}));
  }
  res.writeHead(404,{'content-type':'application/json'});
  res.end(JSON.stringify({error:'Not found'}));
}).listen(PORT,'0.0.0.0',()=>console.log('EWU health server on '+PORT));

poll().catch(e=>{console.error(e);process.exit(1)});

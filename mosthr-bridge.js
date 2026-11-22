import { createHmac, randomUUID } from 'node:crypto';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const bridgeText = {
 uk: { jobs:'Вакансії', empty:'Опублікованих вакансій поки немає.', consent:'Одержувач ваших даних:', policy:'Повідомлення про обробку даних:', fields:'Передамо лише ім’я, телефон, місто, доступність і опис досвіду для цієї вакансії. AI-аналіз не запускається. /agree — погодитися; /cancel — скасувати.', questions:['Ваше ім’я та прізвище?','Телефон із кодом країни?','У якому місті ви перебуваєте?','Коротко опишіть досвід (до 500 символів).'], pending:'Заявку збережено в EWU. Передача агенції очікує підтвердження. Перевірити: /status', sent:'Агенція отримала вашу заявку.', cancelled:'Заявку скасовано.', invalid:'Перевірте відповідь і спробуйте ще раз.', unavailable:'Вакансія недоступна або змінилася. Відкрийте /jobs та подайтеся знову.', failed:'Інтеграція тимчасово недоступна. Спробуйте пізніше.', noApplications:'У вас ще немає заявок MostHR.', stages:{new:'Заявку отримано',contacted:'Рекрутер позначив контакт',interview:'Етап співбесіди',documents:'Етап документів',placed:'Рекрутер позначив працевлаштування',withdrawn:'Запис видалено в агенції',pending:'Очікує передачі',blocked:'Передачу зупинено — відкрийте /jobs та подайтеся знову'} },
 pl: { jobs:'Oferty pracy', empty:'Brak opublikowanych ofert.', consent:'Odbiorca Twoich danych:', policy:'Informacja o przetwarzaniu danych:', fields:'Przekażemy tylko imię i nazwisko, telefon, miasto, dostępność oraz opis doświadczenia dla tej oferty. Bez analizy AI. /agree — zgoda; /cancel — anuluj.', questions:['Imię i nazwisko?','Telefon z kodem kraju?','W jakim mieście jesteś?','Krótko opisz doświadczenie (do 500 znaków).'], pending:'Zgłoszenie zapisano w EWU. Przekazanie agencji czeka na potwierdzenie. Sprawdź: /status', sent:'Agencja otrzymała Twoje zgłoszenie.', cancelled:'Anulowano zgłoszenie.', invalid:'Sprawdź odpowiedź i spróbuj ponownie.', unavailable:'Oferta jest niedostępna lub zmieniła się. Otwórz /jobs i zgłoś się ponownie.', failed:'Integracja jest chwilowo niedostępna. Spróbuj później.', noApplications:'Nie masz jeszcze zgłoszeń MostHR.', stages:{new:'Otrzymano zgłoszenie',contacted:'Rekruter oznaczył kontakt',interview:'Etap rozmowy',documents:'Etap dokumentów',placed:'Rekruter oznaczył zatrudnienie',withdrawn:'Agencja usunęła profil',pending:'Oczekuje na przekazanie',blocked:'Przekazanie zatrzymano — otwórz /jobs i zgłoś się ponownie'} },
 en: { jobs:'Jobs', empty:'No published jobs yet.', consent:'Recipient of your data:', policy:'Privacy notice:', fields:'Only your name, phone, city, availability and experience will be sent for this job. No AI analysis. /agree — consent; /cancel — cancel.', questions:['Your full name?','Phone with country code?','Which city are you in?','Briefly describe your experience (up to 500 characters).'], pending:'Saved in EWU. Delivery to the agency is awaiting confirmation. Check: /status', sent:'The agency has received your application.', cancelled:'Application cancelled.', invalid:'Check your answer and try again.', unavailable:'Job unavailable or changed. Open /jobs and apply again.', failed:'Integration temporarily unavailable. Please try later.', noApplications:'No MostHR applications yet.', stages:{new:'Application received',contacted:'Recruiter marked contact',interview:'Interview stage',documents:'Documents stage',placed:'Recruiter marked employment',withdrawn:'Agency deleted the profile',pending:'Awaiting delivery',blocked:'Delivery stopped — open /jobs and apply again'} },
 ru: { jobs:'Вакансии', empty:'Опубликованных вакансий пока нет.', consent:'Получатель ваших данных:', policy:'Информация об обработке данных:', fields:'Передадим только имя, телефон, город, доступность и опыт для этой вакансии. Без AI-анализа. /agree — согласиться; /cancel — отменить.', questions:['Имя и фамилия?','Телефон с кодом страны?','В каком вы городе?','Кратко опишите опыт (до 500 символов).'], pending:'Заявка сохранена в EWU. Передача агентству ожидает подтверждения. Проверка: /status', sent:'Агентство получило вашу заявку.', cancelled:'Заявка отменена.', invalid:'Проверьте ответ и попробуйте снова.', unavailable:'Вакансия недоступна или изменилась. Откройте /jobs и подайтесь снова.', failed:'Интеграция временно недоступна. Попробуйте позже.', noApplications:'Заявок MostHR пока нет.', stages:{new:'Заявка получена',contacted:'Рекрутер отметил контакт',interview:'Этап собеседования',documents:'Этап документов',placed:'Рекрутер отметил трудоустройство',withdrawn:'Агентство удалило профиль',pending:'Ожидает передачи',blocked:'Передача остановлена — откройте /jobs и подайтесь снова'} },
 es: { jobs:'Vacantes', empty:'Aún no hay vacantes publicadas.', consent:'Destinatario de sus datos:', policy:'Aviso de privacidad:', fields:'Solo enviaremos nombre, teléfono, ciudad, disponibilidad y experiencia para esta vacante. Sin análisis de IA. /agree — aceptar; /cancel — cancelar.', questions:['¿Nombre y apellido?','¿Teléfono con código de país?','¿En qué ciudad está?','Describa brevemente su experiencia (máximo 500 caracteres).'], pending:'Guardado en EWU. La entrega a la agencia espera confirmación. Consulte /status', sent:'La agencia recibió su solicitud.', cancelled:'Solicitud cancelada.', invalid:'Revise su respuesta e inténtelo de nuevo.', unavailable:'Vacante no disponible o modificada. Abra /jobs y vuelva a postularse.', failed:'Integración temporalmente no disponible. Inténtelo más tarde.', noApplications:'Aún no tiene solicitudes MostHR.', stages:{new:'Solicitud recibida',contacted:'El reclutador marcó contacto',interview:'Etapa de entrevista',documents:'Etapa de documentos',placed:'El reclutador marcó contratación',withdrawn:'La agencia eliminó el perfil',pending:'Pendiente de entrega',blocked:'Entrega detenida — abra /jobs y vuelva a postularse'} },
 pt: { jobs:'Vagas', empty:'Ainda não há vagas publicadas.', consent:'Destinatário dos seus dados:', policy:'Aviso de privacidade:', fields:'Enviaremos apenas nome, telefone, cidade, disponibilidade e experiência para esta vaga. Sem análise de IA. /agree — aceitar; /cancel — cancelar.', questions:['Nome e apelido?','Telefone com indicativo do país?','Em que cidade está?','Descreva a experiência (até 500 caracteres).'], pending:'Guardado na EWU. A entrega à agência aguarda confirmação. Consulte /status', sent:'A agência recebeu a sua candidatura.', cancelled:'Candidatura cancelada.', invalid:'Verifique a resposta e tente novamente.', unavailable:'Vaga indisponível ou alterada. Abra /jobs e candidate-se novamente.', failed:'Integração temporariamente indisponível. Tente mais tarde.', noApplications:'Ainda não tem candidaturas MostHR.', stages:{new:'Candidatura recebida',contacted:'Recrutador marcou contacto',interview:'Etapa de entrevista',documents:'Etapa de documentos',placed:'Recrutador marcou contratação',withdrawn:'Agência eliminou o perfil',pending:'Aguarda entrega',blocked:'Entrega interrompida — abra /jobs e candidate-se novamente'} },
 de: { jobs:'Stellen', empty:'Noch keine veröffentlichten Stellen.', consent:'Empfänger Ihrer Daten:', policy:'Datenschutzhinweis:', fields:'Nur Name, Telefon, Stadt, Verfügbarkeit und Erfahrung werden für diese Stelle übermittelt. Keine KI-Analyse. /agree — zustimmen; /cancel — abbrechen.', questions:['Vor- und Nachname?','Telefon mit Ländervorwahl?','In welcher Stadt sind Sie?','Beschreiben Sie Ihre Erfahrung (bis 500 Zeichen).'], pending:'Bei EWU gespeichert. Übermittlung an die Agentur wartet auf Bestätigung. Prüfen: /status', sent:'Die Agentur hat Ihre Bewerbung erhalten.', cancelled:'Bewerbung abgebrochen.', invalid:'Bitte Antwort prüfen und erneut versuchen.', unavailable:'Stelle nicht verfügbar oder geändert. Öffnen Sie /jobs und bewerben Sie sich erneut.', failed:'Integration vorübergehend nicht verfügbar. Später erneut versuchen.', noApplications:'Noch keine MostHR-Bewerbungen.', stages:{new:'Bewerbung erhalten',contacted:'Kontakt durch Recruiter markiert',interview:'Gesprächsphase',documents:'Dokumentenphase',placed:'Beschäftigung durch Recruiter markiert',withdrawn:'Agentur hat Profil gelöscht',pending:'Übermittlung ausstehend',blocked:'Übermittlung gestoppt — /jobs öffnen und erneut bewerben'} },
};

const availabilityQuestions = {
 uk:'Коли можете почати? /now — негайно; /2weeks — за 2 тижні; /month — за місяць.',
 pl:'Kiedy możesz zacząć? /now — od zaraz; /2weeks — za 2 tygodnie; /month — za miesiąc.',
 en:'When can you start? /now — now; /2weeks — in 2 weeks; /month — in a month.',
 ru:'Когда можете начать? /now — сразу; /2weeks — через 2 недели; /month — через месяц.',
 es:'¿Cuándo puede empezar? /now — ahora; /2weeks — en 2 semanas; /month — en un mes.',
 pt:'Quando pode começar? /now — agora; /2weeks — em 2 semanas; /month — num mês.',
 de:'Wann können Sie anfangen? /now — sofort; /2weeks — in 2 Wochen; /month — in einem Monat.'
};

export function createMosthrClient({ baseUrl, key, fetchImpl = fetch }) {
  const url = new URL(baseUrl);
  if (url.username || url.password || url.search || url.hash || (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost','127.0.0.1'].includes(url.hostname)))) throw new Error('MostHR requires HTTPS');
  if (!key || key.length < 32) throw new Error('MostHR bridge key must have at least 32 characters');
  const base = url.origin + '/api/integrations/ewu/bot';
  async function request(path, body) {
    const r = await fetchImpl(base + path, { method: body ? 'POST':'GET', redirect:'error',
      headers:{ Authorization:`Bearer ${key}`, ...(body ? {'Content-Type':'application/json'}:{}) },
      ...(body ? {body:JSON.stringify(body)}:{}), signal:AbortSignal.timeout(10_000) });
    if (!r.ok) { const e=new Error('MostHR request failed'); e.status=r.status; throw e; }
    return r.json();
  }
  return { jobs:async () => (await request('/jobs')).jobs, submit:body => request('/applications',body), status:(applicationId,externalCandidateKey) => request('/status',{applicationId,externalCandidateKey}) };
}

export function createPgBridgeStore(pool) {
  return {
    async init() {
      await pool.query(`CREATE TABLE IF NOT EXISTS ewu_mosthr_dialogues (telegram_id bigint PRIMARY KEY, state jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())`);
      await pool.query(`CREATE TABLE IF NOT EXISTS ewu_mosthr_outbox (id uuid PRIMARY KEY, publication_id uuid NOT NULL, telegram_id bigint NOT NULL,
        language text NOT NULL, title text NOT NULL, external_candidate_key text NOT NULL, payload jsonb NOT NULL,
        state text NOT NULL DEFAULT 'pending', remote_id uuid, last_stage text, attempts int NOT NULL DEFAULT 0,
        next_attempt_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (publication_id, telegram_id))`);
    },
    async get(id) {
      const row=(await pool.query('SELECT state, updated_at FROM ewu_mosthr_dialogues WHERE telegram_id=$1',[id])).rows[0];
      if(!row) return null;
      return new Date(row.updated_at).getTime()<Date.now()-86_400_000 ? {step:'expired',language:row.state.language} : row.state;
    },
    async put(id,state) { await pool.query(`INSERT INTO ewu_mosthr_dialogues(telegram_id,state) VALUES($1,$2) ON CONFLICT(telegram_id) DO UPDATE SET state=EXCLUDED.state, updated_at=now()`,[id,JSON.stringify(state)]); },
    async clear(id) { await pool.query('DELETE FROM ewu_mosthr_dialogues WHERE telegram_id=$1',[id]); },
    async enqueue(row) {
      const r=await pool.query(`INSERT INTO ewu_mosthr_outbox(id,publication_id,telegram_id,language,title,external_candidate_key,payload)
        VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(publication_id,telegram_id) DO UPDATE SET
        payload=CASE WHEN ewu_mosthr_outbox.state='blocked' THEN EXCLUDED.payload ELSE ewu_mosthr_outbox.payload END,
        state=CASE WHEN ewu_mosthr_outbox.state='blocked' THEN 'pending' ELSE ewu_mosthr_outbox.state END,
        next_attempt_at=now() RETURNING *`,[row.id,row.publicationId,row.telegramId,row.language,row.title,row.externalCandidateKey,JSON.stringify(row.payload)]);
      return r.rows[0];
    },
    async list(id) { return (await pool.query('SELECT id, title, state, last_stage FROM ewu_mosthr_outbox WHERE telegram_id=$1 ORDER BY created_at DESC LIMIT 20',[id])).rows; },
    async work(fn) {
      const c=await pool.connect();
      try {
        await c.query('BEGIN');
        const {rows}=await c.query(`SELECT * FROM ewu_mosthr_outbox WHERE state IN ('pending','delivered') AND next_attempt_at<=now() ORDER BY next_attempt_at LIMIT 10 FOR UPDATE SKIP LOCKED`);
        for (const row of rows) {
          const next=await fn(row);
          await c.query(`UPDATE ewu_mosthr_outbox SET state=$2, remote_id=$3, last_stage=$4, payload=$5,
            attempts=attempts+1, next_attempt_at=now()+($6::int * interval '1 second') WHERE id=$1`,
          [row.id,next.state,next.remoteId||row.remote_id||null,next.lastStage||row.last_stage||null,JSON.stringify(next.payload ?? row.payload),next.delay||60]);
        }
        await c.query('COMMIT');
      } catch(e) { await c.query('ROLLBACK'); throw e; } finally { c.release(); }
    },
    async cleanup() {
      // Unfinished forms expire after 24h; undelivered PII is retained for at most seven days.
      await pool.query("UPDATE ewu_mosthr_dialogues SET state=jsonb_build_object('step','expired','language',state->>'language') WHERE updated_at < now()-interval '24 hours' AND state->>'step'!='expired'");
      await pool.query("DELETE FROM ewu_mosthr_dialogues WHERE updated_at < now()-interval '90 days'");
      await pool.query("UPDATE ewu_mosthr_outbox SET state='blocked',payload='{}'::jsonb WHERE state='pending' AND created_at < now()-interval '7 days'");
      await pool.query("DELETE FROM ewu_mosthr_outbox WHERE created_at < now()-interval '90 days'");
    },
  };
}

export function createMosthrBridge({ client, store, send, botUsername, subjectSecret, getLanguage = async () => null, onEnter = async () => {} }) {
  if (!/^[a-zA-Z0-9_]{5,32}$/.test(botUsername || '') || !subjectSecret || subjectSecret.length < 32) throw new Error('MostHR bot identity configuration missing');
  const externalKey = (publicationId, telegramId) => createHmac('sha256',subjectSecret).update(`${publicationId}:${telegramId}`).digest('hex');
  const pack = language => bridgeText[language] || bridgeText.en;
  async function handle(msg) {
    if (msg?.chat?.type !== 'private' || !msg.from?.id) return false;
    const value=String(msg.text || '').trim(), telegramId=msg.from.id;
    const language=(await getLanguage(telegramId)) || msg.from.language_code?.slice(0,2) || 'en';
    const t=pack(language);
    const start=value.match(/^\/start(?:@[a-zA-Z0-9_]+)? mhr_([0-9a-f-]+)$/i);
    if (/^\/(start|reset|cancel)(?:@[a-zA-Z0-9_]+)?$/.test(value)) {
      const existing=await store.get(telegramId); await store.clear(telegramId);
      if(value==='/cancel' && existing) { await send(msg.chat.id,t.cancelled); return true; }
      return false;
    }
    if (/^\/jobs(?:\s+\d+)?$/.test(value)) {
      try {
        const jobs=await client.jobs(), page=Math.max(1,Number(value.split(/\s+/)[1])||1), pageJobs=jobs.slice((page-1)*5,page*5);
        if(!pageJobs.length) { await send(msg.chat.id,t.empty); return true; }
        for(const job of pageJobs) await send(msg.chat.id,`${job.title}\n${job.city}\n${job.salaryRange || ''}\n${t.consent} ${job.agencyName}\nhttps://t.me/${botUsername}?start=mhr_${job.id}`);
        if(jobs.length>page*5) await send(msg.chat.id,`/jobs ${page+1}`);
      } catch { await send(msg.chat.id,t.failed); }
      return true;
    }
    if(value==='/status') {
      const rows=await store.list(telegramId);
      await send(msg.chat.id,rows.length ? rows.map(r=>`${r.title}: ${t.stages[['delivered','finished'].includes(r.state) ? r.last_stage : r.state] || r.state}`).join('\n').slice(0,3900) : t.noApplications);
      return true;
    }
    if(start) {
      if(!UUID.test(start[1])) { await send(msg.chat.id,t.unavailable); return true; }
      try {
        const job=(await client.jobs()).find(j=>j.id===start[1]);
        if(!job) { await store.clear(telegramId); await send(msg.chat.id,t.unavailable); return true; }
        await onEnter(telegramId,language);
        await store.put(telegramId,{job,language,step:'consent',data:{}});
        await send(msg.chat.id,`${job.title}\n${job.city}\n${job.salaryRange || ''}\n${job.description || ''}`.slice(0,3500));
        // Keep recipient, notice and consent instructions intact even for long job descriptions.
        await send(msg.chat.id,`${t.consent} ${job.agencyName}\n${t.policy} ${job.privacyUrl}\n\n${t.fields}`);
      } catch { await send(msg.chat.id,t.failed); }
      return true;
    }
    const s=await store.get(telegramId); if(!s) return false;
    const st=pack(s.language);
    if(s.step==='expired') { await send(msg.chat.id,st.unavailable); return true; }
    if(s.step==='consent') {
      if(value!=='/agree') { await send(msg.chat.id,st.fields); return true; }
      s.acceptedAt=new Date().toISOString(); s.step=0;
      await store.put(telegramId,s); await send(msg.chat.id,st.questions[0]); return true;
    }
    const fields=['fullName','phone','city','experienceSummary','availability'], limits=[160,40,120,500,20];
    if(!value || (value.startsWith('/') && s.step!==4) || value.length>limits[s.step] || (s.step===1 && !/^\+?[0-9][0-9 ()-]{6,38}[0-9]$/.test(value))) {
      await send(msg.chat.id,st.invalid); return true;
    }
    if(s.step===4 && !['/now','/2weeks','/month'].includes(value)) { await send(msg.chat.id,st.invalid); return true; }
    s.data[fields[s.step]]=s.step===4 ? ({'/now':'available','/2weeks':'twoWeeks','/month':'oneMonth'}[value]) : value;
    if(s.step<4) { s.step++; await store.put(telegramId,s); await send(msg.chat.id,s.step===4 ? (availabilityQuestions[s.language] || availabilityQuestions.en) : st.questions[s.step]); return true; }
    let current;
    try { current=(await client.jobs()).find(j=>j.id===s.job.id); }
    catch { await store.put(telegramId,s); await send(msg.chat.id,st.failed); return true; }
    if(!current || current.consentVersion!==s.job.consentVersion) { await store.clear(telegramId); await send(msg.chat.id,st.unavailable); return true; }
    const applicationId=randomUUID(), externalCandidateKey=externalKey(s.job.id,telegramId);
    const receipt=await store.enqueue({id:applicationId,publicationId:s.job.id,telegramId,language:s.language,title:s.job.title,externalCandidateKey,
      payload:{applicationId,publicationId:s.job.id,externalCandidateKey,transferConsent:true,consentVersion:s.job.consentVersion,consentAcceptedAt:s.acceptedAt,candidate:s.data}});
    await store.clear(telegramId);
    await send(msg.chat.id,['delivered','finished'].includes(receipt?.state) ? `${st.sent}\n${st.stages[receipt.last_stage] || ''}` : st.pending);
    return true;
  }
  let busy=false;
  async function tick() {
    if(busy) return; busy=true;
    try {
      await store.cleanup();
      await store.work(async row => {
        const t=pack(row.language);
        try {
          if(row.state==='pending') {
            const result=await client.submit(row.payload);
            await send(row.telegram_id,`${t.sent}\n${row.title}: ${t.stages[result.stage] || result.stage}`);
            return {state:result.stage==='withdrawn' ? 'finished':'delivered',remoteId:result.applicationId,lastStage:result.stage,payload:{},delay:60};
          }
          const result=await client.status(row.remote_id,row.external_candidate_key);
          if(result.stage!==row.last_stage) await send(row.telegram_id,`${row.title}: ${t.stages[result.stage] || result.stage}`);
          return {state:result.stage==='withdrawn' ? 'finished':'delivered',lastStage:result.stage,payload:{},delay:60};
        } catch(e) {
          if([400,404,409,413].includes(e.status)) {
            await send(row.telegram_id,`${row.title}: ${t.unavailable}`);
            return {state:'blocked',payload:{},delay:60};
          }
          return {state:row.state,delay:Math.min(3600,30*2**Math.min(row.attempts||0,7))};
        }
      });
    } finally { busy=false; }
  }
  return {handle,tick};
}

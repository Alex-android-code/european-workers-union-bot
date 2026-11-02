"""Small reviewed flow catalogue; no paid translation call at runtime."""
TEXT = {
 'uk': dict(menu='EWU — оберіть дію',candidate='👷 Шукаю роботу',employer='🏢 Шукаю працівників',legal='📄 Легалізація і документи',about='ℹ️ Про EWU',contact='📞 Координатор',
  candidate_q=['Ваше ім’я?','У якому місті ви зараз?','Контактний телефон із кодом країни?','Яку роботу шукаєте?'],
  employer_q=['Назва компанії?','Місто роботи?','Які працівники потрібні? Не вказуйте чужі персональні дані.','Контактний телефон із кодом країни?'],
  legal_q=['Якої країни стосується запит?','Коротке загальне питання. Не надсилайте документи, PESEL або медичні дані.','Контактний телефон із кодом країни?'],
  saved='Заявку збережено. Це ще не підтвердження працевлаштування. /status — стан; /arrival — погоджений план прибуття.',
  no_plan='Погодженого актуального плану прибуття ще немає. Не вирушайте без підтвердження координатора.',
  no_apps='У вас немає збережених заявок.',phone='Вкажіть коректний телефон із кодом країни.',progress='Крок',unknown='Оберіть дію в меню. Повідомлення не пересилається координатору автоматично.'),
 'pl': dict(menu='EWU — wybierz opcję',candidate='👷 Szukam pracy',employer='🏢 Szukam pracowników',legal='📄 Legalizacja i dokumenty',about='ℹ️ O EWU',contact='📞 Koordynator',
  candidate_q=['Jak masz na imię?','W jakim mieście teraz jesteś?','Telefon kontaktowy z kodem kraju?','Jakiej pracy szukasz?'],
  employer_q=['Nazwa firmy?','Miasto pracy?','Jakich pracowników potrzebujecie? Nie podawaj danych innych osób.','Telefon kontaktowy z kodem kraju?'],
  legal_q=['Jakiego kraju dotyczy pytanie?','Krótko opisz ogólne pytanie. Nie wysyłaj dokumentów, PESEL ani danych medycznych.','Telefon kontaktowy z kodem kraju?'],
  saved='Zgłoszenie zapisano. Nie oznacza to potwierdzenia zatrudnienia. /status — stan; /arrival — uzgodniony plan przyjazdu.',no_plan='Brak uzgodnionego aktualnego planu przyjazdu. Nie wyjeżdżaj bez potwierdzenia koordynatora.',no_apps='Brak zapisanych zgłoszeń.',phone='Podaj poprawny telefon z kodem kraju.',progress='Krok',unknown='Wybierz opcję w menu. Wiadomość nie jest automatycznie przekazywana koordynatorowi.'),
 'ru': dict(menu='EWU — выберите действие',candidate='👷 Ищу работу',employer='🏢 Ищу работников',legal='📄 Легализация и документы',about='ℹ️ Об EWU',contact='📞 Координатор',
  candidate_q=['Ваше имя?','В каком городе вы сейчас?','Контактный телефон с кодом страны?','Какую работу ищете?'],
  employer_q=['Название компании?','Город работы?','Какие работники нужны? Не указывайте чужие персональные данные.','Контактный телефон с кодом страны?'],
  legal_q=['Какой страны касается вопрос?','Короткий общий вопрос. Не отправляйте документы, PESEL или медицинские данные.','Контактный телефон с кодом страны?'],
  saved='Заявка сохранена. Это ещё не подтверждение трудоустройства. /status — состояние; /arrival — согласованный план приезда.',no_plan='Согласованного актуального плана приезда пока нет. Не выезжайте без подтверждения координатора.',no_apps='Сохранённых заявок нет.',phone='Укажите правильный телефон с кодом страны.',progress='Шаг',unknown='Выберите действие в меню. Сообщение не пересылается координатору автоматически.'),
 'uz': dict(menu='EWU — amalni tanlang',candidate='👷 Ish qidiryapman',employer='🏢 Ishchilar qidiryapman',legal='📄 Qonuniylashtirish va hujjatlar',about='ℹ️ EWU haqida',contact='📞 Koordinator',
  candidate_q=['Ismingiz?','Hozir qaysi shahardasiz?','Davlat kodi bilan aloqa telefoningiz?','Qanday ish qidiryapsiz?'],
  employer_q=['Kompaniya nomi?','Ish shahri?','Qanday ishchilar kerak? Boshqa shaxslarning ma’lumotlarini yozmang.','Davlat kodi bilan aloqa telefoningiz?'],
  legal_q=['Savol qaysi mamlakatga tegishli?','Umumiy savolni qisqacha yozing. Hujjat, PESEL yoki tibbiy ma’lumot yubormang.','Davlat kodi bilan aloqa telefoningiz?'],
  saved='Ariza saqlandi. Bu ishga qabul tasdig‘i emas. /status — holat; /arrival — kelishilgan kelish rejasi.',no_plan='Hozircha tasdiqlangan kelish rejasi yo‘q. Koordinator tasdig‘isiz yo‘lga chiqmang.',no_apps='Saqlangan arizalar yo‘q.',phone='Davlat kodi bilan to‘g‘ri telefon raqamini yozing.',progress='Bosqich',unknown='Menyudan amal tanlang. Xabar koordinatorga avtomatik yuborilmaydi.')
}

# Original seven-language catalogue, plus Uzbek retained from the recovery.
TEXT.update({
 'en': dict(menu='EWU — choose an option',candidate='👷 I’m looking for work',employer='🏢 I’m looking for workers',legal='📄 Legalization and documents',about='ℹ️ About EWU',contact='📞 Contact coordinator',
  candidate_q=['Your name?','Which city are you in now?','Contact phone with country code?','What work are you looking for?'],
  employer_q=['Company name?','Work city?','What workers do you need? Do not include other people’s personal data.','Contact phone with country code?'],
  legal_q=['Which country does your question concern?','Brief general question. Do not send documents, PESEL or medical data.','Contact phone with country code?'],
  saved='Application saved. This does not confirm employment. /status — application status; /arrival — agreed arrival plan.',
  no_plan='There is no current agreed arrival plan. Do not travel without coordinator confirmation.',no_apps='You have no saved applications.',phone='Enter a valid phone number with country code.',progress='Step',unknown='Choose an option from the menu. Your message is not automatically forwarded to a coordinator.'),
 'de': dict(menu='EWU — wählen Sie eine Option',candidate='👷 Ich suche Arbeit',employer='🏢 Ich suche Mitarbeiter',legal='📄 Legalisierung und Dokumente',about='ℹ️ Über EWU',contact='📞 Koordinator kontaktieren',
  candidate_q=['Ihr Name?','In welcher Stadt sind Sie derzeit?','Kontakttelefon mit Ländervorwahl?','Welche Arbeit suchen Sie?'],
  employer_q=['Firmenname?','Arbeitsort?','Welche Mitarbeiter benötigen Sie? Geben Sie keine personenbezogenen Daten anderer Personen an.','Kontakttelefon mit Ländervorwahl?'],
  legal_q=['Welches Land betrifft Ihre Frage?','Kurze allgemeine Frage. Senden Sie keine Dokumente, PESEL oder Gesundheitsdaten.','Kontakttelefon mit Ländervorwahl?'],
  saved='Anfrage gespeichert. Dies ist keine Beschäftigungsbestätigung. /status — Bearbeitungsstand; /arrival — vereinbarter Anreiseplan.',
  no_plan='Es gibt noch keinen aktuellen vereinbarten Anreiseplan. Reisen Sie nicht ohne Bestätigung des Koordinators.',no_apps='Sie haben keine gespeicherten Anfragen.',phone='Geben Sie eine gültige Telefonnummer mit Ländervorwahl an.',progress='Schritt',unknown='Wählen Sie eine Option im Menü. Ihre Nachricht wird nicht automatisch an einen Koordinator weitergeleitet.'),
 'es': dict(menu='EWU — elija una opción',candidate='👷 Busco trabajo',employer='🏢 Busco trabajadores',legal='📄 Legalización y documentos',about='ℹ️ Sobre EWU',contact='📞 Contactar coordinador',
  candidate_q=['¿Su nombre?','¿En qué ciudad está ahora?','¿Teléfono de contacto con código de país?','¿Qué trabajo busca?'],
  employer_q=['¿Nombre de la empresa?','¿Ciudad de trabajo?','¿Qué trabajadores necesita? No incluya datos personales de otras personas.','¿Teléfono de contacto con código de país?'],
  legal_q=['¿A qué país se refiere su consulta?','Pregunta general breve. No envíe documentos, PESEL ni datos médicos.','¿Teléfono de contacto con código de país?'],
  saved='Solicitud guardada. Esto no confirma la contratación. /status — estado; /arrival — plan de llegada acordado.',
  no_plan='Todavía no hay un plan de llegada vigente y acordado. No viaje sin la confirmación del coordinador.',no_apps='No tiene solicitudes guardadas.',phone='Introduzca un teléfono válido con código de país.',progress='Paso',unknown='Elija una opción del menú. Su mensaje no se reenvía automáticamente al coordinador.'),
 'pt': dict(menu='EWU — escolha uma opção',candidate='👷 Procuro trabalho',employer='🏢 Procuro trabalhadores',legal='📄 Legalização e documentos',about='ℹ️ Sobre a EWU',contact='📞 Contactar coordenador',
  candidate_q=['O seu nome?','Em que cidade está agora?','Telefone de contacto com indicativo do país?','Que trabalho procura?'],
  employer_q=['Nome da empresa?','Cidade de trabalho?','Que trabalhadores precisa? Não inclua dados pessoais de outras pessoas.','Telefone de contacto com indicativo do país?'],
  legal_q=['A que país se refere a sua questão?','Pergunta geral breve. Não envie documentos, PESEL nem dados médicos.','Telefone de contacto com indicativo do país?'],
  saved='Pedido guardado. Isto não confirma a contratação. /status — estado; /arrival — plano de chegada acordado.',
  no_plan='Ainda não existe um plano de chegada atual e acordado. Não viaje sem confirmação do coordenador.',no_apps='Não tem pedidos guardados.',phone='Introduza um telefone válido com indicativo do país.',progress='Passo',unknown='Escolha uma opção do menu. A sua mensagem não é automaticamente encaminhada ao coordenador.')
})

from privacy.onboarding import LANGUAGES
TEXT = {lang: TEXT[lang] for lang in LANGUAGES}

RIGHTS = {
 'uk': ('Запит зареєстровано. Адміністратор перевірить його застосовність і повідомить результат. Номер: ', 'Для виправлення: /correct поле значення. Поля: name, city, phone, profession.', 'Оберіть мову', 'Необов’язкові згоди не ввімкнені. Ознайомлення не є згодою.'),
 'pl': ('Żądanie zarejestrowano. Administrator sprawdzi jego zastosowanie i przekaże wynik. Numer: ', 'Sprostowanie: /correct pole wartość. Pola: name, city, phone, profession.', 'Wybierz język', 'Opcjonalne zgody są wyłączone. Zapoznanie się z informacją nie jest zgodą.'),
 'ru': ('Запрос зарегистрирован. Администратор проверит его применимость и сообщит результат. Номер: ', 'Исправление: /correct поле значение. Поля: name, city, phone, profession.', 'Выберите язык', 'Необязательные согласия выключены. Ознакомление не является согласием.'),
 'en': ('Request registered. The controller will check applicability and report the outcome. Reference: ', 'Correction: /correct field value. Fields: name, city, phone, profession.', 'Choose your language', 'Optional consents are disabled. Acknowledgement is not consent.'),
 'de': ('Antrag registriert. Der Verantwortliche prüft die Anwendbarkeit und teilt das Ergebnis mit. Nummer: ', 'Berichtigung: /correct Feld Wert. Felder: name, city, phone, profession.', 'Sprache wählen', 'Optionale Einwilligungen sind deaktiviert. Kenntnisnahme ist keine Einwilligung.'),
 'es': ('Solicitud registrada. El responsable comprobará su aplicabilidad y comunicará el resultado. Referencia: ', 'Rectificación: /correct campo valor. Campos: name, city, phone, profession.', 'Elija su idioma', 'Los consentimientos opcionales están desactivados. La lectura no es consentimiento.'),
 'pt': ('Pedido registado. O responsável verificará a aplicabilidade e comunicará o resultado. Referência: ', 'Retificação: /correct campo valor. Campos: name, city, phone, profession.', 'Escolha o idioma', 'Os consentimentos opcionais estão desativados. A leitura não é consentimento.'),
}

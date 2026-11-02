"""Canonical recruitment states; legacy codes remain readable during migration."""
STATUSES=('NEW','FORM_COMPLETED','UNDER_REVIEW','APPROVED','DEPARTURE_CONFIRMED','ARRIVED','STARTED','REJECTED','WITHDRAWN','NO_SHOW','DID_NOT_START','FINISHED')
LABELS={
 'uk':['Новий','Анкета заповнена','На розгляді','Схвалений','Підтверджений виїзд','Прибув','Почав роботу','Відмова','Відкликав заявку','Не прибув','Не вийшов на роботу','Завершив роботу'],
 'pl':['Nowy','Formularz wypełniony','W trakcie rozpatrywania','Zaakceptowany','Wyjazd potwierdzony','Przyjechał','Rozpoczął pracę','Odrzucony','Wycofał zgłoszenie','Nie przyjechał','Nie rozpoczął pracy','Zakończył pracę'],
 'ru':['Новый','Анкета заполнена','На рассмотрении','Одобрен','Выезд подтверждён','Прибыл','Начал работу','Отказ','Отозвал заявку','Не прибыл','Не вышел на работу','Завершил работу'],
 'en':['New','Form completed','Under review','Approved','Departure confirmed','Arrived','Started work','Rejected','Application withdrawn','Did not arrive','Did not start work','Finished work'],
 'de':['Neu','Formular ausgefüllt','In Prüfung','Genehmigt','Abreise bestätigt','Angekommen','Arbeit begonnen','Abgelehnt','Bewerbung zurückgezogen','Nicht angekommen','Arbeit nicht angetreten','Arbeit beendet'],
 'es':['Nuevo','Formulario completado','En revisión','Aprobado','Salida confirmada','Llegó','Empezó a trabajar','Rechazado','Solicitud retirada','No llegó','No empezó a trabajar','Trabajo finalizado'],
 'pt':['Novo','Formulário preenchido','Em análise','Aprovado','Partida confirmada','Chegou','Começou a trabalhar','Recusado','Candidatura retirada','Não chegou','Não iniciou o trabalho','Trabalho concluído'],
}
LEGACY={'CONTACTED':'UNDER_REVIEW','OFFERED':'APPROVED','CONFIRMED':'APPROVED','TRAVEL_PLANNED':'DEPARTURE_CONFIRMED','CLOSED':'FINISHED'}

def label(status,lang):
    status=LEGACY.get(status,status)
    return LABELS.get(lang,LABELS['uk'])[STATUSES.index(status)] if status in STATUSES else status

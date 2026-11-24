"""Read a patient's date/time without interpreting names or administrative fields."""
import re
from datetime import datetime, timedelta

WEEKDAYS = ('segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo')
NAMED_DAY = r'(?:depois de amanha|amanha|hoje|(?:proxim[oa] )?(?:' + '|'.join(WEEKDAYS) + r')(?:[- ]feira)?)'
BOOKING_INTENT = re.compile(r'\b(?:agende|agendar|marque|marcar|reserve|reservar|(?:quero|preciso de|gostaria de) (?:um )?agendamento)\b')


def named_date(value, today):
    if value in ('hoje', 'amanha', 'depois de amanha'):
        return today + timedelta(days=('hoje', 'amanha', 'depois de amanha').index(value))
    weekday = value.removeprefix('proxima ').removeprefix('proximo ').split('-')[0].split()[0]
    return today + timedelta(days=(WEEKDAYS.index(weekday) - today.weekday()) % 7 or 7)


def normalize_separators(text):
    return re.sub(r'(?<=\d)\s*/\s*(?=\d)','/',text)


def patient_datetime(text):
    text=normalize_separators(text)
    pattern=r'(?<![\d/\-])(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{4})?)(?![\d/\-])'
    matches=list(re.finditer(pattern,text))
    dates=list(dict.fromkeys(m.group() for m in matches))
    if len(dates)>1:raise ValueError('Escolha uma única data para o agendamento.')
    for value in dates:
        if '-' in value or value.count('/')==2:
            try:datetime.strptime(value,'%Y-%m-%d' if '-' in value else '%d/%m/%Y')
            except ValueError:raise ValueError('Essa data não existe. Informe dia, mês e ano válidos.') from None
    # Mask dates before reading times: the colon after an ISO date is not an hour.
    remainder=text
    for m in reversed(matches):remainder=remainder[:m.start()]+' '*len(m.group())+remainder[m.end():]
    if '/' in remainder:raise ValueError('Não consegui ler a data. Use dia/mês/ano, por exemplo 12/11/2026.')
    relative=re.findall(r'\b'+NAMED_DAY+r'\b',remainder)
    if len(set(relative))>1 or (dates and relative):raise ValueError('Informe uma única data, sem combinar dias diferentes.')
    times=[]
    time_pattern=r'(?<![\d:/\-])(\d{1,2})(?:\s*h(?:oras?)?(?:\s*(\d{2}))?|\s*:\s*(\d{2}))(?![\d:/\-])'
    for match in re.finditer(time_pattern,remainder):
        hour=int(match.group(1));minute=int(match.group(2) or match.group(3) or '0')
        if not 0<=hour<24 or not 0<=minute<60:raise ValueError('Informe um horário válido, como 08:30.')
        times.append(f'{hour:02}:{minute:02}')
    if not times:
        bare=re.search(r'\bas?\s+(\d{1,2})(?![\d:/])\b',remainder)
        if bare:
            hour=int(bare.group(1))
            if hour>=24:raise ValueError('Informe um horário válido.')
            part=re.match(r'\s+da (manha|tarde|noite)\b',remainder[bare.end():])
            if part and hour <= 12:
                hour=hour % 12 + (0 if part.group(1)=='manha' else 12)
            times.append(f'{hour:02}:00')
    times=list(dict.fromkeys(times))
    if len(times)>1:raise ValueError('Você enviou vários horários. Escolha apenas um, por exemplo: 12/11/2026 às 08:30. Ainda não agendei.')
    return ' '.join(dates+list(dict.fromkeys(relative))+times)

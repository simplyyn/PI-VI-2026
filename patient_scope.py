"""Local routing for questions that can be answered in the patient channel."""
import re

from assistant import normalize


PRIVATE_TOPICS = re.compile(
    r'\b(?:fatur\w*|receita(?:s)?|lucro(?:s)?|salario(?:s)?|folha de pagamento|'
    r'estoque|insumos|relatori\w*|indicador\w*|estatistic\w*|balanco|'
    r'prontuarios?|cpf|senhas?|credencia\w*|dados internos|outros? pacientes?|'
    r'(?:lista|nomes?|contatos?|telefones?) (?:d[eo]s? )?(?:todos os )?(?:pacientes|clientes))\b'
)
AGGREGATE = re.compile(r'\b(?:quant[oa]s|total|numero|volume|media|contagem)\b')
CLINIC_RECORDS = re.compile(
    r'\b(?:pacientes|clientes|consultas|agendamentos|atendimentos|limpezas|profilaxias|procedimentos|'
    r'fizeram|fizemos|fazem|realizaram|realizamos|atenderam|foram (?:feitos|feitas|realizados|realizadas))\b'
)
RECORDED_ACTIVITY = re.compile(r'\b(?:fizeram|fizemos|realizaram|realizamos|atenderam|foram (?:feitos|feitas|realizados|realizadas))\b')
PUBLIC_TOPICS = re.compile(
    r'\b(?:odont\w*|dent\w*|gengiv\w*|consulta\w*|agend\w*|reagend\w*|remarc\w*|'
    r'marcar|marque|reservar|reserve|horari\w*|disponive\w*|disponibilidade|funcionamento|enderec\w*|'
    r'contato|telefone|recepcao|convenio\w*|planos?|cancel\w*|'
    r'pagamento\w*|pix|cartao|orcamento|procedimento\w*|limpeza\w*|profilax\w*|'
    r'clareamento|avaliacao|canal|restaurac\w*|extrac\w*|implante\w*|cirurg\w*|'
    r'siso|aparelho|ortodont\w*|protese|faceta\w*|radiografi\w*|fluor|selante|'
    r'raspagem|endodont\w*|periodont\w*|carie\w*|boca)\b'
)
UNRELATED = re.compile(
    r'\b(?:quanto e\s+(?:\d+|um|dois|tres|quatro)\s*(?:mais\b|menos\b|vezes\b|dividido\b|[+*/×÷-])|'
    r'\d+\s*[+*×÷]\s*\d+|dois mais dois|ignore (?:as |todas as )?instrucoes|'
    r'prompt (?:do sistema|interno)|finja ser (?:o )?admin\w*)'
)
BOOKING_WORDS = re.compile(r'\b(?:pode ser|prefiro|quero|escolho|no dia|dia|para|as|depois de amanha|amanha|hoje|horas?|e)\b')


def patient_response(question, *, booking_active=False):
    """Return a local reply, or None when booking or public knowledge can answer."""
    message = normalize(question)
    if PRIVATE_TOPICS.search(message) or (
        AGGREGATE.search(message) and CLINIC_RECORDS.search(message)
        and (RECORDED_ACTIVITY.search(message) or not re.search(
            r'\b(?:devo|preciso|recomendad\w*|(?:minhas|meus) (?:consultas|agendamentos))\b', message))
    ):
        return reply('Dados internos da clínica são restritos à equipe. Posso ajudar com seus agendamentos, horários, convênios e informações públicas sobre procedimentos.', 'restrito')
    if message in {'oi', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'ajuda', 'obrigado', 'obrigada'}:
        return reply('Posso ajudar com agendamentos, convênios, horários e procedimentos da clínica. O que você gostaria de saber?', 'atendimento')
    if not UNRELATED.search(message) and (
        PUBLIC_TOPICS.search(message) or (booking_active and booking_reply(message))
    ):
        return None
    return reply('Posso ajudar com assuntos da clínica, como agendamentos, horários, convênios e procedimentos odontológicos.', 'fora_do_escopo')


def reply(text, kind):
    return dict(resposta=text, fontes=[], gerado_por_llm=False, tipo=kind)


def booking_reply(question):
    message = normalize(question)
    if message in {'confirmar', 'confirmo', 'sim', 'pode agendar', 'cancelar', 'desistir'}:
        return True
    return bool(re.search(r'\d|\b(?:hoje|amanha)\b', message)
                and re.fullmatch(r'[\d\s/:h.,;-]*', BOOKING_WORDS.sub('', message)))

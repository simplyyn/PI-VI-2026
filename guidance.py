"""Orientação inicial de encaminhamento; não diagnostica nem escolhe tratamento."""
import re
import unicodedata

def initial_guidance(question):
    text=''.join(c for c in unicodedata.normalize('NFKD',question.lower()) if not unicodedata.combining(c))
    text=re.sub(r'\bnao (?:tenho|sinto|estou com) (?:dificuldade (?:para|de) (?:respirar|engolir)|dor|inchaco|sangramento)\b','',text)
    text=re.sub(r'\bsem (?:dor|inchaco|sangramento)\b','',text)
    urgent=('dificuldade para respirar','dificuldade de respirar','nao consigo respirar',
            'dificuldade para engolir','dificuldade de engolir','nao consigo engolir',
            'sangramento que nao para','sangramento nao para','sangramento intenso')
    if any(phrase in text for phrase in urgent):
        return dict(resposta='Esse relato pode precisar de atendimento imediato. Se você está com dificuldade para respirar ou engolir, ou com sangramento intenso que não para, procure um pronto atendimento agora. Não espere uma resposta do chat ou um horário de rotina. O dentista precisará avaliar a causa; não é possível indicar um procedimento por aqui.',
                    fontes=[],gerado_por_llm=False,tipo='orientacao_urgente',procedimento_sugerido=None)
    symptoms=re.search(r'\b(dor|dores|doendo|doi|sensibilidade|inchaco|inchada|inchado|sangramento|sangrando|quebrado|quebrou|fraturado)\b',text)
    dental=re.search(r'\b(dente|dentes|dental|gengiva|gengivas|boca|bochecha|rosto|mandibula|siso)\b',text)
    if symptoms and dental:
        return dict(resposta='Para entender o que está acontecendo, o próximo passo é uma consulta de avaliação odontológica. O dentista vai examinar a região e conversar com você antes de indicar qualquer tratamento. Só pelo relato não dá para concluir se é necessário restauração, canal, extração ou outro procedimento. Há quanto tempo isso começou? Se houver dor forte ou persistente, inchaço ou febre, procure atendimento odontológico com prioridade. Se houver dificuldade para respirar ou engolir, procure um pronto atendimento imediatamente.',
                    fontes=[],gerado_por_llm=False,tipo='orientacao_inicial',procedimento_sugerido='Consulta de avaliação odontológica')
    return None

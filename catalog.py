"""Opções de cadastro; indicação e disponibilidade dependem de avaliação."""
PROCEDURE_OPTIONS = (
    'Consulta de avaliação', 'Limpeza dental (profilaxia)', 'Clareamento dental',
    'Restauração dentária', 'Tratamento de canal', 'Extração dentária simples',
    'Raspagem periodontal', 'Avaliação ortodôntica', 'Implante dentário', 'Prótese dentária',
    'Extração de siso', 'Coroa dentária', 'Facetas e lentes de contato dental',
    'Aparelho ortodôntico', 'Alinhadores transparentes', 'Radiografia periapical',
    'Placa de mordida', 'Aplicação tópica de flúor', 'Aplicação de selante',
    'Consulta odontopediátrica', 'Prótese protocolo',
)


def requested_procedure(message, options=PROCEDURE_OPTIONS):
    from scheduling import normalized
    import re

    aliases = {
        'limpeza': 'Limpeza dental (profilaxia)', 'profilaxia': 'Limpeza dental (profilaxia)',
        'avaliacao': 'Consulta de avaliação', 'canal': 'Tratamento de canal',
        'clareamento': 'Clareamento dental', 'restauracao': 'Restauração dentária',
        'raspagem': 'Raspagem periodontal', 'fluor': 'Aplicação tópica de flúor',
    }
    for option in sorted(options, key=len, reverse=True):
        if re.search(r'\b'+re.escape(normalized(option))+r'(?!\w)', message):
            return option
    for alias, procedure in aliases.items():
        if procedure in options and re.search(r'\b'+alias+r'\b', message):
            return procedure
    return None

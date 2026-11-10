"""Curated public references, checked 2026-11-06. Not a clinic's approved fees."""
from dataclasses import dataclass

REVIEWED = '06/11/2026'
MARKET = 'https://dentmap.com.br/blog/tabela-precos-procedimentos-dentista-2026'
CAASP = 'https://www.caasp.org.br/arquivos/tabelasodonto/ODT_Tabela_Interior_Referenciado_Agregado_2025.pdf'
GENERAL = 'https://www.nhs.uk/live-well/healthy-teeth-and-gums/dental-treatments/'
CANAL = 'https://www.nhs.uk/tests-and-treatments/root-canal-treatment/'
WHITENING = 'https://www.nhs.uk/tests-and-treatments/teeth-whitening/'
GUM = 'https://www.nhs.uk/conditions/gum-disease/'
BRACES = 'https://www.nhs.uk/tests-and-treatments/braces/'
CHILDREN = 'https://www.nhs.uk/live-well/healthy-teeth-and-gums/taking-care-of-childrens-teeth/'
BRUXISM = 'https://www.nhs.uk/symptoms/teeth-grinding/'
XRAY = 'https://www.mouthhealthy.org/all-topics-a-z/x-rays'
PRICE_NOTE = ('Estimativa informativa, sujeita à avaliação e ao orçamento da clínica. '
              'Não é preço fixo, tabela aprovada pela clínica ou média nacional. '
              'Confirmar o que está incluído antes de contratar; etapas complementares não devem ser presumidas.')


@dataclass(frozen=True)
class Procedure:
    name: str
    aliases: str
    explanation: str
    price: str
    source: str
    unit: str
    clinical_source: str = GENERAL

    def article(self):
        origin = ('Faixa publicada para clínicas particulares do Sudeste, DentMap, abril de 2026. '
                  'O levantamento do editor não foi auditado por este projeto.' if self.source == MARKET else
                  'Valor da tabela contratual CAASP, rede referenciada do interior, categoria Agregado, 2025. '
                  'Não representa preço médio particular de 2026.')
        return dict(titulo=self.name,categoria='Procedimentos',status=True,conteudo=(
            f'{self.name}. Termos relacionados: {self.aliases}.\n'
            f'O que é: {self.explanation}\n'
            f'Valor de referência: {self.price}. Escopo: {self.unit}.\n'
            f'{origin} {PRICE_NOTE}\n'
            'A indicação depende de consulta com o dentista; o assistente não diagnostica, prescreve ou garante resultado.\n'
            f'Fonte dos valores: {self.source}\nFonte da descrição geral: {self.clinical_source}\nConsulta das fontes: {REVIEWED}.'))


PROCEDURES = (
    Procedure('Consulta de avaliação','consulta inicial, orçamento, exame odontológico',
              'É o primeiro contato para examinar a saúde bucal e discutir necessidades e possibilidades de cuidado.',
              'R$ 150,00 a R$ 400,00',MARKET,'consulta geral; exames e tratamentos devem ser confirmados separadamente'),
    Procedure('Limpeza dental (profilaxia)','limpeza, polimento, prevenção, placa bacteriana',
              'É uma limpeza profissional dos dentes. O dentista diferencia prevenção de tratamento periodontal.',
              'R$ 150,00 a R$ 500,00',MARKET,'limpeza dental; extensão e itens incluídos dependem da avaliação'),
    Procedure('Clareamento dental','clarear os dentes, clareamento caseiro supervisionado, clareamento em consultório',
              'Busca clarear dentes naturais com supervisão odontológica. Coroas e próteses não clareiam da mesma maneira.',
              'R$ 400,00 a R$ 2.000,00',MARKET,'técnica, kit e número de sessões a confirmar',WHITENING),
    Procedure('Restauração dentária','resina, obturação, cárie, dente quebrado',
              'Repõe a parte danificada do dente com um material restaurador escolhido após avaliação.',
              'R$ 131,00 (1 face), R$ 262,00 (2 faces) ou R$ 392,00 (3 faces)',CAASP,'restauração fotopolimerizável, conforme quantidade de faces'),
    Procedure('Tratamento de canal','endodontia, canal do dente, polpa',
              'Trata a região interna do dente quando indicado. O número de sessões varia; restauração ou coroa podem ser necessárias.',
              'R$ 600,00 a R$ 2.500,00',MARKET,'tratamento endodôntico; confirmar dente, complexidade e acabamento restaurador',CANAL),
    Procedure('Extração dentária simples','exodontia, retirar dente, arrancar dente',
              'É a remoção de um dente quando o dentista verifica essa necessidade. Dor isolada não define indicação de extração.',
              'R$ 391,00',CAASP,'exodontia simples; não confundir com cirurgia de dente incluso'),
    Procedure('Raspagem periodontal','limpeza profunda, tártaro, gengiva, raspagem supragengival, raspagem subgengival',
              'É a limpeza de depósitos relacionados à saúde das gengivas, podendo envolver áreas abaixo da gengiva.',
              'R$ 262,00 (supragengival) ou R$ 391,00 (subgengival)',CAASP,'por sessão; número de sessões depende do exame',GUM),
    Procedure('Avaliação ortodôntica','consulta de ortodontia, aparelho, alinhamento',
              'Examina a posição dos dentes e a mordida antes de planejar aparelho ou alinhadores.',
              'sem valor específico pesquisado para esta avaliação',MARKET,'consulta especializada; não assumir preço de instalação ou tratamento completo',BRACES),
    Procedure('Implante dentário','implante, substituição de dente perdido',
              'É uma opção para substituir dentes ausentes com suporte implantado. Exige planejamento e avaliação individual.',
              'R$ 3.000,00 a R$ 8.000,00',MARKET,'o levantamento não detalha todos os componentes; confirmar coroa, cirurgia e eventuais etapas adicionais'),
    Procedure('Prótese dentária','dentadura, prótese removível, reposição de dentes',
              'Substitui dentes ausentes. Pode ter diferentes materiais e desenhos, definidos em consulta.',
              'R$ 800,00 a R$ 5.000,00',MARKET,'tipo, material, quantidade de dentes e etapas a confirmar'),
    Procedure('Extração de siso','terceiro molar, siso incluso, cirurgia do siso',
              'É a remoção de um terceiro molar quando há indicação. Nem todo siso precisa ser removido.',
              'R$ 300,00 a R$ 1.500,00',MARKET,'complexidade e abrangência do orçamento a confirmar'),
    Procedure('Coroa dentária','coroa, cobertura do dente, coroa metalo-cerâmica, coroa cerâmica',
              'É uma cobertura fixada sobre um dente preparado para recuperar sua forma e função.',
              'R$ 1.463,00 (metalo-cerâmica) ou R$ 1.503,00 (E-max maquiada)',CAASP,'coroa conforme material; confirmar etapas e serviços associados'),
    Procedure('Facetas e lentes de contato dental','faceta, lente dental, estética do sorriso',
              'Recobrem parte da superfície do dente. A necessidade de preparo e as alternativas devem ser discutidas antes da decisão.',
              'R$ 800,00 a R$ 3.000,00',MARKET,'material, quantidade de dentes e unidade de cobrança a confirmar'),
    Procedure('Aparelho ortodôntico','aparelho fixo, ortodontia, correção da mordida',
              'Movimenta dentes de forma planejada pelo ortodontista. O acompanhamento integra o tratamento.',
              'R$ 2.500,00 a R$ 7.000,00',MARKET,'escopo do tratamento a confirmar; não assumir inclusão de manutenção e contenção',BRACES),
    Procedure('Alinhadores transparentes','alinhador, aparelho transparente, Invisalign',
              'São uma modalidade de aparelho removível para movimentação planejada dos dentes.',
              'R$ 8.000,00 a R$ 20.000,00',MARKET,'plano, quantidade de alinhadores, revisões e contenções a confirmar',BRACES),
    Procedure('Radiografia periapical','raio-x periapical, radiografia do dente, exame de imagem',
              'É um exame de imagem para complementar a avaliação de um dente e da região de sua raiz. O dentista decide quando solicitar.',
              'R$ 43,00',CAASP,'Rx periapical diagnóstico; não corresponde a panorâmica ou tomografia',XRAY),
    Procedure('Placa de mordida','placa para bruxismo, placa de relaxamento, placa oclusal',
              'É um dispositivo odontológico cujo uso e acompanhamento devem ser definidos pelo dentista.',
              'R$ 599,00',CAASP,'placa de mordida/relaxamento; confirmar adaptação e retornos',BRUXISM),
    Procedure('Aplicação tópica de flúor','flúor, prevenção de cárie, fluorterapia',
              'É uma medida preventiva aplicada conforme a avaliação odontológica do risco de cárie.',
              'R$ 131,00',CAASP,'aplicação tópica; protocolo individual definido em consulta',CHILDREN),
    Procedure('Aplicação de selante','selante, proteção de sulcos, prevenção infantil',
              'É uma medida preventiva em superfícies indicadas pelo dentista, sem substituir a higiene bucal.',
              'R$ 131,00',CAASP,'por sessão, conforme tabela; quantidade de dentes a confirmar',CHILDREN),
    Procedure('Consulta odontopediátrica','odontopediatria, dentista infantil, consulta de criança',
              'É uma avaliação odontológica voltada à criança e à orientação de seus responsáveis.',
              'R$ 150,00 a R$ 400,00',MARKET,'a categoria publicada é odontopediatria; confirmar serviços incluídos',CHILDREN),
    Procedure('Prótese protocolo','protocolo sobre implantes, reabilitação de arcada',
              'É uma modalidade de reabilitação protética. Sua composição precisa ser detalhada pelo profissional.',
              'R$ 15.000,00 a R$ 40.000,00',MARKET,'arcada, implantes, materiais e cirurgias incluídos devem ser confirmados'),
)


def articles():
    price_lines='\n'.join(f'{p.name}: {p.price}.' for p in PROCEDURES)
    return [
        dict(titulo='Preços e procedimentos',categoria='Financeiro',status=True,conteudo=(
            'Referências de valores odontológicos. '+PRICE_NOTE+'\n'+price_lines+'\n'
            'Faixas regionais: clínicas particulares do Sudeste, DentMap, abril/2026. '
            'Valores pontuais e por faces/sessão: tabela contratual CAASP Interior, Agregado, 2025. '
            'Não combinar essas bases para calcular uma média nacional. Não chamar essas referências de tabela oficial da clínica. '
            'Para unidade, inclusões e limites, consulte o artigo específico de cada procedimento. '
            'Avaliação e limpeza, se ambas forem solicitadas, têm faixa combinada de R$ 300,00 a R$ 900,00, calculada pela soma das faixas publicadas; não é pacote fechado.\n'
            f'Fontes: {MARKET}\n{CAASP}\nConsulta das fontes: {REVIEWED}.')),
        dict(titulo='Procedimentos disponíveis e avaliação profissional',categoria='Procedimentos',status=True,conteudo=(
            'Catálogo de procedimentos para consulta e agendamento: '+ '; '.join(p.name for p in PROCEDURES)+'. '
            'O dentista confirma a indicação e o plano de tratamento. Não se escolhe canal, extração ou implante apenas pelo relato no chat. '
            'Cada procedimento tem artigo próprio com descrição, referência de valor e escopo. '
            'Horário de funcionamento e agendamento são consultados no artigo específico. '
            f'Fontes gerais: {GENERAL}\n{CANAL}\nConsulta: {REVIEWED}.')),
        *[p.article() for p in PROCEDURES],
    ]

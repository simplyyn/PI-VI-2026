"""Stock answers calculated from persisted quantities, without a model or purchase claims."""
import re


def amount(number,unit):
    unit=unit.casefold()
    plural={'caixa':'caixas','pacote':'pacotes','seringa':'seringas','pote':'potes','unidade':'unidades','frasco':'frascos','kit':'kits','rolo':'rolos'}
    return f"{number} {unit if number==1 else plural.get(unit,unit)}"


def stock_answer(items,question):
    from assistant import result
    zero=bool(re.search(r'\b(esgotad\w*|zerad\w*)\b',question) or 'sem estoque' in question)
    critical=zero or any(term in question for term in ('em falta','faltando','falta','baixo','baixa','repor','reposicao','acabando','comprar','compra','critic'))
    healthy=any(term in question for term in ('em dia','adequad','estoque normal','estoque ok'))
    from services import stock_view
    items=[stock_view(item) for item in items]
    empty=sorted([s for s in items if s['status']=='esgotado'],key=lambda s:s['nome'])
    low=sorted([s for s in items if s['status']=='baixo'],key=lambda s:(s['quantidade']/s['minimo'],s['nome']))
    good=sorted([s for s in items if s['status']=='ok'],key=lambda s:s['nome'])
    if not items:return result('Ainda não há materiais cadastrados no estoque da sua clínica.',('Abrir estoque','/estoque'))
    if zero:
        if not empty:return result('Nenhum item está esgotado: todos têm saldo positivo. Isso não significa que todos estejam acima do mínimo.',('Conferir estoque','/estoque'))
        groups=[('Esgotados — saldo zero',empty)]
        intro='Há um item esgotado.' if len(empty)==1 else f'Há {len(empty)} itens esgotados.'
    elif healthy:
        groups=[('Com saldo adequado',good)]
        intro=f"Itens com saldo adequado: {len(good)} de {len(items)}. Eles têm saldo positivo e estão acima do mínimo cadastrado."
    elif critical:
        if not empty and not low:return result('Nenhum item precisa de reposição pelo mínimo cadastrado. Todos têm saldo positivo e estão acima do mínimo.',('Conferir estoque','/estoque'))
        groups=[('Esgotados — saldo zero',empty),('No mínimo ou abaixo dele — ainda há saldo',low)]
        total=len(empty)+len(low)
        intro=(f'{total} itens precisam de reposição' if total>1 else 'Um item precisa de reposição')+f': {len(empty)} com saldo zero e {len(low)} no mínimo ou abaixo dele.'
    else:
        groups=[('Esgotados — saldo zero',empty),('No mínimo ou abaixo dele',low),('Com saldo adequado',good)]
        intro=f"O estoque tem {len(items)} itens cadastrados: {len(empty)} com saldo zero, {len(low)} no mínimo ou abaixo dele e {len(good)} com saldo adequado."
    lines=[intro];shown=0;total=sum(len(rows) for _,rows in groups)
    for heading,rows in groups:
        if not rows or shown>=12:continue
        lines.append('\n'+heading+':')
        for item in rows[:12-shown]:
            quantity,minimum=item['quantidade'],item['minimo']
            short=max(0,minimum-quantity)
            line=f"• {item['nome']}: {amount(quantity,item['unidade'])}; mínimo {amount(minimum,item['unidade'])}."
            if short:line+=(' Falta ' if short==1 else ' Faltam ')+amount(short,item['unidade'])+' para atingir o mínimo.'
            elif quantity==0:line+=' Defina um mínimo para calcular a reposição.'
            elif item['status']=='baixo':line+=' No ponto de reposição: programe a compra antes de uma nova saída.'
            lines.append(line);shown+=1
    if total>shown:lines.append(f'\nMostrei {shown} de {total} itens dessa consulta. Abra o estoque para ver a lista completa.')
    if critical:lines.append('\nA reposição indicada é apenas a diferença até o mínimo cadastrado; nenhuma compra ou entrada foi registrada.')
    return result('\n'.join(lines),('Abrir estoque','/estoque'))

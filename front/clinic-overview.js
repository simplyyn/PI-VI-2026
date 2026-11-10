(async()=>{
 const professionals=document.getElementById('professional-overview'),prices=document.getElementById('clinic-price-list');
 const target=professionals||prices;if(!target)return;
 try{const r=await fetch(professionals?'/api/profissionais':'/api/precos');if(!r.ok)throw Error('Não foi possível consultar os dados.');const rows=await r.json();
 for(const item of rows){const p=document.createElement('p');if(professionals){const days=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];p.textContent=item.nome+' — '+item.especialidades.join(', ')+'. '+Object.entries(item.expediente).map(([day,intervals])=>days[Number(day)]+': '+intervals.map(([a,b])=>a+'–'+b).join(' / ')).join('; ');}else p.textContent=item.procedimento+': '+(item.centavos/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})+' — '+item.unidade;target.append(p);}if(!rows.length)target.textContent=professionals?'Nenhum profissional cadastrado.':'Ainda não há preços próprios definidos. Você pode defini-los pelo assistente, com revisão e confirmação.';
 }catch(error){target.textContent=error.message;}
})();

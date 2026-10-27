(() => {
'use strict';
const detail=document.getElementById('attendance-detail');
const summary=document.getElementById('attendance-summary'),meta=document.getElementById('summary-meta');
const complaint=document.getElementById('complaint-status'),form=document.getElementById('complaint-form');
let selected;
function reviewFields(){const enabled=form.elements.reclamacao.checked;form.elements.categoria.disabled=!enabled;form.elements.motivo.disabled=!enabled;}
form.elements.reclamacao.addEventListener('change',reviewFields);
function plainSummary(text){return text.replace(/\*\*([^*]+)\*\*/g,'$1').replace(/(^|\s)\*\s+/g,' ').replace(/\*([^*]+)\*/g,'$1').replace(/^\s*Resumo(?: do atendimento)?\s*:\s*/i,'').replace(/\b(Solicitação|Ações efetivamente registradas|Desfecho|Pendências)\s*:\s*/g,'').replace(/\s+/g,' ').trim();}
async function api(url,method='GET',data){
 const headers={};if(method!=='GET'){const s=await fetch('/api/session');if(!s.ok)throw Error('Entre novamente no sistema.');headers['X-CSRF-Token']=(await s.json()).csrf_token;headers['Content-Type']='application/json';}
 const r=await fetch(url,{method,headers,...(data===undefined?{}:{body:JSON.stringify(data)})});
 const body=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Não foi possível concluir a análise.');return body;
}
function showSummary(data){
 summary.textContent=data ? plainSummary(data.resumo) : 'Ainda não há resumo. Use o botão Resumo da IA para gerar.';
 meta.textContent=data ? `${data.desatualizado?'Gere novamente para atualizar o resumo.':'Atualizado'} · ${new Date(data.gerado_em).toLocaleString('pt-BR')}` : '';
}
async function load(id){
 selected=String(id);document.getElementById('suggestion-feedback').textContent='';form.hidden=true;summary.textContent='Carregando resumo…';meta.textContent='';complaint.textContent='Carregando classificação…';form.reset();document.getElementById('attendance-guidance').textContent='Use a orientação inicial para consultar o próximo passo a partir do assunto deste atendimento.';
 try{const [s,list,categories]=await Promise.all([api(`/api/atendimentos/${id}/resumo`),api('/api/reclamacoes'),api('/api/reclamacoes/categorias')]);
 if(selected!==String(id))return;
 form.hidden=false;showSummary(s.resumo);const select=form.elements.categoria;select.replaceChildren();for(const c of categories){const option=document.createElement('option');option.value=c.categoria;option.textContent=c.rotulo;select.append(option);}
 const c=list.find(c=>String(c.attendance_id)===String(id));complaint.textContent=c ? (c.reclamacao?`${c.rotulo}: ${c.motivo}`:'Analisado: sem reclamação identificada.')+` (origem: ${c.origem})` : 'Ainda não analisado.';
 if(c){form.elements.reclamacao.checked=c.reclamacao;form.elements.motivo.value=c.motivo;if(c.categoria)select.value=c.categoria;}
 reviewFields();
 }catch(e){if(selected===String(id)){summary.textContent=e.message;complaint.textContent=e.message;}}
}
document.addEventListener('attendance-selected',e=>load(e.detail.id));
document.addEventListener('click',async e=>{
 const button=e.target.closest('button[data-action]');if(!button||!['summary','classify','suggest-ai','guidance'].includes(button.dataset.action)||button.disabled||!selected)return;
 if(button.dataset.action==='guidance'){
  button.disabled=true;const id=selected;const target=document.getElementById('attendance-guidance');target.textContent='Consultando orientação…';
  try{const answer=await api(`/api/atendimentos/${id}/sugestao`,'POST');if(selected===id)target.textContent=answer.resposta;}
  catch(error){if(selected===id)target.textContent=error.message;}finally{button.disabled=false;}return;
 }
 if(button.dataset.action==='suggest-ai'){
  button.disabled=true;const id=selected;const input=document.getElementById('human-message-form').elements.texto;const previous=input.value;
  try{const answer=await api(`/api/atendimentos/${id}/sugestao`,'POST');if(selected!==id)return;
    const feedback=document.getElementById('suggestion-feedback');
    if(answer.tipo==='sem_contexto'){feedback.textContent=answer.resposta;return;}
    if(input.value!==previous){feedback.textContent='Seu rascunho foi preservado. Sugestão: '+answer.resposta;return;}
    input.value=answer.resposta;
    const sources=(answer.fontes||[]).map(s=>s.titulo).join('; ');
    feedback.textContent='Sugestão baseada na última mensagem do cliente. Revise antes de enviar.'+(sources?' Fontes: '+sources:'');
  }
  catch(error){if(selected===id)document.getElementById('suggestion-feedback').textContent=error.message;}finally{button.disabled=false;}return;
 }
 const id=selected;button.disabled=true;const target=button.dataset.action==='summary'?summary:complaint;target.textContent='Analisando…';
 try{const result=await api(`/api/atendimentos/${id}/`+(button.dataset.action==='summary'?'resumo':'reclamacao/classificar'),'POST');if(selected!==id)return;if(button.dataset.action==='summary')showSummary(result);else await load(id);}
 catch(e){if(selected===id)target.textContent=e.message;}
 finally{button.disabled=false;}
});
form.addEventListener('submit',async e=>{e.preventDefault();if(!selected)return;const id=selected;const button=form.querySelector('button');button.disabled=true;
 try{await api(`/api/atendimentos/${id}/reclamacao`,'PUT',{reclamacao:form.elements.reclamacao.checked,categoria:form.elements.reclamacao.checked?form.elements.categoria.value:null,motivo:form.elements.reclamacao.checked?form.elements.motivo.value.trim():''});if(selected===id)await load(id);}catch(e){if(selected===id)complaint.textContent=e.message;}finally{button.disabled=false;}
});
if(detail.dataset.id)load(detail.dataset.id);
})();

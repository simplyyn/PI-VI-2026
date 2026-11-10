(() => {
'use strict';
const detail=document.getElementById('attendance-detail');
const summary=document.getElementById('attendance-summary'),meta=document.getElementById('summary-meta');
const modal=document.getElementById('summary-dialog');
let selected, summaryRequest=0;
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
document.getElementById('summary-close').onclick=()=>modal.close();
async function loadSummary(generate=false){
 const id=selected, version=++summaryRequest;
 summary.textContent='Carregando resumo...';meta.textContent='';
 const refresh=document.getElementById('summary-refresh');refresh.disabled=true;
 try{const data=generate?await api(`/api/atendimentos/${id}/resumo`,'POST'):(await api(`/api/atendimentos/${id}/resumo`)).resumo;
 if(version===summaryRequest&&selected===id)showSummary(data);
 }catch(error){if(version===summaryRequest&&selected===id)summary.textContent=error.message;}
 finally{if(version===summaryRequest)refresh.disabled=false;}
}
document.getElementById('summary-refresh').onclick=()=>loadSummary(true);
document.addEventListener('attendance-selected',e=>{selected=String(e.detail.id);summaryRequest++;modal.close();document.getElementById('suggestion-feedback').textContent='';});
document.addEventListener('click',async e=>{
 const button=e.target.closest('button[data-action]');if(!button||!['summary','classify','suggest-ai','guidance'].includes(button.dataset.action)||button.disabled||!selected)return;
 if(button.dataset.action==='summary'){modal.showModal();await loadSummary();return;}
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
});
if(detail.dataset.id)selected=detail.dataset.id;
})();

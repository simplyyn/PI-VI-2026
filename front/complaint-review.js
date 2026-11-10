(() => {
'use strict';
const select=document.getElementById('complaint-attendance'), form=document.getElementById('complaint-form'), status=document.getElementById('complaint-status');
if(!select)return;
const classify=document.querySelector('[data-action=classify]');
async function api(url,method='GET',data){
 const headers={};if(method!=='GET'){const r=await fetch('/api/session');if(!r.ok)throw Error('Entre novamente.');headers['X-CSRF-Token']=(await r.json()).csrf_token;headers['Content-Type']='application/json';}
 const r=await fetch(url,{method,headers,...(data===undefined?{}:{body:JSON.stringify(data)})});const body=await r.json();if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Não foi possível analisar.');return body;
}
function fields(){form.elements.categoria.disabled=form.elements.motivo.disabled=!form.elements.reclamacao.checked;}
async function load(){
 const id=select.value;form.hidden=!id;classify.disabled=!id;status.textContent='';form.reset();fields();if(!id)return;
 try{const rows=await api('/api/reclamacoes');if(select.value!==id)return;const c=rows.find(c=>String(c.attendance_id)===id);status.textContent=c?(c.reclamacao?`${c.rotulo}: ${c.motivo}`:'Sem reclamação identificada.'):'Ainda não analisado.';if(c){form.elements.reclamacao.checked=c.reclamacao;form.elements.motivo.value=c.motivo||'';if(c.categoria)form.elements.categoria.value=c.categoria;fields();}}
 catch(error){status.textContent=error.message;}
}
select.onchange=load;form.elements.reclamacao.onchange=fields;
classify.onclick=async()=>{const id=select.value;if(!id)return;classify.disabled=true;select.disabled=true;status.textContent='Analisando...';try{await api(`/api/atendimentos/${id}/reclamacao/classificar`,'POST');await load();}catch(error){status.textContent=error.message;}finally{classify.disabled=false;select.disabled=false;}};
form.onsubmit=async e=>{e.preventDefault();const id=select.value;if(!id)return;const button=form.querySelector('button');button.disabled=true;select.disabled=true;try{await api(`/api/atendimentos/${id}/reclamacao`,'PUT',{reclamacao:form.elements.reclamacao.checked,categoria:form.elements.reclamacao.checked?form.elements.categoria.value:null,motivo:form.elements.reclamacao.checked?form.elements.motivo.value.trim():''});await load();status.textContent+=' Revisão salva. Recarregue a página para atualizar os gráficos.';}catch(error){status.textContent=error.message;}finally{button.disabled=false;select.disabled=false;}};
(async()=>{classify.disabled=true;form.hidden=true;try{const [rows,categories]=await Promise.all([api('/api/atendimentos'),api('/api/reclamacoes/categorias')]);for(const r of rows){const o=document.createElement('option');o.value=r.id;o.textContent=r.cliente+' — '+r.preview;select.append(o);}for(const c of categories){const o=document.createElement('option');o.value=c.categoria;o.textContent=c.rotulo;form.elements.categoria.append(o);}}catch(error){status.textContent=error.message;}})();
})();

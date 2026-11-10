(() => {
'use strict';
let batch=null,busy=false;
const feedback=document.getElementById('batch-feedback'),area=document.getElementById('batch-items');
const pendingArea=document.getElementById('pending-conversations'),preview=document.getElementById('batch-preview');
const send=document.getElementById('send-replies'),prepare=document.getElementById('prepare-replies');

async function api(path,method='GET',data){
 const headers={};
 if(method!=='GET'){
  const session=await fetch('/api/session');if(!session.ok)throw Error('Entre novamente.');
  headers['X-CSRF-Token']=(await session.json()).csrf_token;headers['Content-Type']='application/json';
 }
 const response=await fetch(path,{method,headers,...(data?{body:JSON.stringify(data)}:{})});
 const body=await response.json().catch(()=>({}));
 if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Não foi possível concluir.');
 return body;
}

function renderPending(data){
 document.getElementById('pending-count').textContent=`${data.conversas} conversas · ${data.mensagens} mensagens aguardando resposta`;
 pendingArea.replaceChildren();
 for(const item of data.itens||[]){
  const card=document.createElement('article');card.className='chart-card';card.style.marginBottom='16px';
  const title=document.createElement('h3');title.textContent=item.cliente;
  const info=document.createElement('p');info.textContent=`${item.mensagens_pendentes} mensagem(ns) sem resposta · aguardando desde ${new Date(item.desde).toLocaleString('pt-BR')}`;
  const message=document.createElement('p');message.textContent=item.ultima_mensagem;message.style.whiteSpace='pre-wrap';
  const link=document.createElement('a');link.className='link-more';link.href='/atendimentos?atendimento_id='+encodeURIComponent(item.id);link.textContent='Abrir conversa';
  card.append(title,info,message,link);pendingArea.append(card);
 }
 if(!data.itens?.length){const empty=document.createElement('p');empty.textContent='Nenhuma conversa aguardando resposta.';pendingArea.append(empty);}
 prepare.disabled=busy||!data.conversas;
}

async function refreshPending(){const data=await api('/api/pendencias');renderPending(data);return data;}

function renderDraft(draft){
 batch=draft;area.replaceChildren();const items=Array.isArray(draft.items)?draft.items:[];
 const ready=draft.state==='ready'&&items.length>0;
 preview.hidden=!items.length;send.hidden=!ready;send.disabled=!ready;
 for(const item of items){
  const card=document.createElement('section');card.className='chart-card';card.dataset.id=item.id;card.style.marginBottom='16px';
  const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!item.texto&&!item.erro;check.disabled=!ready;
  label.append(check,document.createTextNode(' '+item.cliente));
  const received=document.createElement('p');received.textContent='Última mensagem: '+item.ultima_mensagem;
  const text=document.createElement('textarea');text.value=item.texto;text.maxLength=4000;text.rows=5;text.disabled=!ready;text.style.cssText='width:100%;box-sizing:border-box;padding:12px;font:inherit;';text.setAttribute('aria-label','Resposta para '+item.cliente);
  const status=document.createElement('p');status.className='batch-status';status.textContent=item.erro||'Sugestão: revise antes de enviar.';
  card.append(label,received,text,status);area.append(card);
 }
 feedback.textContent=draft.state==='generating'?'A prévia ainda está sendo preparada. Aguarde e abra novamente o lote.':ready?'Prévia pronta. Revise os textos e selecione quais enviar. Nenhuma mensagem enviada.':'O lote não contém respostas para revisar.';
}

prepare.onclick=async()=>{
 if(busy)return;busy=true;prepare.disabled=send.disabled=true;feedback.textContent='Preparando sugestões, uma conversa por vez…';
 try{renderDraft(await api('/api/respostas/lotes','POST'));}
 catch(error){feedback.textContent=error.message;}
 finally{busy=false;prepare.disabled=false;send.disabled=send.hidden;}
};

send.onclick=async()=>{
 if(busy||!batch||batch.state!=='ready')return;
 const items=[...area.children].filter(c=>c.querySelector('input').checked&&!c.querySelector('input').disabled).map(c=>({id:Number(c.dataset.id),texto:c.querySelector('textarea').value.trim()}));
 if(!items.length||items.some(i=>!i.texto)){feedback.textContent='Selecione respostas e preencha os textos.';return;}
 if(!confirm(`Enviar ${items.length} resposta(s) revisada(s) pelo portal?`))return;
 busy=true;send.disabled=prepare.disabled=true;
 try{
  const result=await api(`/api/respostas/lotes/${batch.id}/enviar`,'POST',{confirmado:true,items});
  for(const item of result.resultados){
   const card=area.querySelector(`[data-id="${item.id}"]`);
   card.querySelector('.batch-status').textContent=item.status==='enviado'?'Enviada pelo portal.':item.status==='ja_enviado'?'Essa resposta já havia sido enviada.':item.erro;
   if(['enviado','ja_enviado'].includes(item.status)){card.querySelector('input').checked=false;card.querySelector('input').disabled=true;card.querySelector('textarea').disabled=true;}
  }
  feedback.textContent=`${result.enviados} resposta(s) enviada(s). Confira os resultados individuais.`;
  await refreshPending();
  send.hidden=![...area.children].some(c=>!c.querySelector('input').disabled);
 }catch(error){feedback.textContent=error.message;}
 finally{busy=false;send.disabled=send.hidden;prepare.disabled=false;}
};

(async()=>{
 send.hidden=true;send.disabled=true;preview.hidden=true;
 let pendingLoaded=false;
 try{
  await refreshPending();pendingLoaded=true;
  const id=new URLSearchParams(location.search).get('lote');
  if(id&&/^\d+$/.test(id))renderDraft(await api('/api/respostas/lotes/'+id));
  else feedback.textContent='Você pode abrir uma conversa ou preparar sugestões para até cinco pendências.';
 }catch(error){feedback.textContent=error.message;if(!pendingLoaded){document.getElementById('pending-count').textContent='Não foi possível consultar as pendências.';pendingArea.textContent='Atualize a página para tentar novamente.';}}
})();
})();

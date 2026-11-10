'use strict';
let customerBusy=false,customerVersion='',retryMessage=null,customerInitialized=false;
const customerFeedback=document.getElementById('customer-feedback');
async function customerApi(path,method='GET',data){
 const headers={};if(method!=='GET'){const r=await fetch('/api/session');if(!r.ok)throw Error('Entre novamente no sistema.');headers['X-CSRF-Token']=(await r.json()).csrf_token;headers['Content-Type']='application/json';}
 const r=await fetch(path,{method,headers,...(data?{body:JSON.stringify(data)}:{})});const body=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Não foi possível concluir.');return body;
}
function renderCustomer(data){
 const confirmation=document.getElementById('booking-confirmation');confirmation.hidden=data.acao?.estado!=='aguardando_confirmacao';
 if(!customerInitialized){document.getElementById('customer-auto').checked=data.status!=='escalated';customerInitialized=true;}
 const signature=JSON.stringify(data);if(signature===customerVersion)return;customerVersion=signature;
 const area=document.getElementById('demo-messages'),nearBottom=area.scrollHeight-area.scrollTop-area.clientHeight<100;area.replaceChildren();
 if(!data.mensagens.length){const p=document.createElement('p');p.textContent='Olá! Pergunte sobre procedimentos, preços e horários, ou peça para agendar uma avaliação.';area.append(p);}
 for(const m of data.mensagens){const group=document.createElement('div');group.className='demo-msg-group';const bubble=document.createElement('div');bubble.className='demo-msg '+(m.autor==='client'?'user-msg':'ai-msg');const text=document.createElement('div');text.className='demo-msg-bubble';text.style.whiteSpace='pre-wrap';text.textContent=m.texto;const when=document.createElement('small');when.className='demo-msg-time';when.textContent=({client:'Você',human:'Equipe da clínica',ai:'Assistente'}[m.autor]||'Sistema')+' · '+new Date(m.criado_em).toLocaleString('pt-BR');bubble.append(text,when);group.append(bubble);area.append(group);}
 if(nearBottom||customerBusy)area.scrollTop=area.scrollHeight;
 const appointments=document.getElementById('customer-appointments');appointments.replaceChildren();for(const a of data.agendamentos||[]){const p=document.createElement('p');p.textContent=`${a.data} ${a.horario.slice(0,5)} — ${a.procedimento} — ${a.dentista} (${a.status})`;appointments.append(p);}if(!data.agendamentos?.length)appointments.textContent='Nenhum agendamento registrado.';
}
async function refreshCustomer(){if(customerBusy||document.hidden)return;try{renderCustomer(await customerApi('/api/cliente/conversa'));}catch(error){customerFeedback.textContent=error.message;}}
async function enviarMensagem(){
 const input=document.getElementById('demo-input'),text=input.value.trim();if(!text||customerBusy)return;
 if(!retryMessage||retryMessage.texto!==text)retryMessage={texto:text,request_id:crypto.randomUUID(),resposta_automatica:document.getElementById('customer-auto').checked};
 customerBusy=true;const button=document.querySelector('.demo-input-bar button');button.disabled=true;input.disabled=true;customerFeedback.textContent='Registrando mensagem...';
 try{const data=await customerApi('/api/cliente/mensagens','POST',retryMessage);renderCustomer(data);input.value='';retryMessage=null;customerFeedback.textContent=data.aviso||'Mensagem registrada.';}
 catch(error){customerFeedback.textContent=error.message+' Seu texto foi preservado. Se tentar novamente, o envio não será duplicado.';}
 finally{customerBusy=false;button.disabled=false;input.disabled=false;input.focus();}
}
function toggleDark(){document.documentElement.classList.toggle('dark');localStorage.setItem('smartdent-dark',document.documentElement.classList.contains('dark')?'1':'0');}
document.getElementById('confirm-booking').onclick=()=>{if(customerBusy)return;document.getElementById('demo-input').value='confirmar';enviarMensagem();};
document.getElementById('cancel-booking').onclick=()=>{if(customerBusy)return;document.getElementById('demo-input').value='cancelar';enviarMensagem();};
document.getElementById('customer-auto').addEventListener('change',async event=>{if(!event.target.checked)return;try{renderCustomer(await customerApi('/api/cliente/retomar','POST',{}));customerFeedback.textContent='Assistente automático retomado. Você pode enviar sua próxima pergunta.';}catch(error){event.target.checked=false;customerFeedback.textContent=error.message;}});
window.lucide?.createIcons();refreshCustomer();setInterval(refreshCustomer,4000);

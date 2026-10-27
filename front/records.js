(() => {
'use strict';
const resource=document.getElementById('records-root').dataset.resource;
const records=JSON.parse(document.getElementById('records-data').textContent);
const map=new Map(records.map(r=>[String(r.id),r]));
const dialog=document.getElementById('crud-dialog'), form=document.getElementById('crud-form'), fields=document.getElementById('crud-fields'), error=document.getElementById('crud-error'), feedback=document.getElementById('crud-feedback');
let mode, id, selected, busy=false, statusFilter='todos';
const definitions={
 pacientes:[['nome','Nome','text',true,200],['telefone','Telefone','text',false,40],['email','E-mail','email',false,254],['status','Status',['novo','ativo','inativo']],['plano','Plano / Convênio','text',false,100],['ultima_consulta','Última consulta','date'],['proxima_consulta','Próxima consulta','date'],['procedimentos','Quantidade de procedimentos','number',true,1000000000]],
 agendamentos:[['paciente_id','Paciente','patient',true],['data','Data','date',true],['horario','Horário','time',true],['duracao','Duração em minutos','number',true,1440],['procedimento','Procedimento','text',true,200],['dentista','Dentista','text',true,200],['status','Status',['pendente','confirmado','cancelado']]],
 atendimentos:[['cliente','Nome do cliente','text',true,200],['preview','Assunto / Solicitação','textarea',true,2000],['status','Status',['pending','resolved','escalated']],['canal','Canal',['human','ai']]]
};
async function api(path,method='GET',data) {
 const headers={};
 if(method!=='GET') {const s=await fetch('/api/session');if(!s.ok)throw Error('Sua sessão expirou. Entre novamente.'); headers['X-CSRF-Token']=(await s.json()).csrf_token;headers['Content-Type']='application/json';}
 const r=await fetch(path,{method,headers,...(data===undefined?{}:{body:JSON.stringify(data)})});
 if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(Array.isArray(d.detail)?d.detail.map(e=>`${e.loc.at(-1)}: ${e.msg}`).join('; '):d.detail||'Não foi possível concluir a operação.');}
 return r.status===204?null:r.json();
}
function payload(record){const d={};for(const [key] of definitions[resource])d[key]=record[key];return d;}
async function open(action,identifier,patientId) {
 mode=action;id=identifier;error.textContent='';fields.replaceChildren();const record=action==='edit' ? map.get(identifier)||{} : {};
 document.getElementById('crud-title').textContent=(action==='edit'?'Editar':'Cadastrar')+' '+({pacientes:'paciente',agendamentos:'agendamento',atendimentos:'atendimento'}[resource]);
 let patients=[];if(resource==='agendamentos'){patients=await api('/api/pacientes');if(!patients.length)throw Error('Cadastre um paciente antes de criar um agendamento.');}
 for(const [key,label,type,required,max] of definitions[resource]) {
  const wrapper=document.createElement('label');wrapper.textContent=label;
  const select=Array.isArray(type)||type==='patient';const input=document.createElement(select?'select':type==='textarea'?'textarea':'input');input.name=key;input.required=!!required;
  if(select){const options=type==='patient'?patients.map(p=>[p.id,p.nome]):type.map(v=>[v,v]);for(const [value,text] of options){const o=document.createElement('option');o.value=value;o.textContent=text;input.append(o);}}
  else if(type!=='textarea')input.type=type;
  if(type==='number'){input.min=key==='duracao'?'1':'0';input.max=max;input.step='1';}
  else if(max)input.maxLength=max;
  if(record[key]!=null)input.value=record[key];else if(key==='paciente_id'&&patientId)input.value=patientId;else if(key==='procedimentos')input.value=0;else if(key==='duracao')input.value=30;
  wrapper.append(input);fields.append(wrapper);
 }
 dialog.showModal();fields.querySelector('input,select,textarea').focus();
}
form.addEventListener('submit',async event=>{
 event.preventDefault();if(busy)return;const data={};
 for(const field of fields.querySelectorAll('input,select,textarea')){data[field.name]=field.type==='number'||field.name==='paciente_id'?Number(field.value):field.value.trim();if(['ultima_consulta','proxima_consulta'].includes(field.name)&&!field.value)data[field.name]=null;if(field.required&&data[field.name]===''){error.textContent='Preencha os campos obrigatórios.';return;}}
 busy=true;document.getElementById('crud-save').disabled=true;
 try{await api('/api/'+resource+(mode==='edit'?'/'+id:''),mode==='edit'?'PUT':'POST',data);location.reload();}catch(e){error.textContent=e.message;}finally{busy=false;document.getElementById('crud-save').disabled=false;}
});
document.getElementById('crud-cancel').onclick=()=>{if(!busy)dialog.close();};dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
function selectAttendance(identifier){
 selected=identifier;const r=map.get(identifier);if(!r)return;
 document.getElementById('attendance-detail').hidden=false;document.getElementById('attendance-name').textContent=r.cliente;document.getElementById('attendance-subject').textContent=r.preview;
 const area=document.getElementById('attendance-messages');area.replaceChildren();
 for(const m of r.mensagens||[]){const row=document.createElement('div');row.className='message-row';const text=document.createElement('p');text.className='message-bubble';text.textContent=m.texto;const when=document.createElement('small');when.textContent='Atendente humano · '+new Date(m.criado_em).toLocaleString('pt-BR');row.append(text,when);area.append(row);}
 if(!r.mensagens?.length)area.textContent='Nenhuma mensagem registrada.';
 document.querySelectorAll('.conv-item').forEach(el=>el.classList.toggle('active',el.dataset.id===identifier));
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('button[data-action]');if(!button||button.disabled)return;const action=button.dataset.action;const identifier=button.closest('[data-id]')?.dataset.id||selected;
 try{
  if(action==='create'||action==='edit'){await open(action,identifier);return;}
  if(action==='select'){selectAttendance(identifier);return;}
  if(action==='schedule'){location.href='/agendamentos?paciente_id='+encodeURIComponent(identifier);return;}
  if(action==='ai-info'){feedback.textContent='Resumo e sugestão por IA dependem da integração com um modelo real. Essa função ainda não está disponível.';return;}
  if(action==='filter'){const search=document.getElementById('records-search');search.scrollIntoView({behavior:'smooth',block:'center'});search.focus({preventScroll:true});return;}
  if(action==='clear-filter'){document.getElementById('agenda-date').value='';document.getElementById('records-search').value='';document.getElementById('records-filter').value='todos';statusFilter='todos';filter();calendar();return;}
  if(action==='previous-month'||action==='next-month'){month.setMonth(month.getMonth()+(action==='next-month'?1:-1));calendar();return;}
  if(action==='history'){const history=await api('/api/agendamentos');const entries=history.filter(a=>String(a.paciente_id)===identifier);feedback.textContent=entries.length?entries.map(a=>`${a.data} ${a.horario.slice(0,5)} — ${a.procedimento} (${a.status})`).join(' | '):'Nenhum agendamento registrado para esse paciente.';return;}
  if(action==='export'){const data=JSON.stringify(records,null,2);const url=URL.createObjectURL(new Blob([data],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='pacientes.json';link.click();URL.revokeObjectURL(url);return;}
  if(action==='delete'){if(!confirm('Excluir este registro definitivamente?'))return;button.disabled=true;await api('/api/'+resource+'/'+identifier,'DELETE');location.reload();return;}
  const record=map.get(identifier);if(!record)return;
  if(['confirm','cancel','escalate','resolve'].includes(action)){if(action==='cancel'&&!confirm('Cancelar esta consulta?'))return;button.disabled=true;const data=payload(record);data.status={confirm:'confirmado',cancel:'cancelado',escalate:'escalated',resolve:'resolved'}[action];if(action==='escalate')data.canal='human';await api('/api/'+resource+'/'+identifier,'PUT',data);location.reload();}
 }catch(e){feedback.textContent=e.message;button.disabled=false;}
});
const messageForm=document.getElementById('human-message-form');
messageForm?.addEventListener('submit',async event=>{event.preventDefault();if(!selected)return;const input=messageForm.elements.texto;const text=input.value.trim();if(!text)return;const button=messageForm.querySelector('button[type=submit]');button.disabled=true;try{const updated=await api('/api/atendimentos/'+selected+'/mensagens','POST',{texto:text});map.set(selected,updated);input.value='';selectAttendance(selected);}catch(e){feedback.textContent=e.message;}finally{button.disabled=false;}});
function filter(){const query=(document.getElementById('records-search')||document.getElementById('searchPacientes')).value.toLocaleLowerCase('pt-BR');const date=document.getElementById('agenda-date')?.value;for(const el of document.querySelectorAll('[data-id]')){const r=map.get(el.dataset.id);const text=[r.nome,r.telefone,r.cliente,r.preview,r.paciente,r.dentista,r.procedimento].filter(Boolean).join(' ').toLocaleLowerCase('pt-BR');el.hidden=!text.includes(query)||(statusFilter!=='todos'&&r.status!==statusFilter)||(!!date&&r.data!==date);}const empty=document.getElementById('records-empty');if(empty)empty.hidden=[...document.querySelectorAll('[data-id]')].some(el=>!el.hidden);}
(document.getElementById('records-search')||document.getElementById('searchPacientes')).addEventListener('input',filter);
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelector('.filter-tab.active')?.classList.remove('active');b.classList.add('active');statusFilter=b.dataset.filter;filter();}));
document.getElementById('records-filter')?.addEventListener('change',e=>{statusFilter=e.target.value;filter();});
// Escolher a data no campo leva o calendário até o mês dela e marca o dia.
document.getElementById('agenda-date')?.addEventListener('change',e=>{const [y,m]=e.target.value.split('-').map(Number);if(y&&m)month.setFullYear(y,m-1,1);filter();calendar();});
const month=new Date();month.setDate(1);
const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
function calendar(){const area=document.getElementById('calDays');if(!area)return;area.replaceChildren();const title=month.toLocaleDateString('pt-BR',{month:'long',year:'numeric'});document.getElementById('calendar-title').textContent=title[0].toUpperCase()+title.slice(1);const input=document.getElementById('agenda-date');const today=iso(new Date());for(let i=0;i<month.getDay();i++)area.append(document.createElement('div'));const count=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();for(let day=1;day<=count;day++){const button=document.createElement('button');button.type='button';button.className='cal-day';button.textContent=day;const date=iso(new Date(month.getFullYear(),month.getMonth(),day));const total=records.filter(r=>r.data===date).length;if(total){button.classList.add('has-apt');button.title=total+(total===1?' consulta':' consultas');}if(date===today)button.classList.add('today');if(date===input.value){button.classList.add('selected');button.setAttribute('aria-pressed','true');}
 // Clicar no dia já selecionado remove o filtro de data.
 button.onclick=()=>{input.value=input.value===date?'':date;filter();calendar();};area.append(button);}}
calendar();
if(resource==='atendimentos'&&records.length)selectAttendance(String(records[0].id));
if(resource==='agendamentos'){const patientId=new URLSearchParams(location.search).get('paciente_id');if(patientId)open('create',undefined,patientId).catch(e=>feedback.textContent=e.message);}
})();

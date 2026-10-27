window.smartdentAsk = async function (question) {
  const sessionResponse = await fetch('/api/session');
  if (!sessionResponse.ok) throw Error('Sua sessão expirou. Entre novamente.');
  const session = await sessionResponse.json();
  const response = await fetch('/api/chat', {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify({pergunta:question})});
  const data = await response.json().catch(()=>({}));
  if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Não foi possível obter a resposta.');
  const sources = (data.fontes||[]).map(s=>`[${s.id}] ${s.titulo}`).join('; ');
  return data.resposta + (sources ? '\n\nFontes consultadas: '+sources : '');
};
window.smartdentAskOwner = async function(question,context=null) {
  const session=await fetch('/api/session');
  if(!session.ok)throw Error('Sua sessão expirou. Entre novamente.');
  const token=(await session.json()).csrf_token;
  const response=await fetch('/api/assistente',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({pergunta:question,contexto:context})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Não foi possível consultar o assistente. Tente novamente.');
  const sources=(data.fontes||[]).map(s=>`[${s.id}] ${s.titulo}`).join('; ');
  if(sources)data.resposta+='\n\nFontes: '+sources;
  return data;
};

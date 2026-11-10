// Behavior checks without a browser; layout still requires a visual check.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup() {
 const events={},calls=[],elements={};
 for(const id of ['attendance-detail','attendance-summary','summary-meta','summary-dialog','summary-close','summary-refresh','suggestion-feedback'])elements[id]={textContent:'',dataset:{},disabled:false};
 const input={value:''};elements['human-message-form']={elements:{texto:input}};
 const modal=elements['summary-dialog'];modal.open=false;modal.showModal=()=>modal.open=true;modal.close=()=>modal.open=false;
 let suggestion;
 const fetch=async(url,options={})=>{calls.push([url,options.method||'GET']);if(url==='/api/session')return {ok:true,json:async()=>({csrf_token:'fake'})};if(url.endsWith('/sugestao'))return {ok:true,json:async()=>suggestion?await suggestion:({resposta:'Resposta sugerida',fontes:[]})};return {ok:true,json:async()=>({resumo:{resumo:'Resumo salvo',gerado_em:'2030-01-01T00:00:00Z'}})};};
 const document={getElementById:id=>elements[id],addEventListener:(name,fn)=>events[name]=fn};
 vm.runInNewContext(fs.readFileSync('front/attendance-analysis.js','utf8'),{document,fetch,Date});
 return {events,calls,elements,input,modal,setSuggestion:promise=>suggestion=promise,select:id=>events['attendance-selected']({detail:{id}}),click:action=>events.click({target:{closest:()=>({dataset:{action}})}})};
}
(async()=>{
 const env=setup();env.select(1);await env.click('summary');
 assert.equal(env.modal.open,true);assert.equal(env.elements['attendance-summary'].textContent,'Resumo salvo');
 assert.equal(env.calls.some(([,method])=>method==='POST'),false,'Opening a saved summary must not generate again');
 env.modal.close();await env.click('suggest-ai');
 assert.equal(env.input.value,'Resposta sugerida');assert.equal(env.calls.some(([url])=>url.endsWith('/mensagens')),false,'Suggestion must never send a message');
 let resolve;env.setSuggestion(new Promise(r=>resolve=r));const pending=env.click('suggest-ai');env.input.value='Meu rascunho';
 resolve({resposta:'Nova sugestão',fontes:[]});await pending;
 assert.equal(env.input.value,'Meu rascunho');assert.match(env.elements['suggestion-feedback'].textContent,/preservado/);
 let resolveOther;env.setSuggestion(new Promise(r=>resolveOther=r));const other=env.click('suggest-ai');env.select(2);env.input.value='Paciente dois';resolveOther({resposta:'Paciente um',fontes:[]});await other;
 assert.equal(env.input.value,'Paciente dois','Delayed answer must not overwrite another conversation');assert.equal(env.modal.open,false);
 console.log('4 attendance UI behavior checks passed (no visual browser validation).');
})().catch(error=>{console.error(error);process.exitCode=1;});

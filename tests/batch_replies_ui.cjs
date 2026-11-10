const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.style={};this.dataset={};this.textContent='';this.hidden=false;this.disabled=false;this.checked=false;this.value='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 setAttribute(key,value){this[key]=value;}
 querySelector(selector){for(const c of this.children){if(c.tag===selector||selector==='.'+c.className)return c;const found=c.querySelector?.(selector);if(found)return found;}return null;}
}
function setup({search='',state='ready',fail=false}={}){
 const ids={};for(const id of ['pending-count','batch-feedback','batch-items','send-replies','prepare-replies','pending-conversations','batch-preview'])ids[id]=new Element();
 const calls=[],pending={conversas:2,mensagens:3,itens:[{id:7,cliente:'Pedro',mensagens_pendentes:2,desde:'2026-11-10T10:00:00Z',ultima_mensagem:'Qual o preço da limpeza?'},{id:8,cliente:'Ana',mensagens_pendentes:1,desde:'2026-11-10T11:00:00Z',ultima_mensagem:'Quais os horários?'}]};
 const draft={id:3,state,items:state==='ready'?[{id:7,cliente:'Pedro',ultima_mensagem:'Qual o preço?',texto:'A equipe pode confirmar seu orçamento.',erro:''}]:[]};
 const fetch=async(path,options={})=>{calls.push({path,method:options.method||'GET'});return {ok:!fail,json:async()=>fail?{detail:'Sessão expirada'}:path==='/api/pendencias'?pending:path==='/api/session'?{csrf_token:'fake'}:draft};};
 vm.runInNewContext(fs.readFileSync('front/batch-replies.js','utf8'),{document:{getElementById:id=>ids[id],createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})},fetch,location:{search},URLSearchParams,Date,confirm:()=>{throw Error('A confirmação não deveria ser chamada neste cenário');}});
 return {ids,calls};
}
(async()=>{
 const initial=setup();await new Promise(setImmediate);
 assert.equal(initial.ids['pending-conversations'].children.length,2);
 assert.equal(initial.ids['pending-conversations'].children[0].children[0].textContent,'Pedro');
 assert.equal(initial.ids['pending-conversations'].children[0].querySelector('a').href,'/atendimentos?atendimento_id=7');
 assert.equal(initial.ids['send-replies'].hidden,true);assert.equal(initial.ids['send-replies'].disabled,true);
 await initial.ids['send-replies'].onclick();assert.equal(initial.calls.some(c=>c.method==='POST'),false,'Opening the page must not generate or send messages');
 const ready=setup({search:'?lote=3'});await new Promise(setImmediate);
 assert.equal(ready.ids['pending-conversations'].children.length,2);assert.equal(ready.ids['batch-preview'].hidden,false);assert.equal(ready.ids['send-replies'].hidden,false);assert.equal(ready.ids['batch-items'].children[0].querySelector('textarea').value,'A equipe pode confirmar seu orçamento.');
 const generating=setup({search:'?lote=3',state:'generating'});await new Promise(setImmediate);assert.equal(generating.ids['send-replies'].hidden,true);assert.match(generating.ids['batch-feedback'].textContent,/preparada/);
 const failed=setup({fail:true});await new Promise(setImmediate);assert.equal(failed.ids['send-replies'].hidden,true);assert.match(failed.ids['batch-feedback'].textContent,/Sessão expirada/);
 assert.match(fs.readFileSync('front/style.css','utf8'),/\[hidden\]\s*\{\s*display:\s*none\s*!important/,'Global flex styles must not override hidden controls');
 console.log('4 pending-replies UI scenarios passed: list, ready draft, processing and load failure.');
})().catch(error=>{console.error(error);process.exitCode=1;});

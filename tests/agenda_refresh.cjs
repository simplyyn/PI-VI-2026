// Cross-window refresh behavior with a minimal DOM, without browser layout claims.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(){this.listeners={};this.value='';this.dataset={};this.hidden=false;this.children=[];this.open=false;this.textContent='';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 replaceChildren(...children){this.children=children;}
 get childNodes(){return this.children;}
}
const elements={},intervals=[],windowEvents={};
for(const id of ['records-root','records-data','crud-dialog','crud-form','crud-fields','crud-error','crud-feedback','crud-cancel','crud-save','records-search','records-filter','agenda-date','agenda-professional','records-empty'])elements[id]=new Element();
elements['records-root'].dataset.resource='agendamentos';
const original=[{profissional_id:59,id:1,paciente:'Pedro',data:'2026-11-11',horario:'08:00',duracao:30,status:'confirmado'}];
const next=[...original,{profissional_id:59,id:2,paciente:'Pedro',data:'2026-11-17',horario:'08:30',duracao:30,status:'confirmado'},
 {profissional_id:59,id:3,paciente:'Pedro',data:'2026-11-17',horario:'10:00',duracao:30,status:'pendente'},
 {profissional_id:59,id:4,paciente:'Carlos',data:'2026-11-17',horario:'11:00',duracao:30,status:'confirmado'},{profissional_id:58,id:5,paciente:'Pedro',data:'2026-11-17',horario:'15:00',duracao:30,status:'confirmado'}];
elements['records-data'].textContent=JSON.stringify(original);
elements['records-search'].value='Pedro';elements['records-filter'].value='confirmado';elements['agenda-date'].value='2026-11-17';
elements['agenda-professional'].value='59';elements['agenda-professional'].options=[{value:''},{value:'58'},{value:'59'}];
const list=new Element(),metrics=new Element(),subtitle=new Element();
function card(id){const e=new Element();e.dataset.id=String(id);return e;}
list.children=original.map(r=>card(r.id));
const document={hidden:false,getElementById:id=>elements[id]||null,addEventListener:()=>{},
 querySelectorAll:selector=>selector==='[data-id]'?list.children:[],
 querySelector:selector=>({'.agenda-list-panel':list,'.metrics-grid':metrics,'.page-subtitle':subtitle}[selector]||null)};
class DOMParser {parseFromString(){return {
 getElementById:id=>id==='records-data'?{textContent:JSON.stringify(next)}:null,
 querySelector:selector=>selector==='.agenda-list-panel'?{childNodes:next.map(r=>card(r.id))}:selector==='.metrics-grid'?{childNodes:[]}:{textContent:'5 consultas cadastradas'}
 };}}
vm.runInNewContext(fs.readFileSync('front/records.js','utf8'),{document,window:{addEventListener:(name,fn)=>windowEvents[name]=fn},DOMParser,
 sessionStorage:{getItem:()=>null},location:{search:'?profissional_id=59'},URLSearchParams,Date,Map,
 setInterval:(fn,ms)=>{intervals.push({fn,ms});},fetch:async path=>{assert.equal(path,'/agendamentos');return {ok:true,text:async()=>'<rendered agenda>'};}});
(async()=>{
 elements['records-filter'].listeners.change({target:elements['records-filter']});
 assert.equal(intervals.length,1,'Agenda must poll even when no event arrives from this window');
 assert.equal(intervals[0].ms,4000);
 intervals[0].fn();await new Promise(setImmediate);
 assert.equal(elements['agenda-professional'].value,'59');assert.equal(elements['agenda-date'].value,'2026-11-17');assert.equal(elements['records-search'].value,'Pedro');assert.equal(elements['records-filter'].value,'confirmado');
 assert.deepEqual(list.children.filter(c=>!c.hidden).map(c=>c.dataset.id),['2']);
 assert.equal(subtitle.textContent,'5 consultas cadastradas');assert.equal(typeof windowEvents.focus,'function');
 console.log('Agenda polling refreshed external bookings and preserved date, search and status filters.');
})().catch(error=>{console.error(error);process.exitCode=1;});

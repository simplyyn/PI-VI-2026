(() => {
const button=document.getElementById('classify-pending');if(!button)return;
button.addEventListener('click',async()=>{
 button.disabled=true;const feedback=document.getElementById('analysis-feedback');feedback.textContent='Analisando atendimentos pendentes da clínica…';
 try{const session=await fetch('/api/session');if(!session.ok)throw Error('Entre novamente.');const token=(await session.json()).csrf_token;
 const response=await fetch('/api/reclamacoes/classificar?limite=10',{method:'POST',headers:{'X-CSRF-Token':token}});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Não foi possível analisar.');location.reload();}
 catch(e){feedback.textContent=e.message;}finally{button.disabled=false;}
});
})();

(async()=>{
 const target=document.getElementById('llm-usage');if(!target)return;
 try{const response=await fetch('/api/ia/uso');if(!response.ok)throw Error('Não foi possível consultar o consumo registrado.');const data=await response.json();target.textContent=`${data.chamadas_registradas} respostas registradas · ${data.tokens_entrada} tokens de entrada · ${data.tokens_saida} tokens de saída informados. ${data.chamadas_sem_contagem} resposta(s) sem contagem completa. Os valores acumulam desde o início do registro local.`;}
 catch(error){target.textContent=error.message;}
})();

'use strict';
let csrf='';let me=null;
const el=id=>document.getElementById(id);
const show=(id,ok)=>el(id).classList.toggle('hidden',!ok);
const notify=message=>{el('notice').textContent=message};
async function api(path,method='GET',body=null,extra={}){
 const options={method,credentials:'same-origin',headers:{...extra}};
 if(method!=='GET'){options.headers['X-CSRF-Token']=csrf;options.headers['Content-Type']='application/json';options.body=JSON.stringify(body??{})}
 const res=await fetch('/api/v1/'+path,options);let out={};try{out=await res.json()}catch{}
 if(!res.ok)throw new Error(out.error || `Request failed (${res.status})`);return out;
}
async function loadCsrf(){let v=await api('auth/csrf');csrf=v.csrf_token}
async function refreshPatients(){let v=await api('patients');let s=el('patient-select');s.replaceChildren();
 for(let p of v.patients){let o=document.createElement('option');o.value=p.id;o.textContent=`${p.reference} — ${p.display_name}`;s.append(o)}}
async function refreshLearnings(){let v=await api('admin/learnings');let slot=el('learnings');slot.replaceChildren();
 for(let l of v.learnings){let card=document.createElement('div');card.className='card';let h=document.createElement('strong');h.textContent=l.pattern;card.append(h);
 let p=document.createElement('p');p.textContent=`${l.description} — ${l.support} independent jobs — ${l.status}`;card.append(p);
 if(l.status==='suggested'){for(let choice of ['approved','rejected','deferred']){let b=document.createElement('button');b.type='button';b.textContent=choice;b.addEventListener('click',async()=>{try{await api('admin/learnings/'+l.id+'/decision','POST',{decision:choice});await refreshLearnings();notify('Decision recorded')}catch(e){notify(e.message)}});card.append(b)}}slot.append(card)}
}
function authenticated(actor){me=actor;show('login',false);show('workspace',true);el('identity').textContent=actor.name+' · '+actor.role;el('doctor').hidden=actor.role!=='doctor';el('admin').hidden=actor.role!=='admin';if(actor.role==='doctor')refreshPatients().catch(e=>notify(e.message));else refreshLearnings().catch(e=>notify(e.message))}
window.addEventListener('DOMContentLoaded',async()=>{
 try{await loadCsrf();let actor=await api('auth/me');authenticated(actor)}catch{show('login',true)}
 el('login-form').addEventListener('submit',async e=>{e.preventDefault();try{let v=await api('auth/login','POST',{email:el('email').value,password:el('password').value});csrf=v.csrf_token;authenticated(v);notify('Authenticated')}catch(err){notify(err.message)}});
 el('logout').addEventListener('click',async()=>{try{await api('auth/logout','POST');me=null;show('workspace',false);show('login',true);await loadCsrf()}catch(err){notify(err.message)}});
 el('patient-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('patients','POST',{reference:el('patient-ref').value,display_name:el('patient-name').value});await refreshPatients();notify('Patient registered')}catch(err){notify(err.message)}});
 el('report-form').addEventListener('submit',async e=>{e.preventDefault();try{let id=crypto.randomUUID();let uploads=Array.from(el('files').files);let expect=uploads.length>0;
 if(!expect && !el('transcript').value.trim())throw new Error('Enter dictation text or upload audio');
 let result=await api('report-jobs','POST',{patient_id:el('patient-select').value,transcript:el('transcript').value,language_config:el('language').value,expect_uploads:expect},{'Idempotency-Key':id});
 const jid=result.job_id;
 if(expect){
  let audio=0,images=0;
  for(let f of uploads){
   let ext=f.name.split('.').pop().toLowerCase();let kind=['png','jpg','jpeg'].includes(ext)?'image':'audio';
   if((kind==='image' && ++images>5)||(kind==='audio' && ++audio>5))throw new Error('Too many files');
   let mimes={wav:'audio/wav',mp3:'audio/mpeg',m4a:'audio/mp4',webm:'audio/webm',ogg:'audio/ogg',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg'};
   let mime=mimes[ext];if(!mime||f.size>25*1024*1024)throw new Error('Unsupported or oversized file');
   let presigned=await api('report-jobs/'+jid+'/uploads','POST',{kind,content_type:mime});
   let form=new FormData();for(let [k,v] of Object.entries(presigned.upload.fields))form.append(k,v);
   form.append('file',f);
   let up=await fetch(presigned.upload.url,{method:'POST',body:form});
   if(!up.ok)throw new Error('Private upload failed');
   await api('report-jobs/'+jid+'/uploads/'+presigned.asset_id+'/confirm','POST');
  }
  await api('report-jobs/'+jid+'/uploads/complete','POST');
 }
 notify('Queued: '+result.job_id);el('approve-job').value=result.job_id;show('approval-form',true);el('doctor-result').textContent='Awaiting worker processing. Refresh browser / check status before doctor approval.';
 let counter=0;let timer=setInterval(async()=>{counter++;if(counter>60){clearInterval(timer);return}try{let x=await api('report-jobs/'+jid);el('doctor-result').textContent='Report status: '+x.status;if(x.status==='draft_ready'){clearInterval(timer);let a=document.createElement('a');a.href='/api/v1/report-jobs/'+jid+'/draft';a.textContent='Download draft for clinical review';el('doctor-result').append(document.createTextNode(' · '),a)}}catch{clearInterval(timer)}},3000)
 }catch(err){notify(err.message)}});
 el('approval-form').addEventListener('submit',async e=>{e.preventDefault();try{let r=await api('report-jobs/'+el('approve-job').value+'/approve','POST',{final_text:el('final-text').value,attest:el('attest').checked});notify('Doctor approval: '+r.status)}catch(err){notify(err.message)}});
 el('refresh-learnings').addEventListener('click',()=>refreshLearnings().catch(e=>notify(e.message)));
});

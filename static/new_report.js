document.addEventListener('DOMContentLoaded',()=>{
  const sample=document.querySelector('#load-sample');
  if(sample) sample.addEventListener('click',()=>{
    document.querySelector('#transcript').value='Specimen: appendix. Sections reveal acute inflammation and neutrophilic infiltrate. Patient temperature was measured at 102 degrees Fahrenheit. Histopathology finding dictated: acute appendicitis. Please bold acute appendicitis in the report.';
    const select=document.querySelector('#patient_id');
    if(select.options.length>1&&!select.value) select.selectedIndex=1;
  });
  const images=document.querySelector('#images');
  if(images)images.addEventListener('change',()=>{document.querySelector('#file-count').textContent=images.files.length+' image(s) selected';});
  const start=document.querySelector('#record-start'), stop=document.querySelector('#record-stop');
  const status=document.querySelector('#record-status'), input=document.querySelector('#audio_notes');
  let stream,recorder,parts=[];
  const say=text=>{ if(status)status.textContent=text; };
  if(!start||!stop||!input)return;
  if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder){start.disabled=true;say('Microphone capture is not supported in this browser. Upload an audio file instead.');return;}
  start.addEventListener('click',async()=>{
    try{
      if(input.files.length>=5){say('Maximum five voice notes. Remove one before recording.');return;}
      stream=await navigator.mediaDevices.getUserMedia({audio:true});parts=[];
      const preferred=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
      recorder=new MediaRecorder(stream, preferred?{mimeType:preferred}:{});
      recorder.ondataavailable=e=>{if(e.data.size)parts.push(e.data);};
      recorder.onstop=()=>{
        try{
          const mime=recorder.mimeType||'audio/webm';
          const ext=mime.includes('mp4')?'m4a':'webm';
          const blob=new Blob(parts,{type:mime});
          if(blob.size>12*1024*1024){say('Recording exceeds 12MB; please shorten it.');return;}
          const files=new DataTransfer();
          for(const f of input.files)files.items.add(f);
          files.items.add(new File([blob],`voice-note-${Date.now()}.${ext}`,{type:mime}));
          input.files=files.files;
          say(`Recorded note added (${(blob.size/1024).toFixed(0)} KB). ${input.files.length} audio note(s) ready.`);
        }finally{stream?.getTracks().forEach(t=>t.stop()); start.disabled=false;stop.disabled=true;}
      };
      recorder.start(); start.disabled=true;stop.disabled=false;say('Recording microphone… select Stop when finished. Upload only approved evaluation audio.');
    }catch(e){say('Microphone permission failed. You can upload a voice file instead.');stream?.getTracks().forEach(t=>t.stop());start.disabled=false;stop.disabled=true;}
  });
  stop.addEventListener('click',()=>{if(recorder?.state==='recording')recorder.stop();});
});

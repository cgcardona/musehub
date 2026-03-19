"use strict";(()=>{var Ms="/api/v1";function lt(){return localStorage.getItem("musehub_token")??""}function Qe(t){localStorage.setItem("musehub_token",t)}function Cs(){localStorage.removeItem("musehub_token")}function tn(){let t=lt();return t?{Authorization:"Bearer "+t,"Content-Type":"application/json"}:{}}async function te(t,e={}){let n=await fetch(Ms+t,{...e,headers:{...tn(),...e.headers??{}}});if(n.status===401||n.status===403)throw ve("Session expired or invalid token \u2014 please re-enter your JWT."),new Error("auth");if(!n.ok){let o=await n.text();throw new Error(n.status+": "+o)}return n.json()}function ve(t){let e=document.getElementById("token-form"),n=document.getElementById("content");if(e&&(e.style.display="block"),n&&(n.innerHTML=""),t){let o=document.getElementById("token-msg");o&&(o.textContent=t)}}function Hs(){let e=document.getElementById("token-input")?.value.trim()??"";e&&(Qe(e),location.reload())}function en(t){return t?new Date(t).toLocaleString(void 0,{dateStyle:"medium",timeStyle:"short"}):"--"}function Ss(t){if(!t)return"--";let e=(Date.now()-new Date(t).getTime())/1e3;return e<60?"just now":e<3600?Math.floor(e/60)+"m ago":e<86400?Math.floor(e/3600)+"h ago":e<604800?Math.floor(e/86400)+"d ago":en(t)}function Bs(t){return t?t.substring(0,8):"--"}function _s(t){if(!t||isNaN(t))return"--";let e=Math.floor(t/3600),n=Math.floor(t%3600/60),o=Math.floor(t%60);return e>0?`${e}h ${n}m`:n>0?`${n}m ${o}s`:`${o}s`}function be(t){if(isNaN(t))return"0:00";let e=Math.floor(t/60),n=Math.floor(t%60);return`${e}:${n.toString().padStart(2,"0")}`}function ye(t){return t?String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"):""}async function nn(t){if(lt()){let e=document.getElementById("nav-star-btn");e&&(e.style.display="")}}async function As(){let t=document.getElementById("nav-star-icon");t&&(t.textContent=t.textContent==="\u2606"?"\u2605":"\u2606")}var It={playing:!1};function _t(){return document.getElementById("player-audio")}function sn(){return document.getElementById("audio-player")}async function Rs(t){let e=await fetch(t,{headers:{Authorization:"Bearer "+lt()}});if(!e.ok)throw new Error(String(e.status));let n=await e.blob();return URL.createObjectURL(n)}async function Ps(t,e,n){let o=sn(),s=_t();if(!o||!s)return;o.style.display="flex",document.body.classList.add("player-open");let i=document.getElementById("player-title"),r=document.getElementById("player-repo");i&&(i.textContent=e||"Now Playing"),r&&(r.textContent=n||"");try{let a=await Rs(t),l=s;l._blobUrl&&URL.revokeObjectURL(l._blobUrl),l._blobUrl=a,s.src=a}catch{s.src=t}s.load(),s.play().catch(()=>{}),It.playing=!0,ee()}function Ds(){let t=_t();t?.src&&(It.playing?(t.pause(),It.playing=!1):(t.play().catch(()=>{}),It.playing=!0),ee())}function Ns(t){let e=_t();!e||!e.duration||(e.currentTime=t/100*e.duration)}function Fs(){let t=sn(),e=_t();if(t&&(t.style.display="none"),document.body.classList.remove("player-open"),e){e.pause();let n=e;n._blobUrl&&(URL.revokeObjectURL(n._blobUrl),n._blobUrl=void 0),e.src=""}It.playing=!1,ee()}async function js(t,e){let n=await fetch(t,{headers:{Authorization:"Bearer "+lt()}});if(!n.ok)return;let o=await n.blob(),s=URL.createObjectURL(o),i=document.createElement("a");i.href=s,i.download=e,i.click(),URL.revokeObjectURL(s)}function Os(){let t=_t();if(!t?.duration)return;let e=t.currentTime/t.duration*100,n=document.getElementById("player-seek"),o=document.getElementById("player-current");n&&(n.value=String(e)),o&&(o.textContent=be(t.currentTime))}function zs(){let t=_t(),e=document.getElementById("player-duration");t&&e&&(e.textContent=be(t.duration))}function Us(){It.playing=!1,ee();let t=document.getElementById("player-seek");t&&(t.value="0");let e=document.getElementById("player-current");e&&(e.textContent="0:00")}function ee(){let t=document.getElementById("player-toggle");t&&(t.innerHTML=It.playing?"&#9646;&#9646;":"&#9654;")}var qs={feat:{label:"feat",color:"var(--color-success)"},fix:{label:"fix",color:"var(--color-danger)"},refactor:{label:"refactor",color:"var(--color-accent)"},style:{label:"style",color:"var(--color-purple)"},docs:{label:"docs",color:"var(--text-muted)"},chore:{label:"chore",color:"var(--color-neutral)"},init:{label:"init",color:"var(--color-warning)"},perf:{label:"perf",color:"var(--color-orange)"}};function Ws(t){if(!t)return{type:null,scope:null,subject:t??""};let e=t.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.*)/s);return e?{type:e[1].toLowerCase(),scope:e[2]??null,subject:e[3]}:{type:null,scope:null,subject:t}}function Gs(t){if(!t)return"";let e=qs[t]??{label:t,color:"var(--text-muted)"};return`<span class="badge" style="background:${e.color}20;color:${e.color};border:1px solid ${e.color}40">${ye(e.label)}</span>`}function Ys(t){return t?`<span class="badge" style="background:var(--bg-overlay);color:var(--color-purple);border:1px solid var(--color-purple-bg)">${ye(t)}</span>`:""}function Xs(t){let e={},n=[/section:([\w-]+)/i,/track:([\w-]+)/i,/key:([\w#b]+\s*(?:major|minor|maj|min)?)/i,/tempo:(\d+)/i,/bpm:(\d+)/i],o=["section","track","key","tempo","bpm"];return n.forEach((s,i)=>{let r=t.match(s);r&&(e[o[i]]=r[1])}),e}var Vs=["\u{1F525}","\u2764\uFE0F","\u{1F44F}","\u2728","\u{1F3B5}","\u{1F3B8}","\u{1F3B9}","\u{1F941}"];async function on(t,e,n){let o=document.getElementById(n);if(!o)return;let s=window.__repoId,i=[];try{i=await te("/repos/"+s+"/reactions?target_type="+encodeURIComponent(t)+"&target_id="+encodeURIComponent(e))}catch{i=[]}let r={},a={};(Array.isArray(i)?i:[]).forEach(g=>{r[g.emoji]=g.count,a[g.emoji]=g.reacted_by_me});let l=t.replace(/'/g,""),c=String(e).replace(/'/g,""),m=n.replace(/'/g,"");o.innerHTML='<div class="reaction-bar">'+Vs.map(g=>{let d=r[g]??0,p=a[g]?" reaction-btn--active":"",u=d>0?'<span class="reaction-count">'+d+"</span>":"";return'<button class="reaction-btn'+p+`" onclick="toggleReaction('`+l+"','"+c+"','"+g+"','"+m+`')" title="`+g+'">'+g+u+"</button>"}).join("")+"</div>"}async function Js(t,e,n,o){if(!lt()){ve("Sign in to react");return}let s=window.__repoId;try{await te("/repos/"+s+"/reactions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target_type:t,target_id:String(e),emoji:n})}),await on(t,e,o)}catch{}}document.addEventListener("htmx:configRequest",t=>{let e=lt();e&&(t.detail.headers.Authorization="Bearer "+e)});function Ks(){return document.getElementById("repo-header")?.getAttribute("data-repo-id")??null}async function Zs(){if(lt())try{let t=await te("/notifications"),e=Array.isArray(t)?t.filter(o=>!o.is_read).length:0,n=document.getElementById("nav-notif-badge");n&&(n.textContent=e>99?"99+":String(e),n.style.display=e>0?"flex":"none")}catch{}}function an(){if(lt()){let n=document.getElementById("signout-btn");n&&(n.style.display="")}Zs(),typeof window.lucide=="object"&&window.lucide.createIcons();let t=Ks();t&&nn(t);let e=document.getElementById("page-data");if(e)try{let n=JSON.parse(e.textContent??"{}");Qs(n)}catch{}}function Qs(t){let e=t.page;if(!e)return;let n=window.MusePages;n&&typeof n[e]=="function"&&n[e](t)}document.addEventListener("DOMContentLoaded",an);document.addEventListener("htmx:afterSettle",an);window.getToken=lt;window.setToken=Qe;window.clearToken=Cs;window.saveToken=Hs;window.showTokenForm=ve;window.apiFetch=te;window.authHeaders=tn;window.fmtDate=en;window.fmtRelative=Ss;window.shortSha=Bs;window.fmtDuration=_s;window.fmtSeconds=be;window.escHtml=ye;window.initRepoNav=nn;window.toggleStar=As;window.queueAudio=Ps;window.togglePlay=Ds;window.seekAudio=Ns;window.closePlayer=Fs;window.downloadArtifact=js;window.onTimeUpdate=Os;window.onMetadata=zs;window.onAudioEnded=Us;window.parseCommitMessage=Ws;window.commitTypeBadge=Gs;window.commitScopeBadge=Ys;window.parseCommitMeta=Xs;window.loadReactions=on;window.toggleReaction=Js;var to=[.5,.75,1,1.25,1.5,2];function ne(t){if(!isFinite(t)||t<0)return"0:00";let e=Math.floor(t/60),n=Math.floor(t%60);return e+":"+(n<10?"0":"")+n}var he=class t{_ws=null;_opts;_autoPlay=!1;constructor(e){this._opts=e}static init(e){let n=new t(e);return n._setup(),n}_setup(){let e=this,n=this._opts;this._ws=WaveSurfer.create({container:n.waveformEl,waveColor:"#4a5568",progressColor:"#1f6feb",cursorColor:"#58a6ff",height:80,barWidth:2,barGap:1}),this._ws.on("ready",()=>{let o=e._ws.getDuration();n.timeDurEl&&(n.timeDurEl.textContent=ne(o)),n.playBtnEl&&(n.playBtnEl.disabled=!1),e._autoPlay&&(e._autoPlay=!1,e._ws.play())}),this._ws.on("play",()=>{n.playBtnEl&&(n.playBtnEl.innerHTML="&#9646;&#9646;")}),this._ws.on("pause",()=>{n.playBtnEl&&(n.playBtnEl.innerHTML="&#9654;")}),this._ws.on("finish",()=>{n.playBtnEl&&(n.playBtnEl.innerHTML="&#9654;")}),this._ws.on("timeupdate",o=>{n.timeCurEl&&(n.timeCurEl.textContent=ne(o))}),this._ws.on("region-update",o=>{let s=o;n.loopInfoEl&&(n.loopInfoEl.textContent="Loop: "+ne(s.start)+" \u2013 "+ne(s.end),n.loopInfoEl.style.display=""),n.loopBtnEl&&(n.loopBtnEl.style.display="")}),this._ws.on("region-clear",()=>{n.loopInfoEl&&(n.loopInfoEl.style.display="none"),n.loopBtnEl&&(n.loopBtnEl.style.display="none")}),this._ws.on("error",o=>{if(n.waveformEl){let s=document.createElement("p");s.style.cssText="color:#f85149;padding:16px;margin:0;",s.textContent="\u274C Audio unavailable: "+String(o),n.waveformEl.appendChild(s)}}),n.playBtnEl&&(n.playBtnEl.disabled=!0,n.playBtnEl.addEventListener("click",()=>e._ws.playPause())),n.speedSelEl&&(to.forEach((o,s)=>{let i=document.createElement("option");i.value=String(o),i.textContent=o+"x",s===2&&(i.selected=!0),n.speedSelEl.appendChild(i)}),n.speedSelEl.addEventListener("change",function(){e._ws.setPlaybackRate(parseFloat(this.value))})),n.loopBtnEl&&(n.loopBtnEl.style.display="none",n.loopBtnEl.addEventListener("click",()=>e._ws.clearRegion())),n.loopInfoEl&&(n.loopInfoEl.style.display="none"),n.volSliderEl&&n.volSliderEl.addEventListener("input",function(){e._ws.setVolume(parseFloat(this.value))}),document.addEventListener("keydown",o=>{let s=o.target?.tagName??"";if(!(s==="INPUT"||s==="TEXTAREA"||s==="SELECT")){if(o.code==="Space")o.preventDefault(),e._ws.playPause();else if(o.code==="KeyL")e._ws.clearRegion();else if(o.code==="ArrowLeft"){let i=Math.max(0,e._ws.getCurrentTime()-5),r=e._ws.getDuration();r>0&&e._ws.seekTo(i/r)}else if(o.code==="ArrowRight"){let i=e._ws.getCurrentTime()+5,r=e._ws.getDuration();r>0&&e._ws.seekTo(Math.min(1,i/r))}}})}load(e,n=!1){this._autoPlay=n,this._opts.playBtnEl&&(this._opts.playBtnEl.disabled=!0),this._opts.timeCurEl&&(this._opts.timeCurEl.textContent="0:00"),this._opts.timeDurEl&&(this._opts.timeDurEl.textContent="0:00"),this._ws.load(e)}destroy(){this._ws&&(this._ws.destroy(),this._ws=null)}};window.AudioPlayer=he;var se=["#58a6ff","#3fb950","#f0883e","#bc8cff","#ff7b72","#79c0ff","#56d364","#ffa657","#d2a8ff","#ffa198"],eo=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];function rn(t){let e=Math.floor(t/12)-1;return eo[t%12]+e}function ln(t){let e=t%12;return e===1||e===3||e===6||e===8||e===10}var G=36,cn=21,dn=108;function we(t){return t==null?"":String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}function no(t,e,n={}){let o=t.tracks??[],s=t.tempo_bpm??120,i=t.time_signature??"4/4",r=t.total_beats??0,a=n.selectedTrack??-1,l=[];if(o.forEach(k=>{(a===-1||k.track_id===a)&&(k.notes??[]).forEach(_=>l.push(_))}),l.length===0){e.innerHTML='<p style="color:var(--text-muted);padding:16px;">No MIDI notes found.</p>';return}let c=Math.max(cn,l.reduce((k,_)=>Math.min(k,_.pitch),127)-2),m=Math.min(dn,l.reduce((k,_)=>Math.max(k,_.pitch),0)+2),g=m-c+1;e.innerHTML=so(t,o,a,r,s,i);let d=e.querySelector("#piano-roll-outer"),p=e.querySelector("#piano-canvas"),u=document.querySelector(".piano-roll-tooltip");if(!d||!p)return;let v=d,h=p,L=60,$=14,y=0,C=0,x=!1,M=0,N=0,A=window.devicePixelRatio||1;function O(){return v.clientWidth||800}function J(){return Math.min(Math.max(g*$+40,200),600)}function z(){let k=O(),_=J();v.style.height=_+"px",h.width=k*A,h.height=_*A,h.style.width=k+"px",h.style.height=_+"px"}function B(k,_){return 20+(m-k-C)*$}function gt(k,_){return G+(k-y)*L}function q(){let k=O(),_=J(),T=h.getContext("2d");if(!T)return;T.setTransform(A,0,0,A,0,0),T.clearRect(0,0,k,_);let K=k-G;T.fillStyle="#0d1117",T.fillRect(0,0,k,_);for(let E=c;E<=m;E++){let H=B(E,_);T.fillStyle=ln(E)?"#131820":"#0d1117",T.fillRect(G,H,K,$),E%12===0&&(T.fillStyle="#1f2937",T.fillRect(G,H,K,1))}let Et=K/L,zt=Math.floor(y),X=Math.ceil(y+Et+1),b=L<8?8:L<20?4:L<40?2:1;for(let E=zt;E<=X;E+=b){let H=gt(E,K),I=E%4===0;T.strokeStyle=I?"#30363d":"#1a2030",T.lineWidth=I?1:.5,T.beginPath(),T.moveTo(H,20),T.lineTo(H,_),T.stroke(),I&&H>=G&&(T.fillStyle="#8b949e",T.font="9px monospace",T.fillText(String(E),H+2,14))}l.forEach(E=>{let H=gt(E.start_beat,K),I=gt(E.start_beat+E.duration_beats,K),V=B(E.pitch,_),j=Math.max(I-H-1,2),at=Math.max($-1,3);if(I<G||H>k)return;let Q=se[E.track_id%se.length],rt=.4+E.velocity/127*.6;T.globalAlpha=rt,T.fillStyle=Q,T.fillRect(Math.max(H,G),V+1,j,at),T.globalAlpha=rt*.8,T.fillStyle="#ffffff",T.fillRect(Math.max(H,G),V+1,j,1),T.globalAlpha=1});for(let E=c;E<=m;E++){let H=B(E,_),I=ln(E);T.fillStyle=I?"#1a1a1a":"#e6edf3",T.fillRect(0,H+1,I?G*.65:G-1,Math.max($-1,2)),!I&&E%12===0&&(T.fillStyle="#58a6ff",T.font="9px monospace",T.fillText(rn(E),2,H+$-2))}T.fillStyle="#161b22",T.fillRect(G,0,K,20),T.fillStyle="#0d1117",T.fillRect(0,0,G,20),T.fillStyle="#8b949e",T.font="10px monospace",T.fillText(s.toFixed(1)+" BPM  "+i,G+6,13)}let ft=e.querySelector("#zoom-x"),St=e.querySelector("#zoom-y"),vt=e.querySelector("#track-sel");ft?.addEventListener("input",function(){L=parseInt(this.value,10),z(),q()}),St?.addEventListener("input",function(){$=parseInt(this.value,10),z(),q()}),vt?.addEventListener("change",function(){a=parseInt(this.value,10),l=[],o.forEach(k=>{(a===-1||k.track_id===a)&&(k.notes??[]).forEach(_=>l.push(_))}),l.length>0&&(c=Math.max(cn,l.reduce((k,_)=>Math.min(k,_.pitch),127)-2),m=Math.min(dn,l.reduce((k,_)=>Math.max(k,_.pitch),0)+2),g=m-c+1),z(),q()}),h.addEventListener("mousedown",k=>{x=!0,M=k.clientX,N=k.clientY,v.classList.add("panning")}),window.addEventListener("mousemove",k=>{if(x){let _=k.clientX-M,T=k.clientY-N;y=Math.max(0,y-_/L),C=Math.max(0,C-T/$),M=k.clientX,N=k.clientY,q()}else et(k)}),window.addEventListener("mouseup",()=>{x=!1,v.classList.remove("panning")}),h.addEventListener("mouseleave",()=>{u&&(u.style.display="none")});function et(k){if(!u)return;let _=h.getBoundingClientRect(),T=k.clientX-_.left,K=k.clientY-_.top;if(T<G||K<20){u.style.display="none";return}let Et=y+(T-G)/L,zt=m-Math.floor((K-20)/$)-Math.round(C),X=l.find(b=>b.pitch===zt&&b.start_beat<=Et&&b.start_beat+b.duration_beats>=Et);if(!X){u.style.display="none";return}u.innerHTML="<strong>"+rn(X.pitch)+"</strong> (MIDI "+X.pitch+")<br>Beat: "+X.start_beat.toFixed(2)+"<br>Duration: "+X.duration_beats.toFixed(2)+" beats<br>Velocity: "+X.velocity+"<br>Track: "+X.track_id+" / Ch "+X.channel,u.style.display="block",u.style.left=k.clientX+14+"px",u.style.top=k.clientY-10+"px"}window.addEventListener("resize",()=>{z(),q()}),z(),q()}function so(t,e,n,o,s,i){let r='<option value="-1">All tracks</option>'+e.map(l=>{let c=l.track_id===n?" selected":"";return'<option value="'+l.track_id+'"'+c+">"+we(l.name??"Track "+l.track_id)+" ("+(l.notes??[]).length+" notes)</option>"}).join(""),a=e.map(l=>'<div class="track-legend-item"><div class="track-legend-swatch" style="background:'+se[l.track_id%se.length]+'"></div>'+we(l.name??"Track "+l.track_id)+"</div>").join("");return'<div class="piano-roll-wrapper"><div class="piano-roll-controls"><label>Track: <select id="track-sel">'+r+'</select></label><label>H-Zoom: <input type="range" id="zoom-x" min="4" max="200" value="60" style="width:80px"></label><label>V-Zoom: <input type="range" id="zoom-y" min="4" max="40" value="14" style="width:60px"></label><span style="font-size:12px;color:#8b949e;margin-left:auto">'+o.toFixed(1)+" beats &bull; "+s.toFixed(1)+" BPM &bull; "+we(i)+'</span></div><div id="piano-roll-outer"><canvas id="piano-canvas"></canvas></div><div class="track-legend">'+a+"</div></div>"}var oo={render:no};window.PianoRoll=oo;function io(t){let e=document.getElementById("clone-input");document.querySelectorAll("[data-clone-tab]").forEach(n=>{n.addEventListener("click",()=>{document.querySelectorAll("[data-clone-tab]").forEach(o=>o.classList.remove("active")),n.classList.add("active"),e&&(e.value=t[n.dataset.cloneTab]??"")})})}function ao(){let t=document.getElementById("clone-copy-btn"),e=document.getElementById("clone-input");!t||!e||t.addEventListener("click",()=>{navigator.clipboard.writeText(e.value).then(()=>{let n=t.innerHTML;t.innerHTML="\u2713 Copied!",t.classList.add("clone-copy-flash"),setTimeout(()=>{t.innerHTML=n,t.classList.remove("clone-copy-flash")},1800)})})}function ro(){let t=document.getElementById("nav-star-btn"),e=document.getElementById("stat-stars");[t,e].forEach(n=>{n?.addEventListener("click",o=>{o.preventDefault();let s=window;typeof s.toggleStar=="function"&&s.toggleStar()})})}function nt(t){let e=t.repo_id;e&&typeof window.initRepoNav=="function"&&window.initRepoNav(String(e)),t.clone_musehub!==void 0&&(io({musehub:t.clone_musehub??"",https:t.clone_https??"",ssh:t.clone_ssh??""}),ao()),ro()}var lo=[{id:"blank",icon:"\u{1F4DD}",title:"Blank Issue",description:"Start with a clean slate.",body:""},{id:"bug",icon:"\u{1F41B}",title:"Bug Report",description:"Something isn't working as expected.",body:`## What happened?


## Steps to reproduce

1. 
2. 
3. 

## Expected behaviour


## Actual behaviour

`},{id:"feature",icon:"\u2728",title:"Feature Request",description:"Suggest a new musical idea or capability.",body:`## Summary


## Motivation


## Proposed approach

`},{id:"arrangement",icon:"\u{1F3B5}",title:"Arrangement Issue",description:"Track needs musical arrangement work.",body:`## Track / Section


## Current arrangement


## Desired arrangement


## Musical context

`},{id:"theory",icon:"\u{1F3BC}",title:"Music Theory",description:"Related to harmony, rhythm, or theory decisions.",body:`## Theory concern


## Affected section / instrument


## Suggested resolution

`}],st=new Set;function co(){let t=document.getElementById("create-issue-panel"),e=document.getElementById("template-picker");!t||!e||(e.style.display="",t.style.display="none")}function mo(t){let e=lo.find(r=>r.id===t);if(!e)return;let n=document.getElementById("issue-body");n&&(n.value=e.body);let o=document.getElementById("template-picker");o&&(o.style.display="none");let s=document.getElementById("create-issue-panel");s&&(s.style.display="");let i=document.getElementById("issue-title");i&&i.focus()}function uo(t,e){e?st.add(t):st.delete(t),mn()}function mn(){let t=document.getElementById("bulk-toolbar"),e=document.getElementById("bulk-count");if(!t||!e)return;let n=st.size;n>0?(t.classList.add("visible"),e.textContent=n===1?"1 issue selected":`${n} issues selected`):t.classList.remove("visible")}function po(){st.clear(),document.querySelectorAll(".issue-row-check").forEach(t=>{t.checked=!1}),mn()}function go(){st.size>0&&confirm(`Close ${st.size} issue(s)?`)&&location.reload()}function fo(){st.size>0&&confirm(`Reopen ${st.size} issue(s)?`)&&location.reload()}function vo(){if(!document.getElementById("bulk-label-select")?.value){alert("Please select a label first.");return}st.size>0&&location.reload()}function bo(){if(!document.getElementById("bulk-milestone-select")?.value){alert("Please select a milestone first.");return}st.size>0&&location.reload()}function un(t){nt(t),document.querySelectorAll("[data-filter-select]").forEach(n=>{n.addEventListener("change",()=>n.closest("form")?.requestSubmit())});let e=document.querySelector("[data-search-input]");if(e){let n;e.addEventListener("input",()=>{clearTimeout(n),n=setTimeout(()=>e.closest("form")?.requestSubmit(),300)})}document.addEventListener("change",n=>{let o=n.target.closest("[data-issue-toggle]");o&&uo(o.dataset.issueToggle,o.checked)}),document.addEventListener("click",n=>{let o=n.target.closest("[data-bulk-action]");if(!o)return;let s=o.dataset.bulkAction;s==="assign-label"?vo():s==="assign-milestone"?bo():s==="close"?go():s==="reopen"?fo():s==="deselect"&&po()}),document.addEventListener("click",n=>{let o=n.target.closest("[data-action]");if(!o)return;let s=o.dataset.action;if(s==="show-template-picker")co();else if(s==="hide-template-picker"){let i=document.getElementById("template-picker");i&&(i.style.display="none")}else if(s==="select-template"){let i=o.dataset.templateId;i&&mo(i)}})}function yo(t,e){let n=document.getElementById(t),o=document.getElementById(e);if(!n||!o)return;let s=n.querySelector(".tag-text-input");if(!s)return;let i=o.value?o.value.split(",").filter(Boolean):[];function r(){n.querySelectorAll(".tag-pill").forEach(a=>a.remove()),i.forEach(a=>{let l=document.createElement("span");l.className="tag-pill",l.textContent=a+" ";let c=document.createElement("button");c.type="button",c.className="tag-pill-remove",c.textContent="\xD7",c.addEventListener("click",()=>{i=i.filter(m=>m!==a),r()}),l.appendChild(c),n.insertBefore(l,s)}),o.value=i.join(",")}s.addEventListener("keydown",a=>{if(a.key==="Enter"||a.key===","){a.preventDefault();let l=s.value.trim().replace(/,/g,"");l&&!i.includes(l)&&(i.push(l),r()),s.value=""}else a.key==="Backspace"&&s.value===""&&i.length>0&&(i.pop(),r())}),n.addEventListener("click",()=>s.focus()),r()}function ho(){document.querySelectorAll(".visibility-card").forEach(t=>{let e=t;e.addEventListener("click",()=>{document.querySelectorAll(".visibility-card").forEach(o=>{o.setAttribute("aria-checked","false"),o.classList.remove("selected")}),e.setAttribute("aria-checked","true"),e.classList.add("selected");let n=e.querySelector("input[type=radio]");n&&(n.checked=!0)}),e.addEventListener("keydown",n=>{(n.key==="Enter"||n.key===" ")&&e.click()})})}async function wo(t){t.preventDefault();let e=document.getElementById("submit-btn"),n=document.getElementById("submit-error");n&&(n.style.display="none");let o=document.getElementById("f-owner").value.trim(),s=document.getElementById("f-name").value.trim(),i=document.getElementById("f-description").value.trim(),r=document.getElementById("f-license").value||null,a=document.getElementById("f-branch"),l=a&&a.value.trim()||"main",c=document.getElementById("f-initialize").checked,m=document.querySelector('input[name="visibility"]:checked'),g=m?m.value:"private",d=document.querySelector(".wizard-layout"),p=d?._x_dataStack?.[0]?[...d._x_dataStack[0].topics]:[];e&&(e.disabled=!0,e.textContent="Creating\u2026");try{let u=window,v=typeof u.getToken=="function"?u.getToken():"";if(!v){typeof u.showTokenForm=="function"&&u.showTokenForm("Sign in to create a repository.");return}let h=await fetch("/new",{method:"POST",headers:{Authorization:"Bearer "+v,"Content-Type":"application/json"},body:JSON.stringify({owner:o,name:s,description:i,visibility:g,license:r,topics:p,tags:[],initialize:c,defaultBranch:l})});if(h.status===401||h.status===403){typeof u.showTokenForm=="function"&&u.showTokenForm("Session expired \u2014 re-enter your JWT.");return}let L=await h.json();if(h.status===201){window.location.href=L.redirect;return}n&&(n.textContent="\u274C "+(L.detail||"Failed to create repository."),n.style.display="")}catch(u){n&&(n.textContent="\u274C "+(u instanceof Error?u.message:String(u)),n.style.display="")}finally{e&&(e.disabled=!1,e.textContent="Create repository")}}function pn(t){yo("tag-input-container","tags-hidden"),ho(),document.getElementById("wizard-form")?.addEventListener("submit",n=>{wo(n)})}function xo(){let t=document.getElementById("play-btn"),e=document.getElementById("stop-btn");t&&t.addEventListener("click",()=>{let n=window.PianoRoll;n?.play&&n.play()}),e&&e.addEventListener("click",()=>{let n=window.PianoRoll;n?.stop&&n.stop()})}async function Eo(t){let e=document.getElementById("piano-canvas");if(!e||window.PianoRoll?.init)return;let o=e.dataset.midiUrl,s=e.dataset.path??null,i=window.apiFetch;if(i)try{let r=document.getElementById("piano-roll-outer");if(s){let l=((await i("/repos/"+encodeURIComponent(t)+"/objects?limit=500")).objects??[]).find(c=>c.path===s);l&&typeof window.renderFromObjectId=="function"&&window.renderFromObjectId(t,l.objectId,r)}else o&&typeof window.renderFromUrl=="function"&&window.renderFromUrl(o,r)}catch{}}async function gn(t){nt(t),xo(),t.repo_id&&await Eo(String(t.repo_id))}var R=null,ht={};function xe(t){if(!isFinite(t)||t<0)return"0:00";let e=Math.floor(t/60),n=Math.floor(t%60);return e+":"+(n<10?"0":"")+n}function $o(t){return t<1024?t+" B":t<1048576?(t/1024).toFixed(0)+" KB":(t/1048576).toFixed(1)+" MB"}function To(t,e){let n=t?t.charCodeAt(t.length-1):0,o=[];for(let s=0;s<16;s++)o.push(Math.round(20+Math.abs(Math.sin((n+s*7)*.8))*45));return o.map(s=>`<div class="track-waveform-bar" style="height:${s}%"></div>`).join("")}function Io(){Object.values(ht).forEach(t=>{t.paused||t.pause()}),document.querySelectorAll(".track-play-btn").forEach(t=>{t.innerHTML="&#9654;",t.classList.remove("is-playing")}),document.querySelectorAll(".track-row").forEach(t=>t.classList.remove("is-playing"))}function Lo(t,e){return`
  <div class="listen-player-card">
    <div class="listen-player-title">Full Mix</div>
    <div class="listen-player-sub">Master render \u2014 all tracks combined</div>
    <div class="listen-controls">
      <button id="mix-play-btn" class="listen-play-btn" disabled title="Play / Pause">&#9654;</button>
      <div class="listen-progress-wrap">
        <div id="mix-progress-bar" class="listen-progress-bar">
          <div id="mix-progress-fill" class="listen-progress-fill"></div>
        </div>
        <div class="listen-time-row">
          <span id="mix-time-cur">0:00</span>
          <span id="mix-time-dur">\u2014</span>
        </div>
      </div>
    </div>
    <div class="listen-actions">
      <a href="${t}" download class="btn btn-secondary btn-sm">&#8595; Download</a>
    </div>
  </div>`}function ko(t){R=new Audio,R.preload="metadata";let e=document.getElementById("mix-play-btn"),n=document.getElementById("mix-progress-fill"),o=document.getElementById("mix-progress-bar"),s=document.getElementById("mix-time-cur"),i=document.getElementById("mix-time-dur");e&&(R.addEventListener("canplay",()=>{e.disabled=!1}),R.addEventListener("timeupdate",()=>{let r=R.duration?R.currentTime/R.duration*100:0;n&&(n.style.width=r+"%"),s&&(s.textContent=xe(R.currentTime))}),R.addEventListener("durationchange",()=>{i&&(i.textContent=xe(R.duration))}),R.addEventListener("ended",()=>{e.innerHTML="&#9654;",n&&(n.style.width="0%"),R.currentTime=0}),R.addEventListener("error",()=>{e.disabled=!0,e.title="Audio unavailable"}),e.addEventListener("click",()=>{Io(),R.paused?(R.src=t,R.play(),e.innerHTML="&#9646;&#9646;"):(R.pause(),e.innerHTML="&#9654;")}),o&&o.addEventListener("click",r=>{if(!R.duration)return;let a=o.getBoundingClientRect();R.currentTime=(r.clientX-a.left)/a.width*R.duration}))}function Mo(t){return t.map(e=>{let n=CSS.escape(e.path),o=e.durationSec?xe(e.durationSec):"\u2014",s=e.size?$o(e.size):"",i=To(e.objectId??e.path,!1);return`
    <div class="track-row" id="track-row-${n}">
      <button class="track-play-btn" id="track-btn-${n}"
              onclick="window._listenPlayTrack(${JSON.stringify(e.path)}, ${JSON.stringify(e.url)}, 'track-btn-${n}', 'track-row-${n}')">&#9654;</button>
      <div class="track-info">
        <div class="track-name">${window.escHtml?window.escHtml(e.name):e.name}</div>
        <div class="track-path">${window.escHtml?window.escHtml(e.path):e.path}</div>
      </div>
      <div class="track-waveform">${i}</div>
      <div class="track-meta">${o}${s?" \xB7 "+s:""}</div>
      <div class="track-row-actions">
        <a class="btn btn-secondary btn-sm" href="${e.url}" download title="Download">&#8595;</a>
      </div>
    </div>`}).join("")}function Co(t,e,n,o){if(R&&!R.paused){R.pause();let a=document.getElementById("mix-play-btn");a&&(a.innerHTML="&#9654;")}Object.keys(ht).forEach(a=>{if(a!==t&&!ht[a].paused){ht[a].pause();let l=document.getElementById("track-row-"+CSS.escape(a));l&&l.classList.remove("is-playing");let c=document.getElementById("track-btn-"+CSS.escape(a));c&&(c.innerHTML="&#9654;",c.classList.remove("is-playing"))}}),ht[t]||(ht[t]=new Audio,ht[t].preload="metadata");let s=ht[t],i=document.getElementById(n),r=document.getElementById(o);s.paused?(s.src=e,s.play(),i&&(i.innerHTML="&#9646;&#9646;",i.classList.add("is-playing")),r&&r.classList.add("is-playing"),s.addEventListener("ended",()=>{i&&(i.innerHTML="&#9654;",i.classList.remove("is-playing")),r&&r.classList.remove("is-playing")},{once:!0})):(s.pause(),i&&(i.innerHTML="&#9654;",i.classList.remove("is-playing")),r&&r.classList.remove("is-playing"))}async function fn(t){nt(t);let e=String(t.repo_id??""),n=t.ref??"main",o=t.api_base??`/api/v1/musehub/repos/${encodeURIComponent(e)}`;window._listenPlayTrack=Co;let s=document.getElementById("content");if(s){s.innerHTML='<p class="loading">Loading audio tracks\u2026</p>';try{let i=window.apiFetch;if(!i)return;let r;try{r=await i(o.replace("/api/v1/musehub","")+"/listen/"+encodeURIComponent(n)+"/tracks")}catch{r={hasRenders:!1,tracks:[],fullMixUrl:null,ref:n,repoId:e}}if(!r.hasRenders||r.tracks.length===0){s.innerHTML=`
      <div class="no-renders-card">
        <span class="no-renders-icon">\u{1F3B5}</span>
        <div class="no-renders-title">No audio renders yet</div>
        <div class="no-renders-sub">Push a commit with .wav, .mp3, .flac, or .ogg files to see them here.</div>
      </div>`;return}let a="";r.fullMixUrl&&(a+=Lo(r.fullMixUrl,"Full Mix")),a+=`<div class="card"><div class="track-list">${Mo(r.tracks)}</div></div>`,s.innerHTML=a,r.fullMixUrl&&ko(r.fullMixUrl)}catch(i){s.innerHTML=`<p class="error">Failed to load: ${i instanceof Error?i.message:String(i)}</p>`}}}function Ho(){let t=document.querySelectorAll(".cd-dim-row");if(!t.length)return;let e=new IntersectionObserver(n=>{n.forEach(o=>{if(!o.isIntersecting)return;let s=o.target,i=s.querySelector(".cd-dim-fill"),r=s.dataset.target??"0";i&&(i.style.width="0",requestAnimationFrame(()=>{i.style.width=`${r}%`})),e.unobserve(s)})},{threshold:.2});t.forEach(n=>{let o=n.querySelector(".cd-dim-fill");o&&(o.style.width="0"),e.observe(n)})}function So(){document.addEventListener("click",async t=>{let e=t.target.closest("[data-sha]");if(!e)return;let n=e.dataset.sha;if(n)try{await navigator.clipboard.writeText(n);let o=e.textContent??"";e.textContent="\u2713",setTimeout(()=>{e.textContent=o},1500)}catch{}})}function Bo(t){return isFinite(t)?`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,"0")}`:"\u2014"}function _o(t){let e=document.getElementById("cd-waveform"),n=document.getElementById("cd-play-btn"),o=document.getElementById("cd-time");if(e)if(window.WaveSurfer){e.innerHTML='<div id="ws-inner" style="height:64px;width:100%"></div>';let s=window.WaveSurfer.create({container:"#ws-inner",waveColor:"var(--color-accent)",progressColor:"#388bfd",height:64,normalize:!0,backend:"MediaElement"});s.load(t),s.on("audioprocess",()=>{o&&(o.textContent=Bo(s.getCurrentTime()))}),s.on("finish",()=>{n&&(n.textContent="\u25B6")}),s.on("error",()=>{e.innerHTML='<span style="color:var(--color-danger);font-size:var(--font-size-sm)">\u26A0 Could not load audio.</span>'}),n&&n.addEventListener("click",()=>{s.playPause(),n.textContent=s.isPlaying()?"\u23F8":"\u25B6"})}else e.innerHTML=`<audio controls preload="none" style="width:100%"><source src="${t}" /></audio>`,n&&(n.style.display="none")}function vn(){Ho(),So();let t=window.__commitCfg;t?.audioUrl&&_o(t.audioUrl)}var w,F=null,ot=null,hn=[],wn=0,qt=!1,Wt=new Set(["mp3","ogg","wav","flac","m4a"]),Ee=new Set(["webp","png","jpg","jpeg","gif"]),$e=new Set(["mid","midi"]),Te=new Set(["abc","musicxml","xml","mxl"]),Ie=new Set(["json","yaml","yml","toml"]),Ao={harmonic:"\u{1F3B5}",rhythmic:"\u{1F941}",melodic:"\u{1F3BC}",structural:"\u{1F3D7}\uFE0F",dynamic:"\u{1F4E2}"};function f(t){return window.escHtml(t)}function Y(t,e){return window.apiFetch(t,e)}function xn(t){return window.fmtDate(t)}function En(t){return window.fmtRelative(t)}function Ro(t,e){navigator.clipboard.writeText(t).then(()=>{let n=e.textContent??"";e.textContent="\u2713",setTimeout(()=>{e.textContent=n},1500)}).catch(()=>{})}function Po(){let t=window.getToken();if(!t)return null;try{return JSON.parse(atob(t.split(".")[1].replace(/-/g,"+").replace(/_/g,"/"))).sub||null}catch{return null}}function $n(t){let e=0;for(let n=0;n<t.length;n++)e=t.charCodeAt(n)+((e<<5)-e);return`hsl(${Math.abs(e)%360},55%,45%)`}function Tn(t){let e=f((t||"?").charAt(0).toUpperCase());return`<span class="comment-avatar" style="background:${$n(t||"")}">${e}</span>`}function bn(t){if(!isFinite(t))return"\u2014";let e=Math.floor(t/60),n=String(Math.floor(t%60)).padStart(2,"0");return`${e}:${n}`}function In(t){wn=t,qt=!1;let e=hn[t],n=document.getElementById("iap-waveform"),o=document.getElementById("iap-play-btn"),s=document.querySelector("#inline-player-root .iap-title");if(s&&(s.textContent=e.name),o&&(o.textContent="\u25B6"),F){try{F.destroy()}catch{}F=null}if(ot&&(ot.pause(),ot=null),n&&(n.innerHTML='<div class="iap-waveform-placeholder">\u{1F3B5} Loading\u2026</div>'),window.WaveSurfer){n&&(n.innerHTML='<div id="iap-ws-container" style="height:72px;width:100%"></div>'),F=window.WaveSurfer.create({container:"#iap-ws-container",waveColor:"#30363d",progressColor:"#1f6feb",height:72,normalize:!0,backend:"MediaElement",fetchParams:{headers:window.authHeaders()}}),F.load(e.url),F.on("ready",()=>{let r=document.getElementById("iap-duration");r&&(r.textContent=bn(F.getDuration()))}),F.on("audioprocess",()=>{let r=document.getElementById("iap-current-time"),a=document.getElementById("iap-progress-fill"),l=F.getCurrentTime()/(F.getDuration()||1)*100;r&&(r.textContent=bn(F.getCurrentTime())),a&&(a.style.width=l+"%")}),F.on("finish",()=>{qt=!1;let r=document.getElementById("iap-play-btn");r&&(r.textContent="\u25B6")}),F.on("error",()=>{n&&(n.innerHTML='<div class="iap-waveform-placeholder" style="color:var(--color-danger)">\u26A0 Could not load audio.</div>')});let i=document.getElementById("iap-volume");i&&F.setVolume(parseFloat(i.value))}else n&&(n.innerHTML=`
      <audio id="iap-audio-fallback" controls preload="none" style="width:100%;margin:var(--space-2) 0">
        <source src="${e.url}" />
      </audio>`),ot=document.getElementById("iap-audio-fallback")}function Do(t){hn=t,wn=0;let e=document.getElementById("inline-player-root");if(!e||!t.length){e&&(e.innerHTML='<p class="text-muted text-sm" style="text-align:center;padding:var(--space-4)">No audio renders attached to this commit.</p>');return}let n=t.map((o,s)=>`<option value="${s}">${f(o.name)}</option>`).join("");e.innerHTML=`
    <div class="iap-title">${f(t[0].name)}</div>
    <div id="iap-waveform" class="iap-waveform-wrap">
      <div class="iap-waveform-placeholder">\u{1F3B5} Loading waveform\u2026</div>
    </div>
    <div class="iap-controls">
      <button id="iap-play-btn" class="iap-play-btn" title="Play / Pause" data-action="iap-play">\u25B6</button>
      <div style="flex:1;min-width:0">
        <div id="iap-progress-bar" class="iap-progress-bar" data-action="iap-seek">
          <div id="iap-progress-fill" class="iap-progress-fill"></div>
        </div>
        <div class="iap-time-row">
          <span id="iap-current-time">0:00</span>
          <span id="iap-duration">\u2014</span>
        </div>
      </div>
      <div class="iap-volume-wrap">
        \u{1F50A}
        <input id="iap-volume" type="range" min="0" max="1" step="0.05" value="0.8"
               class="iap-volume-slider" data-action="iap-volume" />
      </div>
    </div>
    ${t.length>1?`
    <div class="iap-track-selector">
      <label class="iap-track-label">Track</label>
      <select id="iap-track-sel" class="iap-track-select" data-action="iap-track">
        ${n}
      </select>
    </div>`:""}`,In(0)}function No(){let t=document.getElementById("iap-play-btn");F?(F.playPause(),qt=!qt,t&&(t.textContent=qt?"\u23F8":"\u25B6")):ot&&(ot.paused?(ot.play(),t&&(t.textContent="\u23F8")):(ot.pause(),t&&(t.textContent="\u25B6")))}function Fo(t){let e=document.getElementById("iap-progress-bar");if(!e||!F)return;let n=e.getBoundingClientRect(),o=(t.clientX-n.left)/n.width;F.seekTo(Math.max(0,Math.min(1,o)))}function jo(t){F?F.setVolume(parseFloat(t)):ot&&(ot.volume=parseFloat(t))}function Oo(t){In(parseInt(t,10))}function zo(t){let e=Ao[t.dimension]||"\u25C6",n=Math.round(t.score*100);return`<span class="badge badge-dim-${t.color}" title="${f(t.dimension)}: ${n}% change">
    ${e} ${f(t.dimension)} <span class="dim-pct">${t.label}</span>
  </span>`}function Uo(t,e){let n=t.path.split(".").pop().toLowerCase(),o=`/api/v1/repos/${w.repoId}/objects/${t.objectId}/content`,s=t.path.split("/").pop();return Ee.has(n)?`<div class="artifact-card">
      <img data-content-url="${o}" alt="${f(t.path)}" loading="lazy" />
      <span class="path">${f(s)}</span>
    </div>`:Wt.has(n)?`<div class="artifact-card">
      <audio controls preload="none" style="width:100%;margin-bottom:var(--space-1)">
        <source src="${o}" />
      </audio>
      <button class="btn btn-primary btn-sm" style="width:100%;justify-content:center"
              data-action="queue-audio" data-url="${o}" data-name="${f(s)}" data-repo="${f(e)}">
        \u25B6 Queue in Player
      </button>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-1)"
              data-action="download-artifact" data-url="${o}" data-name="${f(s)}">
        \u2B07 Download
      </button>
      <span class="path icon-mp3">${f(s)}</span>
    </div>`:$e.has(n)?`<div class="artifact-card">
      <div class="midi-preview" id="midi-${f(t.objectId)}" data-url="${o}">
        <div class="midi-roll-placeholder">\u{1F3B9} MIDI \u2014 ${f(s)}</div>
      </div>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
              data-action="download-artifact" data-url="${o}" data-name="${f(s)}">
        \u2B07 Download MIDI
      </button>
      <a class="btn btn-ghost btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-1)"
         href="${w.base}/objects/${f(t.objectId)}/piano-roll" target="_blank">
        \u{1F3B9} View in Piano Roll
      </a>
      <span class="path icon-mid">${f(s)}</span>
    </div>`:Te.has(n)?`<div class="artifact-card">
      <div class="score-preview" id="score-${f(t.objectId)}" data-url="${o}" data-ext="${n}">
        <p class="text-muted text-sm" style="padding:var(--space-2)">\u{1F3B6} ${f(n.toUpperCase())} Score \u2014 loading\u2026</p>
      </div>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
              data-action="download-artifact" data-url="${o}" data-name="${f(s)}">
        \u2B07 Download Score
      </button>
      <span class="path">${f(s)}</span>
    </div>`:Ie.has(n)?`<div class="artifact-card artifact-card--meta">
      <div class="meta-file-icon">{ }</div>
      <span class="path">${f(s)}</span>
      <a class="btn btn-secondary btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-2)"
         href="${o}" target="_blank">
        \u{1F441} View JSON
      </a>
    </div>`:`<div class="artifact-card">
    <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
            data-action="download-artifact" data-url="${o}" data-name="${f(s)}">
      \u2B07 Download
    </button>
    <span class="path">${f(s)}</span>
  </div>`}function qo(t,e){let n=g=>g.path.split(".").pop().toLowerCase(),o=t.filter(g=>Ee.has(n(g))),s=t.filter(g=>Wt.has(n(g))),i=t.filter(g=>$e.has(n(g))),r=t.filter(g=>Te.has(n(g))),a=t.filter(g=>Ie.has(n(g))),l=t.filter(g=>{let d=n(g);return!Ee.has(d)&&!Wt.has(d)&&!$e.has(d)&&!Te.has(d)&&!Ie.has(d)}),c=(g,d,p)=>p.length?`<div class="artifact-section">
      <h3 class="artifact-section-title">${d} ${g} <span class="artifact-count">(${p.length})</span></h3>
      <div class="artifact-grid">${p.map(u=>Uo(u,e)).join("")}</div>
    </div>`:"",m=[c("Piano Rolls","\u{1F3B9}",o),c("Audio","\u{1F3B5}",s),c("MIDI","\u{1F3BB}",i),c("Scores","\u{1F3BC}",r),c("Metadata","\u{1F4C4}",a),c("Other","\u{1F4CE}",l)].filter(Boolean);return m.length?m.join(""):`<div class="empty-state" style="padding:var(--space-6)">
      <div class="empty-icon">\u{1F4BE}</div>
      <p class="empty-title">No artifacts</p>
      <p class="empty-desc">Push audio files and MIDI via <code>muse push</code> to see them here.</p>
    </div>`}async function Wo(){document.querySelectorAll("img[data-content-url]").forEach(async t=>{let e=t.dataset.contentUrl;try{t.src=await window._fetchBlobUrl(e)}catch{t.alt="Preview unavailable"}})}function Go(t){let e=[],n=/\b(bass|keys|drums?|strings?|horn|trumpet|sax(?:ophone)?|guitar|piano|synth|pad|lead|percussion|vox|vocals?)\b/gi,o;for(;(o=n.exec(t))!==null;){let s=o[1].toLowerCase();e.includes(s)||e.push(s)}return e}function Yo(t){let e=t.split(`
`);if(e.length<=1)return"";let n=e.slice(1).join(`
`).trim();return n?`<div class="commit-body">${n.split(`
`).map(s=>`<span class="commit-body-line">${f(s)||"&nbsp;"}</span>`).join("")}</div>`:""}function Xo(t,e,n){if(!t.length&&!e.length)return"";let o=(s,i,r)=>{if(!i.length)return"";let a=i[0],l=`/api/v1/repos/${n}/objects/${a.objectId}/content`,c=a.path.split("/").pop();return`<div class="ab-player" id="ab-${r}">
      <div class="ab-label">${s}</div>
      <audio controls preload="none" style="width:100%">
        <source src="${l}" />
      </audio>
      <span class="path text-sm">${f(c)}</span>
    </div>`};return`<div class="card">
    <h2 style="margin-bottom:var(--space-3)">\u{1F50A} Before / After</h2>
    <p class="text-sm text-muted" style="margin-bottom:var(--space-3)">
      Compare the primary audio render of this commit against its parent.
    </p>
    <div class="ab-container">
      ${o("After (this commit)",t,"after")}
      ${o("Before (parent)",e,"before")}
    </div>
  </div>`}function Vo(t){return!t||!t.length?"":t.map(e=>`<span class="badge badge-tag" title="Tag: ${f(e)}">\u{1F3F7} ${f(e)}</span>`).join("")}function Jo(t,e,n){let o=t.filter(s=>(s.parentIds||[]).includes(e));return o.length?o.map(s=>`<a href="${n}/commits/${s.commitId}" class="text-mono text-sm" title="View child commit">${s.commitId.substring(0,8)}</a>`).join(" "):'<span class="text-muted text-sm">none (HEAD or branch tip)</span>'}function At(t){let e=t.indexOf(":"),n=e>=0?t.slice(0,e).toLowerCase():"",o=e>=0?t.slice(e+1):t,i={emotion:"pill-emotion",stage:"pill-stage",ref:"pill-ref",key:"pill-key",tempo:"pill-tempo",time:"pill-time",meter:"pill-time"}[n]||"pill-generic",r=n==="ref"&&/^https?:\/\//.test(o),a=r?o:n?`${w.base}/tags?namespace=${encodeURIComponent(n)}`:null,l=r?' target="_blank" rel="noopener noreferrer"':"",c=n?`<span class="pill-ns">${f(n)}</span><span class="pill-sep">:</span>${f(o)}`:f(t);return a?`<a class="muse-pill ${i}"${l} href="${f(a)}">${c}</a>`:`<span class="muse-pill ${i}">${c}</span>`}function Ko(t,e,n,o,s,i){let r=[];t&&r.push(`in ${f(t.tonic)} ${f(t.mode)}`),e&&r.push(`at ${f(String(e.bpm))} BPM`),n&&r.push(`in ${f(n.timeSignature)}`);let a=i>0?`This commit contains ${i} artifact${i!==1?"s":""}${r.length?" "+r.join(", "):""}.`:r.length?`This commit records musical content ${r.join(", ")}.`:"",l=(s?.dimensions||[]).filter(g=>g.score>=.15).map(g=>f(g.dimension)),c=o?f(o.primaryEmotion):"",m="";return l.length&&c?m=`The primary musical changes are ${l.join(" and ")}, carrying a ${c} character.`:l.length?m=`The primary musical changes are ${l.join(" and ")}.`:c&&(m=`The musical character is ${c}.`),!a&&!m?"":`<p class="commit-prose-summary text-sm">${[a,m].filter(Boolean).join(" ")}</p>`}async function Zo(t,e,n){let o=document.getElementById("muse-tags-panel");if(!o)return;let[s,i,r,a]=await Promise.allSettled([Y(`/repos/${w.repoId}/analysis/${encodeURIComponent(w.commitId)}/key`),Y(`/repos/${w.repoId}/analysis/${encodeURIComponent(w.commitId)}/tempo`),Y(`/repos/${w.repoId}/analysis/${encodeURIComponent(w.commitId)}/meter`),Y(`/repos/${w.repoId}/analysis/${encodeURIComponent(w.commitId)}/emotion`)]),l=s.status==="fulfilled"?s.value:null,c=i.status==="fulfilled"?i.value:null,m=r.status==="fulfilled"?r.value:null,g=a.status==="fulfilled"?a.value:null,d=[];if(l&&d.push(At(`key:${l.tonic} ${l.mode}`)),c&&d.push(At(`tempo:${c.bpm}bpm`)),m&&d.push(At(`time:${m.timeSignature}`)),g&&d.push(At(`emotion:${g.primaryEmotion}`)),g&&g.valence!=null){let L=parseFloat(String(g.valence)),$=L>.6?"positive":L<.4?"tense":"neutral";d.push(At(`stage:${$}`))}let u=[...(t||[]).map(L=>At(L)),...d],v=[];l&&v.push(`
    <div class="meta-item">
      <span class="meta-label">Key</span>
      <span class="meta-value text-sm">
        \u266D ${f(l.tonic)} ${f(l.mode)}
        <span class="text-muted">${(l.keyConfidence*100).toFixed(0)}%</span>
      </span>
    </div>`),c&&v.push(`
    <div class="meta-item">
      <span class="meta-label">Tempo</span>
      <span class="meta-value text-sm">\u23F1 ${f(String(c.bpm))} BPM
        ${c.timeFeel?`<span class="text-muted">${f(c.timeFeel)}</span>`:""}
      </span>
    </div>`),m&&v.push(`
    <div class="meta-item">
      <span class="meta-label">Time sig.</span>
      <span class="meta-value text-sm">${f(m.timeSignature)}</span>
    </div>`),g&&v.push(`
    <div class="meta-item">
      <span class="meta-label">Emotion</span>
      <span class="meta-value text-sm">
        ${f(g.primaryEmotion)}
        <span class="text-muted">${(g.confidence*100).toFixed(0)}%</span>
      </span>
    </div>`);let h=Ko(l,c,m,g,e,n);if(!v.length&&!u.length&&!h){o.innerHTML='<p class="text-muted text-sm">No analysis data available for this commit.</p>';return}o.innerHTML=`
    ${h}
    ${v.length?`<div class="meta-row muse-tags-meta-row" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr));margin-bottom:var(--space-3)">${v.join("")}</div>`:""}
    ${u.length?`<div class="muse-pills-row">${u.join("")}</div>`:""}`}async function Qo(){let t=document.getElementById("xrefs-body");if(!t)return;let e=w.commitId.substring(0,8),[n,o,s]=await Promise.allSettled([Y(`/repos/${w.repoId}/pull-requests?limit=100`),Y(`/repos/${w.repoId}/issues?limit=100`),Y(`/repos/${w.repoId}/sessions?limit=50`)]),i=(n.status==="fulfilled"?n.value.pullRequests:null)||[],r=(o.status==="fulfilled"?o.value.issues:null)||[],a=(s.status==="fulfilled"?s.value.sessions:null)||[],l=i.filter(d=>(d.description||"").includes(w.commitId.substring(0,7))||(d.description||"").includes(e)||(d.fromBranch||"").includes(e)),c=r.filter(d=>(d.body||"").includes(w.commitId.substring(0,7))||(d.body||"").includes(e)||(d.title||"").includes(e)),m=a.filter(d=>(d.commitIds||[]).includes(w.commitId)||(d.description||"").includes(e));if(!l.length&&!c.length&&!m.length){t.innerHTML='<p class="text-muted text-sm" style="margin:0">No cross-references found for this commit.</p>';return}let g="";l.length&&(g+=`<div class="xref-group">
      <div class="xref-group-label">Pull Requests (${l.length})</div>
      <div class="xref-list">
        ${l.map(d=>`
          <div class="xref-item">
            <span class="xref-icon ${d.state==="open"?"xref-open":"xref-closed"}">\u2295</span>
            <a href="${w.base}/pulls/${encodeURIComponent(d.prId)}" class="xref-link">
              ${f(d.title)}
            </a>
            <span class="xref-meta">#${f(String(d.prId))} \xB7 ${f(d.fromBranch||"")} \u2192 ${f(d.toBranch||"")}</span>
          </div>`).join("")}
      </div>
    </div>`),c.length&&(g+=`<div class="xref-group">
      <div class="xref-group-label">Issues (${c.length})</div>
      <div class="xref-list">
        ${c.map(d=>`
          <div class="xref-item">
            <span class="xref-icon ${d.state==="open"?"xref-open":"xref-closed"}">\u25CF</span>
            <a href="${w.base}/issues/${encodeURIComponent(d.number)}" class="xref-link">
              ${f(d.title)}
            </a>
            <span class="xref-meta">#${f(String(d.number))}</span>
          </div>`).join("")}
      </div>
    </div>`),m.length&&(g+=`<div class="xref-group">
      <div class="xref-group-label">Sessions (${m.length})</div>
      <div class="xref-list">
        ${m.map(d=>`
          <div class="xref-item">
            <span class="xref-icon xref-session">\u{1F399}</span>
            <a href="${w.base}/sessions/${encodeURIComponent(d.sessionId)}" class="xref-link">
              ${f(d.title||d.sessionId.substring(0,8))}
            </a>
            <span class="xref-meta">${xn(d.startedAt||d.createdAt||"")}</span>
          </div>`).join("")}
      </div>
    </div>`),t.innerHTML=g}function ti(){document.querySelectorAll('.score-preview[data-ext="abc"]').forEach(async t=>{try{let e=t.dataset.url,n=await fetch(e,{headers:window.authHeaders()}).then(o=>o.text());window.ABCJS?(t.innerHTML="",window.ABCJS.renderAbc(t,n,{responsive:"resize",staffwidth:t.offsetWidth||400})):t.innerHTML='<pre style="font-size:11px;overflow-x:auto">'+f(n.substring(0,400))+"</pre>"}catch{}})}async function ei(){let t=document.getElementById("ai-summary-panel"),e=document.getElementById("ai-summary-body");if(!(!t||!e))try{let n=await Y(`/repos/${w.repoId}/context/${w.commitId}`),o=n.missingElements||[],s=n.suggestions||{},i=Object.keys(s),r="";o.length>0&&(r+='<p class="text-sm text-muted" style="margin-bottom:var(--space-2)">Missing elements:</p>',r+='<ul style="padding-left:var(--space-4);font-size:var(--font-size-sm);color:var(--color-warning)">',r+=o.map(a=>"<li>"+f(a)+"</li>").join(""),r+="</ul>"),i.length>0&&(r+='<p class="text-sm text-muted" style="margin-top:var(--space-3);margin-bottom:var(--space-2)">Suggestions:</p>',r+=i.map(a=>'<div style="margin-bottom:var(--space-2);font-size:var(--font-size-sm)"><strong>'+f(a)+"</strong>: "+f(s[a])+"</div>").join("")),r||(r='<p class="text-sm text-muted">All musical dimensions look complete.</p>'),e.innerHTML=r,t.style.display=""}catch{}}function ni(){let t=document.getElementById("compose-modal");if(t){t.style.display="flex";let e=document.getElementById("compose-output"),n=document.getElementById("compose-stream");e&&(e.style.display="none"),n&&(n.textContent="")}}function yn(){let t=document.getElementById("compose-modal");t&&(t.style.display="none")}async function si(){let e=document.getElementById("compose-prompt")?.value.trim();if(!e)return;let n=document.getElementById("compose-send-btn"),o=document.getElementById("compose-output"),s=document.getElementById("compose-stream");n&&(n.disabled=!0,n.textContent="\u23F3 Generating\u2026"),o&&(o.style.display=""),s&&(s.textContent="");try{let i=await fetch("/api/v1/muse/stream",{method:"POST",headers:{...window.authHeaders(),"Content-Type":"application/json"},body:JSON.stringify({message:e,mode:"compose",repo_id:w.repoId,commit_id:w.commitId})});if(!i.ok){s&&(s.textContent=`\u274C ${i.status}: ${await i.text()}`);return}let r=i.body.getReader(),a=new TextDecoder,l="";for(;;){let{value:c,done:m}=await r.read();if(m)break;l+=a.decode(c,{stream:!0});let g=l.split(`
`);l=g.pop()||"";for(let d of g)if(d.startsWith("data: ")){let p=d.slice(6).trim();if(p==="[DONE]")break;try{let u=JSON.parse(p);typeof u=="string"?s&&(s.textContent+=u):u.content?s&&(s.textContent+=u.content):u.text&&s&&(s.textContent+=u.text)}catch{s&&(s.textContent+=p)}s&&(s.scrollTop=s.scrollHeight)}}}catch(i){s&&(s.textContent+=`

\u274C ${i.message}`)}finally{n&&(n.disabled=!1,n.textContent="\u266A Re-generate")}}function oi(t,e){let n=t.filter(s=>!s.parent_id),o=t.filter(s=>s.parent_id);return n.length===0&&!e?'<p class="text-sm text-muted" style="margin:0">No comments yet.</p>':n.length===0?'<p class="text-sm text-muted" style="margin:0">Be the first to comment.</p>':n.map(s=>ii(s,o,e)).join("")}function ii(t,e,n){let o=n&&t.author===n,s=e.filter(i=>i.parent_id===t.comment_id);return`
<div class="comment-thread" id="comment-${f(t.comment_id)}">
  <div class="comment-row">
    ${Tn(t.author)}
    <div class="comment-body-col">
      <div class="comment-meta">
        <a href="/${encodeURIComponent(t.author)}" class="comment-author">${f(t.author)}</a>
        <span class="comment-ts" title="${f(t.created_at)}">${En(t.created_at)}</span>
      </div>
      <div class="comment-text">${f(t.body)}</div>
      <div class="comment-actions">
        ${n?`<button class="btn btn-ghost btn-xs" data-action="show-reply" data-comment-id="${f(t.comment_id)}">\u21A9 Reply</button>`:""}
        ${o?`<button class="btn btn-ghost btn-xs comment-delete-btn" data-action="delete-comment" data-comment-id="${f(t.comment_id)}">\u{1F5D1}</button>`:""}
      </div>
      <div class="reply-form-slot" id="reply-slot-${f(t.comment_id)}"></div>
      ${s.length>0?`<div class="comment-replies">${s.map(i=>ai(i,n)).join("")}</div>`:""}
    </div>
  </div>
</div>`}function ai(t,e){let n=e&&t.author===e;return`
<div class="comment-row comment-reply-row" id="comment-${f(t.comment_id)}">
  ${Tn(t.author)}
  <div class="comment-body-col">
    <div class="comment-meta">
      <a href="/${encodeURIComponent(t.author)}" class="comment-author">${f(t.author)}</a>
      <span class="comment-ts" title="${f(t.created_at)}">${En(t.created_at)}</span>
    </div>
    <div class="comment-text">${f(t.body)}</div>
    ${n?`<div class="comment-actions"><button class="btn btn-ghost btn-xs comment-delete-btn" data-action="delete-comment" data-comment-id="${f(t.comment_id)}">\u{1F5D1}</button></div>`:""}
  </div>
</div>`}async function Le(){if(document.getElementById("comments-section"))try{let t=await Y(`/repos/${w.repoId}/comments?target_type=commit&target_id=${encodeURIComponent(w.commitId)}`),e=Po(),n=document.getElementById("comments-list");if(n&&(n.innerHTML=oi(t,e)),e){let o=document.getElementById("new-comment-form"),s=document.getElementById("new-comment-avatar");o&&(o.style.display=""),s&&(s.textContent=e.charAt(0).toUpperCase(),s.style.background=$n(e),s.style.color="#fff")}}catch(t){let e=t;if(e.message!=="auth"){let n=document.getElementById("comments-list");n&&(n.innerHTML=`<p class="error text-sm">\u2715 ${f(e.message)}</p>`)}}}async function ri(t){let e=t?`reply-body-${t}`:"new-comment-body",n=document.getElementById(e);if(!n)return;let o=n.value.trim();if(!o)return;let s=t?document.querySelector(`#reply-slot-${t} .comment-submit-btn`):document.getElementById("comment-submit-btn");s&&(s.disabled=!0,s.textContent="Posting\u2026");try{if(await Y(`/repos/${w.repoId}/comments`,{method:"POST",body:JSON.stringify({target_type:"commit",target_id:w.commitId,body:o,parent_id:t||null})}),n.value="",t){let i=document.getElementById(`reply-slot-${t}`);i&&(i.innerHTML="")}await Le()}catch(i){let r=i;r.message!=="auth"&&alert("Failed to post comment: "+r.message)}finally{s&&(s.disabled=!1,s.textContent="Comment")}}async function li(t){if(confirm("Delete this comment?"))try{await Y(`/repos/${w.repoId}/comments/${t}`,{method:"DELETE"}),await Le()}catch(e){let n=e;n.message!=="auth"&&alert("Failed to delete: "+n.message)}}function ci(t){let e=document.getElementById(`reply-slot-${t}`);if(!e)return;if(e.innerHTML.trim()){e.innerHTML="";return}e.innerHTML=`
<div class="reply-form">
  <textarea id="reply-body-${f(t)}" class="form-input comment-textarea" rows="2"
            placeholder="Write a reply\u2026" style="resize:vertical"></textarea>
  <div class="comment-form-actions">
    <button class="btn btn-primary btn-sm comment-submit-btn" data-action="comment-submit" data-parent-id="${f(t)}">Comment</button>
    <button class="btn btn-ghost btn-sm" data-action="cancel-reply" data-parent-id="${f(t)}">Cancel</button>
  </div>
</div>`;let n=document.getElementById(`reply-body-${t}`);n&&n.focus()}function di(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");if(e)switch(e.dataset.action){case"iap-play":No();break;case"iap-seek":Fo(t);break;case"queue-audio":{let{url:n,name:o,repo:s}=e.dataset;n&&typeof window.queueAudio=="function"&&window.queueAudio(n,o??"",s??"");break}case"download-artifact":{let{url:n,name:o}=e.dataset;n&&typeof window.downloadArtifact=="function"&&window.downloadArtifact(n,o??"");break}case"copy-sha":Ro(e.dataset.sha??"",e);break;case"open-compose":ni();break;case"compose-close":yn();break;case"compose-send":si();break;case"compose-modal-backdrop":t.target===e&&yn();break;case"comment-submit":ri(e.dataset.parentId||null);break;case"cancel-reply":{let n=document.getElementById(`reply-slot-${e.dataset.parentId}`);n&&(n.innerHTML="");break}case"show-reply":ci(e.dataset.commentId??"");break;case"delete-comment":li(e.dataset.commentId??"");break}}),document.addEventListener("input",t=>{let e=t.target;e.dataset.action==="iap-volume"&&jo(e.value)}),document.addEventListener("change",t=>{let e=t.target;e.dataset.action==="iap-track"&&Oo(e.value)})}async function mi(){try{let[t,e,n]=await Promise.all([Y(`/repos/${w.repoId}/commits?limit=200`),Y(`/repos/${w.repoId}/objects`),Y(`/repos/${w.repoId}/commits/${w.commitId}/diff-summary`).catch(()=>null)]),o=t.commits||[],s=o.find(B=>B.commitId===w.commitId),i=e.objects||[],r=w.repoId;if(!s){let B=document.getElementById("content");B&&(B.innerHTML=`<div class="card"><p class="error">Commit ${f(w.commitId)} not found in recent history.</p></div>`);return}let a=window.parseCommitMessage(s.message),l=window.parseCommitMeta(s.message),c=Go(s.message),m=window.commitTypeBadge(a.type),g=window.commitScopeBadge(a.scope),d=n?(n.dimensions||[]).filter(B=>B.score>=.15).map(zo).join(""):"",p=(s.parentIds||[]).length>0?s.parentIds.map(B=>`<a href="${w.base}/commits/${B}" class="text-mono text-sm" title="View parent commit">${B.substring(0,8)}</a>`).join(" "):'<span class="text-muted text-sm">none (root commit)</span>',u=Jo(o,s.commitId,w.base),v=c.length>0?c.map(B=>`<span class="nav-meta-tag">\u{1F3B8} ${f(B)}</span>`).join(""):"",h=Vo(s.tags||[]),L=(s.parentIds||[])[0]||null,$=[];if(L)try{$=(await Y(`/repos/${w.repoId}/objects?commit_id=${L}`)).objects||[]}catch{}let y=i.filter(B=>Wt.has(B.path.split(".").pop().toLowerCase())),C=$.filter(B=>Wt.has(B.path.split(".").pop().toLowerCase())),x=y,M=x.length>1?`<div class="card">
          <h2 style="margin-bottom:var(--space-3)">\u{1F399} Stem Browser</h2>
          <p class="text-sm text-muted" style="margin-bottom:var(--space-3)">Solo individual instrument stems.</p>
          <div class="stem-browser" id="stem-browser">
            ${x.map((B,gt)=>{let q=B.path.split("/").pop().replace(/\.[^.]+$/,""),ft=`/api/v1/repos/${w.repoId}/objects/${B.objectId}/content`;return`<div class="stem-row" id="stem-row-${gt}">
                <button class="player-btn" data-action="queue-audio" data-url="${ft}" data-name="${f(q)}" data-repo="" title="Play stem">\u25B6</button>
                <span class="stem-label">${f(q)}</span>
                <div class="waveform-bar" style="flex:1;height:32px;cursor:pointer" data-action="queue-audio" data-url="${ft}" data-name="${f(q)}" data-repo="">
                  ${Array.from({length:48},(St,vt)=>{let et=(q.charCodeAt(vt%q.length)+vt)*1103515245;return`<div class="wave-col" style="height:${20+Math.abs(et)%70}%"></div>`}).join("")}
                </div>
              </div>`}).join("")}
          </div>
        </div>`:"",N=qo(i,r),A=[l.key?`<div class="meta-item"><span class="meta-label">Key</span><span class="meta-value text-sm">\u266D ${f(l.key)}</span></div>`:"",l.tempo||l.bpm?`<div class="meta-item"><span class="meta-label">Tempo</span><span class="meta-value text-sm">\u23F1 ${f(l.tempo||l.bpm)} BPM</span></div>`:"",l.section?`<div class="meta-item"><span class="meta-label">Section</span><span class="meta-value badge badge-dim-structural">${f(l.section)}</span></div>`:"",l.meter?`<div class="meta-item"><span class="meta-label">Meter</span><span class="meta-value text-sm">${f(l.meter)}</span></div>`:""].filter(Boolean).join(""),O=o.filter(B=>(B.parentIds||[]).includes(w.commitId))[0],J=document.getElementById("content");J&&(J.innerHTML=`
      <div class="commit-liner-notes">

        <div class="commit-header-row">
          <div class="commit-header-left">
            ${m}${g}
            ${v}
            ${h}
          </div>
          <div class="commit-header-right">
            <a href="${w.base}/commits/${w.commitId}/diff" class="btn btn-secondary btn-sm">
              \u2295 Musical Diff
            </a>
            <a href="${w.base}/context/${w.commitId}" class="btn btn-secondary btn-sm">
              \u{1F9E0} AI Context
            </a>
            <button class="btn btn-primary btn-sm" data-action="open-compose">
              \u{1F3B5} Compose Variation
            </button>
          </div>
        </div>

        ${d?`<div class="card dim-badges-card">
          <div class="dim-badges-label">Musical Changes</div>
          <div class="dim-badges-row">${d}</div>
        </div>`:""}

        <div class="card commit-message-card">
          <h1 class="commit-subject">${f(a.subject||s.message)}</h1>
          ${a.type||a.scope?`
          <div style="margin-top:var(--space-2);font-size:var(--font-size-sm);color:var(--text-muted)">
            ${a.type?`<strong>${f(a.type)}</strong>`:""}
            ${a.scope?` in <strong>${f(a.scope)}</strong>`:""}
          </div>`:""}
          ${Yo(s.message)}
        </div>

        <div class="card iap-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">\u{1F3A7} Listen</h2>
            <a href="${w.listenUrl}" class="btn btn-secondary btn-sm" target="_blank">
              Open Full Listen Page \u2197
            </a>
          </div>
          <div id="inline-player-root">
            <p class="text-muted text-sm">Loading audio\u2026</p>
          </div>
        </div>

        <div class="card">
          <h2 style="margin:0 0 var(--space-3) 0">\u{1F3F7} Muse Tags &amp; Metadata</h2>
          <div id="muse-tags-panel"><p class="loading text-sm">Loading analysis\u2026</p></div>
        </div>

        <div class="card">
          <div class="meta-row" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
            <div class="meta-item">
              <span class="meta-label">Author</span>
              <span class="meta-value">
                <a href="/${f(s.author)}" class="text-sm">${f(s.author)}</a>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Date</span>
              <span class="meta-value text-sm">${xn(s.timestamp)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Branch</span>
              <span class="meta-value text-mono text-sm">${f(s.branch||"\u2014")}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">SHA</span>
              <span class="meta-value" style="display:flex;align-items:center;gap:var(--space-1)">
                <span class="text-mono text-sm sha-full" title="${f(w.commitId)}">${f(w.commitId)}</span>
                <button class="btn btn-ghost btn-xs copy-btn" data-action="copy-sha" data-sha="${f(w.commitId)}" title="Copy full SHA">\u29C9</button>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Parents</span>
              <span class="meta-value">${p}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Children</span>
              <span class="meta-value">${u}</span>
            </div>
            ${A}
          </div>
        </div>

        ${Xo(y,C,w.repoId)}

        ${M}

        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">Artifacts (${i.length})</h2>
            ${x.length>0?`
            <button class="btn btn-primary btn-sm"
                    data-action="queue-audio"
                    data-url="/api/v1/repos/${w.repoId}/objects/${x[0].objectId}/content"
                    data-name="${f(x[0].path.split("/").pop())}"
                    data-repo="${f(w.repoId)}">
              \u25B6 Play Latest
            </button>`:""}
          </div>
          ${N}
        </div>

        <div class="card" style="padding:var(--space-3) var(--space-4)">
          <div id="commit-reactions"><p class="text-muted text-sm">Loading reactions\u2026</p></div>
        </div>

        <div class="card" id="ai-summary-panel" style="display:none;border-color:var(--color-accent)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">\u{1F9E0} What changed musically?</h2>
            <button class="btn btn-secondary btn-sm" data-action="open-compose">
              \u{1F3B5} Compose Variation
            </button>
          </div>
          <div id="ai-summary-body"><p class="loading text-sm">Analyzing\u2026</p></div>
        </div>

        <div class="card" id="comments-section">
          <h2 style="margin:0 0 var(--space-3) 0">\u{1F4AC} Discussion</h2>
          <div id="comments-list"><p class="loading text-sm">Loading comments\u2026</p></div>
          <div id="new-comment-form" style="display:none;margin-top:var(--space-4)">
            <div class="comment-row" style="align-items:flex-start">
              <span class="comment-avatar" id="new-comment-avatar" style="background:var(--bg-overlay);color:var(--text-muted)">?</span>
              <div style="flex:1">
                <textarea id="new-comment-body" class="form-input comment-textarea" rows="3"
                          placeholder="Leave a comment\u2026" style="resize:vertical"></textarea>
                <div class="comment-form-actions" style="margin-top:var(--space-2)">
                  <button id="comment-submit-btn" class="btn btn-primary btn-sm"
                          data-action="comment-submit" data-parent-id="">Comment</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">\u{1F517} Mentioned In</h2>
          </div>
          <div id="xrefs-body"><p class="loading text-sm">Loading cross-references\u2026</p></div>
        </div>

        <div style="display:flex;gap:var(--space-3);margin-top:var(--space-2);flex-wrap:wrap">
          ${s.parentIds&&s.parentIds.length>0?`<a href="${w.base}/commits/${s.parentIds[0]}" class="btn btn-secondary btn-sm">\u2190 Parent Commit</a>`:""}
          ${O?`<a href="${w.base}/commits/${O.commitId}" class="btn btn-secondary btn-sm">Child Commit \u2192</a>`:""}
          <a href="${w.base}" class="btn btn-ghost btn-sm">\u2190 Back to commits</a>
        </div>
      </div>`),ti(),Wo(),typeof window.loadReactions=="function"&&window.loadReactions("commit",w.commitId,"commit-reactions");let z=y.map(B=>({name:B.path.split("/").pop().replace(/\.[^.]+$/,""),url:`/api/v1/repos/${w.repoId}/objects/${B.objectId}/content`}));Do(z),Zo(s.tags||[],n,i.length),Qo()}catch(t){let e=t;if(e.message!=="auth"){let n=document.getElementById("content");n&&(n.innerHTML=`<p class="error">\u2715 ${f(e.message)}</p>`)}}}function Ln(t){w=window.__commitPageCfg,w&&(nt({repo_id:w.repoId}),di(),mi(),ei(),Le())}function S(t){return t?String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"):""}function Mn(t){if(!t)return"";let e=new Date(t),n=Math.floor((Date.now()-e.getTime())/1e3);return n<60?"just now":n<3600?Math.floor(n/60)+"m ago":n<86400?Math.floor(n/3600)+"h ago":Math.floor(n/86400)+"d ago"}function ui(t){let e=t.days??[],n=[],o=[];for(let a of e)o.push(a),o.length===7&&(n.push(o),o=[]);o.length&&n.push(o);let s=n.map(a=>`<div class="heatmap-col">${a.map(c=>`<div class="heatmap-cell" data-intensity="${c.intensity}" title="${S(c.date)}: ${c.count} commit${c.count!==1?"s":""}"></div>`).join("")}</div>`).join(""),i=[0,1,2,3].map(a=>`<div class="heatmap-cell" data-intensity="${a}" style="display:inline-block"></div>`).join(""),r=document.getElementById("heatmap-section");r&&(r.innerHTML=`
    <div class="card">
      <h2 style="margin-bottom:12px">\u{1F4C8} Contribution Activity</h2>
      <div class="heatmap-grid">${s}</div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;color:var(--text-muted)">
        Less ${i} More &nbsp;\xB7&nbsp; ${t.totalContributions??0} contributions in the last year
        &nbsp;\xB7&nbsp; Longest streak: ${t.longestStreak??0} days
        &nbsp;\xB7&nbsp; Current streak: ${t.currentStreak??0} days
      </div>
    </div>`)}function pi(t){let e=t.map(s=>`<div class="badge-card ${s.earned?"earned":"unearned"}" title="${S(s.description)}">
      <div class="badge-icon">${S(s.icon)}</div>
      <div class="badge-info">
        <div class="badge-name">${S(s.name)}</div>
        <div class="badge-desc">${S(s.description)}</div>
      </div>
    </div>`).join(""),n=t.filter(s=>s.earned).length,o=document.getElementById("badges-section");o&&(o.innerHTML=`<div class="card"><h2 style="margin-bottom:12px">\u{1F3C6} Achievements (${n}/${t.length})</h2><div class="badge-grid">${e}</div></div>`)}function gi(t,e){if(!t?.length)return;let n=t.map(s=>{let i=s.primaryGenre?`<span>\u{1F3B5} ${S(s.primaryGenre)}</span>`:"",r=s.language?`<span>\u{1F524} ${S(s.language)}</span>`:"";return`<div class="pinned-card">
      <h3><a href="/${S(s.owner)}/${S(s.slug)}">${S(s.name)}</a></h3>
      ${s.description?`<p class="pinned-desc">${S(s.description)}</p>`:""}
      <div class="pinned-meta">${i}${r}<span>\u2B50 ${s.starsCount??0}</span><span>\u{1F374} ${s.forksCount??0}</span></div>
    </div>`}).join(""),o=document.getElementById("pinned-section");o&&(o.innerHTML=`<div class="card"><h2 style="margin-bottom:12px">\u{1F4CC} Pinned</h2><div class="pinned-grid">${n}</div></div>`)}var Gt="",fi="repos",ke=[];function vi(t){let e=(t.displayName??t.username??"?")[0].toUpperCase(),n=t.avatarUrl?`<div class="avatar-lg"><img src="${S(t.avatarUrl)}" alt="${S(t.username)}" /></div>`:`<div class="avatar-lg" style="background:${S(t.avatarColor??"#1f6feb")}">${S(e)}</div>`,o=window.getToken?!!window.getToken():!1,s=document.getElementById("profile-hdr");return s&&(s.innerHTML=`
    <div class="profile-hdr">
      ${n}
      <div>
        <h1 style="margin:0 0 4px">${S(t.displayName??t.username)}</h1>
        <div style="font-size:14px;color:var(--text-muted);margin-bottom:8px">@${S(t.username)}</div>
        ${t.bio?`<p style="font-size:14px;margin-bottom:8px">${S(t.bio)}</p>`:""}
        <div style="display:flex;gap:16px;font-size:13px;color:var(--text-muted);flex-wrap:wrap">
          ${t.location?`<span>\u{1F4CD} ${S(t.location)}</span>`:""}
          ${t.website?`<a href="${S(t.website)}" target="_blank" rel="noopener noreferrer">\u{1F517} ${S(t.website)}</a>`:""}
          <span>\u{1F465} <strong>${t.followersCount??0}</strong> followers \xB7 <strong>${t.followingCount??0}</strong> following</span>
          <span>\u2B50 ${t.starsCount??0} stars</span>
        </div>
      </div>
    </div>`),o}function Me(t){let e=document.getElementById("tab-content");if(e){if(!t.length){e.innerHTML='<p style="color:var(--text-muted);text-align:center;padding:24px">No repositories yet.</p>';return}e.innerHTML=t.map(n=>`
    <div class="repo-card" style="margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <a href="/${S(n.owner)}/${S(n.slug)}" style="font-weight:600;font-size:14px">${S(n.name)}</a>
        ${n.isPrivate?'<span class="badge badge-secondary">Private</span>':""}
      </div>
      ${n.description?`<p style="font-size:13px;color:var(--text-muted);margin:4px 0 0">${S(n.description)}</p>`:""}
      <div style="display:flex;gap:12px;font-size:12px;color:var(--text-muted);margin-top:8px;flex-wrap:wrap">
        ${n.primaryGenre?`<span>\u{1F3B5} ${S(n.primaryGenre)}</span>`:""}
        ${n.language?`<span>\u{1F524} ${S(n.language)}</span>`:""}
        <span>\u2B50 ${n.starsCount??0}</span>
        <span>\u{1F374} ${n.forksCount??0}</span>
        ${n.updatedAt?`<span>Updated ${Mn(n.updatedAt)}</span>`:""}
      </div>
    </div>`).join("")}}async function bi(){let t=document.getElementById("tab-content");if(t){t.innerHTML='<p class="loading">Loading starred repos\u2026</p>';try{let e=await fetch("/api/v1/users/"+Gt+"/starred").then(n=>n.json());if(!e.length){t.innerHTML='<p style="color:var(--text-muted);text-align:center;padding:24px">No starred repos yet.</p>';return}Me(e)}catch{t.innerHTML='<p class="error">Failed to load starred repos.</p>'}}}async function kn(t){let e=document.getElementById("tab-content");if(e){e.innerHTML=`<p class="loading">Loading ${t}\u2026</p>`;try{let n=t==="followers"?"/api/v1/users/"+Gt+"/followers-list":"/api/v1/users/"+Gt+"/following-list",o=await fetch(n).then(s=>s.json());if(!o.length){e.innerHTML=`<p style="color:var(--text-muted);text-align:center;padding:24px">No ${t} yet.</p>`;return}e.innerHTML=o.map(s=>{let i=(s.displayName??s.username??"?")[0].toUpperCase();return`<div style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-default)">
        <div style="width:36px;height:36px;border-radius:50%;background:${S(s.avatarColor??"#1f6feb")};display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;flex-shrink:0">${S(i)}</div>
        <div><a href="/${S(s.username)}" style="font-weight:600">${S(s.displayName??s.username)}</a>
          ${s.bio?`<p style="font-size:12px;color:var(--text-muted);margin:2px 0 0">${S(s.bio)}</p>`:""}</div>
      </div>`}).join("")}catch{e.innerHTML=`<p class="error">Failed to load ${t}.</p>`}}}async function Cn(t,e){let n=document.getElementById("tab-content");if(n){n.innerHTML='<p class="loading">Loading activity\u2026</p>';try{let o=await fetch(`/api/v1/users/${Gt}/activity?filter=${t}&page=${e}&limit=20`).then(l=>l.json()),s=o.events??[];if(!s.length){n.innerHTML='<p style="color:var(--text-muted);text-align:center;padding:24px">No activity yet.</p>';return}let i=s.map(l=>`
      <div class="activity-row">
        <span class="activity-icon">\u{1F4DD}</span>
        <div class="activity-body">
          <div class="activity-description">${S(l.description??l.type)}</div>
          <div class="activity-meta">${Mn(l.timestamp)}${l.repo?` \xB7 <a href="/${S(l.repo)}">${S(l.repo)}</a>`:""}</div>
        </div>
      </div>`).join(""),r=Math.ceil((o.total??0)/20),a=r>1?`
      <div class="activity-pagination">
        ${e>1?`<button class="btn btn-secondary" data-activity-page="${e-1}" data-activity-filter="${t}">&larr; Prev</button>`:""}
        <span class="activity-pagination-label">Page ${e} of ${r}</span>
        ${e<r?`<button class="btn btn-secondary" data-activity-page="${e+1}" data-activity-filter="${t}">Next &rarr;</button>`:""}
      </div>`:"";n.innerHTML=i+a,n.querySelectorAll("[data-activity-page]").forEach(l=>{l.addEventListener("click",()=>{Cn(l.dataset.activityFilter??"all",Number(l.dataset.activityPage))})})}catch{n.innerHTML='<p class="error">Failed to load activity.</p>'}}}function yi(t,e="all",n=1){switch(fi=t,document.querySelectorAll(".tab-btn").forEach(o=>{o.classList.toggle("active",o.dataset.tab===t)}),t){case"repos":Me(ke);break;case"stars":bi();break;case"followers":kn("followers");break;case"following":kn("following");break;case"activity":Cn(e,n);break}}async function Hn(t){let e=t.username??"";if(!e)return;Gt=e;let n=document.getElementById("profile-hdr"),o=document.getElementById("tabs-section");n&&(n.innerHTML='<p class="loading">Loading profile\u2026</p>');try{let[s,i]=await Promise.all([fetch("/api/v1/users/"+e).then(a=>{if(!a.ok)throw new Error(String(a.status));return a.json()}),fetch("/"+e+"?format=json").then(a=>{if(!a.ok)throw new Error(String(a.status));return a.json()})]),r=vi(s);ui(i.heatmap??{days:(s.contributionGraph??[]).map(a=>({...a,intensity:a.count===0?0:a.count<=3?1:a.count<=6?2:3})),totalContributions:0,longestStreak:0,currentStreak:0}),pi(i.badges??[]),gi(i.pinnedRepos??[],r),ke=s.repos??[],o&&(o.removeAttribute("hidden"),o.querySelectorAll(".tab-btn").forEach(a=>{a.addEventListener("click",()=>yi(a.dataset.tab??"repos"))})),Me(ke)}catch(s){n&&(n.innerHTML=`<p class="error">\u2715 Could not load profile for @${S(e)}: ${S(s instanceof Error?s.message:String(s))}</p>`)}}var Z=null,Be=[],_e=[],Ae=[],Re="all",ct={commits:!0,emotion:!0,sections:!0,tracks:!0,sessions:!0,prs:!0,releases:!0},_n=1,mt,dt=52,Mt=24,hi=36,kt=10,Rt=100,wi=kt+Rt,Yt=138,oe=155,ie=172,Sn=196,Bn=230,Lt=256,ae=330,xi=272,Ei=304,Ce=370;function $i(t){switch(t){case"day":return 24*3600*1e3;case"week":return 168*3600*1e3;case"month":return 720*3600*1e3;default:return 1/0}}function Ti(){if(!Z?.commits?.length)return[];let t=Z.commits,e=$i(Re);if(e===1/0)return t;let n=new Date(t[t.length-1].timestamp).getTime();return t.filter(o=>n-new Date(o.timestamp).getTime()<=e)}function it(t,e,n,o){return n===e?dt+(o-dt-Mt)/2:dt+(t-e)/(n-e)*(o-dt-Mt)}function He(t,e,n,o){return t.filter(s=>{let i=new Date(s[e]).getTime();return i>=n&&i<=o})}function Ii(t){return new Date(t).toLocaleDateString(void 0,{month:"short",day:"numeric"})}function re(t){return new Date(t).toLocaleString(void 0,{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}function Li(t,e){if(t.length<2)return"";let n=t.map(o=>`${o.x.toFixed(1)},${o.y.toFixed(1)}`).join(" L");return`M${t[0].x.toFixed(1)},${e} L${n} L${t[t.length-1].x.toFixed(1)},${e} Z`}function Pt(){let t=document.getElementById("timeline-svg-container");if(!t)return;if(!Z){t.innerHTML='<div class="tl-loading"><div class="tl-loading-inner">Loading timeline\u2026</div></div>';return}let e=Ti();if(e.length===0){t.innerHTML='<div class="tl-loading"><div class="tl-loading-inner">No commits in this time window.</div></div>';return}let n=Math.max(t.clientWidth||900,dt+Mt+e.length*22),o=e.map($=>new Date($.timestamp).getTime()),s=Math.min(...o),i=Math.max(...o),r=new Set(e.map($=>$.commitId)),a="",l="",c="",m="",g="";l+=`
    <rect x="0" y="${kt}" width="${n}" height="${Rt+16}" fill="#58a6ff" fill-opacity="0.03" rx="0"/>
    <rect x="0" y="${Yt}" width="${n}" height="${ie-Yt}" fill="#ffffff" fill-opacity="0.015"/>
    <rect x="0" y="${Lt}" width="${n}" height="${ae-Lt+6}" fill="#2dd4bf" fill-opacity="0.025"/>`;let p='stroke="#30363d" stroke-width="1" stroke-dasharray="4 4"';l+=`
    <line x1="${dt}" y1="132" x2="${n-Mt}" y2="132" ${p}/>
    <line x1="${dt}" y1="176" x2="${n-Mt}" y2="176" ${p}/>
    <line x1="${dt}" y1="252" x2="${n-Mt}" y2="252" ${p}/>`;let u='font-size="9" fill="#8b949e" text-anchor="middle" font-family="system-ui,sans-serif"';l+=`
    <text transform="rotate(-90, 18, ${kt+Rt/2})" x="18" y="${kt+Rt/2+3}" ${u}>EMOTION</text>
    <text transform="rotate(-90, 18, ${(Yt+ie)/2})" x="18" y="${(Yt+ie)/2+3}" ${u}>COMMITS</text>
    <text transform="rotate(-90, 18, ${(Lt+ae)/2})" x="18" y="${(Lt+ae)/2+3}" ${u}>EVENTS</text>`;let v=Math.min(8,e.length);for(let $=0;$<v;$++){let y=Math.round($*(e.length-1)/Math.max(1,v-1)),C=e[y],x=it(new Date(C.timestamp).getTime(),s,i,n),M=Ii(C.timestamp);g+=`
      <line x1="${x.toFixed(1)}" y1="${kt}" x2="${x.toFixed(1)}" y2="${Ce-hi}" stroke="#21262d" stroke-width="1"/>
      <text x="${x.toFixed(1)}" y="${Ce-10}" text-anchor="middle" font-size="10" fill="#6e7681" font-family="system-ui,sans-serif">${escHtml(M)}</text>`}if(a+=`
    <linearGradient id="tl-grad-val" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="tl-grad-eng" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3fb950" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#3fb950" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="tl-grad-ten" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f78166" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#f78166" stop-opacity="0.03"/>
    </linearGradient>`,ct.emotion&&Z.emotion){let $=Z.emotion.filter(y=>r.has(y.commitId));if($.length>=2){let y=x=>$.map(M=>({x:it(new Date(M.timestamp).getTime(),s,i,n),y:kt+Rt*(1-M[x])}));for(let x of[.25,.5,.75]){let M=kt+Rt*(1-x);c+=`<line x1="${dt}" y1="${M.toFixed(1)}" x2="${(n-Mt).toFixed(1)}" y2="${M.toFixed(1)}" stroke="#21262d" stroke-width="0.5" stroke-dasharray="2 4"/>`}let C=[["valence","#58a6ff","url(#tl-grad-val)"],["energy","#3fb950","url(#tl-grad-eng)"],["tension","#f78166","url(#tl-grad-ten)"]];for(let[x,M,N]of C){let A=y(x),O=A.map(J=>`${J.x.toFixed(1)},${J.y.toFixed(1)}`).join(" ");c+=`<path d="${Li(A,wi)}" fill="${N}"/>`,c+=`<polyline points="${O}" fill="none" stroke="${M}" stroke-width="1.5" stroke-linejoin="round" opacity="0.9"/>`}}}if(ct.commits){if(e.length>1){let y=it(s,s,i,n),C=it(i,s,i,n);c+=`<line x1="${y.toFixed(1)}" y1="${oe}" x2="${C.toFixed(1)}" y2="${oe}" stroke="#30363d" stroke-width="2"/>`}let $=new Map;(Z.emotion||[]).forEach(y=>$.set(y.commitId,y)),e.forEach((y,C)=>{let x=it(new Date(y.timestamp).getTime(),s,i,n),M=y.commitId.substring(0,8),N=escHtml((y.message||"").substring(0,60)),A=$.get(y.commitId),O="#58a6ff";if(A){let B=A.valence;B<.33?O="#f78166":B>.66?O="#3fb950":O="#58a6ff"}let J=`${M} \xB7 ${escHtml(y.branch)}<br>${N}<br>${escHtml(y.author)} \xB7 ${re(y.timestamp)}`,z=y.commitId;c+=`<line x1="${x.toFixed(1)}" y1="${Yt}" x2="${x.toFixed(1)}" y2="${ie}" stroke="#21262d" stroke-width="1"/>`,m+=`
        <g class="tl-commit-dot" data-id="${z}"
           onclick="window.openAudioModal && window.openAudioModal('${z}','${M}')"
           style="cursor:pointer"
           onmouseenter="window.tlShowTip && window.tlShowTip(event,'${J.replace(/'/g,"&#39;")}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <circle cx="${x.toFixed(1)}" cy="${oe}" r="7" fill="${O}" stroke="#0d1117" stroke-width="2" opacity="0.92"/>
          <circle cx="${x.toFixed(1)}" cy="${oe}" r="12" fill="transparent"/>
        </g>`})}ct.sections&&Z.sections&&Z.sections.filter(y=>r.has(y.commitId)).forEach(y=>{let C=it(new Date(y.timestamp).getTime(),s,i,n),x=escHtml(y.sectionName),M=y.action==="removed"?"#f78166":"#3fb950",N=y.action==="removed"?"\u2212":"+";m+=`
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${N} ${x} section')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <rect x="${(C-5).toFixed(1)}" y="${Sn-10}" width="10" height="10"
                fill="${M}" rx="2" opacity="0.9"/>
          <text x="${C.toFixed(1)}" y="${Sn+14}" text-anchor="middle"
                font-size="8" fill="${M}" font-family="system-ui,sans-serif">${x}</text>
        </g>`}),ct.tracks&&Z.tracks&&Z.tracks.filter(y=>r.has(y.commitId)).forEach((y,C)=>{let x=it(new Date(y.timestamp).getTime(),s,i,n),M=escHtml(y.trackName),N=y.action==="removed"?"#e3b341":"#a371f7",A=y.action==="removed"?"\u2212":"+",O=C%2*14;m+=`
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${A} ${M} track')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <circle cx="${x.toFixed(1)}" cy="${Bn+O}" r="4" fill="${N}" opacity="0.88"/>
          <text x="${(x+7).toFixed(1)}" y="${Bn+O+3}" font-size="8" fill="${N}" font-family="system-ui,sans-serif">${M}</text>
        </g>`}),ct.sessions&&Be.length>0&&He(Be,"startedAt",s,i).forEach(y=>{let C=it(new Date(y.startedAt).getTime(),s,i,n),x=escHtml((y.intent||"session").substring(0,50)),M=(y.participants||[]).map(A=>escHtml(A)).join(", ")||"no participants",N=`Session: ${x}<br>${M}<br>${re(y.startedAt)}`;m+=`
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${N.replace(/'/g,"&#39;")}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <line x1="${C.toFixed(1)}" y1="${Lt}" x2="${C.toFixed(1)}" y2="${ae}"
                stroke="#2dd4bf" stroke-width="1.5" stroke-dasharray="5 3" opacity="0.65"/>
          <circle cx="${C.toFixed(1)}" cy="${Lt+8}" r="5" fill="#2dd4bf" opacity="0.9"/>
        </g>`}),ct.prs&&_e.length>0&&He(_e,"createdAt",s,i).forEach(y=>{let C=y.mergedAt?new Date(y.mergedAt).getTime():new Date(y.createdAt).getTime(),x=it(C,s,i,n),M=escHtml((y.title||"PR").substring(0,50)),N=y.mergedAt?y.mergedAt:y.createdAt,A=Ei;m+=`
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'PR merge: ${M}<br>${re(N)}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <line x1="${x.toFixed(1)}" y1="${Lt+14}" x2="${x.toFixed(1)}" y2="${A}"
                stroke="#a371f7" stroke-width="1.5" opacity="0.6"/>
          <polygon points="${x},${A+9} ${x-6},${A-1} ${x+6},${A-1}"
                   fill="#a371f7" opacity="0.92"/>
        </g>`}),ct.releases&&Ae.length>0&&He(Ae,"createdAt",s,i).forEach(y=>{let C=it(new Date(y.createdAt).getTime(),s,i,n),x=escHtml((y.tag||"").substring(0,16)),M=xi;m+=`
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'Release: ${x}<br>${re(y.createdAt)}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <polygon points="${C},${M-8} ${C+6},${M} ${C},${M+8} ${C-6},${M}"
                   fill="#e3b341" stroke="#0d1117" stroke-width="1" opacity="0.95"/>
          <text x="${C.toFixed(1)}" y="${M+20}" text-anchor="middle"
                font-size="8" fill="#e3b341" font-family="system-ui,sans-serif">${x}</text>
        </g>`}),t.innerHTML=`
    <svg id="timeline-svg" width="${n}" height="${Ce}"
         xmlns="http://www.w3.org/2000/svg"
         style="display:block;background:#0d1117">
      <defs>${a}</defs>
      ${l}
      ${g}
      ${c}
      ${m}
    </svg>`;let h=document.getElementById("scrubber-thumb");h&&(h.style.left=_n*100+"%");let L=document.getElementById("tl-visible-count");L&&(L.textContent=`${e.length} commit${e.length!==1?"s":""}`)}function ki(){let t=document.getElementById("tl-tooltip");t||(t=document.createElement("div"),t.id="tl-tooltip",t.className="tl-tooltip",document.body.appendChild(t));let e=t;window.tlShowTip=(n,o)=>{e.innerHTML=o,e.style.display="block",e.style.left=n.clientX+14+"px",e.style.top=n.clientY-8+"px"},window.tlHideTip=()=>{e.style.display="none"}}function Mi(t){let e=Math.floor((Date.now()-new Date(t).getTime())/1e3);if(e<60)return"just now";let n=Math.floor(e/60);if(n<60)return`${n}m ago`;let o=Math.floor(n/60);return o<24?`${o}h ago`:`${Math.floor(o/24)}d ago`}function Se(t){if(!isFinite(t)||t<0)return"\u2014";let e=Math.floor(t/60),n=String(Math.floor(t%60)).padStart(2,"0");return`${e}:${n}`}function Ci(t){let e=[],n=/\b(\d{2,3})\s*(?:bpm|BPM)\b/.exec(t);n&&e.push({cls:"am-bpm",label:`\u2669 ${n[1]} BPM`});let o=/\b([A-G][b#]?(?:m(?:aj(?:or)?)?|min(?:or)?|M)?)\b/.exec(t);o&&e.push({cls:"am-key",label:`\u{1F3B5} ${o[1]}`});let s=/emotion:([\w-]+)/i.exec(t);s&&e.push({cls:"",label:`\u{1F49C} ${s[1]}`});let i=/\b(piano|bass|drums?|keys|strings?|guitar|synth|pad|lead|brass|horn|flute|cello|violin|organ|arp|vocals?|percussion|kick|snare|hihat|hi-hat|clap)\b/gi,r=[...new Set([...t.matchAll(i)].map(a=>a[1].toLowerCase()))].slice(0,3);return r.length&&e.push({cls:"am-instr",label:r.join(" \xB7 ")}),e}function Hi(){window.openAudioModal=(t,e)=>{document.getElementById("audio-modal")?.remove();let n=Z?.commits?.find(x=>x.commitId===t),o=n?.message??e,s=n?.author??"?",i=n?.branch??"",r=n?.timestamp??"",a=r?Mi(r):"",l=s[0]?.toUpperCase()??"?",c=Ci(o),m=`/api/v1/repos/${mt.repoId}/commits/${t}/audio`,g=`${mt.baseUrl}/commits/${t}`,d=c.map(x=>`<span class="am-badge ${escHtml(x.cls)}">${escHtml(x.label)}</span>`).join(""),p=document.createElement("div");p.id="audio-modal",p.className="audio-modal",p.setAttribute("role","dialog"),p.setAttribute("aria-modal","true"),p.setAttribute("aria-label",`Audio preview \u2014 commit ${e}`),p.innerHTML=`
      <div class="am-box" id="am-box">

        <div class="am-header">
          <span class="am-header-icon">\u{1F3A7}</span>
          <span class="am-header-title">Audio Preview</span>
          <span class="am-sha">${escHtml(e)}</span>
          <button class="am-close-btn" id="am-close-btn" title="Close (Esc)" aria-label="Close">\u2715</button>
        </div>

        <div class="am-body">
          <div class="am-message">${escHtml(o)}</div>

          <div class="am-meta">
            <span class="am-avatar">${escHtml(l)}</span>
            <span class="am-author">${escHtml(s)}</span>
            ${i?`<span class="am-branch">\u2442 ${escHtml(i)}</span>`:""}
            ${a?`<span title="${escHtml(r)}">${escHtml(a)}</span>`:""}
          </div>

          ${d?`<div class="am-badges">${d}</div>`:""}

          <div class="am-player" id="am-player">
            <div class="am-player-row">
              <button class="am-play-btn" id="am-play-btn" title="Play / Pause" disabled>\u25B6</button>
              <div class="am-progress-wrap" id="am-prog-wrap">
                <div class="am-progress-fill" id="am-prog-fill"></div>
              </div>
              <span class="am-time" id="am-time">Loading\u2026</span>
            </div>
          </div>
        </div>

        <div class="am-footer">
          <a href="${escHtml(g)}" class="btn btn-secondary btn-sm">View commit \u2197</a>
          <button class="btn btn-ghost btn-sm" id="am-close-btn-2">Close</button>
        </div>

      </div>
      <audio id="am-audio" preload="none" style="display:none">
        <source src="${escHtml(m)}" type="audio/mpeg">
      </audio>`;let u=()=>p.remove();p.addEventListener("click",x=>{x.target===p&&u()}),p.querySelector("#am-close-btn")?.addEventListener("click",u),p.querySelector("#am-close-btn-2")?.addEventListener("click",u);let v=x=>{x.key==="Escape"&&(u(),document.removeEventListener("keydown",v))};document.addEventListener("keydown",v),p.addEventListener("remove",()=>document.removeEventListener("keydown",v)),document.body.appendChild(p);let h=p.querySelector("#am-audio"),L=p.querySelector("#am-play-btn"),$=p.querySelector("#am-prog-wrap"),y=p.querySelector("#am-prog-fill"),C=p.querySelector("#am-time");h.addEventListener("canplaythrough",()=>{L.disabled=!1,C.textContent=`0:00 / ${Se(h.duration)}`}),h.addEventListener("error",()=>{L.disabled=!0,C.textContent="No audio",p.querySelector("#am-player").innerHTML=`<div class="am-no-audio">\u{1F507} No audio available for this commit.<br>
         <a href="${escHtml(g)}" style="color:var(--color-accent)">View full commit \u2192</a></div>`}),h.addEventListener("timeupdate",()=>{let x=h.duration?h.currentTime/h.duration*100:0;y.style.width=`${x}%`,C.textContent=`${Se(h.currentTime)} / ${Se(h.duration)}`}),h.addEventListener("ended",()=>{L.textContent="\u25B6"}),L.addEventListener("click",()=>{h.paused?(h.play().catch(()=>{C.textContent="Playback error"}),L.textContent="\u23F8"):(h.pause(),L.textContent="\u25B6")}),$.addEventListener("click",x=>{if(!h.duration)return;let M=$.getBoundingClientRect();h.currentTime=(x.clientX-M.left)/M.width*h.duration}),h.load()}}function Si(){let t=document.getElementById("scrubber-bar");if(!t)return;let e=!1;function n(o){let s=t.getBoundingClientRect(),i=Math.max(0,Math.min(1,(o.clientX-s.left)/s.width));_n=i;let r=document.getElementById("scrubber-thumb");r&&(r.style.left=i*100+"%"),Pt()}t.addEventListener("mousedown",o=>{e=!0,n(o)}),document.addEventListener("mousemove",o=>{e&&n(o)}),document.addEventListener("mouseup",()=>{e=!1})}function Bi(){document.querySelectorAll("[data-layer]").forEach(t=>{t.addEventListener("change",()=>{ct[t.dataset.layer]=t.checked,Pt()})}),document.querySelectorAll("[data-zoom]").forEach(t=>{t.addEventListener("click",()=>{let e=t.dataset.zoom;Re=e,document.querySelectorAll("[data-zoom]").forEach(n=>{n.classList.toggle("active",n.dataset.zoom===e)}),Pt()})})}window.toggleLayer=(t,e)=>{ct[t]=e,Pt()};window.setZoom=t=>{Re=t,document.querySelectorAll("[data-zoom]").forEach(e=>{e.classList.toggle("active",e.dataset.zoom===t)}),Pt()};async function _i(){let[t,e,n]=await Promise.allSettled([apiFetch("/repos/"+mt.repoId+"/sessions?limit=200"),apiFetch("/repos/"+mt.repoId+"/pull-requests?state=merged"),apiFetch("/repos/"+mt.repoId+"/releases")]);t.status==="fulfilled"&&t.value&&(Be=t.value.sessions??[]),e.status==="fulfilled"&&e.value&&(_e=e.value.pullRequests??[]),n.status==="fulfilled"&&n.value&&(Ae=n.value.releases??[])}function An(){mt=window.__timelineCfg,mt&&(initRepoNav(mt.repoId),ki(),Hi(),Si(),Bi(),(async()=>{try{let[t]=await Promise.all([apiFetch("/repos/"+mt.repoId+"/timeline?limit=200"),_i()]);Z=t;let e=document.getElementById("tl-total-count");e&&t.totalCommits&&(e.textContent=String(t.totalCommits)),Pt()}catch(t){let e=t;if(e.message!=="auth"){let n=document.getElementById("timeline-svg-container");n&&(n.innerHTML=`<div class="tl-loading"><div class="tl-loading-inner error">
            \u2715 ${escHtml(e.message)}
          </div></div>`)}}})())}var Rn={NONE:"#6e7681",LOW:"#58a6ff",MED:"#e3b341",HIGH:"#f85149"},Pe=["melodic","harmonic","rhythmic","structural","dynamic"],Xt;function Ai(t,e=260){let n=e/2,o=e/2,s=e*.36,i=t.length,r=Array.from({length:i},(d,p)=>-Math.PI/2+2*Math.PI/i*p),a=(d,p)=>({x:n+d*s*Math.cos(r[p]),y:o+d*s*Math.sin(r[p])}),l=d=>r.map(p=>`${(n+s*d*Math.cos(p)).toFixed(1)},${(o+s*d*Math.sin(p)).toFixed(1)}`).join(" "),c=t.map((d,p)=>{let{x:u,y:v}=a(d.score,p);return`${u.toFixed(1)},${v.toFixed(1)}`}).join(" "),m=`<svg width="${e}" height="${e}" viewBox="0 0 ${e} ${e}" xmlns="http://www.w3.org/2000/svg">`;m+=`<rect width="${e}" height="${e}" fill="#0d1117" rx="10"/>`;for(let d of[.25,.5,.75,1]){let p=d===1?1.5:1;m+=`<polygon points="${l(d)}" fill="none" stroke="#21262d" stroke-width="${p}"/>`}r.forEach(d=>{m+=`<line x1="${n.toFixed(1)}" y1="${o.toFixed(1)}" x2="${(n+s*Math.cos(d)).toFixed(1)}" y2="${(o+s*Math.sin(d)).toFixed(1)}" stroke="#21262d" stroke-width="1"/>`}),m+=`<polygon points="${c}" fill="rgba(88,166,255,0.10)" stroke="#388bfd" stroke-width="2" stroke-linejoin="round"/>`,t.forEach((d,p)=>{let{x:u,y:v}=a(d.score,p),h=Rn[d.level]??"#6e7681";m+=`<circle cx="${u.toFixed(1)}" cy="${v.toFixed(1)}" r="5" fill="${h}" stroke="#0d1117" stroke-width="1.5"/>`});let g=["Melodic","Harmonic","Rhythmic","Structural","Dynamic"];return r.forEach((d,p)=>{let u=(n+s*1.28*Math.cos(d)).toFixed(1),v=(o+s*1.28*Math.sin(d)+4).toFixed(1),h=Math.abs(Math.cos(d))<.2?"middle":Math.cos(d)<0?"end":"start";m+=`<text x="${u}" y="${v}" text-anchor="${h}" font-size="10" fill="#8b949e" font-family="system-ui,sans-serif">${escHtml(g[p]??Pe[p]??"")}</text>`}),m+="</svg>",m}function Ri(t){return[...t].sort((n,o)=>{let s=Pe.indexOf(n.dimension.toLowerCase()),i=Pe.indexOf(o.dimension.toLowerCase());return(s===-1?99:s)-(i===-1?99:i)}).map(n=>{let o=Math.round(n.score*100),s=Rn[n.level]??"#6e7681";return`
      <div class="an-dim-card">
        <div class="an-dim-header">
          <span class="an-dim-name">${escHtml(n.dimension)}</span>
          <span class="an-dim-level an-level-${n.level.toLowerCase()}">${n.level}</span>
          <span class="an-dim-pct">${o}%</span>
        </div>
        <div class="an-dim-bar-track">
          <div class="an-dim-bar-fill" style="width:${o}%;background:${s}"></div>
        </div>
        <p class="an-dim-desc">${escHtml(n.description)}</p>
        <div class="an-dim-commits">
          <span class="an-dim-commit-pill">Branch A \xB7 ${n.branchACommits} commits</span>
          <span class="an-dim-commit-pill">Branch B \xB7 ${n.branchBCommits} commits</span>
        </div>
      </div>`}).join("")}function Pi(t){let e=document.getElementById("an-gauge-circle");if(!e)return;let n=t>=75?"#f85149":t>=50?"#e3b341":t>=20?"#388bfd":"#3fb950";e.style.background=`conic-gradient(${n} ${t}%, #21262d 0)`;let o=document.getElementById("an-gauge-pct");o&&(o.textContent=`${t}%`);let s=document.getElementById("an-gauge-label");s&&(s.textContent=t>=75?"Heavily diverged":t>=50?"Significantly diverged":t>=20?"Mildly diverged":"Nearly identical")}async function Di(t,e){let n=document.getElementById("an-radar-svg"),o=document.getElementById("an-dim-cards"),s=document.getElementById("an-ancestor");n&&(n.innerHTML='<div class="an-loading-sm">Computing divergence\u2026</div>'),o&&(o.innerHTML='<div class="an-loading-sm">Loading dimensions\u2026</div>');try{let i=await apiFetch(`/repos/${Xt.repoId}/divergence?branch_a=${encodeURIComponent(t)}&branch_b=${encodeURIComponent(e)}`),r=Math.round(i.overallScore*100);if(Pi(r),n&&(n.innerHTML=Ai(i.dimensions)),o&&(o.innerHTML=Ri(i.dimensions)),s){let a=i.commonAncestor?i.commonAncestor.substring(0,8):"none";s.textContent=`Common ancestor: ${a}`}}catch(i){let r=i.message??"",a=r;try{let m=r.indexOf(":");if(m!==-1){let g=r.slice(m+1).trim(),d=JSON.parse(g);d.detail&&(a=d.detail)}}catch{}let l=a.toLowerCase().includes("no commits"),c=l?`Branch <strong>${escHtml(t===Xt.defaultBranch?e:t)}</strong> has no commits yet \u2014 push at least one commit to enable divergence analysis.`:escHtml(a);o&&(o.innerHTML=`<div class="an-loading-sm ${l?"":"error"}" style="text-align:left;padding:16px">${c}</div>`),n&&!l&&(n.innerHTML=`<div class="an-loading-sm error">\u2715 ${escHtml(a)}</div>`)}}function Pn(){if(Xt=window.__analysisCfg,!Xt)return;initRepoNav(Xt.repoId);let t=document.getElementById("an-branch-a"),e=document.getElementById("an-branch-b"),n=s=>s?s.options[s.selectedIndex]?.dataset.noCommits!=="true":!0,o=()=>{let s=t?.value,i=e?.value;if(!s||!i)return;let r=n(t),a=n(e);if(!r||!a){let l=escHtml(r?i:s),c=document.getElementById("an-dim-cards");c&&(c.innerHTML=`
          <div class="an-loading-sm" style="text-align:left;padding:16px">
            Branch <strong>${l}</strong> has no commits yet \u2014
            push at least one commit to that branch to enable divergence analysis.
          </div>`);return}Di(s,i)};t?.addEventListener("change",o),e?.addEventListener("change",o),document.getElementById("an-compare-btn")?.addEventListener("click",o),window.onBranchChange=o}function Dn(t,e=document){return Array.from(e.querySelectorAll(t))}function Ni(){let t=document.getElementById("in-tooltip");if(!t)return;function e(o,s,i){t.textContent=o,t.style.left=`${s+14}px`,t.style.top=`${i-28}px`,t.classList.add("in-tooltip--visible")}function n(){t.classList.remove("in-tooltip--visible")}Dn(".in-heatmap-day[data-count]").forEach(o=>{o.addEventListener("mouseenter",s=>{let i=o,r=i.dataset.date??"",a=i.dataset.count??"0";if(!r)return;let l=a==="0"?`No commits on ${r}`:`${a} commit${a==="1"?"":"s"} on ${r}`,c=i.getBoundingClientRect();e(l,c.left+window.scrollX,c.top+window.scrollY)}),o.addEventListener("mouseleave",n)})}function Fi(t){let e=document.getElementById("in-bpm-dots"),n=document.getElementById("in-tooltip");if(!e||!n||t.bpmPoints.length<2)return;let o=t.bpmPoints,s=o.map(l=>l.bpm),i=Math.min(...s),r=Math.max(...s),a=Math.max(r-i,10);o.forEach((l,c)=>{let m=(c/(o.length-1)*580+10).toFixed(1),g=((1-(l.bpm-i)/a)*60+10).toFixed(1),d=document.createElementNS("http://www.w3.org/2000/svg","circle");d.setAttribute("cx",m),d.setAttribute("cy",g),d.setAttribute("r","3"),d.setAttribute("class","in-bpm-dot"),d.setAttribute("data-bpm",String(l.bpm)),d.setAttribute("data-ts",l.ts),d.addEventListener("mouseenter",p=>{let u=l.ts.slice(0,10),v=p;n.textContent=`${l.bpm} BPM \xB7 ${u}`,n.style.left=`${v.clientX+14}px`,n.style.top=`${v.clientY-28}px`,n.classList.add("in-tooltip--visible"),d.setAttribute("r","5")}),d.addEventListener("mouseleave",()=>{n.classList.remove("in-tooltip--visible"),d.setAttribute("r","3")}),e.appendChild(d)})}function ji(){let t=Dn(".js-bar-fill");if(!t.length)return;let e=new IntersectionObserver(n=>{n.forEach(o=>{if(!o.isIntersecting)return;let s=o.target,i=s.style.getPropertyValue("--bar-pct")||"0%";s.style.width="0%",requestAnimationFrame(()=>{s.style.transition="width 0.7s cubic-bezier(0.25, 0.46, 0.45, 0.94)",s.style.width=i}),e.unobserve(s)})},{threshold:.1});t.forEach(n=>e.observe(n))}function Nn(){let t=window.__insightsCfg;t&&(Ni(),ji(),t.bpmPoints.length>=2&&Fi(t))}function Oi(t){return t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}function De(t,e){if(!e||e.length<2)return;let n=e.trim().split(/\s+/).filter(s=>s.length>1);if(!n.length)return;let o=new RegExp(`(${n.map(Oi).join("|")})`,"gi");t.querySelectorAll("[data-highlight]").forEach(s=>{let i=s.textContent??"";o.test(i)&&(o.lastIndex=0,s.innerHTML=i.replace(o,'<mark class="sr-hl">$1</mark>'))})}function Fn(t,e,n){let o=document.querySelector(t),s=document.getElementById(e),i=document.getElementById(n);!o||!s||!i||(o.querySelectorAll("[data-mode]").forEach(r=>{r.addEventListener("click",()=>{s.value=r.dataset.mode??"keyword",o.querySelectorAll("[data-mode]").forEach(a=>a.classList.remove("sr-mode-pill--active")),r.classList.add("sr-mode-pill--active"),i.dispatchEvent(new Event("submit",{bubbles:!0}))})}),o.querySelectorAll("[data-global-mode]").forEach(r=>{let a=document.getElementById("sr-global-mode");a&&r.addEventListener("click",()=>{a.value=r.dataset.globalMode??"keyword",o.querySelectorAll("[data-global-mode]").forEach(l=>l.classList.remove("sr-mode-pill--active")),r.classList.add("sr-mode-pill--active"),i.dispatchEvent(new Event("submit",{bubbles:!0}))})}))}function zi(){document.body.addEventListener("htmx:afterSwap",t=>{let e=t.detail?.target;if(!e)return;let o=document.getElementById("sr-q")?.value??window.__searchCfg?.query??"";De(e,o)})}function Ne(){let e=window.__searchCfg?.query??"",n=document.getElementById("sr-results");n&&e&&De(n,e);let o=document.getElementById("sr-global-results");o&&e&&De(o,e),Fn(".sr-mode-bar","sr-mode-hidden","sr-form"),Fn(".sr-mode-bar","sr-global-mode","sr-global-form"),zi()}function Ui(){let t=document.getElementById("ar-tooltip"),e=document.getElementById("ar-tip-title"),n=document.getElementById("ar-tip-notes"),o=document.getElementById("ar-tip-density"),s=document.getElementById("ar-tip-beats");if(!t)return;function i(a,l,c){let m=a.dataset.instrument??"",g=a.dataset.section??"",d=a.dataset.notes??"0",p=parseFloat(a.dataset.density??"0"),u=a.dataset.beatStart??"0",v=a.dataset.beatEnd??"0";e&&(e.textContent=`${m.charAt(0).toUpperCase()+m.slice(1)} \xB7 ${g.replace(/_/g," ")}`),n&&(n.textContent=d),o&&(o.textContent=`${(p*100).toFixed(0)}%`),s&&(s.textContent=`${parseFloat(u).toFixed(0)}\u2013${parseFloat(v).toFixed(0)}`),t.style.left=`${l+16}px`,t.style.top=`${c-16}px`,t.classList.add("ar-tooltip--visible")}function r(){t.classList.remove("ar-tooltip--visible")}document.querySelectorAll(".ar-cell[data-notes]").forEach(a=>{a.addEventListener("mouseenter",l=>{let c=l;i(a,c.clientX,c.clientY)}),a.addEventListener("mousemove",l=>{let c=l;t.style.left=`${c.clientX+16}px`,t.style.top=`${c.clientY-16}px`}),a.addEventListener("mouseleave",r)})}function qi(){document.querySelectorAll("#ar-matrix tbody tr").forEach(e=>{e.addEventListener("mouseenter",()=>e.classList.add("ar-row-hover")),e.addEventListener("mouseleave",()=>e.classList.remove("ar-row-hover"))})}function Wi(){let t=document.getElementById("ar-matrix");if(!t)return;let e=null;function n(o){t.querySelectorAll(".ar-col-hover").forEach(s=>s.classList.remove("ar-col-hover")),o!==null&&t.querySelectorAll(`[data-col="${o}"]`).forEach(s=>s.classList.add("ar-col-hover"))}t.querySelectorAll("[data-col]").forEach(o=>{o.addEventListener("mouseenter",()=>{let s=parseInt(o.dataset.col??"-1",10);s>=0&&(e=s,n(s))}),o.addEventListener("mouseleave",()=>{e=null,n(null)})})}function Gi(){let t=document.querySelectorAll(".ar-panel-bar-fill");if(!t.length)return;let e=new IntersectionObserver(n=>{n.forEach(o=>{if(!o.isIntersecting)return;let s=o.target,i=s.style.width;s.style.width="0%",requestAnimationFrame(()=>{s.style.transition="width 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94)",s.style.width=i}),e.unobserve(s)})},{threshold:.15});t.forEach(n=>e.observe(n))}function Yi(){document.querySelectorAll(".ar-cell-bar-fill").forEach(t=>{let e=t.style.width;t.style.width="0%",setTimeout(()=>{t.style.transition="width 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)",t.style.width=e},100+Math.random()*200)})}function jn(){Ui(),qi(),Wi(),Gi(),Yi()}function Xi(t){let e=Date.now()-new Date(t).getTime(),n=Math.floor(e/1e3);if(n<60)return"just now";let o=Math.floor(n/60);if(o<60)return`${o}m ago`;let s=Math.floor(o/60);return s<24?`${s}h ago`:`${Math.floor(s/24)}d ago`}function Fe(){document.querySelectorAll("[data-iso]").forEach(t=>{let e=t.dataset.iso;e&&(t.textContent=Xi(e))})}function On(t=document.body){let e=t.querySelectorAll(".av-row, .av-date-header");if(!e.length)return;let n=new IntersectionObserver(o=>{o.forEach((s,i)=>{if(!s.isIntersecting)return;let r=s.target;r.style.animationDelay=`${i*30}ms`,r.classList.add("av-row--visible"),n.unobserve(r)})},{threshold:.05});e.forEach(o=>{o.classList.add("av-row--hidden"),n.observe(o)})}function Vi(){document.body.addEventListener("htmx:afterSwap",t=>{let e=t.detail?.target;e&&(e.id==="av-feed"||e.closest("#av-feed"))&&(On(e),Fe())})}function zn(){On(),Fe(),setInterval(Fe,6e4),Vi()}function Ji(){let t=document.querySelectorAll(".pd-dim-row");if(!t.length)return;let e=new IntersectionObserver(n=>{n.forEach(o=>{if(!o.isIntersecting)return;let s=o.target,i=s.querySelector(".pd-dim-fill"),r=s.dataset.target??"0";i&&(i.style.width="0",requestAnimationFrame(()=>{i.style.width=`${r}%`})),e.unobserve(s)})},{threshold:.2});t.forEach(n=>e.observe(n))}function Ki(){document.addEventListener("click",async t=>{let e=t.target.closest("[data-sha]");if(!e)return;let n=e.dataset.sha;if(n)try{await navigator.clipboard.writeText(n);let o=e.textContent??"";e.textContent="\u2713",setTimeout(()=>{e.textContent=o},1500)}catch{}})}function Zi(){let t=document.querySelectorAll(".pd-strategy"),e=document.querySelector("#merge-btn");if(!t.length||!e)return;let n={merge_commit:"\u2713 Merge pull request",squash:"\u2B1C Squash and merge",rebase:"\u{1F504} Rebase and merge"};t.forEach(o=>{o.addEventListener("click",()=>{let s=o.dataset.strategy??"merge_commit";t.forEach(i=>i.classList.remove("active")),o.classList.add("active"),e.setAttribute("hx-vals",JSON.stringify({mergeStrategy:s,deleteBranch:!0})),e.textContent=n[s]??"\u2713 Merge"})})}function Un(){Ji(),Ki(),Zi()}function Qi(t){let e=new URL(window.location.href);for(let[n,o]of Object.entries(t))o==null||o===""?e.searchParams.delete(n):e.searchParams.set(n,String(o));return e.toString()}function ta(){let t=document.getElementById("branch-sel");t&&t.addEventListener("change",()=>{window.location.href=Qi({branch:t.value||null,page:1})})}var Dt=!1,Ct=new Set;function Wn(){let t=document.getElementById("compare-strip"),e=document.getElementById("compare-count"),n=document.getElementById("compare-link"),o=window.__commitsCfg;if(!t)return;let s=Ct.size;if(e&&(e.textContent=`${s} selected`),s===2&&n&&o){let[i,r]=[...Ct];n.href=`${o.base}/compare/${i}...${r}`,n.style.display=""}else n&&(n.style.display="none");t.classList.toggle("visible",Dt)}function qn(){Dt=!Dt,document.body.classList.toggle("compare-mode",Dt),Ct.clear(),document.querySelectorAll(".compare-check").forEach(e=>{e.checked=!1}),document.querySelectorAll(".commit-list-row").forEach(e=>e.classList.remove("compare-selected")),Wn();let t=document.getElementById("compare-toggle-btn");t&&(t.textContent=Dt?"\u2715 Exit Compare":"\u229E Compare")}function ea(t,e){let n=t.closest(".commit-list-row");if(t.checked){if(Ct.size>=2){t.checked=!1;return}Ct.add(e),n?.classList.add("compare-selected")}else Ct.delete(e),n?.classList.remove("compare-selected");Wn()}function na(){document.getElementById("compare-toggle-btn")?.addEventListener("click",qn),document.getElementById("compare-cancel-btn")?.addEventListener("click",qn),document.addEventListener("change",t=>{let e=t.target.closest(".compare-check");if(!e)return;let n=e.dataset.commitId??e.closest(".commit-list-row")?.dataset.commitId;n&&ea(e,n)})}function sa(){document.body.addEventListener("htmx:afterSwap",()=>{Ct.forEach(t=>{let e=document.querySelector(`[data-commit-id="${t}"]`),n=e?.querySelector(".compare-check");e&&n&&(e.classList.add("compare-selected"),n.checked=!0)}),Dt&&document.body.classList.add("compare-mode")})}function Gn(){ta(),na(),sa()}function Yn(t=document){let e=t.querySelectorAll(".id-comment, .id-reply");if(!e.length)return;let n=new IntersectionObserver(o=>{o.forEach((s,i)=>{if(!s.isIntersecting)return;let r=s.target;r.style.animationDelay=`${i*30}ms`,n.unobserve(r)})},{threshold:.05});e.forEach(o=>n.observe(o))}function oa(){let t=document.querySelector(".id-ms-fill");if(!t)return;let e=t.style.width;t.style.width="0",requestAnimationFrame(()=>{t.style.transition="width 0.6s ease",t.style.width=e})}function ia(){document.body.addEventListener("htmx:afterSwap",t=>{let e=t.detail?.target;e&&(e.id==="issue-comments"||e.closest("#issue-comments"))&&Yn(e)})}function aa(){document.addEventListener("keydown",async t=>{if(t.key!=="y"||t.ctrlKey||t.metaKey||t.altKey)return;let e=document.activeElement;if(!(e&&(e.tagName==="INPUT"||e.tagName==="TEXTAREA")))try{await navigator.clipboard.writeText(window.location.href)}catch{}})}function Xn(){Yn(),oa(),ia(),aa()}function je(t){return!isFinite(t)||t<0?"\u2014":`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,"0")}`}function ra(){let t=document.getElementById("rd-audio"),e=document.getElementById("rd-play-btn"),n=document.getElementById("rd-progress-wrap"),o=document.getElementById("rd-progress-fill"),s=document.getElementById("rd-time"),i=document.getElementById("rd-player"),r=document.getElementById("rd-audio-error");t&&(t.addEventListener("canplaythrough",()=>{e&&(e.disabled=!1),s&&(s.textContent=`0:00 / ${je(t.duration)}`)}),t.addEventListener("timeupdate",()=>{let a=t.duration?t.currentTime/t.duration*100:0;o&&(o.style.width=`${a}%`),s&&(s.textContent=`${je(t.currentTime)} / ${je(t.duration)}`)}),t.addEventListener("ended",()=>{e&&(e.textContent="\u25B6")}),t.addEventListener("error",()=>{i&&(i.style.display="none"),r&&r.classList.add("visible"),s&&(s.textContent="\u2014")}),e&&e.addEventListener("click",()=>{t.paused?(t.play().catch(()=>{i&&(i.style.display="none"),r&&r.classList.add("visible")}),e.textContent="\u23F8"):(t.pause(),e.textContent="\u25B6")}),n&&n.addEventListener("click",a=>{if(!t.duration)return;let l=n.getBoundingClientRect();t.currentTime=(a.clientX-l.left)/l.width*t.duration}),t.load())}function la(){let t=document.querySelectorAll(".rd-asset-row, .rd-dl-card");if(!t.length)return;let e=new IntersectionObserver(n=>{n.forEach((o,s)=>{if(!o.isIntersecting)return;let i=o.target;i.style.animationDelay=`${s*40}ms`,e.unobserve(i)})},{threshold:.05});t.forEach(n=>e.observe(n))}function Vn(){ra(),la()}var ca=["#58a6ff","#3fb950","#f0883e","#bc8cff","#ff7b72","#79c0ff","#56d364","#ffa657","#d2a8ff","#ff9492","#2dd4bf","#fbbf24"],da=["#58a6ff","#3fb950","#bc8cff","#fbbf24","#f0883e","#2dd4bf","#ff9492","#a78bfa"],Ue={feat:"#3fb950",fix:"#f85149",refactor:"#bc8cff",init:"#58a6ff",docs:"#8b949e",style:"#fbbf24",test:"#2dd4bf",chore:"#484f58",perf:"#f0883e"},ma="#2dd4bf",Oe="#f0883e",le=11,ce=44,Vt=28,Jt=24,de=20,Jn=16,tt=1,Ft=0,jt=0,qe=null,ua={},pa={};function Zn(t,e,n){if(n[t])return n[t];let o=0;for(let i=0;i<t.length;i++)o=o*31+t.charCodeAt(i)|0;let s=e[Math.abs(o)%e.length];return n[t]=s,s}function Nt(t){return Zn(t,ca,ua)}function ze(t){return Zn(t,da,pa)}function Kn(t){let e=t.match(/^(\w+)[\(!\:]/);return e?e[1].toLowerCase():null}function ga(t){return Ue[t]||null}function fa(t){let e={},n=0;t.forEach(s=>{e[s.branch]===void 0&&(e[s.branch]=n++)});let o={};return t.forEach((s,i)=>{o[s.commitId]={col:e[s.branch],row:i}}),{pos:o,maxCol:n,branchCol:e}}function Kt(){qe&&qe.setAttribute("transform",`translate(${Ft},${jt}) scale(${tt})`)}function va(t,e,n){let{nodes:o,edges:s,headCommitId:i}=t,r=document.getElementById("dag-loading"),a=document.getElementById("dag-svg");if(r&&(r.style.display="none"),!o.length||!a){a&&(a.style.display="none");let b=document.getElementById("dag-viewport");b&&(b.innerHTML='<div style="padding:40px;text-align:center;color:var(--text-muted)">No commits yet.</div>');return}let{pos:l,maxCol:c,branchCol:m}=fa(o),g={};o.forEach(b=>{g[b.commitId]=b});let d={};o.forEach(b=>{d[b.author]=(d[b.author]||0)+1});let p=Object.entries(d).sort((b,E)=>E[1]-b[1]),u=o.filter(b=>(b.parentIds||[]).length>1).length,v=document.getElementById("stat-authors"),h=document.getElementById("stat-merges");v&&(v.textContent=String(p.length)),h&&(h.textContent=String(u));let L=Object.keys(m).sort((b,E)=>m[b]-m[E]),$=document.getElementById("legend-branches");$&&($.innerHTML=L.map(b=>`<span class="graph-legend-branch">
        <span class="graph-legend-dot" style="background:${Nt(b)}"></span>
        ${window.escHtml(b)}
      </span>`).join(""));let y={};o.forEach(b=>{y[b.branch]=(y[b.branch]||0)+1});let C=document.getElementById("sidebar-branch-list");C&&(C.innerHTML=L.map(b=>`<div class="branch-legend-item">
        <span class="branch-legend-pill" style="background:${Nt(b)}"></span>
        <span style="font-size:12px;color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${window.escHtml(b)}</span>
        <span class="branch-legend-count">${y[b]||0}</span>
      </div>`).join(""));let x=p[0]?p[0][1]:1,M=document.getElementById("sidebar-contributor-list");M&&(M.innerHTML=p.map(([b,E])=>{let H=Math.round(E/x*100),I=ze(b);return`<div class="contributor-item">
        <span class="contributor-avatar-sm" style="background:${I}">${window.escHtml(b[0].toUpperCase())}</span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:4px">
            <span class="contributor-name">${window.escHtml(b)}</span>
            <span class="contributor-count">${E}</span>
          </div>
          <div class="contributor-bar">
            <div class="contributor-bar-fill" style="width:${H}%;background:${I}"></div>
          </div>
        </div>
      </div>`}).join(""));let N=Jt+c*Vt+Jn+520,A=de*2+o.length*ce;a.setAttribute("width",String(N)),a.setAttribute("height",String(A)),a.style.display="block";let O=`<defs>
    <style>
      @keyframes spin { to { transform: rotate(360deg); } }
      .dag-node { cursor: pointer; }
      .dag-edge  { transition: opacity 0.15s; }
    </style>
  </defs>`,J="";s.forEach(b=>{let E=l[b.source],H=l[b.target];if(!E||!H)return;let I=Jt+E.col*Vt,V=de+E.row*ce,j=Jt+H.col*Vt,at=de+H.row*ce,Q=g[b.source],rt=Q?Nt(Q.branch):"#8b949e",bt=(V+at)/2;J+=`<path d="M${I},${V} C${I},${bt} ${j},${bt} ${j},${at}"
      stroke="${rt}" stroke-width="2" fill="none" opacity="0.55" class="dag-edge"/>`});let z="",B="",gt=Jt+c*Vt+Jn;o.forEach(b=>{let E=l[b.commitId],H=Jt+E.col*Vt,I=de+E.row*ce,V=Nt(b.branch),j=ze(b.author),at=b.commitId===i||b.isHead,Q=(b.parentIds||[]).length>1,rt=!!e[b.commitId],bt=(b.author||"?")[0].toUpperCase();if(rt&&(z+=`<circle cx="${H}" cy="${I}" r="${le+5}"
        fill="none" stroke="${ma}" stroke-width="2" opacity="0.8"/>`),at&&(z+=`<circle cx="${H}" cy="${I}" r="${le+(rt?9:4)}"
        fill="none" stroke="${Oe}" stroke-width="2" opacity="0.9"/>`),Q){let yt=le*.9;z+=`<rect x="${H-yt}" y="${I-yt}" width="${yt*2}" height="${yt*2}"
        rx="3" fill="${V}" stroke="${j}" stroke-width="1.5"
        transform="rotate(45 ${H} ${I})"
        class="dag-node" data-id="${b.commitId}"/>`}else z+=`<circle cx="${H}" cy="${I}" r="${le}"
        fill="${V}" stroke="${j}" stroke-width="2"
        class="dag-node" data-id="${b.commitId}"/>`;z+=`<text x="${H}" y="${I+4}" text-anchor="middle"
      font-size="10" font-weight="700" fill="#0d1117"
      style="pointer-events:none;user-select:none">${window.escHtml(bt)}</text>`;let $t=Kn(b.message),ge=$t&&Ue[$t]?`<tspan fill="${Ue[$t]}" font-weight="600">${window.escHtml($t)}</tspan><tspan fill="#8b949e">: </tspan>`:"",Bt=b.message||"",Tt=$t?Bt.replace(/^\w+[^\:]*:\s*/,""):Bt,Ls=Tt.length>56?Tt.substring(0,53)+"\u2026":Tt,fe="",Ut=gt;(b.branchLabels||[]).forEach(yt=>{let Ke=yt.length*6.5+14,Ze=Nt(yt);fe+=`<rect x="${Ut}" y="${I-20}" width="${Ke}" height="13"
        rx="6" fill="${Ze}" opacity="0.2"/>
      <text x="${Ut+7}" y="${I-10}" font-size="10" fill="${Ze}"
        font-weight="600">${window.escHtml(yt)}</text>`,Ut+=Ke+5}),at&&(fe+=`<rect x="${Ut}" y="${I-20}" width="34" height="13"
        rx="6" fill="${Oe}" opacity="0.25"/>
      <text x="${Ut+7}" y="${I-10}" font-size="10" fill="${Oe}"
        font-weight="700">HEAD</text>`);let ks=b.commitId.substring(0,7);B+=`
      ${fe}
      <text x="${gt}" y="${I+4}" class="dag-node" data-id="${b.commitId}"
        style="pointer-events:all">
        <tspan font-family="monospace" font-size="11" fill="#58a6ff">${ks}</tspan>
        <tspan dx="8" font-size="13" fill="#c9d1d9">${ge}${window.escHtml(Ls)}</tspan>
      </text>`}),a.innerHTML=O+`<g id="dag-g">${J}${z}${B}</g>`,qe=document.getElementById("dag-g");let q=document.getElementById("dag-viewport");tt=1,Ft=0,jt=0;let ft=!1,St=0,vt=0;q.addEventListener("wheel",b=>{b.preventDefault();let E=q.getBoundingClientRect(),H=b.clientX-E.left,I=b.clientY-E.top,V=b.deltaY>0?.85:1.18,j=Math.max(.15,Math.min(4,tt*V));Ft=H-(H-Ft)*(j/tt),jt=I-(I-jt)*(j/tt),tt=j,Kt()},{passive:!1}),q.addEventListener("mousedown",b=>{ft=!0,St=b.clientX,vt=b.clientY}),window.addEventListener("mouseup",()=>{ft=!1}),window.addEventListener("mousemove",b=>{ft&&(Ft+=b.clientX-St,jt+=b.clientY-vt,St=b.clientX,vt=b.clientY,Kt())});let et=document.getElementById("dag-popover"),k=document.getElementById("pop-sha"),_=document.getElementById("pop-branch-badge"),T=document.getElementById("pop-msg"),K=document.getElementById("pop-author"),Et=document.getElementById("pop-avatar"),zt=document.getElementById("pop-time"),X=document.getElementById("pop-session");a.addEventListener("mousemove",b=>{let E=b.target.closest("[data-id]");if(!E){et.style.display="none";return}let H=E.getAttribute("data-id"),I=g[H];if(!I){et.style.display="none";return}k.textContent=I.commitId.substring(0,12);let V=Nt(I.branch);_.textContent=I.branch,_.style.background=V+"22",_.style.color=V,_.style.border=`1px solid ${V}44`;let j=Kn(I.message),at=j?I.message.replace(/^\w+[^\:]*:\s*/,""):I.message,Q=j?ga(j):null;T.innerHTML=Q?`<span class="dag-pop-type dag-pop-type-${j}" style="background:${Q}22;color:${Q};border:1px solid ${Q}44">${window.escHtml(j)}</span>${window.escHtml(at)}`:window.escHtml(I.message);let rt=ze(I.author);Et.textContent=(I.author||"?")[0].toUpperCase(),Et.style.background=rt,K.textContent=I.author,zt.textContent=window.fmtDate(I.timestamp);let bt=e[H];bt&&bt.intent?(X.textContent="\u25EF Session: "+bt.intent,X.style.display="block"):X.style.display="none",et.style.display="block";let $t=window.innerWidth,ge=window.innerHeight,Bt=b.clientX+18,Tt=b.clientY+14;Bt+460>$t&&(Bt=b.clientX-460),Tt+220>ge&&(Tt=b.clientY-220),et.style.left=Bt+"px",et.style.top=Tt+"px"}),a.addEventListener("mouseleave",()=>{et.style.display="none"}),a.addEventListener("click",b=>{let E=b.target.closest("[data-id]");if(!E)return;let H=E.getAttribute("data-id");H&&(window.location.href=n+"/commits/"+H)})}function ba(t){let e={};return[...t].sort((o,s)=>new Date(s.startedAt).getTime()-new Date(o.startedAt).getTime()).forEach(o=>{(o.commits||[]).forEach(s=>{e[s]||(e[s]={intent:o.intent||"",sessionId:o.sessionId})})}),e}function ya(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");if(e)switch(e.dataset.action){case"zoom-in":tt=Math.max(.15,Math.min(4,tt*1.25)),Kt();break;case"zoom-out":tt=Math.max(.15,Math.min(4,tt*.8)),Kt();break;case"zoom-reset":tt=1,Ft=0,jt=0,Kt();break}})}async function ha(t){typeof window.initRepoNav=="function"&&window.initRepoNav(t.repoId);try{let[e,n]=await Promise.all([window.apiFetch("/repos/"+t.repoId+"/dag"),window.apiFetch("/repos/"+t.repoId+"/sessions?limit=200").catch(()=>({sessions:[]}))]),o=ba(n.sessions||[]);va(e,o,t.baseUrl)}catch(e){let n=e;if(n.message!=="auth"){let o=document.getElementById("dag-loading");o&&(o.innerHTML=`<span style="color:var(--color-danger)">\u2715 ${window.escHtml(n.message)}</span>`)}}}function Qn(){let t=window.__graphCfg;t&&(ya(),ha(t))}function W(t){return window.escHtml(t)}function We(t){return window.apiFetch(t)}function Zt(t){return typeof window.shortSha=="function"?window.shortSha(t):t.substring(0,8)}function me(t,e,n,o){return!t&&!e?"":t===e?`
    <div class="meta-item">
      <span class="meta-label">${o} ${n}</span>
      <span class="meta-value text-sm">${W(t)}</span>
    </div>`:`
    <div class="meta-item">
      <span class="meta-label">${o} ${n}</span>
      <span class="meta-value text-sm">
        ${t?`<span style="text-decoration:line-through;color:var(--color-danger)">${W(t)}</span> `:""}
        ${e?`<span style="color:var(--color-success)">${W(e)}</span>`:""}
      </span>
    </div>`}function wa(t,e){let n=m=>m.split(".").pop().toLowerCase(),o=m=>m.split("/").pop().replace(/\.[^.]+$/,""),s=new Set((t||[]).map(m=>m.path)),i=new Set((e||[]).map(m=>m.path)),r=(e||[]).filter(m=>!s.has(m.path)),a=(t||[]).filter(m=>!i.has(m.path)),l=(e||[]).filter(m=>s.has(m.path)),c=[];return a.forEach(m=>c.push(`
    <div class="diff-track-row diff-track-removed">
      <span class="diff-sign diff-sign-remove">\u2212</span>
      <span class="text-sm">${W(o(m.path))}</span>
      <span class="text-xs text-muted">.${W(n(m.path))} &bull; removed</span>
    </div>`)),r.forEach(m=>c.push(`
    <div class="diff-track-row diff-track-added">
      <span class="diff-sign diff-sign-add">+</span>
      <span class="text-sm">${W(o(m.path))}</span>
      <span class="text-xs text-muted">.${W(n(m.path))} &bull; added</span>
    </div>`)),l.forEach(m=>c.push(`
    <div class="diff-track-row diff-track-changed">
      <span class="diff-sign diff-sign-change">~</span>
      <span class="text-sm">${W(o(m.path))}</span>
      <span class="text-xs text-muted">.${W(n(m.path))} &bull; modified</span>
    </div>`)),c.length===0?'<p class="text-muted text-sm">No artifact changes detected.</p>':c.join("")}function ts(t,e){let n=t;return`<div style="display:flex;align-items:flex-end;gap:2px;height:80px;background:var(--bg-base);border-radius:var(--radius-sm);padding:var(--space-2)">${Array.from({length:64},()=>{n=n*1103515245+12345&2147483647;let s=10+n%80;return`<div style="flex:1;background:${e};opacity:0.7;border-radius:1px 1px 0 0;min-height:4px;height:${s}%"></div>`}).join("")}</div>`}var U;async function es(t){try{let o=((await We("/repos/"+U.repoId+"/objects")).objects||[]).find(s=>{let i=s.path.split(".").pop().toLowerCase();return["mp3","ogg","wav","flac"].includes(i)});if(o){let s=`/api/v1/repos/${U.repoId}/objects/${o.objectId}/content`;typeof window.queueAudio=="function"&&window.queueAudio(s,Zt(t),U.repoId)}else alert("No audio artifacts found for this commit.")}catch(e){alert("Could not load audio: "+e.message)}}function xa(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");if(e)switch(e.dataset.action){case"load-commit-audio":es(e.dataset.commitId??"");break;case"load-parent-audio":es(e.dataset.commitId??"");break}})}async function Ea(){typeof window.initRepoNav=="function"&&window.initRepoNav(U.repoId);try{let e=(await We("/repos/"+U.repoId+"/commits?limit=200")).commits||[],n=e.find(u=>u.commitId===U.commitId);if(!n){let u=document.getElementById("content");u&&(u.innerHTML='<p class="error">Commit not found.</p>');return}let o=(n.parentIds||[])[0],s=o?e.find(u=>u.commitId===o):null,r=(await We("/repos/"+U.repoId+"/objects")).objects||[],a=window.parseCommitMessage(n.message),l=s?window.parseCommitMessage(s.message):null,c=window.parseCommitMeta(n.message),m=s?window.parseCommitMeta(s.message):{},g=parseInt(o?o.substring(0,8):"0",16)||12345,d=parseInt(U.commitId.substring(0,8),16)||54321,p=document.getElementById("content");p&&(p.innerHTML=`
      <div class="card">
        <div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)">
          <a href="${U.base}/commits/${U.commitId}" class="btn btn-ghost btn-sm">&larr; Back to commit</a>
          <h2 style="margin:0">Musical Diff</h2>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:var(--space-4);align-items:start;margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            ${s?`
            <a href="${U.base}/commits/${o}" class="text-mono text-sm">${Zt(o)}</a>
            <div class="text-sm text-muted" style="margin-top:4px">${W(l.subject||s.message)}</div>
            `:'<span class="text-muted text-sm">Root commit \u2014 no parent</span>'}
          </div>
          <div style="font-size:24px;color:var(--text-muted);align-self:center">\u2192</div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <a href="${U.base}/commits/${U.commitId}" class="text-mono text-sm">${Zt(U.commitId)}</a>
            <div class="text-sm text-muted" style="margin-top:4px">${W(a.subject||n.message)}</div>
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">Musical Properties</h3>
        <div class="meta-row" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));margin-bottom:var(--space-4)">
          ${me(m.key,c.key,"Key","&#9837;")}
          ${me(m.tempo||m.bpm,c.tempo||c.bpm,"BPM","&#9201;")}
          ${me(m.section,c.section,"Section","&#127926;")}
          ${me(s?s.branch:null,n.branch,"Branch","&#9900;")}
        </div>

        <h3 style="margin-bottom:var(--space-3)">Artifact Changes</h3>
        <div style="margin-bottom:var(--space-4)">
          ${s?wa([],r):'<p class="text-muted text-sm">This is the root commit \u2014 all artifacts are new.</p>'}
        </div>

        <h3 style="margin-bottom:var(--space-3)">Audio Waveform Comparison</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent ${s?Zt(o):"\u2014"}</div>
            ${ts(g,"var(--color-accent)")}
            ${s?`<button class="btn btn-secondary btn-sm" style="margin-top:var(--space-2);width:100%" data-action="load-parent-audio" data-commit-id="${W(o)}">&#9654; Preview</button>`:'<p class="text-muted text-sm">No parent</p>'}
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit ${Zt(U.commitId)}</div>
            ${ts(d,"var(--color-success)")}
            <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-2);width:100%" data-action="load-commit-audio" data-commit-id="${W(U.commitId)}">&#9654; Preview</button>
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">Commit Messages</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            <pre style="font-size:12px">${s?W(s.message):"None"}</pre>
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <pre style="font-size:12px">${W(n.message)}</pre>
          </div>
        </div>
      </div>`)}catch(t){let e=t;if(e.message!=="auth"){let n=document.getElementById("content");n&&(n.innerHTML=`<p class="error">&#10005; ${W(e.message)}</p>`)}}}function ns(){let t=window.__diffCfg;t&&(U=t,xa(),Ea())}function $a(t,e){let n=t.trim().toLowerCase().replace(/[^a-z0-9-]/g,"-"),o=document.getElementById("topics-container");if(!n||!o)return;let s=document.createElement("span");s.className="tag-pill";let i=document.createElement("button");i.type="button",i.className="tag-pill-remove",i.dataset.action="remove-pill",i.textContent="\xD7",s.textContent=n,s.appendChild(i),o.insertBefore(s,e),e.value=""}function Ta(){let t=document.getElementById("topic-input");t&&t.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===",")e.preventDefault(),$a(t.value,t);else if(e.key==="Backspace"&&t.value===""){let n=document.getElementById("topics-container"),o=n?n.querySelectorAll(".tag-pill"):[];o.length>0&&o[o.length-1].remove()}})}async function Ia(t){let e=document.getElementById("invite-username"),n=document.getElementById("invite-role"),o=document.getElementById("invite-msg");if(!e||!n||!o)return;let s=e.value.trim(),i=n.value;if(s)try{let r=typeof window.getToken=="function"?window.getToken():null,a={"Content-Type":"application/json"};r&&(a.Authorization="Bearer "+r);let l=await fetch("/api/v1/repos/"+t+"/collaborators",{method:"POST",headers:a,body:JSON.stringify({username:s,role:i})});if(l.ok){e.value="",o.textContent="\u2705 Invited "+s,o.style.color="#3fb950";let c=document.getElementById("collaborators-list");c&&window.htmx&&window.htmx.trigger(c,"load")}else{let c=await l.json().catch(()=>({detail:l.statusText}));o.textContent="\u274C "+(c.detail||"Invite failed."),o.style.color="#f85149"}o.style.display="block",setTimeout(()=>{o.style.display="none"},5e3)}catch(r){o.textContent="\u274C "+r.message,o.style.color="#f85149",o.style.display="block"}}function La(t){let e=document.getElementById("delete-repo-form");e&&e.addEventListener("htmx:before-request",n=>{let o=document.getElementById("confirm-delete-name")?.value.trim(),s=document.getElementById("delete-name-error");o!==t&&(s&&(s.style.display="block"),n.preventDefault())})}function ka(t){document.addEventListener("click",e=>{let n=e.target.closest("[data-action]");if(n)switch(n.dataset.action){case"remove-pill":n.parentElement?.remove();break;case"invite-collaborator":Ia(t.repoId);break}})}function ss(){let t=window.__settingsCfg;t&&(Ta(),ka(t),La(t.fullName))}function os(){let t=document.getElementById("filter-form");t&&t.addEventListener("submit",function(){Array.from(this.elements).forEach(e=>{let n=e;(n.tagName==="SELECT"||n.tagName==="INPUT")&&n.value===""&&(n.disabled=!0)})}),document.querySelectorAll("[data-autosubmit]").forEach(e=>{e.addEventListener("change",()=>e.closest("form")?.requestSubmit())}),document.querySelectorAll("[data-filter][data-value]").forEach(e=>{e.addEventListener("click",n=>{n.preventDefault();let o=e.dataset.filter??"",s=e.dataset.value??"",i=new URLSearchParams(window.location.search),r=i.getAll(o);r.indexOf(s)!==-1?(i.delete(o),r.filter(c=>c!==s).forEach(c=>i.append(o,c)),e.classList.remove("active")):(i.append(o,s),e.classList.add("active"));let a="/explore?"+i.toString();history.pushState({},"",a),window.htmx?.ajax("GET",a,{target:"#repo-grid",swap:"innerHTML"})})}),document.querySelectorAll('[data-action="toggle-sidebar"]').forEach(e=>{e.addEventListener("click",()=>{document.querySelector(".explore-sidebar")?.classList.toggle("open")})})}function is(){let t=document.getElementById("branch-search"),e=document.getElementById("branch-list"),n=document.querySelectorAll(".branch-type-tab"),o="all";function s(){let i=t?t.value.toLowerCase():"";(e?e.querySelectorAll(".branch-card"):[]).forEach(a=>{let l=(a.dataset.branchName||"").toLowerCase(),c=(a.dataset.branchType||"").toLowerCase(),m=!i||l.includes(i),g=o==="all"||c===o;a.style.display=m&&g?"":"none"})}t&&t.addEventListener("input",s),n.forEach(i=>{i.addEventListener("click",r=>{r.preventDefault(),n.forEach(a=>a.classList.remove("active")),i.classList.add("active"),o=i.dataset.filter||"all",s()})})}function as(){let t=document.getElementById("tag-search"),e=document.getElementById("tag-list");!t||!e||t.addEventListener("input",()=>{let n=t.value.toLowerCase();e.querySelectorAll(".tag-card").forEach(o=>{let s=(o.dataset.tagName||"").toLowerCase();o.style.display=!n||s.includes(n)?"":"none"})})}function rs(){let t=document.querySelectorAll(".sess-filter-tab"),e=document.getElementById("sess-search"),n=document.getElementById("session-rows"),o="all";function s(){let i=e?e.value.toLowerCase():"";(n?n.querySelectorAll(".sess-card"):[]).forEach(a=>{let l=(a.dataset.status||"").toLowerCase(),c=(a.dataset.intent||"").toLowerCase()+" "+(a.dataset.location||"").toLowerCase(),m=o==="all"||l===o,g=!i||c.includes(i);a.style.display=m&&g?"":"none"})}t.forEach(i=>{i.addEventListener("click",r=>{r.preventDefault(),t.forEach(a=>a.classList.remove("active")),i.classList.add("active"),o=i.dataset.filter||"all",s()})}),e&&e.addEventListener("input",s)}function ls(){let t=document.querySelectorAll(".rel-filter-tab"),e=document.getElementById("rel-search"),n=document.getElementById("release-rows"),o="all";function s(){let i=e?e.value.toLowerCase():"";(n?n.querySelectorAll(".rel-card"):[]).forEach(a=>{let l=(a.dataset.status||"").toLowerCase(),c=(a.dataset.title||"").toLowerCase(),m=o==="all"||l===o,g=!i||c.includes(i);a.style.display=m&&g?"":"none"})}t.forEach(i=>{i.addEventListener("click",r=>{r.preventDefault(),t.forEach(a=>a.classList.remove("active")),i.classList.add("active"),o=i.dataset.filter||"all",s()})}),e&&e.addEventListener("input",s)}function cs(t){return t==null?"":t<1024?t+"\xA0B":t<1048576?(t/1024).toFixed(1)+"\xA0KB":(t/1048576).toFixed(1)+"\xA0MB"}function Ma(t){if(!t)return"";try{return new Date(t).toLocaleDateString(void 0,{year:"numeric",month:"short",day:"numeric"})}catch{return t}}function Ca(t){let e=t.indexOf(":");return(e>=0?t.slice(e+1):t).slice(0,12)}function Ha(t){return escHtml(t).replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^"\\])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,n=>/^"/.test(n)?/:$/.test(n)?'<span class="json-key">'+n+"</span>":'<span class="json-str">'+n+"</span>":/true|false/.test(n)?'<span class="json-bool">'+n+"</span>":/null/.test(n)?'<span class="json-null">'+n+"</span>":'<span class="json-num">'+n+"</span>")}function Sa(t){let e=new Uint8Array(t),n=Math.min(e.length,512),o="";for(let s=0;s<n;s+=16){let i=e.slice(s,s+16),r=s.toString(16).padStart(8,"0"),a=Array.from(i).map(c=>c.toString(16).padStart(2,"0")).join(" ").padEnd(47," "),l=Array.from(i).map(c=>c>=32&&c<127?String.fromCharCode(c):".").join("");o+='<span class="hex-offset">'+r+'</span><span class="hex-bytes">'+escHtml(a)+'</span><span class="hex-ascii">'+escHtml(l)+`</span>
`}return o}function Ba(t,e,n){let o=t.base+"/piano-roll/"+encodeURIComponent(t.ref)+"/"+t.filePath,s=t.base+"/listen/"+encodeURIComponent(t.ref)+"/"+t.filePath,i='<a class="btn-blob btn-blob-secondary" href="'+escHtml(n)+'" download>&#11015;&#65039;&nbsp;Raw</a>';return e.fileType==="midi"?i+='&nbsp;<a class="btn-blob btn-blob-primary" href="'+escHtml(o)+'">&#127929;&nbsp;View in Piano Roll</a>':e.fileType==="audio"&&(i+='&nbsp;<a class="btn-blob btn-blob-primary" href="'+escHtml(s)+'">&#127925;&nbsp;Listen</a>'),i}function _a(t,e,n){let o=t.base+"/piano-roll/"+encodeURIComponent(t.ref)+"/"+t.filePath;switch(e.fileType){case"midi":return'<div class="blob-midi-banner"><span class="blob-midi-icon">&#127929;</span><div class="blob-midi-title">'+escHtml(e.filename??t.filename)+'</div><div class="blob-midi-sub">MIDI file \u2014 interactive piano roll coming in Phase 2</div><a class="btn-blob btn-blob-primary" href="'+escHtml(o)+'">&#127929;&nbsp;View in Piano Roll</a></div>';case"audio":return'<div class="blob-audio-wrap"><span class="blob-audio-icon">&#127925;</span><div class="blob-audio-name">'+escHtml(e.filename??t.filename)+'</div><audio class="blob-audio-player" controls preload="metadata" src="'+escHtml(n)+'">Your browser does not support audio playback. <a href="'+escHtml(n)+'">Download</a> instead.</audio></div>';case"json":if(e.contentText){let s=e.contentText;try{s=JSON.stringify(JSON.parse(e.contentText),null,2)}catch{}return'<div class="blob-code-wrap"><pre class="blob-code"><code>'+Ha(s)+"</code></pre></div>"}return'<div class="blob-binary-notice">File too large to display inline. <a href="'+escHtml(n)+'">Download raw</a></div>';case"xml":return e.contentText?'<div class="blob-code-wrap"><pre class="blob-code"><code>'+escHtml(e.contentText)+"</code></pre></div>":'<div class="blob-binary-notice">File too large to display inline. <a href="'+escHtml(n)+'">Download raw</a></div>';case"image":return'<div class="blob-img-wrap"><img class="blob-img" src="'+escHtml(n)+'" alt="'+escHtml(e.filename??t.filename)+'"></div>';default:return null}}async function Aa(t,e,n){try{let o=await fetch(t,{headers:{Range:"bytes=0-511"}});if(o.ok||o.status===206){let s=await o.arrayBuffer(),i=Sa(s);e.innerHTML='<div class="blob-hex-wrap"><pre class="blob-hex">'+i+'</pre></div><div class="blob-binary-notice">Showing first '+Math.min(512,n)+" bytes of "+cs(n)+'. <a href="'+escHtml(t)+'" download>Download full file</a></div>'}else e.innerHTML='<div class="blob-binary-notice">Binary file \u2014 <a href="'+escHtml(t)+'" download>Download</a></div>'}catch{e.innerHTML='<div class="blob-binary-notice">Binary file \u2014 <a href="'+escHtml(t)+'" download>Download</a></div>'}}async function Ra(t,e){let n=e.rawUrl??t.base+"/raw/"+encodeURIComponent(t.ref)+"/"+t.filePath,o='<span title="Size">&#128196;&nbsp;'+cs(e.sizeBytes)+'</span><span title="SHA">&#128273;&nbsp;'+escHtml(Ca(e.sha??""))+'</span><span title="Last pushed">&#128197;&nbsp;'+escHtml(Ma(e.createdAt))+"</span>",s='<div class="blob-header"><div class="blob-filename">&#128196;&nbsp;'+escHtml(e.filename??t.filename)+'</div><div class="blob-meta">'+o+'</div><div class="blob-actions">'+Ba(t,e,n)+"</div></div>",i=_a(t,e,n),r='<div class="blob-body" id="blob-body-inner">'+(i!==null?i:'<div class="blob-loading">Rendering\u2026</div>')+"</div>",a=document.getElementById("content");if(a&&(a.innerHTML=s+r),i===null){let l=document.getElementById("blob-body-inner");l&&await Aa(n,l,e.sizeBytes??0)}}async function Pa(t){if(t.ssrBlobRendered&&document.getElementById("blob-ssr-content"))return;let e=document.getElementById("content");if(e){e.innerHTML='<div class="blob-loading">Loading\u2026</div>';try{let n=getToken(),o=n?{Authorization:"Bearer "+n}:{},i="/api/v1/repos/"+t.repoId+"/blob/"+encodeURIComponent(t.ref)+"/"+t.filePath,r=await fetch(i,{headers:o});if(r.status===404){e.innerHTML='<div class="blob-error">&#10060; File not found: <code>'+escHtml(t.filePath)+"</code></div>";return}if(r.status===401){e.innerHTML='<div class="blob-error">&#128274; Private repo \u2014 sign in to view this file.</div>';return}if(!r.ok){e.innerHTML='<div class="blob-error">&#10060; Failed to load file (HTTP '+r.status+").</div>";return}let a=await r.json();await Ra(t,a)}catch(n){let o=document.getElementById("content");o&&(o.innerHTML='<div class="blob-error">&#10060; '+escHtml(String(n))+"</div>")}}}function ds(){let t=window.__blobCfg;t&&Pa(t)}var Da={C3:-7,D3:-6,E3:-5,F3:-4,G3:-3,A3:-2,B3:-1,C4:0,D4:1,E4:2,F4:3,G4:4,A4:5,B4:6,C5:7,D5:8,E5:9,F5:10,G5:11,A5:12,B5:13},Na={C1:-5,D1:-4,E1:-3,F1:-2,G1:-1,A1:0,B1:1,C2:2,D2:3,E2:4,F2:5,G2:6,A2:7,B2:8,C3:9,D3:10,E3:11,F3:12,G3:13,A3:14,B3:15,C4:16},Fa={"1/1":4,"1/2":2,"1/4":1,"1/8":.5,"1/16":.25},wt=null,Qt="all";function Ge(t){return 56-t*8}function ja(t,e){let n=e==="bass"?Na:Da,o=t.pitch_name.replace("#","").replace("b","")+t.octave,s=n[o];return s!==void 0?s:4}function Oa(t){let e=60+t*120+20,n=`<svg class="staff-svg" height="96" width="${e}">`;for(let o=0;o<5;o++){let s=24+o*8;n+=`<line class="staff-line" x1="60" y1="${s}" x2="${e-10}" y2="${s}"/>`}for(let o=0;o<=t;o++){let s=60+o*120;n+=`<line class="bar-line" x1="${s}" y1="24" x2="${s}" y2="56"/>`}return{prefix:n,totalWidth:e}}function za(t){let e=t==="bass"?"Bass":"Treble";return`<text class="clef-text" x="8" y="54" font-size="11" fill="#8b949e" font-weight="600">${escHtml(e)}</text>`}function Ua(t,e){let[n,o]=t.split("/"),s=24+32/2;return`<text class="timesig-text" x="${e}" y="${s-4}" text-anchor="middle">${escHtml(n)}</text><text class="timesig-text" x="${e}" y="${s+12}" text-anchor="middle">${escHtml(o)}</text>`}function qa(t,e,n){let o=Math.floor(t.start_beat/n),s=t.start_beat%n,i=60+o*120+s/n*120+120*.1,r=ja(t,e),a=Ge(r),c=a>=40,m="";if(r<0)for(let p=-2;p>=r;p-=2){let u=Ge(p);m+=`<line class="note-ledger" x1="${i-5-3}" y1="${u}" x2="${i+5+3}" y2="${u}"/>`}else if(r>8)for(let p=10;p<=r;p+=2){let u=Ge(p);m+=`<line class="note-ledger" x1="${i-5-3}" y1="${u}" x2="${i+5+3}" y2="${u}"/>`}let g=Fa[t.duration]??1;if(g<2?m+=`<ellipse class="note-head" cx="${i}" cy="${a}" rx="5" ry="4"/>`:m+=`<ellipse cx="${i}" cy="${a}" rx="5" ry="4" fill="none" stroke="#58a6ff" stroke-width="1.5"/>`,g<4&&(c?m+=`<line class="note-stem" x1="${i+5}" y1="${a}" x2="${i+5}" y2="${a-28}"/>`:m+=`<line class="note-stem" x1="${i-5}" y1="${a}" x2="${i-5}" y2="${a+28}"/>`),g===.5){let p=c?i+5:i-5,u=c?a-28:a+28,v=c?u+10:u-10;m+=`<path d="M${p},${u} Q${p+10},${(u+v)/2} ${p},${v}" stroke="#58a6ff" stroke-width="1.5" fill="none"/>`}return t.pitch_name.includes("#")?m+=`<text x="${i-5-8}" y="${a+4}" font-size="12" fill="#f0883e">#</text>`:t.pitch_name.includes("b")&&(m+=`<text x="${i-5-8}" y="${a+4}" font-size="12" fill="#f0883e">b</text>`),m}function Wa(t){if(!t.notes||t.notes.length===0)return'<div class="score-empty">No notes in this track.</div>';let e=wt?.timeSig??"4/4",n=parseInt(e.split("/")[0],10),o=Math.max(...t.notes.map(l=>l.start_beat))+n,s=Math.ceil(o/n),i=t.clef??"treble",{prefix:r}=Oa(s),a=r;a+=za(i),a+=Ua(e,80);for(let l of t.notes)a+=qa(l,i,n);return a+="</svg>",`
    <div class="staff-container">
      <div class="staff-label">
        &#127929; ${escHtml(t.instrument??"Track "+t.track_id)}
        <span class="staff-clef-label">
          ${escHtml(i)} clef &bull; ${escHtml(t.key_signature??"")}
        </span>
      </div>
      ${a}
    </div>`}function Ga(t){let n=`<button class="track-btn${Qt==="all"?" active":""}" data-track="all">All Parts</button>`;return t.forEach((o,s)=>{n+=`<button class="track-btn${Qt===s?" active":""}" data-track="${s}">`+escHtml(o.instrument??"Track "+s)+"</button>"}),n}function Ya(t){Qt=t,ms()}function ms(){if(!wt)return;let t=wt.tracks??[],e=Qt==="all"?t:t.filter((i,r)=>r===Qt),n=document.getElementById("track-selector");n&&(n.innerHTML=Ga(t),n.querySelectorAll("[data-track]").forEach(i=>{i.addEventListener("click",()=>{let r=i.dataset.track;Ya(r==="all"?"all":parseInt(r,10))})}));let o=document.getElementById("score-meta");o&&(o.innerHTML=`
      <div class="score-meta-item">
        <span class="score-meta-label">Key</span>
        <span class="score-meta-value">${escHtml(wt.key??"\u2014")}</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Tempo</span>
        <span class="score-meta-value">${wt.tempo??"\u2014"} BPM</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Time</span>
        <span class="score-meta-value">${escHtml(wt.timeSig??"\u2014")}</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Parts</span>
        <span class="score-meta-value">${t.length}</span>
      </div>`);let s=document.getElementById("staves");if(s){let i=e.map(Wa).join("");s.innerHTML=i||'<div class="score-empty">No tracks found.</div>'}}async function Xa(t){initRepoNav(t.repoId);try{let e="/repos/"+encodeURIComponent(t.repoId)+"/notation/"+encodeURIComponent(t.ref),n=null;try{n=await apiFetch(e)}catch{}if(n&&typeof n=="object"&&n!==null){let o=n;wt=o.data??o}else wt={key:"C major",tempo:120,timeSig:"4/4",tracks:[{track_id:0,clef:"treble",key_signature:"C major",time_signature:"4/4",instrument:"piano",notes:[{pitch_name:"C",octave:4,duration:"1/4",start_beat:0,velocity:80,track_id:0},{pitch_name:"E",octave:4,duration:"1/4",start_beat:1,velocity:75,track_id:0},{pitch_name:"G",octave:4,duration:"1/4",start_beat:2,velocity:78,track_id:0},{pitch_name:"E",octave:4,duration:"1/4",start_beat:3,velocity:72,track_id:0}]}]};ms()}catch(e){let n=e;if(n.message!=="auth"){let o=document.getElementById("staves");o&&(o.innerHTML='<p class="error">&#10005; Could not load notation: '+escHtml(n.message)+"</p>")}}}function us(){let t=window.__scoreCfg;t&&Xa(t)}function Ye(t){return t===0?"#3fb950":t<=5?"#d29922":t<=20?"#e3964e":"#f85149"}function xt(t,e){let n=document.createElementNS("http://www.w3.org/2000/svg",t);for(let[o,s]of Object.entries(e))n.setAttribute(o,String(s));return n}function Va(t){let e=Math.max(1,t.length),n=Math.max(500,e*190+50),o=n/2-140/2,s=20,i=150,r=t.length*140+Math.max(0,t.length-1)*50,a=n/2-r/2,l=t.length>0?i+50+20:90,c=t.map((m,g)=>({x:a+g*190,y:i,node:m}));return{svgW:n,svgH:l,rootX:o,rootY:s,children:c}}function ps(t,e,n){let o=document.getElementById("fork-detail");if(!o)return;o.style.display="";let s=e.divergenceCommits??0,i=Ye(s),r=(e.owner??"?").charAt(0).toUpperCase(),a=`/${escHtml(e.owner)}/${escHtml(e.repoSlug)}`,l=`${t.base}/compare/${encodeURIComponent(e.repoSlug)}`,c=`${t.base}/pulls/new?head=${encodeURIComponent(e.owner+":main")}`;o.innerHTML=`
    <div class="fork-card">
      <div class="fork-card-title">
        <span class="avatar-badge">${escHtml(r)}</span>
        <a href="${a}" class="fork-card-link">
          ${escHtml(e.owner)}/${escHtml(e.repoSlug)}
        </a>
        ${n?' <span class="fork-upstream-badge">&#9673; upstream</span>':""}
      </div>
      <div class="fork-card-meta">
        ${n?"This is the upstream (source) repository.":`Forked by <strong>${escHtml(e.forkedBy??e.owner)}</strong>
             &bull; <span style="color:${i}">+${s} commit${s!==1?"s":""} ahead</span>`}
      </div>
      <div class="fork-card-actions">
        ${n?"":`
          <a class="btn btn-secondary" href="${l}">&#128256; Compare</a>
          <a class="btn btn-primary"   href="${c}">&#8593; Contribute upstream</a>
        `}
        <a class="btn btn-secondary" href="${a}">View repo &rarr;</a>
      </div>
    </div>`}function gs(t,e,n,o,s){let i=xt("g",{style:"cursor:pointer",tabindex:"0",role:"button","aria-label":`${o.owner}/${o.repoSlug}`}),r=s?"#3fb950":Ye(o.divergenceCommits??0);i.appendChild(xt("rect",{x:e,y:n,width:140,height:50,rx:"8",ry:"8",fill:"var(--bg-overlay, #161b22)",stroke:r,"stroke-width":s?"2":"1.5"}));let a=xt("text",{x:e+140/2,y:n+18,class:"fork-node-label"});a.textContent=`${o.owner}/${o.repoSlug}`,i.appendChild(a);let l=xt("text",{x:e+140/2,y:n+34,class:"fork-node-sub",fill:r});if(s)l.textContent="\u25C9 upstream",l.setAttribute("fill","#3fb950");else{let c=o.divergenceCommits??0;l.textContent=c===0?"\u2261 in sync":`+${c} ahead`}return i.appendChild(l),i.addEventListener("click",()=>ps(t,o,s)),i.addEventListener("keydown",c=>{let m=c;(m.key==="Enter"||m.key===" ")&&ps(t,o,s)}),i}function Ja(t,e,n){let{svgW:o,svgH:s,rootX:i,rootY:r,children:a}=Va(n),l=document.getElementById("fork-svg");if(!l)return;for(;l.firstChild;)l.removeChild(l.firstChild);l.setAttribute("viewBox",`0 0 ${o} ${s}`),l.setAttribute("width",String(o)),l.setAttribute("height",String(s));let c=xt("defs",{}),m=xt("marker",{id:"arr",markerWidth:"8",markerHeight:"6",refX:"7",refY:"3",orient:"auto"});m.appendChild(xt("polygon",{points:"0 0, 8 3, 0 6",fill:"#8b949e"})),c.appendChild(m),l.appendChild(c);let g=i+140/2,d=r+50;for(let{x:p,y:u,node:v}of a){let h=p+70,L=(d+u)/2,$=Ye(v.divergenceCommits??0);l.appendChild(xt("path",{d:`M${g},${d} C${g},${L} ${h},${L} ${h},${u}`,fill:"none",stroke:$,"stroke-width":"1.5","marker-end":"url(#arr)"}))}l.appendChild(gs(t,i,r,e,!0));for(let{x:p,y:u,node:v}of a)l.appendChild(gs(t,p,u,v,!1))}function fs(){let t=window.__forksCfg;if(!t)return;initRepoNav(t.repoId);let n=(t.forkNetwork??{}).root??{},o=n.children??[];Ja(t,n,o)}function vs(){document.querySelectorAll("[data-autosubmit]").forEach(t=>{t.addEventListener("change",()=>{t.closest("form")?.requestSubmit()})})}function Ka(t){let e=0;for(let n=0;n<t.length;n++)e=t.charCodeAt(n)+((e<<5)-e);return`hsl(${Math.abs(e)%360},50%,38%)`}function Za(t){let e=Ka(t),n=window.escHtml((t||"?").charAt(0).toUpperCase());return`<div class="comment-avatar" style="background:${e};color:#e6edf3;font-weight:700;font-size:14px;border:none">${n}</div>`}function ut(t){return`<a href="/${encodeURIComponent(t)}" style="color:var(--text-primary);font-weight:600">${window.escHtml(t)}</a>`}function Ht(t){if(!t)return"";let e=t.split("/"),n=e.length>=2?window.escHtml(e[1]):window.escHtml(t);return`<a href="/${encodeURIComponent(t)}" style="color:var(--color-accent)">${n}</a>`}var Qa={comment:{icon:"\u{1F5E8}\uFE0F",sentence:(t,e)=>`${ut(t)} commented on ${Ht(e)}`},mention:{icon:"\u{1F4AC}",sentence:(t,e)=>`${ut(t)} mentioned you in ${Ht(e)}`},pr_opened:{icon:"\u{1F500}",sentence:(t,e)=>`${ut(t)} opened a PR in ${Ht(e)}`},pr_merged:{icon:"\u2705",sentence:(t,e)=>`${ut(t)} merged a PR in ${Ht(e)}`},issue_opened:{icon:"\u{1F41B}",sentence:(t,e)=>`${ut(t)} opened an issue in ${Ht(e)}`},issue_closed:{icon:"\u2714\uFE0F",sentence:(t,e)=>`${ut(t)} closed an issue in ${Ht(e)}`},new_commit:{icon:"\u{1F3B5}",sentence:(t,e)=>`${ut(t)} committed to ${Ht(e)}`},new_follower:{icon:"\u{1F464}",sentence:t=>`${ut(t)} followed you`}};function tr(t){let e=Qa[t.event_type]??{icon:"\u2022",sentence:l=>ut(l)},n=e.icon,o=e.sentence(t.actor,t.repo_id??""),s=window.fmtRelative(t.created_at),i=!t.is_read,r=i?"border-left:3px solid var(--color-accent);padding-left:calc(var(--space-3) - 3px);":"border-left:3px solid transparent;padding-left:calc(var(--space-3) - 3px);opacity:0.75;",a=i?`<button
         class="mark-read-btn"
         data-notif-id="${window.escHtml(t.notif_id)}"
         data-action="mark-read"
         title="Mark as read"
         style="background:none;border:1px solid var(--border-color);border-radius:50%;width:22px;height:22px;cursor:pointer;color:var(--text-muted);font-size:12px;line-height:1;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;margin-left:var(--space-2)"
       >&#10003;</button>`:"";return`
    <div class="comment-item" data-notif-id="${window.escHtml(t.notif_id)}" style="${r}">
      ${Za(t.actor)}
      <div class="comment-body" style="flex:1;min-width:0">
        <div class="comment-meta" style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap">
          <span style="font-size:16px;line-height:1">${n}</span>
          <span>${o}</span>
          <span style="margin-left:auto;white-space:nowrap;display:flex;align-items:center;gap:var(--space-2)">
            ${window.escHtml(s)}
            ${a}
          </span>
        </div>
        ${i?'<div class="unread-dot" style="width:6px;height:6px;border-radius:50%;background:var(--color-accent);display:inline-block;margin-top:var(--space-1)"></div>':""}
      </div>
    </div>`}function er(){let t=document.getElementById("nav-notif-badge");if(!t)return;let e=parseInt(t.textContent??"",10);isNaN(e)||e<=1?t.style.display="none":t.textContent=String(e-1)}async function nr(t){let e=t.dataset.notifId;if(e)try{await window.apiFetch("/notifications/"+encodeURIComponent(e)+"/read",{method:"POST"});let n=document.querySelector(`.comment-item[data-notif-id="${CSS.escape(e)}"]`);n&&(n.style.borderLeft="3px solid transparent",n.style.opacity="0.75",n.querySelector(".unread-dot")?.remove()),t.remove(),er()}catch(n){n.message!=="auth"&&(t.style.color="var(--color-danger)")}}async function sr(){let t=document.getElementById("mark-all-read-btn");t&&(t.disabled=!0);try{await window.apiFetch("/notifications/read-all",{method:"POST"}),document.querySelectorAll(".comment-item").forEach(n=>{n.style.borderLeft="3px solid transparent",n.style.opacity="0.75",n.querySelector(".unread-dot")?.remove(),n.querySelector(".mark-read-btn")?.remove()});let e=document.getElementById("nav-notif-badge");e&&(e.style.display="none"),t?.remove()}catch(e){if(t&&(t.disabled=!1),e.message!=="auth"){let n=document.getElementById("feed-error");n&&(n.textContent="Could not mark all as read: "+e.message)}}}function or(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");e&&(e.dataset.action==="mark-read"?nr(e):e.dataset.action==="mark-all-read"&&sr())})}async function ir(){let t=document.getElementById("content");if(t)try{let e=await window.apiFetch("/feed?limit=50")??[];if(e.length===0){t.innerHTML=`
        <div class="empty-state">
          <div class="empty-icon">&#127926;</div>
          <p class="empty-title">Your feed is empty</p>
          <p class="empty-desc">Follow musicians and watch repos to see their activity here.</p>
          <a href="/explore" class="btn btn-primary">Explore repos</a>
        </div>`;return}let o=e.some(s=>!s.is_read)&&window.getToken()?`<button
           id="mark-all-read-btn"
           data-action="mark-all-read"
           class="btn btn-secondary"
           style="font-size:12px;padding:4px 10px"
         >&#10003; Mark all as read</button>`:"";t.innerHTML=`
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4)">
        <h1 style="margin:0">Activity Feed</h1>
        ${o}
      </div>
      <p id="feed-error" style="color:var(--color-danger);font-size:13px"></p>
      <div class="card" style="padding:0">
        ${e.map(tr).join("")}
      </div>`}catch(e){e.message!=="auth"&&t&&(t.innerHTML='<p class="error">&#10005; '+window.escHtml(e.message)+"</p>")}}function bs(){or(),ir()}var Xe=["melodic","harmonic","rhythmic","structural","dynamic"],pe={NONE:"#1f6feb",LOW:"#388bfd",MED:"#f0883e",HIGH:"#f85149"},ar={NONE:"#0d2942",LOW:"#102a4c",MED:"#341a00",HIGH:"#3d0000"},ys={melodic:"Melodic",harmonic:"Harmonic",rhythmic:"Rhythmic",structural:"Structural",dynamic:"Dynamic"},rr={energy:"#f0883e",valence:"#3fb950",tension:"#f85149",darkness:"#bc8cff"},Ve={},hs=[],lr="base",P;function cr(t){let s=t.length,i=t.map((d,p)=>{let u=p/s*2*Math.PI-Math.PI/2,v=d.score*140;return{x:180+v*Math.cos(u),y:180+v*Math.sin(u)}}),r=Xe.map((d,p)=>{let u=p/s*2*Math.PI-Math.PI/2;return`${180+140*Math.cos(u)},${180+140*Math.sin(u)}`}).join(" "),a=i.map(d=>`${d.x},${d.y}`).join(" "),l=Xe.map((d,p)=>{let u=p/s*2*Math.PI-Math.PI/2,v=180+140*Math.cos(u),h=180+140*Math.sin(u);return`<line x1="180" y1="180" x2="${v}" y2="${h}" stroke="#30363d" stroke-width="1"/>`}).join(""),c=[.25,.5,.75,1].map(d=>`<polygon points="${Xe.map((u,v)=>{let h=v/s*2*Math.PI-Math.PI/2;return`${180+d*140*Math.cos(h)},${180+d*140*Math.sin(h)}`}).join(" ")}" fill="none" stroke="#21262d" stroke-width="1"/>`).join(""),m=t.map((d,p)=>{let u=p/s*2*Math.PI-Math.PI/2,v=180+162*Math.cos(u),h=180+162*Math.sin(u),L=pe[d.level]??"#8b949e";return`<text x="${v}" y="${h+4}" text-anchor="middle"
      font-size="12" fill="${L}" font-family="system-ui">${ys[d.dimension]??d.dimension}</text>`}).join(""),g=i.map((d,p)=>{let u=pe[t[p].level]??"#58a6ff";return`<circle cx="${d.x}" cy="${d.y}" r="4" fill="${u}" stroke="#0d1117" stroke-width="2"/>`}).join("");return`<svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg"
      style="width:100%;max-width:360px;display:block;margin:0 auto">
    ${c}${l}
    <polygon points="${r}" fill="rgba(88,166,255,0.04)" stroke="#30363d" stroke-width="1"/>
    <polygon points="${a}" fill="rgba(248,81,73,0.18)" stroke="#f85149" stroke-width="2"/>
    ${m}${g}
  </svg>`}function dr(t){return`<span style="display:inline-block;padding:1px 7px;border-radius:10px;
    font-size:11px;font-weight:700;color:#fff;background:${pe[t]??"#8b949e"}">${t}</span>`}function mr(t,e){let n=ar[t.level]??"#161b22",o="dim-"+t.dimension,s=Math.round(t.score*100),i=e?`
    <div style="margin-top:10px;font-size:13px;color:#8b949e">
      <div>${window.escHtml(t.description??"")}</div>
      <div style="margin-top:6px;display:flex;gap:16px">
        <span>Base commits: <b style="color:#e6edf3">${t.branchACommits??0}</b></span>
        <span>Head commits: <b style="color:#e6edf3">${t.branchBCommits??0}</b></span>
      </div>
    </div>`:"";return`<div id="${o}" class="card" style="background:${n};cursor:pointer;margin-bottom:8px"
      data-action="toggle-dim" data-dim="${window.escHtml(t.dimension)}">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:14px;color:#e6edf3;font-weight:600;min-width:90px">
        ${ys[t.dimension]??t.dimension}</span>
      ${dr(t.level)}
      <div style="flex:1;height:6px;background:#21262d;border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${s}%;background:${pe[t.level]??"#58a6ff"};
          border-radius:3px;transition:width .3s"></div>
      </div>
      <span style="font-size:13px;color:#8b949e;white-space:nowrap">${s}% diverged</span>
    </div>
    ${i}
  </div>`}function ws(t){hs=t;let e=document.getElementById("dim-panels");e&&(e.innerHTML=t.map(n=>mr(n,!!Ve[n.dimension])).join(""))}function ue(t,e,n,o){let s=rr[t]??"#58a6ff",i=e>=0?"+":"",r=Math.round(n*100),a=Math.round(o*100),l=Math.round(e*100);return`
    <div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
        <span style="font-size:13px;color:#e6edf3;text-transform:capitalize">${t}</span>
        <span style="font-size:12px;color:${e>=0?"#3fb950":"#f85149"};font-weight:700">
          ${i}${l}%
        </span>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span style="font-size:11px;color:#8b949e;min-width:32px">base</span>
        <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${r}%;background:${s};opacity:0.5;border-radius:4px"></div>
        </div>
        <span style="font-size:11px;color:#8b949e;min-width:28px">${r}%</span>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-top:4px">
        <span style="font-size:11px;color:#8b949e;min-width:32px">head</span>
        <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${a}%;background:${s};border-radius:4px"></div>
        </div>
        <span style="font-size:11px;color:#8b949e;min-width:28px">${a}%</span>
      </div>
    </div>`}function ur(t,e){function l(p){let u=0;for(let v=0;v<p.length;v++)u=Math.imul(31,u)+p.charCodeAt(v)|0;return u>>>0}function c(p){let u=p,v=new Set;for(let h=0;h<768;h++)u=u*1103515245+12345&2147483647,u%100<22&&v.add(h);return v}let m=c(l(t)),g=c(l(e)),d="";for(let p=0;p<24;p++)for(let u=0;u<32;u++){let v=p*32+u,h=m.has(v),L=g.has(v);if(!h&&!L)continue;let $;h&&L?$="#30363d":L?$="#3fb95088":$="#f8514988",d+=`<rect x="${u*15+1}" y="${(23-p)*5+1}"
        width="13" height="4" fill="${$}" rx="1"/>`}return`<svg viewBox="0 0 480 120" xmlns="http://www.w3.org/2000/svg"
      style="width:100%;max-width:480px;border-radius:6px;background:#0d1117;display:block">
    ${d}
  </svg>
  <div style="display:flex;gap:16px;margin-top:6px;font-size:11px;color:#8b949e">
    <span><span style="display:inline-block;width:10px;height:10px;background:#3fb950;border-radius:2px;margin-right:4px"></span>Added in head</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#f85149;border-radius:2px;margin-right:4px"></span>Removed in head</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#30363d;border-radius:2px;margin-right:4px"></span>Unchanged</span>
  </div>`}function pr(t){lr=t,["btn-audio-base","btn-audio-head"].forEach(o=>{let s=document.getElementById(o);s&&(s.style.background="#21262d",s.style.color="#8b949e")});let e=document.getElementById("btn-audio-"+t);e&&(e.style.background="#1f6feb",e.style.color="#fff");let n=document.getElementById("audio-label");n&&(n.textContent=t==="base"?P.baseRef:P.headRef)}function gr(t){let e=(t.commitId??"").substring(0,8),n=t.timestamp?new Date(t.timestamp).toLocaleString():"";return`<div class="card" style="margin-bottom:8px;padding:var(--space-2) var(--space-3)">
    <div style="display:flex;align-items:center;gap:12px">
      <a href="${window.escHtml(P.uiBase)}/commits/${window.escHtml(t.commitId??"")}" class="text-mono"
         style="font-size:13px;color:#58a6ff;text-decoration:none">${window.escHtml(e)}</a>
      <span style="font-size:13px;color:#e6edf3;flex:1">${window.escHtml(t.message??"")}</span>
      <span style="font-size:12px;color:#8b949e;white-space:nowrap">${window.escHtml(t.author??"")}</span>
      <span style="font-size:11px;color:#8b949e;white-space:nowrap">${window.escHtml(n)}</span>
    </div>
  </div>`}async function fr(){window.initRepoNav&&window.initRepoNav(P.repoId);let t=`base=${encodeURIComponent(P.baseRef)}&head=${encodeURIComponent(P.headRef)}`,e=document.getElementById("content");if(e){e.innerHTML='<p class="loading">Computing musical diff&#8230;</p>';try{let n=await window.apiFetch(`/repos/${P.repoId}/compare?${t}`),o=Math.round((n.overallScore??0)*100),s=n.commonAncestor?n.commonAncestor.substring(0,8):null,i=n.dimensions??[],r=n.commits??[],a=n.emotionDiff??{},l=n.createPrUrl??`${P.uiBase}/pulls/new?base=${encodeURIComponent(P.baseRef)}&head=${encodeURIComponent(P.headRef)}`;e.innerHTML=`
      <!-- \u2500\u2500 Header \u2500\u2500 -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:12px">
        <div>
          <h1 style="margin:0;font-size:20px;color:#e6edf3">
            Comparing <code style="font-size:16px">${window.escHtml(P.baseRef)}</code>
            &hellip;
            <code style="font-size:16px">${window.escHtml(P.headRef)}</code>
          </h1>
          ${s?`<div style="font-size:12px;color:#8b949e;margin-top:4px">Common ancestor: <span class="text-mono">${window.escHtml(s)}</span></div>`:'<div style="font-size:12px;color:#f0883e;margin-top:4px">No common ancestor \u2014 diverged histories</div>'}
        </div>
        <a href="${window.escHtml(l)}" class="btn btn-primary">&#10133; Create Pull Request</a>
      </div>

      <!-- \u2500\u2500 Overall score + Radar \u2500\u2500 -->
      <div style="display:grid;grid-template-columns:1fr auto;gap:24px;align-items:start;margin-bottom:24px;flex-wrap:wrap">
        <div>
          <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Musical Divergence</h2>
          <div style="text-align:center;margin-bottom:16px">
            <div style="font-size:40px;font-weight:700;color:#e6edf3">${o}%</div>
            <div style="font-size:12px;color:#8b949e">overall musical divergence</div>
          </div>
          <div id="dim-panels"></div>
        </div>
        <div style="flex-shrink:0">
          <div style="width:280px">${cr(i)}</div>
        </div>
      </div>

      <!-- \u2500\u2500 Piano roll \u2500\u2500 -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Piano Roll Comparison</h2>
        <div style="font-size:12px;color:#8b949e;margin-bottom:12px">
          Deterministic note representation from commit SHA hashes \u2014 green = added, red = removed.
        </div>
        ${ur(P.baseRef,P.headRef)}
      </div>

      <!-- \u2500\u2500 Audio A/B toggle \u2500\u2500 -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Audio A/B Comparison</h2>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <button id="btn-audio-base" data-action="toggle-audio" data-side="base"
            style="padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;background:#1f6feb;color:#fff">
            &#9654; Base: ${window.escHtml(P.baseRef)}
          </button>
          <button id="btn-audio-head" data-action="toggle-audio" data-side="head"
            style="padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;background:#21262d;color:#8b949e">
            &#9654; Head: ${window.escHtml(P.headRef)}
          </button>
        </div>
        <div style="font-size:12px;color:#8b949e">
          Listening to: <span id="audio-label" style="color:#e6edf3">${window.escHtml(P.baseRef)}</span>
        </div>
        <div style="margin-top:8px;font-size:12px;color:#484f58">
          Audio render requires snapshot objects. Toggle queues the correct ref in the player.
        </div>
      </div>

      <!-- \u2500\u2500 Emotion diff \u2500\u2500 -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 16px;font-size:16px;color:#e6edf3">Emotion Diff</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          ${ue("energy",a.energyDelta??0,a.baseEnergy??.5,a.headEnergy??.5)}
          ${ue("valence",a.valenceDelta??0,a.baseValence??.5,a.headValence??.5)}
          ${ue("tension",a.tensionDelta??0,a.baseTension??.5,a.headTension??.5)}
          ${ue("darkness",a.darknessDelta??0,a.baseDarkness??.5,a.headDarkness??.5)}
        </div>
      </div>

      <!-- \u2500\u2500 Commit list \u2500\u2500 -->
      <div style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">
          Commits in <code>${window.escHtml(P.headRef)}</code> not in <code>${window.escHtml(P.baseRef)}</code>
          <span style="font-size:13px;font-weight:400;color:#8b949e;margin-left:8px">
            ${r.length} commit${r.length!==1?"s":""}
          </span>
        </h2>
        ${r.length===0?'<p class="text-muted text-sm">No commits unique to head \u2014 refs are identical or head is behind base.</p>':r.map(gr).join("")}
      </div>

      <!-- \u2500\u2500 Create PR CTA \u2500\u2500 -->
      <div class="card" style="text-align:center;padding:var(--space-5)">
        <div style="font-size:15px;color:#e6edf3;margin-bottom:12px">
          Ready to merge <code>${window.escHtml(P.headRef)}</code> into <code>${window.escHtml(P.baseRef)}</code>?
        </div>
        <a href="${window.escHtml(l)}" class="btn btn-primary" style="font-size:14px;padding:10px 24px">
          Open a Pull Request
        </a>
      </div>`,ws(i)}catch(n){n.message!=="auth"&&e&&(e.innerHTML='<p class="error">&#10005; '+window.escHtml(n.message)+"</p>")}}}function vr(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");if(e){if(e.dataset.action==="toggle-dim"){let n=e.dataset.dim;n&&(Ve[n]=!Ve[n],ws(hs))}else if(e.dataset.action==="toggle-audio"){let n=e.dataset.side;n&&pr(n)}}})}function xs(){P=window.__compareCfg??{repoId:"",baseRef:"",headRef:"",uiBase:""},P.repoId&&(vr(),fr())}var D;function br(t){let e=t.toLowerCase();return e.endsWith(".mid")||e.endsWith(".midi")?"&#127929;":e.endsWith(".mp3")||e.endsWith(".wav")||e.endsWith(".ogg")?"&#127925;":e.endsWith(".json")?"&#123;&#125;":e.endsWith(".webp")||e.endsWith(".png")||e.endsWith(".jpg")||e.endsWith(".jpeg")?"&#128444;":"&#128196;"}function yr(t){return t==null?"":t<1024?t+"\xA0B":t<1048576?(t/1024).toFixed(1)+"\xA0KB":(t/1048576).toFixed(1)+"\xA0MB"}function hr(t){return D.base+"/blob/"+encodeURIComponent(D.ref)+"/"+t}function wr(t){return D.base+"/tree/"+encodeURIComponent(D.ref)+"/"+t}async function xr(){try{let t=window.getToken?window.getToken():localStorage.getItem("muse_token")??"",e=t?{Authorization:"Bearer "+t}:{},n="/api/v1/repos/"+D.repo_id,o=await fetch(n+"/branches",{headers:e});if(!o.ok)return;let s=await o.json(),i=document.getElementById("branch-sel");if(!i)return;i.innerHTML="";let r=s.branches??[];for(let a of r){let l=document.createElement("option");l.value=a.name,l.textContent=a.name,a.name===D.ref&&(l.selected=!0),i.appendChild(l)}if(!r.some(a=>a.name===D.ref)){let a=document.createElement("option");a.value=D.ref,a.textContent=D.ref,a.selected=!0,i.prepend(a)}}catch{}}function Er(t){let e=t.entries??[],n=window.escHtml,o='<div class="tree-header"><div class="ref-selector"><label>Branch&nbsp;/&nbsp;tag:</label><select id="branch-sel" data-ref-select><option value="'+n(D.ref)+'">'+n(D.ref)+"</option></select></div></div>",s;if(e.length===0)s='<div class="tree-empty">This directory is empty.</div>';else{let a="";for(let l of e)l.type==="dir"?a+='<tr><td><span class="tree-icon">&#128193;</span><a class="entry-link" href="'+wr(l.path)+'">'+n(l.name)+'</a></td><td class="tree-size"></td></tr>':a+='<tr><td><span class="tree-icon" title="'+n(l.name)+'">'+br(l.name)+'</span><a class="entry-link" href="'+hr(l.path)+'">'+n(l.name)+'</a></td><td class="tree-size">'+yr(l.sizeBytes)+"</td></tr>";s='<table class="tree-table"><thead><tr><th>Name</th><th style="text-align:right">Size</th></tr></thead><tbody>'+a+"</tbody></table>"}let i=document.getElementById("content");i&&(i.innerHTML=o+s),xr();let r=document.getElementById("branch-sel");r?.addEventListener("change",()=>{let a=r.value,l=D.dir_path?"/"+D.dir_path:"";window.location.href=D.base+"/tree/"+encodeURIComponent(a)+l})}async function $r(){let t=document.getElementById("content");if(t){t.innerHTML='<div class="tree-loading">Loading tree\u2026</div>';try{let e=window.getToken?window.getToken():localStorage.getItem("muse_token")??"",n=e?{Authorization:"Bearer "+e}:{},o="/api/v1/repos/"+D.repo_id,s=D.dir_path?"/"+encodeURIComponent(D.dir_path):"",i="?owner="+encodeURIComponent(D.owner)+"&repo_slug="+encodeURIComponent(D.repo_slug),r=o+"/tree/"+encodeURIComponent(D.ref)+s+i,a=await fetch(r,{headers:n});if(a.status===404){t.innerHTML='<div class="tree-error">&#10060; Ref or path not found.</div>';return}if(!a.ok){t.innerHTML=`<div class="tree-error">&#10060; Failed to load tree (HTTP ${a.status}).</div>`;return}Er(await a.json())}catch(e){t.innerHTML='<div class="tree-error">&#10060; '+window.escHtml(String(e))+"</div>"}}}function Es(t){D={repo_id:String(t.repo_id??""),ref:String(t.ref??""),dir_path:String(t.dir_path??""),owner:String(t.owner??""),repo_slug:String(t.repo_slug??""),base:String(t.base??"")},$r()}var Tr={bass:{bg:"#0d2848",border:"#1f6feb",text:"#79c0ff"},keys:{bg:"#1e1040",border:"#8957e5",text:"#d2a8ff"},piano:{bg:"#1e1040",border:"#8957e5",text:"#d2a8ff"},keyboard:{bg:"#1e1040",border:"#8957e5",text:"#d2a8ff"},synth:{bg:"#1e1040",border:"#8957e5",text:"#d2a8ff"},drums:{bg:"#3d0a0a",border:"#f85149",text:"#ff7b72"},percussion:{bg:"#3d0a0a",border:"#f85149",text:"#ff7b72"},guitar:{bg:"#1a2a00",border:"#56d364",text:"#56d364"},strings:{bg:"#2a1800",border:"#e3b341",text:"#e3b341"},brass:{bg:"#2a1800",border:"#e3b341",text:"#e3b341"},winds:{bg:"#002a2a",border:"#39d353",text:"#39d353"},woodwinds:{bg:"#002a2a",border:"#39d353",text:"#39d353"},vocals:{bg:"#2a002a",border:"#f778ba",text:"#f778ba"},voice:{bg:"#2a002a",border:"#f778ba",text:"#f778ba"}};function Ir(t){let e=(t||"").toLowerCase();for(let[n,o]of Object.entries(Tr))if(e.includes(n))return o;return{bg:"#161b22",border:"#30363d",text:"#8b949e"}}function Lr(t){let e=Ir(t);return`<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500;background:${e.bg};border:1px solid ${e.border};color:${e.text};margin:2px 3px 2px 0">`+window.escHtml(t)+"</span>"}function Ot(t,e,n){return n==null?"":`<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 18px;background:#161b22;border:1px solid #30363d;border-radius:8px;min-width:90px"><span style="font-size:18px;margin-bottom:4px">${t}</span><span style="font-size:18px;font-weight:700;color:#e6edf3;line-height:1.1">${window.escHtml(String(n))}</span><span style="font-size:11px;color:#8b949e;margin-top:2px">${e}</span></div>`}function kr(t){let e=document.getElementById(t);if(!e)return;e.style.display=e.style.display==="none"?"":"none";let n=document.querySelector(`[data-action="toggle-section"][data-target="${t}"]`);n&&(n.textContent=e.style.display==="none"?"\u25B6 Show":"\u25BC Hide")}function Mr(){let t=document.getElementById("raw-json")?.textContent??"";navigator.clipboard.writeText(t).then(()=>{let e=document.getElementById("copy-btn");e&&(e.textContent="Copied!",setTimeout(()=>{e&&(e.textContent="Copy JSON")},2e3))})}var Je=[],$s="",pt;function Cr(t){$s=t||"";let e=document.getElementById("compose-modal");if(!e)return;e.style.display="flex";let n=document.getElementById("compose-prompt");n&&(n.value=$s);let o=document.getElementById("compose-output"),s=document.getElementById("compose-stream");o&&(o.style.display="none"),s&&(s.textContent="")}function Ts(){let t=document.getElementById("compose-modal");t&&(t.style.display="none")}async function Hr(){let e=document.getElementById("compose-prompt")?.value.trim()??"";if(!e)return;let n=document.getElementById("compose-send-btn"),o=document.getElementById("compose-output"),s=document.getElementById("compose-stream");if(!(!n||!o||!s)){n.disabled=!0,n.textContent="\u23F3 Generating\u2026",o.style.display="",s.textContent="";try{let i=await fetch("/api/v1/muse/stream",{method:"POST",headers:{...window.authHeaders(),"Content-Type":"application/json"},body:JSON.stringify({message:e,mode:"compose",repo_id:pt.repo_id,commit_id:pt.ref})});if(!i.ok){s.textContent="\u274C Error: "+i.status+" "+i.statusText;return}let r=i.body.getReader(),a=new TextDecoder;for(;;){let{value:l,done:c}=await r.read();if(c)break;for(let m of a.decode(l,{stream:!0}).split(`
`)){if(!m.startsWith("data:"))continue;let g=m.slice(5).trim();if(g==="[DONE]")break;try{let d=JSON.parse(g);s.textContent+=d.delta??d.text??d.content??"",s.scrollTop=s.scrollHeight}catch{}}}}catch(i){s.textContent="\u274C "+(i.message||String(i))}finally{n.disabled=!1,n.textContent="\u{1F3B5} Generate"}}}async function Sr(){window.initRepoNav&&window.initRepoNav(pt.repo_id);let t=document.getElementById("content");if(t)try{let e=await window.apiFetch("/repos/"+pt.repo_id+"/context/"+pt.ref),n=e.musicalState.activeTracks??[],o=n.length>0?n.map(Lr).join(""):'<em style="color:#8b949e;font-size:13px">No music files found in repo yet.</em>',s=[Ot("\u266D","Key",e.musicalState.key),Ot("\u2669","Mode",e.musicalState.mode),Ot("\u2669","BPM",e.musicalState.tempoBpm),Ot("\u{1D134}","Time Sig",e.musicalState.timeSignature),Ot("\u{1F3BC}","Form",e.musicalState.form),Ot("\u{1F3AD}","Emotion",e.musicalState.emotion)].filter(Boolean).join(""),i=s?`<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">${s}</div>`:'<p style="font-size:13px;color:#8b949e;margin-top:12px">Musical dimensions (key, tempo, etc.) require MIDI analysis \u2014 not yet available.</p>',r=e.missingElements??[],a=r.length>0?r.map(v=>`<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid #21262d;font-size:14px"><span style="color:#f85149;flex-shrink:0;margin-top:1px">\u2610</span><span style="color:#e6edf3">${window.escHtml(v)}</span></div>`).join(""):'<div style="display:flex;align-items:center;gap:8px;font-size:14px;color:#3fb950"><span>\u2705</span><span>All musical dimensions are present.</span></div>',l=r.length>0?"#f85149":"#238636";Je.length=0;let c=e.suggestions??{},m=Object.keys(c),g=m.length>0?m.map(v=>{let h=c[v],L=Je.push(v+": "+h)-1;return`<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #21262d"><div style="font-size:14px;color:#e6edf3;flex:1"><strong style="color:#79c0ff">${window.escHtml(v)}</strong>: ${window.escHtml(h)}</div><button class="btn btn-primary btn-sm" style="flex-shrink:0;white-space:nowrap" data-action="open-compose" data-suggestion-idx="${L}">\u26A1 Implement</button></div>`}).join(""):'<p style="font-size:14px;color:#8b949e">No suggestions available.</p>',d=e.history??[],p=d.length>0?d.map(v=>`
          <div class="commit-row">
            <a class="commit-sha" href="${window.escHtml(pt.base)}/commits/${v.commitId}">${window.shortSha(v.commitId)}</a>
            <span class="commit-msg">${window.escHtml(v.message)}</span>
            <span class="commit-meta">${window.escHtml(v.author)} &bull; ${window.fmtDate(v.timestamp)}</span>
          </div>`).join(""):'<p class="loading">No ancestor commits.</p>',u=JSON.stringify(e,null,2);t.innerHTML=`
      <div style="margin-bottom:12px">
        <a href="${window.escHtml(pt.base)}">&larr; Back to repo</a>
      </div>

      <!-- \u2500\u2500 Header \u2500\u2500 -->
      <div class="card" style="border-color:#1f6feb">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <span style="font-size:20px">\u{1F3B5}</span>
          <h1 style="margin:0;font-size:18px">What the Agent Sees</h1>
        </div>
        <p style="font-size:14px;color:#8b949e;margin-bottom:0">
          Musical context the AI agent receives when generating music at commit
          <code style="font-size:12px;background:#0d1117;padding:2px 6px;border-radius:4px">${window.shortSha(pt.ref)}</code>.
        </p>
      </div>

      <!-- \u2500\u2500 Musical State \u2500\u2500 -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">\u{1F3B5} Musical State</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="musical-state-body">\u25BC Hide</button>
        </div>
        <div id="musical-state-body">
          <div style="margin-bottom:8px">
            <span class="meta-label" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em">Active Tracks</span>
            <div style="margin-top:6px">${o}</div>
          </div>
          ${i}
        </div>
      </div>

      <!-- \u2500\u2500 Missing Elements \u2500\u2500 -->
      <div class="card" style="border-color:${l}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">\u26A0\uFE0F Missing Elements</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="missing-body">\u25BC Hide</button>
        </div>
        <div id="missing-body">${a}</div>
      </div>

      <!-- \u2500\u2500 Suggestions \u2500\u2500 -->
      <div class="card" style="border-color:#238636">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">\u2728 Suggestions</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="suggestions-body">\u25BC Hide</button>
        </div>
        <div id="suggestions-body">${g}</div>
      </div>

      <!-- \u2500\u2500 History Summary \u2500\u2500 -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">\u{1F550} History Summary</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="history-body">\u25BC Hide</button>
        </div>
        <div id="history-body">
          <div class="meta-row" style="margin-bottom:12px">
            <div class="meta-item">
              <span class="meta-label">Commit</span>
              <span class="meta-value" style="font-family:monospace">${window.shortSha(e.headCommit.commitId)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Branch</span>
              <span class="meta-value">${window.escHtml(e.currentBranch)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Author</span>
              <span class="meta-value">${window.escHtml(e.headCommit.author)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Date</span>
              <span class="meta-value">${window.fmtDate(e.headCommit.timestamp)}</span>
            </div>
          </div>
          <pre style="margin-bottom:12px">${window.escHtml(e.headCommit.message)}</pre>
          <h2 style="font-size:14px;margin-bottom:8px">Ancestors (${d.length})</h2>
          ${p}
        </div>
      </div>

      <!-- \u2500\u2500 Raw JSON \u2500\u2500 -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">\u{1F4C4} Raw JSON</h2>
          <div style="display:flex;gap:8px">
            <button id="copy-btn" class="btn btn-secondary btn-sm" data-action="copy-json">Copy JSON</button>
            <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="raw-json-body">\u25BC Hide</button>
          </div>
        </div>
        <div id="raw-json-body">
          <pre id="raw-json">${window.escHtml(u)}</pre>
        </div>
      </div>`}catch(e){e.message!=="auth"&&t&&(t.innerHTML='<p class="error">\u2717 '+window.escHtml(e.message)+"</p>")}}function Br(){document.addEventListener("click",t=>{let e=t.target.closest("[data-action]");if(!e)return;let n=e.dataset.action;if(n==="toggle-section"){let o=e.dataset.target;o&&kr(o)}else if(n==="copy-json")Mr();else if(n==="open-compose"){let o=parseInt(e.dataset.suggestionIdx??"",10);Cr(Je[o]??"")}else n==="close-compose"?Ts():n==="close-compose-backdrop"?t.target===e&&Ts():n==="send-compose"&&Hr()})}function Is(t){pt={repo_id:String(t.repo_id??""),ref:String(t.ref??""),base:String(t.base??"")},Br(),Sr()}var _r={repo:t=>nt(t),"issue-list":t=>un(t),"new-repo":t=>pn(t),"piano-roll":t=>{gn(t)},listen:t=>{fn(t)},"commit-detail":()=>vn(),commit:t=>Ln(t),"user-profile":t=>{Hn(t)},timeline:()=>An(),analysis:()=>Pn(),insights:()=>Nn(),search:()=>Ne(),"global-search":()=>Ne(),arrange:()=>jn(),activity:()=>zn(),"pr-detail":()=>Un(),commits:()=>Gn(),"issue-detail":()=>Xn(),"release-detail":()=>Vn(),graph:()=>Qn(),diff:()=>ns(),settings:()=>ss(),explore:()=>os(),branches:()=>is(),tags:()=>as(),sessions:()=>rs(),"release-list":()=>ls(),blob:()=>ds(),score:()=>us(),forks:()=>fs(),notifications:()=>vs(),feed:()=>bs(),compare:()=>xs(),tree:t=>Es(t),context:t=>Is(t)};window.MusePages=_r;})();

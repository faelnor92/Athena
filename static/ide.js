// Application de la fenêtre IDE (ide.html). Ex-_ideWindowApp d'app.js, injecté
// en <script> inline via document.write — interdit par la CSP stricte. Même
// origine que l'app : jeton lu dans localStorage, projet via ?project=.
(function(){
var API = location.origin;
var TOKEN = "";
try { TOKEN = localStorage.getItem("athena_session_token") || ""; } catch (e) {}
if (TOKEN === "no-auth-required") TOKEN = "";
var PID = new URLSearchParams(location.search).get("project") || "";
window.__pid = PID;  // lu par l'opener (openIdeWindow) pour savoir s'il faut changer de projet
function H(){var h={'Content-Type':'application/json'}; if(TOKEN) h['Authorization']='Bearer '+TOKEN; return h;}
function q(){return PID?('&project_id='+encodeURIComponent(PID)):'';}
function mode(p){var e=(p.split('.').pop()||'').toLowerCase();var m={py:'python',js:'javascript',mjs:'javascript',json:{name:'javascript',json:true},html:'htmlmixed',htm:'htmlmixed',xml:'xml',css:'css',md:'markdown',sh:'shell',bash:'shell',yml:'yaml',yaml:'yaml',c:'text/x-csrc',cpp:'text/x-c++src',h:'text/x-csrc',java:'text/x-java',go:'text/x-go',rs:'text/x-rustsrc'};return m[e]||null;}
var host=document.getElementById('host');
var cm=CodeMirror(host,{lineNumbers:true,theme:'material-darker',autoCloseBrackets:true,matchBrackets:true,indentUnit:4,extraKeys:{'Ctrl-Space':function(c){c.showHint({hint:CodeMirror.hint.anyword,completeSingle:false});},'Ctrl-S':function(){saveActive();},'Cmd-S':function(){saveActive();}}});
cm.setSize('100%','100%');
var cmEl=cm.getWrapperElement();cmEl.style.flex='1';
var prevEl=document.createElement('div');prevEl.style.cssText='flex:1;overflow:auto;display:none;';host.appendChild(prevEl);
function fkind(p){var e=(p.split('.').pop()||'').toLowerCase();if(e==='pdf')return 'pdf';if(['png','jpg','jpeg','gif','webp','svg','bmp','ico'].indexOf(e)>=0)return 'image';if(['zip','tar','gz','tgz','exe','bin','so','dll','o','class','jar','woff','woff2','ttf','otf','mp3','mp4','mov','wav','ogg','webm','wasm'].indexOf(e)>=0)return 'binary';return 'text';}
function renderPrev(p,t){if(t.kind==='image')prevEl.innerHTML='<div style="padding:12px;text-align:center;"><img src="'+t._url+'" style="max-width:100%;height:auto;"></div>';else if(t.kind==='pdf')prevEl.innerHTML='<iframe src="'+t._url+'" style="width:100%;height:100%;border:0;background:#fff;"></iframe>';else prevEl.innerHTML='<div style="padding:14px;opacity:.75;">Fichier binaire — <a style="color:#7aa2ff;" href="'+t._url+'" download="'+p.split('/').pop()+'">télécharger</a></div>';}
function showPreview(p,t){if(t._url){renderPrev(p,t);return;}prevEl.innerHTML='<div style="padding:14px;opacity:.6;">Aperçu…</div>';fetch(API+'/api/workspace/download?path='+encodeURIComponent(p)+q(),{headers:H()}).then(function(r){return r.blob();}).then(function(b){if(t.kind==='image'){var e=(p.split('.').pop()||'').toLowerCase();var mm={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif',webp:'image/webp',svg:'image/svg+xml',bmp:'image/bmp',ico:'image/x-icon'}[e];if(mm&&!b.type)b=new Blob([b],{type:mm});}else if(t.kind==='pdf'){b=new Blob([b],{type:'application/pdf'});}if(t._url){try{URL.revokeObjectURL(t._url);}catch(e){}}t._url=URL.createObjectURL(b);if(active!==p)return;renderPrev(p,t);}).catch(function(e){prevEl.innerHTML='<div style="padding:14px;color:#ff5b89;">Aperçu indisponible: '+e+'</div>';});}
var tabs={}, active=null;
cm.on('change',function(){var t=active&&tabs[active]; if(t&&!t._l&&!t.dirty){t.dirty=true; renderTabs();}});
document.getElementById('proj').textContent = PID? ('· projet '+PID) : '· projet courant';
function setStat(s){document.getElementById('stat').textContent=s||''; if(s) setTimeout(function(){document.getElementById('stat').textContent='';},2500);}
function renderTabs(){var bar=document.getElementById('tabs');bar.innerHTML='';Object.keys(tabs).forEach(function(p){var d=document.createElement('div');d.className='tab'+(p===active?' act':'');var n=document.createElement('span');n.textContent=(tabs[p].dirty?'● ':'')+p.split('/').pop();n.onclick=function(){activate(p);};var x=document.createElement('span');x.textContent='×';x.onclick=function(e){e.stopPropagation();closeTab(p);};d.appendChild(n);d.appendChild(x);bar.appendChild(d);});}
function activate(p){var t=tabs[p];if(!t)return;active=p;if(t.kind&&t.kind!=='text'){cmEl.style.display='none';prevEl.style.display='block';showPreview(p,t);renderTabs();return;}prevEl.style.display='none';cmEl.style.display='';t._l=true;cm.swapDoc(t.doc);t._l=false;renderTabs();setTimeout(function(){cm.refresh();},0);}
function closeTab(p){var t=tabs[p];if(t&&t.dirty&&!confirm('Modifs non enregistrées. Fermer ?'))return;if(t&&t._url){try{URL.revokeObjectURL(t._url);}catch(e){}}delete tabs[p];if(active===p){var k=Object.keys(tabs);active=null;if(k.length)activate(k[k.length-1]);else{cm.swapDoc(CodeMirror.Doc(''));renderTabs();}}else renderTabs();}
function openFile(p){if(tabs[p]){activate(p);return;}var k=fkind(p);if(k!=='text'){tabs[p]={kind:k,dirty:false};activate(p);return;}fetch(API+'/api/workspace/file?path='+encodeURIComponent(p)+q(),{headers:H()}).then(function(r){return r.json();}).then(function(d){if(d.detail){setStat('⚠️ '+d.detail);return;}tabs[p]={kind:'text',doc:CodeMirror.Doc(d.content,mode(p)),mtime:d.mtime||0,dirty:false};activate(p);}).catch(function(e){setStat('⚠️ '+e);});}
function saveActive(){if(!active)return;var t=tabs[active];if(t&&t.kind&&t.kind!=='text'){setStat('Aperçu — non éditable');return;}fetch(API+'/api/workspace/file',{method:'POST',headers:H(),body:JSON.stringify({path:active,content:cm.getValue(),project_id:PID||undefined})}).then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});}).then(function(x){if(x.ok){t.dirty=false;t.mtime=x.d.mtime||t.mtime;renderTabs();setStat('💾 enregistré');}else setStat('❌ '+(x.d.detail||'échec'));}).catch(function(e){setStat('❌ '+e);});}
function loadTree(){fetch(API+'/api/workspace/files'+(PID?('?project_id='+encodeURIComponent(PID)):''),{headers:H()}).then(function(r){return r.json();}).then(function(files){var box=document.getElementById('tree');if(!Array.isArray(files)||!files.length){box.innerHTML='<div style=opacity:.5>Projet vide.</div>';return;}box.innerHTML='';files.forEach(function(f){var d=document.createElement('div');d.className='f';d.textContent='📄 '+f.path;d.title=f.path;d.onclick=function(){openFile(f.path);};box.appendChild(d);});}).catch(function(){});}
document.getElementById('save').onclick=saveActive;
document.getElementById('refresh').onclick=loadTree;
window.openFileInIde=openFile;
window.setIdeProject=function(p){PID=p||'';window.__pid=PID;document.getElementById('proj').textContent=PID?('· projet '+PID):'· projet courant';loadTree();};
loadTree();
setInterval(loadTree,5000);  // auto-refresh de l'arbre dans la fenêtre IDE
})();

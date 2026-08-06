# ruff: noqa: E501
"""Browser control panel served at ``/`` by the debug HTTP server.

Self-contained vanilla HTML/JS (no external assets): a live preview tab, an
outputs tab that edits the four sinks, and a camera-placement tab with a
draggable top-down (XZ) view plus an isometric 3D view fed by ``/state``.
All edits go through ``POST /config`` (``?save=1`` persists to config.toml).
"""

_UI_TEXT = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>easyfbt</title>
<style>
 body{background:#14161a;color:#e8e8e8;font-family:system-ui,sans-serif;margin:0}
 header{display:flex;align-items:center;gap:14px;padding:10px 16px;background:#1d2026}
 header h1{font-size:16px;margin:0;color:#7fd4ff}
 nav button{background:none;border:0;color:#aaa;font-size:14px;padding:8px 12px;cursor:pointer;border-bottom:2px solid transparent}
 nav button.on{color:#fff;border-color:#7fd4ff}
 main{padding:14px 16px;max-width:1080px;margin:0 auto}
 .tab{display:none}.tab.on{display:block}
 img#stream{max-width:100%;max-height:70vh;background:#000;border:1px solid #333}
 fieldset{border:1px solid #333;border-radius:6px;margin:0 0 12px;padding:10px 12px}
 legend{color:#7fd4ff;padding:0 6px}
 label{margin-right:14px;white-space:nowrap}
 input[type=text],input[type=number]{background:#0f1114;color:#eee;border:1px solid #444;border-radius:4px;padding:3px 6px;width:110px}
 input.num{width:70px}
 button.act{background:#2563eb;color:#fff;border:0;border-radius:5px;padding:7px 16px;cursor:pointer;margin-right:8px}
 button.act.save{background:#059669}
 #msg{margin:10px 0;color:#ffd166;min-height:1.2em}
 canvas{background:#0b0d10;border:1px solid #333;border-radius:4px;touch-action:none}
 .cams{display:flex;gap:16px;flex-wrap:wrap}
 .hint{color:#8a8f98;font-size:12px}
</style></head>
<body>
<header><h1>easyfbt</h1>
 <nav>
  <button data-tab="preview" class="on">プレビュー</button>
  <button data-tab="outputs">出力設定</button>
  <button data-tab="cameras">カメラ配置</button>
 </nav>
</header>
<script>window.onerror=(m)=>{const e=document.getElementById("msg");if(e)e.textContent="JS error: "+m;};</script>
<main>
<div id="msg"></div>

<section class="tab on" id="tab-preview">
 <label><input type="checkbox" id="showVideo"> カメラ映像を表示(オフ=黒背景にスケルトンのみ)</label>
 <p><img id="stream" src="/stream" alt="preview"></p>
 <p class="hint">JSONデータ: <a href="/state" style="color:#7fd4ff">/state</a> /
    静止フレーム: <a href="/frame" style="color:#7fd4ff">/frame</a></p>
</section>

<section class="tab" id="tab-outputs">
 <div id="outputs"></div>
 <button class="act" id="applyOut">適用</button>
 <button class="act save" id="saveOut">適用して保存</button>
 <p class="hint">保存すると config.toml に書き込まれ、次回起動時にも有効になります。</p>
</section>

<section class="tab" id="tab-cameras">
 <fieldset><legend>カメラ選択</legend>
  <label>カメラ <select id="camSel"></select></label>
  <label>device <input type="text" id="camDevice"></label>
  <label>高さY <input type="number" id="camY" class="num" step="0.05"> m</label>
  <label>yaw <input type="number" id="camYaw" class="num" step="1"> °</label>
 </fieldset>
 <div class="cams">
  <div>
   <div class="hint">真上図(XZ・ドラッグで移動 / ホイールで回転)</div>
   <canvas id="topView" width="420" height="420"></canvas>
  </div>
  <div>
   <div class="hint">3Dビュー(緑=トラッカー実測, 青=カメラ)</div>
   <canvas id="isoView" width="480" height="420"></canvas>
  </div>
 </div>
 <p>
  <button class="act" id="applyCam">適用</button>
  <button class="act save" id="saveCam">適用して保存</button>
 </p>
 <p class="hint">位置・向きはトラッキング中でも即時反映されます(device等の変更は再起動後)。</p>
</section>
</main>
<script>
"use strict";
let cfg=null, sel=0, state={trackers:[]};
const $=id=>document.getElementById(id);
const msg=t=>{$("msg").textContent=t||"";};

function showTab(name){
 document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("on",x.dataset.tab===name));
 document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("on",x.id==="tab-"+name));
}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{
 location.hash=b.dataset.tab; showTab(b.dataset.tab);
});
if(["preview","outputs","cameras"].includes(location.hash.slice(1))) showTab(location.hash.slice(1));

async function load(){
 cfg=await (await fetch("/config")).json();
 $("showVideo").checked=cfg.debug.show_video;
 renderOutputs(); renderCamSel(); drawTop();
}
async function post(save){
 const r=await fetch("/config"+(save?"?save=1":""),{method:"POST",body:JSON.stringify(cfg)});
 const j=await r.json().catch(()=>({message:"通信エラー"}));
 msg(j.message||(r.ok?"適用しました":"エラー"));
 return r.ok;
}

$("showVideo").onchange=async e=>{cfg.debug.show_video=e.target.checked;await post(false);};

const OUTS=[["vmt","SteamVR (VMT)"],["vrchat","VRChat トラッカー"],["vrcft","表情 (VRCFT方式)"],["udp_json","UDP JSON"]];
function renderOutputs(){
 const box=$("outputs"); box.innerHTML="";
 for(const [key,title] of OUTS){
  const o=cfg.output[key];
  const fs=document.createElement("fieldset");
  let extra="";
  if(key==="vrcft") extra=`<label>prefix <input type="text" data-k="address_prefix" value="${o.address_prefix}"></label>
    <label><input type="checkbox" data-k="send_eyes" ${o.send_eyes?"checked":""}> 視線も送る</label>`;
  fs.innerHTML=`<legend>${title}</legend>
   <label><input type="checkbox" data-k="enabled" ${o.enabled?"checked":""}> 有効</label>
   <label>host <input type="text" data-k="host" value="${o.host}"></label>
   <label>port <input type="number" class="num" data-k="port" value="${o.port}"></label> ${extra}`;
  fs.querySelectorAll("[data-k]").forEach(el=>el.onchange=()=>{
   const k=el.dataset.k;
   o[k]=el.type==="checkbox"?el.checked:(el.type==="number"?Number(el.value):el.value);
  });
  box.appendChild(fs);
 }
}
$("applyOut").onclick=()=>post(false);
$("saveOut").onclick=()=>post(true);

function renderCamSel(){
 const s=$("camSel"); s.innerHTML="";
 cfg.camera.forEach((c,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`#${i} (${c.device})`;s.appendChild(o);});
 s.value=sel=Math.min(sel,cfg.camera.length-1); syncCamFields();
}
function syncCamFields(){
 const c=cfg.camera[sel];
 $("camDevice").value=c.device; $("camY").value=c.position[1]; $("camYaw").value=c.yaw_deg.toFixed(0);
}
$("camSel").onchange=e=>{sel=Number(e.target.value);syncCamFields();drawTop();};
$("camDevice").onchange=e=>{const v=e.target.value;cfg.camera[sel].device=/^\\d+$/.test(v)?Number(v):v;};
$("camY").onchange=e=>{cfg.camera[sel].position[1]=Number(e.target.value);};
$("camYaw").onchange=e=>{cfg.camera[sel].yaw_deg=Number(e.target.value);drawTop();};
$("applyCam").onclick=()=>post(false);
$("saveCam").onclick=()=>post(true);

// ---- top-down XZ view: room X -> canvas x, room Z -> canvas y ----
const tv=$("topView"), tc=tv.getContext("2d"), SC=70; // px per metre
const toCX=x=>tv.width/2+x*SC, toCZ=z=>tv.height/2+z*SC;
function drawTop(){
 tc.clearRect(0,0,tv.width,tv.height);
 tc.strokeStyle="#23272e";
 for(let m=-3;m<=3;m++){
  tc.beginPath();tc.moveTo(toCX(m),0);tc.lineTo(toCX(m),tv.height);tc.stroke();
  tc.beginPath();tc.moveTo(0,toCZ(m));tc.lineTo(tv.width,toCZ(m));tc.stroke();
 }
 // user at origin, facing -Z default
 tc.fillStyle="#4ade80";
 tc.beginPath();tc.arc(toCX(0),toCZ(0),8,0,7);tc.fill();
 tc.fillText("あなた",toCX(0)+12,toCZ(0)+4);
 (cfg?cfg.camera:[]).forEach((c,i)=>{
  const x=toCX(c.position[0]), z=toCZ(c.position[2]);
  const a=(-c.yaw_deg)*Math.PI/180;               // yaw 0 -> looks toward -Z
  const dx=Math.sin(a), dz=-Math.cos(a);
  tc.strokeStyle=i===sel?"#7fd4ff":"#4b5563"; tc.fillStyle=tc.strokeStyle;
  tc.beginPath();tc.arc(x,z,7,0,7);tc.fill();
  for(const off of [-0.5,0.5]){                    // FOV wedge ~57 deg
   const wx=Math.sin(a+off), wz=-Math.cos(a+off);
   tc.beginPath();tc.moveTo(x,z);tc.lineTo(x+wx*55,z+wz*55);tc.stroke();
  }
  tc.beginPath();tc.moveTo(x,z);tc.lineTo(x+dx*70,z+dz*70);tc.stroke();
  tc.fillText("cam"+i,x+10,z-8);
 });
}
let drag=false;
tv.addEventListener("pointerdown",e=>{
 const r=tv.getBoundingClientRect();
 const mx=e.clientX-r.left,my=e.clientY-r.top;
 cfg.camera.forEach((c,i)=>{
  if(Math.hypot(mx-toCX(c.position[0]),my-toCZ(c.position[2]))<14){sel=i;$("camSel").value=i;syncCamFields();}
 });
 drag=true; tv.setPointerCapture(e.pointerId);
});
tv.addEventListener("pointermove",e=>{
 if(!drag||!cfg)return;
 const r=tv.getBoundingClientRect();
 const c=cfg.camera[sel];
 c.position[0]=Math.round(((e.clientX-r.left)-tv.width/2)/SC*20)/20;
 c.position[2]=Math.round(((e.clientY-r.top)-tv.height/2)/SC*20)/20;
 drawTop();
});
tv.addEventListener("pointerup",()=>{drag=false;});
tv.addEventListener("wheel",e=>{
 e.preventDefault(); if(!cfg)return;
 cfg.camera[sel].yaw_deg=(cfg.camera[sel].yaw_deg+(e.deltaY>0?5:-5)+540)%360-180;
 syncCamFields(); drawTop();
},{passive:false});

// ---- isometric 3D view ----
const iso=$("isoView"), ic=iso.getContext("2d"), IS=52;
function P(x,y,z){const c=Math.cos(Math.PI/6),s=Math.sin(Math.PI/6);
 return [iso.width/2+(x-z)*c*IS, iso.height*0.72+(x+z)*s*IS-y*IS];}
function line3(a,b,st){ic.strokeStyle=st;ic.beginPath();ic.moveTo(...P(...a));ic.lineTo(...P(...b));ic.stroke();}
function drawIso(){
 ic.clearRect(0,0,iso.width,iso.height);
 for(let m=-2;m<=2;m++){line3([m,0,-2],[m,0,2],"#23272e");line3([-2,0,m],[2,0,m],"#23272e");}
 line3([0,0,0],[0,2,0],"#374151");
 (cfg?cfg.camera:[]).forEach((c,i)=>{
  const [px,py]=P(c.position[0],c.position[1],c.position[2]);
  ic.fillStyle=i===sel?"#7fd4ff":"#4b5563";
  ic.fillRect(px-5,py-5,10,10);
  const a=(-c.yaw_deg)*Math.PI/180;
  line3(c.position,[c.position[0]+Math.sin(a)*0.6,c.position[1],c.position[2]-Math.cos(a)*0.6],ic.fillStyle);
 });
 for(const t of state.trackers||[]){
  const [px,py]=P(t.pos[0],t.pos[1],t.pos[2]);
  ic.fillStyle="#4ade80";ic.beginPath();ic.arc(px,py,4,0,7);ic.fill();
 }
}
async function poll(){
 try{state=await (await fetch("/state")).json();}catch(e){}
 drawIso(); setTimeout(poll,500);
}
load().then(poll);
</script>
</body></html>
"""

UI_HTML = _UI_TEXT.encode("utf-8")

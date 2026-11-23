// Standalone Griptape widgets load as individual modules. Keep this dialog in sync in both libraries.
function projectFolderMemory(container) {
  return container.__hmbFolderMemory ||= {profiles:new Map(), selections:new Map(), project:"", pending:null};
}

function rememberProjectFolderProfile(memory, uid, value, confirmed = false) {
  if (!uid || !value?.revision || !Array.isArray(value.links)) return;
  const previous = memory.profiles.get(uid);
  if (previous) {
    const incoming = Number.isSafeInteger(value.generation) ? value.generation : -1;
    const current = Number.isSafeInteger(previous.generation) ? previous.generation : -1;
    if (incoming < current || (!confirmed && incoming === current && previous.revision !== value.revision
        && (current >= 0 || previous.confirmed))) return;
    if (previous.revision === value.revision && incoming === current) {
      if (confirmed) previous.confirmed = true;
      return;
    }
    if (value.selected_site_id !== previous.selected_site_id && memory.selections.get(uid) === previous.selected_site_id) {
      memory.selections.set(uid, value.selected_site_id || "");
    }
  }
  memory.profiles.set(uid, {revision:value.revision, generation:value.generation, selected_site_id:value.selected_site_id || "",
    write_site_id:value.write_site_id || "hq", links:value.links.map(link=>({...link})), confirmed:confirmed || previous?.confirmed === true});
}

function syncProjectFolderProfiles(container, snapshot, receiptOnly = false) {
  const memory = container.__hmbFolderMemory;
  if (!memory) return;
  // A missing entry in a partial snapshot says nothing about a saved folder.
  // Explicit profiles, including empty tombstones, carry the workstation's durable generation.
  if (!receiptOnly) {
    rememberProjectFolderProfile(memory, snapshot.project_uid, snapshot.site_settings);
    for (const [id, value] of Object.entries(snapshot.site_profiles || {})) {
      rememberProjectFolderProfile(memory, id, value);
    }
  }
  const req = memory.pending, result = snapshot.site_settings_result;
  if (!req || result?.request_id !== req.request_id || result.project_uid !== req.project_uid) return null;
  memory.pending = null;
  rememberProjectFolderProfile(memory, req.project_uid, result, true);
  const current = memory.profiles.get(req.project_uid);
  if (result.ok && !result.cancelled && req.action === "browse_add"
      && current && current.revision === result.revision && current.generation === result.generation
      && current.links.some(link => link.id === result.added_site_id)) {
    memory.selections.set(req.project_uid, result.added_site_id);
  }
  return {req, result};
}

function openProjectFolderCards(container, state, options) {
  container.__hmbFolderCards?.close();
  const doc = container.ownerDocument, sound = options.media === "sound";
  const label = (ko, en) => state.language === "en" ? en : ko;
  const leaf = path => String(path || "").replace(/[/\\]+$/, "").split(/[/\\]/).pop() || "";
  const memory = projectFolderMemory(container);
  let projects = new Map();
  const dialog = doc.createElement("dialog");
  dialog.className = "hmb-project-folders nodrag nopan nowheel";
  dialog.setAttribute("aria-label", label("프로젝트 Add", "Project Add"));
  dialog.innerHTML = `<style>
.hmb-project-folders{position:fixed;inset:0;margin:auto;height:fit-content;box-sizing:border-box;color-scheme:dark;width:min(540px,94vw);max-height:86vh;padding:0;background:#101725;color:#e6edf7;border:1px solid #46546d;border-radius:12px;box-shadow:0 16px 60px #000a;font:14px/1.4 system-ui,sans-serif;overflow:auto}
.hmb-project-folders::backdrop{background:#06091099}
.hmb-project-folders *{box-sizing:border-box}
.hmb-project-folders header,.hmb-project-folders footer{display:flex;gap:9px;align-items:center}
.hmb-project-folders header{padding:12px 16px;background:linear-gradient(110deg,#4e253f,#182236 70%);border-bottom:1px solid #3b475b;font-size:16px;font-weight:700}
.hmb-project-folders header button{margin-left:auto}
.hmb-project-folders section{padding:16px}
.hmb-project-folders label,.hmb-project-folders [data-pf-heading]{display:block;margin:0 0 6px;color:#c4cfdf;font-size:13px}
.hmb-project-folders select,.hmb-project-folders button{font:inherit;color:inherit;background:#131c2c;border:1px solid #42506a;border-radius:6px;padding:6px 11px}
.hmb-project-folders button{cursor:pointer}
.hmb-project-folders button:disabled{opacity:.45;cursor:default}
.hmb-project-folders :focus-visible{outline:2px solid #65dbed;outline-offset:2px}
.hmb-project-folders select{width:100%;height:36px;background:#0c1320}
.hmb-project-folders .pf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(195px,100%),1fr));gap:8px;max-height:40vh;overflow:auto;padding:3px}
.hmb-project-folders .pf-card{min-width:0;border:1px solid #42506a;border-radius:6px;background:#131c2c;overflow:hidden}
.hmb-project-folders .pf-card:has([aria-pressed=true]){border-color:#42c2d4;background:#123444}
.hmb-project-folders .pf-select{display:flex;align-items:center;gap:10px;width:100%;min-height:50px;text-align:left;border:0;background:transparent}
.hmb-project-folders .pf-write{display:flex;align-items:center;gap:6px;margin:0;padding:2px 10px 8px;font-size:12px;cursor:pointer}
.hmb-project-folders .pf-write input{margin:0;accent-color:#6ad9ed}
.hmb-project-folders .pf-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.hmb-project-folders .pf-icon{color:#7ccadc}
.hmb-project-folders [data-pf-status]{min-height:1.5em;color:#9cabbf;font-size:12px;margin:9px 0}
.hmb-project-folders footer{justify-content:flex-end;border-top:1px solid #334054;padding:10px 16px}
.hmb-project-folders [data-pf-add]{background:#225368;border-color:#387f90}
.hmb-project-folders .pf-controls{margin-top:14px}
.hmb-project-folders [hidden]{display:none!important}
</style>`
    + '<header><span class="pf-icon" aria-hidden="true">▱</span><span data-pf-title></span><button type="button" data-pf-close>×</button></header>'
    + '<section><label><span data-pf-project-label></span><select data-pf-project></select></label><div class="pf-controls"><strong data-pf-heading></strong><div class="pf-grid" data-pf-cards></div></div>'
    + '<div data-pf-status role="status" aria-live="polite"></div></section>'
    + '<footer><button type="button" data-pf-add></button><button type="button" data-pf-remove></button><button type="button" data-pf-done></button></footer>';
  const find = name => dialog.querySelector("[data-pf-" + name + "]");
  const select = find("project"), closeButton = find("close"), add = find("add"), remove = find("remove"), done = find("done");
  find("title").textContent = label("프로젝트 Add", "Project Add");
  find("project-label").textContent = label("프로젝트", "Project");
  find("heading").textContent = label("추가한 폴더", "Added folders");
  add.textContent = label("추가", "Add"); remove.textContent = label("삭제", "Remove");
  done.textContent = label("완료", "Done");
  closeButton.setAttribute("aria-label", label("닫기", "Close"));
  let project = memory.pending?.project_uid || memory.project, disposed = false, confirmRequest = "";
  const notice = text => { find("status").textContent = text || ""; };
  const profile = () => memory.profiles.get(project);
  const selectedId = () => memory.selections.get(project) || "";
  const writeId = () => profile()?.write_site_id || "hq";
  const writeGroup = "hmb-folder-write-" + String(globalThis.crypto?.randomUUID?.() || Math.random());
  function useSnapshot(snapshot) {
    // The editor may publish the local project catalog after the dialog opens.
    const available = sound && Array.isArray(snapshot.site_projects) ? snapshot.site_projects : snapshot.projects || [];
    const next = new Map();
    for (const row of [...available, {project_uid:snapshot.project_uid, project_id:snapshot.project_id, path:snapshot.project_root}]) {
      const id = String(row.project_uid || (row.project_id === snapshot.project_id && snapshot.project_uid) || row.project_id || "");
      const path = String(row.path || row.project_root || "");
      if (id && path && !next.has(id)) next.set(id, {path,name:row.name || row.project_id || leaf(path)});
    }
    const changed = next.size !== projects.size || [...next].some(([id, row]) => {
      const old = projects.get(id); return !old || old.path !== row.path || old.name !== row.name;
    });
    if (changed || !next.has(project)) {
      projects = next;
      if (!projects.has(project)) {
        project = [memory.pending?.project_uid, memory.project, snapshot.project_uid].find(id=>projects.has(id)) || projects.keys().next().value || "";
      }
      select.replaceChildren();
      for (const [id, row] of projects) select.add(new doc.defaultView.Option(row.name, id));
      select.value = project;
    }
    if (project) memory.project = project;
    return changed;
  }
  function paint() {
    const grid = find("cards"); grid.replaceChildren();
    const links = profile()?.links || [];
    const pending = memory.pending;
    let selected = selectedId();
    if (!links.some(link => link.id === selected)) {
      selected = [profile()?.selected_site_id, writeId(), links[0]?.id].find(id=>links.some(link=>link.id === id)) || "";
      memory.selections.set(project, selected);
    }
    for (const item of links) {
      const card = doc.createElement("div"), button = doc.createElement("button"), icon = doc.createElement("span"), name = doc.createElement("span");
      card.className = "pf-card";
      button.type = "button"; button.className = "pf-select"; button.dataset.pfSite = item.id; button.title = item.root;
      button.setAttribute("aria-pressed", String(item.id === selected));
      button.disabled = !!pending;
      icon.className = "pf-icon"; icon.textContent = "📁"; icon.setAttribute("aria-hidden","true");
      name.className = "pf-name"; name.textContent = item.label || leaf(item.root);
      button.append(icon,name); card.appendChild(button); grid.appendChild(card);
      button.onclick = () => { memory.selections.set(project, item.id); paint(); notice(item.root); };
      if (!sound) {
        const field = doc.createElement("label"), radio = doc.createElement("input");
        radio.type = "radio"; radio.name = writeGroup; radio.dataset.pfWriteSite = item.id;
        radio.checked = item.id === writeId(); radio.disabled = !!pending || !profile()?.revision;
        const caption = label("Add 저장 위치", "Add destination");
        radio.setAttribute("aria-label", caption + " · " + (item.label || leaf(item.root)));
        radio.onchange = () => { if (radio.checked && item.id !== writeId()) save(profile().links, item.id); };
        field.className = "pf-write"; field.append(radio, doc.createTextNode(caption)); card.appendChild(field);
      }
    }
    select.disabled = !!pending;
    add.disabled = !project || !!pending;
    done.disabled = !project || !!pending;
    remove.disabled = !profile()?.revision || !!pending || !links.some(link => link.id === selected);
  }
  function close() {
    if (disposed) return;
    disposed = true; dialog.close(); dialog.remove(); delete container.__hmbFolderCards;
    options.trigger?.focus?.({preventScroll:true});
  }
  function request(action, extra = {}) {
    if (disposed || !project || memory.pending) return;
    const id = globalThis.crypto?.randomUUID?.() || Date.now().toString(16) + Math.random().toString(16).slice(2);
    const req = {request_id:id, project_uid:project, action, ...extra};
    memory.pending = req;
    if (action === "confirm") confirmRequest = id;
    paint();
    notice(action === "browse_add" ? label("추가할 폴더를 선택하고 확인을 누르세요.", "Choose a folder and confirm.") : label("폴더 설정 저장 중…", "Saving folder settings…"));
    const fail = error => {
      if (memory.pending !== req) return;
      memory.pending = null;
      container.__hmbFolderCards?.failed(String(error?.message || error));
    };
    try { Promise.resolve(options.send(req)).catch(fail); } catch(error) { fail(error); }
  }
  function save(links, id) {
    if (profile()?.revision) request("update_links", {links, write_site_id:id, expected_revision:profile().revision});
  }
  function receive(snapshot, receiptOnly = false) {
    if (disposed) return;
    const before = profile();
    const acknowledged = syncProjectFolderProfiles(container, snapshot, receiptOnly);
    const changed = !receiptOnly && !memory.pending && useSnapshot(snapshot);
    if (!acknowledged && !changed && before === profile()) return;
    paint();
    if (!acknowledged) return;
    const {req,result} = acknowledged;
    if (!result.ok) {
      notice(result.message || label("폴더 설정을 저장하지 못했습니다.", "Could not save the folder settings.")); return;
    }
    if (req.action === "confirm" && req.request_id === confirmRequest) {
      if (result.revision && result.revision === profile()?.revision && Array.isArray(result.links)
          && result.selected_site_id === req.selected_site_id && profile()?.selected_site_id === req.selected_site_id
          && !result.cancelled) close();
      else notice(label("현재 폴더 설정을 다시 확인해 주세요.", "Review the current folder settings."));
      return;
    }
    const card = find("cards").querySelector('[aria-pressed="true"]');
    notice(result.message || card?.title || "");
  }
  select.onchange = () => { memory.project = project = select.value; paint(); notice(""); };
  add.onclick = () => request("browse_add");
  done.onclick = () => request("confirm", {expected_revision:profile()?.revision || "", selected_site_id:selectedId()});
  remove.onclick = () => {
    const selected = selectedId();
    if (profile()?.links.some(link => link.id === selected)) {
      const remaining = profile().links.filter(link => link.id !== selected);
      const destination = writeId() === selected ? (remaining[0]?.id || "hq") : writeId();
      save(remaining, destination);
    }
  };
  closeButton.onclick = close;
  dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
  dialog.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); close(); }
    event.stopPropagation();
  });
  for (const type of ["pointerdown","mousedown","click","wheel"]) dialog.addEventListener(type, event=>event.stopPropagation());
  container.__hmbFolderCards = {close, receive, failed:message=>{paint(); notice(message);}};
  syncProjectFolderProfiles(container, state);
  useSnapshot(state); paint(); doc.body.appendChild(dialog); dialog.showModal();
  if (!project) notice(label("먼저 프로젝트 폴더를 선택하세요.", "Select a project folder first."));
}
// End standalone project folder dialog.

const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const roles = ["Dialogue", "SFX", "Ambience", "Music"];
const labels = {Dialogue:"대사", SFX:"효과음", Ambience:"환경음", Music:"음악"};
const colors = {Dialogue:"#22d3ee", SFX:"#f472b6", Ambience:"#2dd4bf", Music:"#a78bfa"};
const record = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const soundPayload = props => {let value=props?.value??props?.parameterValue??props?.data??props; if(typeof value==="string"){try{value=JSON.parse(value);}catch{value={};}}return record(value);};
const soundFields = new Set(["schema","version","revision","project_id","project_root","project_uid","channel_uuid","shot","shot_catalog","projects","project_states","assets","folders","tracks","status","busy","error_code","ack_command_id","ui","site_settings","site_settings_result","site_picker_draft","site_projects","site_profiles"]);
const sameSoundValue = (a,b) => {
  if(a===b)return true;
  if(!a||!b||typeof a!=="object"||typeof b!=="object"||Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a);
  return keys.length===Object.keys(b).length&&keys.every(key=>Object.hasOwn(b,key)&&sameSoundValue(a[key],b[key]));
};
export function hmbReduceSoundTransport(state, transport, props, fromRead = false) {
  const raw=soundPayload(props), meta=record(raw.__hmb_sound_transport);
  const unchanged=(needsSync=false)=>({state,transport,kind:"ignored",needsSync});
  if(fromRead&&(meta.mode!=="full"||raw.schema!=="hmb-sound-library-ui"||raw.version!==1
    ||!Array.isArray(raw.assets)||!Array.isArray(raw.tracks)))return unchanged(true);
  if(raw.__hmb_sound_command)return unchanged(); // Local command echoes are not snapshots.
  if(!Object.keys(meta).length&&raw.schema!=="hmb-sound-ui-patch"){
    if(transport?.stream_id){
      // Native SetParameterValueResultSuccess echoes the retained full value.
      // It carries no stream ordering; acknowledge an identical echo without
      // rewinding state or requesting another synchronization indefinitely.
      if(raw.schema==="hmb-sound-library-ui"&&raw.version===1){
        if(sameSoundValue(hmbSoundState(raw),state))return unchanged();
      }
      return unchanged(true);
    }
    return {state:hmbSoundState(raw),transport:transport||null,kind:"full",needsSync:false};
  }
  if(meta.schema!=="hmb-sound-ui-transport"||meta.version!==1||typeof meta.stream_id!=="string"||!meta.stream_id||meta.stream_id.length>128||!Number.isSafeInteger(meta.sequence)||meta.sequence<(fromRead?0:1)||typeof meta.catalog_key!=="string"||!meta.catalog_key||meta.catalog_key.length>128)return unchanged(true);
  if(transport?.retired?.includes(meta.stream_id))return unchanged();
  if(transport?.stream_id===meta.stream_id&&(meta.sequence<transport.sequence||(!fromRead&&meta.sequence===transport.sequence)))return unchanged();
  if(meta.mode==="full"&&raw.schema==="hmb-sound-library-ui"&&raw.version===1&&Array.isArray(raw.assets)&&Array.isArray(raw.tracks)){
    const {__hmb_sound_transport:unused,...full}=raw;
    const retired=transport?.stream_id&&transport.stream_id!==meta.stream_id?[...(transport.retired||[]),transport.stream_id].slice(-8):transport?.retired||[];
    return {state:hmbSoundState(full),transport:{...meta,retired},kind:"full",needsSync:false};
  }
  if(meta.mode!=="delta"||raw.schema!=="hmb-sound-ui-patch"||raw.version!==1
    ||!Number.isSafeInteger(meta.base_sequence)||meta.base_sequence<1||meta.sequence!==meta.base_sequence+1
    ||!Array.isArray(raw.removed)||!raw.values||typeof raw.values!=="object"||Array.isArray(raw.values))return unchanged(true);
  const keys=Object.keys(raw.values), removed=raw.removed;
  if([...keys,...removed].some(key=>typeof key!=="string"||!soundFields.has(key)||["assets","schema","version"].includes(key)))return unchanged(true);
  if(!transport||meta.stream_id!==transport.stream_id||meta.catalog_key!==transport.catalog_key||meta.base_sequence!==transport.sequence){
    return {...unchanged(true),gap:{stream_id:meta.stream_id,sequence:meta.sequence}};
  }
  const merged={...state,...raw.values};for(const key of removed)delete merged[key];
  return {state:hmbSoundState(merged),transport:{...meta,retired:transport.retired||[]},kind:"delta",needsSync:false};
}
export function hmbSoundState(props = {}) {
  let value = props?.value ?? props?.parameterValue ?? props?.data ?? props;
  if (typeof value === "string") { try { value = JSON.parse(value); } catch { value = {}; } }
  const raw = record(value), shot = record(raw.shot), catalog = record(raw.shot_catalog);
  return {...raw, revision:Number.isSafeInteger(raw.revision) && raw.revision >= 0 ? raw.revision : 0,
    busy:raw.busy === true, project_uid:String(raw.project_uid || ""), project_id:String(raw.project_id || ""),
    project_root:String(raw.project_root || ""), ack_command_id:String(raw.ack_command_id || ""),
    shot:{...shot,channel_uuid:String(shot.channel_uuid || ""),shot_uuid:String(shot.shot_uuid || "")},
    shot_catalog:{...catalog,shots:(Array.isArray(catalog.shots) ? catalog.shots : []).filter(v=>v && typeof v === "object")},
    projects:(Array.isArray(raw.projects) ? raw.projects : []).filter(v=>v && typeof v === "object"),
    assets:(Array.isArray(raw.assets) ? raw.assets : []).filter(v=>v && typeof v === "object"),
    folders:(Array.isArray(raw.folders) ? raw.folders : []).filter(v=>typeof v==="string"&&v&&!v.startsWith("/")&&!v.startsWith("\\")&&(!v.includes(":") || /^site:site-[0-9a-f]{32}(?:\/[^:]+)?$/.test(v))&&!v.includes("\0")&&!v.replaceAll("\\","/").split("/").includes("..")),
    tracks:(Array.isArray(raw.tracks) ? raw.tracks : []).filter(v=>v && typeof v === "object")};
}
const read = hmbSoundState;
const previewURL = value => typeof value === "string" && (/^https?:\/\//i.test(value) || /^blob:/i.test(value) || /^\/(?!\/)/.test(value)) ? value : "";
const scopeKey = state => JSON.stringify([state.project_uid,state.shot.channel_uuid,state.shot.shot_uuid]);
const sameShot = (track, row) => String(track.channel_uuid || "") === String(row.channel_uuid || "") && String(track.shot_uuid || "") === String(row.shot_uuid || "");
export function hmbSoundShotRows(state) {
  if (state.shot_catalog.shots.length) return state.shot_catalog.shots.map(row=>({...row,channel_uuid:String(row.channel_uuid || state.shot_catalog.channel_uuid || "")}));
  return !state.shot_catalog.channel_uuid && !state.shot.channel_uuid && !state.shot.shot_uuid
    ? [{shot_uuid:"",channel_uuid:"",number:0,name:"Only",legacy:true}] : [];
}
const seconds = value => {const n=Number(value);return !Number.isFinite(n)||n<0?"--:--":`${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,"0")}`;};
const folderIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h7l2 2h9v12H3z"/></svg>';
const scanFolderIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 19V6h6l2 2h10v4M3 19h8"/><circle cx="16" cy="15" r="3"/><path d="m18.2 17.2 3 3"/></svg>';
const playIcon = '<svg viewBox="0 0 20 20" aria-hidden="true"><path class="hs-play-shape" d="M7 4.5 15 10l-8 5.5z"/></svg>';
const pauseIcon = '<svg viewBox="0 0 20 20" aria-hidden="true"><path class="hs-play-shape" d="M6 4h3v12H6zM11 4h3v12h-3z"/></svg>';
// Decorative audio glyph, not a measured waveform or listening claim.
function wave(seed="") {let hash=0;for(const c of String(seed))hash=(hash*31+c.charCodeAt(0))>>>0;return `<svg class="hs-wave" viewBox="0 0 120 36" aria-hidden="true">${Array.from({length:35},(_,i)=>{const h=4+((hash >>> (i%23))+i*13)%25;return `<path d="M${4+i*3.3} ${18-h/2}v${h}"/>`;}).join("")}</svg>`;}
function assetIdentity(asset) {return String(asset.source_uid || asset.relative_path || "");}
function trackPreview(state, track) {return previewURL(track.preview_url) || previewURL(state.assets.find(a=>assetIdentity(a)===String(track.source_uid || track.relative_path || ""))?.preview_url);}
function assetPreview(state, asset) {return previewURL(asset.preview_url) || previewURL(state.tracks.find(t=>String(t.source_uid || t.relative_path || "")===assetIdentity(asset))?.preview_url);}
export function hmbSoundFolders(state) {const map=new Map();for(const folder of state.folders||[]){const parts=folder.replaceAll("\\","/").split("/").filter(Boolean);for(let i=1;i<=parts.length;i++)map.set(parts.slice(0,i).join("/"),0);}for(const a of state.assets){const parts=String(a.relative_path||"").replaceAll("\\","/").split("/").slice(0,-1);for(let i=1;i<=parts.length;i++){const name=parts.slice(0,i).join("/");map.set(name,(map.get(name)||0)+1);}}return [...map].sort(([a],[b])=>a.localeCompare(b,undefined,{numeric:true}));}

// Widgets are loaded independently as data URLs. Match the ImageAsset shot order.
const shotColors = ['#F472B6', '#3B82F6', '#10B981', '#8B5CF6', '#EAB308'];
const shotColor = shot => shotColors[Number(shot?.number) - 1] || shotColors[0];
const assetLabel = (name, chosen) => name + (chosen ? " · 연결됨" : " · 선택한 샷에 연결");

const style = `
.hmb-sound{--bg:#090c16;--panel:#101523;--line:rgba(148,163,184,.19);--cyan:#22d3ee;--pink:#f472b6;--muted:#8fa3b8;container-type:inline-size;position:relative;width:100%;height:100%;min-height:500px;display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:radial-gradient(circle at 8% -10%,rgba(168,85,247,.16),transparent 34%),linear-gradient(180deg,#0b1020,#060912);color:#e6edf7;font:12px "Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,sans-serif;font-synthesis:none;-webkit-font-smoothing:antialiased}
.hmb-sound,.hmb-sound *{box-sizing:border-box;min-width:0}.hmb-sound :is(button,input,select,textarea){font:inherit;color:inherit}.hmb-sound button{cursor:pointer;border:1px solid var(--line);border-radius:6px;background:#0b1220}.hmb-sound button:disabled{opacity:.35;cursor:default}.hmb-sound button:focus-visible,.hmb-sound input:focus-visible{outline:2px solid #22d3ee;outline-offset:2px}.hmb-sound svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.hmb-sound .hs-head{height:58px;flex:0 0 58px;display:flex;align-items:center;gap:10px;padding:8px 13px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,rgba(72,35,101,.55),rgba(14,23,38,.92) 60%)}.hmb-sound .hs-mark{width:34px;height:34px;display:grid;place-items:center;border:1px solid #9a58b2;border-radius:8px;background:rgba(129,31,144,.3);color:#e6b6fb;box-shadow:inset 0 0 14px #a855f72b}.hmb-sound .hs-heading{display:flex;flex-direction:column;gap:2px}.hmb-sound .hs-heading strong{font-size:15px}.hmb-sound .hs-heading small{font-size:9px;color:#9aa8be}.hmb-sound .hs-actions{display:flex;gap:6px;margin-left:auto}.hmb-sound .hs-actions button{height:30px;min-width:30px;padding:0 9px;border-color:#3577a3;color:#93d7f8;background:linear-gradient(#12304a,#091325)}
.hmb-sound .hs-main{display:grid;grid-template-columns:202px minmax(0,1fr);gap:8px;padding:8px;min-height:180px;flex:1 1 300px}.hmb-sound .hs-panel{min-height:0;border:1px solid var(--line);border-radius:8px;background:rgba(8,13,23,.8);overflow:hidden}.hmb-sound .hs-tree{display:flex;flex-direction:column}.hmb-sound .hs-panel-title{height:35px;flex:0 0 35px;display:flex;align-items:center;justify-content:space-between;padding:0 10px;border-bottom:1px solid var(--line);background:rgba(19,27,42,.78);font-size:10px;font-weight:800;color:#bbcbdd}.hmb-sound .hs-folder-list{padding:6px;overflow:auto}.hmb-sound .hs-tree button{width:100%;min-height:30px;margin-bottom:3px;display:flex;align-items:center;gap:7px;padding:5px 7px;text-align:left;border-color:transparent;background:transparent;color:#9dafc2;font-size:10px}.hmb-sound .hs-tree button svg{flex:0 0 15px;color:#22d3ee}.hmb-sound .hs-tree button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.hmb-sound .hs-tree button b{font-size:9px;font-weight:500;color:#8ca4ba}.hmb-sound .hs-tree button.active{border-color:#22d3ee80;color:#e4fbff;background:linear-gradient(90deg,#0891b22b,#0891b208)}.hmb-sound .hs-tree small{display:block;margin:12px 7px 6px;color:#62778d;font-size:9px}
.hmb-sound .hs-browser{display:flex;flex-direction:column}.hmb-sound .hs-filter{height:43px;flex:0 0 43px;display:flex;align-items:center;gap:9px;padding:6px 9px;border-bottom:1px solid var(--line)}.hmb-sound .hs-filter input{height:29px;min-width:0;flex:1;padding:0 10px;background:#070c15;border:1px solid #34465b;border-radius:7px;outline:none}.hmb-sound .hs-filter b{font-size:9px;color:#63e6d4;white-space:nowrap}.hmb-sound .hs-catalog{overflow:auto;flex:1;min-height:0;padding:9px}.hmb-sound .hs-files{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:9px;align-content:start}.hmb-sound .hs-asset{position:relative;min-height:113px;padding:8px;border:1px solid #344157;border-radius:9px;background:linear-gradient(145deg,#182031,#0b101d);transition:border-color .12s,box-shadow .12s}.hmb-sound .hs-asset.selected{border-color:var(--active-shot-color);box-shadow:0 0 12px color-mix(in srgb,var(--active-shot-color) 28%,transparent)}.hmb-sound .hs-art{height:70px;display:grid;place-items:center;position:relative;color:var(--audio-color);background:radial-gradient(ellipse,#152236aa,transparent 70%);border-bottom:1px solid #33415555}.hmb-sound .hs-wave{width:100%;height:35px;stroke:currentColor;stroke-width:1.5;filter:drop-shadow(0 0 3px currentColor)}.hmb-sound .hs-art .hs-preview{position:absolute;z-index:2;right:0;bottom:4px;width:22px;height:22px;border-color:#4f657c;background:#07111dd9}.hmb-sound .hs-asset-name{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;margin-top:8px}.hmb-sound .hs-asset-meta{display:flex;justify-content:space-between;gap:4px;margin:4px 0 8px;color:#8ca1b8;font-size:9px}.hmb-sound .hs-asset-select{position:absolute;inset:0;z-index:1;width:100%;height:100%;padding:0;border:0;border-radius:inherit;background:transparent}.hmb-sound .hs-asset-select:hover:not(:disabled){box-shadow:inset 0 0 0 1px var(--active-shot-color)}.hmb-sound .hs-more{display:block;margin:12px auto 0;padding:6px 16px;color:#9be8fa}.hmb-sound .hs-empty{display:flex;align-items:center;justify-content:center;min-height:90px;color:#778da4;font-size:11px;text-align:center;line-height:1.8}
.hmb-sound .hs-shot-stack{flex:0 1 auto;max-height:48%;min-height:44px;overflow:auto;display:flex;flex-direction:column;gap:5px;padding:0 8px 8px}.hmb-sound .hs-shot-row{flex:0 0 auto;border:1px solid var(--shot-color);border-radius:8px;background:linear-gradient(100deg,#321c36bb,#11101d);overflow:hidden}.hmb-sound .hs-shot-row.active{border-color:var(--shot-color);background:linear-gradient(100deg,color-mix(in srgb,var(--shot-color) 18%,#08121e),#08121e)}.hmb-sound .hs-shot-head{width:100%;height:30px;display:flex;align-items:center;gap:9px;padding:0 9px;border:0;border-radius:0;background:transparent;text-align:left}.hmb-sound .hs-shot-head i{display:grid;place-items:center;min-width:24px;height:21px;padding:0 4px;border:1px solid #a65c8a;border-radius:5px;background:#7e2a5b44;color:#ffe0f1;font-size:10px;font-style:normal;font-weight:900}.hmb-sound .hs-shot-row.active .hs-shot-head i{border-color:var(--shot-color);background:color-mix(in srgb,var(--shot-color) 22%,transparent);color:var(--shot-color)}.hmb-sound .hs-shot-head strong{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.hmb-sound .hs-shot-head span{color:#dc98c7;font-size:9px}.hmb-sound .hs-shot-row.active .hs-shot-head span{color:var(--shot-color)}.hmb-sound .hs-bound-list{display:flex;gap:7px;padding:5px 7px 7px;overflow-x:auto;border-top:1px solid #50678040}.hmb-sound .hs-bound{position:relative;flex:0 0 220px;width:220px;height:68px;display:grid;grid-template-columns:31px minmax(0,1fr);gap:8px;align-items:center;padding:7px 25px 6px 8px;border:1px solid var(--shot-color);border-radius:8px;background:linear-gradient(145deg,#0c1b29,#080d17)}.hmb-sound .hs-bound.playing{border-color:var(--shot-color);box-shadow:0 0 11px #22d3ee44;background:linear-gradient(145deg,#07344a,#08121f)}.hmb-sound .hs-preview{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;padding:0;border-radius:50%;color:#c5deed;border:1px solid #5d7890;background:#091522}.hmb-sound .hs-preview svg{width:15px;height:15px}.hmb-sound .hs-play-shape{fill:currentColor;stroke:none}.hmb-sound .playing .hs-preview,.hmb-sound .hs-preview[aria-pressed=true]{color:#04232f;background:#1fe4f2;border-color:#8cf8ff;box-shadow:0 0 8px #22d3ee66}.hmb-sound .hs-bound-name{width:100%;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 0 4px;border:0;border-radius:0;background:transparent;color:#d4e4ef;text-align:left;font-size:9px;font-weight:750}.hmb-sound .hs-bound input[type=range]{display:block;width:100%;height:11px;margin:0;padding:0;accent-color:#22d3ee;cursor:pointer}.hmb-sound .hs-time{display:block;text-align:right;font-variant-numeric:tabular-nums;color:#9bb8cd;font-size:8px;margin-top:2px}.hmb-sound .hs-remove{position:absolute;right:4px;top:3px;width:17px;height:17px;padding:0;border:0;color:#b4c7d8;font-size:15px;background:transparent}.hmb-sound .hs-row-empty{color:#67869a;font-size:10px;padding:13px}
.hmb-sound .hs-status{height:32px;flex:0 0 32px;display:flex;align-items:center;padding:0 12px;border-top:1px solid var(--line);color:#8fa8bb;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.hmb-sound .hs-status[data-error=true]{color:#fda4af}.hmb-sound .hs-detail{flex:0 1 auto;min-height:0;max-height:240px;overflow:auto;margin:0 8px 7px;padding:9px;border:1px solid #597591;border-radius:8px;background:#0a1422}.hmb-sound .hs-detail-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}.hmb-sound .hs-detail-head strong{flex:1;font-size:11px}.hmb-sound .hs-detail button{padding:3px 8px;font-size:10px}.hmb-sound .hs-detail select,.hmb-sound .hs-detail input,.hmb-sound .hs-detail textarea{max-width:100%;padding:5px;border:1px solid #3a5068;border-radius:5px;background:#0a1120;color:#e2ebf4;font-size:10px}.hmb-sound .hs-detail textarea{width:100%;height:42px;resize:vertical}.hmb-sound .hs-flags{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:7px}.hmb-sound .hs-flags label{display:flex;align-items:center;gap:4px;font-size:10px}.hmb-sound .hs-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:7px}.hmb-sound .hs-grid label{display:flex;flex-direction:column;gap:4px;font-size:9px;color:#9badc0}
.hmb-sound [data-hmb-native-identity],.hmb-sound [data-hmb-native-actions]{display:none}.hmb-sound[data-hmb-native-header=active] [data-hmb-native-identity],.hmb-sound[data-hmb-native-header=active] [data-hmb-native-actions]{display:flex;align-items:center}.hmb-sound[data-hmb-native-header=active] .hs-brand{display:none}@container(max-width:820px){.hmb-sound .hs-main{grid-template-columns:150px minmax(0,1fr)}.hmb-sound .hs-files{grid-template-columns:repeat(auto-fill,minmax(118px,1fr))}.hmb-sound .hs-heading small{display:none}.hmb-sound .hs-bound{flex-basis:200px;width:200px}}
.hmb-sound .hs-head[data-sound-toggle-surface=header]{cursor:grab}
.react-flow__node:has(.hmb-sound) [data-parameter-name="HMB_SITE_FOLDER_DRAFT"]{display:none!important}
.hmb-sound .hs-main{flex-basis:240px}
.hmb-sound .hs-head[data-sound-toggle-surface=header]:active{cursor:grabbing}
.hmb-sound[data-hmb-native-header=active] [data-hmb-native-identity]{flex:1 1 auto}
.hmb-sound[data-hmb-native-header=active] [data-hmb-native-actions]{flex:0 0 auto}
.hmb-sound[data-hmb-native-header=active] .hs-actions{margin-left:0}
.hmb-sound[data-sound-view=compact]{height:auto;min-height:0}
.hmb-sound[data-sound-view=compact] .hs-main{display:none}
.hmb-sound[data-sound-view=compact] .hs-shot-stack{max-height:min(390px,48vh);padding-top:8px}
[data-hmb-sound-frame][data-sound-view=compact],
.react-flow__node:not([data-hmb-native-icon-layout],[data-hmb-native-rollup-layout],[data-hmb-native-fold-transition]):has([data-hmb-sound-frame][data-sound-view=compact]),
.react-flow__node:not([data-hmb-native-icon-layout],[data-hmb-native-rollup-layout],[data-hmb-native-fold-transition]) :has([data-hmb-sound-frame][data-sound-view=compact]){height:auto!important;min-height:0!important;max-height:none!important}
`;
function renderSoundResults(state, ui, active, selected, busy) {
  const search = ui.search.toLocaleLowerCase();
  const list = state.assets.filter(asset =>
    (!ui.role || asset.role === ui.role) &&
    (!ui.folder || String(asset.relative_path || "").replaceAll("\\", "/").startsWith(ui.folder + "/")) &&
    (!search || `${asset.name} ${asset.relative_path}`.toLocaleLowerCase().includes(search))
  );
  const assets=list.slice(0,ui.limit).map(a=>{
    const id=assetIdentity(a),chosen=selected.some(t=>String(t.source_uid||t.relative_path||"")===id),url=assetPreview(state,a);
    return `<article class="hs-asset${chosen?' selected':''}" data-asset="${escape(id)}" style="--audio-color:${colors[a.role]||'#22d3ee'}"><div class="hs-art">${wave(id)}<button type="button" class="hs-preview" data-preview-asset="${escape(id)}" aria-label="${escape(a.name)} 미리듣기" aria-pressed="false" ${url?'':'disabled'}>${playIcon}</button></div><strong class="hs-asset-name" title="${escape(a.relative_path)}">${escape(a.name)}</strong><div class="hs-asset-meta"><span>${escape(labels[a.role]||a.role||'사운드')}</span><span>${a.duration_seconds?seconds(a.duration_seconds):escape(String(a.extension||'').replace('.','').toUpperCase())}</span></div><button type="button" class="hs-asset-select" data-add="${escape(id)}" aria-label="${escape(assetLabel(a.name,chosen))}" ${busy||chosen||!active?'disabled':''}></button></article>`;
  }).join("");
  return {count:list.length, content:`<div class="hs-files">${assets}</div>${!list.length?'<div class="hs-empty">사운드가 없습니다.<br>대사 · 효과음 · 환경음 · 음악</div>':''}${list.length>ui.limit?'<button class="hs-more" data-more>더 보기</button>':''}`};
}

function render(state, ui, pending) {
  const busy=Boolean(state.busy||pending),rows=hmbSoundShotRows(state);
  const active=rows.find(row=>sameShot(state.shot,row)),selected=active?state.tracks.filter(t=>sameShot(t,active)):[];
  const results=renderSoundResults(state,ui,active,selected,busy);
  const options=(values,current,label=v=>v)=>values.map(v=>`<option value="${escape(v)}"${v===current?" selected":""}>${escape(label(v))}</option>`).join("");
  const field=(t,key,label)=>`<label>${label}<input data-track="${escape(t.instance_id)}" data-field="${key}" type="number" step="0.01" ${key==="gain_db"?'min="-60" max="12"':'min="0"'} value="${escape(t[key]??"")}"></label>`;
  const tree=`<button data-folder="" class="${!ui.folder&&!ui.role?'active':''}">${folderIcon}<span>전체 사운드</span><b>${state.assets.length}</b></button><small>폴더</small>${hmbSoundFolders(state).map(([folder,count])=>`<button data-folder="${escape(folder)}" class="${ui.folder===folder?'active':''}" style="padding-left:${8+(folder.split('/').length-1)*12}px">${folderIcon}<span>${escape((folder.startsWith('site:') && !folder.includes('/') && state.site_settings?.links?.find(link=>link.id===folder.slice(5))?.label) || folder.split('/').at(-1))}</span><b>${count}</b></button>`).join("")}<small>종류별 보기</small>${roles.map(role=>`<button data-role-filter="${role}" class="${ui.role===role?'active':''}"><span>${labels[role]}</span><b>${state.assets.filter(a=>a.role===role).length}</b></button>`).join("")}`;
  const shots=rows.map(row=>{
    const tracks=state.tracks.filter(t=>sameShot(t,row)),isActive=active===row;
    return `<section class="hs-shot-row${isActive?' active':''}" data-shot-row="${escape(row.shot_uuid)}" style="--shot-color:${shotColor(row)}"><button class="hs-shot-head" data-shot="${escape(row.shot_uuid)}" aria-pressed="${isActive}" ${busy?'disabled':''}><i>${row.legacy?'•':escape(String(row.number).padStart(2,'0'))}</i><strong>${escape(row.name)}</strong><span>${tracks.length}개</span></button>${tracks.length?`<div class="hs-bound-list nowheel">${tracks.map(t=>{
      const start=Number(t.in_seconds)||0,end=t.out_seconds==null?Number(t.duration_seconds)||0:Number(t.out_seconds);
      return `<article class="hs-bound" data-instance="${escape(t.instance_id)}"><button class="hs-preview" data-preview-track="${escape(t.instance_id)}" aria-label="${escape(t.name)} 재생" aria-pressed="false" ${trackPreview(state,t)?'':'disabled'}>${playIcon}</button><div><button class="hs-bound-name" data-detail="${escape(t.instance_id)}" title="${escape(t.name)} · 상세 편집">${escape(t.name)}</button><input type="range" min="${start}" max="${end||1}" step="0.01" value="${start}" data-scrub="${escape(t.instance_id)}" aria-label="${escape(t.name)} 재생 위치" ${trackPreview(state,t)?'':'disabled'}><span class="hs-time" data-time="${escape(t.instance_id)}">0:00 / ${seconds(Math.max(0,end-start))}</span></div><button class="hs-remove" data-remove="${escape(t.instance_id)}" aria-label="${escape(t.name)} 연결 해제" ${busy?'disabled':''}>×</button></article>`;
    }).join("")}</div>`:isActive?'<div class="hs-row-empty">사운드 카드를 선택해 이 샷에 연결하세요.</div>':''}</section>`;
  }).join("");
  const detail=state.tracks.find(t=>String(t.instance_id)===ui.detail);
  const drawer=detail?`<section class="hs-detail" data-detail-drawer><div class="hs-detail-head"><strong>${escape(detail.name)} · 사운드 상세</strong><button data-duplicate="${escape(detail.instance_id)}" ${busy?'disabled':''}>복제</button><button data-close-detail aria-label="사운드 상세 닫기">×</button></div><div class="hs-flags"><select data-track="${escape(detail.instance_id)}" data-field="role">${options(roles,detail.role,r=>labels[r])}</select><select data-track="${escape(detail.instance_id)}" data-field="purpose">${options(['both','reference','mix'],detail.purpose,v=>({both:'생성 참고 + 믹싱',reference:'생성 참고',mix:'최종 믹싱'}[v]))}</select>${[['enabled','사용'],['lipsync','립싱크'],['loop','반복']].map(([key,label])=>`<label><input type="checkbox" data-track="${escape(detail.instance_id)}" data-field="${key}"${detail[key]?' checked':''}>${label}</label>`).join('')}<input data-track="${escape(detail.instance_id)}" data-field="target" value="${escape(detail.target)}" placeholder="대상 / 화자"></div><textarea data-track="${escape(detail.instance_id)}" data-field="transcript" placeholder="대사 원문 / 사용 의도">${escape(detail.transcript)}</textarea><div class="hs-grid">${field(detail,'start_seconds','샷 시작(초)')}${field(detail,'in_seconds','음원 IN(초)')}${field(detail,'out_seconds','음원 OUT(빈칸=끝)')}${field(detail,'gain_db','볼륨(dB)')}</div></section>`:'';
  return `<style>${style}</style><div class="hmb-sound nodrag nopan" data-hmb-node-type="HMBSoundLibrary" data-hmb-sound-widget style="--active-shot-color:${shotColor(active)}"><header class="hs-head group" data-sound-toggle-surface="header"><span class="hs-mark hs-brand">${wave('sound')}</span><div class="hs-heading hs-brand"><strong>HMB Sound Library</strong><small>사운드 에셋 · ${escape(active?.name||'샷 선택')}</small></div><div data-hmb-native-identity></div><div data-hmb-native-actions></div><div class="hs-actions nodrag"><button type="button" data-action="site-settings" aria-label="프로젝트 Add" title="프로젝트 Add">S</button><button type="button" data-action="refresh" aria-label="사운드 폴더 다시 읽기" title="사운드 폴더 다시 읽기" ${!ui.syncNotice&&(busy||!state.project_root)?'disabled':''}>${scanFolderIcon}</button><button data-action="cancel" ${busy?'':'hidden'}>준비 취소</button></div></header><div class="hs-main"><aside class="hs-panel hs-tree"><div class="hs-panel-title">사운드 폴더<span>${state.assets.length}</span></div><div class="hs-folder-list nowheel">${tree}</div></aside><section class="hs-panel hs-browser"><div class="hs-filter"><input data-search placeholder="⌕  사운드 검색" aria-label="사운드 검색" value="${escape(ui.search)}"><b>${selected.length} 선택 / ${results.count}개</b></div><div class="hs-catalog nowheel">${results.content}</div></section></div><div class="hs-shot-stack nowheel" aria-label="ImageAsset 샷 사운드">${shots||'<div class="hs-empty">ImageAsset의 샷을 연결하세요.</div>'}</div>${drawer}<div class="hs-status" role="status" data-error="${Boolean(state.error_code)}">${escape(ui.syncNotice||ui.commandNotice||ui.mediaNotice||(pending?'사운드 작업 적용 중…':state.status||'준비됨'))}${state.error_code?' · '+escape(state.error_code):''}</div></div>`;
}
function hmbSoundImplementation(container, props = {}) {
  if (!container) return {update(){},cleanup(){}};
  if (container.__hmbSoundController) {container.__hmbSoundController.update(props);return container.__hmbSoundController;}
  const initial=hmbReduceSoundTransport(read({}),null,props);
  let latest=props,state=initial.state,transport=initial.transport,disposed=false,pending=null,preview=null,playGeneration=0,pendingSeek=null;
  let syncWaiting=initial.needsSync,syncTimer=null,syncAttempts=0,syncCycle=0,ackTimer=null;
  let painted=null;
  let syncFloor=initial.gap||null;
  const readTarget=()=>syncFloor?.stream_id||transport?.stream_id||"";
  const doc=container.ownerDocument||globalThis.document;
  const ui={search:"",role:"",folder:"",limit:80,detail:"",mediaNotice:"",commandNotice:"",syncNotice:"",nativeHeader:false,compact:false};
  const frame=doc.createElement("div");frame.style.cssText="height:100%;min-height:500px";
  frame.setAttribute("data-hmb-sound-frame", "");
  const initialNoDrag=container.classList.contains("nodrag");
  const root=()=>frame.querySelector("[data-hmb-sound-widget]");
  const announceNativeHeader=phase=>{
    const Event=doc.defaultView?.CustomEvent;
    if(Event)doc.dispatchEvent(new Event(`hmb-color-lut-header-${phase}`,{detail:{container}}));
  };
  const applyNativeHeader=()=>{
    const panel=root();
    panel?.setAttribute("data-hmb-native-header",ui.nativeHeader?"active":"fallback");
    panel?.classList.toggle("nodrag",!ui.nativeHeader);
    container.classList.toggle("nodrag",!ui.nativeHeader);
  };
  const applyView=()=>{
    const view=ui.compact?"compact":"expanded";
    frame.dataset.soundView=view;
    root()?.setAttribute("data-sound-view",view);
  };
  // This element remains connected while cards, Shot rows and status repaint.
  const audio=doc.createElement("audio");audio.preload="none";audio.hidden=true;audio.setAttribute("data-sound-preview-player","");
  container.replaceChildren(frame,audio);
  const retireAudio=()=>{playGeneration++;preview=null;pendingSeek=null;try{audio.pause();audio.removeAttribute("src");audio.preload="none";audio.load();}catch{}};
  const previewTrack=id=>{
    const t=state.tracks.find(t=>String(t.instance_id)===id);
    return t&&hmbSoundShotRows(state).some(row=>sameShot(t,row))?{kind:"track",id,url:trackPreview(state,t),identity:String(t.source_uid||t.relative_path||"")+String(t.media_signature||""),project:state.project_uid,start:Math.max(0,Number(t.in_seconds)||0),end:t.out_seconds==null?Number(t.duration_seconds)||null:Number(t.out_seconds)}:null;
  };
  const previewAsset=id=>{const a=state.assets.find(a=>assetIdentity(a)===id);return a?{kind:"asset",id,url:assetPreview(state,a),identity:assetIdentity(a),project:state.project_uid,start:0,end:Number(a.duration_seconds)||null}:null;};
  const currentPreview=()=>preview?.kind==="track"?previewTrack(preview.id):preview?.kind==="asset"?previewAsset(preview.id):null;
  const bounds=()=>{const start=preview?.start||0,available=Number.isFinite(audio.duration)?audio.duration:preview?.end||0;return {start,end:Math.max(start,preview?.end==null?available:Math.min(available||preview.end,preview.end))};};
  function syncPlayback(){
    if(disposed)return;
    const segment=bounds();
    if(preview&&audio.readyState>=2&&Number.isFinite(audio.duration)&&pendingSeek!==null){const seek=pendingSeek;try{audio.currentTime=Math.max(segment.start,Math.min(segment.end,seek));pendingSeek=null;}catch{}}
    if(preview&&segment.end>segment.start&&audio.currentTime>=segment.end&&!audio.paused)audio.pause();
    const playing=Boolean(preview&&!audio.paused&&!audio.ended);
    for(const button of frame.querySelectorAll("[data-preview-track],[data-preview-asset]")){
      const own=preview&&(button.dataset.previewTrack===preview.id&&preview.kind==="track"||button.dataset.previewAsset===preview.id&&preview.kind==="asset");
      button.setAttribute("aria-pressed",String(Boolean(own&&playing)));button.innerHTML=own&&playing?pauseIcon:playIcon;
    }
    for(const card of frame.querySelectorAll(".hs-bound[data-instance]")){
      const own=preview?.kind==="track"&&card.dataset.instance===preview.id;
      card.classList.toggle("playing",Boolean(own&&playing));
      const t=state.tracks.find(t=>String(t.instance_id)===card.dataset.instance),start=own?segment.start:Number(t?.in_seconds)||0,end=own?segment.end:t?.out_seconds==null?Number(t?.duration_seconds)||0:Number(t.out_seconds);
      const seek=card.querySelector("[data-scrub]");if(seek){seek.min=String(start);seek.max=String(end||1);if(doc.activeElement!==seek)seek.value=String(own?audio.currentTime||start:start);}
      const time=card.querySelector("[data-time]");if(time)time.textContent=`${seconds(own?Math.max(0,(audio.currentTime||0)-start):0)} / ${seconds(Math.max(0,end-start))}`;
    }
  }
  function paintPreparedShot(view){
    // Catalog/track changes use the full renderer. Page and status changes
    // reuse the prepared cards, scroll positions and playing audio element.
    if(!painted || ui.detail || !root() || !sameSoundValue(painted.ui,ui)
      || !["project_uid","project_id","project_root","assets","folders","tracks","shot_catalog"].every(key=>sameSoundValue(painted.state[key],state[key])))return false;
    const rows=hmbSoundShotRows(view),active=rows.find(row=>sameShot(view.shot,row));
    const selected=active?view.tracks.filter(t=>sameShot(t,active)):[];
    const selectedIds=new Set(selected.map(t=>String(t.source_uid||t.relative_path||"")));
    const busy=Boolean(state.busy||pending||syncWaiting),current=root();
    current.style.setProperty("--active-shot-color",shotColor(active));
    current.querySelector(".hs-heading small").textContent=`사운드 에셋 · ${active?.name||'샷 선택'}`;
    const count=current.querySelector(".hs-filter b");
    count.textContent=`${selected.length} 선택 / ${painted.filteredCount}개`;
    for(const card of current.querySelectorAll("[data-asset]")){
      const chosen=selectedIds.has(card.dataset.asset),add=card.querySelector("[data-add]");
      card.classList.toggle("selected",chosen);add.disabled=busy||latest.disabled||chosen||!active;
      add.setAttribute("aria-label",assetLabel(card.querySelector(".hs-asset-name").textContent,chosen));
    }
    for(const row of current.querySelectorAll("[data-shot-row]")){
      const isActive=row.dataset.shotRow===active?.shot_uuid,head=row.querySelector("[data-shot]");
      row.classList.toggle("active",isActive);head.setAttribute("aria-pressed",String(isActive));head.disabled=busy;
      const hint=row.querySelector(".hs-row-empty");
      if(!isActive)hint?.remove();
      else if(!hint&&!row.querySelector(".hs-bound-list")){
        const empty=doc.createElement("div");empty.className="hs-row-empty";empty.textContent="사운드 카드를 선택해 이 샷에 연결하세요.";row.append(empty);
      }
    }
    for(const button of current.querySelectorAll("[data-remove],[data-more]"))button.disabled=busy;
    current.querySelector('[data-action="site-settings"]').disabled=Boolean(latest.disabled);
    current.querySelector('[data-action="refresh"]').disabled=!ui.syncNotice&&(busy||!state.project_root);
    current.querySelector('[data-action="cancel"]').hidden=!busy;
    const status=current.querySelector(".hs-status");status.dataset.error=String(Boolean(state.error_code));
    status.textContent=(ui.syncNotice||ui.commandNotice||ui.mediaNotice||(pending?'사운드 작업 적용 중…':state.status||'준비됨'))+(state.error_code?' · '+state.error_code:'');
    current.toggleAttribute("data-sound-sync-waiting",syncWaiting);syncPlayback();return true;
  }
  function paintSearchResults(){
    const panel = root(), catalog = panel?.querySelector(".hs-catalog");
    if (!catalog) return;
    const rows = hmbSoundShotRows(state);
    const active = rows.find(row => sameShot(pending?.displayShot || state.shot, row));
    const selected = active ? state.tracks.filter(track => sameShot(track, active)) : [];
    const busy = Boolean(state.busy || pending || syncWaiting);
    const results = renderSoundResults(state, ui, active, selected, busy || latest.disabled);
    catalog.innerHTML = results.content;
    panel.querySelector(".hs-filter b").textContent = `${selected.length} 선택 / ${results.count}개`;
    const more = catalog.querySelector("[data-more]");
    if (more) more.disabled = busy;
    if (painted) painted = {...painted, filteredCount:results.count, ui:{...ui}};
    if (preview) syncPlayback();
  }
  function paint(){
    if(disposed)return;
    if(preview){const valid=currentPreview();if(!valid||valid.url!==preview.url||valid.identity!==preview.identity||valid.project!==preview.project)retireAudio();else{preview.start=valid.start;preview.end=valid.end;}}
    // Presentation only: commands still use the confirmed state/context and
    // authoring remains locked until the exact host response arrives.
    const target=pending?.displayShot&&hmbSoundShotRows(state).find(row=>sameShot(row,pending.displayShot));
    const view=target?{...state,shot:target}:state;
    if(paintPreparedShot(view))return;
    const scroll=new Map([...frame.querySelectorAll(".hs-catalog,.hs-shot-stack,.hs-folder-list,.hs-bound-list")].map(el=>[el.className+":"+(el.closest("[data-shot-row]")?.dataset.shotRow||""),[el.scrollTop,el.scrollLeft]]));
    const template=doc.createElement("template");template.innerHTML=render(view,ui,Boolean(pending||syncWaiting));
    const incoming=template.content.querySelector("[data-hmb-sound-widget]");
    const header=incoming.firstElementChild;
    const body=Array.from(incoming.children).slice(1);
    for(const item of body)item.classList.add("nodrag");
    const current=root();
    if(current){
      const liveHeader=current.firstElementChild;
      liveHeader.querySelector(".hs-heading small").textContent=header.querySelector(".hs-heading small").textContent;
      liveHeader.querySelector('[data-action="site-settings"]').disabled=Boolean(latest.disabled);
      liveHeader.querySelector('[data-action="refresh"]').disabled=header.querySelector('[data-action="refresh"]').disabled;
      liveHeader.querySelector('[data-action="cancel"]').hidden=header.querySelector('[data-action="cancel"]').hidden;
      while(current.lastElementChild!==liveHeader)current.lastElementChild.remove();
      current.append(...body);
    }else{
      frame.replaceChildren(template.content);
      applyView();applyNativeHeader();
    }
    for(const el of frame.querySelectorAll(".hs-catalog,.hs-shot-stack,.hs-folder-list,.hs-bound-list")){const saved=scroll.get(el.className+":"+(el.closest("[data-shot-row]")?.dataset.shotRow||""));if(saved){el.scrollTop=saved[0];el.scrollLeft=saved[1];}}
    root()?.toggleAttribute("data-sound-sync-waiting",syncWaiting);
    if(latest.disabled)for(const control of frame.querySelectorAll("[data-add]"))control.disabled=true;
    if(state.busy||pending||syncWaiting)for(const control of frame.querySelectorAll("button,input,select,textarea"))if(!control.matches("[data-action=cancel],[data-action=site-settings],[data-search],[data-folder],[data-role-filter],[data-preview-track],[data-preview-asset],[data-scrub],[data-detail],[data-close-detail],[data-hmb-native-identity] *,[data-hmb-native-actions] *")&&!(syncWaiting&&control.matches('[data-action="refresh"]')))control.disabled=true;
    syncPlayback();
    const filteredCount=Number(frame.querySelector(".hs-filter b").textContent.match(/\/ (\d+)개$/)?.[1]||0);
    painted={state,ui:{...ui},filteredCount};
  }
  function requestSync(reset=false){
    if(disposed)return;
    if(reset){clearTimeout(syncTimer);syncTimer=null;syncAttempts=0;syncCycle++;}
    syncWaiting=true;
    if(syncTimer!==null)return;
    if(syncAttempts>=3){
      ui.syncNotice="사운드 연결 응답을 확인하지 못했습니다. 새로고침으로 다시 확인하세요.";paint();return;
    }
    ui.syncNotice="사운드 최신 목록을 다시 연결하는 중…";syncAttempts++;
    const cycle=syncCycle, expectedStreamId=readTarget();
    syncTimer=setTimeout(()=>{syncTimer=null;requestSync();},1500*syncAttempts);
    paint();
    const Event=doc.defaultView?.CustomEvent;
    if(!Event)return;
    // The native editor owns the session and the node identity. This read
    // never enters the widget property writer, even if the bridge is absent.
    container.dispatchEvent(new Event("hmb-sound-read-snapshot",{detail:{expectedStreamId,receive:value=>{
      if(disposed||!syncWaiting||cycle!==syncCycle||readTarget()!==expectedStreamId)return;
      const received=hmbReduceSoundTransport(state,transport,value,true);
      if(received.kind==="full"&&(!expectedStreamId||received.transport.stream_id===expectedStreamId))acceptTransport(received);
    }}}));
  }
  function command(action,extra={}){
    if(disposed||((pending||state.busy||latest.disabled||syncWaiting)&&action!=="cancel"))return;
    const fail=()=>{if(!disposed){clearTimeout(ackTimer);ackTimer=null;pending=null;state={...state,error_code:"SOUND_TRANSPORT_FAILED",status:"사운드 변경을 전송하지 못했습니다. 연결을 확인하세요."};paint();}};
    if(typeof latest.onChange!=="function"){fail();return;}
    const request={id:globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`,action,...extra,context:{project_uid:state.project_uid,channel_uuid:state.shot.channel_uuid,shot_uuid:state.shot.shot_uuid,revision:state.revision}};
    const displayShot=action==="shot"?hmbSoundShotRows(state).find(row=>row.shot_uuid===extra.shot_uuid):null;
    const owned={id:request.id,revision:state.revision,scope:scopeKey(state),displayShot};pending=owned;ui.commandNotice="";
    clearTimeout(ackTimer);ackTimer=setTimeout(()=>{ackTimer=null;if(!disposed&&pending===owned){owned.recovering=true;requestSync();}},12000);
    const captured={__hmb_sound_command:request};paint();
    try{Promise.resolve(latest.onChange(captured)).catch(()=>{if(pending===owned)fail();});}catch{if(pending===owned)fail();}
  }
  function choosePreview(next,shouldPlay=true){
    if(!next?.url||disposed)return;
    ui.mediaNotice="";
    const same=preview&&preview.kind===next.kind&&preview.id===next.id&&preview.url===next.url&&preview.identity===next.identity&&preview.project===next.project;
    if(same){if(shouldPlay&&!audio.paused){audio.pause();return;}}
    else{playGeneration++;audio.pause();preview=next;audio.preload="auto";audio.setAttribute("src",next.url);pendingSeek=next.start;audio.load();}
    if(shouldPlay){
      const segment=bounds();if(same&&(audio.ended||audio.currentTime<segment.start||segment.end>segment.start&&audio.currentTime>=segment.end-.025)){pendingSeek=segment.start;syncPlayback();}
      const generation=++playGeneration;
      try{Promise.resolve(audio.play()).catch(()=>{if(disposed||generation!==playGeneration)return;ui.mediaNotice="미리듣기를 재생하지 못했습니다. 음원 연결을 확인하세요.";paint();});}catch{ui.mediaNotice="미리듣기를 재생하지 못했습니다.";paint();}
    }
    syncPlayback();
  }
  const click=event=>{
    if(event.target.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"))return;
    const button=event.target.closest?.("button");if(!button||button.disabled)return;
    event.stopPropagation();
    if(button.dataset.action==="site-settings"){
      openProjectFolderCards(container,state,{media:"sound",trigger:button,send(request) {
        if (typeof latest.onChange !== "function") throw new Error("폴더 선택 요청을 보낼 수 없습니다.");
        return latest.onChange({__hmb_sound_command:{id:request.request_id,action:"site_settings",site_settings_request:request}});
      }});
      return;
    }
    if(button.dataset.action==="refresh"&&syncWaiting){requestSync(true);return;}
    if(button.hasAttribute("data-preview-track")){choosePreview(previewTrack(button.dataset.previewTrack));return;}
    if(button.hasAttribute("data-preview-asset")){choosePreview(previewAsset(button.dataset.previewAsset));return;}
    if(button.hasAttribute("data-folder")){ui.folder=button.dataset.folder;ui.role="";ui.limit=80;paint();return;}
    if(button.hasAttribute("data-role-filter")){ui.role=ui.role===button.dataset.roleFilter?"":button.dataset.roleFilter;ui.folder="";ui.limit=80;paint();return;}
    if(button.hasAttribute("data-more")){ui.limit+=80;paint();return;}
    if(button.hasAttribute("data-detail")){ui.detail=ui.detail===button.dataset.detail?"":button.dataset.detail;paint();return;}
    if(button.hasAttribute("data-close-detail")){ui.detail="";paint();return;}
    if(button.hasAttribute("data-shot")){if(button.dataset.shot!==state.shot.shot_uuid){ui.detail="";command("shot",{shot_uuid:button.dataset.shot});}return;}
    if(button.dataset.action){command(button.dataset.action,button.dataset.action==="refresh"?{project_id:state.project_id}:{});return;}
    if(button.dataset.add){const a=state.assets.find(a=>assetIdentity(a)===button.dataset.add),active=hmbSoundShotRows(state).find(row=>sameShot(state.shot,row));if(a&&active)command(active.legacy?"add":"shot_add",{relative_path:a.relative_path,source_uid:a.source_uid||"",...(active.legacy?{}:{shot_uuid:active.shot_uuid})});return;}
    for(const action of ["remove","duplicate"])if(button.dataset[action]){command(action,{instance_id:button.dataset[action]});return;}
  };
  const seek=el=>{const next=previewTrack(el.dataset.scrub);if(!next?.url)return;const time=Number(el.value);if(!Number.isFinite(time))return;choosePreview(next,false);const segment=bounds();pendingSeek=Math.max(segment.start,Math.min(segment.end||time,time));syncPlayback();};
  const change=event=>{const el=event.target;if(el.hasAttribute?.("data-scrub")){event.stopPropagation();seek(el);return;}if(el.dataset?.track&&el.dataset.field){event.stopPropagation();const value=el.type==="checkbox"?el.checked:el.type==="number"?(el.value===""&&el.dataset.field==="out_seconds"?null:Number(el.value)):el.value;command("edit",{instance_id:el.dataset.track,changes:{[el.dataset.field]:value}});}};
  const input=event=>{const el=event.target;if(el.hasAttribute?.("data-scrub")){event.stopPropagation();seek(el);return;}if(!el.hasAttribute?.("data-search"))return;event.stopPropagation();ui.search=el.value;ui.limit=80;paintSearchResults();};
  const localPointer=event=>{if(event.button===1)return;if(event.target.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"))return;if(event.target.closest?.("button,input,select,textarea,.hs-asset,.hs-bound,.hs-shot-row"))event.stopPropagation();};
  const keydown=event=>{if(event.target.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"))return;event.stopPropagation();if(["Delete","Backspace"].includes(event.key)&&!event.target.matches?.("input,textarea,[contenteditable=true]"))event.preventDefault();};
  const dragstart=event=>{if(!event.target.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]")){event.preventDefault();event.stopPropagation();}};
  const nativeHeader=event=>{if(event.target===container){ui.nativeHeader=event.detail?.active===true;applyNativeHeader();}};
  const toggleView=event=>{
    const target=event.target?.nodeType===3?event.target.parentElement:event.target;
    const header=target?.closest?.('[data-sound-toggle-surface="header"]');
    if(event.button!==0||!header||!container.contains(header)||target.closest("[data-hmb-native-identity],[data-hmb-native-actions],button,input,select,textarea,label,a,[contenteditable=true]"))return;
    event.preventDefault();event.stopPropagation();
    ui.compact=!ui.compact;applyView();
    const update=latest.updateNodeInternals||latest.requestNodeInternalsUpdate||latest.onUpdateNodeInternals;
    const node=container.closest(".react-flow__node[data-id]");
    if(typeof update==="function"&&node){try{update(node.dataset.id);}catch{/* ReactFlow also observes the node's size. */}}
  };
  const scrollCardStrip = event => {
    const strip = event.target?.closest?.(".hs-bound-list");
    if (!strip || !event.deltaY || event.deltaX || event.ctrlKey || strip.scrollWidth <= strip.clientWidth
        || strip.scrollHeight > strip.clientHeight + 1) return;
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? strip.clientWidth : 1;
    strip.scrollLeft += event.deltaY * unit;
    event.preventDefault();
    event.stopPropagation();
  };
  const listeners=[["wheel",scrollCardStrip],["click",click],["change",change],["input",input],["keydown",keydown],["keyup",keydown],["pointerdown",localPointer],["mousedown",localPointer],["dragstart",dragstart],["dblclick",toggleView],["hmb-color-lut-header-state",nativeHeader]];
  for(const [name,fn]of listeners)container.addEventListener(name,fn);
  const mediaEvents=["play","pause","ended","timeupdate","loadedmetadata","durationchange","canplay","canplaythrough","progress","error"];
  for(const name of mediaEvents)audio.addEventListener(name,syncPlayback);
  paint();
  container.setAttribute("data-hmb-color-lut-widget","");
  container.setAttribute("data-hmb-native-node-type","HMBSoundLibrary");
  function acceptTransport(received){
    if(received.kind==="ignored")return false;
    // A full snapshot can repair only the gaps it already includes. A new
    // publisher's full snapshot may supersede an older recovery target.
    if(received.kind==="full"&&syncFloor&&(!received.transport
      ||(received.transport.stream_id===syncFloor.stream_id?received.transport.sequence<syncFloor.sequence
        :received.transport.stream_id===transport?.stream_id)))return false;
    const incoming=received.state,epochChanged=Boolean(transport&&received.transport?.stream_id!==transport.stream_id);
    if(!received.transport&&incoming.revision<state.revision)return false;
    if(!received.transport&&!epochChanged&&pending&&incoming.ack_command_id!==pending.id&&scopeKey(incoming)===pending.scope&&incoming.revision<=pending.revision)return false;
    if(pending&&(epochChanged||incoming.ack_command_id===pending.id||scopeKey(incoming)!==pending.scope||incoming.revision>pending.revision)){
      clearTimeout(ackTimer);ackTimer=null;pending=null;
    }else if(pending?.recovering&&received.kind==="full"){
      // A timed-out authoring request is never replayed automatically. Full
      // recovery may prove only the current state, not that command's success.
      clearTimeout(ackTimer);ackTimer=null;pending=null;
      ui.commandNotice="사운드 변경 완료를 확인하지 못했습니다. 현재 목록을 확인한 뒤 다시 선택하세요.";
    }
    transport=received.transport;state=incoming;
    if (container.__hmbFolderCards) container.__hmbFolderCards.receive(state);
    else syncProjectFolderProfiles(container, state);
    const caughtUp = received.kind==="delta" && syncWaiting && !pending
      && (!syncFloor || (received.transport.stream_id===syncFloor.stream_id
        && received.transport.sequence>=syncFloor.sequence));
    if(received.kind==="full"||caughtUp){
      clearTimeout(syncTimer);syncTimer=null;syncAttempts=0;syncWaiting=false;
      syncFloor=null;syncCycle++;ui.syncNotice="";
    }
    paint();
    return true;
  }
  const controller={update(next){
    if(disposed)return;const disabledChanged=Boolean(latest.disabled)!==Boolean(next.disabled),unlocked=Boolean(latest.disabled)&&!next.disabled;latest=next;
    const received=hmbReduceSoundTransport(state,transport,next);
    if(received.needsSync){
      const priorTarget=readTarget(), gap=received.gap;
      if(gap){
        if(syncFloor?.stream_id===gap.stream_id)syncFloor.sequence=Math.max(syncFloor.sequence,gap.sequence);
        else if(!syncFloor||gap.stream_id!==transport?.stream_id)syncFloor=gap;
      }
      const cycle=syncCycle;
      queueMicrotask(()=>{if(cycle===syncCycle)requestSync(unlocked||priorTarget!==readTarget());});
      return;
    }
    if(!acceptTransport(received)&&disabledChanged)paint();
    if(unlocked&&syncWaiting)queueMicrotask(()=>requestSync(true));
  },cleanup(){if(disposed)return;container.__hmbFolderCards?.close();announceNativeHeader("retire");disposed=true;pending=null;clearTimeout(ackTimer);ackTimer=null;clearTimeout(syncTimer);syncTimer=null;retireAudio();for(const [name,fn]of listeners)container.removeEventListener(name,fn);for(const name of mediaEvents)audio.removeEventListener(name,syncPlayback);container.removeAttribute("data-hmb-color-lut-widget");container.removeAttribute("data-hmb-native-node-type");container.classList.toggle("nodrag",initialNoDrag);container.replaceChildren();if(container.__hmbSoundController===controller)delete container.__hmbSoundController;}};
  container.__hmbSoundController=controller;
  announceNativeHeader("ready");
  if(initial.needsSync)queueMicrotask(()=>requestSync());
  return controller;
}

// Existing module-local native disabled-state contract, including safe cancellation.
const HMB_NATIVE_UI_CALLBACKS = new WeakMap();
function hmbNativeUiReadCommand(value, kind) {
  let v = value;
  if (typeof v === "string") { try { v = JSON.parse(v); } catch { return false; } }
  if (!v || typeof v !== "object") return false;
  if (kind === "sound") return (v.__hmb_sound_command || v).action === "cancel";
  if (kind === "thumbnail") return v.schema === "hmb-image-asset-thumbnail-bridge"
    && ["hydrate", "catalog_probe", "catalog_page"].includes(v.operation);
  if (kind === "seedance") return (v.schema === "hmb-seedance-refresh-command"
    && ["refresh_existing", "cancel_draft_final", "open_gallery"].includes(v.action))
    || (v.schema === "hmb-seedance-render-preflight" && ["inspect", "cancel"].includes(v.action))
    || (v.schema === "hmb-seedance-shot-ui" && v.request?.action === "refresh_existing");
  if (kind === "agent") return v.schema === "hmb-agent-shot-row"
    && ["refresh", "cancel_selected"].includes(v.action?.kind);
  if (kind === "finish") return v.ui_transport?.schema === "hmb-finish-ui-transport"
    && v.ui_transport.operation === "refresh";
  if (kind === "lut") return (v.__hmb_color_lut_command__ || v).action === "cancel";
  const command = v.__hmb_picker_command__ || v;
  return ["picker", "picker-bridge"].includes(kind) && command.schema === "hmb-picker-command"
    && (["stop_read", "cancel_pending", "cancel_generate", "cancel_video_import"].includes(command.action)
      || (command.action === "video_tools" && command.payload?.op === "cancel"));
}
// Locked echoes use only primitive/raw-string identity: no state clone/hash.
// Complex values keep the original ownership-preserving update path.
function hmbNativeUiLockedEchoKey(props) {
  if (!props?.disabled || Object.getOwnPropertySymbols(props).length) return null;
  const result = [typeof props.onChange === "function", typeof props.onCommand === "function"];
  for (const key of Object.keys(props)) {
    if (["onChange", "onCommand"].includes(key)) continue;
    const property = Object.getOwnPropertyDescriptor(props, key);
    if (!property || !Object.hasOwn(property, "value")) return null;
    const value = property.value, type = typeof value;
    if (key === "ui_options" && value !== null && type === "object") {
      const prototype = Object.getPrototypeOf(value), keys = Object.keys(value);
      if ((prototype !== Object.prototype && prototype !== null) || keys.length > 64 || Object.getOwnPropertySymbols(value).length) return null;
      result.push(key, "flat-options", keys.length);
      for (const option of keys) {
        const descriptor = Object.getOwnPropertyDescriptor(value, option);
        if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
        const field = descriptor.value, fieldType = typeof field;
        if (field !== null && !["undefined", "boolean", "string", "number"].includes(fieldType)) return null;
        if (fieldType === "number" && !Number.isFinite(field)) return null;
        result.push(option, field);
      }
      continue;
    }
    if (value !== null && !["undefined", "boolean", "string", "number"].includes(type)) return null;
    if (type === "number" && !Number.isFinite(value)) return null;
    result.push(key, "primitive", value);
  }
  return result;
}
function hmbNativeUiLockedEchoMatches(next, previous) {
  return next !== null && previous != null && next.length === previous.length
    && next.every((value, index) => Object.is(value, previous[index]));
}
function hmbNativeUiContract(container, props, mount, policy) {
  if (!container) return mount(container, props);
  let c = container.__hmbNativeUiContract;
  if (c && c.kind !== policy.kind) { c.proxy.cleanup(); c = null; }
  if (!c) {
    c = { kind: policy.kind, active: true, props: {}, handle: null, originals: new Map(), observer: null, listening: false };
    const events = ["pointerdown", "mousedown", "click", "dblclick", "keydown", "beforeinput", "input", "change", "paste", "drop", "dragstart", "submit"];
    c.allowed = target => Boolean(target?.matches?.("video,audio")) || Boolean(policy.allowControl?.(target, c.props, container));
    c.guard = event => {
      if (!c.active || !c.props.disabled || c.allowed(event.target)) return;
      event.preventDefault?.(); event.stopImmediatePropagation?.(); event.stopPropagation?.();
    };
    c.restore = () => {
      c.observer?.disconnect?.();
      if (c.listening) { for (const name of events) container.removeEventListener?.(name, c.guard, true); c.listening = false; }
      for (const [el, old] of c.originals) {
        if ("disabled" in el && el.disabled !== old.disabled) el.disabled = old.disabled;
        if (old.editable !== null && el.getAttribute?.("contenteditable") !== old.editable) el.setAttribute?.("contenteditable", old.editable);
      }
      c.originals.clear();
    };
    c.sync = () => {
      // The normal enabled path adds no observers, DOM queries/writes or timers.
      if (!c.active || !c.props.disabled) return;
      if (!c.listening) { for (const name of events) container.addEventListener?.(name, c.guard, true); c.listening = true; }
      for (const [el] of c.originals) if (container.contains && !container.contains(el)) c.originals.delete(el);
      for (const el of container.querySelectorAll?.("button,input,select,textarea,[contenteditable='true']") || []) {
        if (c.allowed(el)) continue;
        if (!c.originals.has(el)) c.originals.set(el, { disabled: Boolean(el.disabled), editable: el.getAttribute?.("contenteditable") ?? null });
        if ("disabled" in el && !el.disabled) el.disabled = true;
        if (el.getAttribute?.("contenteditable") === "true") el.setAttribute?.("contenteditable", "false");
      }
      if (!c.observer) {
        const Observer = container.ownerDocument?.defaultView?.MutationObserver;
        if (Observer) c.observer = new Observer(() => c.sync());
      }
      c.observer?.observe?.(container, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "contenteditable"] });
    };
    c.wrap = () => {
      const p = { ...c.props }, cells = {};
      for (const name of ["onChange", "onCommand"]) if (typeof p[name] === "function") {
        const cell = { callback: HMB_NATIVE_UI_CALLBACKS.get(p[name]) || p[name] };
        cells[name] = cell;
        const fn = (...args) => {
          if (!c.active) throw new Error("This widget is no longer mounted.");
          if (c.props.disabled && !hmbNativeUiReadCommand(args[0], c.kind)) throw new Error("This control is disabled by Griptape.");
          return cell.callback?.(...args);
        };
        HMB_NATIVE_UI_CALLBACKS.set(fn, cell.callback); p[name] = fn;
      }
      c.callbackCells = cells; return p;
    };
    c.refreshCallbacks = () => {
      for (const [name, cell] of Object.entries(c.callbackCells || {})) {
        const current = c.props[name]; cell.callback = HMB_NATIVE_UI_CALLBACKS.get(current) || current;
      }
    };
    c.proxy = {
      update(nextProps) {
        if (!c.active || c.closing) return;
        const incoming = nextProps || {}, echoKey = hmbNativeUiLockedEchoKey(incoming);
        if (hmbNativeUiLockedEchoMatches(echoKey, c.lockedEchoKey)) { c.props = incoming; c.refreshCallbacks(); return; }
        c.lockedEchoKey = null; c.restore(); c.props = incoming; const next = c.wrap();
        if (typeof c.handle?.update === "function") c.handle.update(next);
        else c.handle = mount(container, next);
        c.sync(); c.lockedEchoKey = c.props === incoming ? echoKey : null;
      },
      cleanup() {
        if (!c.active || c.closing) return; c.closing = true; c.restore();
        try {
          // Preserve the implementation's synchronous final authored-value flush.
          if (typeof c.handle === "function") c.handle(); else c.handle?.cleanup?.();
        } finally {
          c.active = false;
          if (container.__hmbNativeUiContract === c) delete container.__hmbNativeUiContract;
        }
      },
    };
    container.__hmbNativeUiContract = c;
  }
  const incoming = props || c.props || {}, echoKey = hmbNativeUiLockedEchoKey(incoming);
  if (c.handle && hmbNativeUiLockedEchoMatches(echoKey, c.lockedEchoKey)) { c.props = incoming; c.refreshCallbacks(); return c.proxy; }
  c.lockedEchoKey = null; c.restore(); c.props = incoming; c.handle = mount(container, c.wrap()); c.sync(); c.lockedEchoKey = c.props === incoming ? echoKey : null; return c.proxy;
}

function hmbSoundNativeContract(container,props={}) {
 return hmbNativeUiContract(container,props,hmbSoundImplementation,{kind:"sound",allowControl:target=>Boolean(target?.closest?.("[data-preview-track],[data-preview-asset],[data-scrub],[data-action=cancel],[data-sound-sync-waiting] [data-action=refresh],[data-hmb-native-identity],[data-hmb-native-actions]"))});
}

// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN
// Public DOM capture only. Never inspect React internals, replay Delete, or
// pretend a disk/Git update installed the native editor safety contract.
function hmbAcquireNativeStockSafety(container) {
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!doc?.documentElement || !win?.addEventListener || !doc.createElement) return null;
  const key = "__HMB_NATIVE_STOCK_SAFETY_V1__";
  let shared = doc[key];
  if (!shared) {
    const owners = new Set(), identities = new Map();
    let contextNode = null, notice = null, noticeTimer = null, disposed = false;
    const nativeReady = () => doc.documentElement.getAttribute("data-hmb-native-deletion-guard") === "engine-preflight"
      && doc.documentElement.getAttribute("data-hmb-native-deletion-protection-version") === "2";
    const rootOf = value => value?.closest?.(".react-flow__node[data-id]") || null;
    const roots = () => {
      for (const owner of owners) {
        const node = owner.active && owner.container?.isConnected ? rootOf(owner.container) : null;
        if (node) identities.set(node, node.getAttribute("data-id"));
      }
      // A stock fold/virtualized widget unmount is not a node deletion. Keep
      // its exact outer DOM identity until that node actually leaves the view.
      for (const [node] of identities) {
        if (!node.isConnected) identities.delete(node);
        else identities.set(node, node.getAttribute("data-id")); // Native rename keeps this exact retained outer node.
      }
      return new Set(identities.keys());
    };
    const isEditing = target => Boolean(target?.closest?.("input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor"));
    const canvasOf = node => node?.closest?.(".react-flow");
    const managed = () => {
      const current = roots();
      if (!current.size) return false;
      const selected = Array.from(doc.querySelectorAll(".react-flow__node.selected,.react-flow__node[aria-selected='true'],.react-flow__node[data-selected='true']"));
      if (selected.some(node => current.has(node))) return true;
      // Native group ownership is not a public DOM contract. Do not guess its
      // children; an unpatched group in an HMB canvas waits for safe installation.
      return selected.some(node => node.classList.contains("react-flow__node-GroupNode")
        && Array.from(current).some(child => canvasOf(child) && canvasOf(child) === canvasOf(node)));
    };
    const ownedTarget = target => roots().has(rootOf(target));
    const internalTarget = target => Boolean(target?.closest?.("[data-hmb-native-node-type]"))
      && !target.closest("[data-hmb-native-identity],[data-hmb-native-actions]");
    const deleteControl = target => {
      const button = target?.closest?.("button,[role='menuitem']");
      if (!button || internalTarget(button)) return null;
      const label = `${button.getAttribute("aria-label") || ""} ${button.getAttribute("title") || ""} ${button.textContent || ""}`.trim();
      const nodeMenu = /^Delete Node(?:\s|$)/i.test(label);
      const trash = Boolean(button.querySelector("svg.lucide-trash,svg.lucide-trash-2,[data-lucide='trash'],[data-lucide='trash-2']"));
      if (!nodeMenu && !(trash && button.closest(".react-flow"))) return null;
      return { button, nodeMenu };
    };
    const dismiss = () => { win.clearTimeout(noticeTimer); notice?.remove(); notice = null; };
    const show = () => {
      if (disposed || nativeReady()) return;
      if (notice?.isConnected) { notice.querySelector("button")?.focus(); return; }
      notice = doc.createElement("section");
      notice.setAttribute("data-hmb-native-safety-notice", "required");
      notice.setAttribute("role", "alert");
      Object.assign(notice.style, { position: "fixed", zIndex: "2147483647", right: "20px", bottom: "64px", maxWidth: "420px", padding: "18px", border: "1px solid #b89458", borderRadius: "18px", background: "#151c29", color: "#f8fafc", font: "13px/1.6 system-ui,sans-serif", boxShadow: "0 8px 32px #0008" });
      const title = doc.createElement("strong"); title.textContent = "HMB 노드 삭제를 중단했습니다";
      const text = doc.createElement("p");
      text.textContent = "현재 화면에서 연결 상태를 확인할 수 없습니다. 작업을 저장하고 Griptape를 다시 시작한 뒤 확인하세요.";
      const close = doc.createElement("button"); close.type = "button"; close.textContent = "확인";
      Object.assign(close.style, { border: "1px solid #64748b", borderRadius: "999px", background: "#243044", color: "#f8fafc", padding: "6px 18px", cursor: "pointer" });
      close.addEventListener("click", dismiss); notice.append(title, text, close); doc.body.append(notice); close.focus();
      noticeTimer = win.setTimeout(dismiss, 8000);
    };
    const stop = event => { event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation(); show(); };
    const keydown = event => {
      if (disposed || nativeReady() || isEditing(event.target)) return;
      if (["Delete", "Backspace"].includes(event.key) && managed()) stop(event);
    };
    const click = event => {
      if (disposed || nativeReady()) return;
      const action = deleteControl(event.target);
      if (action && (ownedTarget(action.button) || managed()
          || action.nodeMenu && contextNode?.isConnected && roots().has(contextNode))) stop(event);
      else if (!event.target?.closest?.("[data-hmb-native-safety-notice]")) { contextNode = null; dismiss(); }
    };
    const contextmenu = event => { contextNode = rootOf(event.target); };
    const dispose = () => {
      if (disposed) return;
      disposed = true; observer?.disconnect(); dismiss(); contextNode = null;
      win.removeEventListener("keydown", keydown, true); win.removeEventListener("click", click, true); win.removeEventListener("contextmenu", contextmenu, true);
      if (doc[key] === shared) delete doc[key];
    };
    const sync = () => {
      if (disposed) return;
      const retained = roots();
      if (!owners.size && !retained.size) { dispose(); return; }
      if (nativeReady() || !retained.size) dismiss();
    };
    const observer = typeof win.MutationObserver === "function" ? new win.MutationObserver(sync) : null;
    observer?.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-hmb-native-deletion-guard", "data-hmb-native-deletion-protection-version", "data-id"], childList: true, subtree: true });
    win.addEventListener("keydown", keydown, true); win.addEventListener("click", click, true); win.addEventListener("contextmenu", contextmenu, true);
    shared = { owners, sync, release(owner) {
      owner.active = false; owners.delete(owner);
      sync();
    } };
    doc[key] = shared;
  }
  const owner = { container, active: true };
  shared.owners.add(owner);
  shared.sync();
  return { refresh() { if (owner.active) shared.sync(); }, cleanup() { if (owner.active) shared.release(owner); } };
}

// Griptape loads each widget as a separate module. One selection per editor
// document also covers stock parameter fields rendered beside an HMB widget.
function hmbAcquireCanvasWheel(container) {
  const node = container?.matches?.(".widget-container") && container.closest?.(".react-flow__node");
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!node?.closest?.(".react-flow") || !win?.WheelEvent) return null;
  const key = "__HMB_CANVAS_WHEEL_SELECTION_V1__";
  let router = doc[key];
  if (!router) {
    const nodes = new Map();
    let selected = null;
    const activeScroll = "data-hmb-active-scroll";
    const activeSelector = `[${activeScroll}]`;
    const outlineStyle = doc.createElement("style");
    outlineStyle.textContent = `.react-flow .react-flow__node.nowheel ${activeSelector} {
      outline: 2px solid #4dd8ff !important;
      outline-offset: -2px !important;
      anchor-name: --hmb-selected-viewport;
      overscroll-behavior: contain !important;
    }
    .react-flow [data-hmb-scroll-frame] {
      position: absolute !important;
      position-anchor: --hmb-selected-viewport;
      top: anchor(top); left: anchor(left);
      width: anchor-size(width); height: anchor-size(height);
      box-sizing: border-box; border: 2px solid #4dd8ff;
      padding: 0; margin: 0; background: transparent;
      pointer-events: none !important; z-index: 1000;
    }`;
    doc.head.appendChild(outlineStyle);
    // Paint above composited thumbnails and sticky headers, outside the scrolling
    // content. CSS anchors follow native scroll, resize and React Flow zoom.
    const frame = doc.createElement("span");
    frame.setAttribute("data-hmb-scroll-frame", "");
    frame.setAttribute("aria-hidden", "true");
    const anchored = win.CSS?.supports("position-anchor", "--hmb-selected-viewport")
      && win.CSS.supports("width", "anchor-size(width)");
    const modal = "dialog,[role='dialog'],[aria-modal='true'],[role='menu'],[role='listbox']:not(select),[data-registration-backdrop],[data-refresh-review-backdrop]";
    const hasScroll = (element, horizontal) => {
      const room = horizontal ? element.scrollWidth - element.clientWidth : element.scrollHeight - element.clientHeight;
      if (room <= 1) return false;
      const style = win.getComputedStyle(element);
      return /^(auto|scroll|overlay)$/.test(horizontal ? style.overflowX : style.overflowY);
    };
    const canScroll = surface => hasScroll(surface, false) || hasScroll(surface, true);
    const surfaceAt = (target, root) => {
      const group = target.closest?.("[data-hmb-scroll-viewport]");
      if (group && root.contains(group)) return group;
      for (let el = target; el && el !== root; el = el.parentElement) {
        if (el.matches?.("textarea")) return el;
        if (el.matches?.("select,input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit])")) return null;
        if (canScroll(el)) return el;
      }
      return null;
    };
    const syncOutline = () => {
      const surface = selected?.surface;
      if (!surface?.isConnected) return false;
      const scrollable = canScroll(surface);
      surface.toggleAttribute(activeScroll, scrollable);
      if (anchored && scrollable && frame.previousElementSibling !== surface) {
        frame.style.borderRadius = win.getComputedStyle(surface).borderRadius;
        surface.after(frame);
      } else if (!scrollable) {
        frame.remove();
      }
      return scrollable;
    };
    const resized = win.ResizeObserver && new win.ResizeObserver(syncOutline);
    const clearOutline = () => {
      const {root, surface} = selected;
      frame.remove();
      surface.removeAttribute(activeScroll);
      for (const copy of root.querySelectorAll(activeSelector)) copy.removeAttribute(activeScroll);
      for (const copy of root.querySelectorAll("[data-hmb-scroll-frame]")) copy.remove();
    };
    const restoreViewport = () => {
      const {root, key} = selected;
      if (!key || !root.isConnected) return false;
      const matches = [...root.querySelectorAll("[data-hmb-wheel-key]")].filter(el => el.dataset.hmbWheelKey === key);
      if (matches.length !== 1) return false;
      activate(root, matches[0]);
      return true;
    };
    const changed = win.MutationObserver && new win.MutationObserver(records => {
      if (!selected) return;
      const {root, surface} = selected;
      if (!root.contains(surface)) {
        if (restoreViewport()) return;
        changed.disconnect();
        resized?.disconnect();
        clearOutline();
        // Give the renderer one turn to attach the replacement. Release the
        // detached card tree even if there is no subsequent pointer event.
        const detached = selected;
        win.setTimeout(() => {
          if (selected === detached && !restoreViewport()) clear();
        }, 0);
        return;
      }
      if (selected.key !== surface.dataset.hmbWheelKey) { clear(); return; }
      // A cloned field inherits attributes, but only the original owns the wheel.
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added.nodeType !== 1) continue;
          if (added !== frame && added.hasAttribute("data-hmb-scroll-frame")) {
            added.remove();
            continue;
          }
          if (added !== surface) added.removeAttribute(activeScroll);
          for (const copy of added.querySelectorAll(`${activeSelector},[data-hmb-scroll-frame]`)) {
            if (copy.hasAttribute("data-hmb-scroll-frame")) {
              if (copy !== frame) copy.remove();
            } else if (copy !== surface) copy.removeAttribute(activeScroll);
          }
        }
      }
      if (records.some(record => surface.contains(record.target))
          || (anchored && surface.hasAttribute(activeScroll) && frame.previousElementSibling !== surface)) syncOutline();
    });
    const clear = () => {
      if (!selected) return;
      const {surface, root, addedNoWheel, previousOverscroll} = selected;
      changed?.disconnect();
      resized?.disconnect();
      surface.removeEventListener("input", syncOutline, true);
      surface.removeEventListener("load", syncOutline, true);
      clearOutline();
      if (addedNoWheel && root.classList.contains("nowheel")) root.classList.remove("nowheel");
      if (surface.style.overscrollBehavior === "contain") surface.style.overscrollBehavior = previousOverscroll;
      selected = null;
    };
    const activate = (root, surface) => {
      if (surface === selected?.surface) return;
      clear();
      if (!surface) return;
      // Some widget renderers use the viewport className as their scroll
      // restoration key. Put the native wheel filter on the stock node only.
      selected = {root, surface, key:surface.dataset.hmbWheelKey, addedNoWheel: !root.classList.contains("nowheel"), previousOverscroll: surface.style.overscrollBehavior};
      if (selected.addedNoWheel) root.classList.add("nowheel");
      surface.style.overscrollBehavior = "contain";
      syncOutline();
      surface.addEventListener("input", syncOutline, true);
      surface.addEventListener("load", syncOutline, true);
      resized?.observe(surface);
      changed?.observe(root, {subtree:true, childList:true});
      changed?.observe(surface, {subtree:true, childList:true, characterData:true,
        attributes:true, attributeFilter:[activeScroll,"data-hmb-wheel-key","class","style","hidden","rows"]});
    };
    const select = event => {
      if (event.button !== 0 || event.isPrimary === false) return;
      const target = event.target, root = target?.closest?.(".react-flow__node");
      activate(root, nodes.has(root) && !target.closest(modal) ? surfaceAt(target, root) : null);
    };
    const actionAt = target => target.closest("button,textarea,[data-asset],[data-asset-key],[data-video-uid],[data-group-path],[data-instance]");
    const actionKey = element => element && Array.from(element.attributes)
      .filter(a => a.name !== activeScroll && (a.name === "id" || a.name === "name" || a.name.startsWith("data-")))
      .map(a => JSON.stringify([a.name,a.value])).sort().join(",");
    const afterClick = event => {
      const current = selected;
      if (event.button !== 0 || !current?.surface.contains(event.target)) return;
      const action = actionAt(event.target), identity = actionKey(action);
      if (!identity) return;
      const shotAt = el => actionKey(el.closest("[data-shot-row],[data-workspace-uuid],[data-shot-uuid]"));
      const shot = shotAt(action);
      // A card/folder button can repaint its list on click. Reacquire only
      // the same action and viewport under this completed pointer gesture.
      const {clientX, clientY} = event;
      win.setTimeout(() => {
        if (selected !== current || current.surface.isConnected) return;
        const hit = doc.elementFromPoint(clientX, clientY);
        if (!hit || hit.closest(".react-flow__node") !== current.root || hit.closest(modal)) return;
        const nextAction = actionAt(hit), next = surfaceAt(hit, current.root);
        if (next && next.dataset.hmbWheelKey === current.key && next.tagName === current.surface.tagName && next.className === current.surface.className
            && nextAction?.tagName === action.tagName && actionKey(nextAction) === identity
            && shotAt(nextAction) === shot) activate(current.root, next);
      }, 0);
    };
    const escape = event => { if (event.key === "Escape") clear(); };
    const wheel = event => {
      const target = event.target, root = target?.closest?.(".react-flow__node");
      if (!nodes.has(root) || event.defaultPrevented || target.closest(modal)) return;
      if (selected && !selected.root.contains(selected.surface) && !restoreViewport()) clear();
      if (selected && selected.key !== selected.surface.dataset.hmbWheelKey) clear();
      if (!event.ctrlKey && !event.metaKey && selected?.root === root && selected.surface.contains(target)) {
        const surface = selected.surface;
        if (surfaceAt(target, root) === surface && syncOutline()) {
          // Keep native scrolling and widget handlers (virtual lists and
          // horizontal card strips) on the original, trusted event.
          if (!root.classList.contains("nowheel")) root.classList.add("nowheel");
          return;
        }
      }
      // Stock parameters can stop wheel at React's capture phase, before
      // the widget sees it. Deliver one event at the same pointer position
      // to the native canvas handler, above those parameter-specific guards.
      event.preventDefault();
      event.stopPropagation();
      const canvasLayer = root.closest(".react-flow__nodes") || root.parentElement;
      canvasLayer.dispatchEvent(new win.WheelEvent("wheel", event));
    };
    doc.addEventListener("pointerdown", select, true);
    doc.addEventListener("click", afterClick, true);
    doc.addEventListener("keydown", escape, true);
    doc.addEventListener("wheel", wheel, {capture: true, passive: false});
    router = {acquire(root) {
      nodes.set(root, (nodes.get(root) || 0) + 1);
      return () => {
        const count = nodes.get(root) - 1;
        if (count) nodes.set(root, count);
        else {
          nodes.delete(root);
          if (selected?.root === root) clear();
        }
        if (nodes.size) return;
        doc.removeEventListener("pointerdown", select, true);
        doc.removeEventListener("click", afterClick, true);
        doc.removeEventListener("keydown", escape, true);
        doc.removeEventListener("wheel", wheel, true);
        outlineStyle.remove();
        delete doc[key];
      };
    }};
    doc[key] = router;
  }
  return router.acquire(node);
}

function hmbNativeStockSafetyContract(container, props, mount) {
  const previous = container?.__hmbNativeStockSafety;
  const lease = previous?.active ? previous.lease : hmbAcquireNativeStockSafety(container);
  // The stock WidgetLoader adds nowheel to the entire widget host. Leave
  // wheel ownership to each HMB widget's concrete scroll surfaces instead.
  const canvasHost = container?.matches?.(".widget-container") && container.closest?.(".react-flow__node") ? container : null;
  const restoreWheelClass = previous?.active ? previous.restoreWheelClass : canvasHost?.classList.contains("nowheel");
  let handle;
  try { handle = mount(container, props); }
  catch (error) { if (!previous?.active) lease?.cleanup(); throw error; }
  lease?.refresh();
  if (!lease) return handle;
  const allowCanvasWheel = () => {
    if (canvasHost?.classList.contains("nowheel")) canvasHost.classList.remove("nowheel");
  };
  allowCanvasWheel();
  if (previous?.active && previous.handle === handle) return previous.proxy;
  if (previous) previous.active = false;
  const releaseWheel = previous?.releaseWheel || hmbAcquireCanvasWheel(container);
  const state = { active: true, lease, handle, restoreWheelClass, releaseWheel, proxy: null };
  state.proxy = {
    update(next) {
      if (!state.active) return;
      handle?.update?.(next);
      allowCanvasWheel();
      lease.refresh();
    },
    cleanup() {
      if (!state.active) return;
      state.active = false;
      try { if (typeof handle === "function") handle(); else handle?.cleanup?.(); }
      finally {
        releaseWheel?.();
        lease.cleanup();
        if (container.__hmbNativeStockSafety === state) {
          if (restoreWheelClass) canvasHost?.classList.add("nowheel");
          delete container.__hmbNativeStockSafety;
        }
      }
    },
  };
  container.__hmbNativeStockSafety = state;
  return state.proxy;
}
// HMB_NATIVE_STOCK_SAFETY_V1_END
export default function HMBSoundLibraryWidget(container,props={}) {
 return hmbNativeStockSafetyContract(container,props,hmbSoundNativeContract);
}

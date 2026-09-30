// ============================================================
// Permis de travail de chantier — Danone — Application admin
// ============================================================

// ---------- Listes de risques (identiques au permis papier IND-ING-RAQ-001) ----------
const LISTE_A = [
 "Espace clos (permis préalable)","Cadenassage","Travail en hauteur","Périmètre de sécurité",
 "Travaux au toit en périphéries","Chariot-nacelle-transpalette","Outillage et matériel",
 "Électricité et Arc électrique","Équipement de protection individuelle","Ouverture des plafonds (tuiles)",
 "Soudeuse : inspection annuelle + mise à la terre flottante","Obstruction sortie d'urgence",
 "Ouverture pouvant causer une chute"];
const LISTE_B = [
 "Visionnement vidéo SST/BPM","Formation manuel SST/BPM","Tenir les lieux propres et ordonnés",
 "Sortie d'urgence","Douche oculaire","Secouriste et trousse de premiers soins",
 "Premiers soins — Incident-accidents — Bris matériel","Mesures d'urgences (NH3 / alarme incendie)",
 "Manipulation charge (22,5 kg)","Ligne de tir","Pousser versus tirer charge","Rotation de corps",
 "Étirement excessif","Produits chimiques","SafeStart États mentaux"];
const LISTE_C = [
 "Protection des équipements et matières premières","Installation abri temporaire, matériel en bon état",
 "Analyse de risque perçage/meulage/découpe générant particules","Aucune réception/incorporation de ferments (salle ferments + MIF)",
 "Ventilation adéquate","Aucune pesée/incorporation de poudre pendant travaux",
 "Inspection visuelle après travaux en zone doseuse","Rinçage tuyauterie après coupure réseau"];
const LISTE_HAUTEUR = [
 "Analyse de risque de la tâche en hauteur complétée","Hauteur de travail > 3 m (chute)",
 "Garde-corps conformes en place","Plan de sauvetage en hauteur établi",
 "Harnais antichute inspecté et porté","Cordon/absorbeur d'énergie conforme",
 "Points d'ancrage certifiés (>22 kN)","Ligne de vie installée et vérifiée",
 "Échafaudage monté/inspecté par personne qualifiée (carte verte)","Nacelle/plateforme élévatrice inspectée",
 "Échelle sécurisée et attachée (angle 4:1)","Zone au sol délimitée (chute d'objets)",
 "Outils attachés / anti-chute d'objets","Conditions météo vérifiées (vent, glace)",
 "Travailleur formé et apte au travail en hauteur"];
const LISTE_BONBONNE = [
 "Bonbonne arrimée/sécurisée avec système de retenue approuvé (jamais tenue à la main)",
 "Robinet fermé et capuchon de protection en place pendant le levage",
 "Bonbonne transportée et entreposée à la verticale (jamais couchée)",
 "Système de levage certifié pour bonbonnes (jamais d'élingue autour du corps de la bonbonne)",
 "Distance de sécurité maintenue entre la bonbonne et le travailleur pendant le levage",
 "Inspection visuelle avant le levage (fuites, corrosion, date d'épreuve valide)",
 "Bonbonnes oxygène et gaz combustible séparées ou cloisonnées dans la nacelle",
 "Boyaux et raccords vérifiés (pas de fuite, clapets anti-retour en place)",
 "Extincteur à proximité immédiate du poste de travail en hauteur",
 "Bonbonne redescendue et sécurisée au sol dès la fin du travail (jamais laissée en hauteur)"];
const LISTE_TOIT = [
 "Analyse de risque de la tâche au toit complétée","Résistance du toit vérifiée (charge/structure)",
 "Repérage des matériaux fragiles (lucarnes, puits de lumière, tuiles)","Périmètre / rives protégés (garde-corps ou ligne d'avertissement)",
 "Accès au toit sécurisé (échelle/trappe conforme)","Harnais antichute inspecté et porté",
 "Points d'ancrage certifiés au toit","Zone au sol délimitée (chute d'objets)",
 "Outils attachés (anti-chute d'objets)","Conditions météo vérifiées (vent, pluie, glace)",
 "Surveillant/vigie désigné","Travailleur formé et apte au travail au toit"];
const LISTE_HOT = [
 "Pompe à incendie en service, mode automatique","Robinets de réglage gicleurs ouverts",
 "Extincteurs utilisables","Matériel de travail à chaud en bon état",
 "Périmètre de sécurité 35 pi (10m)","Éliminer liquides/poussière/résidus combustibles",
 "Arrêter systèmes de ventilation et manutention","Enlever/protéger matières combustibles",
 "Contrôler volume de gaz ou vapeur inflammables","Surveillance incendie continue pendant travail",
 "Surveillance incendie continue 60 min après travail"];

function buildChecks(containerId, liste, prefix){
  const c = document.getElementById(containerId);
  c.innerHTML = liste.map((t,i)=>`
    <label class="chk">
      <input type="checkbox" value="${i+1}. ${t}" data-grp="${prefix}">
      <span><b>${i+1}.</b> ${t}</span>
    </label>`).join('');
}
buildChecks('risquesA', LISTE_A, 'A');
buildChecks('risquesB', LISTE_B, 'B');
buildChecks('risquesC', LISTE_C, 'C');
buildChecks('risquesHauteur', LISTE_HAUTEUR, 'HAUTEUR');
buildChecks('risquesBonbonne', LISTE_BONBONNE, 'BONBONNE');
buildChecks('risquesToit', LISTE_TOIT, 'TOIT');
buildChecks('risquesHot', LISTE_HOT, 'HOT');

function getChecks(grp){ return [...document.querySelectorAll(`input[data-grp="${grp}"]:checked`)].map(c=>c.value); }
function setChecks(grp, values){
  values = values || [];
  document.querySelectorAll(`input[data-grp="${grp}"]`).forEach(c=>{ c.checked = values.includes(c.value); });
}
function esc(s){ return (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
// Une signature n'est affichée que si c'est bien une image PNG en data-URL.
function safeSig(src){ return (typeof src==='string' && src.startsWith('data:image/png;base64,')) ? src : ''; }
function val(id){ const e=document.getElementById(id); return e ? (e.value||'').trim() : ''; }

let tt;
function toast(msg, err){
  const t=document.getElementById('toast'); t.textContent=msg;
  t.style.background = err? 'var(--rouge)':'var(--vert)';
  t.classList.add('show'); clearTimeout(tt);
  tt=setTimeout(()=>t.classList.remove('show'),2800);
}

async function api(path, opts={}){
  const res = await fetch(path, { credentials:'include', headers:{'Content-Type':'application/json'}, ...opts });
  if(res.status === 401){ showLogin(); throw new Error('Non authentifié'); }
  if(!res.ok){
    let detail = 'Erreur';
    try{ detail = (await res.json()).detail || detail; }catch(e){}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type')||'';
  return ct.includes('application/json') ? res.json() : res.text();
}

// ---------- Authentification ----------
let currentUser = null;

function showLogin(){
  document.getElementById('appScreen').style.display='none';
  document.getElementById('loginScreen').style.display='flex';
}
function showApp(){
  document.getElementById('loginScreen').style.display='none';
  document.getElementById('appScreen').style.display='block';
}

async function tryLogin(){
  const username = val('loginUser'), password = document.getElementById('loginPass').value;
  const err = document.getElementById('loginError');
  err.classList.remove('show');
  try{
    const data = await api('/api/auth/login', {method:'POST', body: JSON.stringify({username, password})});
    currentUser = data;
    afterLogin();
  }catch(e){
    err.textContent = e.message || 'Nom d\'utilisateur ou mot de passe incorrect.';
    err.classList.add('show');
  }
}

async function logout(){
  clearInterval(notifPollTimer);
  await api('/api/auth/logout', {method:'POST'}).catch(()=>{});
  currentUser = null;
  location.reload();
}

function afterLogin(){
  showApp();
  document.getElementById('userNameDisplay').textContent = currentUser.full_name;
  document.getElementById('userAvatar').textContent = currentUser.full_name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  const roleLabel = {admin:'Admin', donneur:"Donneur d'ordre"}[currentUser.role] || currentUser.role;
  document.getElementById('userRoleDisplay').textContent = roleLabel;
  document.getElementById('nav-users').classList.toggle('hidden', currentUser.role !== 'admin');
  document.getElementById('nav-mesPermis').classList.toggle('hidden', currentUser.role !== 'donneur');
  loadSectorsIntoSelects();
  loadDonneursDatalist();
  resetForm();
  show(currentUser.role === 'donneur' ? 'mesPermis' : 'registre');
  loadNotifications();
  clearInterval(notifPollTimer);
  notifPollTimer = setInterval(loadNotifications, 25000);
}

async function checkSession(){
  try{
    const data = await api('/api/auth/me');
    if(data.authenticated){ currentUser = data; afterLogin(); }
    else showLogin();
  }catch(e){ showLogin(); }
}

// ---------- Navigation ----------
let lastListView = 'registre';
function show(v){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('active'));
  document.getElementById('view-'+v).classList.add('active');
  document.querySelectorAll('#mainNav button').forEach(b=>b.classList.remove('active'));
  const navBtn = document.getElementById('nav-'+v);
  if(navBtn) navBtn.classList.add('active');
  if(v==='registre' || v==='mesPermis') lastListView = v;
  if(v==='registre'){ loadRegistre(1); }
  if(v==='mesPermis'){ loadMesPermis(1); }
  if(v==='audit'){ loadAuditSectorSelects(); loadAudits(); }
  if(v==='secteurs'){ loadSecteurs(); }
  if(v==='users'){ loadUsers(); }
}
function backToList(){ show(lastListView); }

// ---------- Sections conditionnelles ----------
function syncToggleState(name){
  const checkbox = document.getElementById('f_'+name+'_work');
  document.getElementById(name+'Section').classList.toggle('hidden', !checkbox.checked);
  const stateEl = checkbox.closest('.hot-toggle').querySelector('.state');
  if(stateEl) stateEl.textContent = checkbox.checked ? 'Requis' : 'Non requis';
}
function toggleSection(name){ syncToggleState(name); }

// ---------- Sections numérotées repliables + statut "Renseigné" ----------
function toggleSectionCollapse(id){
  const sec = document.querySelector(`.section[data-sec-id="${id}"]`);
  if(sec) sec.classList.toggle('is-collapsed');
}
const SECTION_STATUS_RULES = {
  donneur: () => (val('f_donneur') && val('f_entreprise') && val('f_executant')) ? 'done' : 'todo',
  description: () => (val('f_description') && val('f_lieux')) ? 'done' : 'todo',
  hauteur: () => {
    if(!document.getElementById('f_height_work').checked) return 'off';
    return (val('f_height_sauvetage') && val('f_height_vigie')) ? 'done' : 'todo';
  },
  toit: () => {
    if(!document.getElementById('f_roof_work').checked) return 'off';
    return val('f_roof_vigie') ? 'done' : 'todo';
  },
  chaud: () => {
    if(!document.getElementById('f_hot_work').checked) return 'off';
    return val('f_hot_surv') ? 'done' : 'todo';
  },
  statut: () => 'done',
};
const SECTION_STATUS_LABELS = { done: '✓ Renseigné', todo: 'À compléter', off: 'Non requis' };
function updateSectionStatuses(){
  Object.keys(SECTION_STATUS_RULES).forEach(id=>{
    const el = document.getElementById('secstat-'+id);
    if(!el) return;
    const state = SECTION_STATUS_RULES[id]();
    el.textContent = SECTION_STATUS_LABELS[state];
    el.className = 'sec-status sec-status--' + state;
  });
}

// ---------- Compteurs de sélection sur les listes de vérification ----------
const RISK_COUNT_GROUPS = [
  ['risquesA','countA'], ['risquesB','countB'], ['risquesC','countC'],
  ['risquesHauteur','countHauteur'], ['risquesBonbonne','countBonbonne'],
  ['risquesToit','countToit'], ['risquesHot','countHot'],
];
function refreshRiskCounts(){
  RISK_COUNT_GROUPS.forEach(([containerId, badgeId])=>{
    const c = document.getElementById(containerId);
    const b = document.getElementById(badgeId);
    if(!c || !b) return;
    const total = c.querySelectorAll('input[type=checkbox]').length;
    const checked = c.querySelectorAll('input[type=checkbox]:checked').length;
    b.textContent = checked + '/' + total;
  });
}
document.getElementById('view-form').addEventListener('change', e=>{
  if(e.target.matches('input[type=checkbox]')) refreshRiskCounts();
  updateSectionStatuses();
});
document.getElementById('view-form').addEventListener('input', updateSectionStatuses);

// ---------- Secteurs (registre uniquement — le formulaire n'assigne plus de secteur) ----------
async function loadSectorsIntoSelects(){
  const sectors = await api('/api/sectors').catch(()=>[]);
  const filterSel = document.getElementById('filterSector');
  filterSel.innerHTML = '<option value="">Tous les secteurs</option>' +
    sectors.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
}

// ---------- Formulaire : création / édition ----------
let currentEditId = null;

function resetForm(){
  currentEditId = null;
  document.getElementById('formTitle').textContent = 'PERMIS DE TRAVAIL DE CHANTIER';
  document.getElementById('numPermisDisplay').textContent = '…';
  loadNextPermitNum();
  document.getElementById('saveBtn').textContent = '💾 Enregistrer';
  document.getElementById('printBtn').classList.add('hidden');
  document.querySelectorAll('#view-form input, #view-form textarea, #view-form select').forEach(e=>{
    if(e.type==='checkbox') e.checked=false; else e.value='';
  });
  document.getElementById('f_statut').value = 'Actif';
  ['height','bonbonne','roof','hot'].forEach(syncToggleState);
  refreshRiskCounts();
  updateSectionStatuses();
  document.getElementById('receptionSignatureBlock').style.display = 'none';
}

async function loadNextPermitNum(){
  try{
    const { num } = await api('/api/permits/next-num');
    // Le numéro définitif est assigné à l'enregistrement — si l'utilisateur a
    // entre-temps ouvert un permis existant à modifier, on n'écrase pas son numéro.
    if(!currentEditId) document.getElementById('numPermisDisplay').textContent = num;
  }catch(e){ /* garde le placeholder si l'appel échoue */ }
}

function collectFormData(){
  return {
    donneur: val('f_donneur'), donneur_tel: val('f_donneur_tel'),
    entreprise: val('f_entreprise'), executant: val('f_executant'), executant_tel: val('f_executant_tel'),
    description: val('f_description'), lieux: val('f_lieux'), zone: val('f_zone'),
    date_debut: val('f_date_debut'), date_fin: val('f_date_fin'),
    risques_a: getChecks('A'), risques_b: getChecks('B'), risques_c: getChecks('C'),
    zone_conforme: val('f_zone_conforme'), zone_comm: val('f_zone_comm'),
    height_work: document.getElementById('f_height_work').checked,
    risques_hauteur: getChecks('HAUTEUR'), height_acces: val('f_height_acces'),
    height_m: val('f_height_m'), height_sauvetage: val('f_height_sauvetage'), height_vigie: val('f_height_vigie'),
    bonbonne_work: document.getElementById('f_bonbonne_work').checked,
    risques_bonbonne: getChecks('BONBONNE'), bonbonne_type: val('f_bonbonne_type'),
    bonbonne_nombre: val('f_bonbonne_nombre'), bonbonne_levage: val('f_bonbonne_levage'),
    roof_work: document.getElementById('f_roof_work').checked,
    risques_toit: getChecks('TOIT'), roof_type: val('f_roof_type'),
    roof_resistance: val('f_roof_resistance'), roof_perimetre: val('f_roof_perimetre'), roof_vigie: val('f_roof_vigie'),
    hot_work: document.getElementById('f_hot_work').checked,
    risques_hot: getChecks('HOT'), hot_nature: val('f_hot_nature'),
    hot_debut: val('f_hot_debut'), hot_fin: val('f_hot_fin'),
    hot_surv: val('f_hot_surv'), hot_ext: val('f_hot_ext'),
    statut: val('f_statut'),
  };
}

function clientValidate(data){
  const missing = [];
  if(!data.donneur) missing.push("donneur d'ordre");
  if(!data.executant) missing.push('exécutant');
  if(!data.entreprise) missing.push('entreprise');
  if(!data.description) missing.push('description');
  if(!data.lieux) missing.push('lieux');
  if(data.height_work || data.roof_work){
    if(!data.height_vigie && !data.roof_vigie) missing.push('vigie (obligatoire — hauteur ou toit)');
    if(data.height_work && !data.height_sauvetage) missing.push('plan de sauvetage (obligatoire — hauteur)');
  }
  if(data.hot_work && !data.hot_surv) missing.push('surveillance incendie (obligatoire — travail à chaud)');
  return missing;
}

async function savePermit(){
  const data = collectFormData();
  const missing = clientValidate(data);
  if(missing.length){
    toast('⚠️ Champs obligatoires manquants : ' + missing.join(', '), true);
    return;
  }
  try{
    let saved;
    if(currentEditId){
      saved = await api(`/api/permits/${currentEditId}`, {method:'PUT', body: JSON.stringify(data)});
      toast('✅ Permis ' + saved.num + ' mis à jour');
    }else{
      saved = await api('/api/permits', {method:'POST', body: JSON.stringify(data)});
      toast('✅ Permis ' + saved.num + ' créé');
    }
    resetForm();
    show('registre');
  }catch(e){
    toast('⚠️ ' + e.message, true);
  }
}

function populateFormFromPermit(p){
  currentEditId = p.id;
  document.getElementById('formTitle').textContent = 'MODIFIER LE PERMIS';
  document.getElementById('numPermisDisplay').textContent = p.num;
  document.getElementById('saveBtn').textContent = '💾 Enregistrer les modifications';
  document.getElementById('f_donneur').value = p.donneur || '';
  document.getElementById('f_donneur_tel').value = p.donneur_tel || '';
  document.getElementById('f_entreprise').value = p.entreprise || '';
  document.getElementById('f_executant').value = p.executant || '';
  document.getElementById('f_executant_tel').value = p.executant_tel || '';
  document.getElementById('f_description').value = p.description || '';
  document.getElementById('f_lieux').value = p.lieux || '';
  document.getElementById('f_zone').value = p.zone || '';
  document.getElementById('f_date_debut').value = p.date_debut || '';
  document.getElementById('f_date_fin').value = p.date_fin || '';
  setChecks('A', p.risques_a); setChecks('B', p.risques_b); setChecks('C', p.risques_c);
  document.getElementById('f_zone_conforme').value = p.zone_conforme || '';
  document.getElementById('f_zone_comm').value = p.zone_comm || '';

  document.getElementById('f_height_work').checked = !!p.height_work;
  setChecks('HAUTEUR', p.risques_hauteur);
  document.getElementById('f_height_acces').value = p.height_acces || '';
  document.getElementById('f_height_m').value = p.height_m || '';
  document.getElementById('f_height_sauvetage').value = p.height_sauvetage || '';
  document.getElementById('f_height_vigie').value = p.height_vigie || '';
  syncToggleState('height');

  document.getElementById('f_bonbonne_work').checked = !!p.bonbonne_work;
  setChecks('BONBONNE', p.risques_bonbonne);
  document.getElementById('f_bonbonne_type').value = p.bonbonne_type || '';
  document.getElementById('f_bonbonne_nombre').value = p.bonbonne_nombre || '';
  document.getElementById('f_bonbonne_levage').value = p.bonbonne_levage || '';
  syncToggleState('bonbonne');

  document.getElementById('f_roof_work').checked = !!p.roof_work;
  setChecks('TOIT', p.risques_toit);
  document.getElementById('f_roof_type').value = p.roof_type || '';
  document.getElementById('f_roof_resistance').value = p.roof_resistance || '';
  document.getElementById('f_roof_perimetre').value = p.roof_perimetre || '';
  document.getElementById('f_roof_vigie').value = p.roof_vigie || '';
  syncToggleState('roof');

  document.getElementById('f_hot_work').checked = !!p.hot_work;
  setChecks('HOT', p.risques_hot);
  document.getElementById('f_hot_nature').value = p.hot_nature || '';
  document.getElementById('f_hot_debut').value = p.hot_debut || '';
  document.getElementById('f_hot_fin').value = p.hot_fin || '';
  document.getElementById('f_hot_surv').value = p.hot_surv || '';
  document.getElementById('f_hot_ext').value = p.hot_ext || '';
  syncToggleState('hot');

  document.getElementById('f_statut').value = p.statut || 'Actif';
  refreshRiskCounts();
  updateSectionStatuses();

  const receptionBlock = document.getElementById('receptionSignatureBlock');
  if(p.reception_nom){
    document.getElementById('receptionSignatureInfo').textContent =
      `${p.reception_nom} — ${(p.reception_le||'').replace('T',' ').slice(0,16)}`;
    document.getElementById('receptionSignatureImg').src = safeSig(p.signature_reception);
    receptionBlock.style.display = 'block';
  } else {
    receptionBlock.style.display = 'none';
  }
}

// ---------- Registre ----------
let registreState = { page:1, search:'', statut:'', sector_id:'' };
let searchDebounce;
function debounceSearch(){
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(()=>loadRegistre(1), 350);
}

async function loadRegistre(page){
  registreState.page = page || registreState.page;
  registreState.search = val('search');
  registreState.statut = val('filterStatut');
  registreState.sector_id = val('filterSector');

  const params = new URLSearchParams({
    page: registreState.page, page_size: 25,
    search: registreState.search, statut: registreState.statut,
  });
  if(registreState.sector_id) params.set('sector_id', registreState.sector_id);

  const data = await api('/api/permits?' + params.toString());
  renderStats(data.stats);
  renderRegistreTable(data.permits);
  renderPagination(data.page, data.pages, data.total);
}

function renderStats(stats){
  const countBadge = document.getElementById('registreCount');
  if(countBadge) countBadge.textContent = stats.total||0;
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="n">${stats.total||0}</div><div class="l">Total permis</div></div>
    <div class="stat"><div class="n" style="color:var(--vert)">${stats.actifs||0}</div><div class="l">Actifs</div></div>
    <div class="stat"><div class="n" style="color:var(--bleu)">${stats.hauteur||0}</div><div class="l">Travail en hauteur</div></div>
    <div class="stat"><div class="n" style="color:var(--violet)">${stats.toit||0}</div><div class="l">Travail au toit</div></div>
    <div class="stat"><div class="n" style="color:var(--rouge)">${stats.chaud||0}</div><div class="l">Travail à chaud</div></div>`;
}

let sectorNamesCache = {};
async function refreshSectorNamesCache(){
  const sectors = await api('/api/sectors').catch(()=>[]);
  sectorNamesCache = {};
  sectors.forEach(s=>sectorNamesCache[s.id]=s.name);
}

function renderRegistreTable(permits){
  const body = document.getElementById('registreBody');
  if(!permits.length){
    body.innerHTML = `<tr><td colspan="11"><div class="empty">Aucun permis trouvé.</div></td></tr>`;
    return;
  }
  body.innerHTML = permits.map(p=>{
    const sb = {'Actif':'b-actif','Fermé':'b-ferme'}[p.statut]||'b-ferme';
    const sectorName = sectorNamesCache[p.sector_id] || '—';
    return `<tr style="cursor:pointer" onclick="openDetail(${p.id})">
      <td><b>${esc(p.num)}</b></td><td>${esc((p.created_at||'').slice(0,10))}</td>
      <td>${esc(p.entreprise)||'—'}</td><td>${esc(p.donneur)||'—'}</td><td>${esc(p.executant)}</td><td>${esc(sectorName)}</td>
      <td>${p.height_work?'<span class="badge b-hauteur">🏗️ Oui</span>':'—'}</td>
      <td>${p.roof_work?'<span class="badge b-toit">🏠 Oui</span>':'—'}</td>
      <td>${p.hot_work?'<span class="badge b-hot">🔥 Oui</span>':'—'}</td>
      <td><span class="badge ${sb}">${esc(p.statut)}</span></td>
      <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();openDetail(${p.id})">👁️</button></td>
    </tr>`;
  }).join('');
}

function renderPagination(page, pages, total){
  document.getElementById('pagination').innerHTML = `
    <button ${page<=1?'disabled':''} onclick="loadRegistre(${page-1})">← Précédent</button>
    <span>Page ${page} / ${pages} (${total} permis)</span>
    <button ${page>=pages?'disabled':''} onclick="loadRegistre(${page+1})">Suivant →</button>`;
}

// ---------- Mes permis (tableau de bord personnel — donneur d'ordre) ----------
let mineState = { page: 1, period: '' };

async function loadDonneursDatalist(){
  const names = await api('/api/donneurs').catch(()=>[]);
  document.getElementById('donneurList').innerHTML = names.map(n=>`<option value="${esc(n)}">`).join('');
}

function setMinePeriod(period){
  mineState.period = period;
  document.getElementById('chipMineAll').classList.toggle('chip-active', period==='');
  document.getElementById('chipMineWeek').classList.toggle('chip-active', period==='week');
  loadMesPermis(1);
}

async function loadMesPermis(page){
  mineState.page = page || mineState.page;
  await refreshSectorNamesCache();
  const params = new URLSearchParams({
    page: mineState.page, page_size: 25, mine: 'true', statut: 'Actif',
  });
  if(mineState.period) params.set('period', mineState.period);
  const data = await api('/api/permits?' + params.toString());
  document.getElementById('mesPermisCount').textContent = data.total || 0;
  document.getElementById('chipMineAll').classList.toggle('chip-active', mineState.period==='');
  document.getElementById('chipMineWeek').classList.toggle('chip-active', mineState.period==='week');
  renderMinePermisTable(data.permits);
  renderMinePagination(data.page, data.pages, data.total);
}

function renderMinePermisTable(permits){
  const body = document.getElementById('minePermisBody');
  if(!permits.length){
    body.innerHTML = `<tr><td colspan="7"><div class="empty">Aucun permis ouvert pour le moment.</div></td></tr>`;
    return;
  }
  body.innerHTML = permits.map(p=>{
    const sb = {'Actif':'b-actif','Fermé':'b-ferme'}[p.statut]||'b-ferme';
    const sectorName = sectorNamesCache[p.sector_id] || '—';
    return `<tr style="cursor:pointer" onclick="openDetail(${p.id})">
      <td><b>${esc(p.num)}</b></td><td>${esc((p.created_at||'').slice(0,10))}</td>
      <td>${esc(p.entreprise)||'—'}</td><td>${esc(p.executant)}</td><td>${esc(sectorName)}</td>
      <td><span class="badge ${sb}">${esc(p.statut)}</span></td>
      <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();openDetail(${p.id})">👁️</button></td>
    </tr>`;
  }).join('');
}

function renderMinePagination(page, pages, total){
  document.getElementById('minePagination').innerHTML = `
    <button ${page<=1?'disabled':''} onclick="loadMesPermis(${page-1})">← Précédent</button>
    <span>Page ${page} / ${pages} (${total} permis)</span>
    <button ${page>=pages?'disabled':''} onclick="loadMesPermis(${page+1})">Suivant →</button>`;
}

// ---------- Détail / modification / fermeture / photos / historique ----------
let currentPermit = null;

async function openDetail(id){
  await refreshSectorNamesCache();
  currentPermit = await api(`/api/permits/${id}`);
  renderDetail(currentPermit);
  show('detail');
}

function riskListHtml(title, items){
  if(!items || !items.length) return '';
  return `<p style="margin-top:10px"><b>${esc(title)} :</b></p><ul style="margin:4px 0 0 18px">${items.map(i=>`<li>${esc(i)}</li>`).join('')}</ul>`;
}

function renderDetail(p){
  document.getElementById('detailNum').textContent = 'Permis ' + p.num;
  const sb = {'Actif':'b-actif','Fermé':'b-ferme','Brouillon':'b-brouillon'}[p.statut]||'b-ferme';
  const sectorName = sectorNamesCache[p.sector_id] || '—';

  let html = `
    <span class="badge ${sb}">${esc(p.statut)}</span>
    <p style="margin-top:10px"><b>Secteur :</b> ${esc(sectorName)}</p>
    <p><b>Donneur d'ordre :</b> ${esc(p.donneur)} (${esc(p.donneur_tel)||'—'})</p>
    <p><b>Entreprise :</b> ${esc(p.entreprise)} &nbsp; <b>Exécutant :</b> ${esc(p.executant)} (${esc(p.executant_tel)||'—'})</p>
    <p style="margin-top:8px"><b>Description :</b> ${esc(p.description)}</p>
    <p><b>Lieux :</b> ${esc(p.lieux)}</p>
    ${p.zone ? `<p><b>Secteur (zone du site) :</b> ${esc(p.zone)}</p>` : ''}
    <p><b>Période :</b> ${esc(p.date_debut)||'—'} au ${esc(p.date_fin)||'—'}</p>
    <p><b>Créé par :</b> ${esc(p.cree_par)||'—'}</p>
    ${riskListHtml('A · Procédures', p.risques_a)}
    ${riskListHtml('B · Comportements', p.risques_b)}
    ${riskListHtml('C · Zone critique', p.risques_c)}`;

  if(p.height_work){
    html += `<div style="margin-top:14px;padding:10px;background:#e8f2fc;border-radius:8px">
      <b>🏗️ Travail en hauteur</b> — Accès : ${esc(p.height_acces)||'—'}, Hauteur : ${esc(p.height_m)||'—'} m,
      Sauvetage : ${esc(p.height_sauvetage)||'—'}, Vigie : ${esc(p.height_vigie)||'—'}
      ${riskListHtml('Vérifications', p.risques_hauteur)}</div>`;
  }
  if(p.bonbonne_work){
    html += `<div style="margin-top:10px;padding:10px;background:#fff8ea;border-radius:8px">
      <b>🛢️ Bonbonnes de gaz</b> — Type : ${esc(p.bonbonne_type)||'—'}
      ${riskListHtml('Vérifications', p.risques_bonbonne)}</div>`;
  }
  if(p.roof_work){
    html += `<div style="margin-top:10px;padding:10px;background:#f1edfa;border-radius:8px">
      <b>🏠 Travail au toit</b> — Type : ${esc(p.roof_type)||'—'}, Résistance : ${esc(p.roof_resistance)||'—'}, Vigie : ${esc(p.roof_vigie)||'—'}
      ${riskListHtml('Vérifications', p.risques_toit)}</div>`;
  }
  if(p.hot_work){
    html += `<div style="margin-top:10px;padding:10px;background:#ffebee;border-radius:8px">
      <b>🔥 Travail à chaud</b> — Nature : ${esc(p.hot_nature)||'—'}, Surveillance : ${esc(p.hot_surv)||'—'}, Extincteur # : ${esc(p.hot_ext)||'—'}
      ${riskListHtml('Précautions', p.risques_hot)}</div>`;
  }

  if(p.statut === 'Fermé'){
    html += `<div style="margin-top:14px;padding:12px;background:#f5f5f5;border-radius:8px">
      <b>Fermé le :</b> ${esc((p.ferme_le||'').replace('T',' ').slice(0,16))}<br>`;
    if(p.signature_donneur){
      html += `<div style="display:flex;gap:20px;margin-top:8px;flex-wrap:wrap">
        <div><div style="font-size:11px;color:var(--gris)">Signature donneur d'ordre</div><img src="${esc(safeSig(p.signature_donneur))}" style="max-width:200px;border:1px solid #ddd;border-radius:4px"></div>
        <div><div style="font-size:11px;color:var(--gris)">Signature exécutant</div><img src="${esc(safeSig(p.signature_executant))}" style="max-width:200px;border:1px solid #ddd;border-radius:4px"></div>
      </div>`;
    }
    html += `</div>`;
  }

  document.getElementById('detailContent').innerHTML = html;
  document.getElementById('closeBtn').style.display = p.statut === 'Fermé' ? 'none' : 'inline-block';
  // Un permis fermé est verrouillé : la révision n'est plus proposée.
  document.getElementById('editBtn').style.display = p.statut === 'Fermé' ? 'none' : 'inline-block';

  const photoGrid = document.getElementById('photoGrid');
  photoGrid.innerHTML = (p.photos||[]).map(ph=>`
    <div class="photo-thumb">
      <img src="/uploads/${encodeURIComponent(ph.filename)}">
      <button onclick="deletePhoto(${ph.id})" title="Supprimer">✕</button>
    </div>`).join('') || '<p class="note">Aucune photo pour ce permis.</p>';

  const historyList = document.getElementById('historyList');
  historyList.innerHTML = (p.history||[]).map(h=>`
    <div class="history-item">
      <div class="dot"></div>
      <div><b>${esc(h.statut)}</b> — ${esc(h.par)||'—'} <span style="color:var(--gris)">(${esc((h.horodatage||'').replace('T',' ').slice(0,16))})</span>
      ${h.note?`<br><span style="color:var(--gris)">${esc(h.note)}</span>`:''}</div>
    </div>`).join('') || '<p class="note">Aucun historique.</p>';
}

function editCurrentPermit(){
  populateFormFromPermit(currentPermit);
  show('form');
}

async function deleteCurrentPermit(){
  if(currentUser.role !== 'admin'){ toast('⚠️ Seul un administrateur peut archiver un permis', true); return; }
  if(!confirm('Archiver ce permis ? Il disparaît du registre mais reste conservé avec son historique et ses signatures.')) return;
  await api(`/api/permits/${currentPermit.id}`, {method:'DELETE'});
  toast('Permis archivé');
  show('registre');
}

function printCurrentPermit(){ window.print(); }

// ---------- Photos ----------
async function uploadPhotos(){
  const input = document.getElementById('photoInput');
  if(!input.files.length){ toast('Choisis au moins une photo', true); return; }
  for(const file of input.files){
    const fd = new FormData();
    fd.append('file', file);
    try{
      await fetch(`/api/permits/${currentPermit.id}/photos`, {method:'POST', credentials:'include', body:fd});
    }catch(e){}
  }
  input.value = '';
  currentPermit = await api(`/api/permits/${currentPermit.id}`);
  renderDetail(currentPermit);
  toast('✅ Photo(s) ajoutée(s)');
}

// ---------- Audit : rapports importés par secteur ----------
async function loadAuditSectorSelects(){
  const sectors = await api('/api/sectors').catch(()=>[]);
  const opts = sectors.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
  const uploadSel = document.getElementById('auditSector');
  const filterSel = document.getElementById('auditFilterSector');
  if(uploadSel) uploadSel.innerHTML = opts;
  if(filterSel) filterSel.innerHTML = '<option value="">Tous les secteurs</option>' + opts;
}

async function loadAudits(){
  const sectorId = val('auditFilterSector');
  const params = sectorId ? `?sector_id=${sectorId}` : '';
  const audits = await api('/api/audits' + params).catch(()=>[]);
  renderAuditsTable(audits);
}

function renderAuditsTable(audits){
  const body = document.getElementById('auditBody');
  if(!audits.length){
    body.innerHTML = `<tr><td colspan="6"><div class="empty">Aucun rapport d'audit importé.</div></td></tr>`;
    return;
  }
  body.innerHTML = audits.map(a=>`
    <tr>
      <td>${esc(a.sector_name)}</td>
      <td>${esc(a.titre)||'—'}</td>
      <td>${esc(a.date_audit)||'—'}</td>
      <td>${esc(a.uploaded_by)||'—'}</td>
      <td>${esc((a.uploaded_at||'').slice(0,10))}</td>
      <td>
        <a class="btn btn-secondary btn-sm" href="/api/audits/${a.id}/download" target="_blank">📄 Ouvrir</a>
        <button class="btn btn-danger btn-sm" onclick="deleteAudit(${a.id})">🗑️</button>
      </td>
    </tr>`).join('');
}

async function uploadAuditReport(){
  const fileInput = document.getElementById('auditFile');
  const sectorId = val('auditSector');
  if(!sectorId){ toast('Choisis un secteur', true); return; }
  if(!fileInput.files.length){ toast('Choisis un fichier', true); return; }
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  fd.append('sector_id', sectorId);
  fd.append('titre', val('auditTitre'));
  fd.append('date_audit', val('auditDate'));
  try{
    const res = await fetch('/api/audits', {method:'POST', credentials:'include', body:fd});
    if(!res.ok){
      const err = await res.json().catch(()=>({}));
      throw new Error(err.detail || 'Erreur');
    }
    fileInput.value = '';
    document.getElementById('auditTitre').value = '';
    document.getElementById('auditDate').value = '';
    toast('✅ Rapport importé');
    loadAudits();
  }catch(e){
    toast(e.message || 'Erreur lors de l\'import', true);
  }
}

async function deleteAudit(auditId){
  if(!confirm('Supprimer ce rapport d\'audit ?')) return;
  await api(`/api/audits/${auditId}`, {method:'DELETE'});
  toast('Rapport supprimé');
  loadAudits();
}

async function deletePhoto(photoId){
  if(!confirm('Supprimer cette photo ?')) return;
  await api(`/api/photos/${photoId}`, {method:'DELETE'});
  currentPermit = await api(`/api/permits/${currentPermit.id}`);
  renderDetail(currentPermit);
}

// ---------- Fermeture avec signatures ----------
let sigCanvases = {};
function initSigPad(id){
  const canvas = document.getElementById(id);
  const ratio = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * ratio;
  canvas.height = canvas.clientHeight * ratio;
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = '#1a1a1a';
  let drawing = false, last = null;
  function pos(e){
    const rect = canvas.getBoundingClientRect();
    const p = e.touches ? e.touches[0] : e;
    return { x: p.clientX-rect.left, y: p.clientY-rect.top };
  }
  function start(e){ drawing=true; last=pos(e); e.preventDefault(); }
  function move(e){
    if(!drawing) return;
    const p = pos(e);
    ctx.beginPath(); ctx.moveTo(last.x,last.y); ctx.lineTo(p.x,p.y); ctx.stroke();
    last = p; e.preventDefault();
  }
  function end(){ drawing=false; }
  canvas.addEventListener('mousedown', start); canvas.addEventListener('mousemove', move); window.addEventListener('mouseup', end);
  canvas.addEventListener('touchstart', start); canvas.addEventListener('touchmove', move); canvas.addEventListener('touchend', end);
  sigCanvases[id] = canvas;
}
function clearSig(id){
  const canvas = sigCanvases[id];
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
}
function isCanvasBlank(canvas){
  const ctx = canvas.getContext('2d');
  const data = ctx.getImageData(0,0,canvas.width,canvas.height).data;
  return !data.some(v=>v!==0);
}

function openCloseModal(){
  document.getElementById('closeModal').classList.remove('hidden');
  setTimeout(()=>{ initSigPad('sigDonneur'); initSigPad('sigExecutant'); }, 30);
}
function closeCloseModal(){ document.getElementById('closeModal').classList.add('hidden'); }

async function confirmClose(){
  const cDon = sigCanvases['sigDonneur'], cExe = sigCanvases['sigExecutant'];
  if(isCanvasBlank(cDon) || isCanvasBlank(cExe)){
    toast('⚠️ Les deux signatures sont requises', true); return;
  }
  const signature_donneur = cDon.toDataURL('image/png');
  const signature_executant = cExe.toDataURL('image/png');
  try{
    await api(`/api/permits/${currentPermit.id}/close`, {
      method:'POST', body: JSON.stringify({signature_donneur, signature_executant})
    });
    // Relit le permis complet (photos et historique inclus) : la réponse de
    // fermeture ne contient que le permis lui-même.
    currentPermit = await api(`/api/permits/${currentPermit.id}`);
    closeCloseModal();
    renderDetail(currentPermit);
    toast('✅ Permis fermé officiellement');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

// ---------- Secteurs & QR ----------
let sectorsCache = [];
async function loadSecteurs(){
  const sectors = await api('/api/sectors');
  sectorsCache = sectors;
  const list = document.getElementById('sectorsList');
  if(!sectors.length){ list.innerHTML = '<p class="note" style="padding:14px 18px">Aucun secteur créé.</p>'; return; }
  list.innerHTML = sectors.map(s=>`
    <div class="sector-row">
      <div>
        <div class="name">${esc(s.name)}</div>
        <div class="note">/secteur/${esc(s.slug)}</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <img src="/api/sectors/${encodeURIComponent(s.slug)}/qrcode.png" style="width:70px;height:70px;border:1px solid #ddd;border-radius:6px">
        <button class="btn btn-secondary btn-sm" onclick="printSectorQR(${s.id})">🖨️ Imprimer</button>
        ${currentUser.role==='admin' ? `<button class="btn btn-danger btn-sm" onclick="deleteSector(${s.id})">🗑️</button>` : ''}
      </div>
    </div>`).join('');
}

async function addSector(){
  const name = val('newSectorName');
  if(!name){ toast('⚠️ Nom de secteur requis', true); return; }
  try{
    await api('/api/sectors', {method:'POST', body: JSON.stringify({name})});
    document.getElementById('newSectorName').value = '';
    loadSecteurs();
    loadSectorsIntoSelects();
    toast('✅ Secteur créé');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

async function deleteSector(id){
  if(!confirm('Supprimer ce secteur ? Les permis existants ne seront plus rattachés.')) return;
  await api(`/api/sectors/${id}`, {method:'DELETE'});
  loadSecteurs(); loadSectorsIntoSelects();
}

function printSectorQR(sectorId){
  const sector = sectorsCache.find(x=>x.id===sectorId);
  if(!sector) return;
  const slug = encodeURIComponent(sector.slug), name = esc(sector.name);
  const w = window.open('', '', 'width=500,height=650');
  w.document.write(`<html><head><title>QR — ${name}</title><style>
    body{font-family:Arial;text-align:center;padding:40px}
    .band{background:#e8f6fc;border:3px solid #005EB8;padding:16px;margin-bottom:20px;font-weight:800;font-size:20px;letter-spacing:1px;color:#005EB8;display:flex;align-items:center;justify-content:center;gap:12px}
    .band img{border:none;border-radius:0;padding:0;height:32px;width:auto}
    .band .star-fallback{display:none;width:32px;height:32px;border-radius:50%;background:#1a1a1a;color:#00ACED;align-items:center;justify-content:center;font-size:16px}
    img{border:3px solid #000;border-radius:10px;padding:14px}
    h2{margin-top:20px}
    p{color:#555;margin-top:10px}
  </style></head><body>
    <div class="band">
      <img src="/static/img/logo-danone-icon.png" alt=""
           onload="this.nextElementSibling.style.display='none'"
           onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex'">
      <span class="star-fallback">★</span>
      <span>DANONE — PERMIS DE TRAVAIL</span>
    </div>
    <h2>${name}</h2>
    <img src="/api/sectors/${slug}/qrcode.png" width="280" height="280">
    <p>Scannez pour consulter votre permis de travail dans ce secteur.</p>
    <script>window.onload=()=>window.print()</script>
  </body></html>`);
}

// ---------- Utilisateurs (admin) ----------
async function loadUsers(){
  const users = await api('/api/users');
  const roleLabel = {admin:'Administrateur', donneur:"Donneur d'ordre"};
  document.getElementById('usersBody').innerHTML = users.map(u=>`
    <tr>
      <td><b>${esc(u.username)}</b></td><td>${esc(u.full_name)}</td><td>${roleLabel[u.role]||u.role}</td>
      <td>${u.id !== currentUser.uid
        ? `<button class="btn btn-secondary btn-sm" title="Réinitialiser le mot de passe" onclick="openPasswordModal(${u.id})">🔑</button>
           <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id})">🗑️</button>`
        : '<span class="note">(vous)</span>'}</td>
    </tr>`).join('');
}

async function addUser(){
  const username = val('newUserName'), full_name = val('newUserFull'), password = val('newUserPass'), role = val('newUserRole');
  if(!username || !full_name || !password){ toast('⚠️ Remplis tous les champs', true); return; }
  try{
    await api('/api/users', {method:'POST', body: JSON.stringify({username, full_name, password, role})});
    document.getElementById('newUserName').value='';
    document.getElementById('newUserFull').value='';
    document.getElementById('newUserPass').value='';
    loadUsers();
    toast('✅ Utilisateur ajouté');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

async function deleteUser(id){
  if(!confirm('Supprimer cet utilisateur ?')) return;
  await api(`/api/users/${id}`, {method:'DELETE'});
  loadUsers();
}

// ---------- Changement de mot de passe ----------
let passwordTargetId = null; // null = mon propre mot de passe

function openPasswordModal(userId){
  passwordTargetId = userId || null;
  document.getElementById('pwTitle').textContent = passwordTargetId ? "Réinitialiser le mot de passe d'un utilisateur" : 'Changer mon mot de passe';
  document.getElementById('pwCurrentRow').style.display = passwordTargetId ? 'none' : 'block';
  ['pwCurrent','pwNew','pwConfirm'].forEach(id=>{ document.getElementById(id).value=''; });
  document.getElementById('pwModal').classList.remove('hidden');
}
function closePasswordModal(){ document.getElementById('pwModal').classList.add('hidden'); }

async function submitPassword(){
  const current = document.getElementById('pwCurrent').value;
  const next = document.getElementById('pwNew').value;
  const confirmation = document.getElementById('pwConfirm').value;
  if(next.length < 10){ toast('⚠️ Le mot de passe doit contenir au moins 10 caractères', true); return; }
  if(next !== confirmation){ toast('⚠️ Les deux mots de passe ne correspondent pas', true); return; }
  try{
    if(passwordTargetId){
      await api(`/api/users/${passwordTargetId}/password`, {method:'PUT', body: JSON.stringify({new_password: next})});
    }else{
      await api('/api/auth/change-password', {method:'POST', body: JSON.stringify({current_password: current, new_password: next})});
    }
    closePasswordModal();
    toast('✅ Mot de passe mis à jour');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

// ---------- Notifications (🔔 réceptions signées) ----------
let notifPollTimer = null;
let notifCache = [];

function timeAgo(iso){
  if(!iso) return '';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  const mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
  if(mins < 1) return "à l'instant";
  if(mins < 60) return `il y a ${mins} min`;
  const hrs = Math.round(mins / 60);
  if(hrs < 24) return `il y a ${hrs} h`;
  return d.toLocaleDateString('fr-CA') + ' ' + d.toLocaleTimeString('fr-CA', {hour:'2-digit', minute:'2-digit'});
}

async function loadNotifications(){
  try{
    const data = await api('/api/notifications');
    notifCache = data.notifications || [];
    const badge = document.getElementById('notifBadge');
    if(data.unread_count > 0){
      badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
      badge.classList.remove('hidden');
    }else{
      badge.classList.add('hidden');
    }
    renderNotifList();
  }catch(e){ /* pas bloquant */ }
}

function renderNotifList(){
  const list = document.getElementById('notifList');
  if(!notifCache.length){
    list.innerHTML = '<div class="empty">Aucune notification.</div>';
    return;
  }
  list.innerHTML = notifCache.map(n => `
    <div class="notif-item" onclick="openNotification(${n.permit_id})">
      ${esc(n.message)}
      <span class="notif-time">${timeAgo(n.created_at)}</span>
    </div>`).join('');
}

function openNotification(permitId){
  toggleNotifDropdown(false);
  show('registre');
  openDetail(permitId);
}

function toggleNotifDropdown(force){
  const dd = document.getElementById('notifDropdown');
  const show = force !== undefined ? force : dd.classList.contains('hidden');
  dd.classList.toggle('hidden', !show);
  if(show){
    api('/api/notifications/seen', {method:'POST'}).catch(()=>{});
    document.getElementById('notifBadge').classList.add('hidden');
  }
}

document.addEventListener('click', e=>{
  const wrap = document.querySelector('.notif-wrap');
  if(wrap && !wrap.contains(e.target)) toggleNotifDropdown(false);
});

// ---------- Démarrage ----------
document.getElementById('loginPass').addEventListener('keydown', e=>{ if(e.key==='Enter') tryLogin(); });
document.getElementById('loginUser').addEventListener('keydown', e=>{ if(e.key==='Enter') tryLogin(); });
checkSession();

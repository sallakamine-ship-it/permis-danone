// Conformité Danone 12 Basics — 12.01 (permis global) / 12.02 (inspection quotidienne)
const PTA_SIGN_LABELS = {
  approbation: 'Approbation — personne compétente désignée',
  entrepreneur: "Représentant de l'entrepreneur",
  hote: 'Hôte / contact Danone',
  sst: 'Représentant SST (ou délégué)',
  qualite: 'Représentant Qualité (ou délégué)',
};

function complianceBadges(p){
  const c = p.compliance; if(!c || p.statut==='Brouillon') return '';
  let h = '';
  if(!c.c1201.ok) h += ` <span class="badge b-hot" title="${esc(c.c1201.issues.join(' • '))}">12.01 ⚠</span>`;
  if(!c.c1202.ok) h += ` <span class="badge b-hot" title="${esc(c.c1202.issues.join(' • '))}">12.02 ⚠</span>`;
  if(c.renewal_due) h += ` <span class="badge b-toit" title="Expire dans ${c.expires_in_days} j">⏳ Renouveler</span>`;
  return h;
}

function conformiteDetailHtml(p){
  const c = p.compliance; if(!c) return '';
  const line = (label, o) => `<div style="margin:4px 0">${o.ok ? '✅' : '⚠️'} <b>${label}</b>
    ${o.ok ? '— conforme' : '<ul style="margin:4px 0 0 20px">'+o.issues.map(i=>`<li>${esc(i)}</li>`).join('')+'</ul>'}</div>`;
  let h = `<div style="margin-top:14px;padding:12px;border-radius:8px;background:${(c.c1201.ok&&c.c1202.ok)?'#e8f5e9':'#fff4e5'}">
    <b>Conformité Danone (12 Basics)</b>
    ${line('12.01 — Permis global', c.c1201)}
    ${line('12.02 — Inspection quotidienne consignée', c.c1202)}
    ${c.expires_in_days!==null ? `<div class="note">Validité : ${c.expires_in_days>=0 ? 'expire dans '+c.expires_in_days+' jour(s)' : 'expiré'}${c.renewal_due?' — <b>renouvellement à planifier</b>':''}</div>`:''}
  </div>`;

  // Signatures PTA / approbation
  const sign = p.pta_sign || {};
  const locked = p.statut === 'Fermé';
  h += `<div style="margin-top:14px;padding:12px;background:#f3f6ee;border-radius:8px"><b>✍️ Approbation et signatures du PTA</b>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-top:8px">`;
  for(const [role,label] of Object.entries(PTA_SIGN_LABELS)){
    const s = sign[role];
    h += `<div style="border:1px solid #d9e2cf;border-radius:6px;padding:8px;background:#fff"><div style="font-size:12px;color:var(--gris)">${label}</div>`;
    if(s){
      h += `<img src="${esc(safeSig(s.signature))}" style="max-width:100%;height:60px;object-fit:contain"><div style="font-size:12px"><b>${esc(s.nom)}</b><br>${esc((s.le||'').replace('T',' ').slice(0,16))}</div>`;
    } else if(!locked && !(role==='approbation' && currentUser.role!=='admin')){
      h += `<button class="btn btn-secondary btn-sm" style="margin-top:6px" onclick="openPtaSign('${role}')">✍️ Signer</button>`;
    } else {
      h += `<div class="note" style="margin-top:6px">${role==='approbation'?'En attente (administrateur)':'Non signé'}</div>`;
    }
    h += `</div>`;
  }
  h += `</div></div>`;

  // Inspections quotidiennes
  const ins = p.inspections || [];
  h += `<div style="margin-top:14px;padding:12px;background:#eef4fb;border-radius:8px"><b>🔍 Inspection quotidienne du chantier</b>`;
  if(c.c1202.missing_days && c.c1202.missing_days.length){
    h += `<div style="margin:6px 0;color:#b26a00">Jours sans inspection : ${c.c1202.missing_days.map(esc).join(', ')}${c.c1202.missing_count>c.c1202.missing_days.length?' …':''}</div>`;
  }
  if(ins.length){
    h += `<div style="overflow-x:auto"><table style="margin-top:6px"><thead><tr><th>Date</th><th>Dangers présents</th><th>Plan de mitigation</th><th>Vérif. Danone</th><th>Par</th></tr></thead><tbody>`
      + ins.slice().reverse().map(i=>`<tr><td>${esc(i.date)}</td>
        <td>${i.aucun_travail?'<i>Aucun travail ce jour</i>':esc(i.dangers)||'—'}</td><td>${esc(i.mitigation)||'—'}</td>
        <td>${i.danone_verify?'✅':'—'}</td><td>${esc(i.par)}</td></tr>`).join('') + `</tbody></table></div>`;
  } else h += `<p class="note">Aucune inspection consignée.</p>`;
  if(p.statut==='Actif'){
    h += `<div style="margin-top:10px;border-top:1px solid #cfe0f3;padding-top:10px">
      <div class="grid2"><div><label>Date</label><input type="date" id="insDate" value="${new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10)}"></div>
      <div style="display:flex;align-items:flex-end;gap:14px"><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="insAucun" onchange="document.getElementById('insFields').classList.toggle('hidden',this.checked)"> Aucun travail ce jour</label>
      <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="insVerify"> Vérifié par Danone</label></div></div>
      <div id="insFields" style="margin-top:8px"><label>Dangers présents (BPF/GMP, ÉPI, obstructions, sortie d'urgence, déchets, permis en place)</label><textarea id="insDangers"></textarea>
      <label style="margin-top:8px;display:block">Plan de mitigation</label><textarea id="insMitigation"></textarea></div>
      <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="saveInspection()">💾 Consigner l'inspection</button></div>`;
  }
  return h + `</div>`;
}

async function saveInspection(){
  try{
    await api(`/api/permits/${currentPermit.id}/inspection`, {method:'POST', body: JSON.stringify({
      date: val('insDate'), aucun_travail: document.getElementById('insAucun').checked,
      dangers: val('insDangers'), mitigation: val('insMitigation'),
      danone_verify: document.getElementById('insVerify').checked })});
    currentPermit = await api(`/api/permits/${currentPermit.id}`);
    renderDetail(currentPermit);
    toast('✅ Inspection consignée');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

let ptaSignRole = null;
function openPtaSign(role){
  ptaSignRole = role;
  document.getElementById('ptaSignTitle').textContent = PTA_SIGN_LABELS[role];
  document.getElementById('ptaSignNom').value = currentUser.full_name || '';
  document.getElementById('ptaSignModal').classList.remove('hidden');
  setTimeout(()=>initSigPad('sigPta'), 30);
}
function closePtaSign(){ document.getElementById('ptaSignModal').classList.add('hidden'); }
async function confirmPtaSign(){
  const canvas = sigCanvases['sigPta'];
  const nom = val('ptaSignNom');
  if(!nom){ toast('⚠️ Nom du signataire requis', true); return; }
  if(isCanvasBlank(canvas)){ toast('⚠️ Signature requise', true); return; }
  try{
    await api(`/api/permits/${currentPermit.id}/pta-sign`, {method:'POST', body: JSON.stringify({role: ptaSignRole, nom, signature: canvas.toDataURL('image/png')})});
    currentPermit = await api(`/api/permits/${currentPermit.id}`);
    closePtaSign();
    renderDetail(currentPermit);
    toast('✅ Signature enregistrée');
  }catch(e){ toast('⚠️ ' + e.message, true); }
}

// ---------- Tableau de conformité (onglet Audit) ----------
const LEVEL_COLORS = {Compliant:'#2e7d32', Significant:'#7cb342', Partial:'#f9a825', Basic:'#c62828', 'N/A':'#777'};
async function loadComplianceReport(){
  const el = document.getElementById('complianceReport'); if(!el) return;
  const r = await api('/api/compliance').catch(()=>null);
  if(!r){ el.innerHTML = '<p class="note">Indisponible.</p>'; return; }
  const lv = (l,pct) => `<span style="background:${LEVEL_COLORS[l]};color:#fff;border-radius:10px;padding:2px 9px;font-size:12px">${l}${pct===null?'':' · '+pct+' %'}</span>`;
  let h = `<p class="note" style="margin-bottom:8px">Niveau indicatif calculé sur les permis non archivés (hors brouillons) : 100 % = Compliant, ≥ 90 % = Significant, ≥ 50 % = Partial, sinon Basic. L'auditeur Danone reste seul juge.</p>
    <p><b>Global :</b> 12.01 ${lv(r.global.level1201, r.global.pct1201)} &nbsp; 12.02 ${lv(r.global.level1202, r.global.pct1202)} &nbsp; <span class="note">(${r.global.total} permis)</span></p>`;
  if(r.zones.length){
    h += `<div style="overflow-x:auto"><table style="margin-top:8px"><thead><tr><th>Secteur (zone)</th><th>Permis</th><th>12.01 — Permis global</th><th>12.02 — Inspection quotidienne</th></tr></thead><tbody>`
      + r.zones.map(z=>`<tr><td>${esc(z.zone)}</td><td>${z.total}</td><td>${lv(z.level1201,z.pct1201)}</td><td>${lv(z.level1202,z.pct1202)}</td></tr>`).join('') + `</tbody></table></div>`;
  }
  if(r.non_conformes.length){
    h += `<details style="margin-top:10px"><summary><b>${r.non_conformes.length} permis à corriger</b></summary><ul style="margin:6px 0 0 18px">`
      + r.non_conformes.map(n=>`<li><a href="#" onclick="openDetail(${n.id});return false"><b>${esc(n.num)}</b></a> — ${esc(n.entreprise||'')} (${esc(n.zone)}) : ${n.issues.map(esc).join(' • ')}</li>`).join('') + `</ul></details>`;
  }
  el.innerHTML = h;
}

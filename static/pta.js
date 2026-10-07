// Contenu du Permis de travail mondial Danone (PTA — révision 03/09/2026).
// Rendu générique : chaque champ est stocké dans permits.pta (JSON, clé -> texte ou liste).
const PTA_YN = ['Oui','Non','N/A'];
const PTA_PPE = {
  ppe: ['Lunettes de sécurité','Écran facial complet','Lunettes étanches (produits chimiques)','Casque/lentilles de soudure/coupe','Casque de sécurité','Cache-oreilles','Bouchons d\'oreilles','Gants de cuir','Gants anti-coupure','Combinaison','Chaussures à embout d\'acier','Bottes chimiques','Bottes de caoutchouc','Écran de soudeur','Résistant aux produits chimiques','Vêtement ignifuge (FRC électrique)','Protection incendie','Dossard réfléchissant','Vêtement pluie/vent'],
  ppe_chute: ['Harnais complet','Longe à enrouleur','Lignes de vie','Pinces de toit','Garde-corps','Barricades','Couvercles de trous'],
  ppe_resp: ['ARI (SCBA)','Air fourni','Pleine face / demi-masque','Chimique','Cagoule','Particules','HEPA'],
};
const PTA_PPE_TITLES = { ppe:'ÉPI requis', ppe_chute:'Protection contre les chutes', ppe_resp:'Protection respiratoire' };
const PTA_QUESTIONS = [
  ['sds','Fiches de données de sécurité (FDS) des produits chimiques fournies à Danone'],
  ['gmp_equip','De l\'équipement sera-t-il apporté en zone BPF/GMP ? (si OUI : revue Qualité requise)'],
  ['inflammables','Matières inflammables/combustibles entreposées, séparées, inspectées et sécurisées selon la procédure ?'],
  ['douche','Douche de sécurité et lave-yeux identifiés et opérationnels (signaler tout équipement non fonctionnel)'],
  ['zone_balisee','Zone de travail identifiée par ruban de signalisation, cônes, barricades, etc.'],
];
// [clé, libellé, [sous-champs [clé, libellé, type('yn'|'text')]]]
const PTA_PROCS = [
  ['loto','Cadenassage (LOTO) — permis requis',[['loto_sources','Sources isolées','text'],['loto_panneau','Emplacement du panneau','text']]],
  ['shunt','Shuntage — permis de shuntage requis',[['shunt_risque','Si aucune procédure : analyse de risques ?','yn']]],
  ['cse','Espace clos — permis requis',[['cse_lieu','Emplacement','text'],['cse_sources','Emplacement des sources associées','text']]],
  ['elec','Travaux électriques sous tension — permis requis',[['elec_panneau','Emplacement du panneau associé','text']]],
  ['chaud','Travaux à chaud — permis requis',[['chaud_gmp','En zone BPF/GMP ? (revue Qualité requise)','yn'],['chaud_brosses','Brosses métalliques en bon état ?','yn'],['chaud_couverture','Couverture/écran de soudage en place ?','yn'],['chaud_alim','Zone de procédé alimentaire couverte ?','yn'],['chaud_nettoyage','Ustensiles appropriés pour le nettoyage ?','yn'],['chaud_guet','Guet(s) de feu en place ?','yn'],['chaud_guet_nb','Nombre de guets dans la zone','text']]],
  ['incendie','Mise hors service d\'un système incendie',[['incendie_tag','Numéro d\'étiquette RSVP','text']]],
  ['hauteur','Travail en hauteur (harnais) — permis requis',[]],
  ['echafaud','Échafaudages utilisés — permis requis',[['echafaud_ehs','Approuvé par EHS ?','yn'],['echafaud_gmp','En zone GMP ? (revue Qualité requise)','yn'],['echafaud_insp','Inspectés et étiquetés ?','yn']]],
  ['levage','Grues, levages critiques, nacelles, autres PIV — permis requis',[['levage_gmp','En zone GMP ? (revue Qualité requise)','yn'],['levage_plan','Plan de levage documenté ?','yn'],['levage_garde','Zone de travail protégée ?','yn'],['levage_chute','Systèmes antichute installés ?','yn'],['levage_propane','Équipement propane/diesel ?','yn'],['levage_insp','Inspections et formations récentes disponibles ?','yn']]],
  ['fouille','Creusage / tranchée / excavation (> 3 po) — permis requis',[['fouille_plans','Plans vérifiés pour les services publics ?','yn'],['fouille_energie','Énergie coupée dans la zone de travail ?','yn'],['fouille_barriere','Barrière de sécurité autour de la zone (DÉFENSE D\'ENTRER) ?','yn'],['fouille_cachees','Intérieur : conduits et tuyaux cachés repérés/marqués ?','yn'],['fouille_loc','Extérieur : service de localisation identifié/marqué ?','yn'],['fouille_scie','Sciage requis ?','yn'],['fouille_sol','Sol exposé ?','yn'],['fouille_coupe','Coupe de tuile, brique, bloc ou cloison sèche ?','yn'],['fouille_cvc','Contrôles de ventilation (CVC) assurés ?','yn']]],
  ['ligne','Piquage à chaud / rupture de ligne — permis requis',[['ligne_gmp','En zone GMP ? (revue Qualité requise)','yn']]],
  ['percage','Perforation de plancher ou de mur',[]],
  ['toit','Accès au toit — permis requis',[]],
  ['permis_ville','Permis municipaux requis',[]],
  ['permis_prov','Permis provinciaux/étatiques requis',[]],
  ['permis_fed','Permis fédéraux requis',[]],
  ['moteur','Moteur à combustion interne',[['moteur_lieu','Emplacement','text']]],
  ['generatrice','Génératrice (extérieur, min. 20 pi de toute porte/fenêtre/ventilation; détecteur 4 gaz dans le bâtiment le plus proche)',[]],
  ['magnetique','Énergie magnétique (outils appropriés pour garder les aimants séparés)',[]],
];
const PTA_CERT_TYPES = ['Personne compétente','Opérateur de grue','Opérateur de chariot élévateur','Utilisateur d\'outil à cartouche','Entrant en espace clos','Plomb','Équipement aérien','Utilisation d\'échafaudage','Excavations','Manipulateur de matières dangereuses','Amiante'];
const PTA_PROGRAM = [
  ['prog_sst','Le service SST (ou délégué) a-t-il participé à la planification ?'],
  ['prog_comm','Des plans de communication sont-ils en place ?'],
  ['prog_employes','Les employés Danone touchés ont-ils été avisés ?'],
  ['prog_entretien','Des pratiques d\'ordre et de propreté sont-elles en place ?'],
  ['prog_arrets','Tous les arrêts planifiés sont-ils coordonnés avec le contact Danone ?'],
  ['prog_meteo','Les conditions météo ont-elles été considérées ?'],
];
const PTA_HAZ_ROWS = 5;

function ptaSelect(key, opts){
  return `<select id="pta_${key}"><option value="">—</option>${opts.map(o=>`<option>${o}</option>`).join('')}</select>`;
}
function ptaChecks(key, items){
  return `<div class="risques-grid" id="pta_${key}">${items.map(i=>`<label class="risque-item"><input type="checkbox" value="${i.replace(/"/g,'&quot;')}"> <span>${i}</span></label>`).join('')}</div>`;
}
function renderPtaForm(){
  const host = document.getElementById('ptaHost');
  if(!host) return;
  let h = `<div class="grid2"><div><label>Sous-traitants (le cas échéant)</label><input type="text" id="pta_sous_traitants"></div>
    <div><label>Hôte / contact sur le site (Danone)</label><input type="text" id="pta_hote"></div></div>`;
  for(const k of Object.keys(PTA_PPE)) h += `<h3 class="pta-h">${PTA_PPE_TITLES[k]}</h3>${ptaChecks(k, PTA_PPE[k])}`;
  h += `<div style="margin-top:8px"><label>Autre ÉPI (préciser)</label><input type="text" id="pta_ppe_autre"></div>`;
  h += `<h3 class="pta-h">Questions générales</h3>`;
  for(const [k,l] of PTA_QUESTIONS) h += `<div class="pta-row"><span>${l}</span>${ptaSelect(k,PTA_YN)}</div>`;
  h += `<h3 class="pta-h">Procédures / programmes requis <small>(Oui = un permis distinct est requis pour la tâche)</small></h3>`;
  for(const [k,l,subs] of PTA_PROCS){
    h += `<div class="pta-proc"><div class="pta-row"><b>${l}</b>${ptaSelect(k,['Oui','Non'])}</div>`;
    if(subs.length){
      h += `<div class="pta-subs hidden" id="pta_subs_${k}">`;
      for(const [sk,sl,st] of subs){
        h += st==='yn'
          ? `<div class="pta-row"><span>${sl}</span>${ptaSelect(sk,['Oui','Non'])}</div>`
          : `<div><label>${sl}</label><input type="text" id="pta_${sk}"></div>`;
      }
      h += `</div>`;
    }
    h += `</div>`;
  }
  h += `<h3 class="pta-h">Certification additionnelle des employés</h3>
    <div class="pta-row"><span>Certification additionnelle requise ?</span>${ptaSelect('cert',['Oui','Non'])}</div>
    <div id="pta_subs_cert" class="hidden">${ptaChecks('cert_types', PTA_CERT_TYPES)}</div>`;
  h += `<h3 class="pta-h">Programme de sécurité de l'entrepreneur — informations générales</h3>`;
  for(const [k,l] of PTA_PROGRAM) h += `<div class="pta-row"><span>${l}</span>${ptaSelect(k,['Oui','Non'])}</div>`;
  h += `<h3 class="pta-h">Dangers liés à la tâche et mesures pour les ÉLIMINER / CONTRÔLER</h3>`;
  for(let i=1;i<=PTA_HAZ_ROWS;i++) h += `<div class="grid2"><div><input type="text" id="pta_haz_${i}" placeholder="Danger ${i}"></div><div><input type="text" id="pta_ctl_${i}" placeholder="Mesure de contrôle ${i}"></div></div>`;
  host.innerHTML = h;
  for(const [k,,subs] of PTA_PROCS){
    if(subs.length) document.getElementById('pta_'+k).addEventListener('change', ptaSyncSubs);
  }
  document.getElementById('pta_cert').addEventListener('change', ptaSyncSubs);
}
function ptaSyncSubs(){
  for(const [k,,subs] of PTA_PROCS){
    if(!subs.length) continue;
    document.getElementById('pta_subs_'+k).classList.toggle('hidden', document.getElementById('pta_'+k).value!=='Oui');
  }
  document.getElementById('pta_subs_cert').classList.toggle('hidden', document.getElementById('pta_cert').value!=='Oui');
}
function ptaScalarKeys(){
  const keys = ['sous_traitants','hote','ppe_autre','cert'];
  PTA_QUESTIONS.forEach(q=>keys.push(q[0]));
  PTA_PROCS.forEach(p=>{ keys.push(p[0]); p[2].forEach(s=>keys.push(s[0])); });
  PTA_PROGRAM.forEach(q=>keys.push(q[0]));
  for(let i=1;i<=PTA_HAZ_ROWS;i++){ keys.push('haz_'+i,'ctl_'+i); }
  return keys;
}
function ptaListKeys(){ return [...Object.keys(PTA_PPE), 'cert_types']; }
function collectPta(){
  const o = {};
  ptaScalarKeys().forEach(k=>{ const v=(document.getElementById('pta_'+k)||{}).value; if(v) o[k]=v; });
  ptaListKeys().forEach(k=>{
    const el = document.getElementById('pta_'+k);
    const l = [...el.querySelectorAll('input:checked')].map(c=>c.value);
    if(l.length) o[k]=l;
  });
  return o;
}
function populatePta(pta){
  pta = pta || {};
  ptaScalarKeys().forEach(k=>{ const el=document.getElementById('pta_'+k); if(el) el.value = pta[k] || ''; });
  ptaListKeys().forEach(k=>{
    const sel = pta[k] || [];
    document.getElementById('pta_'+k).querySelectorAll('input').forEach(c=>{ c.checked = sel.includes(c.value); });
  });
  ptaSyncSubs();
}
function ptaDetailHtml(pta){
  if(!pta || !Object.keys(pta).length) return '';
  const e = (typeof esc==='function') ? esc : (s=>String(s));
  let h = `<div style="margin-top:14px;padding:10px;background:#f3f6ee;border-radius:8px"><b>📋 Permis mondial Danone (PTA)</b>`;
  if(pta.sous_traitants) h += `<p>Sous-traitants : ${e(pta.sous_traitants)}</p>`;
  if(pta.hote) h += `<p>Hôte / contact Danone : ${e(pta.hote)}</p>`;
  for(const k of Object.keys(PTA_PPE)) if((pta[k]||[]).length) h += `<p><b>${PTA_PPE_TITLES[k]} :</b> ${pta[k].map(e).join(', ')}</p>`;
  if(pta.ppe_autre) h += `<p>Autre ÉPI : ${e(pta.ppe_autre)}</p>`;
  const qs = PTA_QUESTIONS.filter(q=>pta[q[0]]).map(q=>`<li>${e(q[1])} — <b>${e(pta[q[0]])}</b></li>`);
  if(qs.length) h += `<ul>${qs.join('')}</ul>`;
  const yes = PTA_PROCS.filter(p=>pta[p[0]]).map(p=>{
    let s = `<li>${e(p[1])} — <b>${e(pta[p[0]])}</b>`;
    const subs = p[2].filter(x=>pta[x[0]]).map(x=>`${e(x[1])} : ${e(pta[x[0]])}`);
    if(subs.length) s += `<br><small>${subs.join(' · ')}</small>`;
    return s+'</li>';
  });
  if(yes.length) h += `<p><b>Procédures / programmes requis</b></p><ul>${yes.join('')}</ul>`;
  if(pta.cert) h += `<p><b>Certification additionnelle :</b> ${e(pta.cert)}${(pta.cert_types||[]).length?' — '+pta.cert_types.map(e).join(', '):''}</p>`;
  const pg = PTA_PROGRAM.filter(q=>pta[q[0]]).map(q=>`<li>${e(q[1])} — <b>${e(pta[q[0]])}</b></li>`);
  if(pg.length) h += `<p><b>Programme de sécurité de l'entrepreneur</b></p><ul>${pg.join('')}</ul>`;
  const hz = [];
  for(let i=1;i<=PTA_HAZ_ROWS;i++) if(pta['haz_'+i]||pta['ctl_'+i]) hz.push(`<li>${e(pta['haz_'+i]||'—')} → ${e(pta['ctl_'+i]||'—')}</li>`);
  if(hz.length) h += `<p><b>Dangers → mesures de contrôle</b></p><ul>${hz.join('')}</ul>`;
  return h + '</div>';
}

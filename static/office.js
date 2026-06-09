/* =========================================================================
   office.js — OPEN SPACE 2.0 : moteur de bureau isométrique (dessiné en code)

   Remplace l'ancien rebuildOfficeFloor() (image de fond + avatars flottants).
   Chaque agent a un VRAI poste : siège + agent assis + bureau + double écran
   qui affiche son activité réelle. Clic = focus + chat. Délégations animées.

   Dépendances réutilisées de l'app (avec repli si absentes) :
     window.agentsConfig, window.currentActiveAgent,
     window.getAgentColor(name), window.getAgentSpriteSVG(typeOrName),
     window.setActiveAgentVisual(name)   (optionnelle)

   API publique : window.OpenSpace = { render, focus, delegate, setStatus, setActivity }
   Compat : window.rebuildOfficeFloor()
   ========================================================================= */
(function () {
  "use strict";

  // --- Géométrie isométrique --------------------------------------------
  var TILE_W = 132, TILE_H = 66;
  var isoX = function (c, r) { return (c - r) * TILE_W / 2; };
  var isoY = function (c, r) { return (c + r) * TILE_H / 2; };

  // --- Métiers : libellé + type d'écran + couleur de repli ---------------
  var ROLES = {
    athena:        { label: "Superviseur", screen: "chart",     act: ["Coordonne l'essaim", "Répartit les tâches", "Analyse les retours"] },
    codeur:        { label: "Développeur", screen: "code",      act: ["Écrit le code", "Refactore un module", "Corrige un bug"] },
    developer:     { label: "Développeur", screen: "code",      act: ["Écrit le code", "Refactore un module", "Corrige un bug"] },
    auteur:        { label: "Rédacteur",   screen: "prose",     act: ["Rédige un article", "Structure le plan", "Peaufine le style"] },
    redacteur:     { label: "Rédacteur",   screen: "prose",     act: ["Rédige un article", "Structure le plan", "Peaufine le style"] },
    correcteur:    { label: "Correcteur",  screen: "review",    act: ["Relit le texte", "Traque les fautes", "Vérifie les faits"] },
    critique:      { label: "Correcteur",  screen: "review",    act: ["Relit le texte", "Traque les fautes", "Vérifie les faits"] },
    traducteur:    { label: "Traducteur",  screen: "translate", act: ["Traduit un passage", "Adapte le ton", "Vérifie le sens"] },
    communitymanager:{ label: "Community", screen: "social",    act: ["Prépare un post", "Programme la campagne", "Répond aux messages"] },
    support:       { label: "Support",     screen: "prose",     act: ["Répond à un ticket", "Aide un utilisateur"] },
    scientifique:  { label: "Data",        screen: "chart",     act: ["Analyse les données", "Entraîne un modèle"] },
    juriste:       { label: "Juriste",     screen: "review",    act: ["Analyse un contrat", "Vérifie un texte de loi", "Rédige un avis juridique"] },
    _default:      { label: "Agent",       screen: "code",      act: ["Au travail", "Traite une requête"] }
  };

  function roleKey(agent) {
    // 1. MÉTIER déduit du RÔLE (description + nom), PAS de l'avatar décoratif.
    //    (L'avatar/sprite reste choisi par l'utilisateur via spriteOf → avatar_type.)
    var txt = ((agent.description || "") + " " + (agent.name || "") + " " +
               (agent.display_name || "")).toLowerCase();
    var byRole = [
      ["juriste",          /jurid|\bdroit\b|avocat|\bloi\b|l[ée]gal|contrat|notaire/],
      ["codeur",           /\bcod|d[ée]velop|develop|program|script|debug|logiciel|backend|frontend/],
      ["traducteur",       /tradu|translat|linguis|interpr[èe]t/],
      ["correcteur",       /corrig|correct|relect|relit|critique|[ée]dit|orthograph|fautes|relecture/],
      ["auteur",           /r[ée]dig|\b[ée]cri|auteur|romanc|article|r[ée]dact|copywrit/],
      ["communitymanager", /communi|\bsocial|r[ée]seau|marketing|influ|\bpost\b|promo|campagne/],
      ["scientifique",     /\bdata\b|statis|graphiqu|analyse de don|scientif|machine learning|\bml\b/],
    ];
    for (var i = 0; i < byRole.length; i++) {
      if (byRole[i][1].test(txt) && ROLES[byRole[i][0]]) return byRole[i][0];
    }
    // 2. avatar_type / nom s'ils SONT déjà une clé de rôle connue (ex. agent "Codeur").
    var k = (agent.avatar_type || agent.name || "").toLowerCase();
    if (ROLES[k]) return k;
    var n = (agent.name || "").toLowerCase();
    if (ROLES[n]) return n;
    // 3. Dernier recours : mappage des avatar_type décoratifs.
    var map = { robot_neon: "athena", dev_purple: "codeur", writer_orange: "auteur",
      manager_gold: "correcteur", artist_pink: "communitymanager", support_green: "support",
      scientist_blue: "scientifique", translator: "traducteur" };
    if (map[k]) return map[k];
    return "_default";
  }
  function roleOf(agent) { return ROLES[roleKey(agent)] || ROLES._default; }
  // Le RÔLE/MÉTIER AFFICHÉ = le nom de l'agent (ce que l'utilisateur a défini : Juriste,
  // Secretaire, Codeur…). Générique : ne dépend d'AUCUNE liste codée en dur, donc un
  // métier inconnu s'affiche tel quel au lieu de tomber sur « Agent ».
  function roleLabelOf(agent) { return (agent.name || agent.display_name || "Agent"); }

  function colorOf(agent) {
    if (typeof window.getAgentColor === "function") return window.getAgentColor(agent.name);
    return "#00f0ff";
  }
  function spriteOf(agent) {
    if (typeof window.getAgentSpriteSVG === "function")
      return window.getAgentSpriteSVG(agent.avatar_type || agent.name);
    return "";
  }

  // --- Contenu animé des écrans selon le métier --------------------------
  function screenContent(role, color, uid) {
    var c = color, dim = "rgba(255,255,255,0.30)";
    function line(x, y, w, col, delay) {
      return '<rect class="ws-screenline" x="' + x + '" y="' + y + '" width="' + w +
        '" height="2.2" rx="1.1" fill="' + col + '" style="animation-delay:' + delay + 's"/>';
    }
    var g = '';
    if (role === "code") {
      g += line(5, 6, 14, c, 0) + line(9, 11, 20, dim, .3) + line(9, 16, 12, c, .6) +
           line(5, 21, 22, dim, .2) + line(9, 26, 16, c, .9);
      g += '<rect class="ws-cursor" x="27" y="26" width="2" height="3" fill="' + c + '"/>';
    } else if (role === "prose") {
      g += line(5, 7, 30, dim, 0) + line(5, 12, 28, dim, .25) + line(5, 17, 31, dim, .5) +
           line(5, 22, 24, dim, .75) + line(5, 27, 18, c, 1);
    } else if (role === "translate") {
      g += line(4, 8, 13, dim, 0) + line(4, 14, 11, dim, .3) + line(4, 20, 13, dim, .6) +
           line(22, 8, 13, c, .15) + line(22, 14, 12, c, .45) + line(22, 20, 10, c, .75);
      g += '<line x1="19" y1="5" x2="19" y2="26" stroke="rgba(255,255,255,0.18)" stroke-width="0.8"/>';
    } else if (role === "review") {
      g += line(5, 7, 26, dim, 0) + line(5, 13, 22, dim, .3);
      g += '<line x1="5" y1="19" x2="25" y2="19" stroke="' + c + '" stroke-width="1.6" opacity="0.5"/>';
      g += line(5, 24, 18, dim, .6);
      g += '<path class="ws-typing" d="M28 22 l2 2 l4 -5" stroke="' + c + '" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
    } else if (role === "social") {
      g += line(5, 7, 28, dim, 0) + line(5, 12, 20, dim, .3);
      g += '<rect x="5" y="17" width="20" height="9" rx="1.5" fill="' + c + '" opacity="0.16"/>';
      g += '<path class="ws-typing" d="M31 24c-1.6-1.4-2.6-2.2-2.6-3.2 0-.8.6-1.4 1.4-1.4.5 0 1 .3 1.2.7.2-.4.7-.7 1.2-.7.8 0 1.4.6 1.4 1.4 0 1-1 1.8-2.6 3.2z" fill="' + c + '"/>';
    } else { // chart
      g += '<rect x="6" y="20" width="4" height="9"  rx="1" fill="' + c + '" opacity="0.85"/>';
      g += '<rect x="13" y="14" width="4" height="15" rx="1" fill="' + c + '" opacity="0.7"/>';
      g += '<rect x="20" y="9"  width="4" height="20" rx="1" fill="' + c + '" opacity="0.95"/>';
      g += '<rect x="27" y="17" width="4" height="12" rx="1" fill="' + c + '" opacity="0.6"/>';
      g += '<polyline class="ws-typing" points="6,18 14,12 21,7 30,13" fill="none" stroke="#fff" stroke-width="1" opacity="0.6"/>';
    }
    return g;
  }

  // Un écran (cadre + dalle + contenu), incliné en iso via skewY.
  function monitor(x, y, skew, role, color, uid) {
    var w = 40, h = 30;
    return '<g transform="translate(' + x + ',' + y + ') skewY(' + skew + ')">' +
      // pied
      '<rect x="' + (w / 2 - 4) + '" y="' + h + '" width="8" height="9" fill="#0c1320"/>' +
      '<rect x="' + (w / 2 - 9) + '" y="' + (h + 8) + '" width="18" height="3" rx="1.5" fill="#0c1320"/>' +
      // cadre
      '<rect x="-2" y="-2" width="' + (w + 4) + '" height="' + (h + 4) + '" rx="3" fill="#0a0f1c" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>' +
      // dalle (glow couleur agent)
      '<rect class="ws-screenglow" x="0" y="0" width="' + w + '" height="' + h + '" rx="2" fill="' + color + '" opacity="0.14"/>' +
      '<rect x="0" y="0" width="' + w + '" height="' + h + '" rx="2" fill="#060b16" opacity="0.55"/>' +
      screenContent(role, color, uid) +
      // reflet
      '<path d="M2 2 L14 2 L4 28 L2 28 Z" fill="#ffffff" opacity="0.05"/>' +
      '</g>';
  }

  // --- Siège (derrière l'agent) -----------------------------------------
  function chairSVG(color) {
    return '<svg class="ws-svg ws-svg-back" viewBox="0 0 220 210" width="220" height="210" xmlns="http://www.w3.org/2000/svg">' +
      // base 5 branches + colonne
      '<ellipse cx="110" cy="178" rx="34" ry="15" fill="#0a1120"/>' +
      '<g stroke="#1b2540" stroke-width="4" stroke-linecap="round">' +
        '<line x1="110" y1="172" x2="86" y2="186"/><line x1="110" y1="172" x2="134" y2="186"/>' +
        '<line x1="110" y1="172" x2="110" y2="190"/><line x1="110" y1="172" x2="92" y2="166"/>' +
        '<line x1="110" y1="172" x2="128" y2="166"/>' +
      '</g>' +
      '<rect x="106" y="150" width="8" height="24" rx="3" fill="#16203a"/>' +
      // assise (rhombus)
      '<polygon points="110,134 150,152 110,170 70,152" fill="#1d2944"/>' +
      '<polygon points="110,134 150,152 110,158 70,152" fill="#243357"/>' +
      // dossier
      '<path d="M82 150 Q80 96 110 90 Q140 96 138 150 Q124 138 110 138 Q96 138 82 150 Z" fill="#1b2540"/>' +
      '<path d="M90 146 Q90 104 110 99 Q130 104 130 146 Q120 138 110 138 Q100 138 90 146 Z" fill="#222f50"/>' +
      '<path d="M110 99 Q130 104 130 146 Q120 138 110 138 Z" fill="rgba(0,0,0,0.18)"/>' +
      // liseré couleur agent sur le dossier
      '<path d="M96 112 Q110 108 124 112" stroke="' + color + '" stroke-width="2" fill="none" opacity="0.7" stroke-linecap="round"/>' +
      '</svg>';
  }

  // --- Bureau + écrans (devant l'agent) ---------------------------------
  function deskSVG(color, role, uid) {
    var s = '<svg class="ws-svg ws-svg-front" viewBox="0 0 220 210" width="220" height="210" xmlns="http://www.w3.org/2000/svg">';
    // plateau iso
    var A = "110,108", B = "190,148", C = "110,188", D = "30,148";
    // faces avant
    s += '<polygon points="30,148 110,188 110,214 30,174" fill="#11192c"/>';   // face avant-gauche
    s += '<polygon points="110,188 190,148 190,174 110,214" fill="#0b1322"/>'; // face avant-droite
    // tranche
    s += '<polygon points="30,148 30,174 110,214 110,188" fill="#0d1525"/>';
    // plateau
    s += '<polygon points="' + A + ' ' + B + ' ' + C + ' ' + D + '" fill="#202c46"/>';
    s += '<polygon points="' + A + ' ' + B + ' ' + C + ' ' + D + '" fill="url(#dtop' + uid + ')" opacity="0.5"/>';
    // liseré néon couleur agent au bord du plateau
    s += '<polyline points="30,148 110,188 190,148" fill="none" stroke="' + color + '" stroke-width="1.6" opacity="0.55"/>';
    // dégradé plateau
    s += '<defs><linearGradient id="dtop' + uid + '" x1="0" y1="0" x2="0" y2="1">' +
         '<stop offset="0" stop-color="#2c3a5c"/><stop offset="1" stop-color="#161f36"/></linearGradient></defs>';
    // clavier (rhombus) + souris
    s += '<polygon points="110,168 142,184 116,196 84,180" fill="#0e1626" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>';
    s += '<polygon points="110,170 138,184 116,193 88,180" fill="#16203a" opacity="0.8"/>';
    s += '<ellipse cx="150" cy="176" rx="6" ry="3.4" fill="#0e1626"/>';
    // mug (couleur agent) côté gauche
    s += '<g transform="translate(56,150)"><ellipse cx="0" cy="6" rx="6" ry="3" fill="#0c1320"/>' +
         '<rect x="-5" y="-4" width="10" height="10" rx="2" fill="#16203a"/>' +
         '<rect x="-5" y="-4" width="10" height="3" rx="1.5" fill="' + color + '" opacity="0.8"/></g>';
    // double écran
    s += monitor(60, 96, 9, role, color, uid + 'a');
    s += monitor(120, 96, -9, role, color, uid + 'b');
    // petit voyant "online" sur le bureau
    s += '<circle class="ws-typing" cx="172" cy="160" r="2.4" fill="' + color + '"/>';
    s += '</svg>';
    return s;
  }

  // --- Décor : sol + murs + fenêtres -------------------------------------
  function backdrop(minC, maxC, minR, maxR, ox, oy) {
    var pad = 1.4;
    var c0 = minC - pad, c1 = maxC + pad, r0 = minR - pad, r1 = maxR + pad;
    var P = function (c, r) { return (ox + isoX(c, r)) + ',' + (oy + isoY(c, r)); };
    var s = '';
    // dalle de sol (un grand losange)
    s += '<polygon points="' + P(c0, r0) + ' ' + P(c1, r0) + ' ' + P(c1, r1) + ' ' + P(c0, r1) +
         '" fill="url(#floorGrad)"/>';
    // quadrillage
    var lines = '';
    for (var c = Math.ceil(c0); c <= Math.floor(c1); c++)
      lines += '<line x1="' + (ox + isoX(c, r0)) + '" y1="' + (oy + isoY(c, r0)) +
               '" x2="' + (ox + isoX(c, r1)) + '" y2="' + (oy + isoY(c, r1)) + '"/>';
    for (var r = Math.ceil(r0); r <= Math.floor(r1); r++)
      lines += '<line x1="' + (ox + isoX(c0, r)) + '" y1="' + (oy + isoY(c0, r)) +
               '" x2="' + (ox + isoX(c1, r)) + '" y2="' + (oy + isoY(c1, r)) + '"/>';
    s += '<g stroke="rgba(120,170,255,0.10)" stroke-width="1">' + lines + '</g>';

    // murs (corner en haut) : mur gauche (le long de r0) et mur droit (le long de c0)
    var wallH = 150;
    // mur arrière-droit (le long de la ligne r=r0, de c0->c1) face caméra (descend vers la droite)
    var wlA = P(c0, r0), wlB = P(c1, r0);
    var ax = ox + isoX(c0, r0), ay = oy + isoY(c0, r0);
    var bx = ox + isoX(c1, r0), by = oy + isoY(c1, r0);
    s += '<polygon points="' + ax + ',' + ay + ' ' + bx + ',' + by + ' ' + bx + ',' + (by - wallH) + ' ' + ax + ',' + (ay - wallH) +
         '" fill="url(#wallR)"/>';
    // mur arrière-gauche (le long de c=c0, r0->r1) (descend vers la gauche)
    var cx = ox + isoX(c0, r1), cy = oy + isoY(c0, r1);
    s += '<polygon points="' + ax + ',' + ay + ' ' + cx + ',' + cy + ' ' + cx + ',' + (cy - wallH) + ' ' + ax + ',' + (ay - wallH) +
         '" fill="url(#wallL)"/>';

    // fenêtres sur le mur droit (cityscape nocturne)
    var winR = '';
    var nW = Math.max(2, Math.round((c1 - c0) / 2));
    for (var i = 0; i < nW; i++) {
      var t0 = (i + 0.18) / nW, t1 = (i + 0.82) / nW;
      var x0 = ax + (bx - ax) * t0, y0 = ay + (by - ay) * t0;
      var x1 = ax + (bx - ax) * t1, y1 = ay + (by - ay) * t1;
      var top = 30, bot = wallH - 26;
      winR += '<polygon points="' + x0 + ',' + (y0 - bot) + ' ' + x1 + ',' + (y1 - bot) + ' ' +
              x1 + ',' + (y1 - top) + ' ' + x0 + ',' + (y0 - top) + '" fill="url(#cityR)" stroke="rgba(120,200,255,0.25)" stroke-width="1.2"/>';
    }
    s += winR;
    // bandeau néon haut du mur droit
    s += '<polyline points="' + ax + ',' + (ay - wallH + 8) + ' ' + bx + ',' + (by - wallH + 8) +
         '" stroke="#00f0ff" stroke-width="2" opacity="0.5"/>';
    s += '<polyline points="' + ax + ',' + (ay - wallH + 8) + ' ' + cx + ',' + (cy - wallH + 8) +
         '" stroke="#d600ff" stroke-width="2" opacity="0.4"/>';

    return s;
  }

  // --- Disposition 1→N agents -------------------------------------------
  function layout(agents) {
    var n = agents.length;
    var cols = Math.max(1, Math.ceil(Math.sqrt(n)));
    if (n <= 3) cols = n;                 // une seule rangée pour 1-3 agents
    var cells = [];
    for (var i = 0; i < n; i++) {
      var gx = i % cols, gy = Math.floor(i / cols);
      cells.push({ c: gx * 2, r: gy * 2 }); // 2 tuiles d'espacement (allées)
    }
    return cells;
  }

  // --- Rendu complet -----------------------------------------------------
  var sceneEl = null, stageEl = null, cam = { z: 1, x: 0, y: 0 };

  // --- Pont vers l'app ----------------------------------------------------
  // agentsConfig / currentActiveAgent sont des `let` GLOBAUX d'app.js : ce ne
  // sont PAS des propriétés de window. On lit donc le binding lexical (partagé
  // entre scripts classiques), avec repli sur window.* (prototype) puis [].
  function appAgents() {
    try { if (typeof agentsConfig !== "undefined" && agentsConfig && agentsConfig.length) return agentsConfig; } catch (e) {}
    return (window.agentsConfig && window.agentsConfig.length) ? window.agentsConfig : [];
  }
  function appActive() {
    try { if (typeof currentActiveAgent !== "undefined" && currentActiveAgent) return currentActiveAgent; } catch (e) {}
    return window.currentActiveAgent || null;
  }

  function render() {
    var view = document.getElementById("view-office");
    if (!view) return;
    var agents = appAgents();
    if (!agents.length) return;

    // structure (créée une fois)
    view.querySelectorAll(".office-stage,.office-legend,.office-hint").forEach(function (e) { e.remove(); });
    var floor = view.querySelector(".office-floor");
    if (floor) floor.style.display = "none"; // neutralise l'ancien sol

    stageEl = document.createElement("div");
    stageEl.className = "office-stage";
    sceneEl = document.createElement("div");
    sceneEl.className = "office-scene";
    stageEl.appendChild(sceneEl);
    view.appendChild(stageEl);

    var cells = layout(agents);
    var minC = Infinity, maxC = -Infinity, minR = Infinity, maxR = -Infinity;
    cells.forEach(function (p) { minC = Math.min(minC, p.c); maxC = Math.max(maxC, p.c); minR = Math.min(minR, p.r); maxR = Math.max(maxR, p.r); });

    // bornes écran pour dimensionner la scène
    var pad = 1.6;
    var corners = [[minC - pad, minR - pad], [maxC + pad, minR - pad], [minC - pad, maxR + pad], [maxC + pad, maxR + pad]];
    var xs = corners.map(function (p) { return isoX(p[0], p[1]); });
    var ys = corners.map(function (p) { return isoY(p[0], p[1]); });
    var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys) - 150, maxY = Math.max.apply(null, ys) + 80; // +mur en haut
    var ox = -minX, oy = -minY;
    var W = maxX - minX, H = maxY - minY;
    sceneEl.style.width = W + "px";
    sceneEl.style.height = H + "px";

    // décor
    var bg = '<svg class="office-backdrop" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">' +
      '<defs>' +
      '<radialGradient id="floorGrad" cx="50%" cy="35%" r="75%"><stop offset="0" stop-color="#1a2740"/><stop offset="1" stop-color="#0a1120"/></radialGradient>' +
      '<linearGradient id="wallR" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0e1830"/><stop offset="1" stop-color="#0a1326"/></linearGradient>' +
      '<linearGradient id="wallL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0b1428"/><stop offset="1" stop-color="#070f20"/></linearGradient>' +
      '<linearGradient id="cityR" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0a1c34"/><stop offset="0.6" stop-color="#13294a"/><stop offset="1" stop-color="#1d3a63"/></linearGradient>' +
      '</defs>' +
      backdrop(minC, maxC, minR, maxR, ox, oy) +
      '</svg>';
    sceneEl.insertAdjacentHTML("beforeend", bg);

    // postes
    agents.forEach(function (agent, i) {
      var p = cells[i];
      var x = ox + isoX(p.c, p.r);
      var y = oy + isoY(p.c, p.r);
      var color = colorOf(agent);
      var role = roleOf(agent);
      var uid = "u" + i;
      var disp = agent.display_name || agent.name;

      var ws = document.createElement("div");
      ws.className = "ws";
      ws.id = "ws-" + agent.name;
      ws.style.left = x + "px";
      ws.style.top = y + "px";
      ws.style.zIndex = 100 + Math.round(p.c + p.r);
      ws.style.setProperty("--agent-color", color);

      ws.innerHTML =
        '<div class="ws-ring"></div>' +
        chairSVG(color) +
        '<div class="ws-agent">' + spriteOf(agent) + '</div>' +
        deskSVG(color, role.screen, uid) +
        '<div class="ws-bubble">' + role.act[0] + '</div>' +
        '<div class="ws-plate">' +
          '<div class="ws-plate-name"><span class="ws-dot"></span>' + esc(disp) + '</div>' +
          '<div class="ws-plate-role">' + esc(roleLabelOf(agent)) + '</div>' +
          '<div class="ws-plate-status">' + role.act[0] + '</div>' +
        '</div>';

      ws.addEventListener("click", function (e) {
        e.stopPropagation();
        OpenSpace.focus(agent.name);
      });
      sceneEl.appendChild(ws);
      applyStatus(agent.name, agent.status || "busy");
    });

    // légende + aide
    view.insertAdjacentHTML("beforeend",
      '<div class="office-legend">' +
        '<span class="leg"><span class="leg-dot busy"></span><b>Actif</b></span>' +
        '<span class="leg"><span class="leg-dot paused"></span><b>En pause</b></span>' +
        '<span class="leg"><span class="leg-dot quota"></span><b>Quota</b></span>' +
      '</div>' +
      '<div class="office-hint">Clic sur un poste = focus &amp; chat · <kbd>molette</kbd> zoom · glisser pour déplacer</div>');

    setupCamera();
    fit();
    var _active = appActive();
    if (_active) OpenSpace.focus(_active, true);
    startSim();
  }

  function esc(s) { return String(s).replace(/[&<>]/g, function (m) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[m]; }); }

  // --- Statut & activité -------------------------------------------------
  var ST = { busy: "#22c55e", paused: "#f59e0b", quota: "#ef4444" };
  function applyStatus(name, status) {
    var ws = document.getElementById("ws-" + name);
    if (!ws) return;
    ws.classList.remove("paused", "quota");
    if (status === "paused") ws.classList.add("paused");
    if (status === "quota") ws.classList.add("quota");
    var dot = ws.querySelector(".ws-dot");
    if (dot) dot.style.setProperty("--st-color", ST[status] || ST.busy);
  }

  function setActivity(name, text) {
    var ws = document.getElementById("ws-" + name);
    if (!ws) return;
    var b = ws.querySelector(".ws-bubble"), s = ws.querySelector(".ws-plate-status");
    if (b) b.textContent = text;
    if (s) s.textContent = text;
  }

  // --- Focus (clic) ------------------------------------------------------
  function focus(name, silent) {
    window.currentActiveAgent = name;
    if (sceneEl) sceneEl.classList.add("has-active");
    document.querySelectorAll(".ws").forEach(function (w) { w.classList.toggle("active", w.id === "ws-" + name); });
    // relais vers l'app si dispo (met à jour le chat de droite)
    if (!silent && typeof window.setActiveAgentVisual === "function") {
      try { window.setActiveAgentVisual(name); } catch (e) {}
    }
    // recentre légèrement sur le poste
    var ws = document.getElementById("ws-" + name);
    if (ws && stageEl) {
      var b = ws.classList; // (focus discret, pas de recadrage agressif)
    }
  }

  // --- Délégation : paquet de travail volant ----------------------------
  function delegate(from, to) {
    if (!sceneEl) return;
    var a = document.getElementById("ws-" + from), b = document.getElementById("ws-" + to);
    if (!a || !b) return;
    var ax = parseFloat(a.style.left), ay = parseFloat(a.style.top) - 60;
    var bx = parseFloat(b.style.left), by = parseFloat(b.style.top) - 60;
    var color = a.style.getPropertyValue("--agent-color") || "#00f0ff";

    var trail = document.createElement("div");
    trail.className = "deleg-trail";
    trail.style.setProperty("--p-color", color);
    var dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy), ang = Math.atan2(dy, dx) * 180 / Math.PI;
    trail.style.left = ax + "px"; trail.style.top = ay + "px";
    trail.style.width = len + "px"; trail.style.transform = "rotate(" + ang + "deg)";
    sceneEl.appendChild(trail);

    var pk = document.createElement("div");
    pk.className = "deleg-packet";
    pk.style.setProperty("--p-color", color);
    pk.style.left = ax + "px"; pk.style.top = ay + "px";
    pk.textContent = "📦";
    sceneEl.appendChild(pk);

    setActivity(from, "Délègue à " + to + "…");
    requestAnimationFrame(function () {
      trail.style.opacity = "0.9";
      pk.style.left = bx + "px"; pk.style.top = by + "px";
    });
    setTimeout(function () {
      pk.style.opacity = "0"; trail.style.opacity = "0";
      var bws = document.getElementById("ws-" + to);
      if (bws) { bws.classList.add("show-bubble"); setActivity(to, "Reçoit une tâche 📥"); }
      setTimeout(function () { pk.remove(); trail.remove(); if (bws) bws.classList.remove("show-bubble"); }, 1400);
    }, 1150);
  }

  // --- Caméra : zoom molette + glisser-déplacer + boutons ----------------
  function applyCam() {
    if (!sceneEl) return;
    sceneEl.style.transform = "translate(" + cam.x + "px," + cam.y + "px) scale(" + cam.z + ")";
  }
  function fit() {
    var view = document.getElementById("view-office");
    if (!view || !sceneEl) return;
    var vw = view.clientWidth, vh = view.clientHeight;
    var sw = sceneEl.offsetWidth, sh = sceneEl.offsetHeight;
    cam.z = Math.min(1.15, Math.min(vw / (sw + 60), vh / (sh + 60)));
    cam.x = 0; cam.y = 0;
    applyCam();
  }
  function setupCamera() {
    var view = document.getElementById("view-office");
    if (!stageEl) return;
    if (stageEl._wired) return; stageEl._wired = true;

    stageEl.addEventListener("wheel", function (e) {
      e.preventDefault();
      var d = e.deltaY < 0 ? 1.12 : 0.89;
      cam.z = Math.max(0.4, Math.min(2.4, cam.z * d));
      sceneEl.classList.add("dragging"); applyCam();
      clearTimeout(stageEl._zt); stageEl._zt = setTimeout(function () { sceneEl.classList.remove("dragging"); }, 120);
    }, { passive: false });

    var drag = null;
    stageEl.addEventListener("pointerdown", function (e) {
      if (e.target.closest(".ws") || e.target.closest(".floating-office-controls")) return;
      drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y };
      stageEl.classList.add("grabbing"); sceneEl.classList.add("dragging");
      stageEl.setPointerCapture(e.pointerId);
    });
    stageEl.addEventListener("pointermove", function (e) {
      if (!drag) return;
      cam.x = drag.cx + (e.clientX - drag.x);
      cam.y = drag.cy + (e.clientY - drag.y);
      applyCam();
    });
    var end = function () { drag = null; stageEl.classList.remove("grabbing"); sceneEl.classList.remove("dragging"); };
    stageEl.addEventListener("pointerup", end);
    stageEl.addEventListener("pointercancel", end);

    // boutons existants
    bind("btn-office-zoom-in", function () { cam.z = Math.min(2.4, cam.z * 1.18); applyCam(); });
    bind("btn-office-zoom-out", function () { cam.z = Math.max(0.4, cam.z * 0.85); applyCam(); });
    var rot = document.getElementById("btn-office-rotate");
    if (rot) { rot.title = "Recentrer la vue"; rot.textContent = "⊙"; rot.onclick = fit; }
    window.addEventListener("resize", function () { clearTimeout(window._ofr); window._ofr = setTimeout(fit, 200); });
  }
  function bind(id, fn) { var el = document.getElementById(id); if (el) el.onclick = fn; }

  // --- Simulation de vie (démo) : rotation des activités ----------------
  var simTimer = null;
  function startSim() {
    if (simTimer) clearInterval(simTimer);
    simTimer = setInterval(function () {
      var agents = appAgents();
      if (agents.length < 2) {
        if (agents[0]) { var r = roleOf(agents[0]); setActivity(agents[0].name, r.act[Math.floor(Math.random() * r.act.length)]); }
        return;
      }
      var _act = appActive();
      var idle = agents.filter(function (a) { return a.name !== _act; });
      var a = idle[Math.floor(Math.random() * idle.length)];
      if (!a) return;
      var role = roleOf(a);
      setActivity(a.name, role.act[Math.floor(Math.random() * role.act.length)]);
    }, 6000);
  }

  // --- API + compat ------------------------------------------------------
  window.OpenSpace = { render: render, focus: focus, delegate: delegate, setStatus: applyStatus, setActivity: setActivity, fit: fit };
  window.rebuildOfficeFloor = render; // compat avec l'appel existant dans app.js

  // --- Bootstrap robuste : ne pas dépendre du timing d'appel d'app.js -----
  // Les agents sont chargés en ASYNC par app.js ; on rend dès qu'ils arrivent,
  // puis on s'appuie sur les appels rebuildOfficeFloor() existants pour les MAJ.
  function _osBoot() { try { render(); } catch (e) { if (window.console) console.error("[OpenSpace]", e); } }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _osBoot);
  else _osBoot();
  (function () {
    var last = -1, tries = 0;
    var iv = setInterval(function () {
      var n = appAgents().length;
      if (n !== last) { last = n; if (n > 0) _osBoot(); }
      if (++tries > 60) clearInterval(iv); // ~30 s de filet
    }, 500);
  })();
})();

// Athena — i18n léger (sans dépendance).
// Le FR est la LANGUE DE BASE : le texte FR est celui codé en dur dans le HTML, capturé au
// premier passage. Les autres langues viennent des dictionnaires ci-dessous ; clé absente →
// repli sur le FR d'origine. Élément traduisible = attribut `data-i18n="cle"`.
// API : window.AthenaI18n.{ current(), setLang(l), apply(root), t(key) }.
(function () {
  "use strict";
  const STORE_KEY = "athena_lang";
  const SUPPORTED = ["fr", "en", "es", "it", "de", "zh", "ja"];

  // Dictionnaires (hors FR = base). Couvre pour l'instant la navigation principale (dock) ;
  // à étendre progressivement (les éléments sans traduction restent en FR — repli propre).
  const DICT = {
    en: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Code","dock.design":"Design","dock.tasks":"Tasks","dock.more":"More","dock.graph":"Graph","dock.branches":"Branches","dock.memory":"Memory","dock.meeting":"Meetings","dock.console":"Console","dock.orchestrator":"Orchestrator",
      "group.agents":"Agents","group.connections":"Connections","group.system":"System","group.extensions":"Extensions",
      "tab.agents":"👤 Agents","tab.keys":"🔑 API Keys","tab.ssh":"🖥️ Terminal & SSH","tab.agenda":"📅 Calendar","tab.messaging":"📨 Messaging","tab.satellites":"🛰️ Voice satellites","tab.behavior":"⚙️ Behavior","tab.pricing":"💰 LLM Pricing","tab.users":"👥 Users","tab.doctor":"🩺 Diagnostics","tab.plugins":"🔌 Plugins","tab.mcp":"🧩 MCP servers","tab.routines":"🗓️ Routines","tab.workflows":"🛠️ Workflows","tab.knowledge":"📚 Knowledge" },
    es: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Código","dock.design":"Diseño","dock.tasks":"Tareas","dock.more":"Más","dock.graph":"Grafo","dock.branches":"Ramas","dock.memory":"Memoria","dock.meeting":"Reuniones","dock.console":"Consola","dock.orchestrator":"Orquestador",
      "group.agents":"Agentes","group.connections":"Conexiones","group.system":"Sistema","group.extensions":"Extensiones",
      "tab.agents":"👤 Agentes","tab.keys":"🔑 Claves API","tab.ssh":"🖥️ Terminal y SSH","tab.agenda":"📅 Agenda","tab.messaging":"📨 Mensajería","tab.satellites":"🛰️ Satélites de voz","tab.behavior":"⚙️ Comportamiento","tab.pricing":"💰 Precios LLM","tab.users":"👥 Usuarios","tab.doctor":"🩺 Diagnóstico","tab.plugins":"🔌 Plugins","tab.mcp":"🧩 Servidores MCP","tab.routines":"🗓️ Rutinas","tab.workflows":"🛠️ Workflows","tab.knowledge":"📚 Conocimiento" },
    it: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Codice","dock.design":"Design","dock.tasks":"Attività","dock.more":"Altro","dock.graph":"Grafo","dock.branches":"Rami","dock.memory":"Memoria","dock.meeting":"Riunioni","dock.console":"Console","dock.orchestrator":"Orchestratore",
      "group.agents":"Agenti","group.connections":"Connessioni","group.system":"Sistema","group.extensions":"Estensioni",
      "tab.agents":"👤 Agenti","tab.keys":"🔑 Chiavi API","tab.ssh":"🖥️ Terminale e SSH","tab.agenda":"📅 Calendario","tab.messaging":"📨 Messaggistica","tab.satellites":"🛰️ Satelliti vocali","tab.behavior":"⚙️ Comportamento","tab.pricing":"💰 Prezzi LLM","tab.users":"👥 Utenti","tab.doctor":"🩺 Diagnostica","tab.plugins":"🔌 Plugin","tab.mcp":"🧩 Server MCP","tab.routines":"🗓️ Routine","tab.workflows":"🛠️ Workflow","tab.knowledge":"📚 Conoscenza" },
    de: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Code","dock.design":"Design","dock.tasks":"Aufgaben","dock.more":"Mehr","dock.graph":"Graph","dock.branches":"Branches","dock.memory":"Speicher","dock.meeting":"Meetings","dock.console":"Konsole","dock.orchestrator":"Orchestrator",
      "group.agents":"Agenten","group.connections":"Verbindungen","group.system":"System","group.extensions":"Erweiterungen",
      "tab.agents":"👤 Agenten","tab.keys":"🔑 API-Schlüssel","tab.ssh":"🖥️ Terminal & SSH","tab.agenda":"📅 Kalender","tab.messaging":"📨 Messaging","tab.satellites":"🛰️ Sprachsatelliten","tab.behavior":"⚙️ Verhalten","tab.pricing":"💰 LLM-Preise","tab.users":"👥 Benutzer","tab.doctor":"🩺 Diagnose","tab.plugins":"🔌 Plugins","tab.mcp":"🧩 MCP-Server","tab.routines":"🗓️ Routinen","tab.workflows":"🛠️ Workflows","tab.knowledge":"📚 Wissen" },
    zh: { "dock.office":"工作区","dock.cockpit":"驾驶舱","dock.code":"代码","dock.design":"设计","dock.tasks":"任务","dock.more":"更多","dock.graph":"图谱","dock.branches":"分支","dock.memory":"记忆","dock.meeting":"会议","dock.console":"控制台","dock.orchestrator":"编排器",
      "group.agents":"智能体","group.connections":"连接","group.system":"系统","group.extensions":"扩展",
      "tab.agents":"👤 智能体","tab.keys":"🔑 API 密钥","tab.ssh":"🖥️ 终端与 SSH","tab.agenda":"📅 日历","tab.messaging":"📨 消息","tab.satellites":"🛰️ 语音卫星","tab.behavior":"⚙️ 行为","tab.pricing":"💰 LLM 价格","tab.users":"👥 用户","tab.doctor":"🩺 诊断","tab.plugins":"🔌 插件","tab.mcp":"🧩 MCP 服务器","tab.routines":"🗓️ 例程","tab.workflows":"🛠️ 工作流","tab.knowledge":"📚 知识" },
    ja: { "dock.office":"オープンスペース","dock.cockpit":"コックピット","dock.code":"コード","dock.design":"デザイン","dock.tasks":"タスク","dock.more":"その他","dock.graph":"グラフ","dock.branches":"ブランチ","dock.memory":"メモリ","dock.meeting":"会議","dock.console":"コンソール","dock.orchestrator":"オーケストレーター",
      "group.agents":"エージェント","group.connections":"接続","group.system":"システム","group.extensions":"拡張",
      "tab.agents":"👤 エージェント","tab.keys":"🔑 API キー","tab.ssh":"🖥️ ターミナル & SSH","tab.agenda":"📅 カレンダー","tab.messaging":"📨 メッセージング","tab.satellites":"🛰️ 音声サテライト","tab.behavior":"⚙️ 動作","tab.pricing":"💰 LLM 料金","tab.users":"👥 ユーザー","tab.doctor":"🩺 診断","tab.plugins":"🔌 プラグイン","tab.mcp":"🧩 MCP サーバー","tab.routines":"🗓️ ルーティン","tab.workflows":"🛠️ ワークフロー","tab.knowledge":"📚 ナレッジ" }
  };
  const LABELS = { fr:"Français", en:"English", es:"Español", it:"Italiano", de:"Deutsch", zh:"中文", ja:"日本語" };

  function detect() {
    try {
      const saved = localStorage.getItem(STORE_KEY);
      if (saved && SUPPORTED.includes(saved)) return saved;
      const nav = (navigator.language || "fr").slice(0, 2).toLowerCase();
      return SUPPORTED.includes(nav) ? nav : "fr";
    } catch (e) { return "fr"; }
  }
  let lang = detect();

  function t(key) {
    if (lang === "fr") return null;            // base : pas de surcharge
    const d = DICT[lang] || {};
    return Object.prototype.hasOwnProperty.call(d, key) ? d[key] : null;
  }

  function apply(root) {
    (root || document).querySelectorAll("[data-i18n]").forEach(function (el) {
      if (el._i18nFr === undefined) el._i18nFr = el.textContent;  // capture la base FR une fois
      const key = el.getAttribute("data-i18n");
      const v = t(key);
      el.textContent = (v != null) ? v : el._i18nFr;              // sinon repli FR d'origine
    });
  }

  function setLang(l) {
    if (!SUPPORTED.includes(l)) return;
    lang = l;
    try { localStorage.setItem(STORE_KEY, l); } catch (e) {}
    document.documentElement.setAttribute("lang", l);
    apply();
  }

  window.AthenaI18n = { current: function () { return lang; }, setLang: setLang, apply: apply, t: t, SUPPORTED: SUPPORTED, LABELS: LABELS };

  document.addEventListener("DOMContentLoaded", function () {
    document.documentElement.setAttribute("lang", lang);
    apply();
    // Câble un éventuel sélecteur de langue présent dans la page.
    const sel = document.getElementById("lang-select");
    if (sel) {
      sel.value = lang;
      sel.addEventListener("change", function () { setLang(sel.value); });
    }
  });
})();

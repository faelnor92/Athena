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
    en: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Code","dock.design":"Design","dock.tasks":"Tasks","dock.more":"More","dock.graph":"Graph","dock.branches":"Branches","dock.memory":"Memory","dock.meeting":"Meetings","dock.console":"Console","dock.orchestrator":"Orchestrator" },
    es: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Código","dock.design":"Diseño","dock.tasks":"Tareas","dock.more":"Más","dock.graph":"Grafo","dock.branches":"Ramas","dock.memory":"Memoria","dock.meeting":"Reuniones","dock.console":"Consola","dock.orchestrator":"Orquestador" },
    it: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Codice","dock.design":"Design","dock.tasks":"Attività","dock.more":"Altro","dock.graph":"Grafo","dock.branches":"Rami","dock.memory":"Memoria","dock.meeting":"Riunioni","dock.console":"Console","dock.orchestrator":"Orchestratore" },
    de: { "dock.office":"Open Space","dock.cockpit":"Cockpit","dock.code":"Code","dock.design":"Design","dock.tasks":"Aufgaben","dock.more":"Mehr","dock.graph":"Graph","dock.branches":"Branches","dock.memory":"Speicher","dock.meeting":"Meetings","dock.console":"Konsole","dock.orchestrator":"Orchestrator" },
    zh: { "dock.office":"工作区","dock.cockpit":"驾驶舱","dock.code":"代码","dock.design":"设计","dock.tasks":"任务","dock.more":"更多","dock.graph":"图谱","dock.branches":"分支","dock.memory":"记忆","dock.meeting":"会议","dock.console":"控制台","dock.orchestrator":"编排器" },
    ja: { "dock.office":"オープンスペース","dock.cockpit":"コックピット","dock.code":"コード","dock.design":"デザイン","dock.tasks":"タスク","dock.more":"その他","dock.graph":"グラフ","dock.branches":"ブランチ","dock.memory":"メモリ","dock.meeting":"会議","dock.console":"コンソール","dock.orchestrator":"オーケストレーター" }
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

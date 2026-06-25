"""Outils TEXTE du Swarm : sélection d'outils par pertinence, récupération de tool-calls
écrits en texte, détection d'intention annoncée, chargement des skills dynamiques.

Fonctions PURES (sans état du Swarm) extraites de l'ancien `core/swarm.py`. Les tables
de groupes-domaine (`_TOOL_GROUPS`/`_TOOL_GROUP_KEYWORDS`/`_TOOL_DOMAIN`) vivent ici car
elles servent à la fois à `select_tool_subset` et au moteur (qui les importe).
"""
import glob
import importlib.util
import json
import os

# ── Filtrage d'outils par pertinence (économie de tokens) ──────────────────────
# Les schémas des ~47 outils pèsent ~5 000 tokens RÉ-ENVOYÉS à chaque tour. La plupart
# des requêtes n'en utilisent que 0–2. On range les outils « lourds et spécialisés » en
# GROUPES-DOMAINE activés par mots-clés ; tout outil HORS groupe (mémoire, infos de base,
# planification, orchestration, skills dynamiques, MCP, transfer_/delegate_) reste TOUJOURS
# exposé. Principe de sûreté : on ne RETIRE qu'un outil explicitement rangé dans un groupe
# NON activé → jamais de coupe d'un outil cœur ou inconnu.
_TOOL_GROUPS = {
    "code": {
        "execute_python_code", "execute_bash_command", "read_file", "write_file",
        "edit_file", "apply_patch", "run_checks", "run_tests", "request_code_review",
        "remember_project_note", "search_code", "find_definition",
        "find_references", "file_outline", "git_status", "git_diff", "git_log",
        "git_create_branch", "git_commit", "git_create_worktree", "git_list_worktrees",
        "git_remove_worktree", "run_rigid_pipeline", "list_ssh_hosts",
    },
    "domotique": {"get_ha_state", "call_ha_service", "get_current_room", "trigger_workflow"},
    "web": {"web_search", "web_scrape", "render_page", "deep_research"},
    "media": {"generate_image", "generate_artistic_image", "generate_artistic_video"},
    "agenda": {"add_calendar_event", "list_calendar_events", "delete_calendar_event",
               "add_list_item", "get_list_items", "toggle_list_item", "delete_list_item"},
    "email": {"read_inbox", "read_email", "create_email_draft", "search_emails",
              "mark_emails_read", "archive_emails", "clean_inbox", "list_mail_folders"},
    "documents": {"analyze_document", "transcribe_and_summarize_meeting", "ingest_file"},
    "nextcloud": {"nextcloud_list_files", "nextcloud_read_file", "nextcloud_write_file",
                  "nextcloud_delete_file", "nextcloud_list_tasks", "nextcloud_search_contacts"},
    "redaction": {"document_open", "document_read", "document_revise", "document_publish",
                  "document_autorevise", "document_check_coherence", "document_translate", "document_check_repetitions"},
    "skills": {"delete_skill"},  # save_new_skill : hors groupe → jamais filtré (créer un outil à tout moment)
    "computer": {"computer_use_action"},
    "vision": {"analyze_image", "capture_screen", "ocr_image", "ocr_document"},
    "routines": {"create_routine", "list_routines"},
    "proxmox": {"proxmox_status", "proxmox_vm_action", "proxmox_vm_exec", "proxmox_vm_logs"},
    "transport": {"get_driving_route", "get_traffic_incidents"},
    "n8n": {"trigger_workflow", "list_n8n_workflows", "get_n8n_workflow", "get_n8n_executions",
            "run_n8n_workflow", "set_n8n_workflow_active", "create_n8n_workflow",
            "update_n8n_workflow", "delete_n8n_workflow"},
}
_TOOL_GROUP_KEYWORDS = {
    "code": ["code", "cod", "programme", "programm", "script", "python", "javascript", "bug",
             "fonction", "function", "fichier", "file", "git", "commit", "refactor", "compil",
             "erreur", "debug", "débug", "dépôt", "repo", "classe", "class", "variable",
             "lint", "patch", "branche", "branch", "terminal", "bash", "shell", "déploie",
             "ssh", "serveur", "server", "vm", "hôte", "host", "machine", "distant", "remote",
             "connecte", "connecte-toi", "connexion", "connecter", "nas", "openmediavault", "omv",
             "synology", "raspberry", "raspberrypi", "proxmox", "docker"],
    "domotique": ["lumière", "lumiere", "lampe", "allume", "éteins", "eteins", "chauffage",
                  "volet", "prise", "salon", "chambre", "cuisine", "maison", "home assistant",
                  "thermostat", "scène", "scene", "domotique", "radiateur", "store", "interrupteur"],
    "proxmox": ["proxmox", "vm", "machine virtuelle", "hyperviseur", "lxc", "conteneur",
                "container", "cluster", "nœud", "noeud", "qemu", "pve", "vmid", "redémarre la vm",
                "démarre la vm", "arrête la vm", "hôte", "host"],
    "n8n": ["n8n", "workflow", "automatisation", "automatise", "automatiser", "webhook",
            "scénario", "scenario", "no-code", "nocode", "zapier", "make.com", "intégration",
            "déclencheur", "declencheur", "trigger", "pipeline"],
    "web": ["cherche", "recherche", "web", "internet", "google", "actualité", "actualite",
            "approfondi", "approfondie", "deep", "état de l'art", "etat de l'art", "compare", "comparer", "dossier",
            "news", "nouvelle", "site", "url", "http", "lien", "en ligne", "scrape"],
    "media": ["image", "dessine", "dessin", "photo", "illustration", "vidéo", "video", "logo",
              "picture", "génère une image", "genere une image", "affiche"],
    "agenda": ["agenda", "calendrier", "rendez-vous", "rdv", "événement", "evenement", "réunion",
               "reunion", "liste", "courses", "tâche", "tache", "todo", "to-do", "rappelle",
               "planifie", "planning", "échéance", "deadline"],
    "email": ["mail", "email", "e-mail", "courriel", "inbox", "boîte", "boite",
              "brouillon", "messagerie", "archive", "archiver", "ménage", "menage",
              "newsletter", "spam", "publicité", "publicite", "non lus", "non-lus",
              "promotion", "promotions", "réseaux sociaux", "reseaux sociaux"],
    "documents": ["document", "pdf", "résume ce", "resume ce", "analyse ce", "compte rendu",
                  "compte-rendu", "transcris", "transcription", "ingère", "ingere"],
    "nextcloud": ["nextcloud", "webdav", "carddav", "contact", "carnet d'adresses", "fichier nextcloud",
                  "mon cloud", "drive perso"],
    "redaction": ["roman", "chapitre", "manuscrit", "docx", "document word", ".docx", "réviser",
                  "reviser", "relire", "relis", "réécris", "reecris", "corrige le", "corrige mon",
                  "modifications suivies", "révision", "revision", "mon document", "mon texte",
                  # cohérence + répétitions + traduction (sinon ces demandes n'exposent pas les outils)
                  "cohérence", "coherence", "incohérence", "incoherence", "répétition", "repetition",
                  "répétitions", "repetitions", "traduis", "traduire", "traduction", "translate",
                  "en anglais", "en espagnol", "en allemand", "en italien"],
    "skills": ["compétence", "competence", "skill", "nouvel outil", "apprends à"],
    "computer": ["souris", "clic", "navigateur", "navigue", "site web", "clique sur"],
    "vision": ["image", "photo", "capture", "capture d'écran", "screenshot", "écran", "ecran",
               "vois-tu", "que vois", "regarde l'image", "regarde cette image", "lis l'image",
               "analyse l'image", "analyse cette image", "sur l'image", "cette image", "visuel",
               # OCR : extraction de texte d'une image/PDF scanné
               "ocr", "scan", "scanné", "scanne", "numérisé", "extrais le texte", "extrait le texte",
               "lis le document", "lis ce document", "transcris", "transcription", "texte de l'image",
               "facture", "reçu", "recu", "ticket", "carte d'identité", "document scanné"],
    "routines": ["routine", "routines", "chaque matin", "tous les matins", "chaque jour",
                 "tous les jours", "chaque semaine", "rappel récurrent", "automatise", "périodique",
                 "programme une tâche", "planifie tous les", "récurrent"],
    "transport": ["voiture", "route", "autoroute", "trajet", "temps de trajet", "en combien de temps",
                  "embouteillage", "embouteillages", "bouchon", "bouchons", "circulation", "trafic",
                  "accident de la route", "travaux", "péage", "peage", "gps", "conduire", "rouler",
                  "itinéraire", "itineraire", "km", "kilomètres"],
}
# Index inversé nom→groupe (un outil n'est dans qu'un seul groupe).
_TOOL_DOMAIN = {name: grp for grp, names in _TOOL_GROUPS.items() for name in names}

_INTENT_MARKERS = (
    "je vais", "je lance", "laisse-moi", "laisse moi", "je m'en occupe", "je men occupe",
    "un instant", "je vérifie", "je verifie", "je récupère", "je recupere", "je consulte",
    "je regarde", "permets-moi", "permet moi", "je commence", "je procède", "je procede",
    "je m'occupe", "je te prépare", "je prepare", "c'est parti", "tout de suite")
_ASK_USER_MARKERS = (
    "veux-tu", "veux tu", "souhaites-tu", "souhaites tu", "dois-je", "dois je",
    "préfères-tu", "preferes-tu", "tu veux que", "tu préfères", "je te propose",
    "puis-je", "puis je", "est-ce que tu veux")
# Marqueurs de COMPTE-RENDU : l'action est DÉJÀ faite (le résultat est dans le message).
# Si présents, ce n'est pas une intention à relancer → pas d'auto-continuation (anti-relance
# d'un « voici ce que j'ai trouvé… » que le modèle prend pour une annonce future).
_DONE_MARKERS = (
    "voici", "voilà", "voila", "j'ai trouvé", "j'ai trouve", "j'ai terminé", "j'ai termine",
    "j'ai fait", "c'est fait", "terminé", "fait :", "résultat :", "resultat :", "en résumé",
    "en resume", "voici ce que", "voici les", "voici le", "j'ai récupéré", "j'ai recupere",
    "j'ai consulté", "j'ai consulte", "j'ai vérifié", "j'ai verifie")


def looks_like_announced_intent(content: str) -> bool:
    """Vrai si le message ANNONCE une action (« je vais… ») SANS poser de question à l'utilisateur.
    Sert à l'auto-continuation : on relance l'agent pour qu'il EXÉCUTE au lieu de rendre la main.
    On respecte les demandes d'avis/approbation (présence d'une question → False)."""
    msg = (content or "").strip()
    if not msg or len(msg) > 600:
        return False
    low = msg.lower()
    if "?" in msg or any(p in low for p in _ASK_USER_MARKERS):
        return False
    # Compte-rendu d'une action DÉJÀ faite (« voici ce que j'ai trouvé… ») → pas une intention
    # future à relancer : on s'abstient (sinon on relance une action déjà exécutée).
    if any(p in low for p in _DONE_MARKERS):
        return False
    return any(p in low for p in _INTENT_MARKERS)


def select_tool_subset(text: str, available_names) -> set:
    """Renvoie le sous-ensemble de noms d'outils à EXPOSER pour cette requête.
    On active les groupes-domaine dont un mot-clé apparaît dans `text` ; on conserve
    TOUJOURS les outils hors groupe. Voir _TOOL_GROUPS pour le détail/sûreté."""
    text_l = (text or "").lower()
    active = {g for g, kws in _TOOL_GROUP_KEYWORDS.items() if any(k in text_l for k in kws)}
    keep = set()
    for name in available_names:
        grp = _TOOL_DOMAIN.get(name)
        if grp is None or grp in active:
            keep.add(name)
    return keep


def select_relevant_funcs(text, funcs, top_n):
    """Top-N fonctions les plus PERTINENTES pour `text`, par recouvrement de tokens sur
    (nom + 1re ligne de docstring). Utilisé pour borner les outils « extra » non groupés
    (skills auto-induites + outils MCP, souvent 20-50 par serveur) sans gonfler le contexte.
    Sans embedding : zéro coût/latence, déterministe. Les fonctions sans recouvrement
    gardent un score 0 et sont départagées par leur ordre d'origine (tri stable)."""
    import re
    _word = re.compile(r"[a-zà-ÿ0-9_]{3,}", re.IGNORECASE)
    def _toks(s):
        return {w.lower() for w in _word.findall(s or "")}
    q = _toks(text)
    scored = []
    for i, f in enumerate(funcs):
        name = getattr(f, "__name__", "")
        head = (getattr(f, "__doc__", "") or "").strip().split("\n", 1)[0]
        # le nom (mots dé-soulignés) compte double : signal fort de pertinence.
        score = len(q & _toks(name + " " + head)) + len(q & _toks(name.replace("_", " ")))
        scored.append((-score, i, f))
    scored.sort()
    # On ne garde que les fonctions RÉELLEMENT pertinentes (recouvrement > 0). Avant, on
    # « comblait » le top-N avec des outils sans rapport (ex. 12 outils Home Assistant exposés
    # pour une requête « calendrier » → l'agent partait sur HA). Rien ne matche ⇒ liste vide.
    return [f for negscore, _, f in scored if negscore < 0][:top_n]


def load_dynamic_skills() -> dict:
    """Charge dynamiquement tous les scripts Python du dossier skills/ comme des fonctions."""
    skills = {}
    if not os.path.exists("skills"):
        return skills
    for file_path in glob.glob("skills/*.py"):
        file_name = os.path.basename(file_path)
        skill_name = file_name.replace(".py", "")
        try:
            # Importation dynamique
            spec = importlib.util.spec_from_file_location(skill_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Récupère la fonction qui porte le même nom que le fichier
            func = getattr(module, skill_name, None)
            if func:
                skills[skill_name] = func
        except Exception as e:
            print(f"[\033[91mErreur Skill\033[0m] Impossible de charger {file_name} : {e}")
    return skills


class _TextToolCallFunc:
    """Fonction d'un tool_call SYNTHÉTIQUE (récupéré depuis du texte). Même interface
    que les tool_calls structurés de litellm/OpenAI : .name + .arguments (str JSON)."""
    __slots__ = ("name", "arguments")
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _TextToolCall:
    __slots__ = ("id", "type", "function")
    def __init__(self, name: str, arguments: str, idx: int):
        self.id = f"call_text_{idx}"
        self.type = "function"
        self.function = _TextToolCallFunc(name, arguments)


def _loads_lenient(raw):
    """json.loads TOLÉRANT : répare les fautes fréquentes des LLM (virgules traînantes,
    littéraux Python None/True/False, quotes simples). Renvoie l'objet ou None."""
    try:
        return json.loads(raw)
    except Exception:
        pass
    import re as _re
    s = (raw or "").strip()
    s = _re.sub(r",\s*([}\]])", r"\1", s)                      # virgules traînantes
    s = _re.sub(r"\bNone\b", "null", s)
    s = _re.sub(r"\bTrue\b", "true", s)
    s = _re.sub(r"\bFalse\b", "false", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    if '"' not in s and "'" in s:                              # quotes simples → doubles
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            pass
    return None


def parse_text_tool_calls(content: str, valid_names) -> list:
    """RÉCUPÈRE les appels d'outils écrits en TEXTE par le modèle (qwen3 & co. émettent
    parfois le tool-call dans le contenu — bloc ```json, balise <tool_call>… — au lieu du
    format structuré, et l'outil n'est alors jamais exécuté). Renvoie une liste d'objets
    tool_call synthétiques (compatibles avec la boucle), ou [].

    Garde-fou anti faux-positif : on n'accepte QUE des appels dont le nom correspond à un
    outil RÉELLEMENT disponible — sinon le modèle montre peut-être juste du JSON à l'usager.
    """
    if not content or not valid_names:
        return []
    import re as _re
    valid = set(valid_names)
    candidates = []
    # 1) Balises <tool_call>{…}</tool_call> (style Hermes/Qwen).
    candidates += _re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, _re.DOTALL)
    # 2) Blocs de code ```json … ``` / ```tool_call … ``` (objet ou liste).
    candidates += _re.findall(r"```(?:json|tool_call|tool)?\s*(\[.*?\]|\{.*?\})\s*```", content, _re.DOTALL)
    # 3) Repli : le contenu entier est peut-être un JSON nu.
    _stripped = content.strip()
    if not candidates and (_stripped.startswith("{") or _stripped.startswith("[")):
        candidates.append(_stripped)

    out = []
    for raw in candidates:
        data = _loads_lenient(raw)
        if data is None:
            continue
        for it in (data if isinstance(data, list) else [data]):
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("tool") or it.get("tool_name")
            args = it.get("arguments")
            if args is None:
                args = it.get("args") or it.get("parameters") or it.get("tool_input") or it.get("input")
            # Style OpenAI imbriqué : {"function": {"name": …, "arguments": …}}.
            fn = it.get("function")
            if isinstance(fn, dict):
                name = name or fn.get("name")
                if args is None:
                    args = fn.get("arguments")
            if args is None:
                args = {}
            if not name or name not in valid:
                continue
            if isinstance(args, str):
                args_str = args
            else:
                try:
                    args_str = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_str = "{}"
            out.append(_TextToolCall(name, args_str, len(out) + 1))
        if out:
            break  # un bloc valide suffit

    # Repli : appel « style Python » écrit en texte — outil({...}) ou outil()
    # ou outil(key="value", key2=123).
    # On n'accepte qu'un nom d'outil RÉELLEMENT disponible (anti faux-positif).
    if not out:
        # 1) outil({json}) ou outil()
        for m in _re.finditer(r"\b([a-zA-Z_]\w*)\s*\(\s*(\{.*?\})?\s*\)", content, _re.DOTALL):
            name = m.group(1)
            if name not in valid:
                continue
            data = _loads_lenient(m.group(2) or "{}")
            if not isinstance(data, dict):
                continue
            try:
                args_str = json.dumps(data, ensure_ascii=False)
            except Exception:
                args_str = "{}"
            out.append(_TextToolCall(name, args_str, len(out) + 1))
            break
    if not out:
        # 2) outil(key="value", key2=123) — kwargs Python
        for m in _re.finditer(r"\b([a-zA-Z_]\w*)\s*\(([^)]+)\)", content, _re.DOTALL):
            name = m.group(1)
            if name not in valid:
                continue
            raw_args = m.group(2).strip()
            # Parser les kwargs Python : key="val", key2='val2', key3=123, key4=True
            kwargs = {}
            for kv in _re.finditer(
                    r"""([a-zA-Z_]\w*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([\w.+-]+))""",
                    raw_args):
                k = kv.group(1)
                v = kv.group(2) if kv.group(2) is not None else (
                    kv.group(3) if kv.group(3) is not None else kv.group(4))
                # Conversion des types basiques
                if v is not None:
                    vl = v.lower()
                    if vl == "true":
                        v = True
                    elif vl == "false":
                        v = False
                    elif vl == "none" or vl == "null":
                        v = None
                    else:
                        try:
                            v = int(v)
                        except (ValueError, TypeError):
                            try:
                                v = float(v)
                            except (ValueError, TypeError):
                                pass
                kwargs[k] = v
            if kwargs:
                try:
                    args_str = json.dumps(kwargs, ensure_ascii=False)
                except Exception:
                    args_str = "{}"
                out.append(_TextToolCall(name, args_str, len(out) + 1))
                break
    return out


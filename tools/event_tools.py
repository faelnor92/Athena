"""Outils Vigie : Athena peut configurer la surveillance proactive et lire le journal.

La supervision elle-même est PILOTÉE PAR ÉVÉNEMENT (sources externes qui poussent sur
POST /api/events) — ces outils ne font que régler/consulter, ils ne lancent aucune boucle.
"""
import core.events as events


def configure_monitoring(enabled: bool = None, min_severity: str = None,
                         auto_investigate: bool = None, telegram_chat_id: str = None) -> str:
    """
    Configure la surveillance proactive (agent Vigie). Tout est optionnel ; seuls les champs
    fournis sont modifiés.

    Args:
        enabled (bool): activer/désactiver la réaction aux événements.
        min_severity (str): seuil minimal traité — "info", "warning" ou "critical".
        auto_investigate (bool): autoriser le Vigie à investiguer avec des outils (sinon il
            se contente d'analyser et d'alerter).
        telegram_chat_id (str): chat Telegram destinataire des alertes et des validations.
    Returns:
        str: état de la configuration après mise à jour.
    """
    updates = {}
    if enabled is not None:
        updates["enabled"] = bool(enabled)
    if min_severity is not None:
        ms = str(min_severity).strip().lower()
        if ms not in ("info", "warning", "critical"):
            return "Erreur : min_severity doit être info, warning ou critical."
        updates["min_severity"] = ms
    if auto_investigate is not None:
        updates["auto_investigate"] = bool(auto_investigate)
    if telegram_chat_id is not None:
        updates["telegram_chat_id"] = str(telegram_chat_id).strip()
    cfg = events.set_config(updates) if updates else events.config()
    return (f"Surveillance proactive : {'ACTIVÉE' if cfg['enabled'] else 'désactivée'} ; "
            f"seuil = {cfg['min_severity']} ; investigation auto = {cfg['auto_investigate']} ; "
            f"alertes Telegram = {'oui' if cfg['telegram_chat_id'] else 'non'}. "
            "Les sources (Zabbix/Grafana/HA/SNMP) poussent sur POST /api/events.")


def list_recent_events(limit: int = 10) -> str:
    """Liste les derniers événements de supervision reçus (et leur statut de traitement)."""
    evs = events.recent()[: max(1, min(limit, 50))]
    if not evs:
        return "Aucun événement de supervision récent."
    out = []
    for e in evs:
        out.append(f"[{e.get('severity')}] {e.get('type')} / {e.get('source')} — "
                   f"{(e.get('message') or '')[:120]} ({e.get('status')})")
    return "Événements récents :\n" + "\n".join(out)

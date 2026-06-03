# Conscience spatiale (optionnel)

Athena peut agir sur **la pièce où tu te trouves** (suivre ta voix, régler le chauffage
de la bonne pièce, déclencher le transfert de musique). C'est **désactivé par défaut** :
si tu n'as pas de détection de présence, rien ne change.

> Principe : **Home Assistant** est la source de vérité de ta position (il fait ça très
> bien). Athena se contente de **lire** une entité HA qui indique la pièce courante.
> Athena ne fait PAS de calcul Bluetooth lui-même (le RSSI brut est trop bruité).

## 1. Mettre en place la détection de pièce dans Home Assistant

Choisis UNE approche :

### Option A — mmWave par pièce (recommandé, le plus fiable)
Un capteur de présence à ondes mmWave par pièce (ex. **Aqara FP2**, ou un **LD2410**
sur un ESP32 via ESPHome). Présence instantanée, précise, **sans rien porter sur toi**.

Crée ensuite un capteur HA « pièce courante » (template) qui renvoie le nom de la pièce
occupée la plus récemment, par ex. dans `configuration.yaml` :

```yaml
template:
  - sensor:
      - name: "Pièce actuelle"
        unique_id: piece_actuelle
        state: >
          {% if is_state('binary_sensor.presence_salon','on') %} salon
          {% elif is_state('binary_sensor.presence_cuisine','on') %} cuisine
          {% elif is_state('binary_sensor.presence_bureau','on') %} bureau
          {% else %} {{ states('sensor.piece_actuelle') }} {% endif %}
```

### Option B — BLE avec ESPresense / Bermuda (réutilise tes ESP32)
Tu portes une balise (montre, porte-clés BLE, téléphone) et tes ESP32 servent de
récepteurs. Installe **ESPresense** sur les ESP et l'intégration **Bermuda** (ou
ESPresense) dans HA. Elle expose un capteur de zone/pièce.
⚠️ Plus bruité : garde une **temporisation** (rester quelques secondes dans une pièce
avant de basculer) pour éviter le clignotement.

> ❌ L'IP / le device_tracker du téléphone ne donne que **présent/absent de la maison**,
> pas la pièce — inutilisable pour le follow-me.

## 2. Activer côté Athena

Dans ⚙️ Réglages → Comportement & Sécurité → **Présence / follow-me** :

- **Entité HA de pièce courante** = l'entité créée à l'étape 1 (ex. `sensor.piece_actuelle`).
  (équivaut à `PRESENCE_ENTITY=sensor.piece_actuelle` dans `.env`)

Puis, pour chaque satellite vocal (⚙️ Réglages → Satellites), renseigne sa **pièce
(`area`)** — elle doit correspondre aux valeurs renvoyées par l'entité de présence
(`salon`, `cuisine`…). C'est ce qui permettra de router la voix vers le bon satellite.

## 3. Ce qu'Athena peut alors faire

- **Savoir où tu es** : l'outil `get_current_room` lit l'entité de présence.
- **Agir sur la bonne pièce** : « augmente le chauffage » → Athena cible la clim de ta
  pièce actuelle via `call_ha_service`.

Coche l'outil **📍 Présence : Pièce actuelle** sur les agents concernés.

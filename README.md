# AWEKAS Weather Station for Home Assistant

Custom Integration zur Einbindung von Wetterdaten und lückenlosen Niederschlagsakkumulationen der **AWEKAS Weather Station** in Home Assistant.

Diese Integration nutzt das native `UtilityMeterSensor`-Framework von Home Assistant, um Niederschlagswerte auch über Systemneustarts hinweg stabil, fehlertolerant und LTS-konform (Long-Term Statistics) aufzuzeichnen.

---

## Features

* 🌧️ **Präzise Niederschlagsmessung:** Robuste Erfassung von Tages-, Monats- und Jahresniederschlägen (`mm`).
* 🔄 **Nahtlose Resets:** Automatischer Zurücksetz-Zyklus mit `periodically_resetting=True`.
* 💾 **Persistenz & LTS-Ready:** Schutz vor Datenverlusten bei ungraceful Shutdowns und volle Kompatibilität mit den Home Assistant Langzeitstatistiken.
* 🛡️ **Defensive Boot-Logik:** Verhindert `unavailable`- oder `unknown`-Zustände beim Systemstart durch gezielte Initialisierung.

---

## Installation via HACS (Benutzerdefiniertes Repository)

1. Öffne **HACS** in deiner Home Assistant Instanz.
2. Gehe auf **Integrationen**.
3. Klicke oben rechts auf die **drei Punkte (`⋮`)** und wähle **Benutzerdefinierte Repositories**.
4. Trage die URL dieses GitHub-Repositories ein:
   `https://github.com/xpertsavenue/ha_awekas_weather`
5. Wähle als Kategorie **Integration** und klicke auf **Hinzufügen**.
6. Suche nach **AWEKAS Weather Station**, klicke auf **Herunterladen** und starte Home Assistant neu.

---

## Konfiguration

1. Gehe in Home Assistant zu **Einstellungen** > **Geräte & Dienste**.
2. Klicke unten rechts auf **Integration hinzufügen**.
3. Suche nach **AWEKAS Weather** und folge den Anweisungen auf dem Bildschirm (Eingabe deiner AWEKAS API-Zugangsdaten).

---

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE).
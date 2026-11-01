# AWEKAS Weather Station for Home Assistant

[![Validate](https://github.com/xpertsavenue/ha_awekas_weather/actions/workflows/validate.yml/badge.svg)](https://github.com/xpertsavenue/ha_awekas_weather/actions/workflows/validate.yml)
[![Tests](https://github.com/xpertsavenue/ha_awekas_weather/actions/workflows/tests.yml/badge.svg)](https://github.com/xpertsavenue/ha_awekas_weather/actions/workflows/tests.yml)

Custom Integration zur Einbindung der aktuellen Messwerte, Tagesstatistiken und der Wettervorhersage einer **AWEKAS-Wetterstation** in Home Assistant.

---

## Features

* 🌡️ **Messwerte:** Temperatur, Feuchte, Luftdruck, Wind, Niederschlag, Strahlung, Helligkeit, Sonnenscheindauer, Luftqualität und die Zusatzkanäle der Station (Bodentemperatur, Bodenfeuchte, Blattnässe). Sensoren, die deine Station laut AWEKAS nicht hat, werden deaktiviert angelegt.
* 📅 **Tagesstatistiken:** Min/Max-Werte des Tages mit Uhrzeit als Attribut, Feinstaub als 24-Stunden-Mittel (standardmäßig deaktiviert).
* 🌦️ **Wetter-Entity:** Aktuelles Wetter aus dem Wetterbericht der Station und 6-Tage-Vorhersage (mit AWEKAS Stationsweb-Abo). Die Position der Station wird auf der Karte angezeigt.
* 🌧️ **Monats- und Jahresniederschlag:** Summiert den Tagesniederschlag der Station. Monat und Jahr wechseln nach der Ortszeit der Station. Die Summen bleiben über Neustarts erhalten und sind für die Langzeitstatistik geeignet.
* 🏷️ **Gerät mit Stationsdaten:** Standort als Name, Hardware, Software und Link zur Stationswebseite.
* 🩺 **Diagnose:** Zeitpunkt der letzten Messung und Ablaufdatum des Stationsweb-Abos. Lädt die Station eine Stunde lang keine Daten hoch, werden die Messwerte als nicht verfügbar angezeigt.
* 🔑 **Re-Authentifizierung**, wenn der API-Schlüssel abläuft.
* ⏱️ **Abfrage jede Minute** (die API erlaubt 240 pro Stunde). Ist das Kontingent erschöpft, pausieren die Abfragen für 15 Minuten.

## Aktion: Niederschlagssumme setzen

Mit `awekas_weather.set_precipitation_total` setzt du den **Monats- oder Jahresniederschlag** nachträglich auf einen Wert, zum Beispiel nach einer Neuinstallation oder wenn eine Messung gefehlt hat. Die Summe läuft ab diesem Wert weiter, Regen, den die Station schon gemeldet hat, wird nicht noch einmal addiert.

Du findest die Aktion unter *Entwicklerwerkzeuge → Aktionen*:

```yaml
action: awekas_weather.set_precipitation_total
target:
  entity_id: sensor.vielau_niederschlag_monat
data:
  value: 42.5   # Millimeter
```

**Hinweis zur Langzeitstatistik:** Home Assistant wertet eine Erhöhung der Summe in der Statistik als Regen, der in diesem Moment gefallen ist. Setzt du den Jahreswert von 1,2 auf 50 mm, zeigt die Statistik für diese Stunde 48,8 mm Niederschlag. Willst du die Statistik ebenfalls korrigieren, geht das unter *Entwicklerwerkzeuge → Statistiken → Summe anpassen*.

## Voraussetzungen

* **AWEKAS Plus** muss in deinem AWEKAS-Benutzerprofil aktiviert sein, sonst liefert die API keine Daten.
* Den **API-Schlüssel** findest du in deinem AWEKAS-Benutzerprofil.
* Die **Wettervorhersage** gibt es nur mit aktivem AWEKAS Stationsweb-Abo.

---

## Installation via HACS (Benutzerdefiniertes Repository)

1. Öffne **HACS** in deiner Home Assistant Instanz.
2. Klicke oben rechts auf die **drei Punkte (`⋮`)** und wähle **Benutzerdefinierte Repositories**.
3. Trage die URL dieses GitHub-Repositories ein:
   `https://github.com/xpertsavenue/ha_awekas_weather`
4. Wähle als Kategorie **Integration** und klicke auf **Hinzufügen**.
5. Suche nach **AWEKAS Weather Station**, klicke auf **Herunterladen** und starte Home Assistant neu.

---

## Konfiguration

1. Gehe in Home Assistant zu **Einstellungen** > **Geräte & Dienste**.
2. Klicke unten rechts auf **Integration hinzufügen**.
3. Suche nach **AWEKAS Weather** und gib deinen API-Schlüssel ein.

### Parameter der Einrichtung

| Feld | Pflicht | Beschreibung |
|---|---|---|
| **API-Schlüssel** | ja | Der API-Zugangsschlüssel aus deinem AWEKAS-Benutzerprofil. Du kannst ihn so einfügen, wie AWEKAS ihn anzeigt, auch mit Zeichen wie `%2B`. Im Profil muss **AWEKAS Plus** aktiviert sein. |

Beim Speichern ruft die Integration die AWEKAS-API auf. Meldet sie einen Fehler, erscheint er im Formular:

| Meldung | Bedeutung |
|---|---|
| Ungültige Authentifizierung | AWEKAS lehnt den API-Schlüssel ab. |
| AWEKAS plus nicht aktiviert | Aktiviere AWEKAS Plus in deinem Benutzerprofil. |
| Kontingent aufgebraucht | Du hast die erlaubten Abfragen (240 pro Stunde) erreicht. Versuche es später erneut. |
| Verbindung fehlgeschlagen | Die API ist nicht erreichbar. |

Jede Wetterstation lässt sich nur einmal einrichten, auch mit einem anderen API-Schlüssel.

---

## Integration entfernen

1. Gehe zu **Einstellungen** > **Geräte & Dienste** und öffne **AWEKAS Weather**.
2. Klicke neben dem Eintrag auf die **drei Punkte (`⋮`)** und wähle **Löschen**.
   Das Gerät und alle Entitäten werden entfernt. **Auch die gespeicherten Monats- und Jahressummen des Niederschlags gehen dabei verloren.**
3. Wenn du die Integration über HACS installiert hast, öffne sie dort, wähle **Entfernen** und starte Home Assistant neu.

Die bereits aufgezeichneten Langzeitstatistiken bleiben in der Datenbank. Du kannst sie unter **Entwicklerwerkzeuge** > **Statistiken** löschen.

---

## Entwicklung

Die Entwicklungsumgebung ist ein VS Code Dev Container mit Home Assistant, siehe [.devcontainer/README.md](.devcontainer/README.md).

```bash
pytest                      # Tests
ruff check . && ruff format --check .   # Lint
```

---

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE).

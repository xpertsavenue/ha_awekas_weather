# Changelog

## 1.3.0 – 2026-11-01

Große Überarbeitung: Die Integration nutzt jetzt die komplette AWEKAS-API (Version 2.1), korrigiert mehrere Fehler bei Einheiten und Zählern und kommt mit Tests.

**Voraussetzungen:** Home Assistant 2026.6.0 oder neuer. In deinem AWEKAS-Benutzerprofil muss **AWEKAS Plus** aktiviert sein.

### ⚠️ Wichtig beim Update

- **Das Update läuft automatisch.** Deine Einträge werden migriert, Entitäten und Entity-IDs bleiben erhalten. Auch die gespeicherten Monats- und Jahressummen des Niederschlags werden übernommen. Mach vorher ein Backup.
- **Anzeigenamen ändern sich.** Das Gerät heißt jetzt wie der Standort deiner Station (z. B. „Vielau“) statt „AWEKAS Weather“. Eigene Namen, die du vergeben hast, bleiben unverändert.
- **Statistik-Hinweis möglich.** Weil sich bei einigen Sensoren Einheit oder Statistik-Art ändern (Bodenfeuchte, Windrichtung, Niederschlag der letzten Stunde bzw. 24 Stunden), kann Home Assistant unter *Entwicklerwerkzeuge → Statistiken* einen Hinweis anzeigen. Dort lässt er sich mit einem Klick beheben.
- **Die Sprachauswahl ist entfallen.** Sie wirkte nur auf Vorhersagetexte, die die Integration nie angezeigt hat.

### Neu

- **Aktion `awekas_weather.set_precipitation_total`:** Setzt den Monats- oder Jahresniederschlag nachträglich auf einen Wert, z. B. nach einer Neuinstallation. Die Summe läuft ab diesem Wert weiter. Mehr dazu in der README.
- **Stationsdaten:** Das Gerät zeigt Standort, Hardware, Software und den Link zur Stationswebseite. Die Position der Station steht an der Wetter-Entity und erscheint auf der Karte.
- **Aktuelles Wetter aus dem Wetterbericht der Station,** nachts als „klare Nacht“. Ohne Bericht gilt weiterhin die Vorhersage von heute. Die Wetter-Entity zeigt zusätzlich Taupunkt und Windböen.
- **Diagnose-Sensoren:** Zeitpunkt der letzten Messung und Ablaufdatum des Stationsweb-Abos.
- **Veraltete Daten werden erkannt:** Lädt die Station eine Stunde lang nichts hoch, zeigen die Messwerte „nicht verfügbar“ statt eines alten Werts.
- **Neue Sensoren:** Feinstaub PM1, PM2.5 und PM10 als 24-Stunden-Mittel (standardmäßig deaktiviert).
- **Uhrzeit der Tageswerte:** Die Min/Max-Sensoren der Tagesstatistik zeigen im Attribut `timestamp`, wann der Wert erreicht wurde.
- **Sensoren passend zur Station:** Anhand der Sensorliste von AWEKAS werden nur die Sensoren aktiviert, die deine Station wirklich hat. Alle anderen werden deaktiviert angelegt.
- **Eigene Meldung bei fehlendem AWEKAS Plus** statt einer allgemeinen Verbindungsstörung.
- **Einrichtung:** Jede Wetterstation lässt sich nur einmal einrichten, auch mit einem anderen API-Schlüssel. Bei der Neu-Anmeldung wird geprüft, dass der neue Schlüssel zur selben Station gehört. Das Eingabefeld für den Schlüssel ist ein Passwortfeld.

### Geändert

- **Abfrage jede Minute** statt alle 30 Sekunden. Ist das Kontingent des API-Schlüssels erschöpft, pausieren die Abfragen 15 Minuten.
- **Monats- und Jahresniederschlag** sind jetzt eigene Summen-Sensoren statt Verbrauchszähler. Sie wechseln nach der Ortszeit der Station und überstehen Neustarts.
- **Windgeschwindigkeiten** verwenden die Einheit **km/h**, wie AWEKAS sie liefert. Home Assistant rechnet bei Bedarf um.
- **Einheiten:** Bodenfeuchte in **cbar**, Helligkeit in **lx**, Sonnenscheindauer in **h**.
- **Statistik-Arten:** Windrichtungen werden als Winkel ausgewertet, Niederschlag der letzten Stunde bzw. 24 Stunden ist keine Summe mehr (er kann sinken).
- **Wettervorhersage:** Die Tage beginnen um Mitternacht Ortszeit. Alle Wettercodes von AWEKAS sind zugeordnet, unbekannte Codes ergeben keinen Zustand mehr. Die Vorhersage wird nur angeboten, wenn die Station eine hat (AWEKAS Stationsweb).
- **Fehlerbehandlung:** Meldungen der API werden genau unterschieden, Fehlertexte stehen auf Deutsch und Englisch zur Verfügung. Der API-Schlüssel taucht nicht mehr in Fehlermeldungen auf.

### Behoben

- **API-Schlüssel mit Sonderzeichen wurden abgelehnt.** AWEKAS gibt Schlüssel in URL-kodierter Form aus (z. B. `%2B`). Sie werden jetzt korrekt verarbeitet.
- **Geräte und Entitäten wurden doppelt angelegt,** wenn der API-Schlüssel bei einer Neu-Anmeldung ersetzt wurde.
- **Sensoren verschwanden aus der Registry,** wenn die API beim Start einmal keinen Wert lieferte. Auch Namen und Einstellungen gingen dabei verloren.
- **Die Wettervorhersage in Karten aktualisierte sich nicht.**

### Entwickler

- Neuer API-Client (`api.py`) und gemeinsame Basisklasse (`entity.py`).
- Tests mit `pytest-homeassistant-custom-component` und GitHub Actions (hassfest, HACS, Ruff, pytest).
- Dev Container: Pakete im Image, Home Assistant startet automatisch mit dem Container, Ports werden von Docker veröffentlicht, VS Code Tasks und Debug-Konfiguration.
- Quality Scale: Silber.

# TeddyCloud Runtime

Home-Assistant-Custom-Integration für lokale TeddyCloud-Installationen.

## Funktionen

- Einrichtung über die Home-Assistant-Oberfläche
- Unterstützung mehrerer Tonieboxen
- Frei konfigurierbare Regeln aus Custom-Tonie und TeddyCloud-Serie
- Rekursives Einlesen der vollständigen TAF-Bibliothek
- Exakte Laufzeitbestimmung aus Ogg/Opus-Daten
- Persistenter Laufzeit- und Wiedergabefortschritt
- Eigener Timer je Box, RUID, Audio-ID und Zufallsrunde
- Automatischer Folgenabschluss, sobald eine Box die Gesamtlaufzeit erreicht
- Zufällige Folgenauswahl ohne Wiederholung innerhalb einer Runde
- Automatische Zuweisung der nächsten TAF-Datei in TeddyCloud
- Sofortige Erstzuweisung, wenn ein konfigurierter Tonie noch eine Datei aus
  einer anderen Serie enthält

## Voraussetzungen und Datenquelle

TeddyCloud muss bereits mit einem MQTT-Broker verbunden sein. Die
Toniebox-Datenpunkte werden von TeddyCloud über MQTT übertragen und durch die
MQTT-Integration in Home Assistant als Entitäten bereitgestellt.

TeddyCloud Runtime erzeugt diese Toniebox-Entitäten nicht selbst und verbindet
sich auch nicht direkt mit den Tonieboxen. Die Integration verwendet die
bereits in Home Assistant vorhandenen MQTT-Entitäten für:

- aktuelle Audio-ID
- Wiedergabestatus
- aktuelle Tag-UID

Zusätzlich greift TeddyCloud Runtime über die konfigurierte lokale
TeddyCloud-Adresse auf Bibliothek, Metadaten und TAF-Dateien zu. Vor der
Einrichtung müssen die benötigten Toniebox-Entitäten deshalb unter
**Einstellungen → Geräte & Dienste → MQTT** in Home Assistant vorhanden sein.

## Installation über HACS

Das Repository ist derzeit nicht im offiziellen HACS-Standardkatalog
enthalten. Es kann aber als benutzerdefiniertes Repository hinzugefügt werden:

1. HACS in Home Assistant öffnen.
2. **Integrationen** auswählen.
3. Oben rechts das Menü mit den drei Punkten öffnen.
4. **Benutzerdefinierte Repositories** auswählen.
5. Als Repository
   `https://github.com/New-three/teddycloud-runtime` eintragen.
6. Als Kategorie **Integration** auswählen und mit **Hinzufügen** bestätigen.
7. In HACS nach **TeddyCloud Runtime** suchen und die Integration
   herunterladen.
8. Home Assistant vollständig neu starten.
9. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen und
   nach **TeddyCloud Runtime** suchen.

Für diese Installationsart muss HACS bereits in Home Assistant eingerichtet
sein.

## Manuelle Installation

1. Den Ordner `custom_components/teddycloud_runtime` nach
   `/config/custom_components/teddycloud_runtime` kopieren.
2. Home Assistant vollständig neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
4. Nach **TeddyCloud Runtime** suchen.
5. TeddyCloud-Adresse und die drei Sensoren der ersten Toniebox auswählen.

Die Beschreibung enthält bewusst keine Beispiel-IP. Verwendet wird immer die
Adresse der eigenen lokalen TeddyCloud.

Beim ersten Start analysiert die Integration alle gültigen TAF-Dateien der
Bibliothek. Dabei werden nur kleine HTTP-Bereiche der Audiodateien übertragen.
Die ermittelten Laufzeiten werden dauerhaft in Home Assistant gespeichert.

## Tonieboxen konfigurieren

Weitere Boxen werden unter
**Einstellungen → Geräte & Dienste → TeddyCloud Runtime → Konfigurieren**
hinzugefügt. Für jede Box werden folgende Werte benötigt:

- frei wählbarer Boxname
- Sensor der aktuellen Audio-ID
- Sensor des Wiedergabestatus
- Sensor der aktuellen Tag-UID

## Custom-Tonie-Regeln

Die Integration enthält keine voreingestellten Tonies oder Serien. Regeln
werden über **Konfigurieren → Custom-Tonie-Regel hinzufügen** angelegt.

Jede Regel besteht aus:

- frei wählbarer Regelname
- UID des physischen Custom-Tonies
- exakter Serienname aus den TeddyCloud-Custom-Metadaten

Neue Bibliotheksdateien mit demselben Seriennamen werden beim nächsten
Einlesen automatisch in die Zufallsauswahl aufgenommen.

### Beispiel für eine Serienregel

Dieses Beispiel ist keine Voreinstellung. Die Regel muss vom Nutzer selbst
angelegt und mit der UID des eigenen Custom-Tonies ausgefüllt werden.

1. **Einstellungen → Geräte & Dienste → TeddyCloud Runtime →
   Konfigurieren** öffnen.
2. **Custom-Tonie-Regel hinzufügen** auswählen.
3. Die Felder beispielsweise so ausfüllen:

   - Name: `Meine Serien-Zufallswiedergabe`
   - Tonie-UID: `AA:BB:CC:DD:EE:FF:00:11`
   - Serie: `Meine Beispielserie`

4. Die Beispiel-UID durch die tatsächliche UID des eigenen Custom-Tonies
   ersetzen.
5. Speichern und den Tonie auf eine konfigurierte Toniebox stellen.

Der Serienname muss exakt so geschrieben sein, wie er in den
TeddyCloud-Custom-Metadaten steht. Die Integration nimmt anschließend alle
vorhandenen und später ergänzten Custom-Folgen dieser Serie in die
Zufallsauswahl auf.

## Wiedergabeverhalten

`Playback=OFF` pausiert den Timer der betreffenden Box. Sobald eine Box die
vollständige Laufzeit erreicht, gilt die Folge für den Custom-Tonie global als
beendet. Die Integration weist ihm danach die nächste Folge zu.

Die laufende Wiedergabe wird nicht unterbrochen. Die Toniebox lädt die neue
Zuordnung beim erneuten Auflegen und dem dafür vorgesehenen langen Ohrdruck.

Nach jeder vollständig durchlaufenen Zufallsrunde wird eine neue Reihenfolge
erzeugt.

### Verhalten bei einem Home-Assistant-Neustart

Die aktive Folge, RUID, Audio-ID, Zufallsrunde und abgespielte Zeit werden
dauerhaft gespeichert. Sind die MQTT-Entitäten nach einem Neustart noch nicht
verfügbar, bleibt der letzte bekannte Stand sichtbar und der
Wiedergabestatus lautet `waiting_for_mqtt`.

Während dieses Wartezustands wird der Timer angehalten. Es wird keine Folge
automatisch abgeschlossen oder neu zugewiesen. Sobald dieselbe RUID und
Audio-ID wieder vorliegen und MQTT eine aktive Wiedergabe meldet, läuft der
Timer am gespeicherten Stand weiter. Die Zeit während des Neustarts wird nicht
mitgezählt.

### Bekannte Einschränkung des Timers

Der Timer zählt die Zeit, in der Home Assistant die Wiedergabe als aktiv
meldet. Die tatsächliche Abspielposition innerhalb einer TAF-Datei wird von
den verwendeten Toniebox-Sensoren nicht bereitgestellt.

Werden Kapitel oder Teile einer Folge übersprungen oder wird innerhalb der
Folge vor- beziehungsweise zurückgespult, kann der berechnete Fortschritt
deshalb von der tatsächlichen Abspielposition abweichen. Dadurch kann die
nächste Folge zu früh oder zu spät zugewiesen werden. Bei normaler Wiedergabe
ohne häufiges Springen arbeitet der Timer wie vorgesehen.

## Sensoren

- Folge und Serie
- Audio-ID und RUID
- Gesamtlaufzeit und Kapitelanzahl
- abgespielte und verbleibende Zeit
- Fortschritt und Wiedergabestatus
- nächste zugewiesene Folge
- Cache- und Bibliotheksstatus

## Aktionen

Jede konfigurierte Toniebox besitzt außerdem den Button
**Nächste Folge zuweisen**. Er schließt die aktuell gespeicherte Folge manuell
ab und weist dem Custom-Tonie sofort die nächste Folge seiner Zufallsrunde zu.
Der Button funktioniert auch mit einer nach einem Neustart
wiederhergestellten Sitzung.

- `teddycloud_runtime.reload_library`
- `teddycloud_runtime.refresh_runtime`
- `teddycloud_runtime.clear_cache`
- `teddycloud_runtime.mark_complete`
- `teddycloud_runtime.reset_progress`
- `teddycloud_runtime.retry_assignment`

## Diagnose

Bei Problemen:

1. Erreichbarkeit der konfigurierten TeddyCloud-Adresse prüfen.
2. Unter **Einstellungen → System → Protokolle** nach
   `teddycloud_runtime` suchen.
3. Keine Passwörter, Tokens oder vollständigen Diagnosearchive öffentlich
   teilen.

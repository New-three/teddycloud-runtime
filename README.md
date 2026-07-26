# TeddyCloud Runtime

Home-Assistant-Custom-Integration fÃ¼r lokale TeddyCloud-Installationen.

## Funktionen

- Einrichtung Ã¼ber die Home-Assistant-OberflÃ¤che
- UnterstÃ¼tzung mehrerer Tonieboxen
- Frei konfigurierbare Regeln aus Custom-Tonie und TeddyCloud-Serie
- Rekursives Einlesen der vollstÃ¤ndigen TAF-Bibliothek
- Exakte Laufzeitbestimmung aus Ogg/Opus-Daten
- Persistenter Laufzeit- und Wiedergabefortschritt
- Eigener Timer je Box, RUID, Audio-ID und Zufallsrunde
- Automatischer Folgenabschluss, sobald eine Box die Gesamtlaufzeit erreicht
- ZufÃ¤llige Folgenauswahl ohne Wiederholung innerhalb einer Runde
- Automatische Zuweisung der nÃ¤chsten TAF-Datei in TeddyCloud
- Sofortige Erstzuweisung, wenn ein konfigurierter Tonie noch eine Datei aus
  einer anderen Serie enthÃ¤lt

## Voraussetzungen und Datenquelle

TeddyCloud muss bereits mit einem MQTT-Broker verbunden sein. Die
Toniebox-Datenpunkte werden von TeddyCloud Ã¼ber MQTT Ã¼bertragen und durch die
MQTT-Integration in Home Assistant als EntitÃ¤ten bereitgestellt.

TeddyCloud Runtime erzeugt diese Toniebox-EntitÃ¤ten nicht selbst und verbindet
sich auch nicht direkt mit den Tonieboxen. Die Integration verwendet die
bereits in Home Assistant vorhandenen MQTT-EntitÃ¤ten fÃ¼r:

- aktuelle Audio-ID
- Wiedergabestatus
- aktuelle Tag-UID

ZusÃ¤tzlich greift TeddyCloud Runtime Ã¼ber die konfigurierte lokale
TeddyCloud-Adresse auf Bibliothek, Metadaten und TAF-Dateien zu. Vor der
Einrichtung mÃ¼ssen die benÃ¶tigten Toniebox-EntitÃ¤ten deshalb unter
**Einstellungen â†’ GerÃ¤te & Dienste â†’ MQTT** in Home Assistant vorhanden sein.

## Installation Ã¼ber HACS

Das Repository ist derzeit nicht im offiziellen HACS-Standardkatalog
enthalten. Es kann aber als benutzerdefiniertes Repository hinzugefÃ¼gt werden:

1. HACS in Home Assistant Ã¶ffnen.
2. **Integrationen** auswÃ¤hlen.
3. Oben rechts das MenÃ¼ mit den drei Punkten Ã¶ffnen.
4. **Benutzerdefinierte Repositories** auswÃ¤hlen.
5. Als Repository
   `https://github.com/New-three/teddycloud-runtime` eintragen.
6. Als Kategorie **Integration** auswÃ¤hlen und mit **HinzufÃ¼gen** bestÃ¤tigen.
7. In HACS nach **TeddyCloud Runtime** suchen und die Integration
   herunterladen.
8. Home Assistant vollstÃ¤ndig neu starten.
9. **Einstellungen â†’ GerÃ¤te & Dienste â†’ Integration hinzufÃ¼gen** Ã¶ffnen und
   nach **TeddyCloud Runtime** suchen.

FÃ¼r diese Installationsart muss HACS bereits in Home Assistant eingerichtet
sein.

## Manuelle Installation

1. Den Ordner `custom_components/teddycloud_runtime` nach
   `/config/custom_components/teddycloud_runtime` kopieren.
2. Home Assistant vollstÃ¤ndig neu starten.
3. **Einstellungen â†’ GerÃ¤te & Dienste â†’ Integration hinzufÃ¼gen** Ã¶ffnen.
4. Nach **TeddyCloud Runtime** suchen.
5. TeddyCloud-Adresse und die drei Sensoren der ersten Toniebox auswÃ¤hlen.

Die Beschreibung enthÃ¤lt bewusst keine Beispiel-IP. Verwendet wird immer die
Adresse der eigenen lokalen TeddyCloud.

Beim ersten Start analysiert die Integration alle gÃ¼ltigen TAF-Dateien der
Bibliothek. Dabei werden nur kleine HTTP-Bereiche der Audiodateien Ã¼bertragen.
Die ermittelten Laufzeiten werden dauerhaft in Home Assistant gespeichert.

## Tonieboxen konfigurieren

Weitere Boxen werden unter
**Einstellungen â†’ GerÃ¤te & Dienste â†’ TeddyCloud Runtime â†’ Konfigurieren**
hinzugefÃ¼gt. FÃ¼r jede Box werden folgende Werte benÃ¶tigt:

- frei wÃ¤hlbarer Boxname
- Sensor der aktuellen Audio-ID
- Sensor des Wiedergabestatus
- Sensor der aktuellen Tag-UID

## Custom-Tonie-Regeln

Die Integration enthÃ¤lt keine voreingestellten Tonies oder Serien. Regeln
werden Ã¼ber **Konfigurieren â†’ Custom-Tonie-Regel hinzufÃ¼gen** angelegt.

Jede Regel besteht aus:

- frei wÃ¤hlbarer Regelname
- UID des physischen Custom-Tonies
- exakter Serienname aus den TeddyCloud-Custom-Metadaten

Neue Bibliotheksdateien mit demselben Seriennamen werden beim nÃ¤chsten
Einlesen automatisch in die Zufallsauswahl aufgenommen.

### Beispiel fÃ¼r eine Serienregel

Dieses Beispiel ist keine Voreinstellung. Die Regel muss vom Nutzer selbst
angelegt und mit der UID des eigenen Custom-Tonies ausgefÃ¼llt werden.

1. **Einstellungen â†’ GerÃ¤te & Dienste â†’ TeddyCloud Runtime â†’
   Konfigurieren** Ã¶ffnen.
2. **Custom-Tonie-Regel hinzufÃ¼gen** auswÃ¤hlen.
3. Die Felder beispielsweise so ausfÃ¼llen:

   - Name: `Meine Serien-Zufallswiedergabe`
   - Tonie-UID: `AA:BB:CC:DD:EE:FF:00:11`
   - Serie: `Meine Beispielserie`

4. Die Beispiel-UID durch die tatsÃ¤chliche UID des eigenen Custom-Tonies
   ersetzen.
5. Speichern und den Tonie auf eine konfigurierte Toniebox stellen.

Der Serienname muss exakt so geschrieben sein, wie er in den
TeddyCloud-Custom-Metadaten steht. Die Integration nimmt anschlieÃŸend alle
vorhandenen und spÃ¤ter ergÃ¤nzten Custom-Folgen dieser Serie in die
Zufallsauswahl auf.

## Wiedergabeverhalten

`Playback=OFF` pausiert den Timer der betreffenden Box. Sobald eine Box die
vollstÃ¤ndige Laufzeit erreicht, gilt die Folge fÃ¼r den Custom-Tonie global als
beendet. Die Integration weist ihm danach die nÃ¤chste Folge zu.

Die laufende Wiedergabe wird nicht unterbrochen. Die Toniebox lÃ¤dt die neue
Zuordnung beim erneuten Auflegen und dem dafÃ¼r vorgesehenen langen Ohrdruck.

Nach jeder vollstÃ¤ndig durchlaufenen Zufallsrunde wird eine neue Reihenfolge
erzeugt.

### Verhalten bei einem Home-Assistant-Neustart

Die aktive Folge, RUID, Audio-ID, Zufallsrunde und abgespielte Zeit werden
dauerhaft gespeichert. Sind die MQTT-EntitÃ¤ten nach einem Neustart noch nicht
verfÃ¼gbar, bleibt der letzte bekannte Stand sichtbar und der
Wiedergabestatus lautet `waiting_for_mqtt`.

WÃ¤hrend dieses Wartezustands wird der Timer angehalten. Es wird keine Folge
automatisch abgeschlossen oder neu zugewiesen. Sobald dieselbe RUID und
Audio-ID wieder vorliegen und MQTT eine aktive Wiedergabe meldet, lÃ¤uft der
Timer am gespeicherten Stand weiter. Die Zeit wÃ¤hrend des Neustarts wird nicht
mitgezÃ¤hlt.

### Bekannte EinschrÃ¤nkung des Timers

Der Timer zÃ¤hlt die Zeit, in der Home Assistant die Wiedergabe als aktiv
meldet. Die tatsÃ¤chliche Abspielposition innerhalb einer TAF-Datei wird von
den verwendeten Toniebox-Sensoren nicht bereitgestellt.

Werden Kapitel oder Teile einer Folge Ã¼bersprungen oder wird innerhalb der
Folge vor- beziehungsweise zurÃ¼ckgespult, kann der berechnete Fortschritt
deshalb von der tatsÃ¤chlichen Abspielposition abweichen. Dadurch kann die
nÃ¤chste Folge zu frÃ¼h oder zu spÃ¤t zugewiesen werden. Bei normaler Wiedergabe
ohne hÃ¤ufiges Springen arbeitet der Timer wie vorgesehen.

## Sensoren

- Folge und Serie
- Audio-ID und RUID
- Gesamtlaufzeit und Kapitelanzahl
- abgespielte und verbleibende Zeit
- Fortschritt und Wiedergabestatus
- nÃ¤chste zugewiesene Folge
- Cache- und Bibliotheksstatus

## Aktionen

Jede konfigurierte Toniebox besitzt auÃŸerdem den Button
**NÃ¤chste Folge zuweisen**. Er schlieÃŸt die aktuell gespeicherte Folge manuell
ab und weist dem Custom-Tonie sofort die nÃ¤chste Folge seiner Zufallsrunde zu.
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

1. Erreichbarkeit der konfigurierten TeddyCloud-Adresse prÃ¼fen.
2. Unter **Einstellungen â†’ System â†’ Protokolle** nach
   `teddycloud_runtime` suchen.
3. Keine PasswÃ¶rter, Tokens oder vollstÃ¤ndigen Diagnosearchive Ã¶ffentlich
   teilen.
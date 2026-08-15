# Raumbuchung mit Genehmigungs-Workflow (`room_reservation`)

Odoo 19 CE Modul zur Verwaltung von Räumen und Buchungsanträgen mit
mehrstufiger Freigabe, Kapazitäts- und Ausstattungsprüfung.

> Status: **in Entwicklung** — dieses README ist das Gerüst gemäß Aufgabenstellung
> und wird während der Umsetzung befüllt.

---

## 1. Funktionsbeschreibung

### Motivation

Odoo 19 **Community** enthält kein Raumbuchungssystem. Das Modul `room`
(„Meeting Rooms") ist Enterprise-exklusiv und hängt zudem an `web_gantt`,
das ebenfalls nur in Enterprise verfügbar ist. Ebenso `appointment`.
In CE bleibt lediglich `calendar` — Termine ohne jedes Raum- oder
Ressourcenkonzept. Dieses Modul schließt genau diese Lücke.

### Fachlicher Umfang

<!-- TODO: nach Implementierung final beschreiben -->

- **Raumverwaltung** — Räume mit Kapazität, Standort und Ausstattung
- **Buchungsanträge** — Reservierung eines Raums für einen Zeitraum
- **Genehmigungs-Workflow** — Anträge werden durch Manager freigegeben
- **Konfliktfreiheit** — Doppelbelegungen werden systemseitig verhindert
- **Automatik** — überfällige, noch nicht genehmigte Anträge verfallen

### Datenmodell

<!-- TODO: Feldlisten ergänzen, sobald die Models stehen -->

| Model | Zweck |
| --- | --- |
| `booking.room` | Buchbarer Raum |
| `booking.room.equipment` | Ausstattungsmerkmal (Beamer, Whiteboard, …) |
| `booking.reservation` | Buchungsantrag |
| `res.users` (`_inherit`) | Erweiterung um eigene Reservierungen |

> Der Namespace `booking.*` wird bewusst statt `room.*` verwendet, um
> Kollisionen mit dem Enterprise-Modul `room` auszuschließen.

### Status-Workflow

<!-- TODO: Übergänge und Berechtigungen final dokumentieren -->

```
draft → to_approve → confirmed → done
             ↓            ↓
         cancelled    cancelled
```

### Geschäftsregeln

<!-- TODO: je Regel auf Implementierung und Test verweisen -->

1. Keine Doppelbelegung eines Raums für überschneidende Zeiträume
2. Teilnehmerzahl darf die Raumkapazität nicht überschreiten
3. Ende muss nach dem Beginn liegen
4. Keine Buchung in der Vergangenheit
5. Freigabe ausschließlich durch die Manager-Gruppe

### Berechtigungen

<!-- TODO: Zugriffsmatrix (Model × Gruppe × CRUD) ergänzen -->

| Gruppe | Rechte |
| --- | --- |
| `group_booking_user` | eigene Reservierungen anlegen und bearbeiten |
| `group_booking_manager` | Räume verwalten, alle Reservierungen freigeben |

### Views und Navigation

<!-- TODO: ergänzen -->

---

## 2. Herangehensweise

### Architekturentscheidungen

| Entscheidung | Begründung | Verworfene Alternative |
| --- | --- | --- |
| Zeitraum als `Datetime start`/`stop`, `duration` computed | Odoo-Konvention (`calendar.event`); UTC-Speicherung und Zeitzonen-Anzeige übernimmt das Framework | `Date` plus Float-Uhrzeit — erzeugt eigene Zeitzonenlogik |
| Overlap über halboffene Intervalle (`A.start < B.stop AND A.stop > B.start`) | Back-to-back-Buchungen (10–11 Uhr, 11–12 Uhr) müssen zulässig bleiben | Geschlossene Intervalle — praxisuntauglich |
| Overlap-Prüfung als `@api.constrains` | Idiomatisch und direkt testbar; verbleibende Race Condition siehe [Abgrenzung](#abgrenzung-non-goals) | PostgreSQL-`EXCLUDE` mit `tstzrange` — wasserdicht, erzwingt aber die Extension `btree_gist` |
| Status-Wechsel über deklarative Übergangs-Map plus zentrale Transition-Methode | Neue Zustände ändern eine Datenstruktur statt jeder Action-Methode; ein parametrisierter Test deckt alle Kombinationen ab | Prüfung in jeder `action_*`-Methode — Open/Closed-Verletzung |
| Kapazitätsprüfung als `@api.onchange` **und** `@api.constrains` | `onchange` ist reine UI und schützt nicht bei Import oder API-Zugriff; erst `constrains` sichert die Integrität | Nur `onchange` |
| Vergangenheits-Prüfung nur bei Neuanlage | Eine laufende oder vergangene Buchung muss stornier- und korrigierbar bleiben | Prüfung bei jedem Schreibvorgang — blockiert Statuswechsel an bestehenden Sätzen |
| Lesezugriff für alle, Schreibzugriff nur auf eigene Reservierungen | Belegung muss einsehbar sein, sonst ist der Kalender wertlos; getrennte Record Rules für `perm_read` und `perm_write`/`perm_unlink` | Nur eigene sichtbar — Raumbelegung nicht nachvollziehbar |
| Organisator als `res.users`, `depends` nur auf `base` und `mail` | Modul läuft auf jeder CE-Instanz ohne HR und bleibt isoliert testbar | `hr.employee` — fachlich näher (Abteilung, Vorgesetzter als Genehmiger), kostet aber die `hr`-Abhängigkeit; `res.partner` — erlaubt externe Bucher, macht aber „meine Buchungen" in Record Rules unsauber |
| Ausstattung als eigenes Model mit m2m-Relation | Filterbar über Domains und ohne Code-Änderung erweiterbar | `Selection`-Feld — nicht durch Anwender pflegbar |
| Cron-Schwelle über `ir.config_parameter` | Konfigurierbar statt hardcodiert; Tests setzen den Parameter, statt die Systemzeit zu manipulieren | Konstante im Code |
| Referenz über `ir.sequence` | Odoo-Standard für fachliche Belegnummern | Computed `display_name` aus Raum und Datum — nicht stabil referenzierbar |

### Vorgehen

Umsetzung in aufeinander aufbauenden Schritten, jeder Schritt ein eigener Commit.

<!-- TODO: Commit-Referenzen je Schritt ergänzen -->

1. **Gerüst** — Verzeichnisstruktur, `__manifest__.py` mit `depends` auf `base` und `mail`
2. **Models** — `booking.room.equipment`, `booking.room`, `booking.reservation`,
   Erweiterung von `res.users` um eigene Reservierungen
3. **Geschäftslogik** — Constraints, Status-Übergänge, computed fields
4. **Security** — Gruppen, Zugriffsrechte, Record Rules
5. **Views** — list, form, search, calendar sowie Menüs und Aktionen
6. **Automatisierung** — Sequenz, Scheduled Action, Aktivität für Genehmiger
7. **Tests** — Geschäftsregeln, Status-Übergänge, Zugriffsbeschränkung
8. **Dokumentation** — README vervollständigen

### Abgrenzung (Non-Goals)

Bewusst nicht umgesetzt, um den Umfang der Probearbeit zu wahren:

- **Multi-Company** — kein `company_id`; erfordert zusätzliche Record Rules ohne
  fachlichen Mehrwert für die gestellte Aufgabe
- **Wiederkehrende Buchungen** — Rekurrenzlogik ist ein eigenständiges Thema
- **Absicherung gegen konkurrierende Transaktionen** — die Overlap-Prüfung per
  `@api.constrains` kann bei zwei exakt gleichzeitig schreibenden Transaktionen
  theoretisch umgangen werden. Wasserdicht wäre ein PostgreSQL-`EXCLUDE`-Constraint
  über `tstzrange`, was die Extension `btree_gist` als Installationsvoraussetzung
  nach sich zöge. Bewusst zurückgestellt und hier dokumentiert.
- **Externe Bucher** — Reservierungen setzen einen Odoo-Benutzer voraus

---

## 3. Installationsanleitung

### Voraussetzungen

<!-- TODO: konkrete Versionen ergänzen -->

- Odoo 19.0 Community Edition
- PostgreSQL
- Python (Version gemäß Odoo 19 Anforderungen)

### Installation

<!-- TODO: getestete Schritte einsetzen -->

```bash
# 1. Repository in den Addons-Pfad klonen

# 2. Odoo mit aktualisierter Modulliste starten

# 3. Modul über Apps installieren
```

### Tests ausführen

<!-- TODO: exakten Befehl einsetzen -->

```bash
```

---

## 4. Zeitaufwand

<!-- TODO: Ist-Werte nach Abschluss eintragen -->

| Arbeitspaket | Geplant | Tatsächlich |
| --- | --- | --- |
| Projektgerüst und Manifest | 0,5 h | |
| Models und Geschäftslogik | 1,5 h | |
| Views, Menüs, Security | 1,5 h | |
| Scheduled Action und Aktivitäten | 1,0 h | |
| Tests | 1,5 h | |
| Dokumentation und Git-Historie | 1,0 h | |
| **Summe** | **7,0 h** | |

---

## 5. Definition of Done

<!-- TODO: abhaken, sobald erfüllt und verifiziert -->

**Funktion**

- [ ] Modul ist auf einer frischen Odoo 19 CE Instanz ohne Fehler installierbar
- [ ] Deinstallation und Neuinstallation funktionieren fehlerfrei
- [ ] Alle Geschäftsregeln sind implementiert und greifen
- [ ] Der Status-Workflow ist vollständig durchlaufbar

**Codequalität**

- [ ] PEP8-konform, geprüft mit Linter
- [ ] Odoo-Konventionen für Struktur, Benennung und Manifest eingehalten
- [ ] Fehlerfälle werfen `UserError` bzw. `ValidationError` mit klarer Meldung
- [ ] Benutzertexte sind übersetzbar

**Security**

- [ ] Zugriffsrechte für alle Models definiert
- [ ] Record Rules greifen, aus Benutzersicht verifiziert

**Tests**

- [ ] Automatisierte Tests für alle Geschäftsregeln
- [ ] Tests für erlaubte und unerlaubte Status-Übergänge
- [ ] Test für die Zugriffsbeschränkung
- [ ] Gesamte Testsuite läuft grün

**Dokumentation und Abgabe**

- [ ] README vollständig, alle Platzhalter aufgelöst
- [ ] Nachvollziehbare Git-Historie mit thematisch getrennten Commits
- [ ] Repository auf GitHub verfügbar

---

## 6. Bewertungsmatrix

Gewichtung gemäß Aufgabenstellung, zur Selbsteinschätzung.

<!-- TODO: Selbsteinschätzung nach Abschluss eintragen -->

| Kriterium | Gewicht | Nachweis | Selbsteinschätzung |
| --- | --- | --- | --- |
| Codequalität und Tests | 50 % | | |
| Odoo-Kenntnisse | 20 % | | |
| Dokumentation | 20 % | | |
| Git-Historie | 10 % | | |

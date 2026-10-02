# BedLink

## Emergency Response Coordination Platform

**From the emergency call to the hospital handover: one connected emergency network.**

BedLink is a browser-based emergency response coordination prototype that connects an ambulance console, a backend triage and hospital-matching layer, a hospital console, and a dispatch command center. It demonstrates how patient information, vital signs, hospital resources, acceptance decisions, and live operational events can move through one shared workflow.

> The goal is not simply to find a hospital. The goal is to help identify a hospital that is operationally prepared to receive the patient.

BedLink is a demonstration application only. Its triage score is rule-based and not clinically validated. It must not be used for real medical care or real patient information.

## Table of Contents

- [Project Overview](#project-overview)
- [Why This Is Different](#why-this-is-different)
- [Core Innovation: Confirm Before Arrival](#core-innovation-confirm-before-arrival)
- [Key Features](#key-features)
  - [Ambulance Console](#ambulance-console)
  - [Live Vital History and Deterioration](#live-vital-history-and-deterioration)
  - [Medical Operations Assistant](#medical-operations-assistant)
  - [Dynamic Hospital Matching](#dynamic-hospital-matching)
  - [Hospital Console](#hospital-console)
  - [Dispatch Command Center](#dispatch-command-center)
  - [Emergency Simulation Mode](#emergency-simulation-mode)
- [Architecture / Workflow](#architecture--workflow)
  - [Runtime Architecture](#runtime-architecture)
  - [Current Emergency Workflow](#current-emergency-workflow)
  - [Triage Calculation](#triage-calculation)
- [Technology Stack](#technology-stack)
- [Setup & Installation Instructions](#setup--installation-instructions)
  - [Requirements](#requirements)
  - [Run Locally](#run-locally)
  - [Stop or Reset](#stop-or-reset)
  - [Troubleshooting](#troubleshooting)
- [Dataset / API Information](#dataset--api-information)
  - [Dataset](#dataset)
  - [API Endpoints](#api-endpoints)
- [Screenshots / Demo Information](#screenshots--demo-information)
- [Product Vision and Future Workflow](#product-vision-and-future-workflow)
  - [Two-minute Confirmation and Escalation](#two-minute-confirmation-and-escalation)
  - [Ambulance-hospital Emergency Chat](#ambulance-hospital-emergency-chat)
  - [Resource Reservation and Hospital Preparation](#resource-reservation-and-hospital-preparation)
  - [Live Routing and ETA Awareness](#live-routing-and-eta-awareness)
  - [Digital Handover](#digital-handover)
  - [Roles and Auditability](#roles-and-auditability)
  - [Post-emergency Analytics](#post-emergency-analytics)
- [Limitations](#limitations)
- [Future Scope](#future-scope)
- [License and Usage Note](#license-and-usage-note)

## Project Overview

Most basic emergency transport applications stop at:

```text
Find hospital -> Show ETA -> Navigate
```

BedLink demonstrates a broader coordination flow:

```text
Ambulance -> Patient -> Live vitals -> Hospital matching
    -> Hospital request -> Accept or decline -> Dispatch updates
    -> Hospital preparation -> Arrival
```

The current prototype includes three coordinated views:

- **Ambulance Console:** patient context, vitals, location, triage, scenario lookup, and hospital requests.
- **Hospital Console:** capacity, supplies, staff availability, freshness indicators, incoming requests, and accept/decline decisions.
- **Dispatch Command Center:** active ambulances, simulated movement, request status, event history, and backend activity.

At startup, the backend creates an in-memory demo state containing three ambulances, five hospitals, fictional resources, staff, events, and API activity. Browser clients receive updated state through a Server-Sent Events connection.

## Why This Is Different

The prototype treats hospital selection as an operational matching problem rather than a distance-only lookup. A hospital can be nearby but unsuitable if it lacks the requested resource, has no appropriate bed, is overloaded, or has stale availability data.

The product direction described by this project is a connected emergency network in which:

- Ambulance crews share patient and vital information before arrival.
- Hospitals can explicitly accept or decline an incoming case.
- Dispatch sees the same emergency state as the ambulance and hospital teams.
- Resource availability affects hospital ranking.
- Hospital readiness continues to matter after a destination is selected.
- The emergency can eventually be closed with a structured handover and operational history.

Some of these capabilities are implemented in the current demo; others are future scope. The status table below keeps that distinction explicit.

| Capability | Current prototype status |
| --- | --- |
| Ambulance status and location | Implemented with simulated updates |
| Rule-based triage score | Implemented as a demo calculation |
| Vital history | Implemented with in-memory history and SVG sparklines |
| Hospital matching | Implemented with Operation Match ranking |
| Explicit hospital accept/decline | Implemented |
| Hospital response timeout and automatic escalation | Planned |
| Ambulance-hospital chat | Planned |
| Full resource reservation | Planned; acceptance currently decrements emergency beds |
| Hospital preparation state | Partially implemented through trauma-bay preparation |
| Live GPS, routing, and traffic-aware ETA | Planned; current map and ETA are simulated |
| Digital patient handover | Planned |
| Post-emergency analytics | Planned |
| Authentication and role-based permissions | Planned |

## Core Innovation: Confirm Before Arrival

The current workflow does not automatically accept an ambulance when it selects a hospital. The ambulance sends a request to one hospital, and hospital staff explicitly choose **Accept Ambulance** or **Decline** with an optional reason.

```text
Ambulance selects hospital
          |
          v
Hospital receives pending request
       /       \
  Accept      Decline
    |            |
Destination   Ambulance can choose
confirmed     another ranked hospital
```

The intended product evolution is a **Confirm and Hold** workflow with a two-minute response window. If a hospital declines or fails to respond, the system would offer the case to the next best untried hospital. This timeout and automatic escalation behavior is not implemented in the current `server.py` demo.

## Key Features

### Ambulance Console

- Send an emergency alert for a selected ambulance.
- Show patient type, crew, location, speed, ETA, and destination.
- Update heart rate, oxygen saturation, blood pressure, and respiratory rate.
- Calculate and display a transparent rule-based triage score from 0 to 100.
- Classify the score as `MODERATE`, `HIGH`, or `CRITICAL`.
- Simulate a worsening or stabilizing patient condition.
- Advance the simulated ambulance location and ETA.
- Send a hospital acceptance request.
- Display pending, accepted, or declined request state.
- Open patient details and vital-history sparkline charts.

### Live Vital History and Deterioration

The application stores recent vital readings in memory and shows their trends for heart rate, SpO2, systolic blood pressure, and respiratory rate. When vitals change, the dashboard records an event and recalculates the triage score.

The current implementation provides rule-based operational warnings. It does not diagnose a patient or replace clinical judgment.

### Medical Operations Assistant

The assistant is a keyword and database lookup tool, not an LLM. It recognizes demo prompts for:

- Severe chest pain and cardiac symptoms
- Road accidents and trauma
- Breathing difficulty and asthma
- Stroke symptoms
- Major bleeding
- Unconsciousness
- High fever

It can also look up requirements such as ICU beds, trauma bays, ventilators, oxygen, blood, emergency medication, IV fluids, and operating rooms.

### Dynamic Hospital Matching

Hospitals are ranked using **Operation Match**, which combines operational factors instead of using distance alone:

| Factor | Weight |
| --- | ---: |
| Resource compatibility | 40% |
| Bed availability | 20% |
| Travel efficiency | 20% |
| Data freshness | 10% |
| Hospital load | 10% |

Each match displays the score, ETA, distance, requested-resource availability, bed availability, freshness state, load, and a score breakdown.

### Hospital Console

- Switch between five seeded hospitals.
- Review emergency capacity and supplies.
- Increment or decrement resource quantities.
- See available, low, critical, full, and out-of-stock states.
- View resource freshness and simulate stale data.
- Verify all hospital values to refresh timestamps.
- Cycle staff through `AVAILABLE`, `BUSY`, and `OFF DUTY`.
- Accept or decline incoming ambulance requests.
- Select an optional decline reason.
- Prepare a trauma bay after acceptance.
- Review a filtered staff activity log.

### Dispatch Command Center

- View active ambulances, status, priority, ETA, and destination.
- Track hospital request status.
- View a simulated dispatch map.
- Filter events by source or criticality.
- Review recent backend API activity.
- Receive live state updates through SSE.

### Emergency Simulation Mode

The **Demo Mode** button runs a scripted ambulance-side scenario for `AMB-204`:

1. Run a road-accident lookup.
2. Create an emergency alert.
3. Update location.
4. Worsen patient vitals twice.
5. Send a hospital acceptance request.
6. Update location again.

Hospital acceptance or decline remains a manual action in the Hospital Console.

## Architecture / Workflow

### Runtime Architecture

```text
Browser: index.html
        |
        | HTTP GET and JSON POST
        v
Python server.py
        |
        +-- Static page serving
        +-- API routing and validation
        +-- In-memory ambulance and hospital state
        +-- Rule-based triage calculation
        +-- Operation Match ranking
        +-- Event history and API log
        |
        +-- GET /api/stream (Server-Sent Events)
                    |
                    v
          Browser receives state snapshots and re-renders
```

### Current emergency workflow

1. An ambulance sends an alert containing patient type and vitals.
2. The backend calculates a demo triage score and priority level.
3. The operator selects a scenario or asks for operational resources.
4. Required resources are calculated and hospitals are ranked.
5. The ambulance sends an acceptance request to one selected hospital.
6. The selected hospital explicitly accepts or declines the request.
7. On acceptance, the ambulance destination changes and the hospital's emergency-bed count decreases.
8. The hospital can prepare a trauma bay and mark the trauma surgeon busy.
9. Dispatch sees events, request status, ETA, and simulated map updates.
10. Connected browser clients receive the latest state over SSE.

### Triage calculation

The score uses oxygen saturation, heart rate, systolic blood pressure, respiratory rate, and a trauma adjustment. It is capped at 100:

- `CRITICAL`: score 75 or higher
- `HIGH`: score 50 to 74
- `MODERATE`: score below 50

This is an operational demo formula, not a medical protocol.

## Technology Stack

| Layer | Technology |
| --- | --- |
| Frontend | HTML, CSS, and vanilla JavaScript |
| Backend | Python 3 standard library |
| HTTP server | `http.server.ThreadingHTTPServer` |
| Live updates | Server-Sent Events via `/api/stream` |
| State | In-memory Python dictionaries |
| Visualization | Inline SVG gauges, sparklines, and simulated map |
| Persistence | None; state resets when the process stops |
| External dependencies | None |

## Setup & Installation Instructions

### Requirements

- Python 3.8 or later
- A modern browser with JavaScript and Server-Sent Events support
- PowerShell, Command Prompt, macOS Terminal, or a Linux shell

No package installation is required because the backend uses only the Python standard library.

### Run locally

Open a terminal in the project directory and run:

```powershell
python server.py
```

Then open [http://localhost:8100](http://localhost:8100).

To use another port:

```powershell
python server.py 9000
```

Then open [http://localhost:9000](http://localhost:9000).

### Stop or reset

- Press `Ctrl+C` to stop the server.
- Use **Reset** in the dashboard to restore the initial in-memory state.
- Restarting the server also resets the state.

### Troubleshooting

- If the dashboard shows `Backend unreachable`, confirm that `server.py` is running and that the browser uses the correct port.
- If port `8100` is occupied, use another port such as `python server.py 8101`.
- The normal launch path is through the Python server; do not open `index.html` directly.

## Dataset / API Information

### Dataset

There is no external dataset. `server.py` seeds fictional hospital and ambulance data at runtime, including:

- Three ambulances with fictional IDs, crews, locations, statuses, and patient records.
- Five hospitals with distances, capacity, supplies, staff, and activity logs.
- Example vitals, scenario requirements, and timestamps.

All state is held in memory and is shared by connected browser clients.

### API endpoints

The backend accepts JSON requests and returns JSON responses.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/state` | Return the complete current state |
| `GET` | `/api/ambulances` | Return ambulance records |
| `GET` | `/api/hospitals` | Return hospital names |
| `GET` | `/api/hospital/resources` | Return hospital resource records |
| `GET` | `/api/events` | Return the event feed |
| `GET` | `/api/stream` | Open the live SSE state stream |
| `POST` | `/api/ambulance/alert` | Create or update an ambulance emergency |
| `POST` | `/api/ambulance/vitals` | Update patient vitals |
| `POST` | `/api/ambulance/location` | Advance simulated location and ETA |
| `POST` | `/api/ambulance/action` | Worsen, stabilize, request, or complete an action |
| `POST` | `/api/ambulance/query` | Run a scenario or resource lookup |
| `POST` | `/api/ambulance/hospital-request` | Send a request to one hospital |
| `POST` | `/api/ambulance/select` | Compatibility alias for hospital request |
| `POST` | `/api/hospital/accept` | Accept a pending request |
| `POST` | `/api/hospital/decline` | Decline a pending request |
| `POST` | `/api/hospital/prepare` | Prepare a trauma bay after acceptance |
| `POST` | `/api/hospital/resource` | Change a capacity or supply quantity |
| `POST` | `/api/hospital/staff` | Cycle a staff member's availability |
| `POST` | `/api/hospital/freshness` | Verify or age hospital data |
| `POST` | `/api/demo` | Start the scripted demo sequence |
| `POST` | `/api/demo/reset` | Reset all in-memory state |

Example PowerShell request:

```powershell
$body = @{ id = "AMB-204"; action = "worsen" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8100/api/ambulance/action `
  -ContentType "application/json" `
  -Body $body
```

Invalid requests return HTTP `422` with a JSON error object. The API currently has no authentication, authorization, rate limiting, persistence, or external healthcare integration.

## Screenshots / Demo Information

No screenshot files are currently committed. The dashboard itself is the demonstration surface.

Recommended hackathon walkthrough:

1. Start the server and open the dashboard.
2. Click **Demo Mode** to populate the live event stream.
3. Try **Road Accident** or **Severe Chest Pain** in the Ambulance Console.
4. Review the generated requirements and Operation Match ranking.
5. Click **REQUEST ACCEPTANCE** for a hospital.
6. Switch to that hospital in the Hospital Console.
7. Click **ACCEPT AMBULANCE** or **DECLINE** with a reason.
8. Change a hospital resource or simulate stale data.
9. Watch the Ambulance and Dispatch panels update live.
10. Use **Reset** to repeat the scenario.

## Product Vision and Future Workflow

The supplied product concept extends the current prototype into a complete emergency lifecycle:

```text
Emergency created
    -> Patient profile and live vitals
    -> Hospital matching
    -> Confirm and hold request
    -> Accept, decline, or timeout
    -> Next-best hospital escalation
    -> Ambulance-hospital communication
    -> Resource reservation
    -> Hospital preparation
    -> ETA and route updates
    -> Patient arrival
    -> Digital handover
    -> Emergency closure and analytics
```

The intended future experience includes the following capabilities:

### Two-minute confirmation and escalation

A hospital would receive a targeted request with a two-minute response window. A decline or timeout would automatically trigger the next best eligible hospital and keep the ambulance crew informed.

### Ambulance-hospital emergency chat

Each emergency could have an in-case communication channel for structured messages such as:

- Patient condition worsening
- Live vitals updated
- ETA changed
- Trauma team requested
- ICU or ventilator needed
- Blood preparation requested
- Patient stabilized

Important messages would also become timeline events.

### Resource reservation and hospital preparation

After acceptance, the system could reserve specific resources for the incoming patient rather than only changing aggregate counters:

```text
ICU bed       -> Reserved
Ventilator    -> Reserved
Trauma bay    -> Ready
Trauma team   -> Notified
Blood         -> Preparing
```

### Live routing and ETA awareness

A production version could integrate GPS, traffic-aware routing, route deviation detection, alternate routes, and updated ETAs. The current dashboard uses a simulated SVG map and demo ETA calculations.

### Digital handover

At arrival, a future handover workflow could include patient ID, demographics, allergies, symptoms, initial and latest vitals, vital trends, treatment provided, transport events, ambulance details, and arrival time. Hospital staff could explicitly accept the handover to close the emergency.

### Roles and auditability

Future role-based workflows could distinguish paramedics, emergency doctors, nurses, hospital administrators, and dispatchers. Important actions would record who performed them, what happened, when it happened, and which emergency was affected.

### Post-emergency analytics

A completed emergency could produce response-time, transport-time, preparation-time, handover-time, vital-trend, resource-use, and event summaries.

## Limitations

- Data is fictional, seeded, and stored only in memory.
- Restarting the server loses events, resource changes, staff changes, and requests.
- The triage formula is not clinical guidance or a validated model.
- The map, travel distance, and ETA are simulated rather than GPS or traffic based.
- The assistant uses keywords and predefined scenarios rather than general language understanding.
- There is no ambulance-hospital chat in the current implementation.
- There is no two-minute timer, automatic timeout handling, or automatic next-hospital escalation.
- Full resource reservation is not implemented; acceptance currently decrements emergency-bed availability.
- Digital handover and post-emergency analytics are not implemented.
- There is no authentication, role-based access control, immutable audit identity, or encryption configuration.
- All connected users share global process state.
- There are no automated unit, API, browser, concurrency, accessibility, or security tests.
- The application is not hardened for production traffic or real patient data.

## Future Scope

- Add persistent storage and an event-sourced emergency record.
- Implement explicit resource reservations and release rules.
- Add two-minute hospital response timers and deterministic escalation.
- Add secure ambulance-hospital communication with structured messages.
- Integrate GPS, routing, traffic-aware ETAs, and map services.
- Add digital handover and emergency closure workflows.
- Add authentication, role-based permissions, and immutable audit logs.
- Replace fictional records with configurable, approved healthcare integrations.
- Add clinician-reviewed protocols, governance, explainability, and safety controls.
- Add automated unit, API, browser, accessibility, security, and load tests.
- Support reconnect recovery and multi-user conflict handling for live streams.

## License and Usage Note

No license file is included. Treat this repository as a local demonstration. Do not enter real patient, hospital, or emergency-response data into the application.

## Emergency Response, Connected

One patient. One ambulance. One hospital. One continuous emergency workflow.

# TeddyCloud Runtime

A custom Home Assistant integration for local TeddyCloud installations.

## Features

- Setup through the Home Assistant user interface
- Support for multiple Tonieboxes
- Configurable rules that link a Tonie to a series in the TeddyCloud library
- Recursive scanning of the complete TAF library
- Accurate runtime detection from Ogg/Opus data
- Persistent runtime and playback progress
- A separate timer for each Toniebox, RUID, audio ID, and shuffle cycle
- Automatic episode completion when one Toniebox reaches the full runtime
- Random episode selection without repeats within a shuffle cycle
- Automatic assignment of the next TAF file in TeddyCloud
- Immediate first assignment if a configured Tonie still contains content from
  another series

## Requirements and data sources

TeddyCloud must already be connected to an MQTT broker. TeddyCloud publishes
the Toniebox data over MQTT, and the MQTT integration in Home Assistant
provides it as entities.

TeddyCloud Runtime does not create these entities and does not connect
directly to the Tonieboxes. It uses the existing Home Assistant MQTT entities
for:

- the current audio ID
- the playback status
- the current tag UID

The integration also uses the configured local TeddyCloud address to access
the library, metadata, and TAF files. Before starting the setup, make sure the
required Toniebox entities are available under
**Settings → Devices & services → MQTT** in Home Assistant.

## Installation with HACS

The repository is not currently included in the default HACS catalog, but it
can be added as a custom repository:

1. Open HACS in Home Assistant.
2. Select **Integrations**.
3. Open the three-dot menu in the top-right corner.
4. Select **Custom repositories**.
5. Enter `https://github.com/New-three/teddycloud-runtime` as the repository.
6. Select **Integration** as the category and confirm with **Add**.
7. Find **TeddyCloud Runtime** in HACS and download it.
8. Restart Home Assistant completely.
9. Open **Settings → Devices & services → Add integration** and search for
   **TeddyCloud Runtime**.

HACS must already be installed and configured in Home Assistant.

## Manual installation

1. Copy `custom_components/teddycloud_runtime` to
   `/config/custom_components/teddycloud_runtime`.
2. Restart Home Assistant completely.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **TeddyCloud Runtime**.
5. Enter the TeddyCloud address and select the three entities for the first
   Toniebox.

No example IP address is included. Always enter the address of your own local
TeddyCloud instance.

On its first run, the integration analyses all valid TAF files in the library.
Only small byte ranges of the audio files are transferred. The detected
runtimes are stored permanently in Home Assistant.

## Configuring Tonieboxes

Additional Tonieboxes can be added under
**Settings → Devices & services → TeddyCloud Runtime → Configure**.

The following information is required for each Toniebox:

- a name of your choice
- the entity containing the current audio ID
- the entity containing the playback status
- the entity containing the current tag UID

## Tonie rules

The integration does not include any preset Tonies or series. Add your own
rules under **Configure → Add Custom Tonie rule**.

Each rule contains:

- a rule name of your choice
- the UID of the physical Tonie used as the trigger
- the exact series name from the TeddyCloud custom metadata

The trigger may be a Creative Tonie or an original Tonie. New library files
with the same series name are automatically included in the random selection
the next time the library is scanned.

### Example series rule

This example is not a preset. You must create the rule yourself and replace
the example UID with the UID of your own Tonie.

1. Open **Settings → Devices & services → TeddyCloud Runtime → Configure**.
2. Select **Add Custom Tonie rule**.
3. Enter values such as:

   - Name: `My random series`
   - Tonie UID: `AA:BB:CC:DD:EE:FF:00:11`
   - Series: `My example series`

4. Replace the example UID with the actual UID of your Tonie.
5. Save the rule and place the Tonie on a configured Toniebox.

The series name must match the TeddyCloud custom metadata exactly. All current
and future custom episodes with that series name are then included in the
random selection.

## Playback behaviour

The integration reads the runtime of the current audio file from the
TeddyCloud library and uses it as a playback timer. `Playback=OFF` pauses the
timer for that Toniebox.

When one Toniebox reaches the full runtime, the episode is considered complete
for that Tonie. The integration then assigns the next randomly selected
episode in TeddyCloud.

The current playback is not interrupted. The Toniebox keeps its current
content until it performs a freshness check. To start a freshness check, press
either ear for about three seconds until you hear a sound. The Toniebox then
checks TeddyCloud for updated content.

The timer for the newly assigned episode starts only after the Toniebox reports
the new audio ID. Until then, the current episode can still be played as often
as you like.

Episodes are not repeated within a shuffle cycle. Once every episode in the
selected series has been assigned, a new random order is created.

### Behaviour after a Home Assistant restart

The active episode, RUID, audio ID, shuffle cycle, and elapsed playback time
are stored permanently. If the MQTT entities are not yet available after a
restart, the last known state remains visible and the playback status is
`waiting_for_mqtt`.

The timer is paused while waiting for MQTT. No episode is completed or
reassigned automatically. As soon as the same RUID and audio ID are available
again and MQTT reports active playback, the timer resumes from its saved
position. Time spent restarting is not counted.

### Known timer limitation

The timer measures how long Home Assistant reports active playback. The
Toniebox entities used by the integration do not provide the actual playback
position within a TAF file.

Skipping chapters or seeking forwards or backwards can therefore cause the
calculated progress to differ from the real playback position. As a result,
the next episode may be assigned too early or too late. During normal playback
without frequent skipping, the timer works as intended.

## Sensors

- episode and series
- audio ID and RUID
- total runtime and chapter count
- elapsed and remaining time
- progress and playback status
- next episode
- cache and library status

## Controls and services

Each configured Toniebox also has an **Assign next episode** button. It marks
the currently stored episode as complete and immediately assigns the next
episode from the Tonie's shuffle cycle. The button also works with a playback
session restored after a restart.

Available services:

- `teddycloud_runtime.reload_library`
- `teddycloud_runtime.refresh_runtime`
- `teddycloud_runtime.clear_cache`
- `teddycloud_runtime.mark_complete`
- `teddycloud_runtime.reset_progress`
- `teddycloud_runtime.retry_assignment`

## Troubleshooting

If something does not work:

1. Check that the configured TeddyCloud address is reachable.
2. Open **Settings → System → Logs** and search for
   `teddycloud_runtime`.
3. Do not share passwords, tokens, or complete diagnostic archives publicly.

"""Constants for TeddyCloud Runtime."""

from datetime import timedelta

DOMAIN = "teddycloud_runtime"
PLATFORMS = ["sensor", "button"]

CONF_AUDIO_ID_ENTITY = "audio_id_entity"
CONF_PLAYBACK_ENTITY = "playback_entity"
CONF_TAG_ENTITY = "tag_entity"
CONF_BOXES = "boxes"
CONF_BOX_ID = "box_id"
CONF_BOX_NAME = "box_name"
CONF_RULES = "rules"
CONF_RULE_ID = "rule_id"
CONF_RULE_NAME = "rule_name"
CONF_TONIE_UID = "tonie_uid"
CONF_SERIES = "series"

DEFAULT_HOST = "http://teddycloud.local"
DEFAULT_AUDIO_ID_ENTITY = "sensor.toniebox_content_audio_id"
DEFAULT_PLAYBACK_ENTITY = "sensor.toniebox_playback"
DEFAULT_TAG_ENTITY = "sensor.toniebox_tag_valid"

UPDATE_INTERVAL = timedelta(minutes=30)
STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}.runtime_cache"
PLAYBACK_STORE_KEY = f"{DOMAIN}.playback_state"
TAIL_WINDOW = 65_536
MAX_TAIL_WINDOW = 1_048_576
LIBRARY_CONCURRENCY = 2

SERVICE_RELOAD_LIBRARY = "reload_library"
SERVICE_REFRESH_RUNTIME = "refresh_runtime"
SERVICE_CLEAR_CACHE = "clear_cache"
SERVICE_MARK_COMPLETE = "mark_complete"
SERVICE_RESET_PROGRESS = "reset_progress"
SERVICE_RETRY_ASSIGNMENT = "retry_assignment"

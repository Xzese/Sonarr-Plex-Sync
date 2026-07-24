#!/usr/bin/env python3
import os
from plexapi.server import PlexServer
from jellyfin_apiclient_python import JellyfinClient
from pyarr import SonarrAPI
from dotenv import load_dotenv
import datetime
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "output/log.txt")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_RETENTION_WEEKS = int(os.getenv("LOG_RETENTION_WEEKS", "4"))

# Configure file rotation for logs.
os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
log_handler = TimedRotatingFileHandler(
    LOG_FILE,
    when="W0",
    interval=1,
    atTime=datetime.time(0, 0),
    backupCount=max(0, LOG_RETENTION_WEEKS),
    encoding="utf-8",
)
log_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

logger = logging.getLogger("sonarr_delete_watched_episodes")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger.addHandler(log_handler)
logger.propagate = False


def add_to_log(message):
    logger.info(message)

def get_last_played_date(user_data):
    """
    Jellyfin has been inconsistent about which playback timestamp fields are
    present across versions and item types. Return a date when we can, or None
    when the record cannot be safely compared.
    """
    if not isinstance(user_data, dict):
        return None

    raw_timestamp = (
        user_data.get("LastPlayedDate")
        or user_data.get("DatePlayed")
        or user_data.get("LastPlayedDateUtc")
        or user_data.get("LastPlayedAt")
    )
    if not raw_timestamp:
        return None

    try:
        return datetime.datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None

def require_env(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def normalize_tvdb_id(raw_id):
    """
    Normalize TVDB IDs extracted from providers.
    Returns None for missing/empty/null values that would break API requests.
    """
    if raw_id is None:
        return None

    if isinstance(raw_id, str):
        value = raw_id.strip()
    else:
        value = str(raw_id).strip()

    if not value:
        return None
    if value.lower() in {"none", "null", "nan"}:
        return None
    return value

try:
    # Check and prompt for necessary environment variables
    sonarr_url = require_env('SONARR_URL')
    sonarr_key = require_env('SONARR_KEY')
    if not sonarr_url.startswith(('http://', 'https://')):
        raise ValueError("SONARR_URL must include a scheme, e.g. https://your.sonarr:8989")
    delete_by_default = os.getenv('DEFAULT_DELETE')

    # Validate and prompt for the number of days until deletion
    days_until_deletion = os.getenv('DAYS_TO_DELETE', '2')
    if days_until_deletion:
        while True:
            try:
                days_until_deletion = int(days_until_deletion)
                if days_until_deletion < 0:
                    days_until_deletion = 2
                else:
                    break
            except ValueError:
                days_until_deletion = 2
    else:
        days_until_deletion = 2

    episode_dict = {}
    invalid_ids = set()
    series_name_by_tvdb = {}

    media_service = (os.getenv('MEDIA_SERVICE', 'plex') or 'plex').lower()
    match media_service:
        case 'plex':
            plex_url = os.getenv('PLEX_URL')
            plex_token = os.getenv('PLEX_TOKEN')
            if not plex_url or not plex_token:
                raise ValueError("PLEX_URL and PLEX_TOKEN are required when MEDIA_SERVICE=plex")

            # Add 'd' to days_until_deletion
            days_until_deletion = str(days_until_deletion) + "d"

            # Set up Plex and Sonarr instances
            plex = PlexServer(plex_url, plex_token)
            showLibrary = plex.library.section('TV Shows')
            
            #Get All Unwatched Episodes watched after days until deletion and add to an array nested dictionary in the format {Show:[Episodes]}
            for episode in showLibrary.search(unwatched=False,libtype='episode',filters={"lastViewedAt<<":days_until_deletion,"genre=" if delete_by_default == "false" else "genre!=": "Delete" if delete_by_default == "false" else "Keep"}):
                show = episode.season().show()
                show_title = getattr(show, "title", "unknown series")
                tvShowKey = None
                for guid in show.guids:
                    if 'tvdb' in str(guid):
                        tvShowKey = normalize_tvdb_id(str(guid)[13:-1])
                if not tvShowKey:
                    invalid_ids.add("plex-series")
                    add_to_log(f"Skipping episode missing series tvdb id: '{episode.title}' from series '{show_title}'")
                    continue
                series_name_by_tvdb[tvShowKey] = show_title
                if tvShowKey not in episode_dict:
                    episode_dict[tvShowKey] = []
                ep_tvdb_id = None
                for guid in episode.guids:
                    if 'tvdb' in str(guid):
                        ep_tvdb_id = normalize_tvdb_id(str(guid)[13:-1])
                if ep_tvdb_id:
                    episode_dict[tvShowKey].append(ep_tvdb_id)
                else:
                    invalid_ids.add(f"plex-episode/{tvShowKey}")
                    add_to_log(
                        f"Skipping episode missing episode tvdb id: '{episode.title}' in series '{show_title}' (series tvdb id {tvShowKey})"
                    )
        
        case "jellyfin":
            jellyfin_url = os.getenv('JELLYFIN_URL')
            jellyfin_token = os.getenv('JELLYFIN_TOKEN')
            if not jellyfin_url or not jellyfin_token:
                raise ValueError("JELLYFIN_URL and JELLYFIN_TOKEN are required when MEDIA_SERVICE=jellyfin")

            client = JellyfinClient()
            client.config.data["auth.ssl"] = True
            client.config.data["app.name"] = 'sonarr_sync_app'
            client.config.data["app.version"] = '0.0.1'
            client.authenticate({"Servers": [{"AccessToken": jellyfin_token, "address": jellyfin_url}]}, discover=False)
            
            params={
                "recursive": "true",
                "includeItemTypes": "series",
                "fields": "ProviderIds",
                "isFavorite": "true"
            }

            user_id = client.jellyfin._get("Users")[0]['Id']
            favourite_query = client.jellyfin._get(f"Users/{user_id}/Items", params=params)['Items']
            favourite_series = [item['Id'] for item in favourite_query ]
            
            start_index = 0
            limit = 100

            params={
                "recursive": "true",
                "includeItemTypes": "episode",
                "fields": "ProviderIds",
                "isFavorite": "false",
                "IsMissing": "false",
                "filters":"IsPlayed",
                "SortBy":"SeriesSortName,SortName",
                "SortOrder":"Ascending",
                "Limit": str(limit),
                "StartIndex": str(start_index)
            }

            query = client.jellyfin._get(f"Users/{user_id}/Items", params=params)
            watched_episodes = query['Items']

            while query['TotalRecordCount'] > start_index:
                start_index += limit
                params['StartIndex'] = str(start_index)
                query = client.jellyfin._get(f"Users/{user_id}/Items", params=params)
                watched_episodes += query['Items']
            
            
            filtered_watched_episodes = {}
            filtered_watched_series_names = {}
            for ep in watched_episodes:
                series_id = normalize_tvdb_id(ep.get("SeriesId"))
                tvdb_id = normalize_tvdb_id(ep.get("ProviderIds", {}).get("Tvdb"))
                episode_name = ep.get("Name") or ep.get("name") or "unknown episode"
                series_name = ep.get("SeriesName") or ep.get("Series") or "unknown series"
                user_data = ep.get("UserData", {})
                last_played_date = get_last_played_date(user_data)
                if not series_id:
                    invalid_ids.add("jellyfin-series")
                    add_to_log(f"Skipping episode missing series tvdb id: '{episode_name}' in series '{series_name}'")
                    continue
                if not tvdb_id:
                    invalid_ids.add(f"jellyfin-episode/{series_id}")
                    add_to_log(f"Skipping episode missing episode tvdb id: '{episode_name}' in series '{series_name}'")
                    continue
                if (
                    series_id
                    and series_id not in favourite_series
                    and user_data.get("Played") is True
                    and last_played_date
                    and last_played_date < (datetime.datetime.today() - datetime.timedelta(days=days_until_deletion)).date()
                ):
                    if series_id:
                        if series_id not in filtered_watched_episodes:
                            filtered_watched_episodes[series_id] = []
                            filtered_watched_series_names[series_id] = series_name
                        filtered_watched_episodes[series_id].append(tvdb_id)
                    else:
                        invalid_ids.add("jellyfin-series")

            series_ids = ",".join(series_id for series_id in filtered_watched_episodes.keys() if series_id)
            if not series_ids:
                series_ids = None

            params={
                "recursive": "true",
                "includeItemTypes": "series",
                "fields": "ProviderIds",
                "ids": series_ids
            }

            series_tvdb_map = {}
            if series_ids:
                series_query = client.jellyfin._get(f"Users/{user_id}/Items", params=params)
                series_tvdb_map = {
                    normalize_tvdb_id(item["Id"]): normalize_tvdb_id(item.get("ProviderIds", {}).get("Tvdb"))
                    for item in series_query["Items"]
                    if normalize_tvdb_id(item.get("Id")) and normalize_tvdb_id(item.get("ProviderIds", {}).get("Tvdb"))
                }

            for key, value in filtered_watched_episodes.items():
                tvdb_series_id = series_tvdb_map.get(key)
                if tvdb_series_id:
                    episode_dict[tvdb_series_id] = value
                    series_name_by_tvdb[tvdb_series_id] = filtered_watched_series_names.get(key, "unknown series")
                else:
                    invalid_ids.add(f"mapped-series/{key}")
                    add_to_log(
                        f"Skipping mapped series '{filtered_watched_series_names.get(key, 'unknown series')}' (series id {key}) because tvdb mapping is missing"
                    )

    deleted_episode = False
    
    sonarr = SonarrAPI(sonarr_url, sonarr_key)
    payload = {"monitored": False}

    #Unmonitor and Delete all old watched episodes
    for tvshow_id, episode_ids in episode_dict.items():
        tvshow_id = normalize_tvdb_id(tvshow_id)
        if not tvshow_id:
            add_to_log(f"Skipping episode cleanup for invalid series id: {tvshow_id}")
            continue
        if not episode_ids:
            continue
        sonarr_series = sonarr.get_series(id_=tvshow_id,tvdb=True)[0]
        sonarr_series_title = sonarr_series['title']
        sonarr_series_id = sonarr_series['id']
        sonarr_episodes = sonarr.get_episode(id_=sonarr_series_id,series=True)
        for episode in sonarr_episodes:
            if str(episode["tvdbId"]) in episode_ids and episode['hasFile'] == True:
                deleted_episode = True
                sonarr.upd_episode(episode['id'],payload)
                sonarr.del_episode_file(episode['episodeFileId'])
                add_to_log("Unmonitored and Deleted " + sonarr_series_title + " S" + str(episode['seasonNumber']) + "E" + str(episode['episodeNumber']))
                print("Unmonitored and Deleted " + sonarr_series_title + " S" + str(episode['seasonNumber']) + "E" + str(episode['episodeNumber']))
                # If episode is last in season then unmonitor season
                season_stats = next(i for i in sonarr_series['seasons'] if i['seasonNumber'] == episode['seasonNumber'])
                if episode['episodeNumber'] == season_stats['statistics']['totalEpisodeCount']:
                    next(i for i in sonarr_series['seasons'] if i['seasonNumber'] == episode['seasonNumber'])['monitored'] = False
                    sonarr.upd_series(sonarr_series)
                    add_to_log("Unmonitored " + sonarr_series_title + " Season " + str(episode['seasonNumber']))
                    print("Unmonitored " + sonarr_series_title + " Season " + str(episode['seasonNumber']))

    match media_service:
        case 'plex':            
            showLibrary.update()
            showLibrary.emptyTrash()
        case 'jellyfin':
            client.jellyfin.refresh_library()

    add_to_log("Deleted All Watched Episodes") if deleted_episode else add_to_log(f"No Episodes to Delete from {media_service}")
    print("Deleted All Watched Episodes") if deleted_episode else print("No Episodes to Delete")

except Exception as error:
    # Surface a concise, actionable reason for failures involving URL/id construction.
    if "Id': 'None'" in str(error):
        message = (
            "Script failed due to an invalid Sonarr request id (None). "
            f"Invalid IDs observed during filtering: {', '.join(sorted(invalid_ids)) if invalid_ids else 'none'}."
        )
    elif "MissingSchema" in str(error.__class__.__name__) or "MissingSchema" in str(error):
        message = f"Script failed during Sonarr request construction. Raw error: {error}"
    else:
        message = str(error)
    add_to_log("Script failed due to " + message)
    print("Script failed due to ", message)
    sys.exit(1)

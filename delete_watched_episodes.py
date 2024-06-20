#!/usr/bin/env python

import os
from plexapi.server import PlexServer
from pyarr import SonarrAPI
import os
from dotenv import load_dotenv, set_key
from pathlib import Path
import datetime
import time

# Path to the .env file
env_path = Path('.env')

def add_to_log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.getenv('LOG_FILE'), 'a') as f:
        f.write(f'[{timestamp}] {message}\n')

try:
    # Load existing environment variables from the .env file if it exists
    if env_path.exists():
        load_dotenv(env_path)

    # Function to prompt the user for input if the environment variable is not set
    def get_env_variable(var_name, prompt):
        value = os.getenv(var_name)
        if not value:
            value = input(f"{prompt}: ")
            set_key(str(env_path), var_name, value)
        return value

    # Function to validate and prompt for a positive integer input
    def get_non_negative_integer(prompt):
        while True:
            try:
                value = int(input(f"{prompt}: "))
                if value < 0:
                    print("Please enter a non negative integer.")
                else:
                    return value
            except ValueError:
                print("Please enter a valid non negative integer.")

    # Check and prompt for necessary environment variables
    plex_url = get_env_variable('PLEX_URL', 'Please enter your Plex URL')
    plex_token = get_env_variable('PLEX_TOKEN', 'Please enter your Plex Token (Refer to https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/ for help finding)')
    sonarr_url = get_env_variable('SONARR_URL', 'Please enter your Sonarr URL')
    sonarr_key = get_env_variable('SONARR_KEY', 'Please enter your Sonarr API Key (On Sonarr go to Settings => General)')
    delete_by_default = get_env_variable('DEFAULT_DELETE', 'Do you want episodes to be deleted by default? Answer true or false')

    # Validate and prompt for the number of days until deletion
    days_until_deletion = os.getenv('DAYS_TO_DELETE')
    if days_until_deletion:
        while True:
            try:
                days_until_deletion = int(days_until_deletion)
                if days_until_deletion < 0:
                    print("DAYS_TO_DELETE must be a non negative integer.")
                    days_until_deletion = get_non_negative_integer('Please enter the number of days until deletion')
                else:
                    break
            except ValueError:
                print("DAYS_TO_DELETE must be a non negative integer.")
                days_until_deletion = get_non_negative_integer('Please enter the number of days until deletion')
    else:
        days_until_deletion = get_non_negative_integer('Please enter the number of days until deletion')

    # Set the DAYS_TO_DELETE environment variable in the .env file
    set_key(str(env_path), 'DAYS_TO_DELETE', str(days_until_deletion))

    # Add 'd' to days_until_deletion
    days_until_deletion = str(days_until_deletion) + "d"

    # Set up Plex and Sonarr instances
    plex = PlexServer(plex_url, plex_token)
    showLibrary = plex.library.section('TV Shows')
    sonarr = SonarrAPI(sonarr_url, sonarr_key)
    payload = {"monitored": False}

    episode_dict = {}
    #Get All Unwatched Episodes watched after days until deletion and add to an array nested dictionary in the format {Show:[Episodes]}
    for episode in showLibrary.search(unwatched=False,libtype='episode',filters={"lastViewedAt<<":days_until_deletion,"genre=" if delete_by_default == "false" else "genre!=": "Delete" if delete_by_default == "false" else "Keep"}):
        for guid in episode.season().show().guids:
            if 'tvdb' in str(guid):
                tvShowKey = str(guid)[13:-1]
        if tvShowKey not in episode_dict:
            episode_dict[tvShowKey] = []
        for guid in episode.guids:
            if 'tvdb' in str(guid):
                episode_dict[tvShowKey].append(int(str(guid)[13:-1]))

    #Unmonitor and Delete all old watched episodes
    for tvshow_id, episode_ids in episode_dict.items():
        sonarr_series = sonarr.get_series(id_=tvshow_id,tvdb=True)[0]
        sonarr_series_title = sonarr_series['title']
        sonarr_series_id = sonarr_series['id']
        sonarr_episodes = sonarr.get_episode(id_=sonarr_series_id,series=True)
        for episode in sonarr_episodes:
            if episode["tvdbId"] in episode_ids and episode['hasFile'] == True:
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
                
    showLibrary.update()
    showLibrary.emptyTrash()
    add_to_log("Completed")
    print("Completed")
except Exception as error:
    add_to_log("Script failed due to " + error)
    print("Script failed due to ", error)

while True:
    time.sleep(86400)
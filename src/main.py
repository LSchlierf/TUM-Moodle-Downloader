#!/bin/env python
import json

import globals
import authentication
import credential_handler
import moodle_downloader

if __name__ == "__main__":
    with open(globals.DOWNLOAD_CONFIG_PATH, mode='r', encoding='utf-8') as main_config:
        config_data = json.load(main_config)

    username, password = credential_handler.get_credentials()

    session = authentication.start_session(
        username,
        password
    )

    if session is None:
        print('Could not start Moodle session.')
        exit(1)

    globals.set_global_session(session)

    moodle_downloader.download_via_config()

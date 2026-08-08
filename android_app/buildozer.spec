[app]
title = Download Manager
package.name = downloadmanager
package.domain = com.downloadmanager
source.dir = .
# The app needs the shared core engine, which lives one level up.
source.include_patterns = ../core/*.py,../core/**/*.py
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy,requests,pyjnius
orientation = portrait
fullscreen = 0

# INTERNET: obviously, for downloads.
# ACCESS_NETWORK_STATE: lets the app check connectivity before retrying.
# WAKE_LOCK + FOREGROUND_SERVICE: needed so a download in progress
#   survives the screen turning off / the app being backgrounded --
#   not wired up yet (see README's "known gaps"), but the permissions
#   are declared now since adding them later means a manifest bump.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,FOREGROUND_SERVICE

android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# Registers this app as a handler for magnet: links and .torrent files --
# see intent_filters.xml for what's actually being injected, and
# https://buildozer.readthedocs.io for buildozer's current option name/
# format for this (it has changed across versions; verify against
# whatever buildozer version you're building with).
android.manifest.intent_filters = intent_filters.xml

[buildozer]
log_level = 2
warn_on_root = 1

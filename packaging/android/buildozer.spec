[app]
title = Renmon
package.name = renmon
package.domain = org.renmon
source.dir = app
source.include_exts = py,json,js,html,css
version = 0.1.3
requirements = python3,pyjnius,android,sqlite3,pywebview==6.2.1,typing_extensions,proxy_tools,bottle
orientation = all
fullscreen = 0
android.permissions = (name=android.permission.BLUETOOTH;maxSdkVersion=30), BLUETOOTH_CONNECT
android.api = 35
android.minapi = 26
android.ndk = 28c
android.ndk_api = 26
android.archs = arm64-v8a
android.accept_sdk_license = False
android.add_jars = vendor/pywebview-android.jar
android.allow_backup = False
p4a.hook = privacy.py
p4a.bootstrap = sdl2
p4a.branch = master
p4a.commit = 58d21141

[buildozer]
log_level = 2
warn_on_root = 1
build_dir = ../../build/android
bin_dir = ../../dist/android

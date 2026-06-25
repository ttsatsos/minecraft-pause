#!/bin/sh
set -e

# Xcode Cloud post-clone hook.
# Stamp the build number from Xcode Cloud's monotonic CI_BUILD_NUMBER so every
# cloud build supersedes the previous one on TestFlight. Without this, each build
# ships as 1.0 (1) and TestFlight offers "Open" instead of "Update" — i.e. a new
# build can look like it "doesn't have the changes". Same pattern as Almara.
#
# GENERATE_INFOPLIST_FILE = YES, so CFBundleVersion derives from the
# CURRENT_PROJECT_VERSION build setting in the pbxproj.

if [ -z "$CI_BUILD_NUMBER" ]; then
    echo "CI_BUILD_NUMBER not set — leaving build number unchanged."
    exit 0
fi

PROJECT=$(/usr/bin/find "$CI_PRIMARY_REPOSITORY_PATH" -name project.pbxproj -path '*MinecraftControl.xcodeproj*' | head -1)
if [ -z "$PROJECT" ] || [ ! -f "$PROJECT" ]; then
    echo "ERROR: MinecraftControl project.pbxproj not found under $CI_PRIMARY_REPOSITORY_PATH" >&2
    exit 1
fi

echo "Setting CURRENT_PROJECT_VERSION to $CI_BUILD_NUMBER in $PROJECT"
sed -i '' "s/CURRENT_PROJECT_VERSION = [0-9][0-9]*;/CURRENT_PROJECT_VERSION = ${CI_BUILD_NUMBER};/g" "$PROJECT"
echo "OK"

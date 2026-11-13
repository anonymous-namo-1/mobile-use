#!/bin/bash
# Build the Phone Agent APK without Gradle (javac + d8 + aapt2), signed with a local key.
set -e
cd "$(dirname "$0")"
SDK=${ANDROID_HOME:-$HOME/android-sdk}; BT=$SDK/build-tools/34.0.0; JAR=$SDK/platforms/android-34/android.jar
rm -rf build && mkdir -p build/classes build/dex build/res
"$BT/aapt2" compile --dir res -o build/res/
"$BT/aapt2" link --manifest AndroidManifest.xml -I "$JAR" --min-sdk-version 30 --target-sdk-version 34 \
    -o build/base.apk build/res/*.flat
javac -Xlint:-options --release 11 -cp "$JAR" -d build/classes $(find src -name '*.java')
"$BT/d8" --release --lib "$JAR" --min-api 30 --output build/dex $(find build/classes -name '*.class')
(cd build/dex && zip -q ../base.apk classes.dex)
"$BT/zipalign" -f 4 build/base.apk build/aligned.apk
KS=${KEYSTORE:-agent.keystore}
[ -f "$KS" ] || keytool -genkeypair -keystore "$KS" -storepass "${KS_PASS:-mobileuse}" \
    -keypass "${KS_PASS:-mobileuse}" -alias agent -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Mobile Use" >/dev/null 2>&1
"$BT/apksigner" sign --ks "$KS" --ks-pass "pass:${KS_PASS:-mobileuse}" --out build/mobile-use.apk build/aligned.apk
"$BT/apksigner" verify build/mobile-use.apk
ls -la build/mobile-use.apk

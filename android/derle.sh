#!/bin/bash
# Android widget APK'sını Gradle olmadan derler. Çıktı: HavaTahmini.apk
set -e
cd "$(dirname "$0")"
SDK="$LOCALAPPDATA/Android/Sdk"; BT="$SDK/build-tools/36.0.0"; JAR="$SDK/platforms/android-36/android.jar"
rm -rf build && mkdir -p build/gen build/classes build/dex
"$BT/aapt2.exe" compile --dir res -o build/res.zip
"$BT/aapt2.exe" link -o build/ham.apk -I "$JAR" --manifest AndroidManifest.xml --min-sdk-version 26 --target-sdk-version 34 --java build/gen build/res.zip
javac --release 8 -encoding UTF-8 -cp "$JAR" -d build/classes $(find build/gen src -name '*.java') 2>&1 | grep -v "^warning\|^Note\|^1 warning" || true
"$BT/d8.bat" --lib "$JAR" --min-api 26 --output build/dex $(find build/classes -name '*.class')
cp build/ham.apk build/tam.apk
(cd build/dex && "$JAVA_HOME/bin/jar.exe" uf ../tam.apk classes.dex)
[ -f anahtar.jks ] || keytool -genkeypair -keystore anahtar.jks -storepass havatahmini -keypass havatahmini -alias hava -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Hava Tahmini" >/dev/null 2>&1
"$BT/zipalign.exe" -f -p 4 build/tam.apk build/hiza.apk
"$BT/apksigner.bat" sign --ks anahtar.jks --ks-pass pass:havatahmini --key-pass pass:havatahmini --out HavaTahmini.apk build/hiza.apk
"$BT/apksigner.bat" verify HavaTahmini.apk && ls -la HavaTahmini.apk

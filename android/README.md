# EARNIVANTA Android

This Android app opens the live EARNIVANTA portal in a secure Android WebView so the APK uses the existing website, authentication flow, API and database rather than a second, disconnected account system.

- App ID: `com.earnivanta.app`
- Portal: `https://earnivanta.pages.dev/portal.html`
- Minimum Android: 6.0 (API 23)
- Build: GitHub Actions workflow **Build EARNIVANTA APK**
- Output: debug APK artifact for direct testing. A signed release requires a private signing key and is not created by this workflow.

The website and backend are not modified by the Android app addition.

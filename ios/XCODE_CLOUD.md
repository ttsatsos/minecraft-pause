# Xcode Cloud setup (one-time)

The repo already has everything Xcode Cloud needs to *build*:

- `MinecraftControl.xcodeproj` with a **shared scheme** (`xcshareddata/xcschemes/MinecraftControl.xcscheme`, Release archive)
- `ci_scripts/ci_post_clone.sh` — stamps the TestFlight build number from `$CI_BUILD_NUMBER`
- `ExportOptions.plist` — `app-store-connect`, team `GJ436JCWU2`

The **workflow** itself isn't a file in the repo — Xcode Cloud stores it server-side.
Create it once (same as Almara / Mama Coco):

## 1. App Store Connect record

App Store Connect → **Apps → +  → New App**
- Platform: iOS, Bundle ID: `nr10.MinecraftControl` (register it under Certificates,
  Identifiers & Profiles first if it isn't in the dropdown), name: e.g. "MC Control",
  SKU: anything (`minecraftcontrol`).

## 2. Create the workflow in Xcode

1. `cd ios && xcodegen generate && open MinecraftControl.xcodeproj`
2. Sign in with the Apple ID on team `GJ436JCWU2` (Xcode → Settings → Accounts).
3. **Product → Xcode Cloud → Create Workflow**.
4. Pick the `MinecraftControl` app/scheme. When prompted, grant Xcode Cloud access
   to the GitHub repo `ttsatsos/minecraft-pause` (authorize the Apple GitHub app).
5. Configure the workflow:
   - **Start Condition:** Branch Changes → `main`
   - **Environment:** latest Xcode, macOS
   - **Action:** Archive — iOS
   - **Post-Action:** TestFlight (Internal Testing) → your internal group (e.g. "Family")
6. Save. Xcode Cloud runs an initial build.

## 3. After it's live

- Fill `MinecraftControl/Config.swift` (or the in-app gear) with the kid's Mac
  Tailscale URL + the agent token **before** the first build you actually install.
- `git push` to `main` → Xcode Cloud builds → auto-distributes to the internal group.
  The `ci_post_clone.sh` stamp guarantees each build supersedes the last (TestFlight
  shows "Update", not "Open").
- Fallback without Xcode Cloud: `Product → Archive → Distribute App → TestFlight`.

## Regenerating the project

`project.yml` is the source of truth. After editing it:

```bash
cd ios && xcodegen generate
```

The `.xcodeproj` and the shared scheme are committed (Xcode Cloud needs them); user
state inside the project is gitignored.

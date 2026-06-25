# Remote Minecraft Parent Control

Freeze Minecraft Java Edition on a kid's Mac from a parent's iPhone in two taps.
Pressing **PAUSE** makes the game look frozen (not crashed); if the kid tries to
get back in, the game is killed.

- **Pause** → `SIGSTOP` the game's JVM. The window stays on screen showing the
  last frame, input does nothing — looks like "Dad paused my game," not a crash.
- **Guard mode** (armed automatically on pause) → a 5×/second loop watches the
  game. If the frozen process resumes, or the kid force-quits and relaunches,
  it gets `SIGKILL`'d instantly. No clever event interception — just your
  guard-mode polling idea, which is the reliable approach.
- **Resume** → `SIGCONT`, guard off. The kid is back in where they left off.
- **End game** → `SIGKILL`.

Pure Python 3 stdlib, one background process, near-zero CPU.

## Architecture

```
 iPhone (Safari / home-screen icon)         Kid's Mac Mini
 ┌───────────────────────────┐              ┌──────────────────────────────┐
 │  one giant PAUSE button    │  HTTP +tok   │ agent.py  (LaunchAgent)       │
 │  http://<mac-ip>:8731/?t=… │ ───────────► │  • serves the control page    │
 └───────────────────────────┘              │  • /api/pause /resume /kill    │
                                            │  • guard loop → SIGKILL        │
                                            └──────────────────────────────┘
```

The "app" is a web page the agent serves. Add it to your iPhone home screen and
it behaves like a native one-screen app — no Xcode, no App Store, no 7-day
re-signing. (A native wrapper can come later if you ever want it.)

## Install (on the kid's Mac, logged in as the kid)

```bash
cd minecraft-pause
bash install.sh
```

It copies the agent to `~/.minecraft-pause/`, installs a LaunchAgent that
auto-starts at login, starts it, and prints the parent URL with the token, e.g.:

```
http://192.168.1.42:8731/?t=Xy9...
```

### One-time macOS permission

So the "Minecraft paused by parent" notifications appear, allow notifications for
the agent's host (Python/osascript) if macOS prompts. Pause/kill themselves need
no special permission — the agent runs as the same user that owns the game, so it
can signal it directly. Run `install.sh` as the kid's account for that reason.

## Parent's iPhone — native app (recommended)

A native SwiftUI app lives in [`ios/`](ios/), built for the same
**Xcode Cloud → TestFlight** pipeline as the other apps (team `GJ436JCWU2`,
bundle id `nr10.MinecraftControl`, `ci_scripts/ci_post_clone.sh` build-number
stamping). One screen, one giant **PAUSE** button, live status, plus small
**Resume** / **End game** buttons. It reaches the kid's Mac over Tailscale, so it
works from anywhere — not just home Wi-Fi.

### Expose the agent over Tailscale (on the kid's Mac)

The agent listens on `127.0.0.1:8731`; `tailscale serve` fronts it as HTTPS on
your tailnet (valid cert, no ports opened to the public internet):

```bash
tailscale serve --bg 8731
tailscale serve status     # prints https://<kids-mac>.<tailnet>.ts.net
```

That `https://*.ts.net` URL + the token from `~/.minecraft-pause/token` are what
you paste into the app's setup (gear icon) — or hardcode in
[`ios/MinecraftControl/Config.swift`](ios/MinecraftControl/Config.swift) before
the first build. The app sends the token as the `X-Token` header.

### Build & ship

```bash
cd ios
xcodegen generate          # regenerate MinecraftControl.xcodeproj from project.yml
open MinecraftControl.xcodeproj
```

Then either push to `main` and let Xcode Cloud build → distribute to your
TestFlight internal group, or `Product → Archive → Distribute` once. Install via
TestFlight on the parent's iPhone; it stays installed (no 7-day expiry).

## Parent's iPhone — PWA fallback

The agent also serves the one-button control page directly. On the same Wi-Fi (or
over Tailscale), open `http://<mac>:8731/?t=<token>` in Safari →
**Share → Add to Home Screen**. No Xcode needed; you re-save the URL if the token
rotates. The native app is the better long-term option.

## Security

- Every API call requires the secret token (`~/.minecraft-pause/token`, mode
  600, auto-generated). No token → `401`.
- Treat the token like a password; rotate by deleting the token file and
  restarting the agent, then update the URL/token in the app (gear sheet).
- `tailscale serve` gives you HTTPS scoped to your tailnet (not the public
  internet). Plain HTTP is fine on a home LAN if you skip Tailscale; add a TLS
  reverse proxy only if you expose it more broadly.
- The app stores the token in `UserDefaults`. Fine for a private family app; move
  to Keychain if you want it hardened.

## Files

| File | Purpose |
|------|---------|
| `agent.py` | The whole agent: HTTP API, control page, pause/guard/kill logic |
| `install.sh` | Installs + loads the LaunchAgent, prints the parent URL |
| `uninstall.sh` | Removes the LaunchAgent |
| `ios/` | Native SwiftUI iPhone app (XcodeGen `project.yml` → `MinecraftControl.xcodeproj`, Xcode Cloud `ci_scripts/`, `ExportOptions.plist`) |

## Notes / tuning

- Process matching targets the game **JVM** (vanilla, Fabric, Forge, Prism,
  MultiMC) and deliberately ignores the Electron "Minecraft Launcher" so the
  launcher UI is never frozen/killed. Adjust `_is_game()` in `agent.py` if you
  run an unusual launcher.
- Guard poll interval: `MCPAUSE_GUARD_INTERVAL` (default `0.2`s). Port:
  `MCPAUSE_PORT` (default `8731`).
- Live logs: `tail -f ~/.minecraft-pause/agent.log`.
```

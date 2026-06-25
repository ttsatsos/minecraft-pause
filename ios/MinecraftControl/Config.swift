import Foundation

/// Build-time defaults. These seed the app the first time it launches; after that
/// they can be changed at runtime from the gear sheet (stored in UserDefaults),
/// so you don't have to rebuild to rotate the token or move the Mac.
///
/// Set both before your first Xcode Cloud build:
///   - gatewayURL: the kid's Mac as exposed by `tailscale serve` (https://*.ts.net)
///   - token:      contents of ~/.minecraft-pause/token on the kid's Mac
enum Config {
    static let defaultGatewayURL = "https://your-kids-mac.tailXXXX.ts.net"
    static let defaultToken = "PASTE_AGENT_TOKEN"
}

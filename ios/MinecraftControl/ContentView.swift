import SwiftUI

struct ContentView: View {
    @AppStorage("gatewayURL") private var gatewayURL = Config.defaultGatewayURL
    @AppStorage("token") private var token = Config.defaultToken

    @State private var status: AgentStatus?
    @State private var error: String?
    @State private var busy = false
    @State private var showSettings = false

    private var client: AgentClient { AgentClient(baseURL: gatewayURL, token: token) }
    private var isPaused: Bool { status?.mode == "paused" || status?.mode == "guarding" }
    private var isLocked: Bool { status?.locked == true }
    private var configured: Bool {
        !gatewayURL.contains("tailXXXX") && !token.contains("PASTE_AGENT_TOKEN")
            && !gatewayURL.isEmpty && !token.isEmpty
    }

    private let lockReasons: [(String, String)] = [
        ("Homework", "Time for homework."),
        ("Reading", "Time to read."),
        ("Dinner", "Time for dinner."),
        ("Come downstairs", "Come downstairs."),
    ]

    var body: some View {
        ZStack {
            Color(red: 0.043, green: 0.043, blue: 0.051).ignoresSafeArea()
            VStack(spacing: 18) {
                header
                statusLine
                pauseButton
                secondaryRow
                Divider().overlay(Color.white.opacity(0.08))
                lockRow
            }
            .padding(20)
        }
        .task { await refreshLoop() }
        .sheet(isPresented: $showSettings) {
            SettingsSheet(gatewayURL: $gatewayURL, token: $token)
        }
    }

    private var lockRow: some View {
        Group {
            if isLocked {
                Button { act { try await $0.unlock() } } label: {
                    Label("Unlock Mac", systemImage: "lock.open.fill")
                }
                .buttonStyle(LockStyle(locked: true))
            } else {
                Menu {
                    ForEach(lockReasons, id: \.0) { title, message in
                        Button(title) { act { try await $0.lock(message) } }
                    }
                    Divider()
                    Button("Just lock") { act { try await $0.lock("Locked by Dad.") } }
                } label: {
                    Label("Lock Mac", systemImage: "lock.fill")
                }
                .buttonStyle(LockStyle(locked: false))
            }
        }
        .disabled(busy || !configured)
    }

    // MARK: - Pieces

    private var header: some View {
        ZStack {
            Text("Minecraft Control")
                .font(.system(size: 17, weight: .semibold))
            HStack {
                Spacer()
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.top, 4)
    }

    private var statusLine: some View {
        let (text, color): (String, Color) = {
            if !configured { return ("Tap the gear to set the Mac URL + token", .orange) }
            if let e = error { return (e == "Wrong token" ? "Wrong token" : "Can't reach Mac", .red) }
            if isLocked { return ("Mac locked", .purple) }
            switch status?.mode {
            case "guarding", "paused": return ("Paused — guarding against restarts", .yellow)
            case "running":            return ("Minecraft is running", .green)
            case "not_running":        return ("Minecraft not running", .secondary)
            default:                   return ("Checking…", .secondary)
            }
        }()
        return HStack(spacing: 8) {
            Circle().fill(color).frame(width: 9, height: 9)
            Text(text).font(.system(size: 15)).foregroundStyle(color == .secondary ? .secondary : .primary)
        }
        .frame(minHeight: 22)
    }

    private var pauseButton: some View {
        Button {
            act { try await $0.pause() }
        } label: {
            VStack(spacing: 4) {
                Text(isPaused ? "PAUSED" : "PAUSE")
                    .font(.system(size: 44, weight: .heavy))
                if isPaused {
                    Text("guard on").font(.system(size: 20, weight: .semibold)).opacity(0.9)
                } else {
                    Text("MINECRAFT").font(.system(size: 44, weight: .heavy))
                }
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(
                LinearGradient(
                    colors: isPaused
                        ? [Color(red: 1.0, green: 0.76, blue: 0.29), Color(red: 0.96, green: 0.62, blue: 0.04)]
                        : [Color(red: 1.0, green: 0.36, blue: 0.36), Color(red: 0.83, green: 0.12, blue: 0.18)],
                    startPoint: .top, endPoint: .bottom
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        }
        .buttonStyle(PressStyle())
        .disabled(busy || !configured)
        .opacity(configured ? 1 : 0.4)
    }

    private var secondaryRow: some View {
        HStack(spacing: 12) {
            Button("Resume") { act { try await $0.resume() } }
                .buttonStyle(SecondaryStyle(tint: .primary))
            Button("End game") { act { try await $0.kill() } }
                .buttonStyle(SecondaryStyle(tint: Color(red: 1.0, green: 0.54, blue: 0.54)))
        }
        .disabled(busy || !configured)
    }

    // MARK: - Networking

    private func refreshLoop() async {
        while !Task.isCancelled {
            await refresh()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func refresh() async {
        guard configured else { return }
        do { status = try await client.status(); error = nil }
        catch { self.error = (error as? AgentError)?.errorDescription ?? error.localizedDescription }
    }

    private func act(_ op: @escaping (AgentClient) async throws -> AgentStatus) {
        guard !busy, configured else { return }
        busy = true
        let haptic = UIImpactFeedbackGenerator(style: .heavy)
        haptic.impactOccurred()
        Task {
            do { status = try await op(client); error = nil }
            catch { self.error = (error as? AgentError)?.errorDescription ?? error.localizedDescription }
            busy = false
        }
    }
}

// MARK: - Styles

private struct PressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .brightness(configuration.isPressed ? -0.05 : 0)
            .animation(.easeOut(duration: 0.08), value: configuration.isPressed)
    }
}

private struct SecondaryStyle: ButtonStyle {
    let tint: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .padding(16)
            .background(Color(red: 0.086, green: 0.086, blue: 0.102))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.08)))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.08), value: configuration.isPressed)
    }
}

private struct LockStyle: ButtonStyle {
    let locked: Bool
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 18, weight: .bold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(18)
            .background(
                LinearGradient(
                    colors: locked
                        ? [Color(red: 0.55, green: 0.35, blue: 0.9), Color(red: 0.42, green: 0.24, blue: 0.78)]
                        : [Color(red: 0.20, green: 0.20, blue: 0.24), Color(red: 0.14, green: 0.14, blue: 0.17)],
                    startPoint: .top, endPoint: .bottom
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.08), value: configuration.isPressed)
    }
}

// MARK: - Settings

private struct SettingsSheet: View {
    @Binding var gatewayURL: String
    @Binding var token: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Kid's Mac (Tailscale serve URL)") {
                    TextField("https://your-mac.tailXXXX.ts.net", text: $gatewayURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                }
                Section("Agent token") {
                    TextField("token from ~/.minecraft-pause/token", text: $token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .navigationTitle("Setup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview { ContentView() }

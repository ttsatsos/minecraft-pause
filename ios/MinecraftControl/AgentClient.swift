import Foundation

/// Mirrors the JSON returned by agent.py's /api/* endpoints.
struct AgentStatus: Decodable, Equatable {
    let mode: String          // running | paused | guarding | not_running
    let running: Bool
    let paused: Bool
    let isGuarding: Bool
    let pids: [Int]
    let locked: Bool?         // whole-device lock overlay active (older agents omit this)

    enum CodingKeys: String, CodingKey {
        case mode, running, paused, pids, locked
        case isGuarding = "guard"
    }
}

enum AgentError: LocalizedError {
    case badURL
    case http(Int)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .badURL:            return "Bad gateway URL"
        case .http(let code):    return code == 401 ? "Wrong token" : "Server error (\(code))"
        case .transport(let m):  return m
        }
    }
}

/// Thin async client for the Mac agent. Auth is the shared token via X-Token.
struct AgentClient {
    let baseURL: String
    let token: String

    private func send(_ path: String, method: String,
                      query: [String: String] = [:]) async throws -> AgentStatus {
        let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var comps = URLComponents(string: trimmed) else { throw AgentError.badURL }
        comps.path = path
        if !query.isEmpty {
            comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = comps.url else { throw AgentError.badURL }

        var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 8)
        req.httpMethod = method
        req.setValue(token, forHTTPHeaderField: "X-Token")

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else { throw AgentError.transport("No response") }
            guard (200..<300).contains(http.statusCode) else { throw AgentError.http(http.statusCode) }
            return try JSONDecoder().decode(AgentStatus.self, from: data)
        } catch let e as AgentError {
            throw e
        } catch {
            throw AgentError.transport(error.localizedDescription)
        }
    }

    func status() async throws -> AgentStatus { try await send("/api/status", method: "GET") }
    func pause()  async throws -> AgentStatus { try await send("/api/pause",  method: "POST") }
    func resume() async throws -> AgentStatus { try await send("/api/resume", method: "POST") }
    func kill()   async throws -> AgentStatus { try await send("/api/kill",   method: "POST") }
    func lock(_ reason: String) async throws -> AgentStatus {
        try await send("/api/lock", method: "POST", query: ["msg": reason])
    }
    func unlock() async throws -> AgentStatus { try await send("/api/unlock", method: "POST") }
}

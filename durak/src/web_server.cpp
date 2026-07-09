#include <cstdlib>
#include <cstring>
#include <chrono>
#include <mutex>
#include <string>

#include "eval.hpp"
#include "httplib.h"
#include "play_session.hpp"

using namespace durak;

namespace {

std::mutex g_mtx;
PlaySession g_session;

bool try_parse_seed(const std::string& body, std::uint64_t& seed) {
    const char* key = "\"seed\"";
    const std::size_t pos = body.find(key);
    if (pos == std::string::npos) return false;
    const std::size_t colon = body.find(':', pos);
    if (colon == std::string::npos) return false;
    seed = std::strtoull(body.c_str() + colon + 1, nullptr, 10);
    return true;
}

std::uint64_t fresh_seed() {
    const auto t = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    static std::uint64_t ctr = 0;
    return splitmix(static_cast<std::uint64_t>(t) ^ (++ctr * 0x9E3779B97F4A7C15ull)) & 0xFFFFFFFFu;
}

int parse_index(const std::string& body) {
    const char* key = "\"index\"";
    const std::size_t pos = body.find(key);
    if (pos == std::string::npos) return -1;
    const std::size_t colon = body.find(':', pos);
    if (colon == std::string::npos) return -1;
    return std::atoi(body.c_str() + colon + 1);
}

}  // namespace

int main(int argc, char** argv) {
    int port = 8080;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) port = std::atoi(argv[++i]);
    }

    httplib::Server svr;

    svr.set_default_headers({{"Access-Control-Allow-Origin", "*"},
                             {"Cache-Control", "no-store"}});

    svr.Options(R"(/.*)", [](const httplib::Request&, httplib::Response& res) {
        res.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        res.set_header("Access-Control-Allow-Headers", "Content-Type");
        return httplib::StatusCode::OK_200;
    });

    svr.Post("/api/new", [](const httplib::Request& req, httplib::Response& res) {
        std::lock_guard lock(g_mtx);
        std::uint64_t seed = 0;
        if (!try_parse_seed(req.body, seed)) seed = fresh_seed();
        g_session.new_game(seed, 0);
        res.set_content(g_session.to_json(), "application/json; charset=utf-8");
    });

    svr.Get("/api/state", [](const httplib::Request&, httplib::Response& res) {
        std::lock_guard lock(g_mtx);
        res.set_content(g_session.to_json(), "application/json; charset=utf-8");
    });

    svr.Post("/api/move", [](const httplib::Request& req, httplib::Response& res) {
        std::lock_guard lock(g_mtx);
        const int idx = parse_index(req.body);
        if (idx < 0 || !g_session.apply_human_move(idx)) {
            res.status = 400;
            res.set_content(R"({"error":"invalid move"})", "application/json");
            return;
        }
        res.set_content(g_session.to_json(), "application/json; charset=utf-8");
    });

    const std::string web_root = std::string(DURAK_WEB_DIR);
    svr.set_mount_point("/", web_root.c_str());

    std::printf("Durak web UI: http://localhost:%d\n", port);
    std::printf("Playing vs B2 heuristic agent\n");
    if (!svr.listen("0.0.0.0", port)) {
        std::fprintf(stderr, "Failed to listen on port %d\n", port);
        return 1;
    }
    return 0;
}

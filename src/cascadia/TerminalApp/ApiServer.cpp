// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

#include "pch.h"
#include "ApiServer.h"

#include <WinSock2.h>
#include <WS2tcpip.h>
#include <json/json.h>
#include <future>
#include <vector>
#include <algorithm>

#pragma comment(lib, "Ws2_32.lib")

using winrt::Windows::UI::Core::CoreDispatcherPriority;

namespace winrt::TerminalApp::implementation
{
    ApiServer::ApiServer(winrt::Windows::UI::Core::CoreDispatcher dispatcher,
                         ControlGetter getter,
                         BarColorSetter barColor,
                         TabLister tabLister,
                         NewTabAction newTab,
                         CloseTabAction closeTab,
                         HwndGetter hwndGetter,
                         TabColorGetter tabColorGetter,
                         TitleResolver titleResolver,
                         TabRenamer tabRenamer) :
        _dispatcher(dispatcher),
        _getControl(std::move(getter)),
        _setBarColor(std::move(barColor)),
        _listTabs(std::move(tabLister)),
        _newTab(std::move(newTab)),
        _closeTab(std::move(closeTab)),
        _hwndGetter(std::move(hwndGetter)),
        _getTabColor(std::move(tabColorGetter)),
        _resolveTitle(std::move(titleResolver)),
        _renameTab(std::move(tabRenamer))
    {
    }

    ApiServer::~ApiServer()
    {
        Stop();
    }

    void ApiServer::Start(uint16_t port)
    {
        if (_thread.joinable())
        {
            return;
        }
        _port = port;
        _stop = false;
        _thread = std::thread([this]() { _Run(); });
    }

    void ApiServer::Stop()
    {
        _stop = true;
        if (_thread.joinable())
        {
            _thread.join();
        }
    }

    static std::string _ReadLine(SOCKET s)
    {
        std::string line;
        char ch;
        while (true)
        {
            int r = recv(s, &ch, 1, 0);
            if (r != 1)
            {
                break;
            }
            if (ch == '\n')
            {
                break;
            }
            if (ch != '\r')
            {
                line.push_back(ch);
            }
            if (line.size() > 65536)
            {
                break;
            }
        }
        return line;
    }

    template<typename F>
    static auto _RunOnUI(winrt::Windows::UI::Core::CoreDispatcher const& d, F&& f) -> decltype(f())
    {
        using R = decltype(f());
        std::promise<R> p;
        auto fut = p.get_future();
        d.RunAsync(CoreDispatcherPriority::Normal, [&]() {
            try
            {
                if constexpr (std::is_void_v<R>)
                {
                    f();
                    p.set_value();
                }
                else
                {
                    p.set_value(f());
                }
            }
            catch (...)
            {
                p.set_exception(std::current_exception());
            }
        });
        return fut.get();
    }

    void ApiServer::_Run()
    {
        WSADATA wsa{};
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        {
            return;
        }
        SOCKET listener = socket(AF_INET, SOCK_STREAM, 0);
        if (listener == INVALID_SOCKET)
        {
            WSACleanup();
            return;
        }
        int reuse = 1;
        setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<char*>(&reuse), sizeof(reuse));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(_port);
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

        // Try the hinted port first, then up to +15 fallback ports. This lets
        // each WindowsTerminal window (including ones spun off by "Move tab
        // to new window") claim its own port instead of silently failing.
        bool bound = false;
        for (uint16_t off = 0; off < 16; ++off)
        {
            addr.sin_port = htons(static_cast<uint16_t>(_port + off));
            if (::bind(listener, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0 &&
                listen(listener, 5) == 0)
            {
                _port = static_cast<uint16_t>(_port + off);
                bound = true;
                break;
            }
        }
        if (!bound)
        {
            closesocket(listener);
            WSACleanup();
            return;
        }

        while (!_stop)
        {
            fd_set rs;
            FD_ZERO(&rs);
            FD_SET(listener, &rs);
            timeval tv{ 0, 200000 };
            int sel = select(0, &rs, nullptr, nullptr, &tv);
            if (sel <= 0)
            {
                continue;
            }
            SOCKET cli = accept(listener, nullptr, nullptr);
            if (cli == INVALID_SOCKET)
            {
                continue;
            }

            auto req = _ReadLine(cli);
            std::string resp;
            try
            {
                resp = _Handle(req);
            }
            catch (...)
            {
                resp = "{\"error\":\"server exception\"}";
            }
            resp.push_back('\n');
            send(cli, resp.c_str(), static_cast<int>(resp.size()), 0);
            closesocket(cli);
        }
        closesocket(listener);
        WSACleanup();
    }

    std::string ApiServer::_Handle(std::string const& line)
    {
        Json::Value reply;
        Json::CharReaderBuilder rb;
        std::unique_ptr<Json::CharReader> jr{ rb.newCharReader() };
        Json::Value req;
        std::string err;
        if (!jr->parse(line.c_str(), line.c_str() + line.size(), &req, &err))
        {
            reply["error"] = "parse error: " + err;
            Json::StreamWriterBuilder wb;
            wb["indentation"] = "";
            return Json::writeString(wb, reply);
        }
        reply["id"] = req.get("id", Json::Value::null);
        const auto method = req.get("method", "").asString();
        int tabIdx = req.get("params", Json::Value()).get("tab", -1).asInt();
        // tab_name (if present) overrides numeric tab index, so callers can
        // address tabs by stable name even after add/close shuffles indices.
        const auto tabName = req.get("params", Json::Value()).get("tab_name", "").asString();
        if (!tabName.empty() && _resolveTitle)
        {
            tabIdx = _RunOnUI(_dispatcher, [&]() -> int {
                return _resolveTitle(tabName);
            });
        }

        try
        {
            if (method == "send_text")
            {
                const auto textU = req["params"].get("text", "").asString();
                const auto text = winrt::to_hstring(textU);
                _RunOnUI(_dispatcher, [&]() {
                    if (auto c = _getControl(tabIdx))
                    {
                        c.SendInput(text);
                    }
                });
                reply["result"] = "ok";
            }
            else if (method == "get_buffer")
            {
                const auto n = req["params"].get("lines", 50).asInt();
                const auto all = _RunOnUI(_dispatcher, [&]() -> winrt::hstring {
                    if (auto c = _getControl(tabIdx))
                    {
                        return c.ReadEntireBuffer();
                    }
                    return L"";
                });
                // Sanitize UTF-16 BEFORE converting to UTF-8. Terminal text buffer
                // sometimes carries lone surrogate code units in trailing cells of
                // double-width chars; winrt::to_string would emit WTF-8 (CESU-like)
                // for those, and jsoncpp would then JSON-escape them as "\uDCxx",
                // which round-trips into Python as lone low surrogates and looks like
                // mojibake. We pair up valid surrogates and drop the orphans.
                std::wstring_view view{ all };
                std::wstring clean;
                clean.reserve(view.size());
                for (size_t i = 0; i < view.size(); ++i)
                {
                    wchar_t ch = view[i];
                    if (ch >= 0xD800 && ch <= 0xDBFF)
                    {
                        if (i + 1 < view.size() && view[i + 1] >= 0xDC00 && view[i + 1] <= 0xDFFF)
                        {
                            clean.push_back(ch);
                            clean.push_back(view[i + 1]);
                            ++i;
                        }
                    }
                    else if (ch >= 0xDC00 && ch <= 0xDFFF)
                    {
                    }
                    else
                    {
                        clean.push_back(ch);
                    }
                }
                const auto allUtf8 = winrt::to_string(clean);
                std::vector<std::string> lines;
                size_t start = 0;
                for (size_t i = 0; i <= allUtf8.size(); ++i)
                {
                    if (i == allUtf8.size() || allUtf8[i] == '\n')
                    {
                        std::string s = allUtf8.substr(start, i - start);
                        if (!s.empty() && s.back() == '\r')
                        {
                            s.pop_back();
                        }
                        lines.emplace_back(std::move(s));
                        start = i + 1;
                    }
                }
                Json::Value arr(Json::arrayValue);
                size_t take = (n <= 0) ? 0 : std::min<size_t>(static_cast<size_t>(n), lines.size());
                for (size_t i = lines.size() - take; i < lines.size(); ++i)
                {
                    arr.append(lines[i]);
                }
                Json::Value res;
                res["lines"] = arr;
                res["total_rows"] = static_cast<int>(lines.size());
                reply["result"] = res;
            }
            else if (method == "get_selection")
            {
                const bool trim = req["params"].get("trim", true).asBool();
                struct Sel { bool has; winrt::hstring text; };
                auto sel = _RunOnUI(_dispatcher, [&]() -> Sel {
                    if (auto c = _getControl(tabIdx))
                    {
                        if (c.HasSelection())
                        {
                            return { true, c.SelectedText(trim) };
                        }
                    }
                    return { false, L"" };
                });
                std::wstring_view view{ sel.text };
                std::wstring clean;
                clean.reserve(view.size());
                for (size_t i = 0; i < view.size(); ++i)
                {
                    wchar_t ch = view[i];
                    if (ch >= 0xD800 && ch <= 0xDBFF)
                    {
                        if (i + 1 < view.size() && view[i + 1] >= 0xDC00 && view[i + 1] <= 0xDFFF)
                        {
                            clean.push_back(ch);
                            clean.push_back(view[i + 1]);
                            ++i;
                        }
                    }
                    else if (ch >= 0xDC00 && ch <= 0xDFFF)
                    {
                    }
                    else
                    {
                        clean.push_back(ch);
                    }
                }
                Json::Value res;
                res["has_selection"] = sel.has;
                res["text"] = winrt::to_string(clean);
                reply["result"] = res;
            }
            else if (method == "get_scroll_state")
            {
                struct State { int offset; int view; int buf; };
                auto st = _RunOnUI(_dispatcher, [&]() -> State {
                    if (auto c = _getControl(tabIdx))
                    {
                        return { c.ScrollOffset(), c.ViewHeight(), c.BufferHeight() };
                    }
                    return { 0, 0, 0 };
                });
                const int maxOffset = (st.buf > st.view) ? (st.buf - st.view) : 0;
                const int scrolledBack = (maxOffset > st.offset) ? (maxOffset - st.offset) : 0;
                Json::Value res;
                res["scroll_offset"] = st.offset;
                res["view_height"] = st.view;
                res["buffer_height"] = st.buf;
                res["at_bottom"] = (scrolledBack == 0);
                res["scrolled_back_rows"] = scrolledBack;
                reply["result"] = res;
            }
            else if (method == "get_viewport")
            {
                struct State { winrt::hstring text; int offset; int view; };
                auto st = _RunOnUI(_dispatcher, [&]() -> State {
                    if (auto c = _getControl(tabIdx))
                    {
                        return { c.ReadEntireBuffer(), c.ScrollOffset(), c.ViewHeight() };
                    }
                    return { L"", 0, 0 };
                });
                std::wstring_view view{ st.text };
                std::wstring clean;
                clean.reserve(view.size());
                for (size_t i = 0; i < view.size(); ++i)
                {
                    wchar_t ch = view[i];
                    if (ch >= 0xD800 && ch <= 0xDBFF)
                    {
                        if (i + 1 < view.size() && view[i + 1] >= 0xDC00 && view[i + 1] <= 0xDFFF)
                        {
                            clean.push_back(ch);
                            clean.push_back(view[i + 1]);
                            ++i;
                        }
                    }
                    else if (ch >= 0xDC00 && ch <= 0xDFFF)
                    {
                    }
                    else
                    {
                        clean.push_back(ch);
                    }
                }
                const auto utf8 = winrt::to_string(clean);
                std::vector<std::string> lines;
                size_t s = 0;
                for (size_t i = 0; i <= utf8.size(); ++i)
                {
                    if (i == utf8.size() || utf8[i] == '\n')
                    {
                        std::string row = utf8.substr(s, i - s);
                        if (!row.empty() && row.back() == '\r')
                        {
                            row.pop_back();
                        }
                        lines.emplace_back(std::move(row));
                        s = i + 1;
                    }
                }
                const int start = std::max(0, st.offset);
                const int end = std::min<int>(static_cast<int>(lines.size()), start + st.view);
                Json::Value arr(Json::arrayValue);
                for (int i = start; i < end; ++i)
                {
                    arr.append(lines[i]);
                }
                Json::Value res;
                res["lines"] = arr;
                res["scroll_offset"] = st.offset;
                res["view_height"] = st.view;
                res["buffer_height_visible"] = static_cast<int>(lines.size());
                reply["result"] = res;
            }
            else if (method == "set_bar_color")
            {
                const auto hex = winrt::to_hstring(req["params"].get("color", "").asString());
                _RunOnUI(_dispatcher, [&]() {
                    if (_setBarColor)
                    {
                        _setBarColor(tabIdx, hex);
                    }
                });
                reply["result"] = "ok";
            }
            else if (method == "get_font_size")
            {
                const float cached = _lastSetFontSize.load();
                const auto size = (cached > 0.0f) ? cached : _RunOnUI(_dispatcher, [&]() -> float {
                    if (auto c = _getControl(tabIdx))
                    {
                        return c.Settings().FontSize();
                    }
                    return 0.0f;
                });
                reply["result"] = size;
            }
            else if (method == "set_font_size")
            {
                const auto target = static_cast<float>(req["params"].get("size", 12.0).asDouble());
                _RunOnUI(_dispatcher, [&]() {
                    if (auto c = _getControl(tabIdx))
                    {
                        const float baseline = (_lastSetFontSize.load() > 0.0f) ? _lastSetFontSize.load() : c.Settings().FontSize();
                        c.AdjustFontSize(target - baseline);
                    }
                });
                _lastSetFontSize.store(target);
                reply["result"] = "ok";
            }
            else if (method == "get_tab_color")
            {
                if (tabIdx < 0)
                {
                    reply["error"] = "get_tab_color requires tab or tab_name";
                }
                else
                {
                    auto hex = _RunOnUI(_dispatcher, [&]() -> winrt::hstring {
                        if (_getTabColor) return _getTabColor(tabIdx);
                        return L"";
                    });
                    Json::Value res;
                    res["color"] = winrt::to_string(hex);
                    res["has_color"] = !hex.empty();
                    res["tab"] = tabIdx;
                    reply["result"] = res;
                }
            }
            else if (method == "rename_tab")
            {
                if (tabIdx < 0)
                {
                    reply["error"] = "rename_tab requires tab or tab_name";
                }
                else
                {
                    const auto newTitle = req["params"].get("title", "").asString();
                    _RunOnUI(_dispatcher, [&]() {
                        if (_renameTab) _renameTab(tabIdx, newTitle);
                    });
                    reply["result"] = "ok";
                }
            }
            else if (method == "list_tabs")
            {
                auto tabs = _RunOnUI(_dispatcher, [&]() -> std::vector<std::pair<int, std::string>> {
                    if (_listTabs)
                    {
                        return _listTabs();
                    }
                    return {};
                });
                Json::Value arr(Json::arrayValue);
                for (auto const& [idx, title] : tabs)
                {
                    Json::Value e;
                    e["index"] = idx;
                    e["title"] = title;
                    arr.append(e);
                }
                Json::Value res;
                res["tabs"] = arr;
                res["count"] = static_cast<int>(tabs.size());
                reply["result"] = res;
            }
            else if (method == "new_tab")
            {
                _RunOnUI(_dispatcher, [&]() {
                    if (_newTab) _newTab();
                });
                reply["result"] = "ok";
            }
            else if (method == "close_tab")
            {
                const int idx = req["params"].get("tab", -1).asInt();
                if (idx < 0)
                {
                    reply["error"] = "close_tab requires params.tab (>=0)";
                }
                else
                {
                    _RunOnUI(_dispatcher, [&]() {
                        if (_closeTab) _closeTab(idx);
                    });
                    reply["result"] = "ok";
                }
            }
            else if (method == "window_action")
            {
                const auto action = req["params"].get("action", "").asString();
                HWND hwnd = _hwndGetter ? _hwndGetter() : nullptr;
                if (!hwnd)
                {
                    reply["error"] = "no hosting hwnd";
                }
                else
                {
                    int cmd = -1;
                    if (action == "maximize") cmd = SW_MAXIMIZE;
                    else if (action == "minimize") cmd = SW_MINIMIZE;
                    else if (action == "restore") cmd = SW_RESTORE;
                    else if (action == "normal") cmd = SW_SHOWNORMAL;
                    if (cmd < 0)
                    {
                        reply["error"] = "unknown action (maximize/minimize/restore/normal)";
                    }
                    else
                    {
                        ShowWindow(hwnd, cmd);
                        reply["result"] = "ok";
                    }
                }
            }
            else if (method == "get_window_rect")
            {
                HWND hwnd = _hwndGetter ? _hwndGetter() : nullptr;
                if (!hwnd)
                {
                    reply["error"] = "no hosting hwnd";
                }
                else
                {
                    RECT r{};
                    GetWindowRect(hwnd, &r);
                    WINDOWPLACEMENT pl{ sizeof(pl) };
                    GetWindowPlacement(hwnd, &pl);
                    const bool maximized = (pl.showCmd == SW_SHOWMAXIMIZED);
                    const bool minimized = (pl.showCmd == SW_SHOWMINIMIZED);
                    Json::Value res;
                    res["x"] = static_cast<int>(r.left);
                    res["y"] = static_cast<int>(r.top);
                    res["width"] = static_cast<int>(r.right - r.left);
                    res["height"] = static_cast<int>(r.bottom - r.top);
                    res["maximized"] = maximized;
                    res["minimized"] = minimized;
                    reply["result"] = res;
                }
            }
            else if (method == "set_window_rect")
            {
                HWND hwnd = _hwndGetter ? _hwndGetter() : nullptr;
                if (!hwnd)
                {
                    reply["error"] = "no hosting hwnd";
                }
                else
                {
                    RECT cur{};
                    GetWindowRect(hwnd, &cur);
                    const int x = req["params"].get("x", static_cast<int>(cur.left)).asInt();
                    const int y = req["params"].get("y", static_cast<int>(cur.top)).asInt();
                    const int w = req["params"].get("width", static_cast<int>(cur.right - cur.left)).asInt();
                    const int h = req["params"].get("height", static_cast<int>(cur.bottom - cur.top)).asInt();
                    MoveWindow(hwnd, x, y, w, h, TRUE);
                    reply["result"] = "ok";
                }
            }
            else
            {
                reply["error"] = "unknown method: " + method;
            }
        }
        catch (winrt::hresult_error const& e)
        {
            reply["error"] = "winrt hresult: " + winrt::to_string(e.message());
        }
        catch (std::exception const& e)
        {
            reply["error"] = std::string{ "std exception: " } + e.what();
        }
        catch (...)
        {
            reply["error"] = "unknown exception";
        }

        Json::StreamWriterBuilder wb;
        wb["indentation"] = "";
        return Json::writeString(wb, reply);
    }
}

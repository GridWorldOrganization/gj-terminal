// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.
//
// ApiServer: external control endpoint for WindowsTerminal.
// TCP listener on 127.0.0.1:<port>, line-based JSON-RPC:
//   send_text       { text: "..." }     -> ok
//   get_buffer      { lines: N }        -> { lines: [..., latest last] }
//   set_font_size   { size: float }     -> ok

#pragma once

#include <atomic>
#include <thread>
#include <functional>

namespace winrt::TerminalApp::implementation
{
    class ApiServer
    {
    public:
        // index < 0 = active control; otherwise indexed tab.
        using ControlGetter = std::function<winrt::Microsoft::Terminal::Control::TermControl(int)>;
        // tab < 0 = TabRow background (whole bar); tab >= 0 = individual tab tint
        using BarColorSetter = std::function<void(int tab, winrt::hstring const&)>;
        // tab >= 0 returns hex like "#rrggbb"; "" if no color set or invalid index
        using TabColorGetter = std::function<winrt::hstring(int tab)>;
        using TitleResolver = std::function<int(std::string const& title)>;
        using TabRenamer = std::function<void(int tab, std::string const& title)>;
        // Returns list of (index, title) for all tabs.
        using TabLister = std::function<std::vector<std::pair<int, std::string>>()>;
        using NewTabAction = std::function<void()>;
        using CloseTabAction = std::function<void(int)>;
        using HwndGetter = std::function<HWND()>;

        ApiServer(winrt::Windows::UI::Core::CoreDispatcher dispatcher,
                  ControlGetter getter,
                  BarColorSetter barColor,
                  TabLister tabLister,
                  NewTabAction newTab,
                  CloseTabAction closeTab,
                  HwndGetter hwndGetter,
                  TabColorGetter tabColorGetter,
                  TitleResolver titleResolver,
                  TabRenamer tabRenamer);
        ~ApiServer();

        ApiServer(const ApiServer&) = delete;
        ApiServer& operator=(const ApiServer&) = delete;

        void Start(uint16_t port);
        void Stop();

    private:
        void _Run();
        std::string _Handle(std::string const& line);

        winrt::Windows::UI::Core::CoreDispatcher _dispatcher{ nullptr };
        ControlGetter _getControl;
        BarColorSetter _setBarColor;
        TabLister _listTabs;
        NewTabAction _newTab;
        CloseTabAction _closeTab;
        HwndGetter _hwndGetter;
        TabColorGetter _getTabColor;
        TitleResolver _resolveTitle;
        TabRenamer _renameTab;
        std::atomic<bool> _stop{ false };
        std::atomic<float> _lastSetFontSize{ -1.0f };
        std::thread _thread;
        uint16_t _port{ 0 };
    };
}

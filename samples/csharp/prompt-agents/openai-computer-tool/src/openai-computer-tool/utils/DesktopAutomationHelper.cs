// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace OpenAIComputerTool.Utils;

/// <summary>
/// Local Windows desktop helper for executing OpenAI Computer Tool (<c>computer_call</c>) actions.
/// Translates each batched action returned by the Azure AI Foundry Prompt Agent
/// (<c>click</c>, <c>double_click</c>, <c>triple_click</c>, <c>move</c>, <c>drag</c>, <c>scroll</c>,
/// <c>type</c>, <c>keypress</c>, <c>wait</c>, <c>screenshot</c>) into OS-level mouse and keyboard
/// operations via Win32 <c>user32.dll</c> and captures desktop screenshots encoded as PNG via
/// <see cref="Graphics.CopyFromScreen(int, int, int, int, Size)"/> for <c>computer_call_output</c>.
/// </summary>
public static class DesktopAutomationHelper
{
    private const int SmCxScreen = 0;
    private const int SmCyScreen = 1;

    private const uint MouseEventLeftDown = 0x0002;
    private const uint MouseEventLeftUp = 0x0004;
    private const uint MouseEventRightDown = 0x0008;
    private const uint MouseEventRightUp = 0x0010;
    private const uint MouseEventMiddleDown = 0x0020;
    private const uint MouseEventMiddleUp = 0x0040;
    private const uint MouseEventWheel = 0x0800;
    private const uint MouseEventHWheel = 0x01000;

    private const uint KeyEventKeyUp = 0x0002;
    private const uint KeyEventUnicode = 0x0004;
    private const uint InputKeyboard = 1;

    private static bool s_dpiInitialized;

    private static readonly Dictionary<string, byte> KeyMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ENTER"] = 0x0D,
        ["RETURN"] = 0x0D,
        ["TAB"] = 0x09,
        ["SPACE"] = 0x20,
        ["BACKSPACE"] = 0x08,
        ["DELETE"] = 0x2E,
        ["ESC"] = 0x1B,
        ["ESCAPE"] = 0x1B,
        ["UP"] = 0x26,
        ["DOWN"] = 0x28,
        ["LEFT"] = 0x25,
        ["RIGHT"] = 0x27,
        ["PAGEUP"] = 0x21,
        ["PAGEDOWN"] = 0x22,
        ["HOME"] = 0x24,
        ["END"] = 0x23,
        ["CTRL"] = 0x11,
        ["CONTROL"] = 0x11,
        ["ALT"] = 0x12,
        ["SHIFT"] = 0x10,
        ["WIN"] = 0x5B,
        ["META"] = 0x5B,
        ["CMD"] = 0x5B,
        ["F1"] = 0x70,
        ["F2"] = 0x71,
        ["F3"] = 0x72,
        ["F4"] = 0x73,
        ["F5"] = 0x74,
        ["F6"] = 0x75,
        ["F7"] = 0x76,
        ["F8"] = 0x77,
        ["F9"] = 0x78,
        ["F10"] = 0x79,
        ["F11"] = 0x7A,
        ["F12"] = 0x7B,
    };

    public static void HandleAction(JsonElement action)
    {
        EnsureWindowsDesktop();
        CheckFailSafeCorner();

        string type = action.GetProperty("type").GetString() ?? string.Empty;
        switch (type)
        {
            case "screenshot":
                break;

            case "click":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                string button = action.TryGetProperty("button", out JsonElement btnProp)
                    ? btnProp.GetString() ?? "left"
                    : "left";
                Click(x, y, button, clicks: 1);
                break;
            }

            case "double_click":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                Click(x, y, "left", clicks: 2);
                break;
            }

            case "triple_click":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                Click(x, y, "left", clicks: 3);
                break;
            }

            case "move":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                SmoothMoveTo(x, y, durationMs: 100);
                break;
            }

            case "drag":
            {
                if (!action.TryGetProperty("path", out JsonElement pathProp) ||
                    pathProp.ValueKind != JsonValueKind.Array ||
                    pathProp.GetArrayLength() == 0)
                {
                    break;
                }

                List<(int X, int Y)> points = [];
                foreach (JsonElement pt in pathProp.EnumerateArray())
                {
                    points.Add((pt.GetProperty("x").GetInt32(), pt.GetProperty("y").GetInt32()));
                }

                SmoothMoveTo(points[0].X, points[0].Y, durationMs: 100);
                mouse_event(MouseEventLeftDown, 0, 0, 0, UIntPtr.Zero);
                Thread.Sleep(50);

                for (int i = 1; i < points.Count; i++)
                {
                    SmoothMoveTo(points[i].X, points[i].Y, durationMs: 120);
                }

                Thread.Sleep(50);
                mouse_event(MouseEventLeftUp, 0, 0, 0, UIntPtr.Zero);
                break;
            }

            case "scroll":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                SetCursorPos(x, y);

                int scrollY = action.TryGetProperty("scroll_y", out JsonElement syProp) ? syProp.GetInt32() : 0;
                if (scrollY != 0)
                {
                    int wheelDelta = (-scrollY / 100) * 120;
                    if (wheelDelta == 0)
                    {
                        wheelDelta = scrollY > 0 ? -120 : 120;
                    }

                    mouse_event(MouseEventWheel, 0, 0, unchecked((uint)wheelDelta), UIntPtr.Zero);
                }

                int scrollX = action.TryGetProperty("scroll_x", out JsonElement sxProp) ? sxProp.GetInt32() : 0;
                if (scrollX != 0)
                {
                    int hWheelDelta = (scrollX / 100) * 120;
                    if (hWheelDelta == 0)
                    {
                        hWheelDelta = scrollX > 0 ? 120 : -120;
                    }

                    mouse_event(MouseEventHWheel, 0, 0, unchecked((uint)hWheelDelta), UIntPtr.Zero);
                }

                break;
            }

            case "type":
            {
                string text = action.GetProperty("text").GetString() ?? string.Empty;
                TypeText(text);
                break;
            }

            case "keypress":
            {
                if (!action.TryGetProperty("keys", out JsonElement keysProp) ||
                    keysProp.ValueKind != JsonValueKind.Array)
                {
                    break;
                }

                List<string> rawKeys = [];
                foreach (JsonElement k in keysProp.EnumerateArray())
                {
                    string? val = k.GetString();
                    if (!string.IsNullOrEmpty(val))
                    {
                        rawKeys.Add(val);
                    }
                }

                PressKeys(rawKeys);
                break;
            }

            case "wait":
            {
                int ms = action.TryGetProperty("ms", out JsonElement msProp) ? msProp.GetInt32() : 1000;
                Thread.Sleep(Math.Max(0, ms));
                break;
            }
        }

        Thread.Sleep(50);
    }

    public static string TakeDesktopScreenshot()
    {
        EnsureWindowsDesktop();

        int width = GetSystemMetrics(SmCxScreen);
        int height = GetSystemMetrics(SmCyScreen);
        if (width <= 0 || height <= 0)
        {
            throw new InvalidOperationException("Failed to query primary desktop dimensions.");
        }

        using Bitmap bitmap = new(width, height, PixelFormat.Format32bppArgb);
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.CopyFromScreen(0, 0, 0, 0, new Size(width, height), CopyPixelOperation.SourceCopy);
        }

        using MemoryStream ms = new();
        bitmap.Save(ms, ImageFormat.Png);
        return Convert.ToBase64String(ms.ToArray());
    }

    private static void EnsureWindowsDesktop()
    {
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            throw new PlatformNotSupportedException(
                "DesktopAutomationHelper requires a Windows desktop session at runtime.");
        }

        if (!s_dpiInitialized)
        {
            SetProcessDPIAware();
            s_dpiInitialized = true;
        }
    }

    private static void CheckFailSafeCorner()
    {
        if (GetCursorPos(out POINT pt) && pt.X <= 1 && pt.Y <= 1)
        {
            throw new InvalidOperationException(
                "Fail-safe triggered because mouse cursor is in the top-left corner of the screen.");
        }
    }

    private static void Click(int x, int y, string button, int clicks)
    {
        SetCursorPos(x, y);
        Thread.Sleep(30);

        (uint downFlag, uint upFlag) = button.ToLowerInvariant() switch
        {
            "right" => (MouseEventRightDown, MouseEventRightUp),
            "middle" or "wheel" => (MouseEventMiddleDown, MouseEventMiddleUp),
            _ => (MouseEventLeftDown, MouseEventLeftUp),
        };

        for (int i = 0; i < clicks; i++)
        {
            mouse_event(downFlag, 0, 0, 0, UIntPtr.Zero);
            Thread.Sleep(25);
            mouse_event(upFlag, 0, 0, 0, UIntPtr.Zero);
            if (i + 1 < clicks)
            {
                Thread.Sleep(60);
            }
        }
    }

    private static void SmoothMoveTo(int targetX, int targetY, int durationMs)
    {
        if (!GetCursorPos(out POINT start))
        {
            SetCursorPos(targetX, targetY);
            return;
        }

        const int steps = 8;
        int sleepPerStep = Math.Max(5, durationMs / steps);
        for (int i = 1; i <= steps; i++)
        {
            int curX = start.X + ((targetX - start.X) * i / steps);
            int curY = start.Y + ((targetY - start.Y) * i / steps);
            SetCursorPos(curX, curY);
            Thread.Sleep(sleepPerStep);
        }
    }

    private static void TypeText(string text)
    {
        foreach (char ch in text)
        {
            if (ch == '\r')
            {
                continue;
            }

            if (ch == '\n')
            {
                keybd_event(0x0D, 0, 0, UIntPtr.Zero);
                Thread.Sleep(15);
                keybd_event(0x0D, 0, KeyEventKeyUp, UIntPtr.Zero);
                Thread.Sleep(20);
                continue;
            }

            INPUT[] inputs = new INPUT[2];
            inputs[0].type = InputKeyboard;
            inputs[0].u.ki.wScan = ch;
            inputs[0].u.ki.dwFlags = KeyEventUnicode;

            inputs[1].type = InputKeyboard;
            inputs[1].u.ki.wScan = ch;
            inputs[1].u.ki.dwFlags = KeyEventUnicode | KeyEventKeyUp;

            _ = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
            Thread.Sleep(20);
        }
    }

    private static void PressKeys(List<string> keys)
    {
        List<byte> vks = [];
        foreach (string key in keys)
        {
            if (TryResolveVirtualKey(key, out byte vk))
            {
                vks.Add(vk);
            }
        }

        if (vks.Count == 0)
        {
            return;
        }

        foreach (byte vk in vks)
        {
            keybd_event(vk, 0, 0, UIntPtr.Zero);
            Thread.Sleep(20);
        }

        for (int i = vks.Count - 1; i >= 0; i--)
        {
            keybd_event(vks[i], 0, KeyEventKeyUp, UIntPtr.Zero);
            Thread.Sleep(20);
        }

        if (vks.Count == 1 && vks[0] == 0x5B)
        {
            Thread.Sleep(600);
        }
    }

    private static bool TryResolveVirtualKey(string key, out byte vk)
    {
        if (KeyMap.TryGetValue(key, out vk))
        {
            return true;
        }

        if (key.Length == 1)
        {
            char upper = char.ToUpperInvariant(key[0]);
            if ((upper >= 'A' && upper <= 'Z') || (upper >= '0' && upper <= '9'))
            {
                vk = (byte)upper;
                return true;
            }

            short mapped = VkKeyScanW(key[0]);
            if (mapped != -1)
            {
                vk = (byte)(mapped & 0xFF);
                return true;
            }
        }

        vk = 0;
        return false;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public InputUnion u;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)]
        public MOUSEINPUT mi;

        [FieldOffset(0)]
        public KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [DllImport("user32.dll")]
    private static extern bool SetProcessDPIAware();

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT lpPoint);

    [DllImport("user32.dll")]
    private static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern short VkKeyScanW(char ch);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
}

// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.Buffers.Binary;
using System.IO.Compression;
using System.Text.Json;

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Pure managed C# 1280x800 in-container Virtual Paint Desktop with a built-in
/// bitmap font renderer, toolbar buttons (<c>Oval</c>, <c>Brush</c>, <c>Fill</c>,
/// <c>Yellow</c>, <c>Black</c>, <c>Blue</c>, <c>Red</c>, <c>Green</c>, <c>Clear</c>,
/// <c>Save</c>), drawing primitives, and a zero-dependency PNG encoder.
/// Runs identically inside Linux containers, Azure Hosted Agent sandboxes, and Windows.
/// </summary>
public sealed class VirtualPaintDesktop
{
    public const int ScreenWidth = 1280;
    public const int ScreenHeight = 800;

    private readonly byte[] _rgb = new byte[ScreenWidth * ScreenHeight * 3];
    private readonly List<ToolbarButton> _buttons;
    private readonly string _outputFile;

    private string _currentTool = "oval";
    private RgbColor _currentColor = new(255, 215, 0); // Yellow
    private string _statusMessage = "Virtual Paint Ready (1280x800)";
    private int _cursorX = ScreenWidth / 2;
    private int _cursorY = ScreenHeight / 2;

    public VirtualPaintDesktop(string outputFile)
    {
        _outputFile = outputFile;
        _buttons =
        [
            new("Oval",   10,  42,  85,  82, new(225, 225, 225), () => SelectTool("oval")),
            new("Brush",  95,  42, 175,  82, new(225, 225, 225), () => SelectTool("brush")),
            new("Fill",  185,  42, 255,  82, new(225, 225, 225), () => SelectTool("fill")),
            new("Yellow",275,  42, 365,  82, new(255, 215,   0), () => SelectColor(new(255, 215, 0), "Yellow")),
            new("Black", 375,  42, 455,  82, new( 20,  20,  20), () => SelectColor(new(0, 0, 0), "Black")),
            new("Blue",  465,  42, 540,  82, new( 30, 136, 229), () => SelectColor(new(30, 136, 229), "Blue")),
            new("Red",   550,  42, 620,  82, new(229,  57,  53), () => SelectColor(new(229, 57, 53), "Red")),
            new("Green", 630,  42, 710,  82, new( 67, 160,  71), () => SelectColor(new(67, 160, 71), "Green")),
            new("Clear", 730,  42, 810,  82, new(245, 245, 245), ClearCanvas),
            new("Save",  820,  42, 900,  82, new(209, 231, 221), SaveImage),
        ];

        ResetDesktop();
    }

    public string OutputFile => _outputFile;

    public static string BuildPaintPrompt(string outputFile) =>
        PaintSmileyScenario.BuildPaintPrompt(outputFile);

    public void HandleAction(JsonElement action)
    {
        string actionType = action.TryGetProperty("type", out JsonElement typeProp)
            ? typeProp.GetString() ?? string.Empty
            : string.Empty;

        switch (actionType)
        {
            case "click":
            case "double_click":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                _cursorX = ClampX(x);
                _cursorY = ClampY(y);
                HandleClick(_cursorX, _cursorY);
                break;
            }

            case "move":
            {
                int x = action.GetProperty("x").GetInt32();
                int y = action.GetProperty("y").GetInt32();
                _cursorX = ClampX(x);
                _cursorY = ClampY(y);
                break;
            }

            case "drag":
            {
                if (!action.TryGetProperty("path", out JsonElement pathProp) ||
                    pathProp.ValueKind != JsonValueKind.Array ||
                    pathProp.GetArrayLength() < 2)
                {
                    break;
                }

                List<(int X, int Y)> points = [];
                foreach (JsonElement pt in pathProp.EnumerateArray())
                {
                    points.Add((ClampX(pt.GetProperty("x").GetInt32()), ClampY(pt.GetProperty("y").GetInt32())));
                }

                HandleDrag(points);
                _cursorX = points[^1].X;
                _cursorY = points[^1].Y;
                SaveImage();
                break;
            }

            case "keypress":
            {
                if (action.TryGetProperty("keys", out JsonElement keysProp) &&
                    keysProp.ValueKind == JsonValueKind.Array)
                {
                    List<string> keys = [];
                    foreach (JsonElement k in keysProp.EnumerateArray())
                    {
                        string? s = k.GetString();
                        if (!string.IsNullOrEmpty(s))
                        {
                            keys.Add(s.ToLowerInvariant());
                        }
                    }

                    if (keys.Contains("s") && (keys.Contains("ctrl") || keys.Contains("control")))
                    {
                        SaveImage();
                    }
                }

                break;
            }

            case "type":
            case "scroll":
            case "wait":
            case "screenshot":
                break;
        }
    }

    public string TakeScreenshotBase64()
    {
        byte[] pngBytes = EncodeRgbToPng(_rgb, ScreenWidth, ScreenHeight);
        return Convert.ToBase64String(pngBytes);
    }

    public void SaveImage()
    {
        byte[] pngBytes = EncodeRgbToPng(_rgb, ScreenWidth, ScreenHeight);
        string? dir = Path.GetDirectoryName(_outputFile);
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        File.WriteAllBytes(_outputFile, pngBytes);
        _statusMessage = $"Saved: {Path.GetFileName(_outputFile)}";
        RenderToolbar();
        pngBytes = EncodeRgbToPng(_rgb, ScreenWidth, ScreenHeight);
        File.WriteAllBytes(_outputFile, pngBytes);
    }

    private void SelectTool(string tool)
    {
        _currentTool = tool;
        _statusMessage = $"Tool: {tool} | Color: {FormatColorName(_currentColor)}";
        RenderToolbar();
    }

    private void SelectColor(RgbColor color, string name)
    {
        _currentColor = color;
        _statusMessage = $"Tool: {_currentTool} | Color: {name}";
        RenderToolbar();
    }

    private void ClearCanvas()
    {
        FillRect(10, 95, ScreenWidth - 10, ScreenHeight - 10, new(255, 255, 255));
        DrawRectOutline(10, 95, ScreenWidth - 10, ScreenHeight - 10, new(180, 180, 180), 2);
        _statusMessage = "Canvas cleared";
        RenderToolbar();
    }

    private void ResetDesktop()
    {
        // Window background
        FillRect(0, 0, ScreenWidth - 1, ScreenHeight - 1, new(240, 240, 240));
        // Window title bar
        FillRect(0, 0, ScreenWidth - 1, 34, new(31, 41, 55));
        DrawText(16, 10, "PAINT - OPENAI COMPUTER TOOL VIRTUAL DESKTOP (1280X800)", new(255, 255, 255), scale: 2);

        // White drawing canvas
        FillRect(10, 95, ScreenWidth - 10, ScreenHeight - 10, new(255, 255, 255));
        DrawRectOutline(10, 95, ScreenWidth - 10, ScreenHeight - 10, new(180, 180, 180), 2);

        RenderToolbar();
    }

    private void RenderToolbar()
    {
        // Toolbar strip
        FillRect(0, 35, ScreenWidth - 1, 90, new(230, 230, 230));

        foreach (ToolbarButton btn in _buttons)
        {
            FillRect(btn.X1, btn.Y1, btn.X2, btn.Y2, btn.Fill);

            bool isSelected =
                string.Equals(btn.Label, _currentTool, StringComparison.OrdinalIgnoreCase) ||
                (btn.Label == "Yellow" && _currentColor == new RgbColor(255, 215, 0)) ||
                (btn.Label == "Black" && _currentColor == new RgbColor(0, 0, 0));

            RgbColor borderColor = isSelected ? new(13, 110, 253) : new(90, 90, 90);
            int borderThickness = isSelected ? 3 : 1;
            DrawRectOutline(btn.X1, btn.Y1, btn.X2, btn.Y2, borderColor, borderThickness);

            RgbColor textColor = btn.Label == "Black" ? new(255, 255, 255) : new(20, 20, 20);
            int textWidth = btn.Label.Length * 12;
            int textX = btn.X1 + Math.Max(4, ((btn.X2 - btn.X1) - textWidth) / 2);
            int textY = btn.Y1 + 13;
            DrawText(textX, textY, btn.Label.ToUpperInvariant(), textColor, scale: 2);
        }

        // Status text area on the right of the toolbar
        DrawText(920, 55, _statusMessage.ToUpperInvariant(), new(45, 55, 72), scale: 2);
    }

    private void HandleClick(int x, int y)
    {
        foreach (ToolbarButton btn in _buttons)
        {
            if (x >= btn.X1 && x <= btn.X2 && y >= btn.Y1 && y <= btn.Y2)
            {
                btn.OnClick();
                return;
            }
        }

        if (y >= 95 && _currentTool == "fill")
        {
            FloodFillCanvas(_currentColor);
        }
    }

    private void HandleDrag(List<(int X, int Y)> points)
    {
        (int x0, int y0) = points[0];
        if (y0 < 95)
        {
            HandleClick(x0, y0);
            return;
        }

        if (_currentTool == "oval")
        {
            (int x1, int y1) = points[^1];
            FillEllipse(x0, y0, x1, y1, _currentColor, new(0, 0, 0));
        }
        else
        {
            for (int i = 0; i + 1 < points.Count; i++)
            {
                DrawThickLine(points[i].X, points[i].Y, points[i + 1].X, points[i + 1].Y, _currentColor, radius: 5);
            }
        }
    }

    private void FloodFillCanvas(RgbColor color)
    {
        FillRect(12, 97, ScreenWidth - 12, ScreenHeight - 12, color);
    }

    private void FillEllipse(int x0, int y0, int x1, int y1, RgbColor fill, RgbColor outline)
    {
        int left = Math.Max(12, Math.Min(x0, x1));
        int right = Math.Min(ScreenWidth - 12, Math.Max(x0, x1));
        int top = Math.Max(97, Math.Min(y0, y1));
        int bottom = Math.Min(ScreenHeight - 12, Math.Max(y0, y1));

        double cx = (left + right) / 2.0;
        double cy = (top + bottom) / 2.0;
        double rx = Math.Max(2.0, (right - left) / 2.0);
        double ry = Math.Max(2.0, (bottom - top) / 2.0);

        for (int y = top; y <= bottom; y++)
        {
            double dy = (y - cy) / ry;
            for (int x = left; x <= right; x++)
            {
                double dx = (x - cx) / rx;
                double dist = (dx * dx) + (dy * dy);
                if (dist <= 1.0)
                {
                    SetPixel(x, y, dist >= 0.90 ? outline : fill);
                }
            }
        }
    }

    private void DrawThickLine(int x0, int y0, int x1, int y1, RgbColor color, int radius)
    {
        int steps = Math.Max(Math.Abs(x1 - x0), Math.Abs(y1 - y0));
        if (steps == 0)
        {
            FillCircle(x0, y0, radius, color);
            return;
        }

        for (int i = 0; i <= steps; i++)
        {
            int x = x0 + ((x1 - x0) * i / steps);
            int y = y0 + ((y1 - y0) * i / steps);
            if (y >= 96)
            {
                FillCircle(x, y, radius, color);
            }
        }
    }

    private void FillCircle(int cx, int cy, int r, RgbColor color)
    {
        int r2 = r * r;
        for (int dy = -r; dy <= r; dy++)
        {
            for (int dx = -r; dx <= r; dx++)
            {
                if ((dx * dx) + (dy * dy) <= r2)
                {
                    SetPixel(cx + dx, cy + dy, color);
                }
            }
        }
    }

    private void FillRect(int x0, int y0, int x1, int y1, RgbColor color)
    {
        int left = Math.Clamp(Math.Min(x0, x1), 0, ScreenWidth - 1);
        int right = Math.Clamp(Math.Max(x0, x1), 0, ScreenWidth - 1);
        int top = Math.Clamp(Math.Min(y0, y1), 0, ScreenHeight - 1);
        int bottom = Math.Clamp(Math.Max(y0, y1), 0, ScreenHeight - 1);

        for (int y = top; y <= bottom; y++)
        {
            int rowOffset = y * ScreenWidth * 3;
            for (int x = left; x <= right; x++)
            {
                int idx = rowOffset + (x * 3);
                _rgb[idx] = color.R;
                _rgb[idx + 1] = color.G;
                _rgb[idx + 2] = color.B;
            }
        }
    }

    private void DrawRectOutline(int x0, int y0, int x1, int y1, RgbColor color, int thickness)
    {
        for (int t = 0; t < thickness; t++)
        {
            FillRect(x0 + t, y0 + t, x1 - t, y0 + t, color);
            FillRect(x0 + t, y1 - t, x1 - t, y1 - t, color);
            FillRect(x0 + t, y0 + t, x0 + t, y1 - t, color);
            FillRect(x1 - t, y0 + t, x1 - t, y1 - t, color);
        }
    }

    private void SetPixel(int x, int y, RgbColor color)
    {
        if (x < 0 || x >= ScreenWidth || y < 0 || y >= ScreenHeight)
        {
            return;
        }

        int idx = ((y * ScreenWidth) + x) * 3;
        _rgb[idx] = color.R;
        _rgb[idx + 1] = color.G;
        _rgb[idx + 2] = color.B;
    }

    private void DrawText(int x, int y, string text, RgbColor color, int scale = 2)
    {
        int cursorX = x;
        foreach (char c in text)
        {
            if (Glyphs.TryGetValue(c, out byte[]? rows))
            {
                for (int row = 0; row < 7; row++)
                {
                    byte bits = rows[row];
                    for (int col = 0; col < 5; col++)
                    {
                        if (((bits >> (4 - col)) & 1) != 0)
                        {
                            for (int sy = 0; sy < scale; sy++)
                            {
                                for (int sx = 0; sx < scale; sx++)
                                {
                                    SetPixel(cursorX + (col * scale) + sx, y + (row * scale) + sy, color);
                                }
                            }
                        }
                    }
                }
            }

            cursorX += 6 * scale;
        }
    }

    private static string FormatColorName(RgbColor c) =>
        c switch
        {
            { R: 255, G: 215, B: 0 } => "Yellow",
            { R: 0, G: 0, B: 0 } => "Black",
            { R: 30, G: 136, B: 229 } => "Blue",
            { R: 229, G: 57, B: 53 } => "Red",
            { R: 67, G: 160, B: 71 } => "Green",
            _ => "Custom",
        };

    private static int ClampX(int x) => Math.Clamp(x, 0, ScreenWidth - 1);

    private static int ClampY(int y) => Math.Clamp(y, 0, ScreenHeight - 1);

    private static byte[] EncodeRgbToPng(byte[] rgb, int width, int height)
    {
        using MemoryStream output = new();
        output.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);

        Span<byte> ihdr = stackalloc byte[13];
        BinaryPrimitives.WriteInt32BigEndian(ihdr[..4], width);
        BinaryPrimitives.WriteInt32BigEndian(ihdr.Slice(4, 4), height);
        ihdr[8] = 8;  // 8-bit depth
        ihdr[9] = 2;  // Truecolor RGB
        ihdr[10] = 0; // Deflate compression
        ihdr[11] = 0; // Adaptive filtering
        ihdr[12] = 0; // No interlace
        WritePngChunk(output, "IHDR"u8, ihdr);

        int rowStride = width * 3;
        int scanlineBytes = rowStride + 1;
        byte[] rawScanlines = new byte[scanlineBytes * height];
        for (int y = 0; y < height; y++)
        {
            int dstOffset = y * scanlineBytes;
            rawScanlines[dstOffset] = 0; // Filter: None
            Buffer.BlockCopy(rgb, y * rowStride, rawScanlines, dstOffset + 1, rowStride);
        }

        using (MemoryStream compressed = new())
        {
            using (ZLibStream zlib = new(compressed, CompressionLevel.Fastest, leaveOpen: true))
            {
                zlib.Write(rawScanlines, 0, rawScanlines.Length);
            }

            WritePngChunk(output, "IDAT"u8, compressed.GetBuffer().AsSpan(0, (int)compressed.Length));
        }

        WritePngChunk(output, "IEND"u8, ReadOnlySpan<byte>.Empty);
        return output.ToArray();
    }

    private static void WritePngChunk(Stream stream, ReadOnlySpan<byte> chunkType, ReadOnlySpan<byte> data)
    {
        Span<byte> lengthBytes = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(lengthBytes, (uint)data.Length);
        stream.Write(lengthBytes);
        stream.Write(chunkType);
        if (!data.IsEmpty)
        {
            stream.Write(data);
        }

        uint crc = 0xFFFFFFFFu;
        crc = UpdateCrc32(crc, chunkType);
        crc = UpdateCrc32(crc, data);
        crc = ~crc;

        Span<byte> crcBytes = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(crcBytes, crc);
        stream.Write(crcBytes);
    }

    private static uint UpdateCrc32(uint crc, ReadOnlySpan<byte> buffer)
    {
        foreach (byte b in buffer)
        {
            crc ^= b;
            for (int i = 0; i < 8; i++)
            {
                crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320u : crc >> 1;
            }
        }

        return crc;
    }

    private readonly record struct RgbColor(byte R, byte G, byte B);

    private sealed record ToolbarButton(
        string Label,
        int X1,
        int Y1,
        int X2,
        int Y2,
        RgbColor Fill,
        Action OnClick);

    // Compact 5x7 uppercase bitmap font so button labels are crisp in container screenshots.
    private static readonly Dictionary<char, byte[]> Glyphs = new()
    {
        ['A'] = [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
        ['B'] = [0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110],
        ['C'] = [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
        ['D'] = [0b11100, 0b10010, 0b10001, 0b10001, 0b10001, 0b10010, 0b11100],
        ['E'] = [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111],
        ['F'] = [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000],
        ['G'] = [0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110],
        ['H'] = [0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
        ['I'] = [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
        ['J'] = [0b00111, 0b00010, 0b00010, 0b00010, 0b10010, 0b10010, 0b01100],
        ['K'] = [0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001],
        ['L'] = [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
        ['M'] = [0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001],
        ['N'] = [0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001, 0b10001],
        ['O'] = [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
        ['P'] = [0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000],
        ['Q'] = [0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101],
        ['R'] = [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
        ['S'] = [0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110],
        ['T'] = [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
        ['U'] = [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
        ['V'] = [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
        ['W'] = [0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b11011, 0b10001],
        ['X'] = [0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001],
        ['Y'] = [0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100],
        ['Z'] = [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111],
        ['0'] = [0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110],
        ['1'] = [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
        ['2'] = [0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111],
        ['3'] = [0b11110, 0b00001, 0b00001, 0b01110, 0b00001, 0b00001, 0b11110],
        ['4'] = [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
        ['5'] = [0b11111, 0b10000, 0b10000, 0b11110, 0b00001, 0b00001, 0b11110],
        ['6'] = [0b01110, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110],
        ['7'] = [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000],
        ['8'] = [0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110],
        ['9'] = [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b01110],
        [':'] = [0b00000, 0b00100, 0b00100, 0b00000, 0b00100, 0b00100, 0b00000],
        ['-'] = [0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000],
        ['_'] = [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b11111],
        ['.'] = [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00100, 0b00100],
        ['('] = [0b00010, 0b00100, 0b01000, 0b01000, 0b01000, 0b00100, 0b00010],
        [')'] = [0b01000, 0b00100, 0b00010, 0b00010, 0b00010, 0b00100, 0b01000],
        ['|'] = [0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
        [' '] = [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    };
}

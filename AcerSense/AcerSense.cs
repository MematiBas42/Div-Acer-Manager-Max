using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace DivAcerManagerMax;

/// <summary>
///     Client for communicating with the AcerSense daemon over Unix socket
/// </summary>
public class AcerSense : IDisposable
{
    private const string SocketPath = "/var/run/AcerSense.sock";

    /// <summary>
    ///     Send a command to the AcerSense daemon and receive response
    /// </summary>
    /// <param name="command">Command name</param>
    /// <param name="parameters">Optional parameters</param>
    /// <returns>Response from daemon as a JsonDocument</returns>
    private const int MaxRetryAttempts = 3;

    private const int RetryDelayMs = 500;

    // Cache of available features
    private HashSet<string> _availableFeatures = new();

    private bool _disposed;
    private Socket _socket;

    public AcerSense()
    {
        IsConnected = false;
    }

    public bool IsConnected { get; private set; }

    // Events
    public event EventHandler<string> ThermalProfileChanged;
    public event EventHandler<FanSpeedSettings> FanSpeedChanged;
    public event EventHandler<bool> PowerStateChanged;

    private Socket _eventSocket;
    private bool _isListening;
    private Task _listeningTask;
    private CancellationTokenSource _cancellationTokenSource;

    /// <summary>
    /// Starts the background listener for daemon events
    /// </summary>
    public void StartListening()
    {
        if (_isListening) return;
        _isListening = true;
        _cancellationTokenSource = new CancellationTokenSource();
        _listeningTask = Task.Run(() => ListenLoopAsync(_cancellationTokenSource.Token));
    }

    private async Task ListenLoopAsync(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            try
            {
                if (_eventSocket != null) try { _eventSocket.Dispose(); } catch { }

                _eventSocket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.IP);
                var endpoint = new UnixDomainSocketEndPoint(SocketPath);
                
                await _eventSocket.ConnectAsync(endpoint, token);
                
                using var stream = new NetworkStream(_eventSocket, false);
                using var reader = new StreamReader(stream, Encoding.UTF8);

                while (!token.IsCancellationRequested)
                {
                    // Read line-by-line (Framing)
                    var jsonString = await reader.ReadLineAsync();
                    if (jsonString == null) break; // Disconnected

                    if (!string.IsNullOrWhiteSpace(jsonString))
                        ProcessIncomingMessage(jsonString);
                }
            }
            catch (Exception)
            {
                // Retry loop
            }

            if (!token.IsCancellationRequested)
                await Task.Delay(2000, token);
        }
    }

    public async Task<JsonDocument> SendCommandAsync(string command, Dictionary<string, object> parameters = null)
    {
        var attempt = 0;
        while (attempt < MaxRetryAttempts)
            try
            {
                if (!IsConnected)
                {
                    await ConnectAsync();
                    if (!IsConnected) throw new InvalidOperationException("Not connected to daemon");
                }

                var request = new
                {
                    command,
                    @params = parameters ?? new Dictionary<string, object>()
                };

                // Append Newline Delimiter
                var requestJson = JsonSerializer.Serialize(request) + "\n";
                var requestBytes = Encoding.UTF8.GetBytes(requestJson);

                await _socket.SendAsync(requestBytes, SocketFlags.None);

                // Read response line-by-line using NetworkStream for framing
                // We use a temporary stream wrapper for the read operation to utilize StreamReader
                // Note: We don't dispose the stream here as it would close the socket
                using var stream = new NetworkStream(_socket, false);
                using var reader = new StreamReader(stream, Encoding.UTF8, false, 4096, true); // leaveOpen=true

                var responseJson = await reader.ReadLineAsync();
                
                if (responseJson != null)
                {
                    return JsonDocument.Parse(responseJson);
                }

                IsConnected = false;
                attempt++;
                await Task.Delay(RetryDelayMs);
            }
            catch (Exception ex)
            {
                // Console.WriteLine($"Error communicating: {ex.Message}");
                IsConnected = false;
                attempt++;
                await Task.Delay(RetryDelayMs);
            }

        throw new IOException($"Failed to communicate with daemon after {MaxRetryAttempts} attempts");
    }

    /// <summary>
    ///     Get all settings from the AcerSense daemon
    /// </summary>
    /// <returns>All settings as a JsonDocument</returns>
    public async Task<AcerSenseSettings> GetAllSettingsAsync()
    {
        var response = await SendCommandAsync("get_all_settings");
        var success = response.RootElement.GetProperty("success").GetBoolean();

        if (success)
        {
            var data = response.RootElement.GetProperty("data");
            var settings = JsonSerializer.Deserialize<AcerSenseSettings>(data.GetRawText());

            // Update available features cache
            if (settings.AvailableFeatures != null)
                _availableFeatures = new HashSet<string>(settings.AvailableFeatures);

            return settings;
        }

        var error = response.RootElement.GetProperty("error").GetString();
        throw new Exception($"Failed to get settings: {error}");
    }

    /// <summary>
    ///     Set thermal profile
    /// </summary>
    /// <param name="profile">Profile name</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetThermalProfileAsync(string profile)
    {
        if (!IsFeatureAvailable("thermal_profile"))
        {
            Console.WriteLine("Thermal profile feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "profile", profile }
        };

        var response = await SendCommandAsync("set_thermal_profile", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set fan speeds
    /// </summary>
    /// <param name="cpu">CPU fan speed (0-100)</param>
    /// <param name="gpu">GPU fan speed (0-100)</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetFanSpeedAsync(int cpu, int gpu)
    {
        if (!IsFeatureAvailable("fan_speed"))
        {
            Console.WriteLine("Fan speed control is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "cpu", cpu },
            { "gpu", gpu }
        };

        var response = await SendCommandAsync("set_fan_speed", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set backlight timeout
    /// </summary>
    /// <param name="enabled">Enable or disable timeout</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetBacklightTimeoutAsync(bool enabled)
    {
        if (!IsFeatureAvailable("backlight_timeout"))
        {
            Console.WriteLine("Backlight timeout feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_backlight_timeout", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set battery calibration
    /// </summary>
    /// <param name="enabled">Start or stop calibration</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetBatteryCalibrationAsync(bool enabled)
    {
        if (!IsFeatureAvailable("battery_calibration"))
        {
            Console.WriteLine("Battery calibration feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_battery_calibration", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set battery limiter
    /// </summary>
    /// <param name="enabled">Enable or disable battery limit</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetBatteryLimiterAsync(bool enabled)
    {
        if (!IsFeatureAvailable("battery_limiter"))
        {
            Console.WriteLine("Battery limiter feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_battery_limiter", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set boot animation sound
    /// </summary>
    /// <param name="enabled">Enable or disable boot sound</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetBootAnimationSoundAsync(bool enabled)
    {
        if (!IsFeatureAvailable("boot_animation_sound"))
        {
            Console.WriteLine("Boot animation sound feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_boot_animation_sound", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set LCD override
    /// </summary>
    /// <param name="enabled">Enable or disable LCD override</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetLcdOverrideAsync(bool enabled)
    {
        if (!IsFeatureAvailable("lcd_override"))
        {
            Console.WriteLine("LCD override feature is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_lcd_override", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set USB charging level
    /// </summary>
    /// <param name="level">USB charging level (0, 10, 20, or 30)</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetUsbChargingAsync(int level)
    {
        if (!IsFeatureAvailable("usb_charging"))
        {
            Console.WriteLine("USB charging control is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "level", level }
        };

        var response = await SendCommandAsync("set_usb_charging", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set keyboard per-zone mode colors
    /// </summary>
    /// <param name="zone1">Zone 1 color (hex RGB)</param>
    /// <param name="zone2">Zone 2 color (hex RGB)</param>
    /// <param name="zone3">Zone 3 color (hex RGB)</param>
    /// <param name="zone4">Zone 4 color (hex RGB)</param>
    /// <param name="brightness">Brightness (0-100)</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetPerZoneModeAsync(string zone1, string zone2, string zone3, string zone4, int brightness)
    {
        if (!IsFeatureAvailable("per_zone_mode"))
        {
            Console.WriteLine("Per-zone keyboard mode is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "zone1", zone1 },
            { "zone2", zone2 },
            { "zone3", zone3 },
            { "zone4", zone4 },
            { "brightness", brightness }
        };

        var response = await SendCommandAsync("set_per_zone_mode", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set keyboard lighting effect
    /// </summary>
    /// <param name="mode">Effect mode (0-7)</param>
    /// <param name="speed">Effect speed (0-9)</param>
    /// <param name="brightness">Brightness (0-100)</param>
    /// <param name="direction">Direction (1=right to left, 2=left to right)</param>
    /// <param name="red">Red component (0-255)</param>
    /// <param name="green">Green component (0-255)</param>
    /// <param name="blue">Blue component (0-255)</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetFourZoneModeAsync(int mode, int speed, int brightness, int direction, int red, int green,
        int blue)
    {
        if (!IsFeatureAvailable("four_zone_mode"))
        {
            Console.WriteLine("Four-zone keyboard mode is not available on this device");
            return false;
        }

        var parameters = new Dictionary<string, object>
        {
            { "mode", mode },
            { "speed", speed },
            { "brightness", brightness },
            { "direction", direction },
            { "red", red },
            { "green", green },
            { "blue", blue }
        };

        var response = await SendCommandAsync("set_four_zone_mode", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set Hyprland integration status
    /// </summary>
    /// <param name="enabled">Enable or disable integration</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetHyprlandIntegrationAsync(bool enabled)
    {
        var parameters = new Dictionary<string, object>
        {
            { "enabled", enabled }
        };

        var response = await SendCommandAsync("set_hyprland_integration", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set default profile preference
    /// </summary>
    /// <param name="source">"ac" or "bat"</param>
    /// <param name="profile">Profile name</param>
    /// <returns>True if successful</returns>
    public async Task<bool> SetDefaultProfilePreferenceAsync(string source, string profile)
    {
        var parameters = new Dictionary<string, object>
        {
            { "source", source },
            { "profile", profile }
        };

        var response = await SendCommandAsync("set_default_profile_preference", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    /// <summary>
    ///     Set Hyprland opacity settings
    /// </summary>
    public async Task<bool> SetHyprlandOpacitySettingsAsync(double acActive, double acInactive, double batActive, double batInactive)
    {
        var parameters = new Dictionary<string, object>
        {
            { "ac_active", acActive },
            { "ac_inactive", acInactive },
            { "bat_active", batActive },
            { "bat_inactive", batInactive }
        };

        var response = await SendCommandAsync("set_hyprland_opacity_settings", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    protected virtual void Dispose(bool disposing)
    {
        if (_disposed) return;

        if (disposing)
        {
            Disconnect();
            _socket?.Dispose();
        }

        _disposed = true;
    }

    private string FormatFeatureName(string featureName)
    {
        if (string.IsNullOrEmpty(featureName))
            return featureName;

        var withSpaces = featureName.Replace('_', ' ');
        return char.ToUpper(withSpaces[0]) + withSpaces.Substring(1);
    }
}

/// <summary>
///     Models for AcerSense settings
/// </summary>
public class AcerSenseSettings
{
    [JsonPropertyName("laptop_type")] public string LaptopType { get; set; } = "UNKNOWN";

    [JsonPropertyName("has_four_zone_kb")] public bool HasFourZoneKb { get; set; }

    [JsonPropertyName("available_features")]
    public List<string> AvailableFeatures { get; set; } = new();

    [JsonPropertyName("version")] public string Version { get; set; } = "NOT CONNECTED PROPERLY";
    [JsonPropertyName("driver_version")] public string DriverVersion { get; set; } = "DRIVER VERSION NOT FOUND";


    [JsonPropertyName("thermal_profile")] public ThermalProfileSettings ThermalProfile { get; set; } = new();

    [JsonPropertyName("backlight_timeout")]
    public string BacklightTimeout { get; set; } = "0";

    [JsonPropertyName("battery_calibration")]
    public string BatteryCalibration { get; set; } = "0";

    [JsonPropertyName("battery_limiter")] public string BatteryLimiter { get; set; } = "0";

    [JsonPropertyName("boot_animation_sound")]
    public string BootAnimationSound { get; set; } = "0";

    [JsonPropertyName("fan_speed")] public FanSpeedSettings FanSpeed { get; set; } = new();

    [JsonPropertyName("lcd_override")] public string LcdOverride { get; set; } = "0";

    [JsonPropertyName("usb_charging")] public string UsbCharging { get; set; } = "0";

    [JsonPropertyName("per_zone_mode")] public string PerZoneMode { get; set; } = "";

    [JsonPropertyName("four_zone_mode")] public string FourZoneMode { get; set; } = "";

    [JsonPropertyName("modprobe_parameter")]
    public string ModprobeParameter { get; set; } = "";

    [JsonPropertyName("hyprland_integration")]
    public bool HyprlandIntegration { get; set; }

    [JsonPropertyName("default_ac_profile")]
    public string DefaultAcProfile { get; set; } = "balanced";

    [JsonPropertyName("default_bat_profile")]
    public string DefaultBatProfile { get; set; } = "low-power";

    [JsonPropertyName("ac_active_opacity")]
    public double AcActiveOpacity { get; set; } = 0.97;

    [JsonPropertyName("ac_inactive_opacity")]
    public double AcInactiveOpacity { get; set; } = 0.95;

    [JsonPropertyName("bat_active_opacity")]
    public double BatActiveOpacity { get; set; } = 1.0;

    [JsonPropertyName("bat_inactive_opacity")]
    public double BatInactiveOpacity { get; set; } = 1.0;
}

public class ThermalProfileSettings
{
    [JsonPropertyName("current")] public string Current { get; set; } = "balanced";

    [JsonPropertyName("available")] public List<string> Available { get; set; } = new();
}

public class FanSpeedSettings
{
    [JsonPropertyName("cpu")] public string Cpu { get; set; } = "0";

    [JsonPropertyName("gpu")] public string Gpu { get; set; } = "0";
}
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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
    private const int MaxRetryAttempts = 3;
    private const int RetryDelayMs = 500;

    // Cache of available features
    private HashSet<string> _availableFeatures = new();

    private bool _disposed;
    private Socket? _socket;
    private Socket? _eventSocket;
    private bool _isListening;
    private Task? _listeningTask;
    private CancellationTokenSource? _cancellationTokenSource;

    // Events
    public event EventHandler<string>? ThermalProfileChanged;
    public event EventHandler<FanSpeedSettings>? FanSpeedChanged;
    public event EventHandler<bool>? PowerStateChanged;

    public AcerSense()
    {
        IsConnected = false;
    }

    public bool IsConnected { get; private set; }

    public bool IsFeatureAvailable(string featureName)
    {
        return _availableFeatures.Contains(featureName);
    }

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
                    var jsonString = await reader.ReadLineAsync();
                    if (jsonString == null) break; 

                    if (!string.IsNullOrWhiteSpace(jsonString))
                        ProcessIncomingMessage(jsonString);
                }
            }
            catch (Exception)
            {
                // Retry
            }

            if (!token.IsCancellationRequested)
                await Task.Delay(2000, token);
        }
    }

    private void ProcessIncomingMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("type", out var typeProp) && 
                typeProp.GetString() == "event")
            {
                var eventName = doc.RootElement.GetProperty("event").GetString();
                var data = doc.RootElement.GetProperty("data");

                switch (eventName)
                {
                    case "thermal_profile_changed":
                        var profile = data.GetProperty("profile").GetString();
                        if (profile != null) ThermalProfileChanged?.Invoke(this, profile);
                        break;
                    case "fan_speed_changed":
                        var fanData = JsonSerializer.Deserialize<FanSpeedSettings>(data.GetRawText());
                        if (fanData != null) FanSpeedChanged?.Invoke(this, fanData);
                        break;
                    case "power_state_changed":
                        var isAc = data.GetProperty("plugged_in").GetBoolean();
                        PowerStateChanged?.Invoke(this, isAc);
                        break;
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error processing event: {ex.Message}");
        }
    }

    private async Task<bool> ValidateConnection()
    {
        if (!IsConnected) return false;
        try
        {
            var response = await SendCommandAsync("ping");
            return response.RootElement.GetProperty("success").GetBoolean();
        }
        catch
        {
            IsConnected = false;
            return false;
        }
    }

    public async Task<bool> ConnectAsync()
    {
        try
        {
            if (IsConnected && await ValidateConnection()) return true;

            _socket?.Dispose();
            _socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.IP);
            var endpoint = new UnixDomainSocketEndPoint(SocketPath);

            await _socket.ConnectAsync(endpoint);
            IsConnected = true;

            await RefreshAvailableFeaturesAsync();
            return true;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Failed to connect to daemon: {ex.Message}");
            IsConnected = false;
            return false;
        }
    }

    private async Task RefreshAvailableFeaturesAsync()
    {
        try
        {
            var response = await SendCommandAsync("get_supported_features");
            if (response.RootElement.GetProperty("success").GetBoolean())
            {
                var features = response.RootElement.GetProperty("data").GetProperty("available_features");
                _availableFeatures.Clear();
                foreach (var feature in features.EnumerateArray())
                {
                    var name = feature.GetString();
                    if (name != null)
                        _availableFeatures.Add(FormatFeatureName(name));
                }
            }
        }
        catch { }
    }

    public void Disconnect()
    {
        if (IsConnected)
        {
            try { _socket?.Close(); } catch { }
            finally { IsConnected = false; }
        }
    }

    public async Task<JsonDocument> SendCommandAsync(string command, Dictionary<string, object>? parameters = null)
    {
        var attempt = 0;
        while (attempt < MaxRetryAttempts)
        {
            try
            {
                if (!IsConnected && !await ConnectAsync()) throw new IOException("Not connected");

                var request = new { command, @params = parameters ?? new Dictionary<string, object>() };
                var requestBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request) + "\n");

                if (_socket == null) throw new IOException("Socket is null");
                await _socket.SendAsync(requestBytes, SocketFlags.None);

                using var stream = new NetworkStream(_socket, false);
                using var reader = new StreamReader(stream, Encoding.UTF8, false, 4096, true);
                var responseJson = await reader.ReadLineAsync();
                
                if (responseJson != null) return JsonDocument.Parse(responseJson);

                IsConnected = false;
            }
            catch { IsConnected = false; }
            attempt++;
            await Task.Delay(RetryDelayMs);
        }
        throw new IOException("Communication failed");
    }

    public async Task<AcerSenseSettings> GetAllSettingsAsync()
    {
        var response = await SendCommandAsync("get_all_settings");
        if (response.RootElement.GetProperty("success").GetBoolean())
        {
            var data = response.RootElement.GetProperty("data");
            var settings = JsonSerializer.Deserialize<AcerSenseSettings>(data.GetRawText());
            if (settings?.AvailableFeatures != null)
                _availableFeatures = new HashSet<string>(settings.AvailableFeatures);
            return settings ?? new AcerSenseSettings();
        }
        throw new Exception("Failed to get settings");
    }

    public async Task<bool> SetThermalProfileAsync(string profile)
    {
        try {
            if (!IsFeatureAvailable("thermal_profile")) return false;
            var response = await SendCommandAsync("set_thermal_profile", new Dictionary<string, object> { { "profile", profile } });
            return response.RootElement.TryGetProperty("success", out var successProp) && successProp.GetBoolean();
        } catch { return false; }
    }

    public async Task<bool> SetFanSpeedAsync(int cpu, int gpu)
    {
        try {
            if (!IsFeatureAvailable("fan_speed")) return false;
            var response = await SendCommandAsync("set_fan_speed", new Dictionary<string, object> { { "cpu", cpu }, { "gpu", gpu } });
            return response.RootElement.TryGetProperty("success", out var successProp) && successProp.GetBoolean();
        } catch { return false; }
    }

    public async Task<bool> SetBacklightTimeoutAsync(bool enabled)
    {
        if (!IsFeatureAvailable("backlight_timeout")) return false;
        var response = await SendCommandAsync("set_backlight_timeout", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetBatteryCalibrationAsync(bool enabled)
    {
        if (!IsFeatureAvailable("battery_calibration")) return false;
        var response = await SendCommandAsync("set_battery_calibration", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetBatteryLimiterAsync(bool enabled)
    {
        if (!IsFeatureAvailable("battery_limiter")) return false;
        var response = await SendCommandAsync("set_battery_limiter", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetBootAnimationSoundAsync(bool enabled)
    {
        if (!IsFeatureAvailable("boot_animation_sound")) return false;
        var response = await SendCommandAsync("set_boot_animation_sound", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetLcdOverrideAsync(bool enabled)
    {
        if (!IsFeatureAvailable("lcd_override")) return false;
        var response = await SendCommandAsync("set_lcd_override", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetUsbChargingAsync(int level)
    {
        if (!IsFeatureAvailable("usb_charging")) return false;
        var response = await SendCommandAsync("set_usb_charging", new Dictionary<string, object> { { "level", level } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetPerZoneModeAsync(string zone1, string zone2, string zone3, string zone4, int brightness)
    {
        if (!IsFeatureAvailable("per_zone_mode")) return false;
        var parameters = new Dictionary<string, object> { { "zone1", zone1 }, { "zone2", zone2 }, { "zone3", zone3 }, { "zone4", zone4 }, { "brightness", brightness } };
        var response = await SendCommandAsync("set_per_zone_mode", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetFourZoneModeAsync(int mode, int speed, int brightness, int direction, int red, int green, int blue)
    {
        if (!IsFeatureAvailable("four_zone_mode")) return false;
        var parameters = new Dictionary<string, object> { { "mode", mode }, { "speed", speed }, { "brightness", brightness }, { "direction", direction }, { "red", red }, { "green", green }, { "blue", blue } };
        var response = await SendCommandAsync("set_four_zone_mode", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetHyprlandIntegrationAsync(bool enabled)
    {
        var response = await SendCommandAsync("set_hyprland_integration", new Dictionary<string, object> { { "enabled", enabled } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetDefaultProfilePreferenceAsync(string source, string profile)
    {
        var response = await SendCommandAsync("set_default_profile_preference", new Dictionary<string, object> { { "source", source }, { "profile", profile } });
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public async Task<bool> SetHyprlandOpacitySettingsAsync(double acActive, double acInactive, double batActive, double batInactive)
    {
        var parameters = new Dictionary<string, object> { { "ac_active", acActive }, { "ac_inactive", acInactive }, { "bat_active", batActive }, { "bat_inactive", batInactive } };
        var response = await SendCommandAsync("set_hyprland_opacity_settings", parameters);
        return response.RootElement.GetProperty("success").GetBoolean();
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (_disposed) return;
        if (disposing)
        {
            _cancellationTokenSource?.Cancel();
            _cancellationTokenSource?.Dispose();
            Disconnect();
            _socket?.Dispose();
            _eventSocket?.Dispose();
        }
        _disposed = true;
    }

    private string FormatFeatureName(string featureName)
    {
        if (string.IsNullOrEmpty(featureName)) return string.Empty;
        var withSpaces = featureName.Replace('_', ' ');
        return char.ToUpper(withSpaces[0]) + withSpaces.Substring(1);
    }
}

public class AcerSenseSettings
{
    [JsonPropertyName("laptop_type")] public string LaptopType { get; set; } = "UNKNOWN";
    [JsonPropertyName("has_four_zone_kb")] public bool HasFourZoneKb { get; set; }
    [JsonPropertyName("available_features")] public List<string> AvailableFeatures { get; set; } = new();
    [JsonPropertyName("version")] public string Version { get; set; } = "1.0.0";
    [JsonPropertyName("driver_version")] public string DriverVersion { get; set; } = "Unknown";
    [JsonPropertyName("thermal_profile")] public ThermalProfileSettings ThermalProfile { get; set; } = new();
    [JsonPropertyName("backlight_timeout")] public string BacklightTimeout { get; set; } = "0";
    [JsonPropertyName("battery_calibration")] public string BatteryCalibration { get; set; } = "0";
    [JsonPropertyName("battery_limiter")] public string BatteryLimiter { get; set; } = "0";
    [JsonPropertyName("boot_animation_sound")] public string BootAnimationSound { get; set; } = "0";
    [JsonPropertyName("fan_speed")] public FanSpeedSettings FanSpeed { get; set; } = new();
    [JsonPropertyName("fan_rpms")] public FanSpeedSettings FanRpms { get; set; } = new();
    [JsonPropertyName("lcd_override")] public string LcdOverride { get; set; } = "0";
    [JsonPropertyName("usb_charging")] public string UsbCharging { get; set; } = "0";
    [JsonPropertyName("per_zone_mode")] public string PerZoneMode { get; set; } = "";
    [JsonPropertyName("four_zone_mode")] public string FourZoneMode { get; set; } = "";
    [JsonPropertyName("modprobe_parameter")] public string ModprobeParameter { get; set; } = "";
    [JsonPropertyName("hyprland_integration")] public bool HyprlandIntegration { get; set; }
    [JsonPropertyName("default_ac_profile")] public string DefaultAcProfile { get; set; } = "balanced";
    [JsonPropertyName("default_bat_profile")] public string DefaultBatProfile { get; set; } = "low-power";
    [JsonPropertyName("ac_active_opacity")] public double AcActiveOpacity { get; set; } = 0.97;
    [JsonPropertyName("ac_inactive_opacity")] public double AcInactiveOpacity { get; set; } = 0.95;
    [JsonPropertyName("bat_active_opacity")] public double BatActiveOpacity { get; set; } = 1.0;
    [JsonPropertyName("bat_inactive_opacity")] public double BatInactiveOpacity { get; set; } = 1.0;
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

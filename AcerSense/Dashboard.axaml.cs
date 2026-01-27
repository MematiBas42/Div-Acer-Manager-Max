using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Animation;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Threading;
using LiveChartsCore;
using LiveChartsCore.Measure;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Avalonia;
using LiveChartsCore.SkiaSharpView.Painting;
using Material.Icons.Avalonia;
using SkiaSharp;

namespace DivAcerManagerMax;

public partial class Dashboard : UserControl, INotifyPropertyChanged
{
    private const int REFRESH_INTERVAL_MS = 2000;
    private const int MAX_HISTORY_POINTS = 60;
    private const int MIN_RPM_FOR_ANIMATION = 100;
    private const double MAX_ANIMATION_DURATION = 5.0;
    private const double MIN_ANIMATION_DURATION = 0.05;
    private const int RPM_CHANGE_THRESHOLD = 500;

    private readonly RotateTransform _cpuFanRotateTransform = new();
    private readonly RotateTransform _gpuFanRotateTransform = new();
    private readonly DispatcherTimer _refreshTimer;
    private readonly Dictionary<string, string> _systemInfoPaths = new();

    private bool _animationsInitialized;
    private string? _batteryDir;
    private int _batteryPercentageInt;
    private string _batteryStatus = "Unknown";
    private string _batteryTimeRemainingString = "0";
    private Animation? _cpuFanAnimation;
    private int _cpuFanSpeedRpm;
    private string _cpuName = "Unknown CPU";
    private double _cpuTemp;
    private ObservableCollection<double> _cpuTempHistory = new();
    private double _cpuUsage;
    private Animation? _gpuFanAnimation;
    private int _gpuFanSpeedRpm;
    private string _gpuName = "Unknown GPU";
    private double _gpuTemp;
    private ObservableCollection<double> _gpuTempHistory = new();
    private GpuType _gpuType = GpuType.Unknown;
    private double _gpuUsage;
    private bool _hasBattery;
    private string _kernelVersion = "Unknown";
    private int _lastCpuRpm;
    private int _lastGpuRpm;
    private string _osVersion = "Unknown";
    private string _ramTotal = "Unknown";
    private double _ramUsage;
    private CartesianChart? _temperatureChart;
    private ObservableCollection<ISeries> _tempSeries = new();
    private AcerSense? _client;
    private long _lastTotalTime;
    private long _lastIdleTime;

    public Dashboard()
    {
        InitializeComponent();
        DataContext = this;

        // Initialize rotate transforms
        _cpuFanRotateTransform = new RotateTransform();
        _gpuFanRotateTransform = new RotateTransform();

        // Initialize default values for battery properties
        BatteryPercentage.Text = "0";
        BatteryTimeRemaining.Text = "0";
        BatteryStatus = "Unknown";

        // Fetch static system information once at initialization
        InitializeStaticSystemInfo();

        // Setup refresh timer but don't start it yet - will start when visible
        _refreshTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(REFRESH_INTERVAL_MS)
        };
        _refreshTimer.Tick += RefreshDynamicMetrics;

        // Initial refresh
        RefreshDynamicMetricsAsync();
    }

    public void SetClient(AcerSense client)
    {
        if (_client == client) return; // Prevent double subscription
        
        if (_client != null)
        {
            _client.FanSpeedChanged -= OnFanSpeedChanged;
            _client.PowerStateChanged -= OnPowerStateChanged;
        }

        _client = client;
        if (_client != null)
        {
            _client.FanSpeedChanged += OnFanSpeedChanged;
            _client.PowerStateChanged += OnPowerStateChanged;
        }
    }

    private void OnFanSpeedChanged(object? sender, FanSpeedSettings e)
    {
        Dispatcher.UIThread.Post(() =>
        {
            var cpuFanSpeedText = this.FindControl<TextBlock>("CpuFanSpeed");
            var gpuFanSpeedText = this.FindControl<TextBlock>("GpuFanSpeed");

            if (int.TryParse(e.Cpu, out var cpuSpeed))
            {
                CpuFanSpeedRPM = cpuSpeed;
                if (cpuFanSpeedText != null) cpuFanSpeedText.Text = $"{cpuSpeed} RPM";
            }
            if (int.TryParse(e.Gpu, out var gpuSpeed))
            {
                GpuFanSpeedRPM = gpuSpeed;
                if (gpuFanSpeedText != null) gpuFanSpeedText.Text = $"{gpuSpeed} RPM";
            }
            UpdateFanAnimations();
        });
    }

    private void LogDashboard(string message) {
        if (_client == null || _client.IsConnected == false) return;
        // Logic to check logging state could be added here if needed, 
        // but for now we'll just minimize console output.
    }

    private void OnPowerStateChanged(object? sender, bool isPluggedIn)
    {
        // Trigger a refresh to update battery status text immediately
        RefreshDynamicMetricsAsync();
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        _refreshTimer.Start();
        Console.WriteLine("Dashboard attached: Refresh timer started.");
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnDetachedFromVisualTree(e);
        _refreshTimer.Stop();
        Console.WriteLine("Dashboard detached: Refresh timer stopped.");
    }

    public string CpuName
    {
        get => _cpuName;
        set => SetProperty(ref _cpuName, value);
    }
    public string GpuName { get => _gpuName; set => SetProperty(ref _gpuName, value); }
    public int CpuFanSpeedRPM { get => _cpuFanSpeedRpm; set => SetProperty(ref _cpuFanSpeedRpm, value); }
    public int GpuFanSpeedRPM { get => _gpuFanSpeedRpm; set => SetProperty(ref _gpuFanSpeedRpm, value); }
    public string OsVersion { get => _osVersion; set => SetProperty(ref _osVersion, value); }
    public string KernelVersion { get => _kernelVersion; set => SetProperty(ref _kernelVersion, value); }
    public string RamTotal { get => _ramTotal; set => SetProperty(ref _ramTotal, value); }
    public double CpuTemp { get => _cpuTemp; set => SetProperty(ref _cpuTemp, value); }
    public double GpuTemp { get => _gpuTemp; set => SetProperty(ref _gpuTemp, value); }
    public double CpuUsage { get => _cpuUsage; set => SetProperty(ref _cpuUsage, value); }
    public double RamUsage { get => _ramUsage; set => SetProperty(ref _ramUsage, value); }
    public double GpuUsage { get => _gpuUsage; set => SetProperty(ref _gpuUsage, value); }
    public string BatteryStatus { get => _batteryStatus; set => SetProperty(ref _batteryStatus, value); }
    public int BatteryPercentageInt { get => _batteryPercentageInt; set => SetProperty(ref _batteryPercentageInt, value); }
    public string BatteryTimeRemainingString { get => _batteryTimeRemainingString; set => SetProperty(ref _batteryTimeRemainingString, value); }
    public bool HasBattery { get => _hasBattery; set => SetProperty(ref _hasBattery, value); }

    public new event PropertyChangedEventHandler? PropertyChanged;

    private void RefreshDynamicMetrics(object? sender, EventArgs e) => RefreshDynamicMetricsAsync();

    private async void RefreshDynamicMetricsAsync()
    {
        try
        {
            var data = new MetricsData();
            await Task.Run(async () =>
            {
                try {
                    data.CpuUsage = GetCpuUsage();
                    data.CpuTemp = GetCpuTemperature();
                    data.RamUsage = GetRamUsage();
                    var gm = GetGpuMetrics();
                    data.GpuTemp = gm.temperature;
                    data.GpuUsage = gm.usage;
                    var bi = GetBatteryInfo();
                    data.BatteryPercentage = bi.percentage;
                    data.BatteryStatus = bi.status ?? "Unknown";
                    data.BatteryTimeRemaining = FormatTimeRemain(data.BatteryStatus, bi.timeRemaining);
                    
                    if (_client != null && _client.IsConnected)
                    {
                        var s = await _client.GetAllSettingsAsync();
                        // Use FanRpms for real sensor readings on the dashboard
                        if (s != null && s.FanRpms != null) {
                            if (s.FanRpms.Cpu != null && int.TryParse(s.FanRpms.Cpu, out var cs)) data.CpuFanSpeedRPM = cs;
                            if (s.FanRpms.Gpu != null && int.TryParse(s.FanRpms.Gpu, out var gs)) data.GpuFanSpeedRPM = gs;
                        }
                    }
                } catch (Exception taskEx) {
                    Console.WriteLine($"Metric Task Error: {taskEx.Message}");
                }
            });

            CpuUsage = data.CpuUsage; CpuTemp = data.CpuTemp; RamUsage = data.RamUsage;
            GpuTemp = data.GpuTemp; GpuUsage = data.GpuUsage;
            BatteryPercentageInt = data.BatteryPercentage; BatteryStatus = data.BatteryStatus;
            
            var blb = this.FindControl<ProgressBar>("BatteryLevelBar");
            var btr = this.FindControl<TextBlock>("BatteryTimeRemaining");
            var cfs = this.FindControl<TextBlock>("CpuFanSpeed");
            var gfs = this.FindControl<TextBlock>("GpuFanSpeed");

            if (btr != null) btr.Text = data.BatteryTimeRemaining;
            if (blb != null) blb.Value = data.BatteryPercentage;
            if (cfs != null) cfs.Text = $"{data.CpuFanSpeedRPM} RPM";
            if (gfs != null) gfs.Text = $"{data.GpuFanSpeedRPM} RPM";
            
            CpuFanSpeedRPM = data.CpuFanSpeedRPM; GpuFanSpeedRPM = data.GpuFanSpeedRPM;
            UpdateFanAnimations();

            if (_cpuTempHistory.Count >= MAX_HISTORY_POINTS) _cpuTempHistory.RemoveAt(0);
            _cpuTempHistory.Add(data.CpuTemp);
            if (_gpuTempHistory.Count >= MAX_HISTORY_POINTS) _gpuTempHistory.RemoveAt(0);
            _gpuTempHistory.Add(data.GpuTemp);
        }
        catch (Exception ex) { Console.WriteLine($"Error: {ex.Message}"); }
    }

    private void InitializeStaticSystemInfo()
    {
        try {
            CpuName = GetCpuName(); DetectGpuType(); GpuName = GetGpuName();
            FindSystemPaths();
            var gd = GetGpuDriverVersion(); InitializeTemperatureGraph();
            Dispatcher.UIThread.Post(() => { var gdt = this.FindControl<TextBlock>("GpuDriver"); if (gdt != null) gdt.Text = gd; });
            OsVersion = GetOsVersion(); KernelVersion = GetKernelVersion();
            RamTotal = GetTotalRam(); CheckForBattery();
        } catch {}
    }

    private string GetCpuName()
    {
        try {
            var info = File.ReadAllText("/proc/cpuinfo");
            var m = Regex.Match(info, @"model name\s+:\s+(.+)");
            if (m.Success) {
                var full = m.Groups[1].Value.Trim();
                var s = Regex.Match(full, @"(^(1[1-9]th Gen )?Intel\(R\)\sCore\(TM\)\s[^\s@]+|AMD\sRyzen\s[^\s@]+(\s[^\s@]+)?)");
                return s.Success ? s.Value.Trim() : full;
            }
        } catch {} return "Unknown CPU";
    }

    private void DetectGpuType()
    {
        if (Directory.Exists("/sys/class/drm/card0/device/driver/module/nvidia") || RunCommand("lspci", "").Contains("NVIDIA")) _gpuType = GpuType.Nvidia;
        else if (Directory.Exists("/sys/class/drm/card0/device/driver/module/amdgpu") || RunCommand("lspci", "").Contains("AMD")) _gpuType = GpuType.Amd;
        else if (RunCommand("lspci", "").Contains("Intel")) _gpuType = GpuType.Intel;
    }

    private string GetGpuName() => _gpuType switch {
        GpuType.Nvidia => GetNvidiaGpuName(),
        GpuType.Amd => GetAmdGpuName(),
        GpuType.Intel => GetIntelGpuName(),
        _ => GetFallbackGpuName()
    };

    private string GetNvidiaGpuName() {
        var outpt = RunCommand("nvidia-smi", "--query-gpu=name --format=csv,noheader");
        if (!string.IsNullOrWhiteSpace(outpt)) return outpt.Trim();
        var lspci = RunCommand("lspci", "-vmm");
        var m = Regex.Match(lspci, @"Device:\s+(.+?)(?:\s*|\[|" + ")");
        return m.Success ? Regex.Replace(m.Groups[1].Value.Trim(), @"\b(G[0-9]{2}|AD[0-9]{3}[A-Z]?)\b", "").Trim() : "NVIDIA GPU";
    }

    private string GetAmdGpuName() {
        var glx = RunCommand("glxinfo", "-B");
        var m = Regex.Match(glx, @"OpenGL renderer string:\s+(.+)");
        return m.Success ? Regex.Replace(m.Groups[1].Value, @"(\(\)|LLVM.*|DRM.*)", "").Trim() : "AMD GPU";
    }

    private string GetIntelGpuName() {
        var lspci = RunCommand("lspci", "-vmm");
        var m = Regex.Match(lspci, @"Device:\s+(.+?)(?:\s*|\[|" + ")");
        return m.Success ? Regex.Replace(m.Groups[1].Value.Trim(), @"\b(Alder Lake|Raptor Lake|Xe)\b", "").Trim() : "Intel Graphics";
    }

    private string GetFallbackGpuName() {
        var lspci = RunCommand("lspci", "-vmm");
        var m = Regex.Match(lspci, @"Device:\s+(.+?)(?:\s*|\[|" + ")");
        return m.Success ? m.Groups[1].Value.Trim() : "Unknown GPU";
    }

    private string GetGpuDriverVersion() {
        try {
            var outpt = _gpuType == GpuType.Nvidia ? RunCommand("nvidia-smi", "--query-gpu=driver_version --format=csv,noheader") : RunCommand("glxinfo", "| grep \"OpenGL version\"");
            var m = Regex.Match(outpt, @"(\d+\.\d+\.\d+)");
            return m.Success ? m.Groups[1].Value : "Unknown";
        } catch { return "Unknown"; }
    }

    private string GetOsVersion() {
        if (File.Exists("/etc/os-release")) {
            var m = Regex.Match(File.ReadAllText("/etc/os-release"), "PRETTY_NAME=\"(.+?)\"");
            if (m.Success) return m.Groups[1].Value;
        }
        return "Linux";
    }

    private string GetKernelVersion() => RunCommand("uname", "-r").Trim();

    private string GetTotalRam() {
        var m = Regex.Match(File.ReadAllText("/proc/meminfo"), @"MemTotal:\s+(\d+) kB");
        return m.Success ? $"{(long.Parse(m.Groups[1].Value) / (1024.0 * 1024.0)):F2} GB" : "Unknown";
    }

    private void CheckForBattery() {
        if (!Directory.Exists("/sys/class/power_supply")) { HasBattery = false; return; }
        
        var dirs = Directory.GetDirectories("/sys/class/power_supply")
            .Where(d => {
                var typePath = Path.Combine(d, "type");
                return File.Exists(typePath) && File.ReadAllText(typePath).Trim() == "Battery";
            }).ToList();

        if (dirs.Any()) {
            _batteryDir = dirs.First();
            HasBattery = true;
            _systemInfoPaths["capacity"] = Path.Combine(_batteryDir, "capacity");
            _systemInfoPaths["status"] = Path.Combine(_batteryDir, "status");
            foreach(var f in new[]{"energy_now","charge_now","power_now","current_now","energy_full","charge_full"}) {
                var p = Path.Combine(_batteryDir, f);
                if (File.Exists(p)) {
                    var key = f.Contains("energy") || f.Contains("charge") ? (f.EndsWith("full") ? "energy_full" : "energy_now") : "power_now";
                    _systemInfoPaths[key] = p;
                }
            }
        } else {
            HasBattery = false;
        }
    }

    private void InitializeTemperatureGraph()
    {
        // Initialize collections
        _cpuTempHistory = new ObservableCollection<double>();
        _gpuTempHistory = new ObservableCollection<double>();

        // Initialize series
        _tempSeries = new ObservableCollection<ISeries>
        {
            new LineSeries<double>
            {
                Values = _cpuTempHistory,
                Name = "CPU Temperature:",
                Stroke = new SolidColorPaint(SKColors.OrangeRed) { StrokeThickness = 3 },
                GeometryStroke = new SolidColorPaint(SKColors.OrangeRed),
                GeometryFill = new SolidColorPaint(SKColors.OrangeRed),
                Fill = new SolidColorPaint(SKColors.Transparent),
                GeometrySize = 5,
                XToolTipLabelFormatter = chartPoint => $"{GetCpuName()}"
            },
            new LineSeries<double>
            {
                Values = _gpuTempHistory,
                Name = "GPU Temperature:",
                Stroke = new SolidColorPaint(SKColors.DarkOrange) { StrokeThickness = 3 },
                GeometryFill = new SolidColorPaint(SKColors.DarkOrange),
                GeometryStroke = new SolidColorPaint(SKColors.DarkOrange),
                Fill = new SolidColorPaint(SKColors.Transparent),
                GeometrySize = 5,
                XToolTipLabelFormatter = chartPoint => $"{GetGpuName()}"
            }
        };

        // Initialize and configure the chart
        _temperatureChart = this.FindControl<CartesianChart>("TemperatureChart");
        if (_temperatureChart != null)
        {
            _temperatureChart.Series = _tempSeries;
            _temperatureChart.XAxes = new List<Axis>
            {
                new()
                {
                    Name = "Time",
                    IsVisible = false
                }
            };
            _temperatureChart.YAxes = new List<Axis>
            {
                new()
                {
                    Name = "Temperature (°C)",
                    NamePaint = new SolidColorPaint(SKColors.Gray),
                    LabelsPaint = new SolidColorPaint(SKColors.Gray),
                    MinLimit = 0,
                    MaxLimit = 100,
                    TextSize = 13
                }
            };
            _temperatureChart.FindingStrategy = FindingStrategy.ExactMatchTakeClosest;
            _temperatureChart.TooltipBackgroundPaint = new SolidColorPaint(SKColor.Parse("#282828").WithAlpha(230));
            _temperatureChart.TooltipTextPaint = new SolidColorPaint(SKColors.WhiteSmoke);
            _temperatureChart.TooltipTextSize = 12;
            _temperatureChart.FontFamily = "Segoe UI";
        }
    }

    private double GetCpuUsage() {
        try {
            var m = Regex.Match(File.ReadAllText("/proc/stat"), @"^cpu\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)");
            if (m.Success) {
                long u=long.Parse(m.Groups[1].Value), n=long.Parse(m.Groups[2].Value), s=long.Parse(m.Groups[3].Value), i=long.Parse(m.Groups[4].Value);
                long t=u+n+s+i;
                if (_lastTotalTime==0) { _lastTotalTime=t; _lastIdleTime=i; return 0; }
                long dt=t-_lastTotalTime, di=i-_lastIdleTime;
                _lastTotalTime=t; _lastIdleTime=i;
                return dt==0 ? 0 : Math.Round((1.0 - di/(double)dt)*100.0, 1);
            }
        } catch {} return 0;
    }

    private double GetCpuTemperature() {
        if (_systemInfoPaths.ContainsKey("cpu_temp_files")) {
            var fs = _systemInfoPaths["cpu_temp_files"].Split(',');
            double sum=0; int c=0;
            foreach(var f in fs) if(File.Exists(f)) { sum += int.Parse(File.ReadAllText(f).Trim())/1000.0; c++; }
            if(c>0) return Math.Round(sum/c, 1);
        }
        var m = Regex.Match(RunCommand("sensors", ""), @"Package id \d+:\s+\+?(\d+\.\d+)°C");
        return m.Success ? double.Parse(m.Groups[1].Value) : 0;
    }

    private double GetRamUsage() {
        var mem = File.ReadAllText("/proc/meminfo");
        var t = Regex.Match(mem, @"MemTotal:\s+(\d+) kB");
        var a = Regex.Match(mem, @"MemAvailable:\s+(\d+) kB");
        return (t.Success && a.Success) ? Math.Round((1.0 - double.Parse(a.Groups[1].Value)/double.Parse(t.Groups[1].Value))*100.0, 1) : 0;
    }

    private (double temperature, double usage) GetGpuMetrics() {
        if (_gpuType == GpuType.Nvidia) {
            var t = double.TryParse(RunCommand("nvidia-smi", "--query-gpu=temperature.gpu --format=csv,noheader").Trim(), out var v) ? v : 0;
            var u = Regex.Match(RunCommand("nvidia-smi", "--query-gpu=utilization.gpu --format=csv,noheader"), @"(\d+)");
            return (t, u.Success ? double.Parse(u.Groups[1].Value) : 0);
        }
        return (0, 0);
    }

    private void FindSystemPaths() {
        foreach(var p in new[]{"/sys/class/hwmon/hwmon5","/sys/class/hwmon/hwmon6","/sys/class/hwmon/hwmon7","/sys/class/hwmon/hwmon8"})
            if(Directory.Exists(p)) {
                var fs = Directory.GetFiles(p, "temp*_input");
                if(fs.Length > 3) { 
                    _systemInfoPaths["cpu_temp_files"] = string.Join(",", fs); 
                    Console.WriteLine($"[Dashboard] Found CPU Reporting Temps at {fs.Length} Cores ({p})");
                    break; 
                }
            }
    }

    private void InitializeFanAnimations(MaterialIcon c, MaterialIcon g) {
        c.RenderTransform = _cpuFanRotateTransform; g.RenderTransform = _gpuFanRotateTransform;
        _cpuFanAnimation = new Animation { Duration = TimeSpan.FromSeconds(1), IterationCount = IterationCount.Infinite, Children = { new KeyFrame { Cue = new Cue(0d), Setters = { new Setter(RotateTransform.AngleProperty, 0d) } }, new KeyFrame { Cue = new Cue(1d), Setters = { new Setter(RotateTransform.AngleProperty, 360d) } } } };
        _gpuFanAnimation = new Animation { Duration = TimeSpan.FromSeconds(1), IterationCount = IterationCount.Infinite, Children = { new KeyFrame { Cue = new Cue(0d), Setters = { new Setter(RotateTransform.AngleProperty, 0d) } }, new KeyFrame { Cue = new Cue(1d), Setters = { new Setter(RotateTransform.AngleProperty, 360d) } } } };
        _cpuFanAnimation.RunAsync(c); _gpuFanAnimation.RunAsync(g);
    }

    private void UpdateFanAnimations() {
        var c = this.FindControl<MaterialIcon>("CpuFanIcon"); var g = this.FindControl<MaterialIcon>("GpuFanIcon");
        if (c == null || g == null) return;
        if (!_animationsInitialized) { InitializeFanAnimations(c, g); _animationsInitialized = true; }
        if (_cpuFanAnimation != null) UpdateFanSpeed(_cpuFanAnimation, _cpuFanSpeedRpm, ref _lastCpuRpm);
        if (_gpuFanAnimation != null) UpdateFanSpeed(_gpuFanAnimation, _gpuFanSpeedRpm, ref _lastGpuRpm);
    }

    private void UpdateFanSpeed(Animation a, int rpm, ref int last) {
        a.Duration = TimeSpan.FromSeconds(rpm < MIN_RPM_FOR_ANIMATION ? MAX_ANIMATION_DURATION : Math.Max(MIN_ANIMATION_DURATION, Math.Min(MAX_ANIMATION_DURATION, 2000.0 / rpm)));
        last = rpm;
    }

    private (int percentage, string status, double timeRemaining) GetBatteryInfo() {
        if (!_hasBattery || _batteryDir == null) return (0, "No Battery", 0);
        try {
            int p = 0;
            if (_systemInfoPaths.ContainsKey("capacity")) {
                p = int.Parse(File.ReadAllText(_systemInfoPaths["capacity"]).Trim());
            }
            
            string s = "Unknown";
            if (_systemInfoPaths.ContainsKey("status")) {
                s = File.ReadAllText(_systemInfoPaths["status"]).Trim();
            }

            double tr = 0;
            if (_systemInfoPaths.ContainsKey("energy_now") && 
                _systemInfoPaths.ContainsKey("power_now") && 
                _systemInfoPaths.ContainsKey("energy_full")) {
                
                double en = double.Parse(File.ReadAllText(_systemInfoPaths["energy_now"]).Trim());
                double pw = double.Parse(File.ReadAllText(_systemInfoPaths["power_now"]).Trim());
                double ef = double.Parse(File.ReadAllText(_systemInfoPaths["energy_full"]).Trim());
                
                if (pw > 0) tr = (s == "Discharging") ? en / pw : (ef - en) / pw;
            }
            return (p, s, tr);
        } catch (KeyNotFoundException ex) {
            Console.WriteLine($"[Dashboard] Missing battery path key: {ex.Message}");
            return (0, "Missing Path", 0);
        } catch (Exception ex) {
            Console.WriteLine($"[Dashboard] Battery info error: {ex.Message}");
            return (0, "Error", 0);
        }
    }

    private string RunCommand(string c, string a) {
        try {
            using var p = new Process { StartInfo = new ProcessStartInfo { FileName = c, Arguments = a, RedirectStandardOutput = true, UseShellExecute = false, CreateNoWindow = true } };
            p.Start(); var o = p.StandardOutput.ReadToEnd(); p.WaitForExit(); return o;
        } catch { return ""; }
    }

    private string FormatTimeRemain(string s, double tr) {
        if ((s == "Charging" || s == "Full") && tr == 0) return "Powered by AC";
        var ts = TimeSpan.FromHours(tr);
        return s == "Discharging" ? $"{ts.Hours:D2}:{ts.Minutes:D2} left" : $"{ts.Hours:D2}:{ts.Minutes:D2} to full";
    }

    protected bool SetProperty<T>(ref T field, T value, [CallerMemberName] string? propertyName = null) {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value; PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName)); return true;
    }

    private class MetricsData {
        public double CpuUsage { get; set; }
        public double CpuTemp { get; set; }
        public double RamUsage { get; set; }
        public double GpuTemp { get; set; }
        public double GpuUsage { get; set; }
        public int BatteryPercentage { get; set; }
        public string BatteryStatus { get; set; } = "Unknown";
        public string BatteryTimeRemaining { get; set; } = "0";
        public int CpuFanSpeedRPM { get; set; }
        public int GpuFanSpeedRPM { get; set; }
    }
    private enum GpuType { Unknown, Nvidia, Amd, Intel }
}
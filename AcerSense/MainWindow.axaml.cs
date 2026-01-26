using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Threading;
using MsBox.Avalonia;

namespace DivAcerManagerMax;

public partial class MainWindow : Window, INotifyPropertyChanged
{
    private static readonly Dictionary<string, string> _specialFormatText = new()
    {
        { "lcd", "LCD" },
        { "usb", "USB" }
    };

    private readonly string _effectColor = "#0078D7";
    private readonly string ProjectVersion = "1.0";

    // UI Controls
    private Button? _applyKeyboardColorsButton;
    private RadioButton? _autoFanSpeedRadioButton;
    private CheckBox? _backlightTimeoutCheckBox;
    private RadioButton? _balancedProfileButton;
    private CheckBox? _batteryLimitCheckBox;
    private CheckBox? _bootAnimAndSoundCheckBox;
    private TextBlock? _calibrationStatusTextBlock;
    public AcerSense? _client;
    private Slider? _cpuFanSlider;
    private int _cpuFanSpeed = 50;
    private TextBlock? _cpuFanTextBlock;
    private Dashboard? _dashboardView;
    private Grid? _daemonErrorGrid;
    private TextBlock? _daemonVersionText;
    private TextBlock? _driverVersionText;
    private Slider? _gpuFanSlider;
    private ComboBox? _defaultAcProfileComboBox;
    private ComboBox? _defaultBatProfileComboBox;
    private int _gpuFanSpeed = 70;
    
    // Opacity Controls
    private Slider? _acActiveOpacitySlider;
    private Slider? _acInactiveOpacitySlider;
    private Slider? _batActiveOpacitySlider;
    private Slider? _batInactiveOpacitySlider;
    private TextBlock? _acActiveOpacityText;
    private TextBlock? _acInactiveOpacityText;
    private TextBlock? _batActiveOpacityText;
    private TextBlock? _batInactiveOpacityText;
    private Button? _applyOpacityButton;

    private TextBlock? _gpuFanTextBlock;
    private TextBlock? _guiVersionTextBlock;
    private ToggleSwitch? _hyprlandIntegrationToggleSwitch;
    private bool _isCalibrating;
    private bool _isConnected;
    private bool _isManualFanControl;
    private int _keyboardBrightness = 100;
    private Slider? _keyBrightnessSlider;
    private TextBlock? _keyBrightnessText;
    private TextBlock? _laptopTypeText;
    private CheckBox? _lcdOverrideCheckBox;
    private RadioButton? _leftToRightRadioButton;
    private ColorPicker? _lightEffectColorPicker;
    private Button? _lightingEffectsApplyButton;
    private ComboBox? _lightingModeComboBox;
    private int _lightingSpeed = 5;
    private Slider? _lightingSpeedSlider;
    private TextBlock? _lightSpeedTextBlock;
    private TextBlock? _linuxKernelVersionText;
    private RadioButton? _lowPowerProfileButton;
    private RadioButton? _manualFanSpeedRadioButton;
    private RadioButton? _maxFanSpeedRadioButton;
    private TextBlock? _modelNameText;
    private RadioButton? _performanceProfileButton;
    private ToggleSwitch? _powerToggleSwitch;
    private RadioButton? _quietProfileButton;
    private Button? _setManualSpeedButton;
    public AcerSenseSettings _settings = new();
    private Button? _startCalibrationButton;
    private Button? _stopCalibrationButton;
    private TextBlock? _supportedFeaturesTextBlock;
    private TextBlock? _thermalProfileInfoText;
    private RadioButton? _turboProfileButton;
    private ComboBox? _usbChargingComboBox;
    private ColorPicker? _zone1ColorPicker;
    private ColorPicker? _zone2ColorPicker;
    private ColorPicker? _zone3ColorPicker;
    private ColorPicker? _zone4ColorPicker;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = this;
        _client = new AcerSense();
        Loaded += MainWindow_Loaded;
    }

    public bool IsCalibrating
    {
        get => _isCalibrating;
        set => SetField(ref _isCalibrating, value);
    }

    private void InitializeComponent()
    {
        AvaloniaXamlLoader.Load(this);
    }

    private void MainWindow_Loaded(object? sender, RoutedEventArgs e)
    {
        BindControls();
        AttachEventHandlers();
        InitializeAsync();
        LoadKeyboardBrighness();
    }

    private void BindControls()
    {
        var nameScope = this.FindNameScope();
        if (nameScope == null) return;

        // Thermal Profile controls
        _lowPowerProfileButton = nameScope.Find<RadioButton>("LowPowerProfileButton");
        _quietProfileButton = nameScope.Find<RadioButton>("QuietProfileButton");
        _balancedProfileButton = nameScope.Find<RadioButton>("BalancedProfileButton");
        _performanceProfileButton = nameScope.Find<RadioButton>("PerformanceProfileButton");
        _turboProfileButton = nameScope.Find<RadioButton>("TurboProfileButton");
        _powerToggleSwitch = nameScope.Find<ToggleSwitch>("PluggedInToggleSwitch");
        _defaultAcProfileComboBox = nameScope.Find<ComboBox>("DefaultAcProfileComboBox");
        _defaultBatProfileComboBox = nameScope.Find<ComboBox>("DefaultBatProfileComboBox");

        // Fan control controls
        _manualFanSpeedRadioButton = nameScope.Find<RadioButton>("ManualFanSpeedRadioButton");
        _maxFanSpeedRadioButton = nameScope.Find<RadioButton>("MaxFanSpeedRadioButton");
        _cpuFanSlider = nameScope.Find<Slider>("CpuFanSlider");
        _gpuFanSlider = nameScope.Find<Slider>("GpuFanSlider");
        _cpuFanTextBlock = nameScope.Find<TextBlock>("CpuFanTextBlock");
        _gpuFanTextBlock = nameScope.Find<TextBlock>("GpuFanTextBlock");
        _setManualSpeedButton = nameScope.Find<Button>("SetManualSpeedButton");
        _autoFanSpeedRadioButton = nameScope.Find<RadioButton>("AutoFanSpeedRadioButton");

        // Battery calibration controls
        _startCalibrationButton = nameScope.Find<Button>("StartCalibrationButton");
        _stopCalibrationButton = nameScope.Find<Button>("StopCalibrationButton");
        _calibrationStatusTextBlock = nameScope.Find<TextBlock>("CalibrationStatusTextBlock");
        _batteryLimitCheckBox = nameScope.Find<CheckBox>("BatteryLimitCheckBox");

        // USB charging controls
        _usbChargingComboBox = nameScope.Find<ComboBox>("UsbChargingComboBox");

        // Keyboard lighting zone controls
        _zone1ColorPicker = nameScope.Find<ColorPicker>("Zone1ColorPicker");
        _zone2ColorPicker = nameScope.Find<ColorPicker>("Zone2ColorPicker");
        _zone3ColorPicker = nameScope.Find<ColorPicker>("Zone3ColorPicker");
        _zone4ColorPicker = nameScope.Find<ColorPicker>("Zone4ColorPicker");
        _keyBrightnessSlider = nameScope.Find<Slider>("KeyBrightnessSlider");
        _keyBrightnessText = nameScope.Find<TextBlock>("KeyBrightnessText");
        _applyKeyboardColorsButton = nameScope.Find<Button>("ApplyKeyboardColorsButton");

        // Lighting effects controls
        _lightingModeComboBox = nameScope.Find<ComboBox>("LightingModeComboBox");
        _lightingSpeedSlider = nameScope.Find<Slider>("LightingSpeedSlider");
        _lightSpeedTextBlock = nameScope.Find<TextBlock>("LightSpeedTextBlock");
        _lightEffectColorPicker = nameScope.Find<ColorPicker>("LightEffectColorPicker");
        _leftToRightRadioButton = nameScope.Find<RadioButton>("LeftToRightRadioButton");
        _lightingEffectsApplyButton = nameScope.Find<Button>("LightingEffectsApplyButton");

        // System settings controls
        _backlightTimeoutCheckBox = nameScope.Find<CheckBox>("BacklightTimeoutCheckBox");
        _lcdOverrideCheckBox = nameScope.Find<CheckBox>("LcdOverrideCheckBox");
        _hyprlandIntegrationToggleSwitch = nameScope.Find<ToggleSwitch>("HyprlandIntegrationToggleSwitch");
        _bootAnimAndSoundCheckBox = nameScope.Find<CheckBox>("BootAnimAndSoundCheckBox");

        // Opacity Controls
        _acActiveOpacitySlider = nameScope.Find<Slider>("AcActiveOpacitySlider");
        _acInactiveOpacitySlider = nameScope.Find<Slider>("AcInactiveOpacitySlider");
        _batActiveOpacitySlider = nameScope.Find<Slider>("BatActiveOpacitySlider");
        _batInactiveOpacitySlider = nameScope.Find<Slider>("BatInactiveOpacitySlider");
        _acActiveOpacityText = nameScope.Find<TextBlock>("AcActiveOpacityText");
        _acInactiveOpacityText = nameScope.Find<TextBlock>("AcInactiveOpacityText");
        _batActiveOpacityText = nameScope.Find<TextBlock>("BatActiveOpacityText");
        _batInactiveOpacityText = nameScope.Find<TextBlock>("BatInactiveOpacityText");
        _applyOpacityButton = nameScope.Find<Button>("ApplyOpacityButton");

        // Info Texts
        _thermalProfileInfoText = nameScope.Find<TextBlock>("ThermalProfileInfoText");
        _modelNameText = nameScope.Find<TextBlock>("ModelNameText");
        _laptopTypeText = nameScope.Find<TextBlock>("LaptopTypeText");
        _supportedFeaturesTextBlock = nameScope.Find<TextBlock>("SupportedFeaturesTextBlock");
        _daemonVersionText = nameScope.Find<TextBlock>("DaemonVersionText");
        _driverVersionText = nameScope.Find<TextBlock>("DriverVersionText");
        _guiVersionTextBlock = nameScope.Find<TextBlock>("ProjectVersionText");
        _daemonErrorGrid = nameScope.Find<Grid>("DaemonErrorGrid");
        _linuxKernelVersionText = nameScope.Find<TextBlock>("LinuxKernelVersionText");
        _dashboardView = nameScope.Find<Dashboard>("DashboardView");

        if (_guiVersionTextBlock != null)
            _guiVersionTextBlock.Text = $"{ProjectVersion}";
    }

    private void AttachEventHandlers()
    {
        if (_lowPowerProfileButton != null) _lowPowerProfileButton.IsCheckedChanged += ProfileButton_Checked;
        if (_quietProfileButton != null) _quietProfileButton.IsCheckedChanged += ProfileButton_Checked;
        if (_balancedProfileButton != null) _balancedProfileButton.IsCheckedChanged += ProfileButton_Checked;
        if (_performanceProfileButton != null) _performanceProfileButton.IsCheckedChanged += ProfileButton_Checked;
        if (_turboProfileButton != null) _turboProfileButton.IsCheckedChanged += ProfileButton_Checked;

        if (_defaultAcProfileComboBox != null) _defaultAcProfileComboBox.SelectionChanged += DefaultProfile_SelectionChanged;
        if (_defaultBatProfileComboBox != null) _defaultBatProfileComboBox.SelectionChanged += DefaultProfile_SelectionChanged;

        if (_manualFanSpeedRadioButton != null) _manualFanSpeedRadioButton.Click += ManualFanControlRadioBox_Click;
        if (_cpuFanSlider != null) _cpuFanSlider.PropertyChanged += CpuFanSlider_ValueChanged;
        if (_gpuFanSlider != null) _gpuFanSlider.PropertyChanged += GpuFanSlider_ValueChanged;
        if (_autoFanSpeedRadioButton != null) _autoFanSpeedRadioButton.Click += AutoFanSpeedRadioButtonClick;
        if (_setManualSpeedButton != null) _setManualSpeedButton.Click += SetManualSpeedButton_OnClick;

        if (_startCalibrationButton != null) _startCalibrationButton.Click += StartCalibrationButton_Click;
        if (_stopCalibrationButton != null) _stopCalibrationButton.Click += StopCalibrationButton_Click;
        if (_batteryLimitCheckBox != null) _batteryLimitCheckBox.Click += BatteryLimitCheckBox_Click;

        if (_keyBrightnessSlider != null) _keyBrightnessSlider.PropertyChanged += KeyboardBrightnessSlider_ValueChanged;
        if (_applyKeyboardColorsButton != null) _applyKeyboardColorsButton.Click += ApplyKeyboardColorsButton_Click;

        if (_lightingSpeedSlider != null) _lightingSpeedSlider.PropertyChanged += LightingSpeedSlider_ValueChanged;
        if (_lightingEffectsApplyButton != null) _lightingEffectsApplyButton.Click += LightingEffectsApplyButton_Click;

        if (_backlightTimeoutCheckBox != null) _backlightTimeoutCheckBox.Click += BacklightTimeoutCheckBox_Click;
        if (_lcdOverrideCheckBox != null) _lcdOverrideCheckBox.Click += LcdOverrideCheckBox_Click;
        if (_hyprlandIntegrationToggleSwitch != null)
            _hyprlandIntegrationToggleSwitch.PropertyChanged += HyprlandIntegration_Toggled;
        if (_bootAnimAndSoundCheckBox != null) _bootAnimAndSoundCheckBox.Click += BootSoundCheckBox_Click;

        if (_acActiveOpacitySlider != null) _acActiveOpacitySlider.PropertyChanged += OpacitySlider_ValueChanged;
        if (_acInactiveOpacitySlider != null) _acInactiveOpacitySlider.PropertyChanged += OpacitySlider_ValueChanged;
        if (_batActiveOpacitySlider != null) _batActiveOpacitySlider.PropertyChanged += OpacitySlider_ValueChanged;
        if (_batInactiveOpacitySlider != null) _batInactiveOpacitySlider.PropertyChanged += OpacitySlider_ValueChanged;
        if (_applyOpacityButton != null) _applyOpacityButton.Click += ApplyOpacityButton_OnClick;
    }

    private void UpdateUIElementVisibility()
    {
        if (_settings == null || _client == null) return;

        var nameScope = this.FindNameScope();
        if (nameScope == null) return;

        var thermalProfilePanel = nameScope.Find<Border>("ThermalProfilePanel");
        var fanControlPanel = nameScope.Find<Border>("FanControlPanel");
        var batteryTab = nameScope.Find<TabItem>("PowerPanel");
        var usbChargingPanel = nameScope.Find<Border>("UsbChargingPanel");
        var keyboardLightingTab = nameScope.Find<TabItem>("KeyboardLightingPanel");
        var zoneColorControlPanel = nameScope.Find<Border>("ZoneColorControlPanel");
        var keyboardEffectsPanel = nameScope.Find<Border>("KeyboardEffectsPanel");
        var systemSettingsTab = nameScope.Find<TabItem>("SystemSettingsPanel");

        if (thermalProfilePanel != null)
            thermalProfilePanel.IsVisible = _client.IsFeatureAvailable("thermal_profile") || AppState.DevMode;

        if (fanControlPanel != null)
            fanControlPanel.IsVisible = _client.IsFeatureAvailable("fan_speed") || AppState.DevMode;

        if (batteryTab != null)
        {
            var hasBatteryFeatures = _client.IsFeatureAvailable("battery_calibration") ||
                                     _client.IsFeatureAvailable("battery_limiter");
            batteryTab.IsVisible = hasBatteryFeatures;

            var calibrationControls = nameScope.Find<Border>("CalibrationControls");
            var limiterControls = nameScope.Find<Border>("LimiterControls");

            if (calibrationControls != null)
                calibrationControls.IsVisible = _client.IsFeatureAvailable("battery_calibration") || AppState.DevMode;

            if (limiterControls != null)
                limiterControls.IsVisible = _client.IsFeatureAvailable("battery_limiter") || AppState.DevMode;
        }

        var hasKeyboardFeatures = _client.IsFeatureAvailable("backlight_timeout") ||
                                  _client.IsFeatureAvailable("per_zone_mode") ||
                                  _client.IsFeatureAvailable("four_zone_mode");

        if (keyboardLightingTab != null)
            keyboardLightingTab.IsVisible = hasKeyboardFeatures;

        if (zoneColorControlPanel != null)
            zoneColorControlPanel.IsVisible = _client.IsFeatureAvailable("per_zone_mode") || AppState.DevMode;

        if (keyboardEffectsPanel != null)
            keyboardEffectsPanel.IsVisible = _client.IsFeatureAvailable("four_zone_mode") || AppState.DevMode;

        if (usbChargingPanel != null)
            usbChargingPanel.IsVisible = _client.IsFeatureAvailable("usb_charging") || AppState.DevMode;

        if (systemSettingsTab != null)
        {
            var backlightControls = nameScope.Find<Border>("BacklightTimeoutControls");
            var lcdControls = nameScope.Find<Border>("LcdOverrideControls");
            var hyprlandControls = nameScope.Find<Border>("HyprlandIntegrationControls");
            var bootSoundControls = nameScope.Find<Border>("BootSoundControls");

            if (backlightControls != null)
                backlightControls.IsVisible = _client.IsFeatureAvailable("backlight_timeout") || AppState.DevMode;

            if (lcdControls != null)
                lcdControls.IsVisible = _client.IsFeatureAvailable("lcd_override") || AppState.DevMode;

            if (hyprlandControls != null)
                hyprlandControls.IsVisible = true; 

            if (bootSoundControls != null)
                bootSoundControls.IsVisible = _client.IsFeatureAvailable("boot_animation_sound") || AppState.DevMode;
        }
    }

    private void UpdateUIBasedOnPowerSource()
    {
        var isPluggedIn = _powerToggleSwitch?.IsChecked ?? false;

        if (_lowPowerProfileButton != null)
            _lowPowerProfileButton.IsVisible = _lowPowerProfileButton.IsEnabled && !isPluggedIn;

        if (_quietProfileButton != null)
            _quietProfileButton.IsVisible = _quietProfileButton.IsEnabled && isPluggedIn;

        if (_balancedProfileButton != null)
            _balancedProfileButton.IsVisible = _balancedProfileButton.IsEnabled;

        if (_performanceProfileButton != null)
            _performanceProfileButton.IsVisible = _performanceProfileButton.IsEnabled && isPluggedIn;

        if (_turboProfileButton != null)
            _turboProfileButton.IsVisible = _turboProfileButton.IsEnabled && isPluggedIn;

        if (_balancedProfileButton != null &&
            ((_lowPowerProfileButton?.IsChecked == true && !_lowPowerProfileButton.IsVisible) ||
             (_quietProfileButton?.IsChecked == true && !_quietProfileButton.IsVisible) ||
             (_performanceProfileButton?.IsChecked == true && !_performanceProfileButton.IsVisible) ||
             (_turboProfileButton?.IsChecked == true && !_turboProfileButton.IsVisible)))
            _balancedProfileButton.IsChecked = true;
    }

    public async void InitializeAsync()
    {
        try
        {
            if (_client == null) _client = new AcerSense();
            _isConnected = await _client.ConnectAsync();
            if (_isConnected)
            {
                if (_daemonErrorGrid != null) _daemonErrorGrid.IsVisible = false;
                await LoadSettingsAsync();
                
                // Set client for dashboard (event system)
                if (_dashboardView != null) _dashboardView.SetClient(_client);

                // Event-Driven: Subscribe to events
                _client.ThermalProfileChanged += OnThermalProfileChanged;
                _client.FanSpeedChanged += OnFanSpeedChanged;
                _client.PowerStateChanged += OnPowerStateChanged;
                
                // Start listening for broadcast events
                _client.StartListening();
                
                await CheckForUpdatesAsync();
            }
            else
            {
                await ShowMessageBox(
                    "Error Connecting to Daemon",
                    "Failed to connect to daemon. The Daemon may be initializing please wait.");
                if (_daemonErrorGrid != null) _daemonErrorGrid.IsVisible = true;
            }
        }
        catch (Exception ex)
        {
            await ShowMessageBox("Error while initializing", $"Error initializing: {ex.Message}");
            if (_daemonErrorGrid != null) _daemonErrorGrid.IsVisible = true;
        }
    }

    // Event Handlers
    private void OnThermalProfileChanged(object? sender, string profile)
    {
        Dispatcher.UIThread.InvokeAsync(() =>
        {
            if (_settings.ThermalProfile != null)
            {
                _settings.ThermalProfile.Current = profile;
                UpdateProfileButtons();
            }
        });
    }

    private void OnFanSpeedChanged(object? sender, FanSpeedSettings e)
    {
        Dispatcher.UIThread.InvokeAsync(() =>
        {
            if (e.Cpu != null && int.TryParse(e.Cpu, out var cpuSpeed))
            {
                if (_cpuFanSlider != null) _cpuFanSlider.Value = cpuSpeed;
                if (_cpuFanTextBlock != null) _cpuFanTextBlock.Text = cpuSpeed == 0 ? "Auto" : $"{cpuSpeed}%";
            }

            if (e.Gpu != null && int.TryParse(e.Gpu, out var gpuSpeed))
            {
                if (_gpuFanSlider != null) _gpuFanSlider.Value = gpuSpeed;
                if (_gpuFanTextBlock != null) _gpuFanTextBlock.Text = gpuSpeed == 0 ? "Auto" : $"{gpuSpeed}%";
            }
        });
    }

    private void OnPowerStateChanged(object? sender, bool isPluggedIn)
    {
        Dispatcher.UIThread.InvokeAsync(() =>
        {
            if (_powerToggleSwitch != null)
            {
                _powerToggleSwitch.IsChecked = isPluggedIn;
                // Note: IsChecked change will trigger UpdateUIBasedOnPowerSource via existing handler
            }
        });
    }

    private async Task CheckForUpdatesAsync()
    {
        try
        {
            using var client = new HttpClient();
            client.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("AcerSense", ProjectVersion));
            client.Timeout = TimeSpan.FromSeconds(5);

            var response = await client.GetAsync("https://api.github.com/repos/MematiBas42/Div-Acer-Manager-Max/releases/latest");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("tag_name", out var tagNameElement))
                {
                    var latestVersion = tagNameElement.GetString()?.TrimStart('v');
                    if (latestVersion != null && latestVersion != ProjectVersion)
                    {
                        var box = MessageBoxManager.GetMessageBoxStandard(
                            "Update Available", 
                            $"A new version ({latestVersion}) is available.\nCurrent: {ProjectVersion}\n\nDo you want to update?",
                            MsBox.Avalonia.Enums.ButtonEnum.YesNo);
                        
                        var result = await box.ShowWindowDialogAsync(this);
                        if (result == MsBox.Avalonia.Enums.ButtonResult.Yes)
                        {
                            UpdateButton_OnClick(null, null);
                        }
                    }
                }
            }
        }
        catch
        {
            // Fail silently
        }
    }

    private async Task LoadSettingsAsync()
    {
        try
        {
            if (_client != null)
            {
                _settings = await _client.GetAllSettingsAsync();
                ApplySettingsToUI();
            }
        }
        catch (Exception ex)
        {
            await ShowMessageBox("Error while loading settings", $"Error loading settings: {ex.Message}");
            _settings = new AcerSenseSettings();
            ApplySettingsToUI();
        }
    }

    private void UpdateProfileButtons()
    {
        if (_settings?.ThermalProfile == null) return;

        var isPluggedIn = _powerToggleSwitch?.IsChecked ?? false;
        var profileConfigs =
            new Dictionary<string, (RadioButton? button, string description, bool showOnBattery, bool showOnAC)>
            {
                { "low-power", (_lowPowerProfileButton, "Prioritizes energy efficiency, reduces performance to extend battery life.", true, false) },
                { "quiet", (_quietProfileButton, "Minimizes noise, prioritizes low power and cooling.", false, true) },
                { "balanced", (_balancedProfileButton, "Optimal mix of performance and noise for everyday tasks.", true, true) },
                { "balanced-performance", (_performanceProfileButton, "Maximizes speed for demanding workloads, higher fan noise", false, true) },
                { "performance", (_turboProfileButton, "Unleashes peak power for extreme tasks, loudest fans.", false, true) }
            };

        foreach (var config in profileConfigs.Values)
            if (config.button != null)
            {
                config.button.IsVisible = false;
                config.button.IsEnabled = false;
            }

        foreach (var profile in _settings.ThermalProfile.Available)
        {
            var profileKey = profile.ToLower();
            if (profileConfigs.TryGetValue(profileKey, out var config) && config.button != null)
            {
                var shouldShow = isPluggedIn ? config.showOnAC : config.showOnBattery;
                config.button.IsEnabled = true;
                config.button.IsVisible = shouldShow || AppState.DevMode;
            }
        }

        if (!string.IsNullOrEmpty(_settings.ThermalProfile.Current))
        {
            var currentProfileKey = _settings.ThermalProfile.Current.ToLower();
            if (profileConfigs.TryGetValue(currentProfileKey, out var config) && config.button?.IsEnabled == true)
            {
                // Temporarily remove event handler to prevent loops
                config.button.IsCheckedChanged -= ProfileButton_Checked;
                config.button.IsChecked = true;
                config.button.IsCheckedChanged += ProfileButton_Checked;

                if (_thermalProfileInfoText != null)
                    _thermalProfileInfoText.Text = config.description;
            }
        }
    }

    private void ApplySettingsToUI()
    {
        UpdateProfileButtons();

        if (_defaultAcProfileComboBox != null && _defaultBatProfileComboBox != null && _settings.ThermalProfile != null)
        {
            var acItems = new List<ComboBoxItem>();
            var batItems = new List<ComboBoxItem>();

            // AC profiles: quiet, balanced, balanced-performance, performance
            var acCompatible = new[] { "quiet", "balanced", "balanced-performance", "performance" };
            // Battery profiles: low-power, balanced
            var batCompatible = new[] { "low-power", "balanced" };

            foreach (var profile in _settings.ThermalProfile.Available)
            {
                var displayName = profile switch
                {
                    "low-power" => "Eco",
                    "quiet" => "Quiet",
                    "balanced" => "Balanced",
                    "balanced-performance" => "Performance",
                    "performance" => "Turbo",
                    _ => char.ToUpper(profile[0]) + profile.Substring(1)
                };

                if (acCompatible.Contains(profile))
                    acItems.Add(new ComboBoxItem { Content = displayName, Tag = profile });
                
                if (batCompatible.Contains(profile))
                    batItems.Add(new ComboBoxItem { Content = displayName, Tag = profile });
            }

            _defaultAcProfileComboBox.SelectionChanged -= DefaultProfile_SelectionChanged;
            _defaultBatProfileComboBox.SelectionChanged -= DefaultProfile_SelectionChanged;

            _defaultAcProfileComboBox.Items.Clear();
            _defaultBatProfileComboBox.Items.Clear();

            foreach (var item in acItems) _defaultAcProfileComboBox.Items.Add(item);
            foreach (var item in batItems) _defaultBatProfileComboBox.Items.Add(item);

            _defaultAcProfileComboBox.SelectedItem = _defaultAcProfileComboBox.Items.OfType<ComboBoxItem>().FirstOrDefault(i => i.Tag?.ToString() == _settings.DefaultAcProfile);
            _defaultBatProfileComboBox.SelectedItem = _defaultBatProfileComboBox.Items.OfType<ComboBoxItem>().FirstOrDefault(i => i.Tag?.ToString() == _settings.DefaultBatProfile);

            _defaultAcProfileComboBox.SelectionChanged += DefaultProfile_SelectionChanged;
            _defaultBatProfileComboBox.SelectionChanged += DefaultProfile_SelectionChanged;
        }

        if (_backlightTimeoutCheckBox != null)
            _backlightTimeoutCheckBox.IsChecked = (_settings.BacklightTimeout ?? "0").Equals("1", StringComparison.OrdinalIgnoreCase);

        if (_batteryLimitCheckBox != null)
            _batteryLimitCheckBox.IsChecked = (_settings.BatteryLimiter ?? "0").Equals("1", StringComparison.OrdinalIgnoreCase);

        var isCalibrating = (_settings.BatteryCalibration ?? "0").Equals("1", StringComparison.OrdinalIgnoreCase);
        IsCalibrating = isCalibrating;
        if (_startCalibrationButton != null) _startCalibrationButton.IsEnabled = !isCalibrating;
        if (_stopCalibrationButton != null) _stopCalibrationButton.IsEnabled = isCalibrating;
        if (_calibrationStatusTextBlock != null)
            _calibrationStatusTextBlock.Text = isCalibrating ? "Status: Calibrating" : "Status: Not calibrating";

        if (_bootAnimAndSoundCheckBox != null)
            _bootAnimAndSoundCheckBox.IsChecked = (_settings.BootAnimationSound ?? "0").Equals("1", StringComparison.OrdinalIgnoreCase);

        if (_lcdOverrideCheckBox != null)
            _lcdOverrideCheckBox.IsChecked = (_settings.LcdOverride ?? "0").Equals("1", StringComparison.OrdinalIgnoreCase);

        if (_hyprlandIntegrationToggleSwitch != null)
            _hyprlandIntegrationToggleSwitch.IsChecked = _settings.HyprlandIntegration;

        if (_acActiveOpacitySlider != null) _acActiveOpacitySlider.Value = _settings.AcActiveOpacity;
        if (_acInactiveOpacitySlider != null) _acInactiveOpacitySlider.Value = _settings.AcInactiveOpacity;
        if (_batActiveOpacitySlider != null) _batActiveOpacitySlider.Value = _settings.BatActiveOpacity;
        if (_batInactiveOpacitySlider != null) _batInactiveOpacitySlider.Value = _settings.BatInactiveOpacity;

        if (_acActiveOpacityText != null) _acActiveOpacityText.Text = $"{_settings.AcActiveOpacity:F2}";
        if (_acInactiveOpacityText != null) _acInactiveOpacityText.Text = $"{_settings.AcInactiveOpacity:F2}";
        if (_batActiveOpacityText != null) _batActiveOpacityText.Text = $"{_settings.BatActiveOpacity:F2}";
        if (_batInactiveOpacityText != null) _batInactiveOpacityText.Text = $"{_settings.BatInactiveOpacity:F2}";

        if (_usbChargingComboBox != null)
        {
            var usbChargingIndex = _settings.UsbCharging switch
            {
                "10" => 1,
                "20" => 2,
                "30" => 3,
                _ => 0
            };
            _usbChargingComboBox.SelectedIndex = usbChargingIndex;
        }

        if (int.TryParse(_settings.FanSpeed?.Cpu ?? "0", out var cpuSpeed))
        {
            _cpuFanSpeed = cpuSpeed;
            if (_cpuFanSlider != null) _cpuFanSlider.Value = cpuSpeed;
            if (_cpuFanTextBlock != null) _cpuFanTextBlock.Text = cpuSpeed == 0 ? "Auto" : $"{cpuSpeed}%";
        }

        if (int.TryParse(_settings.FanSpeed?.Gpu ?? "0", out var gpuSpeed))
        {
            _gpuFanSpeed = gpuSpeed;
            if (_gpuFanSlider != null) _gpuFanSlider.Value = gpuSpeed;
            if (_gpuFanTextBlock != null) _gpuFanTextBlock.Text = gpuSpeed == 0 ? "Auto" : $"{gpuSpeed}%";
        }

        var isManualMode = cpuSpeed > 0 || gpuSpeed > 0;
        _isManualFanControl = isManualMode;
        if (_manualFanSpeedRadioButton != null) _manualFanSpeedRadioButton.IsChecked = isManualMode;
        if (_autoFanSpeedRadioButton != null) _autoFanSpeedRadioButton.IsChecked = !isManualMode;

        ApplyKeyboardSettings();

        if (_lightEffectColorPicker != null) _lightEffectColorPicker.Color = Color.Parse(_effectColor);
        if (_keyBrightnessText != null) _keyBrightnessText.Text = $"{_keyboardBrightness}%";
        if (_lightSpeedTextBlock != null) _lightSpeedTextBlock.Text = _lightingSpeed.ToString();
        if (_daemonVersionText != null) _daemonVersionText.Text = $"{_settings.Version}";
        if (_driverVersionText != null) _driverVersionText.Text = $"{_settings.DriverVersion}";

        if (_laptopTypeText != null)
        {
            var type = _settings.LaptopType;
            if (!string.IsNullOrEmpty(type)) type = char.ToUpper(type[0]) + type.Substring(1).ToLower();
            _laptopTypeText.Text = type;
        }

        if (_supportedFeaturesTextBlock != null)
            _supportedFeaturesTextBlock.Text = string.Join(", ", _settings.AvailableFeatures.Select(FormatFeatureName));

        if (_modelNameText != null) _modelNameText.Text = $"Acer {GetLinuxLaptopModel()}";
        if (_linuxKernelVersionText != null) _linuxKernelVersionText.Text = $"Linux {GetLinuxKernelVersion()}";

        UpdateUIElementVisibility();
    }

    private string GetLinuxLaptopModel()
    {
        try
        {
            if (File.Exists("/sys/class/dmi/id/product_name"))
                return File.ReadAllText("/sys/class/dmi/id/product_name").Trim();

            var startInfo = new ProcessStartInfo
            {
                FileName = "dmidecode",
                Arguments = "-s system-product-name",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using var process = Process.Start(startInfo);
            process?.WaitForExit();
            return process?.StandardOutput.ReadToEnd().Trim() ?? "Unknown";
        }
        catch { return "Unknown"; }
    }

    private string GetLinuxKernelVersion()
    {
        try {
            var getKernel = new ProcessStartInfo
            {
                FileName = "uname",
                Arguments = "-r",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using var process = Process.Start(getKernel);
            process?.WaitForExit();
            return process?.StandardOutput.ReadToEnd().Trim() ?? "Unknown";
        } catch { return "Unknown"; }
    }

    private void ApplyKeyboardSettings()
    {
        if (_settings.HasFourZoneKb)
        {
            // TODO: Parse settings
        }
    }

    private async Task ShowMessageBox(string title, string message)
    {
        var box = MessageBoxManager.GetMessageBoxStandard(title, message);
        await box.ShowWindowDialogAsync(this);
    }

    public void DeveloperMode_OnClick(object? sender, RoutedEventArgs e)
    {
        EnableDevMode(true);
    }

    public void EnableDevMode(bool toEnable)
    {
        AppState.DevMode = toEnable;
        if (_powerToggleSwitch != null) _powerToggleSwitch.IsHitTestVisible = toEnable;
        ApplySettingsToUI();
    }

    private void RetryConnectionButton_OnClick(object? sender, RoutedEventArgs e)
    {
        InitializeAsync();
    }

    private void UpdateButton_OnClick(object? sender, RoutedEventArgs? e)
    {
        Process.Start(new ProcessStartInfo("xdg-open", "https://github.com/MematiBas42/Div-Acer-Manager-Max/releases") { UseShellExecute = true });
    }

    private void IssuePageButton_OnClick(object? sender, RoutedEventArgs e)
    {
        Process.Start(new ProcessStartInfo("xdg-open", "https://github.com/MematiBas42/Div-Acer-Manager-Max/issues") { UseShellExecute = true });
    }

    private void InternalsMangerWindow_OnClick(object? sender, RoutedEventArgs e)
    {
        var internalsManagerWindow = new InternalsManager(this);
        internalsManagerWindow.ShowDialog(this);
    }

    private async void ProfileButton_Checked(object? sender, RoutedEventArgs e)
    {
        if (!_isConnected || _client == null || sender is not RadioButton button || button.IsChecked != true) return;

        var profile = button.Name switch
        {
            "LowPowerProfileButton" => "low-power",
            "QuietProfileButton" => "quiet",
            "BalancedProfileButton" => "balanced",
            "PerformanceProfileButton" => "balanced-performance",
            "TurboProfileButton" => "performance",
            _ => "balanced"
        };

        await _client.SetThermalProfileAsync(profile);

        // UI update will happen via Event, but we can optimistically update UI text here too
        if (profile == "quiet")
        {
            await _client.SetFanSpeedAsync(0, 0);
            _isManualFanControl = false;
            if (!AppState.DevMode)
            {
                if (_manualFanSpeedRadioButton != null) { _manualFanSpeedRadioButton.IsChecked = false; _manualFanSpeedRadioButton.IsEnabled = false; }
                if (_autoFanSpeedRadioButton != null) _autoFanSpeedRadioButton.IsChecked = true;
                if (_maxFanSpeedRadioButton != null) _maxFanSpeedRadioButton.IsEnabled = false;
            }
            if (_thermalProfileInfoText != null) _thermalProfileInfoText.Text = "Minimizes noise, prioritizes low power and cooling.";
        }
        else
        {
            if (_maxFanSpeedRadioButton != null) _maxFanSpeedRadioButton.IsEnabled = true;
            if (_manualFanSpeedRadioButton != null) _manualFanSpeedRadioButton.IsEnabled = true;
            if (_thermalProfileInfoText != null)
                _thermalProfileInfoText.Text = profile switch
                {
                    "low-power" => "Prioritizes energy efficiency, reduces performance to extend battery life.",
                    "balanced" => "Optimal mix of performance and noise for everyday tasks.",
                    "balanced-performance" => "Maximizes speed for demanding workloads, higher fan noise",
                    "performance" => "Unleashes peak power for extreme tasks, loudest fans.",
                    _ => _thermalProfileInfoText.Text
                };
        }
    }

    private async void DefaultProfile_SelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (!_isConnected || _client == null || sender is not ComboBox comboBox || comboBox.SelectedItem is not ComboBoxItem item) return;
        var source = comboBox.Name == "DefaultAcProfileComboBox" ? "ac" : "bat";
        var profile = item.Tag?.ToString();
        if (!string.IsNullOrEmpty(profile)) await _client.SetDefaultProfilePreferenceAsync(source, profile);
    }

    private void ManualFanControlRadioBox_Click(object? sender, RoutedEventArgs e)
    {
        _isManualFanControl = true;
        if (_manualFanSpeedRadioButton != null) _manualFanSpeedRadioButton.IsChecked = true;
        if (_autoFanSpeedRadioButton != null) _autoFanSpeedRadioButton.IsChecked = false;
    }

    private void CpuFanSlider_ValueChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == Slider.ValueProperty)
        {
            _cpuFanSpeed = Convert.ToInt32(e.NewValue);
            if (_cpuFanTextBlock != null) _cpuFanTextBlock.Text = _cpuFanSpeed == 0 ? "Auto" : $"{_cpuFanSpeed}%";
        }
    }

    private void GpuFanSlider_ValueChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == Slider.ValueProperty)
        {
            _gpuFanSpeed = Convert.ToInt32(e.NewValue);
            if (_gpuFanTextBlock != null) _gpuFanTextBlock.Text = _gpuFanSpeed == 0 ? "Auto" : $"{_gpuFanSpeed}%";
        }
    }

    private async void SetManualSpeedButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null) await _client.SetFanSpeedAsync(_cpuFanSpeed, _gpuFanSpeed);
    }

    private async void AutoFanSpeedRadioButtonClick(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null)
        {
            await _client.SetFanSpeedAsync(0, 0);
            _isManualFanControl = false;
            if (_manualFanSpeedRadioButton != null) _manualFanSpeedRadioButton.IsChecked = false;
        }
    }

    private async void MaxFanSpeedRadioButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null) await _client.SetFanSpeedAsync(100, 100);
    }

    private async void StartCalibrationButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null)
        {
            await _client.SetBatteryCalibrationAsync(true);
            if (_startCalibrationButton != null) _startCalibrationButton.IsEnabled = false;
            if (_stopCalibrationButton != null) _stopCalibrationButton.IsEnabled = true;
            if (_calibrationStatusTextBlock != null) _calibrationStatusTextBlock.Text = "Status: Calibrating";
        }
    }

    private async void StopCalibrationButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null)
        {
            await _client.SetBatteryCalibrationAsync(false);
            if (_startCalibrationButton != null) _startCalibrationButton.IsEnabled = true;
            if (_stopCalibrationButton != null) _stopCalibrationButton.IsEnabled = false;
            if (_calibrationStatusTextBlock != null) _calibrationStatusTextBlock.Text = "Status: Not calibrating";
        }
    }

    private async void BatteryLimitCheckBox_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null && sender is CheckBox checkBox) await _client.SetBatteryLimiterAsync(checkBox.IsChecked ?? false);
    }

    private void KeyboardBrightnessSlider_ValueChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == Slider.ValueProperty)
        {
            _keyboardBrightness = Convert.ToInt32(e.NewValue);
            if (_keyBrightnessText != null) _keyBrightnessText.Text = $"{_keyboardBrightness}%";
        }
    }

    private async void ApplyKeyboardColorsButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null && _settings.HasFourZoneKb)
            await _client.SetPerZoneModeAsync(
                _zone1ColorPicker?.Color.ToString().Substring(3) ?? "#4287f5",
                _zone2ColorPicker?.Color.ToString().Substring(3) ?? "#ff5733",
                _zone3ColorPicker?.Color.ToString().Substring(3) ?? "#33ff57",
                _zone4ColorPicker?.Color.ToString().Substring(3) ?? "#FFFF01",
                _keyboardBrightness
            );
    }

    private void LightingSpeedSlider_ValueChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == Slider.ValueProperty)
        {
            _lightingSpeed = Convert.ToInt32(e.NewValue);
            if (_lightSpeedTextBlock != null) _lightSpeedTextBlock.Text = _lightingSpeed.ToString();
        }
    }

    private async void LightingEffectsApplyButton_Click(object? sender, RoutedEventArgs e)
    {
        if ((_isConnected && _client != null && _settings.HasFourZoneKb) || AppState.DevMode)
        {
            if (_client == null) return;
            var mode = _lightingModeComboBox?.SelectedIndex ?? 0;
            var direction = _leftToRightRadioButton?.IsChecked == true ? 1 : 2;
            var color = _lightEffectColorPicker?.Color ?? Color.Parse(_effectColor);

            await _client.SetFourZoneModeAsync(mode, _lightingSpeed, _keyboardBrightness, direction, color.R, color.G, color.B);
        }
    }

    private async void BacklightTimeoutCheckBox_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null && sender is CheckBox checkBox) await _client.SetBacklightTimeoutAsync(checkBox.IsChecked ?? false);
    }

    private async void LcdOverrideCheckBox_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null && sender is CheckBox checkBox) await _client.SetLcdOverrideAsync(checkBox.IsChecked ?? false);
    }

    private async void HyprlandIntegration_Toggled(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property.Name == "IsChecked" && _isConnected && _client != null && sender is ToggleSwitch toggleSwitch)
        {
            await _client.SetHyprlandIntegrationAsync(toggleSwitch.IsChecked ?? false);
        }
    }

    private void OpacitySlider_ValueChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == Slider.ValueProperty && sender is Slider slider)
        {
            var val = slider.Value;
            if (slider == _acActiveOpacitySlider && _acActiveOpacityText != null) _acActiveOpacityText.Text = $"{val:F2}";
            else if (slider == _acInactiveOpacitySlider && _acInactiveOpacityText != null) _acInactiveOpacityText.Text = $"{val:F2}";
            else if (slider == _batActiveOpacitySlider && _batActiveOpacityText != null) _batActiveOpacityText.Text = $"{val:F2}";
            else if (slider == _batInactiveOpacitySlider && _batInactiveOpacityText != null) _batInactiveOpacityText.Text = $"{val:F2}";
        }
    }

    private async void ApplyOpacityButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null)
        {
            await _client.SetHyprlandOpacitySettingsAsync(
                _acActiveOpacitySlider?.Value ?? 0.97,
                _acInactiveOpacitySlider?.Value ?? 0.95,
                _batActiveOpacitySlider?.Value ?? 1.0,
                _batInactiveOpacitySlider?.Value ?? 1.0
            );
        }
    }

    private async void BootSoundCheckBox_Click(object? sender, RoutedEventArgs e)
    {
        if (_isConnected && _client != null && sender is CheckBox checkBox) await _client.SetBootAnimationSoundAsync(checkBox.IsChecked ?? false);
    }

    private async void UsbChargingComboBox_OnSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (_isConnected && _client != null && _usbChargingComboBox != null)
        {
            var level = _usbChargingComboBox.SelectedIndex switch { 1 => 10, 2 => 20, 3 => 30, _ => 0 };
            await _client.SetUsbChargingAsync(level);
        }
    }

    private void LoadKeyboardBrighness()
    {
        var fourZone = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode";
        try
        {
            if (File.Exists(fourZone))
            {
                var content = File.ReadAllText(fourZone).Trim();
                var parts = content.Split(',');
                if (parts.Length > 0 && int.TryParse(parts.Last().Trim(), out var brightness))
                {
                    var slider = this.FindControl<Slider>("KeyBrightnessSlider");
                    if (slider != null) slider.Value = brightness;
                }
            }
        }
        catch { }
    }

    private string FormatFeatureName(string featureName)
    {
        if (string.IsNullOrEmpty(featureName)) return string.Empty;
        var parts = featureName.Split('_');
        var formattedParts = new List<string>();
        foreach (var part in parts)
            if (_specialFormatText.TryGetValue(part, out var format)) formattedParts.Add(format);
            else formattedParts.Add(char.ToUpper(part[0]) + part.Substring(1));
        return string.Join(" ", formattedParts);
    }

    public static class AppState { public static bool DevMode { get; set; } }

    #region INotifyPropertyChanged
    public new event PropertyChangedEventHandler? PropertyChanged;
    protected virtual void OnPropertyChanged([CallerMemberName] string? propertyName = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    protected bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }
    #endregion
}

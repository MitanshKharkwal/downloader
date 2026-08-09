using Microsoft.UI.Xaml.Controls;

namespace DownloadManagerUI;

public sealed partial class SettingsPage : Page
{
    private readonly IpcClient _ipc = new();

    public SettingsPage()
    {
        this.InitializeComponent();
        this.Loaded += SettingsPage_Loaded;
    }

    private async void SettingsPage_Loaded(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        try
        {
            var config = await _ipc.GetConfigAsync();
            DownloadDirInput.Text = config.DownloadDir;
            MaxConcurrentInput.Value = config.MaxConcurrentDownloads;
            SpeedLimitInput.Value = config.GlobalBandwidthLimit;
        }
        catch { }
    }

    private async void SaveSettings_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        try
        {
            var config = new Models.AppConfig
            {
                DownloadDir = DownloadDirInput.Text,
                MaxConcurrentDownloads = (int)MaxConcurrentInput.Value,
                GlobalBandwidthLimit = (int)SpeedLimitInput.Value
            };
            await _ipc.SetConfigAsync(config);

            SaveSuccessBar.IsOpen = true;
            await System.Threading.Tasks.Task.Delay(3000);
            SaveSuccessBar.IsOpen = false;
        }
        catch { }
    }
}

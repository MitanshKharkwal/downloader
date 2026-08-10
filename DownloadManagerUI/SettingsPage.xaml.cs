using Microsoft.UI.Xaml.Controls;

using System.Collections.ObjectModel;
using System.Linq;
using DownloadManagerUI.Models;

namespace DownloadManagerUI;

public sealed partial class SettingsPage : Page
{
    private readonly IpcClient _ipc = new();
    private ObservableCollection<ColumnConfig> _columns;

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

            _columns = new ObservableCollection<ColumnConfig>(SettingsManager.GetColumnConfigs().OrderBy(c => c.DisplayIndex));
            ColumnsListView.ItemsSource = _columns;
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

            if (_columns != null)
            {
                for (int i = 0; i < _columns.Count; i++)
                {
                    _columns[i].DisplayIndex = i;
                }
                SettingsManager.SaveColumnConfigs(_columns.ToList());
            }

            SaveSuccessBar.IsOpen = true;
            await System.Threading.Tasks.Task.Delay(3000);
            SaveSuccessBar.IsOpen = false;
        }
        catch { }
    }

    private void ColumnConfig_Changed(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        if (sender is CheckBox cb && cb.DataContext is ColumnConfig config)
        {
            config.IsVisible = cb.IsChecked ?? false;
        }
    }

}

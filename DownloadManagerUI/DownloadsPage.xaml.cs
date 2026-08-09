using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using System;
using System.Collections.ObjectModel;
using System.Linq;
using DownloadManagerUI.Models;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace DownloadManagerUI;

/// <summary>
/// The main content page displayed inside the application window.
/// Add your UI logic, event handlers, and data binding here.
/// </summary>
public sealed partial class DownloadsPage : Page
{
    public ObservableCollection<DownloadTask> Tasks { get; } = new();
    private readonly IpcClient _ipc = new();
    private DispatcherTimer _timer;

    public DownloadsPage()
    {
        InitializeComponent();

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _timer.Tick += Timer_Tick;
        _timer.Start();

        var clipTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        clipTimer.Tick += ClipTimer_Tick;
        clipTimer.Start();
    }

    private string _lastClipboardText = "";

    private async void ClipTimer_Tick(object? sender, object e)
    {
        try
        {
            var dataPackageView = Windows.ApplicationModel.DataTransfer.Clipboard.GetContent();
            if (dataPackageView.Contains(Windows.ApplicationModel.DataTransfer.StandardDataFormats.Text))
            {
                var text = await dataPackageView.GetTextAsync();
                if (text != _lastClipboardText)
                {
                    _lastClipboardText = text;
                    if (Uri.TryCreate(text, UriKind.Absolute, out Uri uriResult)
                        && (uriResult.Scheme == Uri.UriSchemeHttp || uriResult.Scheme == Uri.UriSchemeHttps || uriResult.Scheme == "magnet"))
                    {
                        var lower = text.ToLower();
                        if (lower.EndsWith(".exe") || lower.EndsWith(".zip") || lower.EndsWith(".rar") ||
                            lower.EndsWith(".7z") || lower.EndsWith(".iso") || lower.EndsWith(".mp4") ||
                            lower.EndsWith(".mkv") || lower.Contains("youtube.com") || lower.Contains("youtu.be"))
                        {
                            UrlInput.Text = text;
                            AddDownload_Click(null!, null!);
                        }
                    }
                }
            }
        }
        catch { }
    }

    private int _failCount = 0;

    private async void Timer_Tick(object? sender, object e)
    {
        try
        {
            var updatedTasks = await _ipc.ListTasksAsync();
            _failCount = 0;
            DaemonOfflineBar.IsOpen = false;

            // Remove old tasks
            var toRemove = Tasks.Where(t => !updatedTasks.Any(ut => ut.Id == t.Id)).ToList();
            foreach (var task in toRemove) Tasks.Remove(task);

            // Add or update tasks
            foreach (var ut in updatedTasks)
            {
                var existing = Tasks.FirstOrDefault(t => t.Id == ut.Id);
                if (existing == null)
                {
                    Tasks.Add(ut);
                }
                else
                {
                    if (existing.Status != "COMPLETED" && ut.Status == "COMPLETED")
                    {
                        ShowCompletionNotification(ut.Source);
                    }
                    existing.Status = ut.Status;
                    existing.DownloadedBytes = ut.DownloadedBytes;
                    existing.TotalBytes = ut.TotalBytes;
                    existing.SpeedBps = ut.SpeedBps;
                    existing.Error = ut.Error;
                    existing.FilePath = ut.FilePath;
                    existing.Priority = ut.Priority;
                }
            }
        }
        catch
        {
            _failCount++;
            if (_failCount >= 2)
            {
                DaemonOfflineBar.IsOpen = true;
            }
        }
    }

    private void ShowCompletionNotification(string fileName)
    {
        try
        {
            var notification = new Microsoft.Windows.AppNotifications.Builder.AppNotificationBuilder()
                .AddText("Download Completed")
                .AddText(fileName)
                .BuildNotification();
            Microsoft.Windows.AppNotifications.AppNotificationManager.Default.Show(notification);
        }
        catch { }
    }

    private async void AddDownload_Click(object sender, RoutedEventArgs e)
    {
        var input = UrlInput.Text.Trim();
        if (string.IsNullOrWhiteSpace(input)) return;

        UrlInput.Text = "";

        var urls = input.Split(new[] { ' ', '\r', '\n', ',' }, StringSplitOptions.RemoveEmptyEntries);

        foreach (var urlStr in urls)
        {
            var url = urlStr.Trim();
            if (string.IsNullOrWhiteSpace(url)) continue;

            if (url.Contains("youtube.com") || url.Contains("youtu.be") || url.Contains("vimeo.com"))
            {
                LoadingVideoBar.IsOpen = true;
                try
                {
                    var res = await _ipc.FetchVideoInfoAsync(url);
                    LoadingVideoBar.IsOpen = false;

                    if (res.GetProperty("ok").GetBoolean())
                    {
                        VideoTitleText.Text = res.GetProperty("title").GetString();

                        var result = await VideoFormatDialog.ShowAsync();
                        if (result == ContentDialogResult.Primary)
                        {
                            var typeIndex = VideoTypeComboBox.SelectedIndex;
                            var qualityIndex = VideoQualityComboBox.SelectedIndex;

                            string formatId = "best";
                            string ext = "mp4";

                            string heightFilter = "";
                            if (qualityIndex == 1) heightFilter = "[height<=2160]";
                            else if (qualityIndex == 2) heightFilter = "[height<=1440]";
                            else if (qualityIndex == 3) heightFilter = "[height<=1080]";
                            else if (qualityIndex == 4) heightFilter = "[height<=720]";
                            else if (qualityIndex == 5) heightFilter = "[height<=480]";
                            else if (qualityIndex == 6) heightFilter = "[height<=360]";

                            if (typeIndex == 0) // Video + Audio
                            {
                                formatId = $"bestvideo{heightFilter}+bestaudio/best";
                            }
                            else if (typeIndex == 1) // Audio Only
                            {
                                formatId = "bestaudio/best";
                                ext = "m4a";
                            }
                            else if (typeIndex == 2) // Video Only
                            {
                                formatId = $"bestvideo{heightFilter}";
                            }

                            var safeTitle = string.Join("_", VideoTitleText.Text.Split(System.IO.Path.GetInvalidFileNameChars()));
                            await _ipc.AddVideoTaskAsync(url, formatId, $"{safeTitle}.{ext}");
                        }
                    }
                }
                catch
                {
                    LoadingVideoBar.IsOpen = false;
                }
            }
            else
            {
                try { await _ipc.AddTaskAsync(url); } catch { }
            }
        }
    }

    private void UrlInput_KeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == Windows.System.VirtualKey.Enter)
        {
            AddDownload_Click(sender, null!);
        }
    }

    private async void ClearFinished_Click(object sender, RoutedEventArgs e)
    {
        try { await _ipc.ClearFinishedAsync(); } catch { }
    }

    private async void Pause_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            try { await _ipc.PauseTaskAsync(id); } catch { }
    }

    private async void Resume_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            try { await _ipc.ResumeTaskAsync(id); } catch { }
    }

    private async void PauseAll_Click(object sender, RoutedEventArgs e)
    {
        try { await _ipc.PauseAllAsync(); } catch { }
    }

    private async void ResumeAll_Click(object sender, RoutedEventArgs e)
    {
        try { await _ipc.ResumeAllAsync(); } catch { }
    }

    private async void Cancel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            try { await _ipc.CancelTaskAsync(id); } catch { }
    }

    private async void Retry_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            try { await _ipc.RetryTaskAsync(id); } catch { }
    }

    private void OpenFolder_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string path && !string.IsNullOrEmpty(path))
        {
            var folder = System.IO.Path.GetDirectoryName(path);
            if (System.IO.Directory.Exists(folder))
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = folder,
                    UseShellExecute = true,
                    Verb = "open"
                });
            }
        }
    }

    private void CopyUrl_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string url && !string.IsNullOrEmpty(url))
        {
            var dataPackage = new Windows.ApplicationModel.DataTransfer.DataPackage();
            dataPackage.SetText(url);
            Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(dataPackage);
        }
    }
}

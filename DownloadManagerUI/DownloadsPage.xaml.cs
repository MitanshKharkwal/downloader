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
    }

    private async void Timer_Tick(object? sender, object e)
    {
        var updatedTasks = await _ipc.ListTasksAsync();
        
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
                existing.Status = ut.Status;
                existing.DownloadedBytes = ut.DownloadedBytes;
                existing.TotalBytes = ut.TotalBytes;
                existing.SpeedBps = ut.SpeedBps;
                existing.Error = ut.Error;
                existing.Priority = ut.Priority;
            }
        }
    }

    private async void AddDownload_Click(object sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(UrlInput.Text))
        {
            await _ipc.AddTaskAsync(UrlInput.Text);
            UrlInput.Text = "";
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
        await _ipc.ClearFinishedAsync();
    }

    private async void Pause_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            await _ipc.PauseTaskAsync(id);
    }

    private async void Resume_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            await _ipc.ResumeTaskAsync(id);
    }

    private async void Cancel_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string id)
            await _ipc.CancelTaskAsync(id);
    }
}
